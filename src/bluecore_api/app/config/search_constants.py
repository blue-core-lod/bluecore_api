"""
###################################################################
##  Known top-level keys that map to direct scalar JSONB fields  ##
###################################################################
"""

TOP_LEVEL_KEYS = {
    "dimensions",
    "code",
    "status",
}

"""
############################################################
##  Mappings for known nested keys for JSONB @> matching  ##
############################################################
"""
MAPPED_KEYS = {
    "mainTitle": ["title", "mainTitle"],
    "subtitle": ["title", "subtitle"],
    "nonSortNum": ["title", "bflc:nonSortNum"],
    "extent": ["extent", "http://www.w3.org/2000/01/rdf-schema#label"],
    "context_bflc": ["@context", "bflc"],
    "context_mads": ["@context", "mads"],
    "context_vocab": ["@context", "@vocab"],
}


"""
########################################################
##  Indexed fields that don't need JSONPath fallback  ##
########################################################
"""
INDEXED_FACETS = {
    "type",
    "rdf_id",
    "rdf_type",
    "mainTitle",
    "derivedFrom",
    "uuid",
    "uri",
    "key",
    "value",
}
