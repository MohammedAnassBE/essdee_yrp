import { extractServerMessage } from "./errorMessages.js"
import { announceServerMessages } from "./serverMessages.js"

const pendingReads = new Map()
const metadata = new Map()
const linkResults = new Map()
const METADATA_LIMIT = 20
const LINK_RESULT_LIMIT = 50
const LINK_RESULT_MS = 30000
const SHORT_LINK_QUERY = 2
// Matches MAX_FILTER_SETS in essdee_yrp/api/list_counts.py.
const COUNT_BATCH_LIMIT = 100
let readGeneration = 0

export function invalidatePendingReads() {
	readGeneration += 1
	pendingReads.clear()
	linkResults.clear()
}

/** Drops every session read cache, including DocType metadata. */
export function clearReadCaches() {
	invalidatePendingReads()
	metadata.clear()
}

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

function sessionExpired(status, payload = {}) {
	return status === 401 || (status === 403 && (
		["AuthenticationError", "SessionExpired"].some((type) => String(payload.exc_type || payload.exception || "").includes(type))
		|| (payload.exc_type === "PermissionError" && /Login to access/i.test(extractServerMessage(payload, "")))
	))
}
function redirectToLogin() {
	clearReadCaches()
	window.location.assign(`/login?redirect-to=${encodeURIComponent(window.location.pathname + window.location.search + window.location.hash)}`)
}

async function request(url, options = {}) {
	const writing = url.startsWith("/api/resource/") && !["GET", "HEAD"].includes(options.method || "GET")
	if (writing) invalidatePendingReads()
	try {
		return await sendRequest(url, options)
	} finally {
		if (writing) invalidatePendingReads()
	}
}

async function sendRequest(url, { silent = false, ...options } = {}) {
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

	const payload = response.status === 204 ? {} : await response.json().catch(() => ({}))
	if (sessionExpired(response.status, payload)) {
		redirectToLogin()
		throw requestError("Your session has expired.", response.status)
	}

	if (!response.ok || payload.exc) {
		throw requestError(
			extractServerMessage(payload, "The server could not complete this action. Please try again. If the problem continues, contact your administrator."),
			response.status,
			payload,
		)
	}
	if (!silent) announceServerMessages(payload)
	return payload
}

export async function callMethod(method, args = {}, requestOptions = {}) {
	// Generic methods may write. Keep only the explicitly shared readers in one generation.
	invalidatePendingReads()
	try {
		return await invokeMethod(method, args, requestOptions)
	} finally {
		invalidatePendingReads()
	}
}

