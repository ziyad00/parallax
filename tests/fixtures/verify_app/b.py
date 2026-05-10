def fetch_orders_for_user(db, uid):
    rows = db.execute(select(Order).where(Order.user_id == uid))
    return rows.scalars().all()


def select(x):
    return None
