def find_between(search_string: str, first: str, last: str) -> str:
    """
    Extracts the substring between the first occurrence of 'first' and the first occurrence of 'last'
    in the 'search_string'.

    Args:
        search_string (str): The string in which to search for the substring.
        first (str): The starting string marker to look for.
        last (str): The ending string marker to look for.

    Returns:
        str: The substring between the first occurrence of 'first' and the first occurrence of 'last',
             or an empty string if either 'first' or 'last' is not found.

    Example:
        >>> find_between("Hello [this] is [an] example", "[", "]")
        'this'
    """
    try:
        # Find the starting index of the substring between 'first' and 'last'
        start = search_string.index(first) + len(first)

        # Find the ending index of the substring between 'first' and 'last'
        end = search_string.index(last, start)

        # Extract the substring between 'first' and 'last' using slicing
        return search_string[start:end]

    except ValueError:
        # If either 'first' or 'last' is not found, return message
        return "Tag not found"


#
