"""Pydantic models for reading a stored record in the shape bibframe-json describes.

Only what a consumer here reads is modelled, and the rest of a record stays
reachable through `model_extra`, since every model is open (`extra="allow"`).
Add a field when something needs it, not before: bibframe-json is still moving
towards v1, and every field modelled is one more thing to carry across a
version change.

These assume the current version's shape, which the reframe DAG in
bluecore-workflows keeps every stored row in: every property a list, a
reference either a URI string or a node with an `@id`, a literal either a
string or a value object. They parse; they do not judge. `bibframe_json.validate`
is what reports a record that breaks the shape's rules.

They are not the API's contract. `WorkSchema.data` stays a dict, and nothing
here should become a `response_model`, or these models turn into a second
specification of the shape alongside bibframe-json's own.
"""

from functools import cache
from typing import Annotated, Any

from bluecore_models.utils.graph import CONTEXT_URL
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    TypeAdapter,
    model_validator,
)

# The context a record has to name for these models to read it: the
# bibframe-json version bluecore-models frames with.
CURRENT_CONTEXT = CONTEXT_URL


class Text(BaseModel):
    """A literal, which keeps its language tag and datatype.

    `str()` gives the value, so a caller that only wants the text needs to know
    none of this.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    value: str = Field(alias="@value")
    language: str | None = Field(default=None, alias="@language")
    datatype: str | None = Field(default=None, alias="@type")

    @model_validator(mode="before")
    @classmethod
    def accept_a_plain_literal(cls, data: Any) -> Any:
        """A plain string, number or boolean is a literal with no tag."""
        if isinstance(data, str | int | float):
            return {"@value": str(data)}
        if (
            isinstance(data, dict)
            and "@value" in data
            and not isinstance(data["@value"], str)
        ):
            return {**data, "@value": str(data["@value"])}
        return data

    def __str__(self) -> str:
        return self.value


class Ref(BaseModel):
    """Something a record points at: an agent, a role, a vocabulary term.

    Usually only a URI, since Blue Core keeps a referenced resource's own
    description in its own row, but a record can also describe one in place,
    as a blank node carrying its label.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    uri: str | None = Field(default=None, alias="@id")
    types: list[str] = Field(default_factory=list, alias="@type")
    # Usually literals, but a node can name itself by pointing at a term.
    label: list["Value"] = Field(default_factory=list, alias="rdfs:label")

    # The properties the record states, in the order it states them.
    _order: tuple[str, ...] = PrivateAttr(default=())

    @model_validator(mode="wrap")
    @classmethod
    def remember_the_order(cls, data: Any, handler: Any) -> Any:
        """Note which properties the record states, and in what order, so that
        `properties()` can give them back as the record wrote them."""
        model = handler(data)
        if isinstance(data, dict):
            model._order = tuple(k for k in data if not k.startswith("@"))
        return model

    def states(self, name: str) -> bool:
        """Whether the record states this property at all, even as empty."""
        return name in self._order

    @property
    def stated(self) -> tuple[str, ...]:
        """The properties the record states, in its order."""
        return self._order

    def values(self, name: str) -> list["Value"]:
        """Any property, modelled or not, as literals and references.

        A modelled property comes back as its model -- a Title, a Contribution
        -- which is a Ref all the same. An unmodelled one is read as it is
        asked for, as a literal where it is one and a Ref otherwise.
        """
        field = _fields_by_alias(type(self)).get(name)
        if field is not None:
            return list(getattr(self, field))
        held = (self.model_extra or {}).get(name)
        if held is None:
            return []
        return _values().validate_python(held if isinstance(held, list) else [held])

    def properties(self) -> dict[str, list["Value"]]:
        """Every property the record states, in its order, as `values()` reads
        each one."""
        return {name: self.values(name) for name in self._order}

    @model_validator(mode="before")
    @classmethod
    def accept_a_bare_uri(cls, data: Any) -> Any:
        """A reference written as a plain string is its URI; see `@type: @id`."""
        if isinstance(data, str):
            return {"@id": data}
        return data

    @model_validator(mode="before")
    @classmethod
    def accept_a_single_type(cls, data: Any) -> Any:
        """`@type` is a keyword, so no `@container` makes it a list."""
        if isinstance(data, dict) and isinstance(data.get("@type"), str):
            return {**data, "@type": [data["@type"]]}
        return data


# Anything a property holds: a literal where it is one, a reference or a
# described node otherwise. Text is tried first, so a plain string is a
# literal; it refuses a node, which then reads as a Ref.
Value = Annotated[Text | Ref, Field(union_mode="left_to_right")]


@cache
def _values() -> TypeAdapter:
    return TypeAdapter(list[Value])


@cache
def _fields_by_alias(model: type[BaseModel]) -> dict[str, str]:
    """The model's fields, keyed by the property each one reads."""
    return {(f.alias or name): name for name, f in model.model_fields.items()}


