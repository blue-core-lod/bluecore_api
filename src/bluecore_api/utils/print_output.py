"""
################################################################################
##  Renders the output of SQL and API requests in console  ##
#############################################################

Example Output:
#######################################################################
API Request:
http://localhost:3000/search/?type=works&mainTitle=%22Le%20mal%20joli%22
-----------------------------------------------------------------------
SQL Parameters:
{'mainTitle': 'Le mal joli', 'type': 'works'}
-----------------------------------------------------------------------
SQL Query:
SELECT works.id AS works_id, resource_base.id AS resource_base_id,
resource_base.type AS resource_base_type, resource_base.data AS resource_base_data,
resource_base.uuid AS resource_base_uuid, resource_base.uri AS resource_base_uri,
resource_base.created_at AS resource_base_created_at,
resource_base.updated_at AS resource_base_updated_at
FROM resource_base JOIN works ON resource_base.id = works.id
WHERE (data -> 'title' ->> 'mainTitle') = %(mainTitle)s AND type = %(type)s
-----------------------------------------------------------------------
Total Works Found: 1
First 10 Results:
  1. <Work https://bcld.info/works/23087177-9395-4e1e-ae1e-d166f3fcabe2>
#######################################################################
"""
def print_results(results, api_request, q={}, params=None):
    reset = "\033[0m"
    bold = "\033[1m"
    magenta = "\033[95m"
    green = "\033[92m"
    blue = "\033[94m"

    num_results = len(results)
    print()
    print(f"{magenta}{'#' * 71}{reset}")
    print(f"{bold}{magenta}API Request:{reset}\n{green}{api_request}{reset}")
    print(f"{magenta}{'-' * 71}{reset}")

    if params:
        print(f"{bold}{magenta}SQL Parameters:{reset}\n{blue}{params}{reset}")
        print(f"{magenta}{'-' * 71}{reset}")

    print(f"{bold}{magenta}SQL Query:{reset}\n{blue}{q}{reset}")

    print(f"{magenta}{'-' * 71}{reset}")
    print(f"{bold}{magenta}Total Works Found:{reset} {green}{num_results}{reset}")

    if num_results > 0:
        print(f"{bold}{magenta}First 10 Results:{reset}")
        for i, res in enumerate(results[:10], start=1):
            print(f"{magenta}  {i}. {reset}{res}")

    print(f"{magenta}{'#' * 71}{reset}")
    print()
