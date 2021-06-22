
def basename(path):
    """
    Gets the last component of a path.

    Arguments:
    path -- File path.
    """
    return path.replace("\\", "/").split("/")[-1]


def join(*paths):
    """
    Joins multiple paths into a single path.

    Arguments:
    *paths -- path components
    """
    path = ""
    for component in paths:
        path += ("/" if path and not path.endswith("/") else "") + component.replace(
            "\\", "/"
        )
    return path
