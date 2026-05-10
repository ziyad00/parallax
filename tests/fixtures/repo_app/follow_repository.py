from .models import Follow, User


class FollowRepository:
    def get_followers(self, db, user_id):
        return select(Follow, User).where(Follow.followee_id == user_id)

    def get_following(self, db, user_id):
        return select(Follow, User).where(Follow.follower_id == user_id)


def select(*args):
    class _Q:
        def where(self, *_):
            return self

    return _Q()
