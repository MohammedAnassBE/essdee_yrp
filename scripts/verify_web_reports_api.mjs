#!/usr/bin/env node

import { readFileSync } from "node:fs"

const SITE = process.env.E2E_SITE || "http://erp-migration-test.site:8001"
const PASSWORD = process.env.E2E_PASSWORD
const USER_A = process.env.E2E_USER_A || "e2e.report.a@example.test"
const USER_B = process.env.E2E_USER_B || "e2e.report.b@example.test"
const ALLOWED_ITEM = process.env.E2E_ALLOWED_ITEM
const DENIED_ITEM = process.env.E2E_DENIED_ITEM
const METHOD_ROOT = "yrp.api.web_reports"
const results = []

if (!PASSWORD || !ALLOWED_ITEM || !DENIED_ITEM) {
	throw new Error("E2E_PASSWORD, E2E_ALLOWED_ITEM, and E2E_DENIED_ITEM are required")
}

const [administratorUser, administratorPassword] = administratorCredentials()
const [userA, userB, administrator] = await Promise.all([
	login(USER_A, PASSWORD),
	login(USER_B, PASSWORD),
	login(administratorUser, administratorPassword),
])

await check("run_web_report succeeds", async () => {
	const response = await method(userB, "run_web_report", {
		report_key: "stock-balance",
		filters: stockFilters(ALLOWED_ITEM),
	})
	assert(response.status === 200, response)
	assert(response.data.mode === "sync", response.data)
})

await expectDenied("run_web_report rejects unknown report", userA, "run_web_report", {
	report_key: "unknown-report",
	filters: {},
})
await expectDenied("run_web_report rejects unknown filter", userA, "run_web_report", {
	report_key: "finishing-plan",
	filters: { forged_filter: "value" },
})
await expectDenied("run_web_report rejects unreadable Link value", userA, "run_web_report", {
	report_key: "stock-balance",
	filters: stockFilters(DENIED_ITEM),
})

const jobsBefore = await reportJobCount(administrator, USER_A)
await check("client background argument cannot force a five-day DPR", async () => {
	const response = await method(userA, "run_web_report", {
		report_key: "cutting-dpr",
		filters: summaryFilters(-4, 0),
		mode: "background",
	})
	assert(response.status === 200, response)
	assert(response.data.mode === "sync", response.data)
	assert(!response.data.job, response.data)
	assert(await reportJobCount(administrator, USER_A) === jobsBefore, "a report job was created")
})

let jobName
await check("run_web_report creates an 11-day background job", async () => {
	const response = await method(userA, "run_web_report", {
		report_key: "cutting-dpr",
		filters: summaryFilters(-11, 0),
		refresh: 1,
	})
	assert(response.status === 200, response)
	assert(response.data.mode === "background", response.data)
	jobName = response.data.job?.name
	assert(jobName, response.data)
})

await check("get_report_job succeeds for owner", async () => {
	const completed = await waitForJob(userA, jobName)
	assert(completed.job.status === "Completed", completed)
	assert(Object.hasOwn(completed, "payload"), completed)
})

await check("download_report_job succeeds for owner", async () => {
	const response = await rawMethod(userA, "download_report_job", {
		report_key: "cutting-dpr",
		job_name: jobName,
	})
	assert(response.status === 200, await response.text())
})
await expectStatus("user B cannot read A job", 403, () => method(userB, "get_report_job", {
	report_key: "cutting-dpr",
	job_name: jobName,
	include_result: 1,
}))
await expectStatus("user B cannot download A job", 403, () => rawMethod(userB, "download_report_job", {
	report_key: "cutting-dpr",
	job_name: jobName,
}))

await expectStatus("owner gets not-found for a deleted job", 404, () => method(userA, "get_report_job", {
	report_key: "cutting-dpr",
	job_name: "missing-job",
	include_result: 1,
}))

for (const [label, session] of [["A", userA], ["B", userB]]) {
	await expectStatus(`user ${label} cannot GET A job DocType`, 403, () => request(
		session,
		`/api/resource/YRP%20Report%20Job/${encodeURIComponent(jobName)}`,
	))
}

