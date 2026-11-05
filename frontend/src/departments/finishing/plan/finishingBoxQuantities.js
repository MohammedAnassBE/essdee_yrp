/** Box Qty entry helper for the alternative plan matrix: boxes × pieces per box, split across colours. Never saved. */

const number = (value) => Number(value) || 0
const round3 = (value) => Math.round(value * 1000) / 1000

/** Split `total` by `weights` in whole pieces; the remainder goes to the first weighted colours. */
export function splitPieces(total, weights) {
	const weightTotal = weights.reduce((sum, weight) => sum + weight, 0)
	const shares = weights.map((weight) => Math.floor((total * weight) / weightTotal + 1e-9))
	let remainder = round3(total - shares.reduce((sum, share) => sum + share, 0))
	const weighted = weights.map((weight, index) => (weight > 0 ? index : -1)).filter((index) => index >= 0)
	for (const index of weighted) {
		if (remainder < 1) break
		shares[index] += 1
		remainder -= 1
	}
	if (remainder > 0) shares[weighted[0]] = round3(shares[weighted[0]] + remainder)
	return shares
}

/** Set item rows are keyed "colour (major colour) @ part"; the IPD ratio is per major colour. */
function ratioColour(key, isSetItem) {
	if (!isSetItem) return key
	return String(key).match(/\(([^)]*)\)/)?.[1]?.trim() ?? key
}

function colourGroups(payload, entry, size, checkable) {
	const groups = {}
	for (const [colour, row] of Object.entries(payload?.data?.data || {})) {
		const target = entry[colour]
		if (!target || !(size in target.sizes) || (checkable && !target.checked)) continue
		;(groups[payload.is_set_item ? row.part || "" : ""] ||= []).push(colour)
	}
	return Object.values(groups)
}

/** Prefill one size's colour quantities from its Box Qty. Returns false and changes nothing when the total is unknown. */
export function applyBoxQuantity({ payload, entry, size, boxes, piecesPerBox, ratio = {}, checkable = false }) {
	const total = number(boxes) * number(piecesPerBox)
	if (total <= 0) return false
	for (const colours of colourGroups(payload, entry, size, checkable)) {
		const ratios = colours.map((colour) => number(ratio[ratioColour(colour, payload.is_set_item)]))
		const weights = ratios.some((value) => value > 0) ? ratios : colours.map(() => 1)
		splitPieces(total, weights).forEach((pieces, index) => {
			entry[colours[index]].sizes[size] = pieces
		})
	}
	return true
}
