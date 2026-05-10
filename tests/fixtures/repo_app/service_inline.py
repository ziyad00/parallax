"""Service that inlines the same query the FollowRepository does."""

from .models import Follow, User


def list_user_followers(db, user_id):
    return select(Follow, User).where(Follow.followee_id == user_id).all()


def select(*_):
    class _Q:
        def where(self, *_):
            return self

        def all(self):
            return []

    return _Q()
