import pathlib

import rdflib


from typing import Union
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select


from bluecore.models import (
    Instance,
    Work,
    BibframeClass,
    BibframeOtherResources,
    ResourceBibframeClass,
    Version,
    TripleVectorIndex,
    VECTOR_SIZE
)

from bluecore.helpers.graph import (
    generate_embedding,
    generate_entity_graph, 
    init_graph
)

BF = rdflib.Namespace("http://id.loc.gov/ontologies/bibframe/")
MADS = rdflib.Namespace("http://www.loc.gov/mads/rdf/v1#")

OTHER_RESOURCES_SPARQL = """SELECT DISTINCT ?object
WHERE {
  ?subject ?predicate ?object .
  FILTER(isIRI(?object))
}
"""

class RecordIngester(object):

    def __init__(self, engine):
        self.errors = []
        self.session = sessionmaker(
            bind=engine,
            autocommit=False,
            autoflush=False, 
            expire_on_commit=False
        )
        self.record_graph = None
        bf_classes_stmt = select(BibframeClass)
        result = self.session.execute(bf_classes_stmt)
        self.bf_classes = {}
        for row in result.all():
            self.bf_classes[row[0].uri] = row[0]


    def __add_bf_classes__(self, 
        bf_entity: Union[Work, Instance],
        bf_graph: rdflib.Graph):
        resource_bf_classes = []
        for class_ in bf_graph.objects(
            subject=rdflib.URIRef(bf_entity.uri),
            predicate=rdflib.RDF.type):
            bf_class = self.bf_classes.get(str(class_))
            if bf_class is None and class_ in BF:
                name = str(class_).split("/")[-1]
                bf_class = BibframeClass(
                    name=name,
                    uri=str(class_)
                )
                self.session.add(bf_class)
                self.bf_classes[str(class_)] = bf_class
            resource_bf_classes.append(
                ResourceBibframeClass(
                    resource=bf_entity,
                    bf_class=bf_class
                )
            )
        if len(resource_bf_classes) > 0:
            self.session.add_all(resource_bf_classes)


    def __add_embedding__(self,
          triple: str,
          version: Version
        ):
        embedding = generate_embedding(triple, VECTOR_SIZE)
        return TripleVectorIndex(
            version=version,
            vector=embedding
        )


    def __add_embeddings__(self, **kwargs):
        resource_uri: rdflib.URIRef = kwargs["resource_uri"]
        bf_graph: rdflib.Graph = kwargs["bf_graph"]
        version: Version = kwargs["version"]
        skolemized_graph = bf_graph.skolemize(basepath=f"{resource_uri}#")
        embeddings = []
        for line in skolemized_graph.serialize(foramt='nt').splitline():
            embeddings.append(
               self.__add_embedding__(
                 line,
                 version
               )
            )
        self.session.add_all(embeddings) 

    def __add_instances__(self, work: Work) -> bool:
        instances = []
        for instance_uri in self.record_graph.subjects(
            predicate=rdflib.RDF.type,
            object=BF.Instance
        ):
            instance_graph = generate_entity_graph(self.record_graph, instance_uri)
            try:
                instance_of = instance_graph.value(
                    subject=instance_uri,
                    predicate=BF.instanceOf,
                    
                )
                if instance_of is None:
                    raise ValueError(f"Instance {instance_uri} has no instanceOf")
                if str(instance_of) != work.uri:
                    raise ValueError(f"Instance {instance_uri} is not an instance of Work {work.uri}")
                instance = self.__save_bf_resource__(
                    resource_uri=instance_uri,
                    bf_graph=instance_graph,
                    db_class=Instance
                )
            except Exception as e:
                self.errors.append(
                    {
                        "uri": instance_uri,
                        "error": str(e)
                    }
                )
                self.session.rollback()
                return False
            instance.work = work
            instances.append(instance)
        self.session.add_all(instances)
        return True

            
    def __add_other_resources__(self,    
        bf_entity: Union[Work, Instance],
        bf_graph: rdflib.Graph):
        other_resources = []
        for row in bf_graph.query(OTHER_RESOURCES_SPARQL):
            resource_uri = row[0]
            if resource_uri in BF or resource_uri in MADS or resource_uri in rdflib.RDF:
                continue
            if self.__is_work_or_instance__(resource_uri):
                continue
            other_resource = self.__get_or_add_other_resource(resource_uri)
            if other_resource:
                other_resources.append(
                    BibframeOtherResources(
                        other_resource=other_resources,
                        bibframe_resource=bf_entity
                    )
                )
        if len(other_resources) > 0:
            self.session.add_all(other_resources)
        
 
    def __is_work_or_instance__(self, uri: rdflib.URIRef) -> bool:
        for class_ in self.record_graph.objects(
            subject=uri,
            predicate=rdflib.RDF.type):
            if isinstance(class_, BF.Work) or isinstance(class_, BF.Instance):
                return True
        return False


    def __save_bf_resource__(self, **kwargs):
        resource_uri: rdflib.URIRef = kwargs["resource_uri"]
        bf_graph: rdflib.Graph = kwargs["bf_graph"] 
        db_class: Union[Work, Instance] = kwargs["db_class"]
        json_ld = bf_graph.serialize(format='json-ld')
        with self.session.begin():
            bf_entity = db_class(uri=str(resource_uri),
                                 data=json_ld)
            version = Version(resource=bf_entity,
                              data=json_ld)
            self.session.add_all([bf_entity, version])
            self.__add_bf_classes__(bf_entity, bf_graph)
            self.__add_other_resources__(bf_entity, bf_graph)
            self.__add_embeddings__(
                resource_uri=resource_uri, 
                bf_graph=bf_graph,
                version=version
            )
        self.session.commit()


    def ingest(self, file_path: pathlib.Path) -> bool:
        self.record_graph = init_graph()
        self.record_graph.parse(
            data=file_path.read_text(),
            format='json-ld'
        )
        work_uri = self.record_graph.value(
            predicate=rdflib.RDF.type,
            object=BF.Work
        )
        work_graph = generate_entity_graph(self.record_graph, work_uri)
        try:
            work = self.__save_bf_resource__(
                resource_uri=work_uri,
                bf_graph=work_graph,
                db_class=Work
            )
        except Exception as e:
            self.errors.append(
                {
                    "uri": work_uri,
                    "error": str(e)
                }
            )
            self.session.rollback()
            return False
        if not self.__add_instances__(work):
            return False
        self.session.commit()
        return True

        
                                      
       
         

