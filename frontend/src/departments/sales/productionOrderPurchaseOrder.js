export const PRODUCTION_ORDER_DOCTYPE = "YRP Production Order"

/** Editor source for a new Purchase Order raised against one or more Production Orders. */
export function purchaseOrderSourceFor(productionOrders = []) {
	const names = productionOrders.filter(Boolean)
	return names.length ? { production_orders: names } : {}
}
