import { KEY_SEPARATOR, stableStringify } from "../ipdEditor.js"

export const COLUMN_SEPARATOR = "\u001e"
export const SINGLE_CLOTH_KEY = "__single__"
export const STITCHING_CATEGORY_DEFAULT = "Body"

const isBlank = (value) => value === null || value === undefined || value === ""
const same = (left, right) => stableStringify(left ?? null) === stableStringify(right ?? null)
const valueOptions = (values) => (values || []).map((value) => ({ value, label: value }))

function uniqueKeys(keys) {
	const seen = new Map()
	return keys.map((key) => {
		const count = seen.get(key) || 0
		seen.set(key, count + 1)
		return count ? `${key}${KEY_SEPARATOR}#${count}` : key
	})
}

export function tableRowKey(row, index, keyField = "") {
	return keyField ? String(row?.[keyField] ?? "") : row?.name || `new:${index}`
}

export function tableGrid(rows, fields, { keyField = "", label = null } = {}) {
	const list = rows || []
	const keys = list.map((row, index) => tableRowKey(row, index, keyField))
	return {
		rows: list.map((row, index) => ({ key: keys[index], label: label ? label(row, index) : keyField ? String(row[keyField] ?? "") : String(index + 1) })),
		model: Object.fromEntries(list.map((row, index) => [keys[index], Object.fromEntries(fields.map((field) => [field, row[field] ?? null]))])),
	}
}

export function tableFromModel(rows, model, fields, { keyField = "" } = {}) {
	return (rows || []).map((row, index) => {
		const cells = model?.[tableRowKey(row, index, keyField)]
		if (!cells) return row
		const changed = fields.filter((field) => field in cells && !same(cells[field], row[field]))
		return changed.length ? { ...row, ...Object.fromEntries(changed.map((field) => [field, cells[field]])) } : row
	})
}

export function processRowsFromModel(rows, model, fields) {
	return tableFromModel(rows, model, fields).map((row, index) => (row !== rows[index] && !same(row.in_stage, rows[index].in_stage) ? { ...row, out_stage: row.in_stage } : row))
}

export function hasStageMismatch(row) {
	return !same(row?.in_stage || null, row?.out_stage || null)
}

export function syncProcessStages(rows) {
	return (rows || []).map((row) => (hasStageMismatch(row) ? { ...row, out_stage: row.in_stage } : row))
}

export function removeTableRow(rows, key, keyField = "") {
	return (rows || []).filter((row, index) => tableRowKey(row, index, keyField) !== key)
}

export function toggleValueRow(rows, field, value, on, makeRow) {
	const list = rows || []
	const present = list.some((row) => row[field] === value)
	if (on && !present) return [...list, makeRow(value)]
	if (!on && present) return list.filter((row) => row[field] !== value)
	return list
}

export function packingRow(value) {
	return { attribute_value: value, quantity: 0 }
}

export function stitchingRow(panel) {
	return { stiching_attribute_value: panel, set_item_attribute_value: null, quantity: 1, category: STITCHING_CATEGORY_DEFAULT, is_default: 0 }
}

export function applyDefaultRadio(before, after) {
	const turnedOn = (after || []).filter((row, index) => Number(row.is_default) && !Number(before?.[index]?.is_default))
	if (!turnedOn.length) return after
	return after.map((row) => {
		const winner = turnedOn.find((candidate) => (candidate.set_item_attribute_value ?? "") === (row.set_item_attribute_value ?? ""))
		return winner && winner !== row && Number(row.is_default) ? { ...row, is_default: 0 } : row
	})
}

export function combinationGrid(value, { options = [], readonlyColumn = "" } = {}) {
	const attributes = value?.attributes || []
	const rows = value?.values || []
	return {
		rows: rows.map((row) => ({ key: String(row.major_attribute ?? ""), label: String(row.major_attribute ?? "") })),
		columns: attributes.map((attribute) => ({ key: attribute, label: attribute, type: "value", options: valueOptions(options), field: "value", readonly: attribute === readonlyColumn })),
		model: Object.fromEntries(rows.map((row) => [String(row.major_attribute ?? ""), Object.fromEntries(attributes.map((attribute) => [attribute, row.val?.[attribute] ?? null]))])),
	}
}

