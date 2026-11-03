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

export const addWeightKey = (clothItem, fabricType, colour) => [clothItem, fabricType, colour || ""].join("\u0000")

// Add Weight: kg per cloth + fabric type + colour, spread over its Dias by the server on Calculate.
export function addWeightDrafts(fabrics) {
	const drafts = {}
	for (const entry of fabrics) {
		for (const [fabricType, colours] of Object.entries(entry.additions || {})) {
			for (const [colour, weight] of Object.entries(colours)) drafts[addWeightKey(entry.cloth_item, fabricType, colour)] = Number(weight) || 0
		}
	}
	return drafts
}

// Build Cloth Program popup: one Add Weight input per cloth, fabric type and colour of the preview.
const previewCells = (preview) =>
	(preview?.tables || []).flatMap((table) =>
		(table.fabric_groups || []).flatMap((group) =>
			table.colours.map((colour) => ({ table, group, colour, key: addWeightKey(table.cloth_item, group.fabric_type, colour) })),
		),
	)

export function previewAddWeightDrafts(preview) {
	return Object.fromEntries(previewCells(preview).map(({ group, colour, key }) => [key, Number(group.additions?.[colour]) || 0]))
}

export function previewAdditions(preview, drafts) {
	return previewCells(preview).map(({ table, group, colour, key }) => ({
		cloth_item: table.cloth_item,
		fabric_type: group.fabric_type,
		colour: colour === "No Colour" ? "" : colour,
		additional_weight: Number(drafts[key]) || 0,
	}))
}
