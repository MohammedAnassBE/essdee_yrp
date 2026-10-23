import { formatDatesInText } from "../utils/dateFormat.js"
import { plainTextFromHtml } from "../utils/documentValues.js"

let handler = null

export function setServerMessageHandler(callback) {
	handler = typeof callback === "function" ? callback : null
}

function parseJson(value) {
	if (typeof value !== "string") return value
	try {
		return JSON.parse(value)
	} catch {
		return value
	}
}

function messageText(value) {
	if (Array.isArray(value)) return value.map((row) => (Array.isArray(row) ? row.map(messageText).join(" | ") : messageText(row))).join("\n")
	return formatDatesInText(plainTextFromHtml(value).replace(/<[^>]*>/g, "").trim())
}

/** Normalise the non-error Frappe `_server_messages` into {title, message, indicator, alert} entries. */
export function parseServerMessages(raw) {
	const list = parseJson(raw)
	if (!Array.isArray(list)) return []
	const messages = []
	for (const item of list) {
		const entry = parseJson(item)
		const data = entry && typeof entry === "object" ? entry : { message: entry }
		// A thrown message left behind by an exception the server caught is not a user message.
		if (data.raise_exception) continue
		const message = messageText(data.message)
		if (!message) continue
		messages.push({
			title: messageText(data.title) || "Message",
			message,
			indicator: data.indicator || "",
			alert: Boolean(data.alert || data.toast),
		})
	}
	return messages
}

/** Show the non-error messages of a successful response through the registered handler. */
export function announceServerMessages(payload) {
	if (!handler || !payload?._server_messages) return
	const messages = parseServerMessages(payload._server_messages)
	if (messages.length) handler(messages)
}