export function combinationFromModel(value, model) {
	const attributes = value?.attributes || []
	return {
		...value,
		values: (value?.values || []).map((row) => {
			const cells = model?.[String(row.major_attribute ?? "")] || {}
			const changed = attributes.filter((attribute) => attribute in cells && !same(cells[attribute], row.val?.[attribute]))
			return changed.length ? { ...row, val: { ...row.val, ...Object.fromEntries(changed.map((attribute) => [attribute, cells[attribute]])) } } : row
		}),
	}
}

function itemKeyColumns(value, carry) {
	return (value?.attributes || []).filter((attribute) => !carry.includes(attribute))
}

function itemKeys(value, carry) {
	const columns = itemKeyColumns(value, carry)
	return uniqueKeys((value?.items || []).map((item) => columns.map((column) => String(item[column] ?? "")).join(KEY_SEPARATOR)))
}

function diaColumn(dia) {
	return {
		type: "link", doctype: "Item Attribute Value", options: valueOptions(dia), field: "dia", width: 140,
		searchHandler: (text) => {
			const query = String(text ?? "").toLowerCase()
			const exact = [], prefixes = [], contains = []
			for (const value of dia || []) {
				const lower = value.toLowerCase()
				if (!query) contains.push(value)
				else if (lower === query) exact.push(value)
				else if (lower.startsWith(query)) prefixes.push(value)
				else if (lower.includes(query)) contains.push(value)
			}
			prefixes.sort((left, right) => left.length - right.length)
			return [...exact, ...prefixes, ...contains].slice(0, 20).map((value) => ({ name: value, label: value }))
		},
	}
}

const CARRY_COLUMNS = {
	Dia: (dia) => (dia?.length ? diaColumn(dia) : { type: "text", width: 110, field: "dia" }),
	Weight: () => ({ label: "Weight (kg)", type: "number", precision: 4, min: 0, field: "weight" }),
	"Required GSM": () => ({ type: "number", precision: 0, min: 0 }),
	Cloth: (_dia, cloths) => ({ type: "select", options: valueOptions(cloths), field: "cloth" }),
}

export function itemsGrid(value, carry, { diaOptions = [], clothOptions = [], attributeColumns = false } = {}) {
	const keyColumns = itemKeyColumns(value, carry)
	const keys = itemKeys(value, carry)
	const items = value?.items || []
	const editable = (value?.attributes || []).filter((attribute) => carry.includes(attribute))
	const headers = attributeColumns ? keyColumns.slice(0, 1) : keyColumns
	const readonly = attributeColumns ? keyColumns.slice(1) : []
	return {
		rowHeaderLabel: headers.join(" · "),
		rows: items.map((item, index) => ({ key: keys[index], label: headers.map((column) => (isBlank(item[column]) ? "—" : item[column])).join(" · ") })),
		columns: [
			...readonly.map((attribute) => ({ key: attribute, label: attribute, type: "text", readonly: true })),
			...editable.map((attribute) => ({ key: attribute, label: attribute, ...CARRY_COLUMNS[attribute]?.(diaOptions, clothOptions) })),
		],
		model: Object.fromEntries(items.map((item, index) => [keys[index], Object.fromEntries([...readonly, ...editable].map((attribute) => [attribute, item[attribute] ?? null]))])),
	}
}

export function itemsFromModel(value, model, carry) {
	const keys = itemKeys(value, carry)
	return {
		...value,
		items: (value?.items || []).map((item, index) => {
			const cells = model?.[keys[index]] || {}
			const changed = carry.filter((attribute) => attribute in cells && !same(cells[attribute], item[attribute]) && (attribute in item || !isBlank(cells[attribute])))
			return changed.length ? { ...item, ...Object.fromEntries(changed.map((attribute) => [attribute, cells[attribute]])) } : item
		}),
	}
}