let fileUrl
await check("administrator can resolve the private attachment", async () => {
	assert(jobName, "background job was not created")
	fileUrl = await attachmentUrl(administrator, jobName)
})
for (const [label, session] of [["A", userA], ["B", userB]]) {
	await check(`user ${label} cannot fetch private attachment`, async () => {
		assert(fileUrl, "attachment URL was not resolved")
		const response = await request(session, fileUrl)
		assert(response.status === 403, `expected 403, got ${response.status}`)
	})
}

await check("get_report_layout succeeds", async () => {
	const response = await method(userA, "get_report_layout", { report_key: "stock-balance" })
	assert(response.status === 200, response)
	assert(response.data.link_sources?.item?.doctype === "Item", response.data)
})

const savedLayout = [
	baseColumn("item", "auto", 140),
	{
		column_key: "linked:item:item_group",
		kind: "linked",
		source_column: "item",
		target_field: "item_group",
		visible: 1,
		align: "left",
		width: 180,
	},
]
await check("save_report_layout succeeds", async () => {
	const response = await method(userA, "save_report_layout", {
		report_key: "stock-balance",
		columns: savedLayout,
	})
	assert(response.status === 200, response)
	assert(response.data.layout?.length === 2, response.data)
})
await expectDenied("save_report_layout rejects duplicate keys", userA, "save_report_layout", {
	report_key: "stock-balance",
	columns: [baseColumn("item"), baseColumn("item")],
})
await expectDenied("save_report_layout rejects width below bound", userA, "save_report_layout", {
	report_key: "stock-balance",
	columns: [baseColumn("item", "auto", 59)],
})
await expectDenied("save_report_layout rejects width above bound", userA, "save_report_layout", {
	report_key: "stock-balance",
	columns: [baseColumn("item", "auto", 601)],
})
await expectDenied("save_report_layout rejects invalid alignment", userA, "save_report_layout", {
	report_key: "stock-balance",
	columns: [baseColumn("item", "diagonal", 120)],
})
for (const targetField of ["name; drop", "not_a_field"]) {
	await expectDenied(`save_report_layout rejects target ${targetField}`, userA, "save_report_layout", {
		report_key: "stock-balance",
		columns: [{ ...savedLayout[1], column_key: `linked:item:${targetField}`, target_field: targetField }],
	})
}
await expectDenied("save_report_layout rejects Password target", userA, "save_report_layout", {
	report_key: "purchase-order-itemwise",
	columns: [{
		column_key: "linked:modified_by:new_password",
		kind: "linked",
		source_column: "modified_by",
		target_field: "new_password",
		visible: 1,
		align: "auto",
		width: 120,
	}],
})

await check("reset_report_layout succeeds", async () => {
	const response = await method(userA, "reset_report_layout", { report_key: "stock-balance" })
	assert(response.status === 200, response)
	assert(response.data.layout === null, response.data)
})

await check("get_link_field_options succeeds", async () => {
	const response = await method(userA, "get_link_field_options", {
		report_key: "stock-balance",
		source_column: "item",
	})
	assert(response.status === 200, response)
	assert(response.data.some((field) => field.fieldname === "item_group"), response.data)
})
await expectDenied("get_link_field_options rejects forged item_name source", userA, "get_link_field_options", {
	report_key: "stock-balance",
	source_column: "item_name",
})

