export function defaultOption(current, options, preferred = "") {
	if (current) return current
	if (preferred) return preferred
	return options?.length === 1 ? (options[0].name ?? options[0]) : ""
}
