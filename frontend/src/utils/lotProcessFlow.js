import { webDocumentPath } from "../router/webDocumentRoutes.js"

export const STATUS_LABELS = { done: "Completed", partial: "Partially completed", idle: "Not started" }
export const TONE_LEGEND = [
	["ok", "Complete"], ["part", "Partial"], ["none", "Not done"],
]
export const DIFFERENCE_LEGEND = [
	["d-ok", "Matched or over"], ["d-1", "Short ≤ 5%"], ["d-2", "Short ≤ 25%"], ["d-3", "Short > 25%"],
]
const TOTAL = "__total"
const number = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 })

export function formatNumber(value) {
	return number.format(Number(value || 0))
}

export function percent(value, total) {
	return total ? Math.round((value / total) * 1000) / 10 : 0
}

/** Green when value reaches 99.5% of reference, amber above zero, red at zero. */
export function statusTone(value, reference) {
	if (!reference) return ""
	if (value >= reference * 0.995) return "ok"
	return value > 0 ? "part" : "none"
}

/** Difference tone: matched or over is green; shortfall share ≤ 5%, ≤ 25%, > 25% get deepening reds. */
export function diffTone(value, reference) {
	if (!reference && !value) return ""
	if (value >= -1e-9) return "d-ok"
	const share = -value / (reference || 1)
	return share <= 0.05 ? "d-1" : share <= 0.25 ? "d-2" : "d-3"
}

const amount = (row, key, size) => Number(row[key]?.[size] || 0)
const hasDelivered = (row) => amount(row, "delivered", TOTAL) > 0
const base = (row, size) => amount(row, hasDelivered(row) ? "delivered" : "planned", size)

const LINES = {
	planned: { label: "Planned", value: (row, size) => amount(row, "planned", size), tone: () => "" },
	delivered: { label: "Delivered", value: (row, size) => amount(row, "delivered", size), tone: (value, row, size) => statusTone(value, amount(row, "planned", size)) },
	received: { label: "Received", value: (row, size) => amount(row, "received", size), tone: (value, row, size) => statusTone(value, base(row, size)) },
	dispatch: { label: "Dispatch", value: (row, size) => amount(row, "dispatch", size), tone: (value, row, size) => statusTone(value, amount(row, "planned", size)) },
	difference: { label: "Difference", value: (row, size) => amount(row, "received", size) - base(row, size), tone: (value, row, size) => diffTone(value, base(row, size)) },
	pending: { label: "Pending", value: (row, size) => amount(row, "delivered", size) - amount(row, "received", size), tone: (value, row, size) => (value > 1e-9 ? diffTone(-value, amount(row, "delivered", size)) : "") },
}

function withTotals(row, sizes) {
	const result = { ...row }
	for (const key of ["planned", "delivered", "received", "dispatch"]) {
		const values = row[key] || {}
		result[key] = { ...values, [TOTAL]: sizes.reduce((sum, size) => sum + Number(values[size] || 0), 0) }
	}
	return result
}

function lines(row, sizes, keys, labels) {
	return keys.map((key) => {
		const line = LINES[key]
		const cell = (size) => {
			const value = line.value(row, size)
			return { value, tone: line.tone(value, row, size) }
		}
		return { key, label: labels[key] || line.label, cells: sizes.map(cell), total: cell(TOTAL) }
	})
}

/** Colour × size table: each row gets the requested lines with status tones; a Total block when there are several rows. */
export function sizeTable(grid, sizes, keys, labels = {}) {
	const rows = grid.map((row) => withTotals(row, sizes))
	const sum = Object.fromEntries(["planned", "delivered", "received", "dispatch"].map((key) => [key, Object.fromEntries(sizes.map((size) => [size, rows.reduce((total, row) => total + amount(row, key, size), 0)]))]))
	return {
		rows: rows.map((row) => ({ colour: row.colour, part: row.part, lines: lines(row, sizes, keys, labels) })),
		footer: rows.length > 1 ? lines(withTotals(sum, sizes), sizes, keys, labels) : null,
	}
}

export function itemHeadline(steps) {
	const started = steps.filter((step) => step.status !== "idle")
	if (!started.length) return "Not started yet."
	const done = steps.filter((step) => step.status === "done").length
	return `At ${started.at(-1).process}. ${done} of ${steps.length} steps complete.`
}

export function clothHeadline(lanes) {
	return `${lanes.filter((lane) => lane.status === "done").length} of ${lanes.length} cloth items ready.`
}

export function documentHref(doctype, name, currentPath) {
	return webDocumentPath(doctype, name, currentPath)
}

export function workOrderHref(workOrder, currentPath) {
	return documentHref(workOrder.target.doctype, workOrder.target.name, currentPath)
}

