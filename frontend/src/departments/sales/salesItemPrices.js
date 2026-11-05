/** Sales Item Price grid helpers: rate types are SD YRP Sales Item Price fields. */
export const DEFAULT_RATE_TYPE = "mrp_rate"

export function groupBySizes(items = []) {
	const groups = new Map()
	for (const item of items) {
		const key = item.sizes.join("|")
		if (!groups.has(key)) groups.set(key, { key, sizes: item.sizes, items: [] })
		groups.get(key).items.push(item)
	}
	return [...groups.values()]
}

export function changedPrices(original = [], edited = [], rateType = DEFAULT_RATE_TYPE) {
	const before = new Map(original.map((item) => [item.item, item]))
	const changes = {}
	for (const item of edited) {
		const old = before.get(item.item)?.prices?.[rateType] || {}
		for (const size of item.sizes) {
			const rate = Number(item.prices?.[rateType]?.[size] ?? 0)
			if (rate !== Number(old[size] ?? 0)) changes[item.variants[size]] = rate
		}
	}
	return changes
}

export function isPriceEditable(item, permissions = {}) {
	return Boolean(item && permissions.can_write)
}
