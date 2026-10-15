#!/usr/bin/env node

import { execFileSync } from "node:child_process"
import { randomBytes } from "node:crypto"
import { readFileSync } from "node:fs"
import { createRequire } from "node:module"
import { pathToFileURL } from "node:url"

const require = createRequire("/home/anas/.claude/playwright/package.json")
const { chromium } = require("playwright")

const SITE = process.env.ESSDEE_TEST_SITE || "http://erp-migration-test.site:8001"
const SITE_NAME = process.env.ESSDEE_TEST_SITE_NAME || "erp-migration-test.site"
const SITES_DIRECTORY = "/home/anas/pilot/benches/frappe-16/sites"
const PYTHON = "/home/anas/pilot/benches/frappe-16/env/bin/python"
const FIXTURE_SCRIPT = (
	"/home/anas/pilot/benches/frappe-16/apps/essdee_yrp/scripts/accounts_hr_fixtures.py"
)
const PASSWORD = process.env.E2E_PASSWORD || randomBytes(18).toString("base64url")
const NETWORK_CHANGED_RESOURCE_ERROR = "Failed to load resource: net::ERR_NETWORK_CHANGED"
const LINK_SEARCH_METHOD = "essdee_yrp.api.link_search.link_search"
const PURCHASE_INVOICE_EDITOR_METHOD = "essdee_yrp.accounts.purchase_invoice_editor.get_purchase_invoice_editor"
const PURCHASE_INVOICE_WORKSPACE_METHOD = (
	"essdee_yrp.accounts.purchase_invoice_workspace.get_purchase_invoice_workspace"
)
const EXPENSE_HEAD_METHOD = "essdee_yrp.erp_purchase_invoice.fetch_items_expense_head"

const KNOWN_MUTATING_API_METHODS = new Set([
	"essdee_yrp.accounts.purchase_invoice_editor.save_purchase_invoice",
	"essdee_yrp.accounts.purchase_invoice_editor.execute_purchase_invoice_command",
	"essdee_yrp.erp_purchase_invoice.submit_erp_invoice",
	"essdee_yrp.work_order_close.close_work_order",
	"essdee_yrp.hr.web_workspace.save_bill_tracking",
	"essdee_yrp.hr.web_workspace.execute_bill_tracking_command",
	"essdee_yrp.overrides.bill_tracking.assign_vendor_bill",
	"essdee_yrp.overrides.bill_tracking.bulk_assign_bills",
	"essdee_yrp.overrides.bill_tracking.make_bill_received_acknowledgement",
	"essdee_yrp.overrides.bill_tracking.request_bill_cancellation",
	"essdee_yrp.overrides.bill_tracking.approve_bill_cancellation",
	"essdee_yrp.overrides.bill_tracking.cancel_vendor_bill",
	"essdee_yrp.overrides.purchase_invoice_api.approve_invoice",
	"yrp.yrp.doctype.yrp_purchase_invoice.yrp_purchase_invoice.approve_invoice",
	"yrp.yrp.doctype.yrp_bill_tracking.yrp_bill_tracking.assign_vendor_bill",
	"yrp.yrp.doctype.yrp_bill_tracking.yrp_bill_tracking.bulk_assign_bills",
	"yrp.yrp.doctype.yrp_bill_tracking.yrp_bill_tracking.make_bill_received_acknowledgement",
	"yrp.yrp.doctype.yrp_bill_tracking.yrp_bill_tracking.cancel_vendor_bill",
	"frappe.desk.form.save.savedocs",
	"frappe.client.set_value",
	"frappe.client.insert",
	"frappe.client.insert_many",
	"frappe.client.save",
	"frappe.client.rename_doc",
	"frappe.client.submit",
	"frappe.client.cancel",
	"frappe.client.delete",
	"frappe.client.bulk_update",
	"frappe.client.attach_file",
])
const READ_ONLY_API_METHODS = new Set([
	"essdee_yrp.accounts.web_capabilities.get_capabilities",
	PURCHASE_INVOICE_EDITOR_METHOD,
	PURCHASE_INVOICE_WORKSPACE_METHOD,
	EXPENSE_HEAD_METHOD,
	"yrp.yrp.doctype.yrp_purchase_invoice.yrp_purchase_invoice.get_eligible_grns",
	"essdee_yrp.hr.web_workspace.get_capabilities",
	"essdee_yrp.hr.web_workspace.get_bill_tracking_workspace",
	"essdee_yrp.fabric_store.web_workspace.get_goods_received_note_workspace",
	"frappe.desk.form.load.getdoctype",
	"frappe.desk.reportview.get_count",
	"frappe.desk.doctype.event.event.get_events",
	"frappe.desk.doctype.notification_log.notification_log.get_notification_logs",
	"essdee_yrp.api.list_columns.get_user_listview",
])
const WORK_ORDER_COMMAND_METHOD = "essdee_yrp.fabric_store.web_workspace.execute_work_order_command"
const SUITES = [
	"launcher",
	"pi-list-view",
	"pi-dialogs",
	"pi-editor",
	"reports",
	"bill-tracking-lifecycle",
	"read-only",
]

function assert(condition, message) {
	if (!condition) throw new Error(message)
}

function fixtureCommand(functionName, kwargs = null) {
	const args = [
		FIXTURE_SCRIPT, "--site", SITE_NAME, functionName,
	]
	if (kwargs) args.push("--kwargs", JSON.stringify(kwargs))
	try {
		return execFileSync(PYTHON, args, {
			cwd: SITES_DIRECTORY,
			encoding: "utf8",
			env: { ...process.env, E2E_PASSWORD: PASSWORD },
			stdio: ["ignore", "pipe", "pipe"],
		})
	} catch (error) {
		const details = [error?.stdout, error?.stderr]
			.filter(Boolean)
			.map(sanitizeSensitiveText)
			.join("\n")
			.trim()
		const reason = sanitizeSensitiveText(error?.message || error)
		throw new Error(`Fixture ${functionName} failed: ${details || reason}`)
	}
}

