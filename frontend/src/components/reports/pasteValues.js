export const PASTE_FORMATS = [
	{ label: "One per line", value: "list" },
	{ label: "Comma separated", value: "comma" },
]

export function parsePastedNames(text, format = "list") {
	const separator = format === "comma" ? /,/ : /[\t\r\n]+/
	return [...new Set(String(text || "").split(separator).map((name) => name.trim()).filter(Boolean))]
}

export function mergeNames(current, names) {
	return [...new Set([...(current || []), ...names])]
}
