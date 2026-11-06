import { formatDisplayDate } from "../../../utils/dateFormat.js"
import { csvText, percentOf, plural, roundQuantity } from "./dashboardFormat.js"

export const PROCESS_STATUS_LABELS = { done: "Completed", partial: "Partial", idle: "Not started" }
export const PROCESS_UNITS = { cloth: ["Kg", "Kg"], cutting: ["Kg", "pcs"], item: ["pcs", "pcs"], packing: ["pcs", "pcs"] }

const sum = (rows, pick) => rows.reduce((total, row) => total + (Number(pick(row)) || 0), 0)
const isDispatched = (row) => row.status === "Dispatched"

export function emptyTrackingFilters() {
	return { ppo: [], lot: [], process: [] }
}

export function hasTrackingScope(filters) {
	return Boolean(filters.ppo.length || filters.lot.length)
}

/** Lots with only the selected processes; lots left with no process are dropped. */
export function matchingTrackingLots(lots, filters) {
	return lots
		.map((row) => ({ ...row, processes: row.processes.filter((step) => !filters.process.length || filters.process.includes(step.name)) }))
		.filter((row) => row.processes.length)
}

export function visibleTrackingLots(matching, showDispatched) {
	return matching.filter((row) => showDispatched || !isDispatched(row))
}

export function hiddenDispatchedCount(matching) {
	return matching.filter(isDispatched).length
}

/** Selection tiles: PPO and Lot filters set the scope; the Process filter and Show dispatched are ignored. */
export function trackingSummary(data, filters) {
	const lots = data.lots || []
	const ppoNames = filters.ppo.length ? filters.ppo.filter((name) => data.ppos?.[name]) : [...new Set(lots.map((row) => row.ppo))]
	const ppos = ppoNames.map((name) => data.ppos?.[name] || {})
	const notStarted = filters.lot.length ? [] : ppos.flatMap((ppo) => (ppo.lots || []).filter((row) => !row.has_work_order))
	const open = lots.filter((row) => !isDispatched(row))
	return {
		ppoCount: ppoNames.length,
		lotCount: lots.length + notStarted.length,
		openLots: open.length,
		dispatchedLots: lots.length - open.length,
		notStartedLots: notStarted.length,
		ppoBoxes: sum(ppos, (ppo) => ppo.boxes),
		ppoPieces: sum(ppos, (ppo) => ppo.pieces),
		dispatched: sum(lots, (row) => row.dispatch),
		workInProgress: sum(open, (row) => Math.max(row.total - row.dispatch, 0)),
		notStarted: sum(notStarted, (row) => row.planned),
		isLotsOnly: !filters.ppo.length,
	}
}

/** PPO row figures over every lot of the PPO with a Work Order, including hidden dispatched lots. */
export function ppoFigures(ppo = {}) {
	const lots = ppo.work_order_lots || []
	const cut = sum(lots, (row) => row.cut_pcs)
	const dispatch = sum(lots, (row) => row.dispatch)
	return {
		boxes: ppo.boxes, pieces: ppo.pieces, piecesPerBox: ppo.pieces_per_box,
		lotPieces: sum(lots, (row) => row.qty), cut, dispatch,
		balance: ppo.pieces ? ppo.pieces - dispatch : null,
		share: ppo.pieces ? dispatch / ppo.pieces : 0,
		isCutOver: Boolean(ppo.pieces && cut > ppo.pieces),
	}
}

/** Dispatch held by the PPO's lots that are not shown; `canShow` when they are all dispatched lots. */
export function hiddenDispatchNote(ppo, shownLots, showDispatched) {
	const shown = new Set(shownLots.map((row) => row.lot))
	const hidden = (ppo.work_order_lots || []).filter((row) => !shown.has(row.lot) && row.dispatch > 0)
	const pieces = ppoFigures(ppo).dispatch - sum(shownLots, (row) => row.dispatch)
	if (pieces <= 0) return null
	return { count: hidden.length, pieces, canShow: !showDispatched && hidden.every(isDispatched) }
}

