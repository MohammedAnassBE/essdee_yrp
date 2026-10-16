export function listStatusFilters(fieldname, options, value) {
	const option = options.find((candidate) =>
		String(typeof candidate === "string" ? candidate : candidate.value) === String(value),
	)
	return Array.isArray(option?.filters) ? option.filters : [[fieldname, "=", value]]
}
