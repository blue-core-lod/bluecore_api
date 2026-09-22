"""Federated search: query Blue Core and external BIBFRAME pools side by side.

Results are grouped by source rather than merged into one ranked list, because
the sources' relevance scores are not comparable (see sources/loc.py) and a
source that fails has to stay visibly distinct from a source with no matches.

Nothing in here writes to the database. An external record becomes a Blue Core
resource only when a cataloger saves it.
"""
