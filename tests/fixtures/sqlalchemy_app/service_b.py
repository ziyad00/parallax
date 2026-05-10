"""Service B — different code, same JOIN. Should cluster with service_a."""

from .models import LineItem, Order, User


def list_user_orders(user_id, since=None):
    rows = select(User, Order, LineItem).where(Order.user_id == User.id)
    if since:
        rows = rows.where(Order.created_at > since)
    return rows


def lookup_unrelated():
    return select(User).where(User.id == 1)


def select(*args):
    return _Q()


class _Q:
    def where(self, *_):
        return self
