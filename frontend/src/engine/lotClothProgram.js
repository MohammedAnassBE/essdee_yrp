// Display uses the finished variant; saving must keep the physical knitting
// output and its final reference. They can have different Dia/Colour values.
export const programDia = (row) => row.finished_dia || row.dia || ""
export const programColour = (row) => row.finished_colour || row.colour || ""
export const roundKg = (value) => Math.round((Number(value) || 0) * 1000) / 1000

function diaNumber(value) {
	const match = String(value || "").match(/-?\d+(?:\.\d+)?/)
	return match ? Number(match[0]) : Number.MAX_SAFE_INTEGER
}

export function programDias(entry) {
	return [...new Set(entry.program.map(programDia).filter(Boolean))].sort(
		(a, b) => diaNumber(a) - diaNumber(b) || String(a).localeCompare(String(b)),
	)
}

export function programDiasWithQuantity(entry) {
	const diasWithQuantity = new Set(
		entry.program
			.filter((row) => (Number(row.weight) || 0) !== 0)
			.map(programDia)
			.filter(Boolean),
	)
	return programDias(entry).filter((dia) => diasWithQuantity.has(dia))
}

export function programColourColumns(entry) {
	const colours = [...new Set(entry.program.map(programColour).filter(Boolean))]
		.sort((a, b) => String(a).localeCompare(String(b)))
	return colours.length ? colours.map((colour) => ({ key: colour, label: colour })) : [{ key: "", label: "Program" }]
}

export function programRow(entry, dia, colour) {
	return entry.program.find((row) => programDia(row) === dia && programColour(row) === colour)
}

// MRP's Cloth Program splits each route by fabric type (Main Fabric, then accessories).
export function programFabricTypes(entry) {
	const groups = new Map()
	for (const row of entry.program) {
		for (const share of row.fabric_split || [{ fabric_type: "Main Fabric", weight: row.weight }]) {
			if (!groups.has(share.fabric_type)) groups.set(share.fabric_type, [])
			groups.get(share.fabric_type).push({ ...row, weight: share.weight })
		}
	}
	return [...groups]
		.sort(([a], [b]) => (a !== "Main Fabric") - (b !== "Main Fabric") || a.localeCompare(b))
		.map(([fabricType, rows]) => ({ fabricType, rows }))
}

export function serializeClothProgram(entries) {
	return entries.map((entry) => ({
		cloth_item: entry.cloth_item,
		program: entry.program.map((row) => ({
			dia: row.dia,
			colour: row.colour || null,
			reference_item_variant: row.reference_item_variant || null,
			weight: row.weight || 0,
		})),
	}))
}
