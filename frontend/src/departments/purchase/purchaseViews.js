import { itemTableProblems, itemTableSaveValues, itemTableValues } from "./item/itemTables.js"

export const PURCHASE_ROUTES = {
	lots: "purchase-lots",
	lot: "purchase-lot",
	lotNew: "purchase-lot-new",
	lotEdit: "purchase-lot-edit",
	items: "purchase-items",
	itemNew: "purchase-item-new",
	item: "purchase-item",
	itemEdit: "purchase-item-edit",
	itemPrices: "purchase-item-prices",
	itemPriceNew: "purchase-item-price-new",
	itemPrice: "purchase-item-price",
	itemPriceEdit: "purchase-item-price-edit",
}

export const PURCHASE_STORE_WORKSPACE_KEYS = ["purchase_orders", "stock_transfers", "box_stickers", "excel_stickers", "reports"]
export const PURCHASE_REPORT_KEYS = ["stock_balance", "purchase_order_itemwise", "lot_cut_quantity"]

export function purchaseLauncherItems() {
	return [
		{
			key: "lots",
			label: "Lot",
			description: "Order quantities, BOM, OCR and cloth program for each lot.",
			icon: "pi pi-th-large",
			to: "/purchase/lots",
		},
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
		...itemTableValues(values),
		name: values.name || "",
		brand: values.brand || "",
		item_group: values.item_group || "",
		stock_uom: values.stock_uom || "",
		gst_hsn_code: values.gst_hsn_code || "",
		description: values.description || "",
		disabled: Number(values.disabled || 0),
		primary_attribute: values.primary_attribute || "",
		dependent_attribute: values.dependent_attribute || "",
		dependent_details: clone(values.dependent_details || []) || [],
		dependent_mapping_modified: values.dependent_mapping_modified || null,
		attributes: (clone(values.attributes || []) || []).map((row) => ({
			...row,
			values: attributeValueLabels(row.values),
		})),
	}
}

export function itemSaveValues(values = {}, options = {}) {
	const attributes = (values.attributes || []).map((row) => ({
		attribute: row.attribute,
		mapping_modified: row.mapping_modified || null,
		values: attributeValueLabels(row.values),
	}))
	const selected = new Set(attributes.map((row) => row.attribute).filter(Boolean))
	const primaryAttribute = itemPrimaryAttribute(values, attributes, selected, options)
	const dependentAttribute = selected.has(values.dependent_attribute) && values.dependent_attribute !== primaryAttribute
		? values.dependent_attribute
		: null
	return {
		...itemTableSaveValues(values),
		name: String(values.name || "").trim(),
		brand: values.brand || null,
		item_group: values.item_group || null,
		stock_uom: values.stock_uom || null,
		gst_hsn_code: values.gst_hsn_code || null,
		description: values.description || null,
		disabled: Number(values.disabled || 0),
		primary_attribute: primaryAttribute,
		dependent_attribute: dependentAttribute,
		dependent_details: dependentAttribute ? dependentDetailSaveRows(values.dependent_details, selected) : [],
		dependent_mapping_modified: values.dependent_mapping_modified || null,
		attributes,
	}
}

function itemPrimaryAttribute(values, attributes, selected, options) {
	if (selected.has(values.primary_attribute)) return values.primary_attribute
	if (attributes.length !== 1 || options.defaultSinglePrimary === false) return null
	return attributes[0].attribute || null
}

export function itemDependentValues(values = {}) {
	const row = (values.attributes || []).find((entry) => entry.attribute && entry.attribute === values.dependent_attribute)
	return row ? attributeValueLabels(row.values) : []
}

export function itemCombinationAttributes(values = {}, numericAttributes = []) {
	const numeric = new Set(numericAttributes || [])
	return (values.attributes || [])
		.map((row) => row.attribute)
		.filter((attribute) => attribute && attribute !== values.dependent_attribute && !numeric.has(attribute))
}

