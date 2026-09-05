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

export function programColourColumns(entry) {
	const colours = [...new Set(entry.program.map(programColour).filter(Boolean))]
		.sort((a, b) => String(a).localeCompare(String(b)))
	return colours.length ? colours.map((colour) => ({ key: colour, label: colour })) : [{ key: "", label: "Program" }]
}

export function programRow(entry, dia, colour) {
	return entry.program.find((row) => programDia(row) === dia && programColour(row) === colour)
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
