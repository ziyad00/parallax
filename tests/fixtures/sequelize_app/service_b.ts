import { User, Order, LineItem } from "./models";

export async function listOrders(userId: number) {
  const u = await User.findByPk(userId);
  const orders = await Order.findAll({ where: { userId: u!.id } });
  const items = await LineItem.findAll({
    where: { orderId: orders.map((o) => o.id) },
  });
  return { u, orders, items };
}