export function groupLotsByPpo(lots) {
	const groups = new Map()
	lots.forEach((row) => groups.set(row.ppo, [...(groups.get(row.ppo) || []), row]))
	return [...groups.entries()]
}

/** Row values of one process: % = received of planned; packing uses lot order pcs. */
export function processMeasure(lot, step) {
	const reference = step.kind === "packing" ? lot.qty : step.planned
	return {
		planned: step.planned, delivered: step.delivered, received: step.received, dispatch: step.dispatch,
		reference, units: PROCESS_UNITS[step.kind] || PROCESS_UNITS.item,
		percent: percentOf(step.received, reference),
		isCloth: step.kind === "cloth",
	}
}

/** One segment per process in first-DC order, the done count and the latest process with activity. */
export function progressStrip(lot) {
	const segments = lot.processes.map((step) => ({
		name: step.name, status: step.status,
		tip: `${step.name} · ${PROCESS_STATUS_LABELS[step.status]} · ${processMeasure(lot, step).percent.toFixed(0)}% received`,
	}))
	const started = lot.processes.filter((step) => step.status !== "idle")
	return {
		segments,
		done: lot.processes.filter((step) => step.status === "done").length,
		total: lot.processes.length,
		current: started.length ? started[started.length - 1].name : "Not started",
	}
}

function ppoOption(row) {
	const hint = !row.item_name || row.item === row.item_name ? row.item || "" : `${row.item} · ${row.item_name}`
	return { value: row.name, hint }
}

/** PPO options (searchable by item), Lot options narrowed by PPO, Process options from the loaded lots. */
export function trackingFilterOptions(options, lots, filters) {
	const inPpo = (row) => !filters.ppo.length || filters.ppo.includes(row.ppo)
	const counts = new Map()
	lots.filter((row) => inPpo(row) && (!filters.lot.length || filters.lot.includes(row.lot)))
		.forEach((row) => row.processes.forEach((step) => counts.set(step.name, (counts.get(step.name) || 0) + 1)))
	return {
		ppo: (options.ppos || []).map(ppoOption),
		lot: (options.lots || []).filter(inPpo).map((row) => ({ value: row.name, hint: row.item || "" })),
		process: [...counts.entries()].map(([value, count]) => ({ value, hint: plural(count, "lot") })),
	}
}

/** Drop Lot and Process picks that are no longer among the options. */
export function pruneTrackingFilters(filters, options) {
	const keep = (values, list) => values.filter((value) => list.some((option) => option.value === value))
	return { ppo: filters.ppo, lot: keep(filters.lot, options.lot), process: keep(filters.process, options.process) }
}

function visibleProcesses(lots) {
	const kinds = new Map()
	lots.forEach((row) => row.processes.forEach((step) => kinds.has(step.name) || kinds.set(step.name, step.kind)))
	return [...kinds.entries()]
}

export function trackingCsv(lots, ppos = {}) {
	const processes = visibleProcesses(lots)
	const units = (kind) => PROCESS_UNITS[kind] || PROCESS_UNITS.item
	const header = [
		"PPO", "PPO Qty boxes", "PPO pcs", "PPO Cut pcs", "PPO Dispatch pcs", "PPO Balance pcs", "Lot", "Item", "Status", "Delivery",
		"Lot pcs", "Cut pcs", "Dispatch pcs", "Balance pcs",
		...processes.flatMap(([name, kind]) => [`${name} Delivered ${units(kind)[0]}`, `${name} Received ${units(kind)[1]}`]),
	]
	const lines = lots.map((row) => {
		const figures = ppoFigures(ppos[row.ppo])
		const byName = Object.fromEntries(row.processes.map((step) => [step.name, step]))
		return [
			row.ppo, figures.boxes ?? "", figures.pieces ?? "", figures.cut, figures.dispatch, figures.balance ?? "",
			row.lot, row.item, row.status, formatDisplayDate(row.delivery, ""), row.qty, row.cut_pcs, row.dispatch, row.balance,
			...processes.flatMap(([name]) => (byName[name] ? [roundQuantity(byName[name].delivered), roundQuantity(byName[name].received)] : ["", ""])),
		]
	})
	return csvText([header, ...lines])
}
