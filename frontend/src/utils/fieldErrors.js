import { plainTextFromHtml } from "./documentValues.js"

export function requiredFieldErrors(fields, values) {
	return Object.fromEntries(fields
		.filter((field) => field.reqd && !String(values[field.fieldname] ?? "").trim())
		.map((field) => [field.fieldname, `${field.label} is required.`]))
}

export function mapFieldError(reason, fields, fallback = "Unable to save this document.") {
	const source = typeof reason === "string" ? reason : reason?.message
	const message = plainTextFromHtml(source || fallback).trim() || fallback
	const errors = {}
	const messages = []
	for (const rawLine of message.split("\n")) {
		const line = rawLine.replace(/^(?:[\w.]*Error|Error):\s*/i, "")
			.replace(/^\[[^\]\n]+,\s*[^\]\n]+\]:\s*/, "").trim()
		if (!line) continue
		let matched = false
		const missing = line.match(/Value missing for [^:]+:\s*(.+)$/i)
		const text = missing?.[1] || line
		for (const field of fields) {
			const names = [field.label, field.fieldname].filter(Boolean)
			if (!names.some((name) => text.toLowerCase().includes(name.toLowerCase()))) continue
			matched = true
			errors[field.fieldname] = missing || /required|mandatory|missing/i.test(line)
				? `${field.label} is required.`
				: line
		}
		if (!matched) messages.push(/Value missing for|MandatoryError|Traceback/i.test(line)
			? "Complete the required fields before saving."
			: line)
	}
	return {
		fields: errors,
		message: [...new Set(messages)].join("\n"),
	}
}
