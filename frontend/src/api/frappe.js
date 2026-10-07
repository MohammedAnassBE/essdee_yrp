import { extractServerMessage } from "./errorMessages.js"

function csrfToken() {
	return window.csrf_token || window.frappe?.csrf_token || ""
}

function queryString(params) {
	const query = new URLSearchParams()
	for (const [key, value] of Object.entries(params)) {
		if (value === undefined || value === null || value === "") continue
		query.set(key, typeof value === "object" ? JSON.stringify(value) : String(value))
	}
	const value = query.toString()
	return value ? `?${value}` : ""
}

async function request(url, options = {}) {
	const response = await fetch(url, {
		credentials: "include",
		...options,
		headers: {
			Accept: "application/json",
			"Content-Type": "application/json",
			"X-Frappe-CSRF-Token": csrfToken(),
			...options.headers,
		},
	})

	if (response.status === 401) {
		window.location.assign(`/login?redirect-to=${encodeURIComponent(window.location.pathname)}`)
		throw new Error("Your session has expired.")
	}

	const payload = response.status === 204 ? {} : await response.json().catch(() => ({}))
	if (!response.ok || payload.exc) {
		throw new Error(extractServerMessage(payload, "The server could not complete this action. Please try again. If the problem continues, contact your administrator."))
	}
	return payload
}

export async function callMethod(method, args = {}) {
	const payload = await request(`/api/method/${method}`, {
		method: "POST",
		body: JSON.stringify(args),
	})
	return payload.message
}

export async function getMeta(doctype) {
	const payload = await request(
		`/api/method/frappe.desk.form.load.getdoctype?doctype=${encodeURIComponent(doctype)}`,
		{ method: "GET" },
	)
	return payload.docs || []
}

export async function getDoc(doctype, name) {
	const payload = await request(
		`/api/resource/${encodeURIComponent(doctype)}/${encodeURIComponent(name)}`,
		{ method: "GET" },
	)
	return payload.data || null
}

export async function createDoc(doctype, values) {
	const payload = await request(`/api/resource/${encodeURIComponent(doctype)}`, {
		method: "POST",
		body: JSON.stringify(values),
	})
	return payload.data || null
}

export async function updateDoc(doctype, name, values) {
	const payload = await request(
		`/api/resource/${encodeURIComponent(doctype)}/${encodeURIComponent(name)}`,
		{
			method: "PUT",
			body: JSON.stringify(values),
		},
	)
	return payload.data || null
}

export function submitDoc(doctype, name, modified = "") {
	return updateDoc(doctype, name, {
		docstatus: 1,
		...(modified ? { modified } : {}),
	})
}

export function cancelDoc(doctype, name, modified = "") {
	return updateDoc(doctype, name, {
		docstatus: 2,
		...(modified ? { modified } : {}),
	})
}

export async function getList(
	doctype,
	{ fields = ["name"], filters = [], orderBy = "modified desc", start = 0, pageLength = 20 } = {},
) {
	const params = {
		fields,
		filters,
		order_by: orderBy,
		limit_start: start,
		limit_page_length: pageLength,
	}
	const payload = await request(
		`/api/resource/${encodeURIComponent(doctype)}${queryString(params)}`,
		{ method: "GET" },
	)
	return payload.data || []
}

export async function getCount(doctype, filters = []) {
	const value = await callMethod("frappe.desk.reportview.get_count", { doctype, filters })
	return Number(value || 0)
}

export async function searchLink(
	doctype,
	text = "",
	filters = {},
	pageLength = 20,
	matchVisibleOnly = false,
) {
	if (!doctype) return []
	const rows = await callMethod("essdee_yrp.api.link_search.link_search", {
		doctype,
		txt: text,
		filters,
		page_length: pageLength,
		match_visible_only: matchVisibleOnly,
	})
	return Array.isArray(rows) ? rows : []
}

export async function searchLinkedDocument(
	doctype,
	linkDoctype,
	linkName,
	text = "",
	pageLength = 20,
) {
	if (!doctype || !linkDoctype || !linkName) return []
	const rows = await callMethod("essdee_yrp.api.link_search.linked_document_search", {
		doctype,
		link_doctype: linkDoctype,
		link_name: linkName,
		txt: text,
		page_length: pageLength,
	})
	return Array.isArray(rows) ? rows : []
}

export async function getBulkEditFields(doctype) {
	const fields = await callMethod("essdee_yrp.api.bulk_edit.get_bulk_edit_fields", { doctype })
	return Array.isArray(fields) ? fields : []
}

export function bulkUpdateField(doctype, docnames, field, value) {
	return callMethod("essdee_yrp.api.bulk_edit.bulk_update_field", {
		doctype,
		docnames,
		fieldname: field.fieldname,
		value,
		child_doctype: field.child_doctype || null,
		parent_table_field: field.parent_table_field || null,
	})
}

const USER_LISTVIEW_METHOD = "yrp.yrp.doctype.yrp_user_listview.yrp_user_listview"

export async function getUserListview(doctype) {
	const rows = await callMethod(`${USER_LISTVIEW_METHOD}.get_user_listview`, {
		doctype_name: doctype,
	})
	return Array.isArray(rows) ? rows : null
}

export function saveUserListview(doctype, columns) {
	return callMethod(`${USER_LISTVIEW_METHOD}.save_user_listview`, {
		doctype_name: doctype,
		columns: JSON.stringify(columns),
	})
}

export function resetUserListview(doctype) {
	return callMethod(`${USER_LISTVIEW_METHOD}.reset_user_listview`, {
		doctype_name: doctype,
	})
}