export function dependentDetailRows(values = {}, stockUom = "", options = {}) {
	if (!values.dependent_attribute) return []
	const previous = new Map((values.dependent_details || []).map((row) => [row.value, row]))
	const allowed = new Set((values.attributes || []).map((row) => row.attribute).filter((attribute) => attribute && attribute !== values.dependent_attribute))
	const keepAllowed = (row) => ({ ...row, attributes: (row.attributes || []).filter((attribute) => allowed.has(attribute)) })
	const stageValues = options.preserveExisting
		? [...new Set([...previous.keys(), ...itemDependentValues(values)])]
		: itemDependentValues(values)
	return stageValues.map((value) => previous.has(value) ? keepAllowed(previous.get(value)) : {
		value,
		uom: stockUom || "",
		display_name: "",
		attributes: values.primary_attribute ? [values.primary_attribute] : [],
	})
}

function dependentDetailSaveRows(rows = [], selected = new Set()) {
	return (rows || []).map((row) => ({
		value: row.value,
		uom: row.uom || null,
		display_name: String(row.display_name || "").trim(),
		attributes: (row.attributes || []).filter((attribute) => selected.has(attribute)),
	}))
}

export function itemDependentProblem(values = {}) {
	const dependent = values.dependent_attribute
	if (!dependent) return ""
	if (!itemDependentValues(values).length && !(values.dependent_mapping_modified && values.dependent_details?.length)) return `Please configure values for Dependent Attribute ${dependent}.`
	if (!values.primary_attribute) return "Please set Primary Attribute for this Item."
	if ((values.dependent_details || []).some((row) => !row.uom)) return `Set the UOM for every ${dependent} value.`
	return ""
}

export function itemCanSave(values = {}) {
	return Boolean(
		String(values.name || "").trim()
		&& values.item_group
		&& values.stock_uom
		&& (values.attributes || []).every((row) => row.attribute)
		&& !itemDependentProblem(values)
		&& !itemTableProblems(values).length,
	)
}

export function storedAttributeMappings(attributes = []) {
	return Object.fromEntries((attributes || []).filter((row) => row?.attribute).map((row) => [row.attribute, {
		mapping: row.mapping || null,
		mapping_modified: row.mapping_modified || null,
		value_count: row.value_count ?? null,
	}]))
}

export function resetAttributeRow(storedMappings = {}, attribute = "") {
	return { mapping: null, mapping_modified: null, value_count: null, ...storedMappings[attribute], attribute, values: [], new_values: [], all_values_allowed: true }
}

export function attributeValueLabels(values = []) {
	return (values || [])
		.map((value) => String(typeof value === "string" ? value : value?.label || value?.value || value?.name || "").trim())
		.filter(Boolean)
}

export function isSameAttributeValue(left, right) {
	return String(left || "").trim().toLowerCase() === String(right || "").trim().toLowerCase()
}

export function matchingAttributeValue(options = [], text = "") {
	return attributeValueLabels(options).find((label) => isSameAttributeValue(label, text)) || null
}

export function addAttributeValueDraft(draft = [], value = "") {
	const label = String(value || "").trim()
	if (!label || draft.some((entry) => isSameAttributeValue(entry, label))) return draft
	return [...draft, label]
}

export function removeAttributeValueDraft(draft = [], value = "") {
	return draft.filter((entry) => entry !== value)
}