function fixtureSetup() {
	const output = fixtureCommand("setup")
	const payload = output.trim().split("\n").reverse().find((line) => line.trim().startsWith("{"))
	assert(payload, `Fixture setup did not return its names: ${output}`)
	return JSON.parse(payload)
}

function fixtureTeardown() {
	fixtureCommand("teardown")
}

const SENSITIVE_VALUES = new Set([PASSWORD])

function sanitizeSensitiveText(value) {
	let text = String(value ?? "")
	for (const secret of SENSITIVE_VALUES) if (secret) text = text.split(secret).join("[REDACTED]")
	return text
}

function isNetworkChangedConsoleMessage(message) {
	return message.type() === "error" && message.text().trim() === NETWORK_CHANGED_RESOURCE_ERROR
}

async function navigate(page, url) {
	let sawNetworkChange = false
	const observeNetworkChange = (message) => {
		if (isNetworkChangedConsoleMessage(message)) sawNetworkChange = true
	}
	page.on("console", observeNetworkChange)
	try {
		return await page.goto(url, { waitUntil: "domcontentloaded" })
	} catch (error) {
		const message = String(error?.message || error)
		const wasNetworkChange = message.includes("net::ERR_NETWORK_CHANGED")
			|| (sawNetworkChange && message.includes("net::ERR_ABORTED"))
		if (!wasNetworkChange) throw error
		return page.goto(url, { waitUntil: "domcontentloaded" })
	} finally {
		page.off("console", observeNetworkChange)
	}
}

async function login(page) {
	const [username, password] = readFileSync("/home/anas/.frappe-debug-creds-mrp3", "utf8").trim().split("\n")
	SENSITIVE_VALUES.add(password.trim())
	await navigate(page, `${SITE}/login`)
	await page.fill("#login_email", username.trim())
	await page.fill("#login_password", password.trim())
	await Promise.all([
		page.waitForNavigation({ waitUntil: "domcontentloaded", timeout: 20_000 }).catch(() => {}),
		page.click(".btn-login, button[type=submit]"),
	])
}

async function loginAs(page, username) {
	await navigate(page, `${SITE}/login`)
	await page.fill("#login_email", username)
	await page.fill("#login_password", PASSWORD)
	await Promise.all([
		page.waitForNavigation({ waitUntil: "domcontentloaded", timeout: 20_000 }).catch(() => {}),
		page.click(".btn-login, button[type=submit]"),
	])
}

async function withPage(browser, signIn, callback) {
	const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
	const page = await context.newPage()
	try {
		await signIn(page)
		return await callback(page, context)
	} finally {
		await context.close()
	}
}

async function waitForApp(page, selector) {
	try {
		await page.locator(selector).first().waitFor({ state: "visible", timeout: 30_000 })
	} catch (error) {
		await navigate(page, page.url())
		try {
			await page.locator(selector).first().waitFor({ state: "visible", timeout: 30_000 })
		} catch {
			const body = (await page.locator("body").innerText().catch(() => "")).slice(0, 1200)
			throw new Error(`${error.message}\nURL: ${page.url()}\nPage: ${body}`)
		}
	}
}

async function waitForIdle(page) {
	await page.waitForLoadState("domcontentloaded")
	await page.waitForTimeout(250)
}

function apiMethod(request) {
	const path = new URL(request.url()).pathname
	const marker = ["/api/v1/method/", "/api/method/"].find((value) => path.includes(value))
	return marker ? decodeURIComponent(path.split(marker)[1]).replace(/\/+$/, "") : ""
}

function requestArgs(request) {
	const query = Object.fromEntries(new URL(request.url()).searchParams)
	if (!request.postData()) return query
	try {
		const body = JSON.parse(request.postData())
		return body && typeof body === "object" ? { ...query, ...body } : query
	} catch {
		return { ...query, ...Object.fromEntries(new URLSearchParams(request.postData())) }
	}
}

function isReadOnlyMethod(method, args) {
	if (READ_ONLY_API_METHODS.has(method)) return true
	return method === WORK_ORDER_COMMAND_METHOD && args.command === "get_close_context"
}

function mutationAttempt(request) {
	const httpMethod = request.method().toUpperCase()
	const path = new URL(request.url()).pathname
	if (/^\/api(?:\/v1)?\/resource(?:\/|$)/.test(path)) {
		const runsMethod = new URL(request.url()).searchParams.has("run_method")
		return httpMethod === "GET" && !runsMethod ? null : { http_method: httpMethod, path }
	}
	if (/^\/api\//.test(path) && !/^\/api(?:\/v1)?\/method\//.test(path)) {
		return { http_method: httpMethod, path }
	}
	const method = apiMethod(request)
	const args = requestArgs(request)
	const isWorkOrderMutation = method === WORK_ORDER_COMMAND_METHOD && args.command !== "get_close_context"
	if (KNOWN_MUTATING_API_METHODS.has(method) || isWorkOrderMutation) {
		return { http_method: httpMethod, path, method, args }
	}
	if (method && isReadOnlyMethod(method, args)) return null
	if (method || httpMethod !== "GET") {
		return { http_method: httpMethod, path, method, args }
	}
	return null
}

function assertMutationGuardPolicy() {
	const request = (httpMethod, path, body = null) => ({
		method: () => httpMethod,
		url: () => `${SITE}${path}`,
		postData: () => body === null ? null : JSON.stringify(body),
	})
	assert(mutationAttempt(request("POST", "/api/method/frappe.desk.form.save.savedocs", {})),
		"The real-record guard allowed savedocs")
	assert(mutationAttempt(request("GET", "/api/method/essdee_yrp.work_order_close.close_work_order")),
		"The real-record guard allowed a mutating GET method")
	assert(mutationAttempt(request("GET", "/api/resource/YRP%20Purchase%20Invoice/REAL?run_method=cancel")),
		"The real-record guard allowed a document-method GET")
	assert(mutationAttempt(request("GET", "/api/v2/method/unverified.reader")),
		"The real-record guard allowed an unrecognised API route")
	assert(mutationAttempt(request("POST", "/api/v1/method/unverified.writer", {})),
		"The real-record guard allowed an unverified v1 method")
	assert(!mutationAttempt(request("POST", `/api/v1/method/${PURCHASE_INVOICE_WORKSPACE_METHOD}`, {})),
		"The real-record guard blocked a verified read method")
	assert(!mutationAttempt(request("POST", `/api/method/${EXPENSE_HEAD_METHOD}`, { items: [] })),
		"The real-record guard blocked the expense-head read")
	assert(!mutationAttempt(request("POST", `/api/method/${WORK_ORDER_COMMAND_METHOD}`, {
		command: "get_close_context",
	})), "The real-record guard blocked the Work Order close-context read")
	assert(mutationAttempt(request("POST", `/api/method/${WORK_ORDER_COMMAND_METHOD}`, {
		command: "close",
	})), "The real-record guard allowed a Work Order close command")
}

