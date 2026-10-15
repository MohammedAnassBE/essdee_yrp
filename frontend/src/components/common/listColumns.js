import { syncOrderedDraft } from "./orderedDraft.js"

export const frappeStandardFilterFields = [
	{ fieldname: "name", fieldtype: "Link", label: "ID" },
	{ fieldname: "owner", fieldtype: "Link", label: "Created By", options: "User" },
	{ fieldname: "idx", fieldtype: "Int", label: "Index" },
	{ fieldname: "creation", fieldtype: "Datetime", label: "Created On" },
	{ fieldname: "modified", fieldtype: "Datetime", label: "Last Updated On" },
	{ fieldname: "modified_by", fieldtype: "Link", label: "Last Updated By", options: "User" },
	{ fieldname: "_user_tags", fieldtype: "Data", label: "Tags" },
	{ fieldname: "_liked_by", fieldtype: "Data", label: "Liked By" },
	{ fieldname: "_comments", fieldtype: "Text", label: "Comments" },
	{ fieldname: "_assign", fieldtype: "Text", label: "Assigned To" },
	{ fieldname: "docstatus", fieldtype: "Int", label: "Document Status" },
]

export function buildColumnOptions(fields, savedColumns, defaultColumns = []) {
	const optionalFields = fields.filter((field) => field.fieldname && field.fieldname !== "name")
	const byName = new Map(optionalFields.map((field) => [field.fieldname, field]))
	const validSavedColumns = Array.isArray(savedColumns)
		? savedColumns.filter((column) => byName.has(column.fieldname))
		: []
	if (validSavedColumns.length) {
		const enabled = []
		const disabled = []
		const seen = new Set()
		for (const saved of validSavedColumns) {
			const field = byName.get(saved.fieldname)
			if (seen.has(field.fieldname)) continue
			const configured = { ...field, enabled: Boolean(saved.enabled) }
			if (configured.enabled) enabled.push(configured)
			else disabled.push(configured)
			seen.add(field.fieldname)
		}
		const newDefaults = defaultColumns.flatMap((fieldname) => {
			const field = byName.get(fieldname)
			if (!field || seen.has(fieldname)) return []
			seen.add(fieldname)
			return [{ ...field, enabled: true }]
		})
		const remaining = []
		for (const field of optionalFields) {
			if (!seen.has(field.fieldname)) remaining.push({ ...field, enabled: false })
		}
		return [...enabled, ...newDefaults, ...disabled, ...remaining]
	}

	const defaults = new Set(defaultColumns)
	const configured = optionalFields.map((field) => ({
		...field,
		enabled: defaults.size ? defaults.has(field.fieldname) : Boolean(field.inListView),
	}))
	if (!configured.some((field) => field.enabled)) {
		configured.slice(0, 5).forEach((field) => {
			field.enabled = true
		})
	}
	return configured
}

export function matchesColumnSearch(column, search) {
	const query = String(search || "").trim().toLowerCase()
	if (!query) return true
	return [column.label, column.fieldname].some((value) =>
		String(value || "").toLowerCase().includes(query),
	)
}

export function syncColumnDraft(currentColumns, incomingColumns, { visible, edited }) {
	return syncOrderedDraft(currentColumns, incomingColumns, {
		visible,
		edited,
		clone: (column) => ({
			fieldname: column.fieldname,
			fieldtype: column.fieldtype,
			label: column.label,
			enabled: Boolean(column.enabled),
		}),
	})
}

export function canSaveColumnDraft(settingsReady, columns) {
	return Boolean(settingsReady && Array.isArray(columns) && columns.length)
}

export function createListInitialisationGuard() {
	let generation = 0
	return {
		begin(doctype) {
			generation += 1
			return { doctype, generation }
		},
		snapshot(doctype) {
			return { doctype, generation }
		},
		isCurrent(request, doctype) {
			return Boolean(
				request
				&& request.doctype === doctype
				&& request.generation === generation,
			)
		},
	}
}

export function currencyReferenceField(column, currencyFields = {}) {
	if (column?.fieldtype !== "Currency") return ""
	return String(currencyFields?.[column.fieldname] || "").trim()
}

export function activeCurrencyReferences(columns, currencyFields = {}) {
	return [...new Set(
		(columns || [])
			.map((column) => currencyReferenceField(column, currencyFields))
			.filter(Boolean),
	)]
}
