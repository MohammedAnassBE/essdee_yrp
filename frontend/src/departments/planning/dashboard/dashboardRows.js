import { csvText, plural } from "./dashboardFormat.js"

export const LADDER = [
	"Fabric not received", "Waiting for cutting", "In cutting", "Waiting for sewing",
	"In sewing", "Ready for packing", "Packing in progress", "Dispatched",
]
export const NO_WORK_ORDER = "No Work Order yet"
export const DASHBOARD_STATUSES = [...LADDER, NO_WORK_ORDER]
export const BEHIND_ORDER = [NO_WORK_ORDER, ...LADDER]
export const LADDER_TONE = {
	"Fabric not received": "amber", "Waiting for cutting": "amber", "In cutting": "amber",
	"Waiting for sewing": "blue", "In sewing": "blue", "Ready for packing": "blue",
	"Packing in progress": "amber", Dispatched: "green",
}
export const SUMMED_FIELDS = ["qty", "cut", "stitch", "packed", "dispatch"]
export const PAGE_SIZE = 50
export const DASHBOARD_FILTERS = ["ppo", "lot", "item", "status"]

const sum = (rows, pick) => rows.reduce((total, row) => total + (Number(pick(row)) || 0), 0)
const isOpen = (row) => row.status !== "Dispatched"

export function emptyDashboardFilters() {
	return { ppo: [], lot: [], item: [], status: [] }
}

export function hasDashboardFilter(filters) {
	return DASHBOARD_FILTERS.some((kind) => filters[kind]?.length)
}

/** Rows matching every filter except `except`, so each filter's options narrow to the others. */
export function filterDashboardRows(rows, filters, except = null) {
	const keep = (kind, row) => kind === except || !filters[kind]?.length || filters[kind].includes(row[kind])
	return rows.filter((row) => DASHBOARD_FILTERS.every((kind) => keep(kind, row)))
}

/** `{ value, hint }` options of one filter from the rows matching the other filters. */
export function dashboardOptions(rows, filters, kind, ppos = {}) {
	const matching = filterDashboardRows(rows, filters, kind)
	if (kind === "lot") return matching.map((row) => ({ value: row.lot, hint: row.item || "" }))
	const counts = new Map()
	matching.forEach((row) => counts.set(row[kind], (counts.get(row[kind]) || 0) + 1))
	const order = kind === "status" ? (value) => DASHBOARD_STATUSES.indexOf(value) : null
	const entries = [...counts.entries()].sort((a, b) => (order ? order(a[0]) - order(b[0]) : String(a[0]).localeCompare(String(b[0]), undefined, { numeric: true })))
	if (kind === "ppo") return entries.map(([value, count]) => ({ value, hint: `${ppos[value]?.item_name || ppos[value]?.item || ""} · ${plural(count, "lot")}` }))
	return entries.map(([value, count]) => ({ value, hint: plural(count, "lot") }))
}

/** Tile figures over the rows matching the filters. */
export function dashboardTotals(data, filters) {
	const rows = filterDashboardRows(data.lots || [], filters)
	const lots = rows.filter((row) => row.has_work_order)
	const open = lots.filter(isOpen)
	const ppoNames = hasDashboardFilter(filters) ? [...new Set(rows.map((row) => row.ppo))] : Object.keys(data.ppos || {})
	const ppos = ppoNames.map((name) => data.ppos?.[name] || {})
	return {
		rows, lots, open, ppoNames,
		ppoCount: ppoNames.length,
		ppoWithWorkOrders: new Set(lots.map((row) => row.ppo)).size,
		ppoPieces: sum(ppos, (ppo) => ppo.pieces),
		ppoBoxes: sum(ppos, (ppo) => ppo.boxes),
		boxesOnly: ppos.filter((ppo) => !ppo.pieces).length,
		cut: sum(lots, (row) => row.cut),
		dispatched: sum(lots, (row) => row.dispatch),
		balance: sum(open, (row) => row.balance),
		late: open.filter((row) => row.delivery && row.delivery < data.as_of),
		notStarted: rows.filter((row) => !row.has_work_order),
	}
}

/** One card per status present: lot count and Σ total pcs (planned pcs for lots with no Work Order). */
export function statusCards(rows) {
	return DASHBOARD_STATUSES.map((status) => {
		const matching = rows.filter((row) => row.status === status)
		const isNoWorkOrder = status === NO_WORK_ORDER
		return { status, isNoWorkOrder, count: matching.length, pieces: sum(matching, (row) => (isNoWorkOrder ? row.qty : row.total)) }
	}).filter((card) => card.count)
}

export function ppoQuantityValue(ppo = {}) {
	return ppo.pieces ?? ppo.boxes ?? 0
}

