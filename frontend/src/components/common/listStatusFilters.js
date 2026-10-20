export function listStatusFilters(fieldname, options, value) {
	const option = options.find((candidate) =>
		String(typeof candidate === "string" ? candidate : candidate.value) === String(value),
	)
	return Array.isArray(option?.filters) ? option.filters : [[fieldname, "=", value]]
}

export function listStandardFilterFields(fields, { statusField = "", statusOptions = [] } = {}) {
	if (!statusField || !statusOptions.length) return fields
	const replaced = new Set(["status", statusField])
	const index = fields.findIndex((field) => replaced.has(field.fieldname))
	if (index < 0) return fields
	const choices = statusOptions.map((option) =>
		typeof option === "string" ? { label: option, value: option } : { label: option.label, value: option.value },
	)
	const statusFilter = { ...fields[index], fieldname: statusField, fieldtype: "Select", options: "", choices }
	const rest = fields.filter((field, position) => position !== index && !replaced.has(field.fieldname))
	return [...rest.slice(0, index), statusFilter, ...rest.slice(index)]
}
