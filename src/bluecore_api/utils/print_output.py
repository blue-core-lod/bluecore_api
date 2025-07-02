def print_results(results, api_request, q={}):
    reset = "\033[0m"
    bold = "\033[1m"
    magenta = "\033[95m"
    cyan = "\033[96m"
    green = "\033[92m"
    blue = "\033[94m"

    num_results = len(results)
    print()
    print(f"{magenta}{'#' * 71}{reset}")
    print(f"{bold}{cyan}API Request:{reset} {green}{api_request}{reset}")
    print(f"{magenta}{'-' * 71}{reset}")
    print(f"{bold}{cyan}SQL Query:\n{reset}{blue}{q}{reset}")
    print(f"{magenta}{'-' * 71}{reset}")
    print(f"{bold}{cyan}Total Works Found:{reset} {green}{num_results}{reset}")

    if num_results > 0:
        print(f"{bold}{cyan}First 10 Results:{reset}")

        for i, res in enumerate(results[:10], start=1):
            print(f"{magenta}  {i}. {reset}{res}")

    print(f"{magenta}{'#' * 71}{reset}")
    print()
