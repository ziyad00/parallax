def get_user_orders(db, user_id):
    rows = db.execute(select(Order).where(Order.user_id == user_id))
    return rows.scalars().all()


def select(x):
    return None