async function installRealRecordMutationGuard(page, suiteLabel) {
	const attempts = []
	const pattern = "**/api/**"
	const handler = async (route) => {
		const attempt = mutationAttempt(route.request())
		if (!attempt) return route.continue()
		attempts.push(attempt)
		return route.abort("blockedbyclient")
	}
	await page.route(pattern, handler)
	return async () => {
		await page.unroute(pattern, handler)
		assert(!attempts.length, `${suiteLabel} attempted real-record mutations: ${JSON.stringify(attempts)}`)
	}
}

function reply(route, message) {
	return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message }) })
}

function replyError(route, message, exceptionType = "ValidationError", status = 417) {
	return route.fulfill({
		status,
		contentType: "application/json",
		body: JSON.stringify({
			exc_type: exceptionType,
			exc: `frappe.exceptions.${exceptionType}: ${message}`,
			_server_messages: JSON.stringify([JSON.stringify({ message })]),
		}),
	})
}

async function callMethod(page, method, args = {}) {
	const result = await page.evaluate(async ({ methodName, values }) => {
		const response = await fetch(`/api/method/${methodName}`, {
			method: "POST",
			credentials: "include",
			headers: {
				Accept: "application/json",
				"Content-Type": "application/json",
				"X-Frappe-CSRF-Token": window.csrf_token || window.frappe?.csrf_token || "",
			},
			body: JSON.stringify(values),
		})
		return { status: response.status, payload: await response.json().catch(() => ({})) }
	}, { methodName: method, values: args })
	assert(result.status >= 200 && result.status < 300 && !result.payload.exc,
		`${method} failed: HTTP ${result.status} ${JSON.stringify(result.payload)}`)
	return result.payload.message
}

async function resourceList(page, doctype, filters, fields, limit = 20, start = 0) {
	const result = await page.evaluate(async ({ documentType, rowFilters, rowFields, pageLength, offset }) => {
		const query = new URLSearchParams({
			filters: JSON.stringify(rowFilters),
			fields: JSON.stringify(rowFields),
			limit_page_length: String(pageLength),
			limit_start: String(offset),
			order_by: "modified desc",
		})
		const response = await fetch(`/api/resource/${encodeURIComponent(documentType)}?${query}`, {
			credentials: "include",
			headers: { Accept: "application/json" },
		})
		return { status: response.status, payload: await response.json().catch(() => ({})) }
	}, { documentType: doctype, rowFilters: filters, rowFields: fields, pageLength: limit, offset: start })
	assert(result.status === 200, `Could not list ${doctype}: HTTP ${result.status} ${JSON.stringify(result.payload)}`)
	return result.payload.data || []
}

async function allResourceRows(page, doctype, filters, fields) {
	const rows = []
	const pageLength = 100
	while (true) {
		const pageRows = await resourceList(page, doctype, filters, fields, pageLength, rows.length)
		rows.push(...pageRows)
		if (pageRows.length < pageLength) return rows
	}
}

async function openAction(page, label) {
	const strip = page.locator(".document-action-strip:visible")
	const direct = strip.getByRole("button", { name: label, exact: true })
	const more = strip.getByRole("button", { name: "More", exact: true })
	await direct.or(more).first().waitFor({ state: "visible", timeout: 30_000 })
	if (await direct.isVisible()) {
		await direct.click()
		return
	}
	await more.click()
	const menu = page.locator(".document-action-menu:visible")
	await menu.waitFor({ state: "visible", timeout: 15_000 })
	const item = menu.getByRole("menuitem", { name: label, exact: true })
	try {
		await item.waitFor({ state: "visible", timeout: 15_000 })
	} catch (error) {
		const actions = await strip.getByRole("button").allInnerTexts()
		throw new Error(`Action ${label} is unavailable. Rendered actions: ${JSON.stringify(actions)}`, { cause: error })
	}
	await item.click()
}

async function noHorizontalOverflow(page, label) {
	const geometry = await page.evaluate(() => ({
		viewport: window.innerWidth,
		pageWidth: document.documentElement.scrollWidth,
		bodyWidth: document.body.scrollWidth,
	}))
	assert(geometry.pageWidth <= geometry.viewport + 1 && geometry.bodyWidth <= geometry.viewport + 1,
		`${label} has horizontal overflow: ${JSON.stringify(geometry)}`)
}

function collectBrowserErrors(page) {
	const errors = []
	page.on("console", (message) => {
		if (message.type() === "error" && !isNetworkChangedConsoleMessage(message)) {
			errors.push(`console: ${message.text()}`)
		}
	})
	page.on("pageerror", (error) => errors.push(`page: ${error.message}`))
	return errors
}

async function assertNoRenderedInvalidValues(page, label) {
	const text = await page.locator("body").innerText()
	assert(!/(^|\s)(?:NaN|undefined)(?=\s|$)/.test(text), `${label} renders NaN or undefined`)
}

async function launcherSuite(browser, fixtures) {
	await withPage(browser, login, async (page) => {
		await navigate(page, `${SITE}/web/`)
		await waitForApp(page, ".department-card-link")
		assert(await page.locator(".department-card-link").count() === 13, "The /web launcher does not show 13 departments")
		assert(await page.getByRole("link", { name: /HR/ }).count(), "The /web launcher is missing HR")

		await navigate(page, `${SITE}/web/accounts`)
		await waitForApp(page, ".workspace-launcher__card")
		assert(await page.locator(".workspace-launcher__card").count() === 2, "Accounts does not show two workspaces")

		await navigate(page, `${SITE}/web/hr`)
		await waitForApp(page, ".workspace-launcher__card")
		assert(await page.locator(".workspace-launcher__card").count() === 2, "HR does not show two workspaces")
	})

	await withPage(browser, (page) => loginAs(page, fixtures.plain_user), async (page) => {
		await navigate(page, `${SITE}/web/accounts`)
		await page.getByText("No permitted Accounts workspaces", { exact: true }).waitFor({ timeout: 30_000 })
	})
}

