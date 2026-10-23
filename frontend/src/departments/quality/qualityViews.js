import { INSPECTION_FIELDS } from "./inspectionFields.js"
import { documentOverviewHasValue, formatDocumentOverviewValue } from "../../utils/documentOverview.js"

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
	{ key: "cancel", label: "Cancel", icon: "pi pi-ban", menuOnly: true, shortcut: "cancel" },
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

export const INSPECTION_TABS = [
	{ key: "inspection", label: "Inspection" },
	{ key: "details", label: "Details" },
	{ key: "debits", label: "Debits" },
]

export const INSPECTION_DETAIL_SECTIONS = [
	{ key: "work_order", label: "Work Order", icon: "pi pi-briefcase", fields: ["against_id", "item", "lot", "supplier", "supplier_name", "order_qty"] },
	{ key: "aql", label: "AQL", icon: "pi pi-sliders-h", fields: ["checking_level", "major_aql_level", "minor_aql_level", "sample_piece_count", "major_defect_maximum_allowed", "minor_defect_maximum_allowed"] },
	{ key: "inspection", label: "Inspection", icon: "pi pi-verified", fields: ["inspection_type", "unit_name", "posting_date", "description", "inspector", "calculated_result", "amended_from"] },
	{ key: "third_party", label: "Third party", icon: "pi pi-building", fields: ["third_party_supplier", "third_party_supplier_name"] },
]

export function inspectionDetailFields(record = {}) {
	return INSPECTION_DETAIL_SECTIONS.flatMap((section) => {
		if (section.key === "third_party" && Number(record.is_third_party) !== 1) return []
		return section.fields.filter((key) => documentOverviewHasValue(record[key])).map((key) => ({
			...INSPECTION_FIELDS[key], value: record[key],
			...(key === "against_id" ? { link_doctype: "YRP Work Order" } : {}),
			...(linkLabel(key, record) ? { value: linkLabel(key, record), link_name: record[key] } : {}),
		}))
	})
}

export function inspectionHeaderFacts(record = {}, fieldnames = ["against_id", "item", "lot", "supplier", "inspection_type", "posting_date"]) {
	return fieldnames
		.filter((key) => documentOverviewHasValue(record[key]))
		.map((key) => ({
			...INSPECTION_FIELDS[key], value: record[key],
			doctype: key === "against_id" ? "YRP Work Order" : INSPECTION_FIELDS[key].fieldtype === "Link" ? INSPECTION_FIELDS[key].options : "",
			display: linkLabel(key, record) || formatDocumentOverviewValue({ ...INSPECTION_FIELDS[key], value: record[key] }),
		}))
}

export function inspectionSummaryFacts(record = {}) {
	return inspectionHeaderFacts(record, [
		"checking_level", "major_aql_level", "minor_aql_level", "unit_name", "description",
		...(Number(record.is_third_party) === 1 ? ["third_party_supplier"] : []),
	])
}

export function inspectionSelectedChips(selection = {}) {
	return [["colours", "colour", "Colours"], ["sizes", "size", "Sizes"]].flatMap(([key, field, label]) => {
		const values = (selection[key] || []).filter((row) => Number(row.selected) === 1 && documentOverviewHasValue(row[field])).map((row) => row[field])
		return values.length ? [{ key, label, values }] : []
	})
}

export function inspectionStatTiles(record = {}, selection) {
	const number = (value) => formatDocumentOverviewValue({ fieldtype: "Int", value })
	const tiles = [["order_qty", "Order Qty"], ["offer_qty", "Offer Qty"], ["sample_piece_count", "Sample Size"]]
		.map(([key, label]) => ({ key, label, value: number(record[key]), hint: "", tone: "neutral" }))
	if (Number(record.offer_qty) > 0 && documentOverviewHasValue(record.sample_piece_count) && Number(record.sample_piece_count) === 0) {
		Object.assign(tiles[2], { value: "—", hint: "Outside AQL range" })
	}
	if (selection && Number(record.order_qty) === 0 && !hasSelectedColourAndSize(selection)) {
		Object.assign(tiles[0], { value: "—", hint: "Select colours and sizes" })
	}
	for (const [key, label] of [["major", "Major"], ["minor", "Minor"]]) {
		const allowed = record[`${key}_defect_maximum_allowed`]
		const found = record[`${key}_defect_found`] ?? 0
		const hasLimit = documentOverviewHasValue(allowed) && Number.isFinite(Number(allowed))
		tiles.push({ key, label, value: number(found), hint: hasLimit ? `of ${number(allowed)} allowed` : "Limit not set",
			tone: hasLimit ? Number(found) <= Number(allowed) ? "success" : "danger" : "neutral" })
	}
	if (Number(record.spi_found)) tiles.push({ key: "spi_found", label: "SPI Found", value: number(record.spi_found), hint: "", tone: "neutral" })
	return tiles
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
	if (!hasAllowedLimits(values)) return ""
	return Number(values.major_defect_found || 0) <= Number(values.major_defect_maximum_allowed)
		&& Number(values.minor_defect_found || 0) <= Number(values.minor_defect_maximum_allowed) ? "Pass" : "Fail"
}

export function inspectionEditorResultState(form = {}, storedCalculated, preview) {
	const isManual = Boolean(form.result) && form.result !== (storedCalculated || "")
	const differs = Boolean(form.result && preview && preview !== form.result)
	return {
		isManual,
		showOverride: isManual && differs,
		message: !differs ? "" : isManual
			? `Result ${form.result} will be kept instead of the calculated ${preview}.`
			: `Result will be recalculated to ${preview} on save.`,
	}
}

function hasAllowedLimits(record) {
	return ["major", "minor"].every((key) => {
		const value = record[`${key}_defect_maximum_allowed`]
		return documentOverviewHasValue(value) && Number.isFinite(Number(value))
	})
}

function hasSelectedColourAndSize(selection) {
	return ["colours", "sizes"].every((key) => (selection[key] || []).some((row) => Number(row.selected) === 1))
}

export function inspectionResultSummary(record = {}) {
	const result = record.result || ""
	const calculated = record.calculated_result || ""
	const isManual = Boolean(result) && result !== record.calculated_result
	const limitResult = inspectionResultPreview(record)
	const notes = []
	if (isManual) {
		notes.push(calculated ? "Manual override" : "Entered manually, not calculated")
		if (limitResult && limitResult !== result) notes.push(`Found defects give ${limitResult} against the allowed limits`)
	}
	return { result, calculated, isManual, limitResult, note: notes.join(". ") }
}

export function inspectionCalculationNotes(record = {}, selection) {
	const notes = []
	const add = (key, text) => notes.push({ key, severity: "warn", text })
	if (Number(record.offer_qty) > 0 && record.major_aql_level && record.minor_aql_level
		&& Number(record.sample_piece_count) === 0) {
		add("aql_range", `Offer Qty ${record.offer_qty} is outside the ${record.major_aql_level} AQL table range, so the sample size is 0.`)
	}
	if (selection) {
		if (!(selection.colours?.length || selection.sizes?.length)) {
			add("no_delivery", "No colours or sizes are recorded on this inspection, so Order Qty is 0.")
		} else if (!hasSelectedColourAndSize(selection)) {
			add("no_selection", "Select colours and sizes to calculate Order Qty.")
		}
	}
	const { result, isManual, limitResult } = inspectionResultSummary(record)
	if (isManual && limitResult && limitResult !== result) {
		add("manual_mismatch", `Result ${result} was entered manually; the found defects give ${limitResult}.`)
	}
	return notes
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
