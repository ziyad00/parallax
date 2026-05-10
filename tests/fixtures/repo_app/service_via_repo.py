"""Service that calls FollowRepository.get_followers — should cluster
with the inline service via the repo-following heuristic."""

from .follow_repository import FollowRepository


_repo = FollowRepository()


def list_user_followers_via_repo(db, user_id):
    return _repo.get_followers(db, user_id)