export function stitchingAccessoryKey(row, setAttribute) {
	return [row?.accessory, setAttribute ? row?.[setAttribute] ?? "" : "", row?.major_colour].map((value) => String(value ?? "")).join(KEY_SEPARATOR)
}

export function stitchingAccessoryGrid(value, { colourOptions = [], clothOptions = [] } = {}) {
	const setAttribute = value?.set_attr || ""
	const items = value?.items || []
	const keys = uniqueKeys(items.map((row) => stitchingAccessoryKey(row, setAttribute)))
	return {
		rowHeaderLabel: ["Accessory", setAttribute, "Major colour"].filter(Boolean).join(" · "),
		rows: items.map((row, index) => ({ key: keys[index], label: [row.accessory, setAttribute ? row[setAttribute] : "", row.major_colour].filter((part) => !isBlank(part)).join(" · ") })),
		columns: [
			{ key: "accessory_colour", label: "Accessory colour", type: "value", options: valueOptions(colourOptions), field: "colour" },
			{ key: "cloth_type", label: "Cloth", type: "select", options: valueOptions(clothOptions), field: "cloth" },
		],
		model: Object.fromEntries(items.map((row, index) => [keys[index], { accessory_colour: row.accessory_colour ?? null, cloth_type: row.cloth_type ?? null }])),
	}
}

export function stitchingAccessoryFromModel(value, model) {
	const setAttribute = value?.set_attr || ""
	const keys = uniqueKeys((value?.items || []).map((row) => stitchingAccessoryKey(row, setAttribute)))
	return {
		...value,
		items: (value?.items || []).map((row, index) => {
			const cells = model?.[keys[index]] || {}
			const changed = ["accessory_colour", "cloth_type"].filter((field) => field in cells && !same(cells[field], row[field]))
			return changed.length ? { ...row, ...Object.fromEntries(changed.map((field) => [field, cells[field]])) } : row
		}),
	}
}

function assortmentRowKey(box, row, attributes) {
	return [box.separator_value, ...[...attributes].sort().map((attribute) => `${attribute}=${row[attribute] ?? ""}`)].join(KEY_SEPARATOR)
}

export function assortmentGrid(value) {
	const attributes = value?.assortment_attributes || []
	const entries = (value?.boxes || []).flatMap((box) => (box.rows || []).map((row) => ({ key: assortmentRowKey(box, row, attributes), box, row })))
	return {
		rowHeaderLabel: [value?.separator_attribute || "Box", ...attributes].join(" · "),
		rows: entries.map(({ key, box, row }) => ({ key, label: [box.box ?? box.separator_value, ...attributes.map((attribute) => row[attribute])].join(" · ") })),
		columns: [{ key: "qty", label: "Quantity", type: "number", precision: 0, min: 0 }],
		model: Object.fromEntries(entries.map(({ key, row }) => [key, { qty: row.qty ?? null }])),
	}
}

export function assortmentFromModel(value, model) {
	const attributes = value?.assortment_attributes || []
	return {
		...value,
		boxes: (value?.boxes || []).map((box) => ({
			...box,
			rows: (box.rows || []).map((row) => {
				const cells = model?.[assortmentRowKey(box, row, attributes)]
				return cells && "qty" in cells && !same(cells.qty ?? 0, row.qty) ? { ...row, qty: cells.qty ?? 0 } : row
			}),
		})),
	}
}

export function panelValuesFor(panel) {
	return panel?.panel_values || [panel?.panel_value].filter(Boolean)
}

export function packingValuesFor(panel, matrix) {
	return panel?.packing_values || matrix?.packing_values || []
}

const panelColumn = (packing, part) => `${packing}${COLUMN_SEPARATOR}${part}`

