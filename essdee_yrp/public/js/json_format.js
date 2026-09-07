// Read-only JSON is data, including when historical rows contain HTML/code.
// Frappe's generic Data fallback inserts JSON strings into the display DOM.
export function format_json_as_code(value, code_formatter) {
    const text = value == null ? "" : typeof value === "string" ? value : JSON.stringify(value, null, 2);
    return code_formatter(text);
}

export function install_json_formatter(formatters) {
    // Keep an upstream/custom JSON implementation when one is already present.
    if (typeof formatters.JSON === "function") return;
    formatters.JSON = (value) => format_json_as_code(value, formatters.Code);
}
