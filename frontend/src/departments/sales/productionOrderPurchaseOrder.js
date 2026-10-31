export const PRODUCTION_ORDER_DOCTYPE = "YRP Production Order"

/** Editor source that prefills a new Purchase Order's Against / Against ID. */
export function purchaseOrderSourceFor(productionOrder) {
	return productionOrder ? { against: PRODUCTION_ORDER_DOCTYPE, against_id: productionOrder } : {}
}