await check("get_linked_values succeeds", async () => {
	const response = await method(userB, "get_linked_values", {
		report_key: "stock-balance",
		requests: [{
			source_column: "item",
			fields: ["item_group"],
			names: [ALLOWED_ITEM, DENIED_ITEM],
		}],
	})
	assert(response.status === 200, response)
	assert(response.data.item?.[ALLOWED_ITEM], response.data)
	assert(response.data.item?.[DENIED_ITEM], response.data)
})
await check("get_linked_values omits unreadable names", async () => {
	const response = await method(userA, "get_linked_values", {
		report_key: "stock-balance",
		requests: [{
			source_column: "item",
			fields: ["item_group"],
			names: [DENIED_ITEM],
		}],
	})
	assert(response.status === 200, response)
	assert(!response.data.item?.[DENIED_ITEM], response.data)
})
for (const targetField of ["name; drop", "not_a_field"]) {
	await expectDenied(`get_linked_values rejects target ${targetField}`, userA, "get_linked_values", {
		report_key: "stock-balance",
		requests: [{ source_column: "item", fields: [targetField], names: [ALLOWED_ITEM] }],
	})
}
await expectDenied("get_linked_values rejects Password target", userA, "get_linked_values", {
	report_key: "purchase-order-itemwise",
	requests: [{ source_column: "modified_by", fields: ["new_password"], names: [USER_A] }],
})
await expectDenied("get_linked_values rejects more than 5000 names", userA, "get_linked_values", {
	report_key: "stock-balance",
	requests: [{
		source_column: "item",
		fields: ["item_group"],
		names: Array.from({ length: 5_001 }, (_value, index) => `ITEM-${index}`),
	}],
})

await expectStatus("user A cannot list layout DocType", 403, () => request(
	userA,
	"/api/resource/YRP%20User%20Report%20Layout",
))

const guestCases = [
	["run_web_report", { report_key: "finishing-plan", filters: {} }],
	["get_report_job", { report_key: "cutting-dpr", job_name: jobName }],
	["download_report_job", { report_key: "cutting-dpr", job_name: jobName }],
	["get_report_layout", { report_key: "stock-balance" }],
	["save_report_layout", { report_key: "stock-balance", columns: [] }],
	["reset_report_layout", { report_key: "stock-balance" }],
	["get_link_field_options", { report_key: "stock-balance", source_column: "item" }],
	["get_linked_values", { report_key: "stock-balance", requests: [] }],
]
for (const [endpoint, argumentsObject] of guestCases) {
	await expectStatus(`guest denied ${endpoint}`, 403, () => rawMethod(null, endpoint, argumentsObject))
}

printResults()
if (results.some((result) => !result.passed)) process.exitCode = 1

async function login(user, password) {
	const response = await fetch(`${SITE}/api/method/login`, {
		method: "POST",
		headers: { "Content-Type": "application/x-www-form-urlencoded" },
		body: new URLSearchParams({ usr: user, pwd: password }),
		redirect: "manual",
	})
	assert(response.status === 200, `login failed for ${user}: ${response.status} ${await response.text()}`)
	const setCookies = response.headers.getSetCookie?.() || [response.headers.get("set-cookie") || ""]
	const session = { user, cookie: setCookies.map((value) => value.split(";", 1)[0]).filter(Boolean).join("; ") }
	const webResponse = await request(session, "/web")
	const webHtml = await webResponse.text()
	const match = webHtml.match(/window\.csrf_token\s*=\s*["']([^"']+)["']/)
	assert(webResponse.status === 200 && match, `unable to load CSRF token for ${user}`)
	session.csrfToken = match[1]
	return session
}

async function method(session, endpoint, argumentsObject) {
	const response = await rawMethod(session, endpoint, argumentsObject)
	const text = await response.text()
	let body
	try {
		body = JSON.parse(text)
	} catch {
		body = { raw: text }
	}
	return { status: response.status, data: body.message, body }
}

function rawMethod(session, endpoint, argumentsObject) {
	if (!session) {
		const query = new URLSearchParams()
		for (const [key, value] of Object.entries(argumentsObject || {})) {
			query.set(key, typeof value === "object" ? JSON.stringify(value) : String(value))
		}
		return request(null, `/api/method/${METHOD_ROOT}.${endpoint}?${query}`)
	}
	return request(session, `/api/method/${METHOD_ROOT}.${endpoint}`, {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify(argumentsObject || {}),
	})
}

function request(session, path, options = {}) {
	const headers = { ...(options.headers || {}) }
	if (session?.cookie) headers.Cookie = session.cookie
	if (session?.csrfToken) headers["X-Frappe-CSRF-Token"] = session.csrfToken
	return fetch(new URL(path, SITE), {
		...options,
		headers,
		redirect: "manual",
	})
}

