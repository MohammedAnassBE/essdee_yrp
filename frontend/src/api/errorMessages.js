import { plainTextFromHtml } from "../utils/documentValues.js"

function parseJson(value) {
	if (typeof value !== "string") return value
	try {
		return JSON.parse(value)
	} catch {
		return value
	}
}

function valuesFrom(value) {
	const parsed = parseJson(value)
	if (Array.isArray(parsed)) return parsed.flatMap(valuesFrom)
	if (parsed && typeof parsed === "object") {
		for (const key of ["message", "detail", "title", "description"]) {
			if (parsed[key]) return valuesFrom(parsed[key])
		}
		return []
	}
	return parsed === null || parsed === undefined ? [] : [String(parsed)]
}

function tracebackMessage(value) {
	const lines = plainTextFromHtml(value)
		.split("\n")
		.map((line) => line.trim())
		.filter(Boolean)
	for (const line of [...lines].reverse()) {
		const match = line.match(/^(?:[A-Za-z_][\w.]*\.)?([A-Za-z_][\w]*(?:Error|Exception|Warning)):\s*(.+)$/)
		if (match?.[2]) return match[2].trim()
	}
	return ""
}

function cleanMessage(value, { traceback = false } = {}) {
	if (traceback) return tracebackMessage(value)
	let message = plainTextFromHtml(value).trim()
	if (!message) return ""
	const exception = message.match(/^(?:[A-Za-z_][\w.]*\.)?([A-Za-z_][\w]*(?:Error|Exception|Warning)):\s*(.+)$/s)
	if (exception?.[2]) message = exception[2].trim()
	if (/^(?:[A-Za-z_][\w.]*\.)+[A-Za-z_][\w]*(?:Error|Exception|Warning)$/.test(message)) return ""
	if (/Traceback \(most recent call last\)/i.test(message)) return tracebackMessage(message)
	return message
}

function uniqueMessages(values, options = {}) {
	const seen = new Set()
	const messages = []
	for (const value of values.flatMap(valuesFrom)) {
		const message = cleanMessage(value, options)
		if (!message || seen.has(message)) continue
		seen.add(message)
		messages.push(message)
	}
	return messages
}

export function extractServerMessage(payload, fallback = "Something went wrong.") {
	const sources = [
		[payload?._server_messages],
		[payload?._error_message],
		[payload?.errors, payload?.messages],
		[payload?.message],
		[payload?.exception],
	]
	for (const source of sources) {
		const messages = uniqueMessages(source)
		if (messages.length) return messages.join("\n")
	}
	const traceback = uniqueMessages([payload?.exc], { traceback: true })
	return traceback.length ? traceback.join("\n") : fallback
}
