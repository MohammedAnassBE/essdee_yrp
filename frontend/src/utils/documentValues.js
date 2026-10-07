export function hasDocumentDisplayValue(value) {
	if (value === null || value === undefined) return false
	if (typeof value === "string") return Boolean(value.trim())
	if (Array.isArray(value)) return value.length > 0
	if (typeof value === "object") return Object.keys(value).length > 0
	return true
}

const htmlEntities = {
	"&amp;": "&",
	"&lt;": "<",
	"&gt;": ">",
	"&quot;": '"',
	"&#39;": "'",
	"&apos;": "'",
	"&nbsp;": " ",
}

export function plainTextFromHtml(value) {
	if (value === null || value === undefined) return ""
	return String(value)
		.replace(/<br\s*\/?\s*>/gi, "\n")
		.replace(/<\/(?:div|p|li)\s*>/gi, "\n")
		.replace(/<li(?:\s[^>]*)?>/gi, "• ")
		.replace(/<\/?(?:a|b|blockquote|code|details|div|em|i|ol|p|pre|section|small|span|strong|summary|ul)(?:\s[^>]*)?>/gi, "")
		.replace(/&(amp|lt|gt|quot|#39|apos|nbsp);/gi, (entity) => htmlEntities[entity.toLowerCase()] || entity)
		.replace(/[ \t]+\n/g, "\n")
		.replace(/\n[ \t]+/g, "\n")
		.replace(/\n{3,}/g, "\n\n")
		.trim()
}

export function normaliseFrappeTime(value) {
	const match = String(value || "").trim().match(/^(\d{1,2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?$/)
	if (!match) return ""
	const hours = Number(match[1])
	const minutes = Number(match[2])
	const seconds = Number(match[3] || 0)
	if (hours > 23 || minutes > 59 || seconds > 59) return ""
	return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`
}
