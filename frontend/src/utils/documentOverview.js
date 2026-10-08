import { plainTextFromHtml } from "./documentValues.js"

export function documentOverviewHasValue(value) {
	if (value === null || value === undefined) return false
	return typeof value !== "string" || value.trim() !== ""
}

export function buildDocumentOverviewGroups(fields = [], definitions = [], options = {}) {
	const visibleFields = fields.filter((field) => field?.fieldname && !field.hidden && (options.includeEmpty || documentOverviewHasValue(field.value)))
	const byName = new Map(visibleFields.map((field) => [field.fieldname, field]))
	const claimed = new Set()
	const groups = definitions.flatMap((definition) => {
		const groupFields = (definition.fields || []).map((fieldname) => byName.get(fieldname)).filter(Boolean)
		if (!groupFields.length) return []
		groupFields.forEach((field) => claimed.add(field.fieldname))
		return [{ ...definition, fields: groupFields }]
	})

	if (options.includeUnclaimed) {
		const unclaimed = visibleFields.filter((field) => !claimed.has(field.fieldname))
		if (unclaimed.length) {
			groups.push({
				key: "additional",
				label: "Additional details",
				description: "Other document information",
				icon: "pi pi-ellipsis-h",
				...(options.unclaimedDefinition || {}),
				fields: unclaimed,
			})
		}
	}

	return groups
}

export function formatDocumentOverviewValue(field = {}) {
	const value = field.value
	if (["Date", "Datetime"].includes(field.fieldtype) && documentOverviewHasValue(value)) {
		const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?/)
		if (match) return `${match[3]}-${match[2]}-${match[1]}${field.fieldtype === "Datetime" && match[4] ? ` · ${match[4]}:${match[5]}${match[6] ? `:${match[6]}` : ""}` : ""}`
	}
	if (field.fieldtype === "Check") return Number(value) ? "Yes" : "No"
	if (["Currency", "Float", "Int", "Percent"].includes(field.fieldtype)) {
		if (!documentOverviewHasValue(value)) return "—"
		const number = Number(value)
		if (!Number.isFinite(number)) return "—"
		const requestedPrecision = field.precision === null || field.precision === undefined || field.precision === ""
			? null
			: Number(field.precision)
		const hasPrecision = Number.isInteger(requestedPrecision)
		const precision = hasPrecision ? Math.min(20, Math.max(0, requestedPrecision)) : 3
		const formatted = number.toLocaleString("en-IN", {
			...(hasPrecision ? { minimumFractionDigits: precision } : {}),
			maximumFractionDigits: precision,
		})
		return field.fieldtype === "Percent" ? `${formatted}%` : formatted
	}
	return documentOverviewHasValue(value) ? plainTextFromHtml(value) : "—"
}
