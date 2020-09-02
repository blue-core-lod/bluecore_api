#!/bin/bash
echo "sleeping for 5 seconds while mongo starts"
sleep 5

echo "Initiating replica set"
mongo --host mongo:27017 <<EOF
  // Initiate replica set
  rs.initiate();
EOF

echo "Initializing db"
mongo --host mongo:27017 <<EOF
  // See https://docs.mongodb.com/manual/reference/method/
  use sinopia_repository

  db.createUser(
    {
      user: "sinopia",
      pwd: "sekret",
      roles: [
        {
          role: "readWrite",
          db: "sinopia_repository"
        }
      ]
    }
  )

  db.resources.createIndex({id: 1}, {unique: true})
  db.resources.createIndex({types: 1})
  db.resources.createIndex({group: 1})
  db.resources.createIndex({templateId: 1})
  db.resources.createIndex({bfAdminMetadataRefs: 1})
  db.resources.createIndex({bfItemRefs: 1})
  db.resources.createIndex({bfInstanceRefs: 1})
  db.resources.createIndex({bfWorkRefs: 1})
  db.resourceVersions.createIndex({id: 1, timestamp: 1}, {unique: true})
  db.resourceMetadata.createIndex({id: 1}, {unique: true})
EOF

echo "Importing resource template docs"
mongoimport --host=mongo:27017 --file=/scripts/rt_literal_property_attrs_doc.json --db=sinopia_repository --collection=resources
mongoimport --host=mongo:27017 --file=/scripts/rt_lookup_property_attrs_doc.json --db=sinopia_repository --collection=resources
mongoimport --host=mongo:27017 --file=/scripts/rt_property_template_doc.json --db=sinopia_repository --collection=resources
mongoimport --host=mongo:27017 --file=/scripts/rt_resource_property_attrs_doc.json --db=sinopia_repository --collection=resources
mongoimport --host=mongo:27017 --file=/scripts/rt_resource_template_doc.json --db=sinopia_repository --collection=resources
mongoimport --host=mongo:27017 --file=/scripts/rt_uri_property_attrs_doc.json --db=sinopia_repository --collection=resources
mongoimport --host=mongo:27017 --file=/scripts/rt_uri_doc.json --db=sinopia_repository --collection=resources
