import { getList } from "../../../api/frappe.js"

/** YRP Item BOM `fetch_from` fields: row field -> Item field (Desk refetches on every Item change). */
export const BOM_ITEM_FETCH = { uom: "stock_uom" }
const ROW_FIELDS = Object.keys(BOM_ITEM_FETCH)

function itemChanged(row, previous) {
	return (row.item || null) !== (previous?.item || null)
}

/** Clears fetched fields on rows whose Item changed and returns the Items whose fields must be read. */
export function bomFetchPlan(previousRows, nextRows) {
	const items = new Set()
	const rows = (nextRows || []).map((row, index) => {
		let previous = row.name && previousRows?.find((candidate) => candidate.name === row.name)
		if (!previous && previousRows?.length === nextRows.length && !(row.name && previousRows[index]?.name)) {
			previous = previousRows[index]
		}
		const changed = previous && itemChanged(row, previous)
		if (row.item && (changed || ROW_FIELDS.some((field) => !row[field]))) items.add(row.item)
		if (!changed) return row
		return { ...row, ...Object.fromEntries(ROW_FIELDS.map((field) => [field, null])) }
	})
	return { rows, items: [...items] }
}

/** Applies fetched Item values to every row using that Item; returns the same array when nothing changes. */
export function applyBomFetch(rows, itemValues) {
	let touched = false
	const next = (rows || []).map((row) => {
		const values = itemValues[row.item]
		if (!values) return row
		const updates = Object.fromEntries(ROW_FIELDS.map((field) => [field, values[BOM_ITEM_FETCH[field]] ?? null]).filter(([field, value]) => row[field] !== value))
		if (!Object.keys(updates).length) return row
		touched = true
		return { ...row, ...updates }
	})
	return touched ? next : rows
}

/** Reads the fetched fields for the given Items in one request, keyed by Item name. */
export async function getBomItemValues(items) {
	const list = await getList("Item", {
		fields: ["name", ...new Set(Object.values(BOM_ITEM_FETCH))],
		filters: [["name", "in", items]], orderBy: "name asc", pageLength: items.length,
	})
	return Object.fromEntries(list.map((item) => [item.name, item]))
}

/** Drops fetched fields from outgoing BOM rows; the server refetches them from the Item on save. */
export function withoutBomFetch(patch) {
	if (!Array.isArray(patch.item_bom)) return patch
	const item_bom = patch.item_bom.map((row) => Object.fromEntries(Object.entries(row).filter(([field]) => !(field in BOM_ITEM_FETCH))))
	return { ...patch, item_bom }
}