async function waitForJob(session, name) {
	const deadline = Date.now() + 120_000
	while (Date.now() < deadline) {
		const response = await method(session, "get_report_job", {
			report_key: "cutting-dpr",
			job_name: name,
			include_result: 1,
		})
		assert(response.status === 200, response)
		if (["Completed", "Error", "Expired"].includes(response.data.job?.status)) return response.data
		await new Promise((resolve) => setTimeout(resolve, 1_000))
	}
	throw new Error(`job ${name} did not finish within 120 seconds`)
}

async function attachmentUrl(session, name) {
	const fields = JSON.stringify(["file_url"])
	const filters = JSON.stringify([
		["attached_to_doctype", "=", "YRP Report Job"],
		["attached_to_name", "=", name],
	])
	const response = await request(session, `/api/resource/File?fields=${encodeURIComponent(fields)}&filters=${encodeURIComponent(filters)}`)
	const body = await response.json()
	assert(response.status === 200 && body.data?.[0]?.file_url, body)
	return body.data[0].file_url
}

async function reportJobCount(session, owner) {
	const filters = JSON.stringify([["owner", "=", owner]])
	const response = await request(session, `/api/resource/YRP%20Report%20Job?fields=${encodeURIComponent('["name"]')}&filters=${encodeURIComponent(filters)}&limit_page_length=0`)
	const body = await response.json()
	assert(response.status === 200, body)
	return body.data.length
}

async function expectDenied(label, session, endpoint, argumentsObject) {
	await check(label, async () => {
		const response = await method(session, endpoint, argumentsObject)
		assert([403, 404, 417].includes(response.status), response)
	})
}

async function expectStatus(label, expectedStatus, requestFunction) {
	await check(label, async () => {
		const response = await requestFunction()
		assert(response.status === expectedStatus, `expected ${expectedStatus}, got ${response.status}`)
	})
}

async function check(label, testFunction) {
	try {
		await testFunction()
		results.push({ label, passed: true, detail: "" })
	} catch (reason) {
		results.push({ label, passed: false, detail: describe(reason) })
	}
}

function assert(condition, detail) {
	if (!condition) throw new Error(describe(detail))
}

function describe(value) {
	if (value instanceof Error) return value.message
	return typeof value === "string" ? value : JSON.stringify(value)
}

function printResults() {
	console.table(results.map(({ label, passed, detail }) => ({
		result: passed ? "PASS" : "FAIL",
		check: label,
		detail: detail.slice(0, 240),
	})))
	const passed = results.filter((result) => result.passed).length
	console.log(`API_SUMMARY passed=${passed} failed=${results.length - passed} total=${results.length}`)
}

function stockFilters(item) {
	const today = dateOffset(0)
	return { from_date: today, to_date: today, item }
}

function summaryFilters(fromOffset, toOffset) {
	return {
		mode: "summary",
		from_date: dateOffset(fromOffset),
		to_date: dateOffset(toOffset),
		items: [],
		lots: [],
		location: "",
	}
}

function dateOffset(offset) {
	const date = new Date()
	date.setUTCDate(date.getUTCDate() + offset)
	return date.toISOString().slice(0, 10)
}

function baseColumn(fieldname, align = "auto", width = 120) {
	return {
		column_key: `base:${fieldname}`,
		kind: "base",
		source_column: "",
		target_field: "",
		visible: 1,
		align,
		width,
	}
}

function administratorCredentials() {
	if (process.env.E2E_ADMIN_USER && process.env.E2E_ADMIN_PASSWORD) {
		return [process.env.E2E_ADMIN_USER, process.env.E2E_ADMIN_PASSWORD]
	}
	const credentialsFile = process.env.E2E_CREDS_FILE || "/home/anas/.frappe-debug-creds-mrp3"
	const [user, password] = readFileSync(credentialsFile, "utf8").trim().split("\n")
	return [user.trim(), password.trim()]
}
