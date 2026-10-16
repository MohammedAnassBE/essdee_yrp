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
		throw requestError("Your session has expired.", response.status)
	}

	const payload = response.status === 204 ? {} : await response.json().catch(() => ({}))
	if (!response.ok || payload.exc) {
		throw requestError(
			extractServerMessage(payload, "The server could not complete this action. Please try again. If the problem continues, contact your administrator."),
			response.status,
			payload,
		)
	}
	return payload
}

export async function callMethod(method, args = {}, requestOptions = {}) {
	const payload = await request(`/api/method/${method}`, {
		...requestOptions,
		method: "POST",
		body: JSON.stringify(args),
	})
	return payload.message
}

function requestError(message, status, payload = {}) {
	return Object.assign(new Error(message), { status, exc_type: payload.exc_type, serverMessages: payload._server_messages })
}

export function uploadFile(file, options = {}) {
	if (!(file instanceof File)) return Promise.reject(new Error("Choose a file to upload."))
	const {
		doctype = "",
		docname = "",
		fieldname = "",
		isPrivate = 1,
		onProgress = null,
		signal = null,
		method = "",
		fields = {},
	} = options

	return new Promise((resolve, reject) => {
		const form = new FormData()
		form.append("file", file, file.name)
		form.append("is_private", isPrivate ? "1" : "0")
		if (doctype) form.append("doctype", doctype)
		if (docname) form.append("docname", docname)
		if (fieldname) form.append("fieldname", fieldname)
		if (method) form.append("method", method)
		for (const [key, value] of Object.entries(fields)) {
			if (value !== undefined && value !== null && value !== "") form.append(key, String(value))
		}

		const xhr = new XMLHttpRequest()
		let settled = false
		const finish = (callback, value) => {
			if (settled) return
			settled = true
			signal?.removeEventListener?.("abort", abort)
			callback(value)
		}
		const abort = () => {
			xhr.abort()
			finish(reject, new DOMException("Upload cancelled.", "AbortError"))
		}

		xhr.open("POST", "/api/method/upload_file")
		xhr.withCredentials = true
		xhr.setRequestHeader("Accept", "application/json")
		xhr.setRequestHeader("X-Frappe-CSRF-Token", csrfToken())
		xhr.upload.addEventListener("progress", (event) => {
			if (!event.lengthComputable || typeof onProgress !== "function") return
			onProgress(Math.min(100, Math.round((event.loaded / event.total) * 100)))
		})
		xhr.addEventListener("load", () => {
			let payload = {}
			try { payload = xhr.responseText ? JSON.parse(xhr.responseText) : {} } catch { /* handled below */ }
			if (xhr.status === 401) {
				window.location.assign(`/login?redirect-to=${encodeURIComponent(window.location.pathname)}`)
				finish(reject, new Error("Your session has expired."))
				return
			}
			if (xhr.status < 200 || xhr.status >= 300 || payload.exc) {
				finish(reject, new Error(extractServerMessage(payload, "The file could not be uploaded. Please try again.")))
				return
			}
			if (typeof onProgress === "function") onProgress(100)
			finish(resolve, payload.message || payload.data || payload)
		})
		xhr.addEventListener("error", () => finish(reject, new Error("The file upload was interrupted. Check your connection and try again.")))
		xhr.addEventListener("abort", () => finish(reject, new DOMException("Upload cancelled.", "AbortError")))
		if (signal?.aborted) abort()
		else {
			signal?.addEventListener?.("abort", abort, { once: true })
			xhr.send(form)
		}
	})
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

const USER_LISTVIEW_METHOD = "essdee_yrp.api.list_columns"

export async function getUserListview(doctype, viewFields = []) {
	const settings = await callMethod(`${USER_LISTVIEW_METHOD}.get_user_listview`, {
		doctype_name: doctype,
		view_fields: viewFields,
	})
	if (
		!settings
		|| typeof settings !== "object"
		|| !Array.isArray(settings.fields)
		|| (settings.columns !== null && !Array.isArray(settings.columns))
		|| (settings.currency_fields !== undefined && (
			typeof settings.currency_fields !== "object"
			|| settings.currency_fields === null
			|| Array.isArray(settings.currency_fields)
			|| Object.entries(settings.currency_fields).some(([fieldname, reference]) =>
				!fieldname || typeof reference !== "string" || !reference.trim(),
			)
		))
	) {
		throw new Error(`Invalid list column settings returned for ${doctype}.`)
	}
	return { ...settings, currency_fields: settings.currency_fields || {} }
}

export function saveUserListview(doctype, columns, viewFields = []) {
	return callMethod(`${USER_LISTVIEW_METHOD}.save_user_listview`, {
		doctype_name: doctype,
		columns,
		view_fields: viewFields,
	})
}

export function resetUserListview(doctype) {
	return callMethod(`${USER_LISTVIEW_METHOD}.reset_user_listview`, {
		doctype_name: doctype,
	})
}

export async function downloadMethodFile(method, args = {}, fallbackName = "download") {
	const response = await fetch(`/api/method/${method}`, {
		method: "POST",
		credentials: "include",
		headers: { "Content-Type": "application/json", "X-Frappe-CSRF-Token": csrfToken() },
		body: JSON.stringify(args),
	})
	if (!response.ok) {
		const payload = await response.json().catch(() => ({}))
		throw new Error(extractServerMessage(payload, "The file could not be downloaded. Please try again."))
	}
	const disposition = response.headers.get("Content-Disposition") || ""
	const filename = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(disposition)?.[1] || fallbackName
	const url = URL.createObjectURL(await response.blob())
	const link = document.createElement("a")
	link.href = url
	link.download = decodeURIComponent(filename)
	link.click()
	window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}
