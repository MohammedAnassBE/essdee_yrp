export function stockBalanceFormFilters(request = {}, dimensions = []) {
	return {
		fromDate: request.from_date || "",
		toDate: request.to_date || "",
		item: dimensionFilterValues(request.item),
		parentItem: dimensionFilterValues(request.parent_item),
		warehouse: request.warehouse || "",
		dimensions: Object.fromEntries(dimensions.map((dimension) => [dimension.fieldname, dimensionFilterValues(request[dimension.fieldname])])),
		removeZero: booleanFilter(request.remove_zero_balance_item, true),
		showAttributes: booleanFilter(request.show_variant_attributes),
		showAgeing: booleanFilter(request.show_stock_ageing_data),
		showInwardSplit: booleanFilter(request.show_inward_date_split),
	}
}

function dimensionFilterValues(value) {
	if (!value) return []
	if (typeof value === "string" && value.trimStart().startsWith("[")) {
		try { value = JSON.parse(value) } catch { /* A document name may start with a bracket. */ }
	}
	return (Array.isArray(value) ? value : [value]).filter(Boolean)
}

export function purchaseOrderFormFilters(request = {}) {
	return {
		item: request.item || "",
		supplier: request.supplier || "",
		purchaseOrder: request.purchase_order || "",
		deliveryLocation: request.delivery_location || "",
		lot: request.lot || "",
		status: request.status || "",
		openStatus: Object.hasOwn(request, "open_status") ? request.open_status || "" : "Open",
		docstatus: request.docstatus ?? "",
		dateBasedOn: request.date_based_on || "",
		fromDate: request.from_date || "",
		toDate: request.to_date || "",
	}
}

export function finishingPlanFormFilters(request = {}) {
	return {
		lot: request.lot || "",
		item: request.item || "",
		season: request.season || "",
		productCategory: request.product_category || "",
	}
}

export function cutBundleFormFilters(request = {}) {
	return { lot: request.lot || "", supplier: request.supplier || "" }
}

function booleanFilter(value, fallback = false) {
	if (value === undefined || value === null) return fallback
	return ![false, 0, "0", "false", ""].includes(value)
}
