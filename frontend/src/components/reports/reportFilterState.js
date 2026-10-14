export function stockBalanceFormFilters(request = {}) {
	return {
		fromDate: request.from_date || "",
		toDate: request.to_date || "",
		item: request.item || "",
		parentItem: request.parent_item || "",
		warehouse: request.warehouse || "",
		lot: request.lot || "",
		receivedType: request.received_type || "",
		removeZero: booleanFilter(request.remove_zero_balance_item, true),
		showAttributes: booleanFilter(request.show_variant_attributes),
		showAgeing: booleanFilter(request.show_stock_ageing_data),
		showInwardSplit: booleanFilter(request.show_inward_date_split),
	}
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
