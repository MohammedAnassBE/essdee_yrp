function approvalTone(value) {
	if (/\b(not approved|unapproved)\b/.test(value)) return "warning"
	if (/\bapproved\b/.test(value)) return "success"
	return ""
}

export function documentStatusTone(label, docstatus = null) {
	const value = String(label || "").toLowerCase()
	const approval = approvalTone(value)
	if (approval) return approval
	if (/(cancel|reject|fail|error)/.test(value)) return "danger"
	if (/(pending|partial|hold|to receive|to deliver|overdue|approval)/.test(value)) return "warning"
	if (/(ready|queued|running|planned|in progress)/.test(value)) return "info"
	if (/closed/.test(value)) return "neutral"
	if (/(submit|complete|approve|receive|deliver|active|open)/.test(value)) return "success"
	if (Number(docstatus) === 2) return "danger"
	if (Number(docstatus) === 1) return "success"
	return "neutral"
}

export function listStatusTone(status) {
	const value = String(status || "").toLowerCase()
	const approval = approvalTone(value)
	if (approval) return approval
	if (["completed", "fully", "closed"].some((token) => value.includes(token)) && !value.includes("partially")) return "success"
	if (value.includes("pending") || value.includes("cancel") || value.includes("reject") || value.includes("overdue")) return "danger"
	if (value.includes("partial") || value.includes("draft") || value.startsWith("to ") || value.includes("close request")) return "warning"
	if (value.includes("submitted") || value.includes("progress") || value.includes("ready") || value.includes("planned")) return "info"
	return "neutral"
}