async function purchaseInvoiceListSuite(browser) {
	await withPage(browser, login, async (page) => {
		const verifyNoMutations = await installRealRecordMutationGuard(page, "Purchase Invoice list suite")
		try {
			const browserErrors = collectBrowserErrors(page)
			await navigate(page, `${SITE}/web/accounts/purchase-invoices`)
			await waitForApp(page, ".common-list-view")
			await page.getByRole("region", { name: "Purchase Invoices records" }).waitFor({ state: "visible", timeout: 30_000 })

			const rows = await resourceList(page, "YRP Purchase Invoice", [
				["docstatus", "=", 1], ["against", "=", "YRP Work Order"],
			], ["name"], 1)
			assert(rows.length, "No submitted Work Order Purchase Invoice is available for read-only verification")
			const path = `${SITE}/web/accounts/purchase-invoices/${encodeURIComponent(rows[0].name)}`
			await navigate(page, path)
			await waitForApp(page, ".purchase-invoice-header")

			for (const tab of ["Details", "Items", "GRNs", "Verification"]) {
				await page.getByRole("tab", { name: new RegExp(`^${tab}`) }).click()
				await waitForIdle(page)
				await assertNoRenderedInvalidValues(page, `${tab} tab`)
				for (const width of [1440, 390]) {
					await page.setViewportSize({ width, height: 900 })
					await noHorizontalOverflow(page, `${tab} tab at ${width}px`)
				}
			}
			await page.setViewportSize({ width: 1440, height: 900 })
			await navigate(page, page.url())
			await waitForApp(page, ".purchase-invoice-header")
			assert(page.url().includes(encodeURIComponent(rows[0].name)), "The Purchase Invoice deep link did not survive reload")
			assert(!browserErrors.length, `Purchase Invoice pages logged browser errors: ${browserErrors.join(" | ")}`)
		} finally {
			await verifyNoMutations()
		}
	})
}

async function purchaseInvoiceDialogsSuite(browser) {
	await withPage(browser, login, async (page) => {
		const verifyNoMutations = await installRealRecordMutationGuard(page, "Purchase Invoice dialogs suite")
		try {
			await navigate(page, `${SITE}/web/accounts/purchase-invoices`)
			await waitForApp(page, ".common-list-view")
			const drafts = await allResourceRows(page, "YRP Purchase Invoice", [
				["docstatus", "=", 0], ["against", "=", "YRP Work Order"], ["approved_by", "is", "not set"],
			], ["name"])
			assert(drafts.length, "No unapproved draft Work Order Purchase Invoice is available")
			await navigate(page, `${SITE}/web/accounts/purchase-invoices/${encodeURIComponent(drafts[0].name)}`)
			await waitForApp(page, ".purchase-invoice-header")
			await openAction(page, "Approve Invoice")
			const approveDialog = page.locator(".p-dialog:visible").filter({ hasText: "Approve Invoice" })
			await approveDialog.waitFor({ state: "visible" })
			await approveDialog.getByRole("button", { name: "Cancel", exact: true }).click()

			await verifyWorkOrderClosePanel(page, drafts)

			const submitted = await resourceList(page, "YRP Purchase Invoice", [["docstatus", "=", 1]], ["name"], 1)
			assert(submitted.length, "No submitted Purchase Invoice is available")
			await navigate(page, `${SITE}/web/accounts/purchase-invoices/${encodeURIComponent(submitted[0].name)}`)
			await waitForApp(page, ".purchase-invoice-header")
			await openAction(page, "Cancel")
			const cancelDialog = page.locator(".p-dialog:visible").filter({ hasText: "Cancel Purchase Invoice?" })
			await cancelDialog.waitFor({ state: "visible" })
			await cancelDialog.getByRole("button", { name: "Keep Invoice", exact: true }).click()
		} finally {
			await verifyNoMutations()
		}
	})
}

async function findWorkOrderCloseCandidate(page, drafts) {
	for (const draft of drafts) {
		const workspace = await callMethod(page, PURCHASE_INVOICE_WORKSPACE_METHOD, { name: draft.name })
		const workOrder = (workspace.work_orders || []).find((row) => row.close_mode)
		if (workOrder) return { invoice: draft.name, workOrder }
	}
	return null
}

async function verifyWorkOrderClosePanel(page, drafts) {
	const candidate = await findWorkOrderCloseCandidate(page, drafts)
	if (!candidate) {
		console.log("SKIP pi-dialogs WO-close controls: no real draft Work Order Purchase Invoice has a non-empty close_mode")
		return
	}
	await navigate(page, `${SITE}/web/accounts/purchase-invoices/${encodeURIComponent(candidate.invoice)}`)
	await waitForApp(page, ".purchase-invoice-header")
	await page.getByRole("tab", { name: /^Verification/ }).click()
	const section = page.locator(".verification-work-order").filter({ hasText: candidate.workOrder.name })
	await section.waitFor({ state: "visible", timeout: 30_000 })
	const label = { close: "Close", request_close: "Request Close", approve_close: "Approve Close" }[
		candidate.workOrder.close_mode
	]
	assert(label, `Unknown Work Order close mode ${JSON.stringify(candidate.workOrder.close_mode)}`)
	await section.getByRole("button", { name: label, exact: true }).click()
	const closePanel = page.locator(".work-order-action-panel:visible")
	await closePanel.waitFor({ state: "visible", timeout: 30_000 })
	await closePanel.locator(`[data-mode="${candidate.workOrder.close_mode}"]`).waitFor({ state: "visible" })
	await closePanel.getByText("Close reason *", { exact: true }).waitFor({ state: "visible", timeout: 30_000 })
	await closePanel.getByRole("button", { name: "Cancel", exact: true }).click()
}

