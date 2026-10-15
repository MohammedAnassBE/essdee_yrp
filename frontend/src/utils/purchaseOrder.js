export function formatIsoDate(value) {
	const match = String(value || "").match(/^(\d{4})-(\d{2})-(\d{2})$/)
	return match ? `${match[3]}-${match[2]}-${match[1]}` : String(value || "")
}

export function addDaysToIsoDate(value, days) {
	const match = String(value || "").match(/^(\d{4})-(\d{2})-(\d{2})$/)
	if (!match) return ""
	const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])))
	date.setUTCDate(date.getUTCDate() + Number(days || 0))
	return date.toISOString().slice(0, 10)
}

export function validatePurchaseOrderItems(form, groups) {
	for (const group of groups || []) {
		for (const row of group.items || []) {
			const item = row.name || row.item_code || "This item"
			const requiredBy = row.schedule_date || form?.schedule_date || ""
			if (!requiredBy) {
				return `${item} needs a Required By date. Edit this item and select the date.`
			}
			if (form?.transaction_date && requiredBy < form.transaction_date) {
				return `${item} has Required By ${formatIsoDate(requiredBy)}, which is before Order Date ${formatIsoDate(form.transaction_date)}. Edit this item and choose a Required By date on or after the Order Date.`
			}
		}
	}
	return ""
}

export function purchaseOrderPriceWarning(status) {
	if (status === "missing") return "No approved price for this supplier"
	if (status === "ambiguous") return "Multiple approved prices for this supplier"
	if (status === "no_slab") return "No approved price slab for this quantity"
	return ""
}

export function createPurchaseOrderPricePath(item, supplier) {
	return `/purchase/item-prices/new?item=${encodeURIComponent(item || "")}&supplier=${encodeURIComponent(supplier || "")}`
}

export function loadPurchaseOrderGroups(groups) {
	return JSON.parse(JSON.stringify(groups || []))
}

export function createPurchaseOrderPreviewController(onPendingChange = () => {}) {
	let revision = 0
	let pendingCount = 0
	return {
		async run(task) {
			const requestRevision = ++revision
			pendingCount += 1
			onPendingChange(true)
			try {
				const value = await task()
				return { stale: requestRevision !== revision, value }
			} catch (error) {
				if (requestRevision !== revision) return { stale: true, value: undefined }
				throw error
			} finally {
				pendingCount -= 1
				onPendingChange(pendingCount > 0)
			}
		},
		revise() { return ++revision },
		pending() { return pendingCount > 0 },
	}
}

export function createPurchaseOrderDraftRevision() {
	let revision = 0
	return {
		revise() { return ++revision },
		current() { return revision },
		isCurrent(candidate) { return candidate === revision },
	}
}

export function currentPurchaseOrderPreview(request, { required = false } = {}) {
	if (!request?.stale) return request?.value
	if (required) throw new Error("Purchase Order pricing changed while the preview was running. Please try again.")
	return null
}

export function applyPurchaseOrderPricePreview(groups, preview, options = {}) {
	const updated = JSON.parse(JSON.stringify(groups || []))
	const results = new Map((preview?.rows || []).map((row) => [`${row.group_index}:${row.item_index}`, row]))
	for (const [groupIndex, group] of updated.entries()) {
		for (const [itemIndex, row] of (group.items || []).entries()) {
			const result = results.get(`${groupIndex}:${itemIndex}`) || { status: "missing", values: {} }
			row.price_status = result.status || "missing"
			row.price_warning = purchaseOrderPriceWarning(row.price_status)
			row.price_create_url = row.price_warning && options.canCreateItemPrice
				? createPurchaseOrderPricePath(row.name, options.supplier)
				: ""
			row.price_lead_time_days = result.lead_time_days ?? null
			const discount = Number(row.discount_percentage || 0)
			const activeValues = Object.entries(row.values || {}).filter(([, value]) => Number(value?.qty || 0) > 0)
			const allActiveValuesResolved = activeValues.length > 0
				&& activeValues.every(([valueKey]) => result.values?.[valueKey]?.status === "ok")
			if (allActiveValuesResolved) row.tax = result.tax || ""
			for (const [valueKey, value] of Object.entries(row.values || {})) {
				const valueResult = result.values?.[valueKey]
				const qty = Number(value?.qty || 0)
				value.price_status = valueResult?.status || row.price_status
				value.price_tier = valueResult?.tier || null
				if (valueResult?.status === "ok") {
					value.rate = Number(valueResult.rate || 0)
					value.tax = valueResult.tax ?? result.tax ?? ""
				} else {
					if (value.rate === undefined || value.rate === null) value.rate = 0
					if (value.tax === undefined || value.tax === null) value.tax = row.tax || ""
				}
				const taxRate = Number(valueResult?.status === "ok"
					? valueResult.tax_rate ?? result.tax_rate ?? 0
					: value.tax ?? row.tax ?? 0)
				value.amount = qty * value.rate
				value.discount_amount = value.amount * discount / 100
				value.tax_amount = (value.amount - value.discount_amount) * taxRate / 100
				value.total_amount = value.amount - value.discount_amount + value.tax_amount
			}
		}
	}
	return updated
}

export function applyPurchaseOrderPriceSchedule(groups, options = {}) {
	const updated = loadPurchaseOrderGroups(groups)
	for (const group of updated) {
		for (const row of group.items || []) {
			if (row.fetch_delivery_date && row.price_status === "ok") {
				if (row.price_lead_time_days === undefined || row.price_lead_time_days === null || Number(row.price_lead_time_days) < 0) {
					throw new Error(`No Item Price lead time is configured for ${row.name}. Turn off Item Price lead time and select Required By manually.`)
				}
				row.schedule_date = addDaysToIsoDate(options.transactionDate, row.price_lead_time_days)
			}
			row.schedule_date ||= options.defaultRequiredBy || ""
			row.expected_delivery_date = row.schedule_date
		}
	}
	return updated
}