function furthestBehind(lots) {
	const open = lots.filter(isOpen).map((row) => row.status)
	if (!open.length) return "Dispatched"
	return open.sort((a, b) => BEHIND_ORDER.indexOf(a) - BEHIND_ORDER.indexOf(b))[0]
}

/** One row per PPO from the filtered lots: quantities summed, PPO Qty once, status = furthest-behind open lot. */
export function groupDashboardRows(rows) {
	const groups = new Map()
	rows.forEach((row) => groups.set(row.ppo, [...(groups.get(row.ppo) || []), row]))
	return [...groups.entries()].map(([ppo, lots]) => {
		const items = [...new Set(lots.map((row) => row.item))]
		const mix = {}
		lots.forEach((row) => { mix[row.status] = (mix[row.status] || 0) + 1 })
		const status = furthestBehind(lots)
		const sums = Object.fromEntries(SUMMED_FIELDS.map((field) => [field, sum(lots, (row) => row[field])]))
		return {
			ppo, isGroup: true, lots, items, mix, status, ...sums,
			lot: lots.map((row) => row.lot).join(", "),
			lotCount: lots.length,
			item: items.length === 1 ? items[0] : `${items.length} items`,
			otherStatuses: Object.keys(mix).length - 1,
			has_work_order: status !== NO_WORK_ORDER,
			breakdown: BEHIND_ORDER.filter((name) => mix[name]).map((name) => `${name}: ${mix[name]}`).join("\n"),
		}
	})
}

const SORT_VALUES = {
	ppo: (row) => row.ppo,
	lot: (row) => row.lotCount ?? row.lot,
	item: (row) => row.item,
	status: (row) => DASHBOARD_STATUSES.indexOf(row.status),
	ppoQty: (row, ppos) => ppoQuantityValue(ppos[row.ppo]),
	qty: (row) => row.qty,
	cut: (row) => row.cut,
	stitch: (row) => row.stitch,
	packed: (row) => row.packed,
	dispatch: (row) => row.dispatch,
}

function compareValues(first, second) {
	if (typeof first === "number" && typeof second === "number") return first - second
	return String(first ?? "").localeCompare(String(second ?? ""), undefined, { numeric: true })
}

/** Sort by one column (`direction` 1 or -1), then PPO, then Lot. */
export function sortDashboardRows(rows, sort, ppos = {}) {
	const value = SORT_VALUES[sort.key] || SORT_VALUES.ppo
	return [...rows].sort((a, b) => compareValues(value(a, ppos), value(b, ppos)) * sort.direction
		|| compareValues(a.ppo, b.ppo) || compareValues(a.lot, b.lot))
}

export function pageRows(rows, page, size = PAGE_SIZE) {
	const pages = Math.max(Math.ceil(rows.length / size), 1)
	const current = Math.min(Math.max(page, 0), pages - 1)
	const start = current * size
	return { rows: rows.slice(start, start + size), page: current, pages, start }
}

export function dashboardCsv(rows, grouped, ppos = {}) {
	const header = ["#", "PPO", grouped ? "Lots" : "Lot", "Item", "Status", "PPO Qty", "PPO Qty unit", "Lot Qty", "Cut Qty", "Stitching Qty", "Packed Qty", "Dispatched Qty"]
	const lines = rows.map((row, index) => [
		index + 1, row.ppo, row.lot, row.item, row.status, ppoQuantityValue(ppos[row.ppo]), ppos[row.ppo]?.pieces ? "pcs" : "box",
		row.qty, row.cut, row.stitch, row.packed, row.dispatch,
	])
	return csvText([header, ...lines])
}

const lotNames = (rows) => rows.map((row) => row.lot)

/** PPO Tracking filters a Dashboard tile opens with. */
export function tileDrill(key, totals) {
	const drills = {
		ppos: { ppo: totals.ppoNames },
		lots: { lot: lotNames(totals.open) },
		ppoQty: { ppo: totals.ppoNames },
		cut: { lot: lotNames(totals.lots.filter((row) => row.cut)), dispatched: true },
		dispatched: { lot: lotNames(totals.lots.filter((row) => row.dispatch)), dispatched: true },
		balance: { lot: lotNames(totals.open) },
		late: { lot: lotNames(totals.late) },
	}
	const drill = drills[key] || {}
	return { ppo: drill.ppo || [], lot: drill.lot || [], dispatched: Boolean(drill.dispatched) }
}

/** PPO Tracking filters of a PPO link (`withLot` false) or Lot link in the table. */
export function rowDrill(row, withLot) {
	return { ppo: [row.ppo], lot: withLot ? [row.lot] : [], dispatched: row.status === "Dispatched" }
}
