"""
Conditional writes (RFC 9110 section 13) for Works and Instances.

A client that reads a resource gets an ETag with it, and can send that ETag
back in If-Match when it saves. If someone else saved in between, the ETags no
longer match and the write is refused with a 412 instead of silently replacing
the other cataloger's changes.

If-Match is optional. Clients that don't send it (Marva, sinopia_editor) keep
the old last-write-wins behavior.
"""

import hashlib

from bluecore_models.models import Instance, Work
from sqlalchemy.orm import Session, sessionmaker

IF_MATCH_DESCRIPTION = (
    "Only apply the change if the resource's current ETag is one of these, or "
    "`*` for any existing resource. Omit it to write unconditionally."
)

PRECONDITION_FAILED_RESPONSE = {
    "description": "If-Match did not match the resource's current ETag.",
    "content": {
        "application/json": {
            "schema": {
                "type": "object",
                "properties": {
                    "detail": {"type": "string"},
                    "uri": {"type": "string"},
                    "etag": {"type": "string"},
                },
            },
            "example": {
                "detail": "https://bcld.info/works/370ccc0a-3280-4036-9ca1-d9b5d5daf7df "
                "has changed since it was read",
                "uri": "https://bcld.info/works/370ccc0a-3280-4036-9ca1-d9b5d5daf7df",
                "etag": '"3f1d0c6b9a2e4f5d8c7b6a5e4d3c2b1a"',
            },
        }
    },
}


class PreconditionFailed(Exception):
    """
    Raised when If-Match doesn't name the resource's current ETag. main.py turns
    it into the 412 response, whose body carries the uri and etag alongside
    detail rather than nested inside it as an HTTPException would.
    """

    def __init__(self, uri: str, etag: str):
        super().__init__(f"{uri} has changed since it was read")
        self.uri = uri
        self.etag = etag


def resource_etag(resource: Instance | Work) -> str:
    """
    The strong ETag for a Work or Instance as it is currently stored.

    It is built from updated_at, which ResourceBase sets on every write that
    changes the resource's data. The version history is no better a source:
    add_version() copies updated_at into versions.created_at, and the
    (resource_id, created_at) unique constraint means two versions of one
    resource can never share it, so updated_at already moves on every change
    and is on the row we lock, without another query.

    A Work's hub_id and an Instance's work_id live on their own tables and can
    change (through _link in save_graph) without updated_at moving, yet they
    appear in the JSON representation, so they are part of the ETag too.

    The value is hashed so clients treat it as opaque rather than parsing a
    timestamp out of it. updated_at is written timezone-aware but read back
    naive, so the tzinfo is dropped to give the same ETag either way.
    """
    link = resource.work_id if isinstance(resource, Instance) else resource.hub_id
    updated_at = resource.updated_at.replace(tzinfo=None).isoformat()
    token = f"{resource.uri}|{updated_at}|{link}"
    return '"' + hashlib.sha256(token.encode()).hexdigest()[:32] + '"'


def composite_etag_headers(instance: Instance) -> dict[str, str]:
    """
    The ETags of the resources a CBD lets a client save, one header each.

    A CBD spans several resources, so no one ETag can stand for it (see
    with_etag in serializer.py). But an editor reads an Instance and its Work
    from it and saves each with If-Match, so it needs both, read in the same
    request as the data they vouch for: fetched separately, a save that landed
    in between would go unnoticed. Each value is an entity-tag, to send back in
    If-Match as it is.
    """
    headers = {"Bluecore-Instance-ETag": resource_etag(instance)}
    if instance.work is not None:
        headers["Bluecore-Work-ETag"] = resource_etag(instance.work)
    return headers


def if_match_satisfied(if_match: str, etag: str) -> bool:
    """
    Whether an If-Match header value admits the current ETag.

    If-Match uses strong comparison, so a weak tag (W/"...") never matches,
    and `*` matches any current representation. An empty header names no tag
    at all, so it matches nothing: a client that meant to send a precondition
    and sent a blank one should be refused, not let through.
    """
    tags = [tag.strip() for tag in if_match.split(",")]
    return "*" in tags or etag in tags


def check_if_match(resource: Instance | Work, if_match: str | None) -> None:
    """Raise PreconditionFailed if If-Match was sent and doesn't match."""
    if if_match is None:
        return
    etag = resource_etag(resource)
    if not if_match_satisfied(if_match, etag):
        raise PreconditionFailed(resource.uri, etag)


def find_for_write[R: (Instance, Work)](
    db: Session, model: type[R], uuid: str, if_match: str | None
) -> R | None:
    """
    Look up the Work or Instance a PUT is about to replace. With If-Match, the
    row is locked (SELECT ... FOR UPDATE) in db's transaction and held until the
    route commits, so the If-Match check and the save that follows can't be
    split by another writer: one that comes later blocks on the lock, and one
    that got there first has committed by the time the lock is granted, so its
    new updated_at is what gets compared. That holds for any writer of the row
    (Marva, sinopia_editor, batch ingest), not just ones that send If-Match.

    populate_existing makes the locked SELECT overwrite anything db already
    holds for the row, so the comparison is always with the locked row.
    """
    query = db.query(model).filter(model.uuid == uuid)
    if if_match is not None:
        query = query.with_for_update().populate_existing()
    return query.first()


def session_maker_for_write(
    db: Session, session_maker: sessionmaker, if_match: str | None
) -> sessionmaker:
    """
    The session_maker to hand save_graph for a PUT.

    save_graph normally opens a session of its own, on its own connection, and
    commits it. With If-Match that can't work: its UPDATE of the row
    find_for_write locked would wait on db's transaction, which is itself
    waiting for save_graph to return. So it is given sessions on db's own
    connection instead, each joining db's transaction through a SAVEPOINT.
    save_graph's commit then only releases the savepoint and its retry rolls
    back to it; the write becomes durable, and the lock is released, only when
    the route commits db.

    Without If-Match nothing changes, and save_graph gets session_maker as is.
    """
    if if_match is None:
        return session_maker
    return sessionmaker(
        bind=db.connection(),
        autoflush=False,
        join_transaction_mode="create_savepoint",
    )