export function panelGroupGrid(matrix, panel, { diaOptions = [] } = {}) {
	const packings = packingValuesFor(panel, matrix)
	const grouped = panelValuesFor(panel).length > 1
	return {
		unitHint: grouped ? "Dia · group kg per piece" : "Dia · kg per piece",
		rowHeaderLabel: matrix?.attributes?.primary || "",
		rows: (panel?.rows || []).map((row) => ({ key: String(row.primary_value), label: String(row.primary_value) })),
		columns: packings.flatMap((packing) => [
			{ key: panelColumn(packing, "dia"), label: `${packing} Dia`, ...diaColumn(diaOptions) },
			{ key: panelColumn(packing, "weight"), label: `${packing} kg`, type: "number", precision: 4, min: 0.0001, field: "weight" },
		]),
		model: Object.fromEntries((panel?.rows || []).map((row) => [String(row.primary_value), Object.fromEntries(packings.flatMap((packing) => [
			[panelColumn(packing, "dia"), row.values?.[packing]?.dia ?? null],
			[panelColumn(packing, "weight"), row.values?.[packing]?.weight ?? null],
		]))])),
	}
}

export function panelGroupErrors(errors, panel) {
	const result = {}
	for (const [rowKey, columns] of Object.entries(errors || {})) {
		const [groupId, primary] = rowKey.split(KEY_SEPARATOR)
		if (groupId !== panel?.group_id) continue
		for (const [packing, message] of Object.entries(columns)) result[primary] = { ...(result[primary] || {}), [panelColumn(packing, "weight")]: message }
	}
	return result
}

function replacePanel(matrix, groupId, update) {
	return { ...matrix, panels: (matrix?.panels || []).map((panel) => (panel.group_id === groupId ? update(panel) : panel)) }
}

export function panelGroupFromModel(matrix, groupId, model) {
	return replacePanel(matrix, groupId, (panel) => ({
		...panel,
		rows: (panel.rows || []).map((row) => {
			const cells = model?.[String(row.primary_value)]
			if (!cells) return row
			const values = { ...(row.values || {}) }
			let changed = false
			for (const packing of packingValuesFor(panel, matrix)) {
				const cell = { dia: cells[panelColumn(packing, "dia")] ?? null, weight: cells[panelColumn(packing, "weight")] ?? null }
				const old = { dia: row.values?.[packing]?.dia ?? null, weight: row.values?.[packing]?.weight ?? null }
				if (same(cell, old)) continue
				values[packing] = { ...(row.values?.[packing] || {}), ...cell }
				changed = true
			}
			return changed ? { ...row, values } : row
		}),
	}))
}

export function splitWeight(total, count) {
	if (isBlank(total)) return Array(count).fill(null)
	const share = Number((Number(total) / count).toFixed(6))
	const values = Array(count).fill(share)
	values[count - 1] = Number((Number(total) - values.slice(0, -1).reduce((sum, value) => sum + value, 0)).toFixed(6))
	return values
}

function normalizeGroup(panel) {
	const values = panelValuesFor(panel)
	return { ...panel, panel_values: values, group_id: values.join(KEY_SEPARATOR), panel_value: values.join(" + ") }
}

function groupedCell(cells, rowLabel, packing) {
	const started = cells.map((cell) => !isBlank(cell?.dia) || !isBlank(cell?.weight))
	const complete = cells.map((cell) => !isBlank(cell?.dia) && Number(cell?.weight) > 0)
	if (started.some(Boolean) && !complete.every(Boolean)) throw new Error(`Complete or clear ${rowLabel}, ${packing} for every selected panel before grouping.`)
	const dias = [...new Set(cells.map((cell) => cell?.dia).filter((dia) => !isBlank(dia)))]
	if (dias.length > 1) throw new Error(`The selected panels use different Dia values for ${rowLabel}, ${packing}.`)
	return { dia: dias[0] || null, weight: complete.every(Boolean) ? Number(cells.reduce((sum, cell) => sum + Number(cell.weight || 0), 0).toFixed(6)) : null }
}

