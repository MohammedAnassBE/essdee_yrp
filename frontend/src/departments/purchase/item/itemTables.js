const scalarFields = ["secondary_unit_of_measure", "product_category"]
const tableColumns = {
	uoms: ["uom", "conversion_factor"],
	additional_parameters: ["additional_parameter_key", "additional_parameter_value"],
	yarn_ratio_details: ["yarn_item", "ratio"],
}

export function stockUomRows(rows = [], stockUom = "", previousStockUom = "") {
	const copied = rows.map((row) => ({ ...row }))
	const retained = copied.filter((row) => !(previousStockUom && row.injectedStockUom === previousStockUom && row.uom === previousStockUom && Number(row.conversion_factor) === 1 && !row.name))
	if (stockUom && !retained.some((row) => row.uom === stockUom)) retained.unshift({ uom: stockUom, conversion_factor: 1, injectedStockUom: stockUom })
	return retained
}

export function itemTableValues(values = {}) {
	return {
		...Object.fromEntries(scalarFields.map((field) => [field, values[field] || ""])),
		...Object.fromEntries(Object.keys(tableColumns).map((field) => [field, (values[field] || []).map((row) => ({ ...row }))])),
		uoms: stockUomRows(values.uoms || [], values.stock_uom),
		categories: [...(values.categories || [])],
		po_excess_allowed_percentage: values.po_excess_allowed_percentage ?? 0,
		is_cloth_item: Number(values.is_cloth_item || 0),
		is_ineligible_for_itc: Number(values.is_ineligible_for_itc || 0),
	}
}

export function itemTableSaveValues(values = {}) {
	const result = itemTableValues(values)
	for (const [field, columns] of Object.entries(tableColumns)) {
		result[field] = result[field].map((row) => Object.fromEntries(["name", ...columns].map((column) => [column, row[column] ?? null])))
	}
	return result
}

export function uomConversionWording(row, stockUom) {
	if (row.conversion_factor == null || String(row.conversion_factor).trim() === "") return "—"
	return `1 ${row.uom} = ${row.conversion_factor} ${stockUom}`
}

export function uniqueProblemMessages(problems = []) {
	return [...new Set(problems.map((problem) => problem.message))]
}

export function stageConversionProblems(values = {}) {
	if (!values.dependent_attribute) return []
	const positive = new Set((values.uoms || []).filter((row) => Number(row.conversion_factor) > 0).map((row) => row.uom))
	return (values.dependent_details || []).flatMap((row) => {
		if (!row.uom) return [{ field: "uoms", stage: row.value, message: `Select a valid UOM for ${values.dependent_attribute} ${row.value}.` }]
		if (row.uom === values.stock_uom || positive.has(row.uom)) return []
		return [{ field: "uoms", stage: row.value, message: `Stage ${row.value} uses UOM ${row.uom}, but UOM Conversion Details has no ${row.uom} → ${values.stock_uom} conversion. Add a ${row.uom} conversion first.` }]
	})
}

export function duplicateParameterProblems(rows = []) {
	const counts = new Map()
	const foldedKey = (row) => String(row.additional_parameter_key || "").trim().toUpperCase().toLowerCase()
	for (const row of rows) counts.set(foldedKey(row), (counts.get(foldedKey(row)) || 0) + 1)
	return rows.flatMap((row, index) => {
		const key = row.additional_parameter_key
		const message = !key ? `Row ${index + 1}: select an Additional Parameter Key.`
			: counts.get(foldedKey(row)) > 1 ? `Additional Parameter Key ${key} is repeated.` : ""
		return message ? [{ field: "additional_parameters", row: index, message }] : []
	})
}

export function stageAttributeProblems(values = {}) {
	if (!values.dependent_attribute) return []
	return (values.dependent_details || []).filter((row) => !row.attributes?.length).map((row) => ({
		field: "stage_attributes", stage: row.value, message: `Stage ${row.value} must use at least one attribute.`,
	}))
}

export function stageVariantNameProblems(values = {}) {
	if (!values.dependent_attribute) return []
	const seen = new Map()
	return (values.dependent_details || []).flatMap((row) => {
		const signature = JSON.stringify([String(row.display_name || "").trim(), [...new Set(row.attributes || [])].sort()])
		if (!seen.has(signature)) {
			seen.set(signature, row.value)
			return []
		}
		const first = seen.get(signature)
		const message = `Stages ${first} and ${row.value} would create variants with the same name. Give one of them a Display Name or tick different attributes.`
		return [first, row.value].map((stage) => ({ field: "dependent_details", stage, message }))
	})
}