function purchaseInvoiceEditorFixture() {
	return {
		values: {
			supplier: "XXXXX",
			against: "Purchase Order",
			posting_date: "2026-10-12",
			due_date: "2026-10-30",
			bill_no: "E2E-AHR-MASKED",
			billing_supplier: "XXXXX",
			bill_date: "2026-10-12",
			eligibility_for_itc: "All Other ITC",
			debit_type: "",
			debit_no: "",
			debit_value: 0,
			remarks: "",
			bill_tracking: "",
		},
		schema: {
			supplier: { label: "Supplier", fieldtype: "Link", options: "Supplier", reqd: true },
			against: { label: "Against", fieldtype: "Select", options: "Purchase Order\nYRP Work Order", reqd: true },
			posting_date: { label: "Posting Date", fieldtype: "Date", reqd: true },
			due_date: { label: "Due Date", fieldtype: "Date" },
			bill_no: { label: "Supplier Invoice No", fieldtype: "Data", reqd: true },
			billing_supplier: { label: "Billing Supplier", fieldtype: "Link", options: "Supplier", reqd: true },
			bill_date: { label: "Supplier Invoice Date", fieldtype: "Date", reqd: true },
			eligibility_for_itc: { label: "Eligibility For ITC", fieldtype: "Select", options: "All Other ITC" },
			debit_type: { label: "Debit Type", fieldtype: "Select" },
			debit_no: { label: "Debit No", fieldtype: "Data" },
			debit_value: { label: "Debit Value", fieldtype: "Currency" },
			remarks: { label: "Remarks", fieldtype: "Small Text" },
		},
		grns: [],
		items: [],
		modified: "2026-10-12 10:00:00.000000",
		docstatus: 0,
		is_rate_only: false,
		erp_sync_enabled: false,
		permissions: { can_submit: false },
	}
}

function fetchedGrnFixture() {
	return {
		additional_field_values: {
			essdee_rate_table_source: "yrp_grn_v1",
			essdee_items: [
				{ group_key: "E2E-AHR-GROUP-1", item: "E2E Item A", lot: "LOT-A", qty: 2, uom: "Nos", source_rate: 48, rate: 50, tax: "GST 5", tax_rate: 5, amount: 100 },
				{ group_key: "E2E-AHR-GROUP-2", item: "E2E Item B", lot: "LOT-B", qty: 3, uom: "Nos", source_rate: 18, rate: 20, tax: "GST 10", tax_rate: 10, amount: 60 },
			],
		},
		tax_rates: { "GST 5": 5, "GST 10": 10 },
	}
}

async function purchaseInvoiceEditorSuite(browser) {
	await withPage(browser, login, async (page) => {
		const saveRequests = []
		await page.route("**/api/method/**", async (route) => {
			const method = apiMethod(route.request())
			if (method.endsWith("get_purchase_invoice_editor")) return reply(route, purchaseInvoiceEditorFixture())
			if (method.endsWith("get_eligible_grns")) {
				return reply(route, [{ name: "E2E-AHR-GRN-001", posting_date: "2026-10-12", against_id: "E2E-AHR-PO-001", supplier_document_no: "GRN-BILL", total_received_quantity: 5, total: 160 }])
			}
			if (method.endsWith("fetch_grn_details")) return reply(route, fetchedGrnFixture())
			if (method.endsWith("save_purchase_invoice")) {
				saveRequests.push(requestArgs(route.request()))
				return replyError(route, "This Purchase Invoice changed after you opened it. Refresh and try again.", "TimestampMismatchError", 409)
			}
			return route.continue()
		})

		await navigate(page, `${SITE}/web/accounts/purchase-invoices/E2E-AHR-MOCK/edit`)
		await waitForApp(page, ".purchase-invoice-editor__body")
		await page.locator(".purchase-invoice-editor__items + .purchase-invoice-editor__notes [data-group='notes']").waitFor()
		assert(await page.locator("#field-remarks-value").count() === 1, "Remarks is rendered more than once")
		const eligibleGrns = page.getByRole("table", { name: "Eligible GRNs" })
		const grnRow = eligibleGrns.getByRole("row", { name: /E2E-AHR-GRN-001/ })
		await grnRow.getByRole("checkbox").check()
		await page.getByRole("button", { name: "Fetch GRN", exact: true }).click()
		await page.getByText("Grouped Items (2)", { exact: true }).waitFor()
		await assertPurchaseInvoiceTotals(page, {
			Total: "160.00",
			Tax: "11.00",
			"Grand Total": "171.00",
			Quantity: "5",
		})

		await page.getByRole("button", { name: "Save", exact: true }).click()
		await page.getByText("This Purchase Invoice changed after you opened it. Refresh and try again.", { exact: true }).waitFor()
		assert(saveRequests.length === 1, `Expected one save request, got ${saveRequests.length}`)
		assert(!Object.hasOwn(saveRequests[0].values, "supplier"), "The masked supplier was posted back to save")
		assert(!Object.hasOwn(saveRequests[0].values, "billing_supplier"), "The masked billing supplier was posted back to save")
		await page.locator(".document-error-dialog:visible").getByRole("button", { name: "OK", exact: true }).click()

		await page.getByRole("button", { name: "Back to Purchase Invoice", exact: true }).click()
		const discardDialog = page.locator(".document-confirmation-shell:visible")
		await discardDialog.getByText("Discard unsaved changes?", { exact: true }).waitFor()
		await discardDialog.getByRole("button", { name: "Discard Changes", exact: true }).click()
		await page.waitForURL(`${SITE}/web/accounts/purchase-invoices/E2E-AHR-MOCK`)
	})
}

async function assertPurchaseInvoiceTotals(page, expected) {
	const actual = Object.fromEntries(await page.locator(".purchase-invoice-editor__metric").evaluateAll((metrics) =>
		metrics.map((metric) => [
			metric.querySelector("span")?.textContent?.trim() || "",
			metric.querySelector("strong")?.textContent?.trim() || "",
		])))
	for (const [label, value] of Object.entries(expected)) {
		assert(actual[label] === value, `${label} is ${JSON.stringify(actual[label])}; expected ${JSON.stringify(value)}`)
	}
}

