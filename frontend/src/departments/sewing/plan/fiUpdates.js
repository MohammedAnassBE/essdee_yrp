import { PLANNING_ROUTES } from "../../planning/planningViews.js"

export function groupFiUpdatesByLot(rows = []) {
	const groups = new Map()
	for (const row of rows) {
		if (!groups.has(row.lot)) groups.set(row.lot, { lot: row.lot, item: row.item, isSetItem: Boolean(row.is_set_item), setAttribute: row.set_attr || "Part", rows: [] })
		groups.get(row.lot).rows.push(row)
	}
	return [...groups.values()]
}

export function fiUpdatePayload(rows = [], dates = {}) {
	return rows
		.filter(row => dates[fiUpdateKey(row)])
		.map(row => ({ sewing_plan: row.sewing_plan, lot: row.lot, colour: row.colour, part: row.part, date: dates[fiUpdateKey(row)] }))
}

export function fiUpdateKey(row) {
	return [row.lot, row.colour, row.part || ""].join("\u0000")
}

export function canShowFiUpdates(routeName, capabilities = {}) {
	return routeName === PLANNING_ROUTES.sewingPlans && capabilities.sections?.plans?.can_update_fi_dates === true
}
