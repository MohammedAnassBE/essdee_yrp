import { diffTone, statusTone } from "../../../utils/lotProcessFlow.js"
import { formatQuantity } from "./dashboardFormat.js"

export const ALL_COLOURS = "All colours"

const groupLabel = (group) => [group.colour || "—", group.part].filter(Boolean).join(" · ")
const amount = (values, key) => Number(values?.[key] || 0)

function gridIndex(detail) {
	return new Map((detail.grid || []).map((group) => [groupLabel(group), group]))
}

/** Cell measures `[planned, delivered, received, dispatch]`; null where the source has no split. */
function gridCell(detail, group, size) {
	const planned = amount(group?.planned, size)
	const delivered = amount(group?.delivered, size)
	return detail.packing ? [planned, delivered, null, null] : [planned, delivered, amount(group?.received, size), 0]
}

function packingSizeCell(detail, size) {
	const planned = (detail.grid || []).reduce((total, group) => total + amount(group.planned, size), 0)
	const packing = detail.packing
	return [planned, amount(packing.delivered, size), amount(packing.received, size), amount(packing.dispatch, size)]
}

function sumCells(cells) {
	return cells.reduce((total, cell) => total.map((value, index) => (value === null || cell[index] === null ? null : value + cell[index])), [0, 0, 0, 0])
}

const plain = (value) => ({ value, text: formatQuantity(value), tone: "" })
const dash = () => ({ value: null, text: "—", tone: "" })

/** Table lines for one process kind; Difference is received − delivered (cutting: − planned). */
function matrixLines(kind) {
	const isCutting = kind === "cutting"
	const reference = (cell) => (isCutting ? cell[0] : cell[1] || cell[0])
	const lines = [
		["planned", "Planned", (cell) => plain(cell[0])],
		["delivered", "Delivered", (cell) => (isCutting ? dash() : { ...plain(cell[1]), tone: statusTone(cell[1], cell[0]) })],
		["received", "Received", (cell) => (cell[2] === null ? dash() : { ...plain(cell[2]), tone: statusTone(cell[2], reference(cell)) })],
	]
	if (kind === "packing") lines.push(["dispatch", "Dispatch", (cell) => (cell[3] === null ? dash() : { ...plain(cell[3]), tone: statusTone(cell[3], cell[0]) })])
	lines.push(["difference", "Difference", (cell) => {
		if (cell[2] === null) return dash()
		const difference = cell[2] - reference(cell)
		return { value: difference, text: `${difference > 0 ? "+" : ""}${formatQuantity(difference)}`, tone: diffTone(difference, reference(cell)) }
	}])
	return lines
}

function matrixRows(kind, rowKeys, columnKeys, cellAt, totalFor = (rowKey, summed) => summed) {
	const lines = matrixLines(kind)
	return rowKeys.map((rowKey) => {
		const cells = columnKeys.map((columnKey) => cellAt(rowKey, columnKey))
		const total = totalFor(rowKey, sumCells(cells))
		const rowLines = total[2] === null ? lines.slice(0, 2) : lines
		return {
			key: rowKey,
			lines: rowLines.map(([key, label, render]) => ({ key, label, cells: cells.map(render), total: render(total) })),
		}
	})
}

/** Colour rows × size columns; packing adds an "All colours" row with the per-size Received and Dispatch. */
export function sizeWiseMatrix(detail) {
	const groups = gridIndex(detail)
	const rowKeys = [...groups.keys(), ...(detail.packing ? [ALL_COLOURS] : [])]
	const cellAt = (label, size) => (label === ALL_COLOURS ? packingSizeCell(detail, size) : gridCell(detail, groups.get(label), size))
	return { columns: detail.sizes || [], rows: matrixRows(detail.kind, rowKeys, detail.sizes || [], cellAt) }
}

/** Size rows × colour columns; packing totals take the per-size Received and Dispatch. */
export function colourWiseMatrix(detail) {
	const groups = gridIndex(detail)
	const columns = [...groups.keys()]
	const totalFor = detail.packing ? (size, summed) => [summed[0], summed[1], ...packingSizeCell(detail, size).slice(2)] : undefined
	const cellAt = (size, label) => gridCell(detail, groups.get(label), size)
	return { columns, rows: matrixRows(detail.kind, detail.sizes || [], columns, cellAt, totalFor) }
}