export function attributeValuesSummary(values = []) {
	const count = (values || []).length
	if (!count) return "All"
	return count === 1 ? "1 value" : `${count} values`
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

export function itemPriceSaveAction(editor = {}) {
	const actions = editor.workflow?.save_actions || []
	return actions.length === 1 ? actions[0] : null
}

export function itemPriceApprovedBy(record = {}) {
	return [1, 2].includes(Number(record.docstatus)) ? record.approved_by || "" : ""
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
		item_price_values: activePriceTiers({ tiers: clone(values.item_price_values || []) || [] }),
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

export function itemPriceSaveValues(values = {}, attributeValueOptions = []) {
	const dependsOnAttribute = Number(values.depends_on_attribute || 0)
	const labels = new Map((attributeValueOptions || []).map((option) => [option.name, option.label]))
	const labelOf = (value) => String(labels.get(value) || value || "")
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
			const attributeOrder = labelOf(left.attribute_value).localeCompare(labelOf(right.attribute_value))
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

export const ITEM_PRICE_SECTIONS = [
	{ key: "item", label: "Item & supplier", description: "What is priced and who supplies it", icon: "pi pi-box", fields: ["item_name", "supplier", "supplier_name"] },
	{ key: "validity", label: "UOM & validity", description: "Unit and the dates this price applies", icon: "pi pi-calendar", fields: ["uom", "from_date", "to_date"] },
	{ key: "tax", label: "Tax & approval", description: "Tax slab and who approved the price", icon: "pi pi-verified", fields: ["tax", "approved_by"] },
]

export function itemPriceOverviewFields(workspace = {}) {
	const approvedBy = itemPriceApprovedBy(workspace.record || {})
	return (workspace.fields || []).map((field) => (field.fieldname === "approved_by" ? { ...field, value: approvedBy, link_name: field.link_name ?? field.value } : field))
}

export function itemPriceFieldLabel(fields, fieldname, fallback) {
	const field = Array.isArray(fields) ? fields.find((row) => row.fieldname === fieldname) : fields?.[fieldname]
	return field?.label || fallback
}

export function itemPriceDateLimit(value) {
	const match = String(value || "").match(/^(\d{4})-(\d{2})-(\d{2})/)
	return match ? new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3])) : undefined
}

export function itemPriceTierValue(field = {}, value) {
	if (value === null || value === undefined || value === "") return "—"
	const number = Number(value)
	if (!Number.isFinite(number)) return "—"
	const precision = itemPriceTierPrecision({ [field.fieldname]: field }, field.fieldname)
	const minimum = field.fieldtype === "Currency" ? Math.min(2, precision) : 0
	return number.toLocaleString("en-IN", { minimumFractionDigits: minimum, maximumFractionDigits: precision })
}

export function itemPriceAttributeHint(itemName, attributes = []) {
	if (!itemName) return "Choose an Item first"
	return attributes.length ? "" : "This Item has no attributes"
}

export function itemPriceSummaryLabel(summary) {
	if (summary === undefined || summary === null) return "…"
	if (!summary.slab_count) return "—"
	const format = (value) => Number(value).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 3 })
	if (summary.min_price === summary.max_price) return format(summary.min_price)
	return `${format(summary.min_price)} – ${format(summary.max_price)}`
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
	Expired: "pi pi-clock",
}

export function itemPriceActionIcon(action = {}) {
	return WORKFLOW_ICONS[action.action] || "pi pi-arrow-right"
}

export function itemPriceActionSeverity(action = {}) {
	if (action.action === "Reject") return "danger"
	return Number(action.next_state_doc_status) === 2 ? "warn" : "success"
}

export function itemPriceActionMessage(action = {}) {
	if (action.preview) return action.preview
	return `Move ${action.documentName || "this Item Price"} from ${action.state} to ${action.next_state}?`
}

export function itemPriceActionItems(workspace = {}, handlers = {}) {
	const workflowActions = (workspace.actions || []).map((action, index) => ({
		key: `workflow-${String(action.action || "action").toLowerCase().replaceAll(" ", "-")}`,
		label: action.label || action.action,
		icon: itemPriceActionIcon(action),
		primary: index === 0,
		severity: itemPriceActionSeverity(action) === "success" ? undefined : itemPriceActionSeverity(action),
		command: () => handlers.workflow?.(action),
	}))
	const documentActions = []
	if (workspace.can_edit) documentActions.push({
		key: "edit",
		label: "Edit",
		icon: "pi pi-pencil",
		primary: !workflowActions.length,
		command: handlers.edit,
	})
	if (workspace.can_delete) documentActions.push({
		key: "delete",
		label: "Delete",
		icon: "pi pi-trash",
		menuOnly: true,
		severity: "danger",
		command: handlers.delete,
	})
	return [...workflowActions, ...documentActions]
}