function uomProblems(values) {
	const rows = stockUomRows(values.uoms || [], values.stock_uom)
	return rows.flatMap((row, index) => {
		let message = ""
		if (!row.uom) message = `Select a valid UOM in UOM Conversion Details row ${index + 1}.`
		else if (rows.filter((other) => other.uom === row.uom).length > 1) message = `Unit of Measure ${row.uom} has been entered more than once in Conversion Factor Table`
		else if (row.uom === values.stock_uom && Number(row.conversion_factor) !== 1) message = `Conversion factor for default Unit of Measure must be 1 in row ${index + 1}`
		else if (!Number.isFinite(Number(row.conversion_factor)) || Number(row.conversion_factor) <= 0) message = `Conversion factor for UOM ${row.uom} must be greater than 0.`
		return message ? [{ field: "uoms", row: index, message }] : []
	})
}

export function yarnRatioTotal(rows = []) {
	return rows.reduce((total, row) => total + Number(row.ratio || 0), 0)
}

function yarnProblems(values) {
	if (!Number(values.is_cloth_item)) return []
	const rows = values.yarn_ratio_details || []
	if (!rows.length) return [{ field: "yarn_ratio_details", message: "Add at least one Yarn Ratio row for a Cloth Item." }]
	const problems = rows.flatMap((row, index) => {
		const invalid = !row.yarn_item || !Number.isFinite(Number(row.ratio)) || Number(row.ratio) <= 0 || rows.some((other, otherIndex) => otherIndex !== index && other.yarn_item === row.yarn_item)
		return invalid ? [{ field: "yarn_ratio_details", row: index, message: `Row ${index + 1}: select a unique Yarn Item and a Ratio greater than zero.` }] : []
	})
	if (Math.abs(yarnRatioTotal(rows) - 100) > 0.001) problems.push({ field: "yarn_ratio_details", message: `Yarn Ratio total must be exactly 100%. Current total is ${yarnRatioTotal(rows)}%.` })
	return problems
}

export function itemTableProblems(values = {}) {
	const problems = [...uomProblems(values), ...stageConversionProblems(values), ...stageAttributeProblems(values), ...stageVariantNameProblems(values), ...duplicateParameterProblems(values.additional_parameters), ...yarnProblems(values)]
	const percentage = Number(values.po_excess_allowed_percentage ?? 0)
	if (!Number.isFinite(percentage) || percentage < 0) problems.push({ field: "po_excess_allowed_percentage", message: "PO Excess Allowed Percentage must be greater than or equal to 0." })
	return problems
}

function conversionSignature(values) {
	const sorted = (rows) => rows.sort(([left], [right]) => String(left).localeCompare(String(right)))
	return JSON.stringify([
		sorted(stockUomRows(values.uoms || [], values.stock_uom).map((row) => [row.uom, Number(row.conversion_factor)])),
		sorted((values.dependent_details || []).map((row) => [row.value, row.uom])),
	])
}

export function itemAttributeEditing(editor = {}, canWrite = false) {
	return {
		rows: canWrite && !editor.attributes_locked,
		values: canWrite,
		primary: canWrite && !editor.primary_attribute_locked,
		dependent: canWrite && !editor.dependent_attribute_locked,
		createValues: canWrite && Boolean(editor.permissions?.can_write_item_attribute),
	}
}

function missingPrimaryWarning(editor) {
	const warning = "Box Sticker auto-create and size-wise pricing need a Primary Attribute."
	if (!editor.primary_attribute_locked) return warning
	return `${warning} ${editor.primary_attribute_lock_message || "Primary Attribute is locked because YRP stock exists for this Item."}`
}

export function itemTableWarnings(values = {}, editor = {}, original = null) {
	const warnings = []
	if (values.attributes?.length && !values.primary_attribute) warnings.push(missingPrimaryWarning(editor))
	if (editor.has_item_transactions && original && conversionSignature(values) !== conversionSignature(original)) warnings.push("Submitted rows keep their stored factor; open drafts and Lots recalculate.")
	const packingUom = editor.fg_uom || "Box"
	const packingRow = (values.uoms || []).find((row) => row.uom === packingUom)
	if (Number(editor.fg_pcs_per_box) > 0 && packingRow && Number(packingRow.conversion_factor) !== Number(editor.fg_pcs_per_box)) warnings.push(`${packingUom} conversion factor differs from FG Item Master Pieces Per Box (${editor.fg_pcs_per_box}).`)
	return warnings
}

export function additionalParameterWording(row) {
	return `${row.additional_parameter_key} ${row.additional_parameter_value || "(chosen per PO)"}`
}