class Contribution(Ref):
    """An agent's part in making a resource, and the roles it played."""

    agent: list[Ref] = Field(default_factory=list)
    role: list[Ref] = Field(default_factory=list)


class Identifier(Ref):
    """A number that names a resource: an ISBN, an LCCN, a local number."""

    value: list[Text] = Field(default_factory=list, alias="rdf:value")
    qualifier: list[Text] = Field(default_factory=list)
    status: list[Ref] = Field(default_factory=list)


class Classification(Ref):
    """A call number, and who assigned it and how far it is trusted."""

    portion: list[Text] = Field(default_factory=list, alias="classificationPortion")
    item_portion: list[Text] = Field(default_factory=list, alias="itemPortion")
    assigner: list[Ref] = Field(default_factory=list)
    status: list[Ref] = Field(default_factory=list)


class ProvisionActivity(Ref):
    """A publication, production, distribution or manufacture of a resource."""

    place: list[Ref] = Field(default_factory=list)
    date: list[Text] = Field(default_factory=list)
    simple_statement: list[Text] = Field(
        default_factory=list, alias="bflc:simpleStatement"
    )
    # The imprint as transcribed, which names an Instance in a link
    simple_place: list[Text] = Field(default_factory=list, alias="bflc:simplePlace")
    simple_agent: list[Text] = Field(default_factory=list, alias="bflc:simpleAgent")
    simple_date: list[Text] = Field(default_factory=list, alias="bflc:simpleDate")


class Term(Ref):
    """A controlled term: a subject or a genre/form heading.

    Named by whichever of its label, its MADS authoritative label or its code
    the record states, and tagged with the authority in `source`.
    """

    authoritative_label: list[Text] = Field(
        default_factory=list, alias="mads:authoritativeLabel"
    )
    code: list[Text] = Field(default_factory=list)
    source: list[Ref] = Field(default_factory=list)


class Title(Ref):
    """A title, or one of the variant forms of it a record carries."""

    main: list[Text] = Field(default_factory=list, alias="mainTitle")
    subtitle: list[Text] = Field(default_factory=list)
    # where a title with no mainTitle can still say what it is, as "English
    # summary title: ..." does
    note: list[Ref] = Field(default_factory=list)

    @property
    def is_variant(self) -> bool:
        """Whether this is a subtype of bf:Title -- VariantTitle, KeyTitle,
        ParallelTitle -- rather than the title proper. An untyped title counts
        as the title proper."""
        return bool(self.types) and not any(
            t.rsplit("/", 1)[-1] == "Title" for t in self.types
        )


class Resource(Ref):
    """What a Work, Instance and Hub have in common."""

    classification: list[Classification] = Field(default_factory=list)
    contribution: list[Contribution] = Field(default_factory=list)
    provision_activity: list[ProvisionActivity] = Field(
        default_factory=list, alias="provisionActivity"
    )
    subject: list[Term] = Field(default_factory=list)
    genre_form: list[Term] = Field(default_factory=list, alias="genreForm")
    identified_by: list[Identifier] = Field(default_factory=list, alias="identifiedBy")
    note: list[Ref] = Field(default_factory=list)
    title: list[Title] = Field(default_factory=list)
    # The name LC files a record under: "King, Stephen, 1947-. Dark tower".
    aap: list[Text] = Field(default_factory=list, alias="bflc:aap")
    # How a stub derived from an authority, such as FAST, names itself.
    authoritative_label: list[Text] = Field(
        default_factory=list, alias="mads:authoritativeLabel"
    )
    relation: list["Relation"] = Field(default_factory=list)
    admin_metadata: list[Ref] = Field(default_factory=list, alias="adminMetadata")
    # The Hub a Work expresses, read from either end: a Work names it here, a
    # Hub names its Works in hasExpression.
    expression_of: list["Resource"] = Field(default_factory=list, alias="expressionOf")
    series_statement: list[Text] = Field(default_factory=list, alias="seriesStatement")


class Relation(Ref):
    """How a resource relates to another: "Series", "Translation of".

    The other end is a Resource, since a record either points at one by uri
    or describes it in place, with a title and an access point of its own.
    """

    relationship: list[Ref] = Field(default_factory=list)
    associated_resource: list["Resource"] = Field(
        default_factory=list, alias="associatedResource"
    )
    series_enumeration: list[Text] = Field(
        default_factory=list, alias="seriesEnumeration"
    )


class Work(Resource):
    """The thing itself, apart from any published edition of it."""


class Instance(Resource):
    """One published edition of a Work."""

    publication_statement: list[Text] = Field(
        default_factory=list, alias="publicationStatement"
    )
    instance_of: list[Ref] = Field(default_factory=list, alias="instanceOf")


class Hub(Resource):
    """The record gathering everything said about a single work."""

    has_expression: list[Resource] = Field(default_factory=list, alias="hasExpression")


# Ref, Relation and Resource each name a class defined after them.
Ref.model_rebuild()
Relation.model_rebuild()
Resource.model_rebuild()
