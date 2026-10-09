/** Client checks and payloads for the Rework Details and Rework Grouped Details actions. */

function outOfRange(value, pending) {
	const number = Number(value || 0)
	return !Number.isFinite(number) || number < 0 || number > Number(pending || 0)
}

export function reworkRowsError(items, requireRework = false) {
	for (const item of items || []) {
		if (outOfRange(item.rejected, item.rework_qty)) return "Rejected quantity must be between 0 and the pending quantity."
		if (outOfRange(item.rework, item.rework_qty)) return "Reworked quantity must be between 0 and the pending quantity."
	}
	if (requireRework && !(items || []).some((item) => Number(item.rework) > 0)) return "Enter at least one Reworked quantity."
	return ""
}

export function rowTotal(values, sizes) {
	return (sizes || []).reduce((sum, size) => sum + (Number(values?.[size]) || 0), 0)
}

export function groupRowInputs(row, sizes) {
	return {
		rejection: Object.fromEntries(sizes.map((size) => [size, Number(row.rejection?.[size]) || 0])),
		rework: Object.fromEntries(sizes.map((size) => [size, 0])),
	}
}

export function groupRowPayload(row, inputs, sizeField, mode) {
	return (row.items || []).map((item) => {
		const size = item[sizeField]
		if (mode === "rework") return { ...item, rework: Number(inputs.rework[size]) || 0 }
		return { ...item, rejected: Number(inputs.rejection[size] ?? item.rejected) || 0 }
	})
}
