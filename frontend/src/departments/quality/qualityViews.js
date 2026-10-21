export const INSPECTION_DOCTYPE = "SD YRP Essdee Quality Inspection"
export const INSPECTION_LIST_COLUMNS = [
	"inspection_type", "against_id", "lot", "item", "supplier", "result", "posting_date",
]
export const INSPECTION_EDITABLE_FIELDS = [
	"against_id", "is_third_party", "third_party_supplier", "inspection_type", "unit_name",
	"offer_qty", "description", "checking_level", "major_aql_level", "minor_aql_level",
	"major_defect_found", "minor_defect_found", "spi_found", "result", "measurement_deviation",
	"remarks_and_suggestions", "upload_quality_approval_sheet",
]

const ACTIONS = [
	{ key: "submit", label: "Submit", icon: "pi pi-check" },
	{ key: "update_status", label: "Update Status", icon: "pi pi-check-circle" },
	{ key: "create_debit", label: "Create Debit", icon: "pi pi-plus" },
	{ key: "edit", label: "Edit", icon: "pi pi-pencil" },
	{ key: "amend", label: "Amend", icon: "pi pi-copy" },
	{ key: "share", label: "Share", icon: "pi pi-share-alt" },
	{ key: "cancel", label: "Cancel", icon: "pi pi-ban", menuOnly: true },
	{ key: "delete", label: "Delete", icon: "pi pi-trash", menuOnly: true },
]

export function inspectionActionItems(actions = {}, handlers = {}) {
	const primary = ["submit", "update_status", "create_debit", "edit", "amend"].find((key) => actions[key]?.allowed)
	return ACTIONS.filter(({ key }) => actions[key]?.allowed).map((action) => ({
		...action,
		label: actions[action.key].label || action.label,
		primary: action.key === primary,
		command: handlers[action.key],
	}))
}

export function resultTone(result) {
	return { Pass: "success", Fail: "danger", Hold: "warning" }[result] || "neutral"
}

export function selectedValues(rows = [], field) {
	return rows.filter((row) => Number(row.selected) === 1).map((row) => row[field]).join(", ")
}

export function inspectionShareCaption(record = {}, selection = {}) {
	return [
		record.inspection_type,
		`Supplier: ${record.supplier_name || ""}`,
		`Style: ${record.item || ""}`,
		`Lot: ${record.lot || ""}`,
		`Size: ${selectedValues(selection.sizes, "size")}`,
		`Colour: ${selectedValues(selection.colours, "colour")}`,
		`Description: ${record.description || ""}`,
		`Order Qty: ${record.order_qty || 0}`,
		`Offer Qty: ${record.offer_qty || 0}`,
		`AQL Sample: ${record.sample_piece_count || 0}`,
		`Allowed Major: ${record.major_defect_maximum_allowed || 0}`,
		`Found Major: ${record.major_defect_found || 0}`,
		`Allowed Minor: ${record.minor_defect_maximum_allowed || 0}`,
		`Found Minor: ${record.minor_defect_found || 0}`,
		`Result: ${record.result || ""}`,
	].join("\n")
}

export function cleanSelection(selection = {}) {
	return Object.fromEntries([["colours", "colour"], ["sizes", "size"]].map(([group, field]) => [
		group, (selection[group] || []).map((row) => ({ [field]: row[field], selected: Number(row.selected) === 1 ? 1 : 0 })),
	]))
}

export function toggleSelection(selection, group, value) {
	const result = cleanSelection(selection)
	const field = group === "colours" ? "colour" : "size"
	result[group] = result[group].map((row) => row[field] === value ? { ...row, selected: row.selected ? 0 : 1 } : row)
	return result
}

export function selectAll(selection, group, selected) {
	const result = cleanSelection(selection)
	result[group] = result[group].map((row) => ({ ...row, selected: selected ? 1 : 0 }))
	return result
}

export function inspectionPayload(values, selection) {
	return {
		...Object.fromEntries(INSPECTION_EDITABLE_FIELDS.filter((key) => key in values).map((key) => [key, values[key]])),
		...(values.amended_from ? { amended_from: values.amended_from } : {}),
		colour_and_size_data: cleanSelection(selection),
	}
}

export function inspectionResultPreview(values) {
	if (values.major_defect_maximum_allowed == null || values.minor_defect_maximum_allowed == null) return ""
	return Number(values.major_defect_found || 0) <= Number(values.major_defect_maximum_allowed)
		&& Number(values.minor_defect_found || 0) <= Number(values.minor_defect_maximum_allowed) ? "Pass" : "Fail"
}

export function validAqlInputs(values) {
	return Number.isInteger(Number(values.offer_qty)) && Number(values.offer_qty) > 0
		&& ["Level 1", "Level 2"].includes(values.checking_level)
		&& Boolean(values.major_aql_level && values.minor_aql_level)
}

/** Clipboard API needs a secure context; fall back to execCommand on plain http. */
export async function copyText(text, doc = globalThis.document, clipboard = globalThis.navigator?.clipboard) {
	if (clipboard?.writeText) {
		try {
			await clipboard.writeText(text)
			return true
		} catch {
			// Permission denied or document not focused: try the legacy path.
		}
	}
	const area = doc.createElement("textarea")
	area.value = text
	area.setAttribute("readonly", "")
	area.style.position = "fixed"
	area.style.opacity = "0"
	doc.body.appendChild(area)
	area.select()
	try { return Boolean(doc.execCommand("copy")) } catch { return false } finally { area.remove() }
}

const LINK_LABEL_FIELDS = { supplier: "supplier_name", third_party_supplier: "third_party_supplier_name" }

/** Show the party name rather than its code on Supplier links. */
export function linkLabel(fieldname, values = {}) {
	return values[LINK_LABEL_FIELDS[fieldname]] || undefined
}