async function invokeMethod(method, args = {}, requestOptions = {}) {
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

/** Ends the Frappe session, then leaves /web for the login page. */
export async function logOut() {
	await invokeMethod("logout")
	clearReadCaches()
	window.location.assign("/login")
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
		invalidatePendingReads()
		const finish = (callback, value) => {
			if (settled) return
			settled = true
			invalidatePendingReads()
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
			if (sessionExpired(xhr.status, payload)) {
				redirectToLogin()
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


function orderedArguments(value) {
	if (Array.isArray(value)) return value.map(orderedArguments)
	if (value && typeof value === "object") {
		return Object.fromEntries(Object.keys(value).sort().map((key) => [key, orderedArguments(value[key])]))
	}
	return value
}

// The user_id cookie follows logins and logouts made in other tabs.
function sessionIdentity() {
	const cookieUser = /(?:^|;\s*)user_id=([^;]*)/.exec(globalThis.document?.cookie || "")?.[1] || ""
	return [window.location?.host, window.frappe?.session?.user, window.frappe?.boot?.user?.name, csrfToken(), cookieUser]
}

function readKey(method, args) {
	return JSON.stringify([...sessionIdentity(), readGeneration, method, orderedArguments(args)])
}

/** Read-only whitelisted method: identical pending calls share one request and never invalidate other reads. */
export async function callRead(method, args = {}) {
	const key = readKey(method, args)
	let pending = pendingReads.get(key)
	if (!pending) {
		pending = invokeMethod(method, args).finally(() => pendingReads.delete(key))
		pendingReads.set(key, pending)
	}
	return structuredClone(await pending)
}

// Cached reads resolve on a later task, like a network response: PrimeVue overlays opened by the
// same click close again when results arrive before that click finishes dispatching.
const nextTask = () => new Promise((done) => setTimeout(done, 0))

function remember(cache, key, value, limit) {
	cache.delete(key)
	cache.set(key, value)
	if (cache.size > limit) cache.delete(cache.keys().next().value)
}

async function linkRead(method, args) {
	if (String(args.txt || "").length > SHORT_LINK_QUERY) return callRead(method, args)
	const key = readKey(method, args)
	const cached = linkResults.get(key)
	if (cached && Date.now() - cached.at < LINK_RESULT_MS) {
		remember(linkResults, key, cached, LINK_RESULT_LIMIT)
		await nextTask()
		// A write or session change during the yield must not deliver the older result.
		return readKey(method, args) === key ? structuredClone(cached.rows) : linkRead(method, args)
	}
	linkResults.delete(key)
	const generation = readGeneration, at = Date.now()
	const rows = await callRead(method, args)
	if (generation === readGeneration) remember(linkResults, key, { at, rows: structuredClone(rows) }, LINK_RESULT_LIMIT)
	return rows
}

export function getActiveWorkflow(doctype) {
	return callRead("essdee_yrp.api.workflow.get_active_workflow", { doctype })
}


const metadataKey = (doctype) => JSON.stringify([...sessionIdentity(), doctype])

/** DocType metadata, cached for the session; each caller gets its own copy. */
export async function getMeta(doctype) {
	const key = metadataKey(doctype)
	const cached = metadata.get(key)
	const docs = cached || request(
		`/api/method/frappe.desk.form.load.getdoctype?doctype=${encodeURIComponent(doctype)}`,
		{ method: "GET" },
	).then((payload) => payload.docs || [])
	if (!cached) docs.catch(() => { if (metadata.get(key) === docs) metadata.delete(key) })
	remember(metadata, key, docs, METADATA_LIMIT)
	if (cached) {
		await nextTask()
		if (metadataKey(doctype) !== key) return getMeta(doctype)
	}
	return structuredClone(await docs)
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

export async function getPrintOptions(doctype, name) {
	const payload = await request(`/api/method/essdee_yrp.api.print.get_print_options${queryString({ doctype, name })}`, { method: "GET" })
	return payload.message
}

export function getRawPrintCommands(doctype, name, format) {
	return callMethod("frappe.www.printview.get_rendered_raw_commands", { doc: doctype, name, print_format: format })
}

/** Created/modified stamps plus one page of parsed Version history, newest first. */
export async function getDocumentActivity(doctype, name, { start = 0, pageLength = 10 } = {}) {
	const args = { doctype, name, start, page_length: pageLength }
	const payload = await request(`/api/method/essdee_yrp.api.document_activity.get_document_activity${queryString(args)}`, { method: "GET" })
	return payload.message
}

export async function getDocPermissions(doctype, name) {
	const payload = await request(`/api/method/frappe.client.get_doc_permissions${queryString({ doctype, docname: name })}`, { method: "GET" })
	return payload.message.permissions
}

export function deleteDoc(doctype, name) {
	return callMethod("frappe.client.delete", { doctype, name })
}

export function submitDoc(doctype, name, modified = "") {
	return callMethod("essdee_yrp.api.lifecycle.submit_document", { doctype, name, modified: modified || undefined })
}

export function cancelDoc(doctype, name, modified = "") {
	return callMethod("essdee_yrp.api.lifecycle.cancel_document", { doctype, name, modified: modified || undefined })
}

export function getDuplicateValues(doctype, name) {
	return callMethod("essdee_yrp.api.duplicate.get_duplicate_values", { doctype, name })
}

export async function getList(
	doctype,
	{ fields = ["name"], filters = [], orderBy = "modified desc", start = 0, pageLength = 20, groupBy } = {},
) {
	const params = {
		fields,
		filters,
		group_by: groupBy,
		order_by: orderBy,
		limit_start: start,
		limit_page_length: pageLength,
	}
	const url = `/api/resource/${encodeURIComponent(doctype)}${queryString(params)}`
	if (url.length > 6000) return await callRead("frappe.client.get_list", { doctype, ...params }) || []
	const payload = await request(url, { method: "GET" })
	return payload.data || []
}

export function getItemFilterValues(items) {
	return callRead("essdee_yrp.api.item_filter.get_item_filter_values", { items })
}

export async function getCount(doctype, filters = [], { distinct = false } = {}) {
	const value = await callRead("frappe.desk.reportview.get_count", distinct ? { doctype, filters, distinct } : { doctype, filters })
	return Number(value || 0)
}

/** `get_count` per filter set in one request per COUNT_BATCH_LIMIT sets; resolves in the same order. */
export async function getCounts(doctype, filterSets = [], { distinct = false } = {}) {
	const batches = []
	for (let start = 0; start < filterSets.length; start += COUNT_BATCH_LIMIT) batches.push(filterSets.slice(start, start + COUNT_BATCH_LIMIT))
	const answers = await Promise.all(batches.map(async (batch) => {
		const args = { doctype, filter_sets: batch }
		const values = await callRead("essdee_yrp.api.list_counts.get_counts", distinct ? { ...args, distinct } : args)
		if (!Array.isArray(values) || values.length !== batch.length) throw new Error("The server returned an incomplete set of counts.")
		return values
	}))
	return answers.flat().map((value) => Number(value || 0))
}

export async function searchLink(
	doctype,
	text = "",
	filters = {},
	pageLength = 20,
	matchVisibleOnly = false,
	{ allowVariants = false } = {},
) {
	if (!doctype) return []
	const rows = await linkRead("essdee_yrp.api.link_search.link_search", {
		doctype,
		txt: text,
		filters,
		page_length: pageLength,
		match_visible_only: matchVisibleOnly,
		...(allowVariants ? { allow_variants: 1 } : {}),
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
	const rows = await linkRead("essdee_yrp.api.link_search.linked_document_search", {
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
	const settings = await callRead(`${USER_LISTVIEW_METHOD}.get_user_listview`, {
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
	// Generic methods may write, like callMethod.
	invalidatePendingReads()
	let response
	try {
		response = await fetch(`/api/method/${method}`, {
			method: "POST",
			credentials: "include",
			headers: { "Content-Type": "application/json", "X-Frappe-CSRF-Token": csrfToken() },
			body: JSON.stringify(args),
		})
	} finally {
		invalidatePendingReads()
	}
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