async function reportsSuite(browser, fixtures) {
	await withPage(browser, login, async (page) => {
		await navigate(page, `${SITE}/web/accounts/reports`)
		await waitForApp(page, ".accounts-reports__tabs")
		const tabs = page.locator(".accounts-reports__desktop [role='tab']")
		assert(await tabs.count() === 5, `Administrator sees ${await tabs.count()} Accounts report tabs instead of 5`)
		for (const label of ["Stock Balance", "Cutting DPR", "Sewing DPR", "Finishing Dispatch", "Ironing DPR"]) {
			await page.getByRole("tab", { name: label, exact: true }).click()
			await waitForIdle(page)
		}
		await page.getByRole("tab", { name: "Sewing DPR", exact: true }).click()
		await page.getByText("Choose a Sewing Unit to generate the DPR.", { exact: true }).waitFor()
		assert(new URL(page.url()).searchParams.get("report") === "sewing-dpr", "Sewing DPR did not retain its report query")

		await navigate(page, `${SITE}/web/hr/reports`)
		await waitForApp(page, ".hr-reports__tabs")
		assert(await page.getByRole("tab", { name: "Attendance", exact: true }).count() === 1, "HR Attendance is not rendered")
	})

	await withPage(browser, (page) => loginAs(page, fixtures.accounts_user), async (page) => {
		const capabilities = await callMethod(page, "essdee_yrp.accounts.web_capabilities.get_capabilities")
		const expectedCount = Object.keys(capabilities.reports || {}).length
		await navigate(page, `${SITE}/web/accounts/reports`)
		await waitForApp(page, ".accounts-reports__tabs")
		const actualCount = await page.locator(".accounts-reports__desktop [role='tab']").count()
		assert(actualCount === expectedCount, `Accounts report tabs ${actualCount} do not match capabilities ${expectedCount}`)
		assert(actualCount === 5, `Accounts User sees ${actualCount} report tabs instead of the granted 5`)
	})
}

function isLinkSearchResponse(response, value) {
	if (response.request().method() !== "POST" || !response.url().includes(LINK_SEARCH_METHOD)) return false
	try {
		const body = requestArgs(response.request())
		const args = typeof body.args === "string" ? JSON.parse(body.args) : (body.args || body)
		return args.txt === value
	} catch {
		return false
	}
}

async function loadLinkOptions(input, value) {
	const page = input.page()
	const responsePromise = page.waitForResponse((response) => isLinkSearchResponse(response, value))
	await input.fill("")
	await input.fill(value)
	const response = await responsePromise
	const payload = await response.json().catch(() => ({}))
	assert(response.ok() && !payload.exc,
		`Link search for ${value} failed: HTTP ${response.status()} ${JSON.stringify(payload)}`)
}

async function selectLink(root, label, value) {
	const input = root.getByLabel(label, { exact: true })
	const page = input.page()
	await input.waitFor({ state: "visible", timeout: 15_000 })
	let lastError
	for (let attempt = 0; attempt < 2; attempt += 1) {
		await loadLinkOptions(input, value)
		const overlay = page.locator(".p-autocomplete-overlay:visible")
		const option = overlay.getByRole("option", { name: value, exact: true }).first()
		try {
			await option.waitFor({ state: "visible", timeout: 10_000 })
			await option.click()
			return
		} catch (error) {
			lastError = error
			if (attempt || await overlay.isVisible()) break
		}
	}
	throw new Error(`Link option ${value} did not remain open after its search response`, { cause: lastError })
}

