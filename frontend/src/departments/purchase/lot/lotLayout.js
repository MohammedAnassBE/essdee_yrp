import { documentOverviewHasValue, formatDocumentOverviewValue } from "../../../utils/documentOverview.js"
import { linkFieldTarget } from "../../../utils/linkTarget.js"

export const LOT_TABS = [
	{ key: "lot", label: "Lot" },
	{ key: "fabric", label: "Cloth Program" },
	{ key: "dia-conversions", label: "Actual Dia Conversions" },
	{ key: "bom", label: "BOM" },
]

const LEGACY_LOT_TABS = {
	details: { tab: "lot" },
	"order-items": { tab: "lot" },
	"order-details": { tab: "lot", section: "order-details" },
	ppo: { tab: "lot", section: "ppo" },
	ocr: { tab: "lot", section: "ocr" },
}

export const LOT_SECTIONS = [
	{ key: "order-details", eyebrow: "Order details", label: "Lot Order Details" },
	{ key: "fabric-details", eyebrow: "Fabric", label: "Fabric Details" },
	{ key: "ipd", eyebrow: "From IPD", label: "Derived from Item Production Detail" },
	{ key: "ppo", eyebrow: "PPO", label: "Linked Production Order" },
	{ key: "transfer", eyebrow: "Transfer", label: "Lot Transfer" },
	{ key: "ocr", eyebrow: "OCR", label: "OCR Detail" },
]

export const LOT_HEADER_GROUPS = [
	{
		key: "order",
		label: "Lot & order",
		icon: "pi pi-shopping-bag",
		description: "Order, item and ownership",
		fields: ["production_order", "item", "production_detail", "season", "assigned_person", "expected_delivery_date"],
	},
	{
		key: "production",
		label: "Production settings",
		icon: "pi pi-cog",
		description: "Sizes, version and capacity",
		fields: ["size_set_colour", "primary_item_attribute", "version", "capacity_planning"],
	},
]
export const LOT_ORDER_DETAIL_FIELDS = ["pack_in_stage", "packing_uom", "total_order_quantity"]
export const LOT_IPD_FIELDS = ["uom", "pack_in_stage", "pack_out_stage", "tech_pack_version", "pattern_version", "packing_combo", "cloth_excess_percentage"]
export const LOT_TRANSFER_FIELDS = ["has_transferred", "is_transferred", "transferred_lot"]
export const LOT_BOM_FIELDS = ["total_quantity", "last_calculated_time"]
export const LOT_FIELD_LABELS = {
	uom: "UOM", pack_in_stage: "Pack In Stage", pack_out_stage: "Pack Out Stage", packing_uom: "Packing UOM",
	version: "Version", cloth_excess_percentage: "Cloth Excess Percentage", total_order_quantity: "Total Order Quantity",
	tech_pack_version: "Tech Pack Version", pattern_version: "Pattern Version", packing_combo: "Packing Combo",
	has_transferred: "Has Transferred", is_transferred: "Is Transferred", transferred_lot: "Transferred Lot",
	total_quantity: "Total Quantity", last_calculated_time: "Last Calculated Time",
}

/** Maps a `?tab=` value, including pre-restructure keys, to a visible tab plus the section to expand. */
export function resolveLotTab(key, tabs = LOT_TABS) {
	const target = LEGACY_LOT_TABS[key] || { tab: key }
	if (!tabs.some((tab) => tab.key === target.tab)) return { tab: "lot", section: "" }
	return { tab: target.tab, section: target.section || "" }
}

/** Ordered collapsible sections whose `visible[key]` is truthy, with optional counts. */
export function lotSections(visible = {}, counts = {}) {
	return LOT_SECTIONS.filter((section) => visible[section.key]).map((section) => ({ ...section, count: counts[section.key] ?? null }))
}

export function hasLotOcr(ocr) {
	return Boolean(ocr) && (Object.keys(ocr.processes || {}).length > 0 || Number(ocr.total_dispatch) > 0)
}

export function hasLotTransfer(values = {}) {
	return LOT_TRANSFER_FIELDS.some((fieldname) => Boolean(values[fieldname]))
}

export function lotEditorTabs(isNew) {
	return isNew ? LOT_TABS.slice(0, 1) : LOT_TABS
}

export function orderDetailRowCount(groups = []) {
	return groups.reduce((sum, group) => sum + (group.items?.length || 0), 0)
}

export function toggleSection(expanded, key) {
	return expanded.includes(key) ? expanded.filter((value) => value !== key) : [...expanded, key]
}

/** Page facts for `fieldnames`, in order; missing ones are skipped unless `includeEmpty`. */
export function workspaceFacts(fields = [], fieldnames = [], includeEmpty = false) {
	const byName = new Map(fields.map((field) => [field.fieldname, field]))
	return fieldnames.flatMap((fieldname) => {
		const field = byName.get(fieldname) || (includeEmpty ? { fieldname, label: LOT_FIELD_LABELS[fieldname] || fieldname, value: null } : null)
		if (!field) return []
		const link = documentOverviewHasValue(field.value) ? linkFieldTarget(field) : null
		return [{ key: fieldname, label: field.label, value: formatDocumentOverviewValue(field), link }]
	})
}

export function workspaceValues(fields = []) {
	return Object.fromEntries(fields.map((field) => [field.fieldname, field.value]))
}

/** Editor facts from the derived values: raw names link UOM, stage values and transferred Lot. */
export function derivedFacts(derived = {}, fieldnames = []) {
	return fieldnames.map((fieldname) => ({
		key: fieldname,
		label: LOT_FIELD_LABELS[fieldname] || fieldname,
		value: derivedDisplay(fieldname, derived[fieldname]),
		link: derivedTarget(derived, fieldname),
	}))
}

function derivedDisplay(fieldname, value) {
	if (["has_transferred", "is_transferred"].includes(fieldname)) return value ? "Yes" : "No"
	return value === null || value === undefined || value === "" ? "—" : value
}

function derivedTarget(derived, fieldname) {
	const value = derived[fieldname]
	if (!value) return null
	if (["uom", "packing_uom"].includes(fieldname)) return { doctype: "UOM", name: value }
	if (fieldname === "transferred_lot") return { doctype: "SD YRP Lot", name: value }
	const stageName = derived[`${fieldname}_name`]
	if (["pack_in_stage", "pack_out_stage"].includes(fieldname) && stageName) return { doctype: "YRP Item Attribute Value", name: stageName }
	return null
}
