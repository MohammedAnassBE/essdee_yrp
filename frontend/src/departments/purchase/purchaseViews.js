export const PURCHASE_ROUTES = {
	items: "purchase-items",
	itemNew: "purchase-item-new",
	item: "purchase-item",
	itemEdit: "purchase-item-edit",
	itemPrices: "purchase-item-prices",
	itemPriceNew: "purchase-item-price-new",
	itemPrice: "purchase-item-price",
	itemPriceEdit: "purchase-item-price-edit",
}

export const PURCHASE_ITEM_PRICE_STATUS_OPTIONS = [
	"Approval Pending",
	"Draft",
	"Approved",
	"Rejected",
	"Expired",
]

export function purchaseLauncherItems() {
	return [
		{
			key: "items",
			label: "Items",
			description: "Create purchase items and their allowed attribute values.",
			icon: "pi pi-box",
			to: "/purchase/items",
		},
		{
			key: "item_prices",
			label: "Item Prices",
			description: "Supplier prices, quantity slabs and approval.",
			icon: "pi pi-indian-rupee",
			to: "/purchase/item-prices",
		},
	]
}

export function itemCodeHint(name, brand) {
	const cleanName = String(name || "").trim()
	const cleanBrand = String(brand || "").trim()
	if (!cleanBrand || cleanName.split(" ")[0]?.toLowerCase() === cleanBrand.toLowerCase()) return cleanName
	return `${cleanBrand} ${cleanName}`.trim()
}

export function itemEditorValues(values = {}) {
	return {
		name: values.name || "",
		brand: values.brand || "",
		item_group: values.item_group || "",
		stock_uom: values.stock_uom || "",
		gst_hsn_code: values.gst_hsn_code || "",
		description: values.description || "",
		disabled: Number(values.disabled || 0),
		primary_attribute: values.primary_attribute || "",
		attributes: clone(values.attributes || []) || [],
	}
}

export function itemSaveValues(values = {}, options = {}) {
	const attributes = (values.attributes || []).map((row) => ({
		attribute: row.attribute,
		mapping_modified: row.mapping_modified || null,
		values: clone(row.values || []) || [],
	}))
	const selectedAttributes = new Set(attributes.map((row) => row.attribute).filter(Boolean))
	const primaryAttribute = attributes.length === 1
		? (selectedAttributes.has(values.primary_attribute)
			? values.primary_attribute
			: (options.defaultSinglePrimary === false ? null : attributes[0].attribute || null))
		: (selectedAttributes.has(values.primary_attribute) ? values.primary_attribute : null)
	return {
		name: String(values.name || "").trim(),
		brand: values.brand || null,
		item_group: values.item_group || null,
		stock_uom: values.stock_uom || null,
		gst_hsn_code: values.gst_hsn_code || null,
		description: values.description || null,
		disabled: Number(values.disabled || 0),
		primary_attribute: primaryAttribute,
		attributes,
	}
}

export function itemAttributeSearchScope(attributesLocked, currentName) {
	return attributesLocked ? String(currentName || "") || null : null
}

export function withSelectedAttributeValues(selected = [], options = []) {
	const merged = new Map()
	for (const option of [...options, ...selected]) {
		const key = option?.name || option?.label
		if (key && !merged.has(key)) merged.set(key, option)
	}
	return [...merged.values()]
}

export function stageItemAttributeValue(selected = [], options = [], value = "") {
	const label = String(value || "").trim()
	const values = [...new Set((selected || []).map((entry) => String(entry || "").trim()).filter(Boolean))]
	if (label && !values.includes(label)) values.push(label)
	return {
		values,
		availableValues: withSelectedAttributeValues(
			values.map((entry) => ({ name: entry, label: entry })),
			options || [],
		),
	}
}

export function itemAttributeCountLabel(value) {
	if (value === null || value === undefined || value === "") return "…"
	const count = Number(value)
	return Number.isFinite(count) && count > 0 ? String(count) : "None"
}

export function itemKindLabel(attributes = []) {
	const names = attributes.map((row) => String(row?.attribute || "").trim()).filter(Boolean)
	return names.length ? `Item with variants (${names.join(" × ")})` : "Plain item"
}

export function itemListFilters(mode = "purchase") {
	const filters = [["variant_of", "is", "not set"]]
	if (mode === "disabled") return [...filters, ["disabled", "=", 1]]
	if (mode === "purchase") filters.push(["is_purchase_item", "=", 1])
	return [...filters, ["disabled", "=", 0]]
}

export function itemRoutePath(name) {
	return `/web/purchase/items/${encodeURIComponent(name)}`
}

export function itemPricePath(name) {
	return `/web/purchase/item-prices/${encodeURIComponent(name)}`
}

export function itemPriceListInitialStatus(capability = {}) {
	return capability.can_submit ? "Approval Pending" : ""
}

export function canSendItemPriceForApproval(editor = {}) {
	return Boolean(editor.workflow?.can_send_for_approval)
}

export function savedItemPriceIdentity(workspace = {}) {
	return {
		name: String(workspace.record?.name || ""),
		modified: workspace.record?.modified || "",
	}
}

