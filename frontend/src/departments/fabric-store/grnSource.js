const SOURCE_KEYS = ["work_order", "purchase_order", "against_id", "duplicate_from"]

/** Source context a new GRN loads from; the same keys the Work Order and Purchase Order Make GRN paths pass. */
export function goodsReceivedNoteSource(against, againstId, deliveryChallan = "") {
	if (!againstId) return {}
	if (against === "Purchase Order") return { purchase_order: againstId }
	return deliveryChallan ? { work_order: againstId, delivery_challan: deliveryChallan } : { work_order: againstId }
}

/** True when a new GRN has a source to load from, so it does not need the source picker. */
export function hasGoodsReceivedNoteSource(source) {
	return SOURCE_KEYS.some((key) => Boolean(source?.[key]))
}
