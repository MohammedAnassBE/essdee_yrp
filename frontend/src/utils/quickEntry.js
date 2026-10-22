const LAYOUT_TYPES = new Set(["Section Break", "Column Break", "Tab Break", "HTML", "Button", "Heading", "Fold", "Image"])
const TABLE_TYPES = new Set(["Table", "Table MultiSelect"])

export function linkCreateValues(filters = {}, createValues = null) {
	if (createValues) return { ...createValues }
	return Object.fromEntries(Object.entries(filters || {}).filter(([, value]) =>
		(typeof value === "string" && value !== "") || typeof value === "number"))
}

function isPromptNamed(meta) {
	return meta.autoname === "Prompt" || meta.naming_rule === "Set by user"
}

export function quickEntryPlan(meta, presets = {}, query = "") {
	const fields = (meta?.fields || []).filter((field) => !LAYOUT_TYPES.has(field.fieldtype)
		&& !field.hidden && !field.read_only && (field.reqd || field.allow_in_quick_entry))
	if (fields.some((field) => TABLE_TYPES.has(field.fieldtype))) return { supported: false, fields: [], locked: [], values: {} }
	if (isPromptNamed(meta)) fields.unshift({ fieldname: "__newname", fieldtype: "Data", label: `${meta.name} Name`, reqd: 1 })
	const known = new Set((meta?.fields || []).map((field) => field.fieldname))
	const values = Object.fromEntries(Object.entries(presets || {}).filter(([fieldname]) => known.has(fieldname)))
	const locked = fields.map((field) => field.fieldname).filter((fieldname) => fieldname in values)
	const titleField = fields.find((field) => field.fieldname === "__newname")
		|| fields.find((field) => field.fieldname === meta.title_field && !(field.fieldname in values))
		|| fields.find((field) => field.fieldtype === "Data" && !(field.fieldname in values))
	if (query && titleField) values[titleField.fieldname] = query
	return { supported: true, fields, locked, values }
}
