export function buildPrintUrl({ doctype, name, format, letterHead, triggerPrint = true, noLetterhead }) {
	const query = new URLSearchParams({ doctype, name, trigger_print: triggerPrint ? "1" : "0", format })
	if (noLetterhead !== null) query.set("no_letterhead", (noLetterhead ?? !letterHead) ? "1" : "0")
	if (letterHead) query.set("letterhead", letterHead)
	return `/printview?${query}`
}

export function openPrintUrl(url) {
	return Boolean(window.open(url, "_blank"))
}
