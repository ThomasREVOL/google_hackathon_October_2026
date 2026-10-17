"""Walk-together matching on data/mock_users.json.

Hard filters: time window overlap, group composition preferences (e.g. same gender only).
Score: shared route overlap (length of common edges / shorter route) + profile compatibility.
Meeting point: shared node with the best safety score (lit, open venue nearby). Groups of 2-4.
"""


def find_group(G, user: dict, candidates: list[dict]) -> dict:
    """-> {group, meeting_point, shared_route}"""
    raise NotImplementedError
