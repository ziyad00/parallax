import { User, Order, LineItem } from "./models";

export function totalForUser(userId: number) {
  return User.findByPk(userId).then((u) =>
    Order.findAll({ where: { userId } }).then((orders) =>
      LineItem.findAll({ where: { orderId: orders.map((o) => o.id) } })
    )
  );
}
