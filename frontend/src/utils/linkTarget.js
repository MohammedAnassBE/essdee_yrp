import { hasWebDocumentPage, webDocumentRoute } from "../router/webDocumentRoutes.js"

export function canReadDoctype(doctype, boot = globalThis.window?.frappe?.boot) {
	if (globalThis.window?.frappe?.session?.user === "Administrator" || boot?.user?.name === "Administrator") return true
	return Array.isArray(boot?.user?.can_read) && boot.user.can_read.includes(doctype)
}

export function deskDocumentPath(doctype, name) {
	const slug = doctype.toLowerCase().replace(/ /g, "-")
	return `/desk/${slug}/${encodeURIComponent(name)}`
}

export function documentLinkTarget(doctype, name, currentPath) {
	if (!doctype || name === null || name === undefined || !String(name).trim()) return null
	if (!hasWebDocumentPage(doctype, currentPath)) return { href: deskDocumentPath(doctype, name), route: null }
	const route = webDocumentRoute(doctype, String(name), currentPath)
	return { href: `/web${route}`, route }
}

export function linkFieldTarget(field, record = {}) {
	const doctype = field.link_doctype || (field.fieldtype === "Link" ? field.options
		: field.fieldtype === "Dynamic Link" ? record[field.options] : null)
	const name = String(field.link_name ?? field.value ?? "").trim()
	return doctype && name ? { doctype, name } : null
}