export function groupPanels(matrix, selectedValues) {
	const selected = (matrix?.panel_values || []).filter((panel) => selectedValues.includes(panel))
	if (selected.length < 2) throw new Error("Select at least two panels to group.")
	const sources = selected.map((value) => (matrix.panels || []).find((panel) => panelValuesFor(panel).length === 1 && panelValuesFor(panel)[0] === value))
	if (sources.some((panel) => !panel)) throw new Error("Ungroup an existing group before creating a different group.")
	const packings = packingValuesFor(sources[0], matrix)
	if (sources.some((panel) => stableStringify(packingValuesFor(panel, matrix)) !== stableStringify(packings))) {
		throw new Error("The selected panels have different fabric colour columns and cannot be grouped.")
	}
	const rows = (sources[0].rows || []).map((sourceRow) => {
		const matching = sources.map((panel) => (panel.rows || []).find((row) => row.primary_value === sourceRow.primary_value))
		const values = Object.fromEntries(packings.map((packing) => [packing, groupedCell(matching.map((row) => row?.values?.[packing]), sourceRow.primary_value, packing)]))
		return { primary_value: sourceRow.primary_value, values }
	})
	const group = normalizeGroup({ panel_values: selected, packing_values: [...packings], rows })
	const ids = new Set(sources.map((panel) => panel.group_id))
	const first = Math.min(...sources.map((panel) => matrix.panels.indexOf(panel)))
	const panels = matrix.panels.filter((panel) => !ids.has(panel.group_id))
	panels.splice(first, 0, group)
	return { matrix: { ...matrix, panels }, groupId: group.group_id }
}

export function ungroupPanel(matrix, groupId) {
	const group = (matrix?.panels || []).find((panel) => panel.group_id === groupId)
	const values = panelValuesFor(group)
	if (values.length < 2) return { matrix, groupId }
	const packings = packingValuesFor(group, matrix)
	const split = values.map((value, index) => normalizeGroup({
		panel_values: [value],
		packing_values: [...packings],
		rows: (group.rows || []).map((row) => ({
			primary_value: row.primary_value,
			values: Object.fromEntries(packings.map((packing) => {
				const cell = row.values?.[packing] || {}
				return [packing, { dia: cell.dia || null, weight: splitWeight(cell.weight, values.length)[index] }]
			})),
		})),
	}))
	const panels = [...matrix.panels]
	panels.splice(panels.indexOf(group), 1, ...split)
	return { matrix: { ...matrix, panels }, groupId: split[0].group_id }
}

export function panelProgress(matrix) {
	let total = 0
	let complete = 0
	for (const panel of matrix?.panels || []) {
		for (const row of panel.rows || []) {
			for (const packing of packingValuesFor(panel, matrix)) {
				total += 1
				const cell = row.values?.[packing]
				if (!isBlank(cell?.dia) && Number(cell?.weight) > 0) complete += 1
			}
		}
	}
	return { total, complete }
}

function clothRowKey(matrix, row) {
	return (matrix?.other_attributes || []).map((attribute) => row.attribute_values?.[attribute] || "").join(KEY_SEPARATOR) || "single"
}

export function panelClothGrid(matrix, panel) {
	const others = matrix?.other_attributes || []
	return {
		rowHeaderLabel: others.join(" / ") || "Mapping",
		rows: (panel?.rows || []).map((row) => ({ key: clothRowKey(matrix, row), label: others.map((attribute) => row.attribute_values?.[attribute] || "—").join(" / ") || "Cloth" })),
		columns: (panel?.packing_values || []).map((packing) => ({ key: packing, label: packing === SINGLE_CLOTH_KEY ? "Cloth" : packing, type: "select", options: valueOptions(matrix?.cloth_options), field: "cloth" })),
		model: Object.fromEntries((panel?.rows || []).map((row) => [clothRowKey(matrix, row), Object.fromEntries((panel.packing_values || []).map((packing) => [packing, row.values?.[packing]?.cloth ?? null]))])),
	}
}

