import json

"""
################################################################################
# Renders the output of SQL and API requests in console with query performance #
################################################################################
# Shows the API request URL, SQL parameters, the raw SQL query,
# any EXPLAIN ANALYZE plan, indexed search params, total results found,
# first 10 results, and the time taken in seconds if given.
# Call this after executing your query to debug or monitor your API behavior.
# ------------------------------------------------------------------------------
"""


def print_results(
    results,
    api_request,
    q={},
    params=None,
    indexed_search_params=None,
    explain=None,
    total=None,
    page=None,
    size=None,
    pages=None,
):
    reset = "\033[0m"
    bold = "\033[1m"
    magenta = "\033[95m"
    green = "\033[92m"
    blue = "\033[94m"

    """
    # --------------------------------------------------------------------------
    # Calculate total number of results
    # --------------------------------------------------------------------------
    """
    num_results = len(results)

    print()
    print(f"{magenta}{'#' * 71}{reset}")
    print(f"{bold}{magenta}API Request:{reset}\n{green}{api_request}{reset}")
    print(f"{magenta}{'-' * 71}{reset}")

    """
    # --------------------------------------------------------------------------
    # Render any indexed search parameters (with stripped quotes)
    # --------------------------------------------------------------------------
    """
    if indexed_search_params:
        indexed_present = {
            k: (
                [v_i.strip('"').strip("'") for v_i in v]
                if isinstance(v, list)
                else str(v).strip('"').strip("'")
            )
            for k, v in indexed_search_params.__dict__.items()
            if v
        }

        if indexed_present:
            print(
                f"{bold}{magenta}INDEXED SEARCH PARAMS:{reset}\n{blue}{json.dumps(indexed_present, indent=2)}{reset}"
            )
            print(f"{magenta}{'-' * 71}{reset}")

    """
    # --------------------------------------------------------------------------
    # Render SQL parameters if provided
    # --------------------------------------------------------------------------
    """
    if params:
        print(f"{bold}{magenta}SQL Parameters:{reset}\n{blue}{params}{reset}")
        print(f"{magenta}{'-' * 71}{reset}")

    """
    # --------------------------------------------------------------------------
    # Render the raw SQL query
    # --------------------------------------------------------------------------
    """
    print(f"{bold}{magenta}SQL Query:{reset}\n{blue}{q}{reset}")
    print(f"{magenta}{'-' * 71}{reset}")

    """
    # --------------------------------------------------------------------------
    # Render EXPLAIN ANALYZE if provided
    # --------------------------------------------------------------------------
    """
    if explain:
        print(f"{bold}{magenta}EXPLAIN ANALYZE:{reset}")
        for line in explain:
            print(f"{blue}{line}{reset}")
        print(f"{magenta}{'-' * 71}{reset}")

    """
    # --------------------------------------------------------------------------
    # Show total found and first 10 results
    # --------------------------------------------------------------------------
    """
    print(f"{bold}{magenta}Total Works Found:{reset} {green}{total}{reset}")
    print(f"{bold}{magenta}Current Page:{reset} {page}")
    print(f"{bold}{magenta}Set Page Size:{reset} {size}")
    print(f"{bold}{magenta}Total Pages:{reset} {pages}")

    if num_results > 0:
        print(f"{bold}{magenta}First 5 Results:{reset}")
        for i, res in enumerate(results[:5], start=1):
            uri = getattr(res, "uri", None)
            typename = getattr(res, "type", None)
            if not uri and hasattr(res, "data") and isinstance(res.data, dict):
                uri = res.data.get("@id")
            # Fallback: use type field if present else ResourceBaseSchema
            classname = typename or res.__class__.__name__
            if uri:
                print(f"{magenta}  {i}.{reset} {blue}<{classname} {uri}>{reset}")
            else:
                print(f"{magenta}  {i}.{reset} {blue}{res}{reset}")

    print(f"{magenta}{'#' * 71}{reset}")
    print()