/** Context key → the report's own filter name, per report key. Only filters the report has are listed. */
export const REPORT_PREFILL = {
	work_in_progress: { lot: "lot", item: "item", process: "process_list" },
	planning_work_in_progress: { lot: "lot", item: "item", process: "process_list" },
	size_wise_stock: { lot: "lot", item: "item", process: "process_list" },
	inward_quantity: { lot: "lot", process: "process" },
	inhouse_quantity: { lot: "lot", process: "process" },
	work_order: { lot: "lot", process: "process_name", supplier: "supplier", item: "item" },
	work_order_pending: { lot: "lot", item: "item", process: "process", supplier: "supplier" },
	process_pending: { lot: "lot", item: "item", process: "process" },
	colour_wise_diff: { lot: "lot", process: "process_list" },
	supplier_pending: { supplier: "supplier", process: "process" },
	dispatch_percentage: { lot: "lot", item: "item" },
	month_wise_detail: { lot: "lot", item: "item" },
	finishing_plan: { lot: "lot", item: "item" },
	multi_ccr: { lot: "lots", item: "items" },
	ppo_report: { item: "items" },
	stock_balance: { lot: "lot" },
	lot_cut_quantity: { lot: "lot" },
	grn_report: { lot: "lot", supplier: "supplier", from_date: "from_date" },
	grn_summary: { lot: "lot", lot_date: "from_date" },
	dc_report: { lot: "lot", supplier: "supplier", from_date: "from_date" },
	stock_entry_report: { lot: "lot", item: "item", lot_date: "from_date" },
	stock_reconciliation_report: { lot: "lot", lot_date: "from_date" },
	stock_update_report: { lot: "lot", lot_date: "from_date" },
	jobwork_issued_items: { lot: "lot", lot_date: "from_date" },
	non_jobwork_issued_items: { lot: "lot", lot_date: "from_date" },
	non_grn_received_items: { lot: "lot", lot_date: "from_date" },
	item_conversion_report: { lot: "lot", lot_date: "from_date" },
	lot_consumption_report: { lot: "lot", lot_date: "start_date" },
	lot_wise_stock_ageing: { lot: "lot" },
	lot_purchase_summary: { lot: "lot" },
	purchase_order_itemwise: { lot: "lot" },
}
/** Fixed filter values a Lot link sets so the report's defaults don't hide the Lot's older or closed documents. */
export const REPORT_FIXED = {
	work_order: { based_on: { label: "Based on", value: "WO Status" } },
	purchase_order_itemwise: { open_status: { label: "Open Status", value: "" } },
}
const CONTEXT_LABELS = { lot: "Lot", process: "Process", supplier: "Supplier", item: "Item", from_date: "From", lot_date: "From" }

/** Filters a report gets from the step context, then its fixed values: `[{ key, label, param, value }]`. */
export function reportPrefill(report, context = {}) {
	const mapped = Object.entries(REPORT_PREFILL[report.key] || {})
		.filter(([key]) => context[key])
		.map(([key, param]) => ({ key, label: CONTEXT_LABELS[key], param, value: context[key] }))
	const fixed = Object.entries(REPORT_FIXED[report.key] || {}).map(([param, { label, value }]) => ({ key: param, label, param, value }))
	return [...mapped, ...fixed]
}

export function reportHref(reportsPath, report, context = {}) {
	const query = new URLSearchParams({ report: report.value })
	for (const filter of reportPrefill(report, context)) query.set(filter.param, filter.value)
	return `${reportsPath}?${query.toString()}`
}

/** Report context of one step: one supplier only when every Work Order shares it; earliest WO date; Lot date for stock reports. */
export function stepReportContext(lot, item, process, workOrders = [], lotDate = "") {
	const suppliers = [...new Set(workOrders.map((row) => row.supplier).filter(Boolean))]
	const dates = workOrders.map((row) => row.wo_date).filter(Boolean).sort()
	return { lot, item, process, supplier: suppliers.length === 1 ? suppliers[0] : "", from_date: dates[0] || "", lot_date: lotDate }
}

/** Received meter share, used by the stage strip pills. */
export function receivedShare(step) {
	const received = step.meters.find((meter) => meter.kind === "Received")
	return received ? percent(received.value, received.total) : 0
}

/** CSS colour from a colour name; unknown names fall back to the swatch default. */
export function colourSwatch(name) {
	return String(name || "").toLowerCase().replace(/\s+/g, "")
}

/** Cloth Program facts for a lane: total Kg, colours and colours per use (Main, Folding…). */
export function fabricSummary(fabric = {}) {
	const program = fabric.program || []
	const uses = {}
	for (const row of program) {
		for (const split of row.fabric_split || []) {
			const use = String(split.fabric_type || "").replace(/ Fabric$/, "")
			uses[use] = [...new Set([...(uses[use] || []), row.colour])]
		}
	}
	return {
		programKg: program.reduce((sum, row) => sum + Number(row.weight || 0), 0),
		colours: [...new Set(program.map((row) => row.colour).filter(Boolean))],
		uses: Object.entries(uses).map(([use, colours]) => `${use} · ${colours.join(", ")}`).join(" · "),
	}
}

/** Reports whose name or group contains `query`, ignoring case. */
export function filterReports(reports = [], query = "") {
	const needle = query.trim().toLowerCase()
	if (!needle) return reports
	return reports.filter((report) => `${report.label} ${report.group || ""}`.toLowerCase().includes(needle))
}

/** Popover list height: 70% of the viewport, capped by the larger space above or below the trigger. */
export function reportsListHeight(rect, viewportHeight, margin = 96) {
	return Math.round(Math.max(160, Math.min(viewportHeight * 0.7, Math.max(viewportHeight - rect.bottom, rect.top) - margin)))
}