export function panelClothFromModel(matrix, groupId, model) {
	return replacePanel(matrix, groupId, (panel) => ({
		...panel,
		rows: (panel.rows || []).map((row) => {
			const cells = model?.[clothRowKey(matrix, row)]
			if (!cells) return row
			const changed = (panel.packing_values || []).filter((packing) => packing in cells && !same(cells[packing], row.values?.[packing]?.cloth))
			if (!changed.length) return row
			return { ...row, values: { ...row.values, ...Object.fromEntries(changed.map((packing) => [packing, { ...(row.values?.[packing] || {}), cloth: cells[packing] }])) } }
		}),
	}))
}

export function embellishmentPanels(value, panels) {
	const stored = Object.values(value || {}).flat().filter((panel) => !(panels || []).includes(panel))
	return [...(panels || []), ...new Set(stored)]
}

export function embellishmentGrid(value, panels) {
	const columns = embellishmentPanels(value, panels)
	const processes = Object.keys(value || {})
	return {
		rows: processes.map((process) => ({ key: process, label: process })),
		columns: columns.map((panel) => ({ key: panel, label: panel, type: "check", width: 72 })),
		model: Object.fromEntries(processes.map((process) => [process, Object.fromEntries(columns.map((panel) => [panel, (value[process] || []).includes(panel) ? 1 : 0]))])),
	}
}

export function embellishmentFromModel(value, model, panels) {
	const columns = embellishmentPanels(value, panels)
	return Object.fromEntries(Object.entries(value || {}).map(([process, stored]) => {
		const cells = model?.[process]
		if (!cells) return [process, stored]
		const kept = (stored || []).filter((panel) => Number(cells[panel] ?? 1))
		const added = columns.filter((panel) => Number(cells[panel]) && !kept.includes(panel))
		const next = [...kept, ...added]
		return [process, same(next, stored) ? stored : next]
	}))
}

export function addEmbellishment(value, process, panels) {
	if (!process) throw new Error("Enter the process")
	return { ...(value || {}), [process]: [...(panels || [])] }
}

export function removeEmbellishment(value, process) {
	return Object.fromEntries(Object.entries(value || {}).filter(([key]) => key !== process))
}

export function markerGrid(groups, panels) {
	const columns = [...(panels || [])]
	for (const panel of (groups || []).flat()) if (!columns.includes(panel)) columns.push(panel)
	return {
		rows: (groups || []).map((_group, index) => ({ key: `group-${index}`, label: `Group ${index + 1}` })),
		columns: columns.map((panel) => ({ key: panel, label: panel, type: "check", width: 72 })),
		model: Object.fromEntries((groups || []).map((group, index) => [`group-${index}`, Object.fromEntries(columns.map((panel) => [panel, group.includes(panel) ? 1 : 0]))])),
	}
}

export function markerFromModel(groups, model, panels) {
	const { columns } = markerGrid(groups, panels)
	return (groups || []).map((group, index) => {
		const cells = model?.[`group-${index}`]
		if (!cells) return group
		const next = columns.map((column) => column.key).filter((panel) => Number(cells[panel]))
		return same([...next].sort(), [...group].sort()) ? group : next
	})
}

export function bundleGroupProblems(groups, panels) {
	const selected = []
	for (const panel of (groups || []).flat()) {
		if (selected.includes(panel)) return [{ panel, message: `Panel ${panel} is grouped multiple times` }]
		selected.push(panel)
	}
	if (selected.length && selected.length !== (panels || []).length) return [{ panel: "", message: "Select All the Panels" }]
	return []
}

export function choiceList(choices, selected) {
	return [...new Set([...(choices || []), ...(selected || [])])]
}

export function toggleChoice(choices, selected, value, on) {
	const wanted = new Set(selected || [])
	if (on) wanted.add(value)
	else wanted.delete(value)
	return choiceList(choices, selected).filter((choice) => wanted.has(choice))
}