export function captureRecordTarget(record = {}, fallbackName = "") {
	return {
		name: String(record.name || fallbackName || ""),
		modified: record.modified || "",
	}
}

export function isCurrentRecordRequest(requestedName, currentName, sequence, currentSequence) {
	return String(requestedName || "") === String(currentName || "") && sequence === currentSequence
}

function clone(value) {
	return JSON.parse(JSON.stringify(value ?? null))
}

export function itemPriceEditorValues(values = {}) {
	return {
		item_name: values.item_name || "",
		supplier: values.supplier || "",
		uom: values.uom || "",
		tax: values.tax || "",
		from_date: values.from_date || "",
		to_date: values.to_date || "",
		depends_on_attribute: Number(values.depends_on_attribute || 0),
		attribute: values.attribute || "",
		item_price_values: clone(values.item_price_values || []) || [],
	}
}

export function itemPriceTierPrecision(fields = {}, fieldname) {
	const precision = Number(fields?.[fieldname]?.precision)
	return Number.isInteger(precision) && precision >= 0 ? precision : (fieldname === "lead_time" ? 0 : 3)
}

export function itemPriceEditorRequestKey({ name = "", routeName = "", item = "", supplier = "" } = {}) {
	return JSON.stringify({
		name: String(name || ""),
		routeName: String(routeName || ""),
		item: name ? "" : String(item || ""),
		supplier: name ? "" : String(supplier || ""),
	})
}

export function itemPriceSaveValues(values = {}) {
	const dependsOnAttribute = Number(values.depends_on_attribute || 0)
	return {
		...itemPriceEditorValues(values),
		depends_on_attribute: dependsOnAttribute,
		attribute: dependsOnAttribute ? values.attribute || null : null,
		item_price_values: (values.item_price_values || []).map((row) => ({
			moq: row.moq,
			price: row.price,
			lead_time: row.lead_time,
			attribute_value: dependsOnAttribute ? row.attribute_value || null : null,
		})).sort((left, right) => {
			const attributeOrder = String(left.attribute_value || "").localeCompare(String(right.attribute_value || ""))
			return attributeOrder || Number(left.moq || 0) - Number(right.moq || 0)
		}),
	}
}

export function itemPriceAttributeValues(attributes = [], attribute = "") {
	return attributes.find((row) => row.attribute === attribute)?.values || []
}

export function itemPriceCanSave(values = {}) {
	if (!values.item_name || !values.supplier || !values.tax || !values.from_date) return false
	const usesAttribute = Boolean(Number(values.depends_on_attribute))
	if (usesAttribute && !values.attribute) return false
	const rows = values.item_price_values || []
	if (!rows.length) return false
	return rows.every((row) => (
		row.moq !== null && row.moq !== undefined && row.moq !== ""
		&& row.price !== null && row.price !== undefined && row.price !== ""
		&& row.lead_time !== null && row.lead_time !== undefined && row.lead_time !== ""
		&& (!usesAttribute || Boolean(row.attribute_value))
	))
}

export function itemPriceGroups(rows = []) {
	const groups = new Map()
	for (const row of rows) {
		const key = row.attribute_value || "__all__"
		if (!groups.has(key)) groups.set(key, {
			key,
			label: row.attribute_value_label || (key === "__all__" ? "All quantities" : key),
			rows: [],
		})
		groups.get(key).rows.push(row)
	}
	return [...groups.values()]
		.map((group) => ({
			...group,
			rows: [...group.rows].sort((left, right) => Number(left.moq || 0) - Number(right.moq || 0)),
		}))
		.sort((left, right) => left.label.localeCompare(right.label))
}

export function activePriceTiers(price = {}) {
	return [...(price.tiers || price.item_price_values || [])].sort((left, right) => {
		const leftLabel = String(left.attribute_value_label || left.attribute_value || "")
		const rightLabel = String(right.attribute_value_label || right.attribute_value || "")
		return leftLabel.localeCompare(rightLabel) || Number(left.moq || 0) - Number(right.moq || 0)
	})
}

const WORKFLOW_ICONS = {
	Submit: "pi pi-send",
	Approve: "pi pi-check-circle",
	Reject: "pi pi-times-circle",
	Expire: "pi pi-clock",
}

export function itemPriceActionItems(workspace = {}, handlers = {}) {
	const workflowActions = (workspace.actions || []).map((action, index) => ({
		key: `workflow-${String(action.action || "action").toLowerCase().replaceAll(" ", "-")}`,
		label: action.label || action.action,
		icon: WORKFLOW_ICONS[action.action] || "pi pi-arrow-right",
		primary: index === 0,
		menuOnly: index > 0,
		command: () => handlers.workflow?.(action),
	}))
	const documentActions = []
	if (workspace.can_edit) documentActions.push({
		key: "edit",
		label: "Edit",
		icon: "pi pi-pencil",
		menuOnly: true,
		command: handlers.edit,
	})
	if (workspace.can_delete) documentActions.push({
		key: "delete",
		label: "Delete",
		icon: "pi pi-trash",
		menuOnly: true,
		command: handlers.delete,
	})
	return [...workflowActions, ...documentActions]
}
