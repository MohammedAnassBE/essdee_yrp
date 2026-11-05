import { webDocumentPath } from "../../../../router/webDocumentRoutes.js"

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

export function reportHref(report, lot, process) {
	const query = new URLSearchParams({ report: report.value })
	if (report.key === "inhouse_quantity") {
		query.set("lot", lot)
		query.set("process", process)
	}
	return `/web/merch/reports?${query.toString()}`
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
