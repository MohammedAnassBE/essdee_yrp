export const TEMPLATE_ITEM_FILTER = Object.freeze(["variant_of", "is", "not set"])

function linkFilterObject(linkFilters) {
	const parsed = typeof linkFilters === "string" && linkFilters ? JSON.parse(linkFilters) : linkFilters
	if (!Array.isArray(parsed)) return parsed && typeof parsed === "object" ? parsed : {}
	return Object.fromEntries(parsed.filter(Array.isArray).map((filter) => {
		const [fieldname, operator, value] = filter.length >= 4 ? filter.slice(1) : filter
		return [fieldname, operator === "=" ? value : [operator, value]]
	}))
}

export function templateItemLinkFilters(linkFilters) {
	const [fieldname, operator, value] = TEMPLATE_ITEM_FILTER
	return { ...linkFilterObject(linkFilters), [fieldname]: [operator, value] }
}

function itemFilterParts(filter, itemFields) {
	if (!Array.isArray(filter) || ![3, 4].includes(filter.length)) return null
	const [doctype, fieldname, operator, value] = filter.length === 4 ? filter : ["", ...filter]
	if (!["=", "!=", "in", "not in"].includes(operator)) return null
	if (!itemFields.some(field => (field.doctype || "") === doctype && field.fieldname === fieldname)) return null
	const items = ["in", "not in"].includes(operator)
		? (Array.isArray(value) ? value : String(value).split(",").map(item => item.trim()))
		: [value]
	return { operator, items: items.filter(item => item !== "" && item != null) }
}

export function templateItemFilterItems(filters, itemFields) {
	return [...new Set(filters.flatMap(filter => itemFilterParts(filter, itemFields)?.items || []))]
}

export function expandTemplateItemFilters(filters, itemFields, variantsByItem) {
	return filters.map(filter => {
		const parts = itemFilterParts(filter, itemFields)
		if (!parts) return filter
		const operator = ["!=", "not in"].includes(parts.operator) ? "not in" : "in"
		const values = [...new Set(parts.items.flatMap(item => variantsByItem[item] || [item]))]
		return [...filter.slice(0, -2), operator, values]
	})
}

export function hasChildTableFilter(filters, doctype) {
	return filters.some(filter => Array.isArray(filter) && filter.length === 4 && filter[0] && filter[0] !== doctype)
}

export function parentGroupBy(filters, doctype) {
	return hasChildTableFilter(filters, doctype) ? `\`tab${doctype}\`.\`name\`` : undefined
}
