"""Service A — joins User + Order + LineItem to compute totals."""

from .models import LineItem, Order, User


def order_total_for_user(user_id):
    return select(LineItem).join(Order).join(User).where(User.id == user_id)


def select(*args):
    return None