async function createBill(page, fixtures, suffix) {
	await navigate(page, `${SITE}/web/hr/bill-tracking/new`)
	await waitForApp(page, ".bill-tracking-editor__body")
	await page.getByRole("button", { name: "Back to Bill Tracking", exact: true }).waitFor()
	await selectLink(page, "Supplier", fixtures.supplier)
	await page.locator("#field-bill_no-value").fill(`E2E-AHR-${suffix}`)
	await page.locator("#field-bill_date-value").fill("12-10-2026")
	await page.locator("#field-bill_date-value").press("Tab")
	await page.locator("#field-invoice_value-value").fill("1250")
	await page.locator("#field-received_via-value").click()
	await page.getByRole("option", { name: "HO", exact: true }).click()
	const saveOptions = page.getByRole("button", { name: "Save options", exact: true })
	if (await saveOptions.isDisabled()) {
		const values = await page.evaluate(() => Object.fromEntries([
			"supplier", "bill_no", "bill_date", "invoice_value", "received_date", "received_via",
		].map((fieldname) => [fieldname, document.getElementById(`field-${fieldname}-value`)?.value || ""])))
		throw new Error(`Save & Submit stayed disabled with fields ${JSON.stringify(values)}`)
	}
	await saveOptions.click()
	await page.getByRole("menuitem", { name: "Save & Submit", exact: true }).click()
	await page.waitForURL(/\/web\/hr\/bill-tracking\/[^/?#]+$/, { timeout: 30_000 })
	await waitForApp(page, ".bill-tracking-header")
	const name = decodeURIComponent(new URL(page.url()).pathname.split("/").pop())
	assert(name, "The submitted Bill Tracking name was not returned in the route")
	return name
}

async function expectBillStatus(page, status) {
	await page.locator(".bill-tracking-header .document-status-badge").filter({ hasText: status }).waitFor({ timeout: 30_000 })
}

async function requestCancellation(page, name) {
	await navigate(page, `${SITE}/web/hr/bill-tracking/${encodeURIComponent(name)}`)
	await waitForApp(page, ".bill-tracking-header")
	await openAction(page, "Request for Cancel")
	const dialog = page.locator(".document-confirmation-shell:visible")
	await dialog.getByRole("button", { name: "Request Cancellation", exact: true }).click()
	await expectBillStatus(page, "Pending Approval")
}

async function approveCancellation(page, name) {
	await navigate(page, `${SITE}/web/hr/bill-tracking/${encodeURIComponent(name)}`)
	await waitForApp(page, ".bill-tracking-header")
	await openAction(page, "Approve Cancel Request")
	const dialog = page.locator(".document-confirmation-shell:visible")
	await dialog.getByRole("button", { name: "Approve Request", exact: true }).click()
	await expectBillStatus(page, "Cancel Request Approved")
}

async function cancelBill(page, name) {
	await navigate(page, `${SITE}/web/hr/bill-tracking/${encodeURIComponent(name)}`)
	await waitForApp(page, ".bill-tracking-header")
	await openAction(page, "Cancel")
	const dialog = page.locator(".bill-tracking-cancel-dialog:visible")
	await dialog.getByRole("textbox", { name: /Cancellation reason/ }).fill("E2E-AHR lifecycle verification")
	await dialog.getByRole("button", { name: "Cancel Bill", exact: true }).click()
	await expectBillStatus(page, "Cancelled")
}

async function assignBill(page, fixtures) {
	await openAction(page, "Assign")
	const dialog = page.locator(".bill-tracking-assign-dialog:visible")
	await selectLink(dialog, "Department", fixtures.department)
	await dialog.getByRole("textbox", { name: "Remarks", exact: true }).fill("E2E-AHR assignment")
	await dialog.getByRole("button", { name: "Assign", exact: true }).click()
	await page.getByRole("button", { name: "Bill Received", exact: true }).waitFor({ timeout: 30_000 })
}

async function acknowledgeBill(page) {
	await openAction(page, "Bill Received")
	const dialog = page.locator(".document-confirmation-shell:visible")
	await dialog.getByRole("button", { name: "Bill Received", exact: true }).click()
	await page.getByRole("tab", { name: /^History/ }).click()
	await page.locator(".bill-tracking-history__table tbody tr").filter({ hasText: "Yes" }).waitFor({ timeout: 30_000 })
}

async function bulkAssign(page, fixtures, assignedName, skippedName) {
	await navigate(page, `${SITE}/web/hr/bill-tracking`)
	await waitForApp(page, ".common-list-view")
	for (const name of [assignedName, skippedName]) {
		const row = page.locator(".p-datatable-tbody tr").filter({ hasText: name })
		await row.waitFor({ state: "visible", timeout: 30_000 })
		await row.locator(".p-checkbox").click()
	}
	await page.getByRole("button", { name: "Assign Selected", exact: true }).click()
	const dialog = page.locator(".bill-tracking-assign-dialog:visible")
	await selectLink(dialog, "Department", fixtures.department)
	await dialog.getByRole("button", { name: "Assign Selected", exact: true }).click()
	await page.getByText(/Assigned 1 bill\. Skipped 1:/).waitFor({ timeout: 30_000 })
}

function isMaskedValue(value) {
	return Boolean(value) && String(value).replace(/[Xx*]/g, "") === ""
}

function assertEditorPrefillPayload(editor, bill, billTracking) {
	const values = editor.values || {}
	assert(values.bill_tracking === billTracking,
		`Hidden Bill Tracking prefill is ${JSON.stringify(values.bill_tracking)}; expected ${JSON.stringify(billTracking)}`)
	assert(values.bill_no === bill.bill_no,
		`Editor response bill number is ${JSON.stringify(values.bill_no)}; expected ${JSON.stringify(bill.bill_no)}`)
	assert(String(values.bill_date) === String(bill.bill_date),
		`Editor response bill date is ${JSON.stringify(values.bill_date)}; expected ${JSON.stringify(bill.bill_date)}`)
	if (isMaskedValue(values.supplier)) {
		assert(isMaskedValue(values.billing_supplier), "The masked supplier exposed the billing supplier")
		return { supplier: values.supplier, billingSupplier: values.billing_supplier }
	}
	assert(values.supplier === bill.supplier, "The editor response did not prefill the Bill Tracking supplier")
	assert(values.billing_supplier === bill.supplier, "The editor response did not prefill the billing supplier")
	return { supplier: bill.supplier, billingSupplier: bill.supplier }
}

async function assertPurchaseInvoicePrefill(page, bill, editor, billTracking) {
	const { supplier, billingSupplier } = assertEditorPrefillPayload(editor, bill, billTracking)
	const expectedFields = [
		["Supplier", "#field-supplier-value", supplier],
		["Billing Supplier", "#field-billing_supplier-value", billingSupplier],
		["Supplier Invoice No", "#field-bill_no-value", bill.bill_no],
		[
			"Supplier Invoice Date",
			"#field-bill_date-value",
			String(bill.bill_date).split("-").reverse().join("-"),
		],
	]
	for (const [label, selector, expected] of expectedFields) {
		const actual = await page.locator(selector).inputValue()
		assert(actual === expected, `${label} prefill is ${JSON.stringify(actual)}; expected ${JSON.stringify(expected)}`)
	}
}

async function billTrackingLifecycleSuite(browser, fixtures) {
	let firstBill = ""
	let bulkOpenBill = ""
	let bulkCancelledBill = ""
	await withPage(browser, (page) => loginAs(page, fixtures.hr_user), async (page) => {
		firstBill = await createBill(page, fixtures, `${Date.now()}-LIFE`)
		await expectBillStatus(page, "Open")
		await page.getByRole("tab", { name: /^History/ }).click()
		await page.locator(".bill-tracking-history__table tbody tr").filter({ hasText: "Open" }).waitFor()
		await page.getByRole("tab", { name: "Details", exact: true }).click()
		await assignBill(page, fixtures)
		await acknowledgeBill(page)
		await requestCancellation(page, firstBill)
	})

	await withPage(browser, (page) => loginAs(page, fixtures.hr_manager), async (page) => {
		await approveCancellation(page, firstBill)
	})

	await withPage(browser, (page) => loginAs(page, fixtures.hr_user), async (page) => {
		await cancelBill(page, firstBill)
		bulkOpenBill = await createBill(page, fixtures, `${Date.now()}-BULK-OPEN`)
		bulkCancelledBill = await createBill(page, fixtures, `${Date.now()}-BULK-CANCEL`)
		await requestCancellation(page, bulkCancelledBill)
	})

	await withPage(browser, (page) => loginAs(page, fixtures.hr_manager), async (page) => {
		await approveCancellation(page, bulkCancelledBill)
	})

	await withPage(browser, (page) => loginAs(page, fixtures.hr_user), async (page) => {
		await cancelBill(page, bulkCancelledBill)
		await bulkAssign(page, fixtures, bulkOpenBill, bulkCancelledBill)
	})

	await withPage(browser, (page) => loginAs(page, fixtures.accounts_user), async (page) => {
		await navigate(page, `${SITE}/web/hr/bill-tracking/${encodeURIComponent(bulkOpenBill)}`)
		await waitForApp(page, ".bill-tracking-header")
		const bills = await resourceList(page, "YRP Bill Tracking", [["name", "=", bulkOpenBill]], [
			"name", "supplier", "bill_no", "bill_date",
		], 1)
		assert(bills.length === 1, `Could not reload created Bill Tracking ${bulkOpenBill}`)
		const editorResponse = page.waitForResponse((response) => (
			apiMethod(response.request()) === PURCHASE_INVOICE_EDITOR_METHOD
			&& requestArgs(response.request()).bill_tracking === bulkOpenBill
		))
		await openAction(page, "Create YRP Purchase Invoice")
		await page.waitForURL(/\/web\/accounts\/purchase-invoices\/new\?/, { timeout: 30_000 })
		await waitForApp(page, ".purchase-invoice-editor__body")
		await page.getByText(`From Bill Tracking ${bulkOpenBill}`, { exact: true }).waitFor()
		const response = await editorResponse
		const payload = await response.json().catch(() => ({}))
		assert(response.ok() && !payload.exc,
			`Purchase Invoice editor prefill failed: HTTP ${response.status()} ${JSON.stringify(payload)}`)
		await assertPurchaseInvoicePrefill(
			page,
			{ ...bills[0], supplier: fixtures.supplier },
			payload.message || {},
			bulkOpenBill,
		)
	})
	fixtureCommand("create_linked_draft_probe", {
		bill_tracking: bulkOpenBill,
		name: `E2E-AHR-PI-${Date.now()}`,
	})
}

async function readOnlySuite(browser, fixtures) {
	await withPage(browser, (page) => loginAs(page, fixtures.plain_user), async (page) => {
		const verifyNoMutations = await installRealRecordMutationGuard(page, "Read-only suite")
		try {
			const capabilities = await callMethod(page, "essdee_yrp.hr.web_workspace.get_capabilities")
			assert(capabilities.sections?.bill_tracking?.can_read, "Plain user lost read-only Bill Tracking access")
			assert(capabilities.sections?.reports?.can_read, "Plain user lost HR report access")
			assert(Object.keys(capabilities.reports || {}).join(",") === "attendance",
				`Plain user HR reports changed: ${JSON.stringify(capabilities.reports)}`)
			await navigate(page, `${SITE}/web/hr`)
			const launcher = page.locator(".workspace-launcher")
			await launcher.getByRole("link", { name: /^Bill Tracking/ }).waitFor({ state: "visible", timeout: 30_000 })
			await launcher.getByRole("link", { name: /^Reports/ }).waitFor({ state: "visible", timeout: 30_000 })

			const bills = await resourceList(page, "YRP Bill Tracking", [["docstatus", "=", 1]], ["name"], 1)
			assert(bills.length, "No real submitted Bill Tracking record is available for read-only verification")
			await navigate(page, `${SITE}/web/hr/bill-tracking/${encodeURIComponent(bills[0].name)}`)
			await waitForApp(page, ".bill-tracking-header")
			const more = page.locator(".document-action-strip__more:visible").first()
			if (await more.count()) {
				await more.click()
				await page.locator(".document-action-menu:visible").waitFor({ state: "visible", timeout: 15_000 })
			}
			for (const action of ["Assign", "Cancel", "Request for Cancel", "Approve Cancel Request"]) {
				assert(!await page.getByRole("button", { name: action, exact: true }).count(), `Plain user can see ${action}`)
				assert(!await page.getByRole("menuitem", { name: action, exact: true }).count(), `Plain user menu contains ${action}`)
			}

			await navigate(page, `${SITE}/web/accounts/purchase-invoices`)
			await page.getByText("You do not have permission to view Purchase Invoices.", { exact: true }).waitFor({ timeout: 30_000 })
		} finally {
			await verifyNoMutations()
		}
	})
}

const SUITE_FUNCTIONS = {
	launcher: launcherSuite,
	"pi-list-view": purchaseInvoiceListSuite,
	"pi-dialogs": purchaseInvoiceDialogsSuite,
	"pi-editor": purchaseInvoiceEditorSuite,
	reports: reportsSuite,
	"bill-tracking-lifecycle": billTrackingLifecycleSuite,
	"read-only": readOnlySuite,
}

async function runSuite(browser, name) {
	let fixtures
	try {
		fixtures = fixtureSetup()
		await SUITE_FUNCTIONS[name](browser, fixtures)
		console.log(`OK ${name}`)
	} finally {
		fixtureTeardown()
	}
}

async function main() {
	assertMutationGuardPolicy()
	const requested = process.argv[2] || "all"
	const selected = requested === "all" ? SUITES : [requested]
	for (const name of selected) assert(SUITE_FUNCTIONS[name], `Unknown suite: ${name}`)
	const browser = await chromium.launch({ headless: true })
	try {
		for (const name of selected) await runSuite(browser, name)
	} finally {
		await browser.close()
	}
}

export {
	PASSWORD,
	SITE,
	assert,
	apiMethod,
	assertMutationGuardPolicy,
	callMethod,
	fixtureCommand,
	fixtureSetup,
	fixtureTeardown,
	installRealRecordMutationGuard,
	login,
	loginAs,
	mutationAttempt,
	navigate,
	openAction,
	requestArgs,
	resourceList,
	sanitizeSensitiveText,
	selectLink,
	waitForApp,
	waitForIdle,
	withPage,
}

const isDirectRun = process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url
if (isDirectRun) {
	main().catch((error) => {
		console.error(sanitizeSensitiveText(error?.stack || error))
		process.exitCode = 1
	})
}
