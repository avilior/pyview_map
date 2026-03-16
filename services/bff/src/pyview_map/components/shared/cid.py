"""Monotonic counter for channel instance IDs (cid).

Each browser connection gets a unique cid within the server process.
"""

import itertools

_counter = itertools.count(1)


def next_cid() -> str:
    """Return the next unique channel instance ID."""
    return str(next(_counter))
