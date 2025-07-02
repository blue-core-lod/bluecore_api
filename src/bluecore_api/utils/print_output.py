def print_results(results, api_request, q={}, params=None):
    reset = "\033[0m"
    bold = "\033[1m"
    magenta = "\033[95m"
    cyan = "\033[96m"
    green = "\033[92m"
    blue = "\033[94m"
    yellow = "\033[93m"

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
