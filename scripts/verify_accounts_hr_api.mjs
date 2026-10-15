#!/usr/bin/env node

import { mkdirSync, readFileSync, writeFileSync } from "node:fs"
import { createRequire } from "node:module"
import { join } from "node:path"

import { accountsHrApiMatrix } from "./accounts_hr_api_matrix.mjs"
import {
	PASSWORD,
	SITE,
	assert,
	fixtureSetup,
	fixtureTeardown,
	installRealRecordMutationGuard,
	navigate,
	openAction,
	sanitizeSensitiveText,
	selectLink,
	waitForApp,
} from "./verify_accounts_hr_workspace.mjs"

const require = createRequire("/home/anas/.claude/playwright/package.json")
const { chromium } = require("playwright")

const ADMIN_CREDENTIALS = "/home/anas/.frappe-debug-creds-mrp3"
const DEFAULT_OUTPUT_DIRECTORY = (
	"/tmp/claude-1000/-home-anas-pilot-benches-frappe-16/"
	+ "348c72ab-5d72-4bcf-a023-b3fbf230e45a/scratchpad"
)
const RESULT_DIRECTORY = join(
	process.env.ACCOUNTS_HR_OUTPUT_DIR || DEFAULT_OUTPUT_DIRECTORY,
	"api_verification",
)
const RESULT_FILE = join(RESULT_DIRECTORY, "accounts_hr_api_results.json")
const PURCHASE_INVOICE = "YRP Purchase Invoice"
const BILL_TRACKING = "YRP Bill Tracking"
const BILL_TRACKING_METHOD = "yrp.yrp.doctype.yrp_bill_tracking.yrp_bill_tracking"
const BILL_TRACKING_OVERRIDE = "essdee_yrp.overrides.bill_tracking"
const HR_WORKSPACE = "essdee_yrp.hr.web_workspace"
const PURCHASE_INVOICE_WORKSPACE = "essdee_yrp.accounts.purchase_invoice_workspace.get_purchase_invoice_workspace"
const API_TIMEOUT = 30_000
const ATTENDANCE_SECRET_ERROR = "Password not found for SD YRP MRP Settings SD YRP MRP Settings hr_api_secret"
const ATTENDANCE_INCOMPLETE = "INCOMPLETE (site lacks hr_api_secret)"
const ERP_SUBMIT_UNAVAILABLE = "UNAVAILABLE (no eligible real invoice)"
const REPORT_USERS = ["accounts", "hr", "plain"]

function parseOptions() {
	const options = { runHttp: true, runUi: true, row: null }
	for (let index = 2; index < process.argv.length; index += 1) {
		const value = process.argv[index]
		if (value === "--http-only") options.runUi = false
		else if (value === "--ui-only") options.runHttp = false
		else if (value === "--row") options.row = Number(process.argv[++index])
		else throw new Error(`Unknown argument: ${value}`)
	}
	assert(options.runHttp || options.runUi, "Choose at least one verification mode")
	if (options.row !== null) assert(Number.isInteger(options.row), "--row requires an integer")
	return options
}

function localToday() {
	const values = new Intl.DateTimeFormat("en-CA", {
		timeZone: "Asia/Kolkata",
		year: "numeric",
		month: "2-digit",
		day: "2-digit",
	}).formatToParts(new Date())
	const parts = Object.fromEntries(values.map(({ type, value }) => [type, value]))
	return `${parts.year}-${parts.month}-${parts.day}`
}

function responseSummary(response) {
	const exception = response.payload?.exc_type || response.payload?.exception || ""
	const message = response.payload?.message
	return `HTTP ${response.status}${exception ? ` ${exception}` : ""}${message === undefined ? "" : ` ${shortJson(message)}`}`
}

function shortJson(value) {
	const output = JSON.stringify(value)
	return output.length > 240 ? `${output.slice(0, 237)}...` : output
}

function hasPermissionFailure(response) {
	return response.status === 403
		|| response.payload?.exc_type === "PermissionError"
}

function assertSuccess(response, label) {
	assert(response.status === 200 && !response.payload?.exc, `${label}: ${responseSummary(response)}`)
}

function hasExactValidationFailure(response, message) {
	return response.payload?.exc_type === "ValidationError"
		&& validationDetails(response).includes(message)
}

function validationDetails(response) {
	return [
		response.payload?.message,
		response.payload?._server_messages,
		response.payload?.exc,
	].filter(Boolean).join(" ")
}

class FrappeSession {
	constructor(context, page, csrfToken, user) {
		this.context = context
		this.page = page
		this.csrfToken = csrfToken
		this.user = user
	}

	static async login(browser, user, password) {
		const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
		const response = await context.request.post(`${SITE}/api/method/login`, {
			form: { usr: user, pwd: password },
		})
		assert(response.ok(), `Login failed for ${user}: HTTP ${response.status()} ${await response.text()}`)
		const page = await context.newPage()
		await navigate(page, `${SITE}/web`)
		const csrfToken = await page.evaluate(() => window.csrf_token || window.frappe?.csrf_token || "")
		assert(csrfToken, `No CSRF token was exposed for ${user}`)
		return new FrappeSession(context, page, csrfToken, user)
	}

	static async guest(browser) {
		const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
		return new FrappeSession(context, null, "", "Guest")
	}

	async call(path, httpMethod, args = {}) {
		const options = {
			headers: { "X-Frappe-CSRF-Token": this.csrfToken },
			timeout: 120_000,
		}
		if (httpMethod === "GET") options.params = encodeQuery(args)
		else options.data = args
		const response = await this.context.request[httpMethod.toLowerCase()](
			`${SITE}/api/method/${path}`,
			options,
		)
		return {
			status: response.status(),
			payload: await response.json().catch(() => ({})),
		}
	}

	async callOk(path, args = {}, httpMethod = "POST") {
		const response = await this.call(path, httpMethod, args)
		assertSuccess(response, `${path} as ${this.user}`)
		return response.payload.message
	}

	async resourceRows(doctype, { fields = ["name"], filters = [], limit = 20 } = {}) {
		const query = new URLSearchParams({
			fields: JSON.stringify(fields),
			filters: JSON.stringify(filters),
			limit_page_length: String(limit),
		})
		const response = await this.context.request.get(
			`${SITE}/api/resource/${encodeURIComponent(doctype)}?${query}`,
		)
		const payload = await response.json().catch(() => ({}))
		assert(response.ok(), `Could not list ${doctype}: HTTP ${response.status()} ${JSON.stringify(payload)}`)
		return payload.data || []
	}

	async resourceDocument(doctype, name) {
		const response = await this.context.request.get(
			`${SITE}/api/resource/${encodeURIComponent(doctype)}/${encodeURIComponent(name)}`,
		)
		const payload = await response.json().catch(() => ({}))
		assert(response.ok(), `Could not read ${doctype} ${name}: HTTP ${response.status()} ${JSON.stringify(payload)}`)
		return payload.data
	}

	async newPage() {
		return this.context.newPage()
	}

	async close() {
		await this.context.close()
	}
}

function encodeQuery(args) {
	return Object.fromEntries(Object.entries(args).filter(([, value]) => value !== undefined).map(([key, value]) => [
		key,
		value !== null && typeof value === "object" ? JSON.stringify(value) : String(value ?? ""),
	]))
}

async function findErpEligibleDraft(accounts, rows, loadedDraft) {
	if (loadedDraft.items?.length) return loadedDraft
	for (const row of rows) {
		if (row.name === loadedDraft.name) continue
		const invoice = await accounts.resourceDocument(PURCHASE_INVOICE, row.name)
		if (invoice.items?.length) return invoice
	}
	throw new Error("No real draft Purchase Invoice with grouped items is available")
}

async function getReferencedWorkOrders(accounts, invoice) {
	const names = [...new Set(
		(invoice.pi_work_order_billed_details || []).map((row) => row.work_order).filter(Boolean),
	)]
	assert(names.length, `${invoice.name} has no billed Work Order detail`)
	const workOrders = []
	for (const name of names) {
		const workOrder = await accounts.resourceDocument("YRP Work Order", name)
		workOrders.push({ name: workOrder.name, modified: workOrder.modified })
	}
	return workOrders
}

async function getErpSubmitEligibility(accounts, invoiceName) {
	const invoice = await accounts.resourceDocument(PURCHASE_INVOICE, invoiceName)
	const workspace = await accounts.callOk(PURCHASE_INVOICE_WORKSPACE, { name: invoiceName }, "GET")
	assertRecord(workspace, PURCHASE_INVOICE, invoiceName, 1, "ERP-submit workspace")
	const capability = requireKeys(
		workspace.capabilities?.submit_erp_bill,
		["allowed", "label", "reason"],
		`${invoiceName} Submit ERP Bill capability`,
	)
	assert(typeof capability.allowed === "boolean", `${invoiceName} returned an invalid ERP-submit capability`)
	assert(typeof workspace.erp_sync_enabled === "boolean", `${invoiceName} omitted ERP sync availability`)
	const isDocumentEligible = Boolean(invoice.erp_inv_name)
		&& Number(invoice.erp_inv_docstatus) === 0
		&& workspace.erp_sync_enabled
	return { capability, invoice, isDocumentEligible, workspace }
}

async function findErpSubmitEligibleInvoice(accounts, candidates) {
	for (const candidate of candidates) {
		const eligibility = await getErpSubmitEligibility(accounts, candidate.name)
		if (!eligibility.isDocumentEligible) continue
		assert(
			eligibility.workspace.permissions?.can_submit === true,
			`${candidate.name} is ERP-submit eligible but Accounts User lacks submit permission`,
		)
		assert(
			eligibility.capability.allowed === true,
			`${candidate.name} is ERP-submit eligible but its workspace capability is disabled`,
		)
		return eligibility.invoice
	}
	return null
}

async function discoverRealRecords(sessions, fixtures) {
	const invoiceFilters = [["supplier", "!=", fixtures.supplier]]
	const submittedRows = await sessions.accounts.resourceRows(PURCHASE_INVOICE, {
		fields: ["name", "modified", "erp_inv_name", "erp_inv_docstatus"],
		filters: [...invoiceFilters, ["docstatus", "=", 1]],
		limit: 20,
	})
	const draftRows = await sessions.accounts.resourceRows(PURCHASE_INVOICE, {
		fields: ["name", "modified"],
		filters: [...invoiceFilters, ["docstatus", "=", 0], ["against", "=", "YRP Work Order"], ["approved_by", "is", "not set"]],
		limit: 20,
	})
	const erpDraftRows = await sessions.accounts.resourceRows(PURCHASE_INVOICE, {
		fields: ["name", "modified"],
		filters: [...invoiceFilters, ["docstatus", "=", 0]],
		limit: 100,
	})
	const erpRows = await sessions.accounts.resourceRows(PURCHASE_INVOICE, {
		fields: ["name", "modified", "erp_inv_name", "erp_inv_docstatus"],
		filters: [...invoiceFilters, ["docstatus", "=", 1], ["erp_inv_name", "is", "set"]],
		limit: 100,
	})
	assert(submittedRows.length, "No real submitted Purchase Invoice is available")
	assert(draftRows.length, "No real unapproved draft Work Order Purchase Invoice is available")
	assert(erpDraftRows.length, "No real draft Purchase Invoice is available")
	assert(erpRows.length, "No real submitted Purchase Invoice with an ERP invoice is available")

	const draft = await sessions.accounts.resourceDocument(PURCHASE_INVOICE, draftRows[0].name)
	const erpEligibleDraft = await findErpEligibleDraft(sessions.accounts, erpDraftRows, draft)
	const erpSubmitEligible = await findErpSubmitEligibleInvoice(sessions.accounts, erpRows)
	const workOrders = await getReferencedWorkOrders(sessions.accounts, draft)
	const sewingUnits = await sessions.administrator.resourceRows("Supplier", {
		fields: ["name"],
		filters: [["is_company_location", "=", 1], ["disabled", "=", 0]],
		limit: 1,
	})
	assert(sewingUnits.length, "No enabled Sewing Unit is available for the Sewing DPR")
	const stockRows = await sessions.accounts.resourceRows("YRP Stock Ledger Entry", {
		fields: ["item", "warehouse"],
		filters: [["posting_date", "<=", localToday()]],
		limit: 1,
	})
	assert(stockRows[0]?.item && stockRows[0]?.warehouse, "No readable Stock Ledger row is available")
	return {
		submittedPurchaseInvoice: submittedRows[0],
		draftWorkOrderPurchaseInvoice: draftRows[0],
		erpEligibleDraftPurchaseInvoice: {
			name: erpEligibleDraft.name,
			modified: erpEligibleDraft.modified,
		},
		erpPurchaseInvoice: erpRows[0],
		erpSubmitEligiblePurchaseInvoice: erpSubmitEligible,
		workOrder: workOrders[0],
		workOrders,
		sewingUnit: sewingUnits[0].name,
		stockItem: stockRows[0].item,
		stockWarehouse: stockRows[0].warehouse,
	}
}

async function snapshotRealRecords(admin, real) {
	const targets = [
		[PURCHASE_INVOICE, real.submittedPurchaseInvoice.name],
		[PURCHASE_INVOICE, real.draftWorkOrderPurchaseInvoice.name],
		[PURCHASE_INVOICE, real.erpEligibleDraftPurchaseInvoice.name],
		[PURCHASE_INVOICE, real.erpPurchaseInvoice.name],
		...(real.erpSubmitEligiblePurchaseInvoice
			? [[PURCHASE_INVOICE, real.erpSubmitEligiblePurchaseInvoice.name]]
			: []),
		...real.workOrders.map((workOrder) => ["YRP Work Order", workOrder.name]),
	]
	const snapshot = {}
	for (const [doctype, name] of targets) {
		const key = `${doctype}:${name}`
		if (snapshot[key]) continue
		const document = await admin.resourceDocument(doctype, name)
		snapshot[key] = {
			modified: document.modified,
			erp_inv_docstatus: doctype === PURCHASE_INVOICE ? document.erp_inv_docstatus : undefined,
		}
	}
	return snapshot
}

function assertSnapshotsEqual(before, after) {
	assert(JSON.stringify(before) === JSON.stringify(after), [
		"A real record changed during API verification.",
		`Before: ${JSON.stringify(before)}`,
		`After: ${JSON.stringify(after)}`,
	].join("\n"))
}

class VerificationContext {
	constructor({ fixtures, real, sessions, row, mode, ui }) {
		this.fixtures = fixtures
		this.real = real
		this.sessions = sessions
		this.row = row
		this.mode = mode
		this.ui = ui
		this.today = localToday()
		this.scenario = {}
		this.sequence = 0
	}

	unique(label) {
		this.sequence += 1
		return `E2E-AHR-API-${this.row.row}-${label}-${Date.now()}-${this.sequence}`
	}

	billValues(label) {
		return {
			supplier: this.fixtures.supplier,
			bill_no: this.unique(label),
			bill_date: this.today,
			invoice_value: 1250,
			received_date: this.today,
			received_via: "HO",
			receive_comment: "E2E-AHR API verification",
			delivery_mob_no: "",
		}
	}

	async prepare() {
		const preparations = {
			"submitted-bill": async () => ({ bill: await this.createBill(true, "SUBMITTED") }),
			"draft-bill": async () => ({ bill: await this.createBill(false, "DRAFT") }),
			"assigned-bill": () => this.prepareAssignedBill(),
			"pending-bill": () => this.preparePendingBill(),
			"approved-bill": () => this.prepareApprovedBill(),
			"bulk-bills": () => this.prepareBulkBills(),
		}
		if (this.row.scenario) {
			this.scenario = await preparations[this.row.scenario]()
			if (this.scenario.bill) {
				const bill = await this.sessions.administrator.resourceDocument(
					BILL_TRACKING,
					this.scenario.bill,
				)
				this.scenario.modified = bill.modified
			}
		}
	}

	async createBill(submit, label) {
		const workspace = await this.sessions.hr.callOk(`${HR_WORKSPACE}.save_bill_tracking`, {
			values: this.billValues(`${this.mode}-${label}`),
			submit,
		})
		const name = workspace?.record?.name
		assert(name, "Bill Tracking creation returned no record name")
		return name
	}

	async prepareAssignedBill() {
		const bill = await this.createBill(true, "ASSIGNED")
		await this.sessions.hr.callOk(`${BILL_TRACKING_METHOD}.assign_vendor_bill`, {
			name: bill,
			assigned_to: this.fixtures.department,
			remarks: "E2E-AHR API setup",
		})
		return { bill }
	}

	async preparePendingBill() {
		const bill = await this.createBill(true, "PENDING")
		await this.sessions.hr.callOk(`${BILL_TRACKING_OVERRIDE}.request_bill_cancellation`, { name: bill })
		return { bill }
	}

	async prepareApprovedBill() {
		const scenario = await this.preparePendingBill()
		await this.sessions.hrm.callOk(`${BILL_TRACKING_OVERRIDE}.approve_bill_cancellation`, {
			name: scenario.bill,
		})
		return scenario
	}

	async prepareBulkBills() {
		const openBill = await this.createBill(true, "BULK-OPEN")
		const cancelledBill = await this.createBill(true, "BULK-CANCELLED")
		await this.sessions.hr.callOk(`${BILL_TRACKING_OVERRIDE}.request_bill_cancellation`, {
			name: cancelledBill,
		})
		await this.sessions.hrm.callOk(`${BILL_TRACKING_OVERRIDE}.approve_bill_cancellation`, {
			name: cancelledBill,
		})
		await this.sessions.hr.callOk(`${BILL_TRACKING_METHOD}.cancel_vendor_bill`, {
			name: cancelledBill,
			cancel_reason: "E2E-AHR bulk verification fixture",
		})
		return { openBill, cancelledBill }
	}

	async assertPositiveState(response) {
		await assertPersistedMutation(this, response)
	}

	async assertRejectedState(expected) {
		if (this.row.path !== `${HR_WORKSPACE}.execute_bill_tracking_command`) return
		const bill = await fixtureBill(this, this.scenario.bill)
		assert(expected === "permission" && bill.docstatus === 0, "Rejected Delete changed the draft bill")
	}
}

function objectPayload(value, label) {
	assert(value && typeof value === "object" && !Array.isArray(value), `${label} did not return an object`)
	return value
}

function requireKeys(value, keys, label) {
	const payload = objectPayload(value, label)
	for (const key of keys) assert(Object.hasOwn(payload, key), `${label} omitted ${key}`)
	return payload
}

function assertArray(value, label) {
	assert(Array.isArray(value), `${label} did not return an array`)
	return value
}

function assertRecord(message, doctype, name, docstatus, label) {
	const required = doctype === PURCHASE_INVOICE
		? ["doctype", "name", "docstatus", "modified"]
		: ["name", "docstatus", "modified"]
	const record = requireKeys(message?.record, required, `${label} record`)
	if (doctype === PURCHASE_INVOICE) {
		assert(record.doctype === doctype, `${label} returned ${record.doctype} instead of ${doctype}`)
	}
	assert(record.name === name, `${label} returned ${record.name} instead of ${name}`)
	assert(record.docstatus === docstatus, `${label} returned docstatus ${record.docstatus}`)
	return record
}

function validateAccountsCapabilities(message, context, label) {
	const payload = requireKeys(message, ["sections", "reports"], label)
	assert(payload.sections?.purchase_invoices?.can_read === true, `${label} omitted Purchase Invoice read`)
	assert(payload.sections?.purchase_invoices?.can_create === true, `${label} omitted Purchase Invoice create`)
	const expected = ["cutting_dpr", "finishing_dispatch", "ironing_dpr", "sewing_dpr", "stock_balance"]
	assert(JSON.stringify(Object.keys(payload.reports).sort()) === JSON.stringify(expected), `${label} report gates changed`)
}

function validateHrCapabilities(message, context, label) {
	const payload = requireKeys(message, ["sections", "reports"], label)
	assert(payload.sections?.bill_tracking?.can_read === true, `${label} omitted Bill Tracking read`)
	assert(payload.sections?.bill_tracking?.can_create === true, `${label} omitted Bill Tracking create`)
	assert(payload.reports?.attendance?.can_read === true, `${label} omitted Attendance`)
}

function validatePurchaseInvoiceWorkspace(message, context, label) {
	assertRecord(message, PURCHASE_INVOICE, context.real.submittedPurchaseInvoice.name, 1, label)
	for (const key of ["details", "totals", "items", "grns", "verification", "debit_summary", "approvals", "work_orders", "print_formats"]) {
		assertArray(message[key], `${label} ${key}`)
	}
	requireKeys(message.permissions, ["can_read", "can_write", "can_submit"], `${label} permissions`)
	requireKeys(message.capabilities, ["show_erp_bill", "cancel", "amend", "delete"], `${label} capabilities`)
}

function validatePurchaseInvoiceEditor(message, context, label) {
	const payload = requireKeys(message, ["values", "grns", "items", "schema", "locked_fields"], label)
	assert(payload.values.bill_tracking === context.scenario.bill, `${label} lost Bill Tracking prefill`)
	assert(payload.values.bill_no?.startsWith("E2E-AHR-API-"), `${label} lost fixture bill number`)
	assertArray(payload.grns, `${label} GRNs`)
	assertArray(payload.items, `${label} items`)
	for (const field of ["supplier", "against", "bill_no", "bill_date"]) {
		requireKeys(payload.schema[field], ["label", "fieldtype", "reqd"], `${label} ${field} schema`)
	}
	assert(["supplier", "bill_no", "bill_date"].every((field) => payload.locked_fields.includes(field)), `${label} omitted locked fields`)
}

function validateWorkOrderCheck(message, context, label) {
	const payload = requireKeys(message, ["all_closed", "open_work_orders", "close_request_wos"], label)
	assert(typeof payload.all_closed === "boolean", `${label} returned a non-boolean all_closed`)
	assertArray(payload.open_work_orders, `${label} open_work_orders`)
	assertArray(payload.close_request_wos, `${label} close_request_wos`)
}

function validateErpLink(message, context, label) {
	assert(typeof message === "string" && message.includes(encodeURIComponent(context.real.erpPurchaseInvoice.erp_inv_name)), `${label} returned the wrong ERP link`)
}

function validateCloseContext(message, context, label) {
	const payload = requireKeys(message, ["permission", "debits", "reason_options", "close_reason", "can_create_debit", "can_approve_debit"], label)
	objectPayload(payload.permission, `${label} permission`)
	assertArray(payload.debits, `${label} debits`)
	assertArray(payload.reason_options, `${label} reason_options`)
	assert(typeof payload.can_create_debit === "boolean", `${label} returned invalid create permission`)
	assert(typeof payload.can_approve_debit === "boolean", `${label} returned invalid approve permission`)
}

function validateBillWorkspace(message, context, label) {
	assertRecord(message, BILL_TRACKING, context.scenario.bill, 1, label)
	assertArray(message.details, `${label} details`)
	assertArray(message.history, `${label} history`)
	requireKeys(message.permissions, ["can_read", "can_write", "can_submit", "can_delete"], `${label} permissions`)
	requireKeys(message.capabilities, ["assign", "bill_received", "submit", "delete"], `${label} capabilities`)
}

function validateBillEditor(message, context, label) {
	const payload = requireKeys(message, ["values", "received_via_options", "schema", "modified", "can_submit"], label)
	assertArray(payload.received_via_options, `${label} received_via_options`)
	assert(typeof payload.can_submit === "boolean", `${label} returned invalid submit permission`)
	for (const field of ["supplier", "bill_no", "bill_date", "invoice_value", "received_via"]) {
		requireKeys(payload.schema[field], ["label", "fieldtype", "reqd"], `${label} ${field} schema`)
	}
}

function validateSubmittedBill(message, context, label) {
	const expectedName = context.scenario.bill || message?.record?.name
	const record = assertRecord(message, BILL_TRACKING, expectedName, 1, label)
	assert(record.form_status === "Open", `${label} returned status ${record.form_status}`)
	assert(record.bill_no?.startsWith("E2E-AHR-API-"), `${label} returned a non-fixture bill`)
	assertArray(message.history, `${label} history`)
	assert(message.history.some((row) => row.action === "Open"), `${label} omitted the Open history row`)
}

function validateStockReport(message, context, label) {
	const payload = requireKeys(message, ["columns", "result"], label)
	const columns = assertArray(payload.columns, `${label} columns`)
	assert(columns.length > 0, `${label} returned no columns`)
	assertArray(payload.result, `${label} result`)
}

function validateCuttingDpr(message, context, label) {
	const payload = requireKeys(message, ["report_data", "bundle_generated", "label_printed", "created"], label)
	assertArray(payload.report_data, `${label} report_data`)
	for (const key of ["bundle_generated", "label_printed", "created"]) {
		assert(Number.isFinite(Number(payload[key])), `${label} returned invalid ${key}`)
	}
}

function validateCuttingSummary(message, context, label) {
	for (const [index, day] of assertArray(message, label).entries()) {
		requireKeys(day, ["date", "report_data", "bundle_generated", "label_printed", "created"], `${label} day ${index}`)
		assertArray(day.report_data, `${label} day ${index} report_data`)
	}
}

function validateSewingDpr(message, context, label) {
	const payload = requireKeys(message, ["date", "headers", "dpr_data", "pending_fi", "status", "blocked", "message"], label)
	assert(payload.date === context.today, `${label} returned date ${payload.date}`)
	assertArray(payload.headers, `${label} headers`)
	objectPayload(payload.dpr_data, `${label} dpr_data`)
	assertArray(payload.pending_fi, `${label} pending_fi`)
	assert(typeof payload.blocked === "boolean", `${label} returned invalid blocked state`)
}

function validateSewingSummary(message, context, label) {
	const payload = requireKeys(message, ["reports", "pending_fi", "status", "blocked", "message"], label)
	assertArray(payload.reports, `${label} reports`)
	assertArray(payload.pending_fi, `${label} pending_fi`)
	assert(["success", "pending_fi"].includes(payload.status), `${label} returned status ${payload.status}`)
	assert(typeof payload.blocked === "boolean", `${label} returned invalid blocked state`)
}

function validateFinishingDispatch(message, context, label) {
	const payload = requireKeys(message, ["data", "sizes"], label)
	assertArray(payload.data, `${label} data`)
	assertArray(payload.sizes, `${label} sizes`)
}

function validateIroningDpr(message, context, label) {
	for (const [index, report] of assertArray(message, label).entries()) {
		requireKeys(report, ["lot", "item", "primary_attributes", "rows"], `${label} report ${index}`)
		assertArray(report.primary_attributes, `${label} report ${index} primary_attributes`)
		assertArray(report.rows, `${label} report ${index} rows`)
	}
}

function validateAttendancePayload(message, context, label) {
	const payload = requireKeys(message, ["columns", "rows", "employee_punches", "shifts", "add_total_row"], label)
	const columns = assertArray(payload.columns, `${label} columns`)
	assert(columns.every((column) => typeof column?.fieldname === "string" && column.fieldname), `${label} returned invalid columns`)
	assertArray(payload.rows, `${label} rows`)
	assertArray(payload.employee_punches, `${label} employee_punches`)
	assertArray(payload.shifts, `${label} shifts`)
}

const SUCCESS_VALIDATORS = {
	"accounts-capabilities": validateAccountsCapabilities,
	"hr-capabilities": validateHrCapabilities,
	"purchase-invoice-workspace": validatePurchaseInvoiceWorkspace,
	"purchase-invoice-editor": validatePurchaseInvoiceEditor,
	"work-order-check": validateWorkOrderCheck,
	"erp-link": validateErpLink,
	"work-order-close-context": validateCloseContext,
	"bill-workspace": validateBillWorkspace,
	"bill-editor": validateBillEditor,
	"bill-submitted": validateSubmittedBill,
	"delivery-people": (message, context, label) => assertArray(message, label),
	"open-delivery-people": (message, context, label) => assertArray(message, label),
	"stock-report": validateStockReport,
	"cutting-dpr": validateCuttingDpr,
	"cutting-summary": validateCuttingSummary,
	"sewing-dpr": validateSewingDpr,
	"open-sewing-dpr": validateSewingDpr,
	"sewing-summary": validateSewingSummary,
	"open-sewing-summary": validateSewingSummary,
	"finishing-dispatch": validateFinishingDispatch,
	"ironing-dpr": validateIroningDpr,
	"open-ironing-dpr": validateIroningDpr,
	"bill-assigned": () => {},
	"bill-received": () => {},
	"cancellation-requested": () => {},
	"cancellation-approved": () => {},
	"bill-cancelled": () => {},
}

async function fixtureBill(context, name) {
	const bill = await context.sessions.administrator.resourceDocument(BILL_TRACKING, name)
	assert(bill.supplier === context.fixtures.supplier, `${name} is not owned by the fixture Supplier`)
	assert(bill.bill_no?.startsWith("E2E-AHR-API-"), `${name} is not an E2E-AHR API bill`)
	return bill
}

function lastAssignment(bill, department) {
	return [...(bill.bill_tracking_history || [])].reverse().find((row) => row.assigned_to === department)
}

async function assertBillSubmitted(context, response) {
	const name = context.scenario.bill || response.payload.message?.record?.name
	assert(name, "Bill submit response returned no record name")
	const bill = await fixtureBill(context, name)
	assert(bill.docstatus === 1 && bill.form_status === "Open", `${name} was not persisted as submitted and Open`)
}

async function assertBillAssigned(context) {
	const bill = await fixtureBill(context, context.scenario.bill)
	const assignment = lastAssignment(bill, context.fixtures.department)
	assert(bill.assigned_to === context.fixtures.department && bill.form_status === "Assigned", `${bill.name} was not assigned`)
	assert(assignment?.action === "Assign", `${bill.name} has no persisted assignment history`)
}

async function assertBillReceived(context) {
	const bill = await fixtureBill(context, context.scenario.bill)
	const assignment = lastAssignment(bill, context.fixtures.department)
	assert(Number(assignment?.received) === 1, `${bill.name} receipt acknowledgement was not persisted`)
}

async function assertBulkAssignment(context) {
	const openBill = await fixtureBill(context, context.scenario.openBill)
	const cancelledBill = await fixtureBill(context, context.scenario.cancelledBill)
	assert(openBill.assigned_to === context.fixtures.department, `${openBill.name} was not assigned by bulk action`)
	assert(openBill.form_status === "Assigned", `${openBill.name} did not persist Assigned status`)
	assert(cancelledBill.docstatus === 2 && cancelledBill.form_status === "Cancelled", `${cancelledBill.name} changed unexpectedly`)
}

async function assertCancellationState(context, status, docstatus = 1) {
	const bill = await fixtureBill(context, context.scenario.bill)
	assert(bill.form_status === status && bill.docstatus === docstatus, `${bill.name} did not persist ${status}`)
	if (docstatus === 2) assert(bill.cancel_reason?.startsWith("E2E-AHR API"), `${bill.name} lost its cancellation reason`)
}

async function assertNoPurchaseInvoice(context) {
	const rows = await context.sessions.administrator.resourceRows(PURCHASE_INVOICE, {
		fields: ["name"],
		filters: [["supplier", "=", context.fixtures.supplier]],
		limit: 20,
	})
	assert(!rows.length, `Invalid Purchase Invoice request persisted ${rows.map((row) => row.name).join(", ")}`)
}

async function assertRealInvoiceUnchanged(context) {
	const expected = context.real.submittedPurchaseInvoice
	const invoice = await context.sessions.administrator.resourceDocument(PURCHASE_INVOICE, expected.name)
	assert(invoice.docstatus === 1 && invoice.modified === expected.modified, `${expected.name} changed after rejected submit`)
}

const PERSISTED_ASSERTIONS = {
	"purchase-invoice-validation": assertNoPurchaseInvoice,
	"action-unavailable": assertRealInvoiceUnchanged,
	"bill-submitted": assertBillSubmitted,
	"bill-assigned": assertBillAssigned,
	"bill-received": assertBillReceived,
	"bulk-partial": assertBulkAssignment,
	"cancellation-requested": (context) => assertCancellationState(context, "Pending Approval"),
	"cancellation-approved": (context) => assertCancellationState(context, "Cancel Request Approved"),
	"bill-cancelled": (context) => assertCancellationState(context, "Cancelled", 2),
}

async function assertPersistedMutation(context, response) {
	if (!context.row.mutates) return
	const assertion = PERSISTED_ASSERTIONS[context.row.positiveExpected]
	if (assertion) await assertion(context, response)
}

function validateBulkResponse(message, expected, context, label) {
	const payload = requireKeys(message, ["assigned", "skipped"], label)
	assertArray(payload.assigned, `${label} assigned`)
	const skipped = assertArray(payload.skipped, `${label} skipped`)
	if (expected === "bulk-partial") {
		assert(JSON.stringify(payload.assigned) === JSON.stringify([context.scenario.openBill]), `${label} assigned the wrong bill`)
		assert(skipped.length === 1 && skipped[0].name === context.scenario.cancelledBill, `${label} skipped the wrong bill`)
		assert(typeof skipped[0].reason === "string" && skipped[0].reason.trim(), `${label} omitted the skip reason`)
		return
	}
	assert(!payload.assigned.length, `${label} assigned a bill`)
	assert(JSON.stringify(skipped.map((row) => row.name).sort()) === JSON.stringify([
		context.scenario.cancelledBill,
		context.scenario.openBill,
	].sort()), `${label} did not skip both fixture bills`)
	assert(skipped.every((row) => /permission|permitted|access|not allowed/i.test(row.reason || "")), `${label} did not report authorization denial for every bill`)
}

function validateSuccessfulResponse(response, expected, context, label) {
	assertSuccess(response, label)
	const validator = SUCCESS_VALIDATORS[expected]
	assert(validator, `Unknown successful response expectation: ${expected}`)
	validator(response.payload.message, context, label)
}

function validateAttendanceResponse(response, context, label) {
	if (hasExactValidationFailure(response, ATTENDANCE_SECRET_ERROR)) {
		return { incomplete: true, actual: ATTENDANCE_INCOMPLETE }
	}
	assert(
		response.status === 200 && !response.payload?.exc,
		`${label}: ${responseSummary(response)} ${shortJson(validationDetails(response))}`,
	)
	validateAttendancePayload(response.payload.message, context, label)
	return null
}

function validatePermissionResponse(response, context, label) {
	assert(hasPermissionFailure(response), `${label}: ${responseSummary(response)}`)
}

function validatePurchaseInvoiceFailure(response, context, label) {
	const expected = "Fetch GRN into Grouped Items before submitting this invoice."
	assert(hasExactValidationFailure(response, expected), `${label}: ${responseSummary(response)} ${shortJson(validationDetails(response))}`)
}

function validateGrnSelectionFailure(response, context, label) {
	assert(hasExactValidationFailure(response, "Please select at least one GRN."), `${label}: ${responseSummary(response)}`)
}

function validateUnavailableAction(response, context, label) {
	const isUnavailable = JSON.stringify(response.payload).includes("not available")
	assert(hasPermissionFailure(response) && isUnavailable, `${label}: ${responseSummary(response)}`)
}

function validateExpenseHeadResponse(response, context, label) {
	if (response.status === 200 && !response.payload?.exc) {
		assertArray(response.payload.message, label)
		return
	}
	const expected = "ERP Purchase Invoice creation is not available on this site."
	assert(hasExactValidationFailure(response, expected), `${label}: ${responseSummary(response)}`)
}

function validateEmptyList(response, context, label) {
	assertSuccess(response, label)
	assert(Array.isArray(response.payload.message) && !response.payload.message.length, `${label} did not return []`)
}

function validateDeniedAccountsCapabilities(response, context, label) {
	assertSuccess(response, label)
	const sections = requireKeys(response.payload.message, ["sections", "reports"], label).sections
	assert(sections?.purchase_invoices?.can_read === false, `${label} exposed Purchase Invoices`)
}

function validateDeniedHrCapabilities(response, context, label) {
	assertSuccess(response, label)
	const sections = requireKeys(response.payload.message, ["sections", "reports"], label).sections
	assert(sections?.bill_tracking?.can_create === false, `${label} exposed Bill Tracking create`)
}

function validateReadOnlyWorkspace(response, context, label) {
	assertSuccess(response, label)
	validateBillWorkspace(response.payload.message, context, label)
	const actions = response.payload.message.capabilities
	const mutating = ["assign", "bill_received", "request_cancel", "approve_cancel", "cancel", "create_purchase_invoice", "edit", "submit", "delete"]
	assert(mutating.every((key) => actions[key]?.allowed === false), `${label} exposed or omitted a mutating action`)
}

function validateDepartmentFailure(response, context, label) {
	const expected = "This bill is not assigned to your department."
	assert(hasExactValidationFailure(response, expected), `${label}: ${responseSummary(response)}`)
}

function validateBulkResult(response, context, label, expected) {
	assertSuccess(response, label)
	validateBulkResponse(response.payload.message, expected, context, label)
}

function validateFixtureDepartment(response, context, label) {
	assertSuccess(response, label)
	const departments = assertArray(response.payload.message, label)
	assert(departments.includes(context.fixtures.department), `${label} omitted the fixture Department`)
}

const RESPONSE_VALIDATORS = {
	permission: validatePermissionResponse,
	"purchase-invoice-validation": validatePurchaseInvoiceFailure,
	"grn-selection-validation": validateGrnSelectionFailure,
	"action-unavailable": validateUnavailableAction,
	"expense-head-response": validateExpenseHeadResponse,
	"empty-list": validateEmptyList,
	"accounts-capabilities-denied": validateDeniedAccountsCapabilities,
	"hr-capabilities-denied": validateDeniedHrCapabilities,
	"read-only-workspace": validateReadOnlyWorkspace,
	"department-validation": validateDepartmentFailure,
	"bulk-partial": (response, context, label) => validateBulkResult(response, context, label, "bulk-partial"),
	"bulk-denied": (response, context, label) => validateBulkResult(response, context, label, "bulk-denied"),
	"fixture-department": validateFixtureDepartment,
	"attendance-report": validateAttendanceResponse,
}

function validateResponse(response, expected, context, label) {
	const validator = RESPONSE_VALIDATORS[expected]
	if (validator) return validator(response, context, label)
	validateSuccessfulResponse(response, expected, context, label)
	return null
}

class UiDriver {
	constructor(results) {
		this.results = results
	}

	async capture(page, context, trigger, expectation = context.row.positiveExpected) {
		const responsePromise = page.waitForResponse(
			(response) => apiPath(response.url()) === context.row.path,
			{ timeout: API_TIMEOUT },
		)
		responsePromise.catch(() => {})
		await trigger()
		const browserResponse = await responsePromise
		const response = {
			status: browserResponse.status(),
			payload: await browserResponse.json().catch(() => ({})),
		}
		const outcome = validateResponse(response, expectation, context, `UI ${context.row.path}`)
		if (!outcome?.incomplete) await context.assertPositiveState(response)
		return outcome || responseSummary(response)
	}

	async openAccounts(page, context) {
		return this.capture(page, context, () => navigate(page, `${SITE}/web/accounts`))
	}

	async openHr(page, context) {
		return this.capture(page, context, () => navigate(page, `${SITE}/web/hr`))
	}

	async openPurchaseInvoice(page, context) {
		const actual = await this.capture(page, context, () => navigate(
			page,
			`${SITE}/web/accounts/purchase-invoices/${encodeURIComponent(context.real.submittedPurchaseInvoice.name)}`,
		))
		await waitForApp(page, ".purchase-invoice-header")
		return actual
	}

	async openPurchaseInvoiceFromBill(page, context) {
		const url = `${SITE}/web/accounts/purchase-invoices/new?bill_tracking=${encodeURIComponent(context.scenario.bill)}`
		const actual = await this.capture(page, context, () => navigate(page, url))
		await waitForApp(page, ".purchase-invoice-editor__body")
		return actual
	}

	async saveEmptyPurchaseInvoice(page, context) {
		await this.openEditorFromScenario(page, context)
		await this.selectPurchaseOrder(page)
		await page.getByRole("button", { name: "Save options", exact: true }).click()
		const actual = await this.capture(
			page,
			context,
			() => page.getByRole("menuitem", { name: "Save & Submit", exact: true }).click(),
			context.row.uiExpected,
		)
		await page.locator(".p-dialog:visible").waitFor({ state: "visible", timeout: API_TIMEOUT })
		return actual
	}

	async searchEligibleGrns(page, context) {
		await this.openEditorFromScenario(page, context)
		const initialLoad = page.waitForResponse(
			(response) => apiPath(response.url()) === context.row.path,
			{ timeout: API_TIMEOUT },
		)
		await this.selectPurchaseOrder(page)
		await initialLoad
		const input = page.getByRole("textbox", { name: "Search GRNs", exact: true })
		await input.waitFor({ state: "visible", timeout: API_TIMEOUT })
		return this.capture(page, context, () => input.fill(context.unique("UI-GRN")))
	}

	async assertFetchGrnDisabled(page, context) {
		await this.openEditorFromScenario(page, context)
		await this.selectPurchaseOrder(page)
		assert(await page.getByRole("button", { name: "Fetch GRN", exact: true }).isDisabled(), "Fetch GRN is enabled without a GRN")
		return "Fetch GRN disabled for an empty selection"
	}

	async openAndCancelApprove(page, context) {
		let requests = 0
		const listener = (request) => { if (apiPath(request.url()) === context.row.path) requests += 1 }
		page.on("request", listener)
		try {
			await navigate(page, `${SITE}/web/accounts/purchase-invoices/${encodeURIComponent(context.real.draftWorkOrderPurchaseInvoice.name)}`)
			await waitForApp(page, ".purchase-invoice-header")
			await openAction(page, "Approve Invoice")
			const dialog = page.locator(".p-dialog:visible").filter({ hasText: "Approve Invoice" })
			await dialog.waitFor({ state: "visible", timeout: API_TIMEOUT })
			await dialog.getByRole("button", { name: "Cancel", exact: true }).click()
			assert(requests === 0, "Cancelling the Approve dialog called the mutation endpoint")
			return "Approve dialog opened and cancelled without a request"
		} finally {
			page.off("request", listener)
		}
	}

	async openVerificationTab(page, context) {
		await navigate(page, `${SITE}/web/accounts/purchase-invoices/${encodeURIComponent(context.real.draftWorkOrderPurchaseInvoice.name)}`)
		await waitForApp(page, ".purchase-invoice-header")
		await page.getByRole("tab", { name: /^Verification/ }).click()
		await page.locator(".purchase-invoice-verification").waitFor({ state: "visible", timeout: API_TIMEOUT })
		return "Verification tab rendered; closure check is server-owned by the workspace"
	}

	async showErpBill(page, context) {
		await page.addInitScript(() => { window.open = (...args) => { window.__e2eOpenedUrl = args[0]; return null } })
		await navigate(page, `${SITE}/web/accounts/purchase-invoices/${encodeURIComponent(context.real.erpPurchaseInvoice.name)}`)
		await waitForApp(page, ".purchase-invoice-header")
		const actual = await this.capture(page, context, () => openAction(page, "Show ERP Bill"))
		assert(await page.evaluate(() => Boolean(window.__e2eOpenedUrl)), "Show ERP Bill did not call window.open")
		return actual
	}

	async assertErpActionMatchesCapability(page, context) {
		const invoice = context.real.erpEligibleDraftPurchaseInvoice
		const workspace = await context.sessions.accounts.callOk(
			PURCHASE_INVOICE_WORKSPACE,
			{ name: invoice.name },
			"GET",
		)
		assertRecord(workspace, PURCHASE_INVOICE, invoice.name, 0, "ERP-eligible draft workspace")
		assert(assertArray(workspace.items, "ERP-eligible draft items").length, `${invoice.name} has no grouped items`)
		assert(workspace.permissions?.can_create === true, `${invoice.name} lacks Purchase Invoice create permission`)
		const capability = workspace.capabilities?.fetch_expense_head
		assert(typeof capability?.allowed === "boolean", `${invoice.name} omitted the Fetch Expense Head capability`)
		assert(
			capability.allowed === Boolean(workspace.erp_sync_enabled),
			`${invoice.name} Fetch Expense Head capability does not match ERP availability`,
		)
		await navigate(page, `${SITE}/web/accounts/purchase-invoices/${encodeURIComponent(invoice.name)}`)
		await waitForApp(page, ".purchase-invoice-header")
		const rendered = await this.isActionRendered(page, "Fetch Expense Head")
		assert(rendered === capability.allowed, "Fetch Expense Head visibility differs from its workspace capability")
		if (!capability.allowed) return "Fetch Expense Head hidden; workspace capability allowed=false"
		return this.fetchExpenseHeadsWithoutSaving(page, context, invoice.name)
	}

	async fetchExpenseHeadsWithoutSaving(page, context, invoiceName) {
		const verifyNoMutations = await installRealRecordMutationGuard(page, "Expense-head UI verification")
		try {
			const responsePromise = page.waitForResponse(
				(response) => apiPath(response.url()) === context.row.path,
				{ timeout: API_TIMEOUT },
			)
			responsePromise.catch(() => {})
			await openAction(page, "Fetch Expense Head")
			const browserResponse = await responsePromise
			const response = {
				status: browserResponse.status(),
				payload: await browserResponse.json().catch(() => ({})),
			}
			assertSuccess(response, `UI ${context.row.path}`)
			assertArray(response.payload.message, `UI ${context.row.path}`)
			const requestItems = JSON.parse(browserResponse.request().postData() || "{}").items || []
			const sentItems = typeof requestItems === "string" ? JSON.parse(requestItems) : requestItems
			assert(sentItems.length > 0, "Expense-head UI request sent no grouped items")
			assert(response.payload.message.length === sentItems.length, "Expense-head response row count differs from request")
			const sentKeys = new Set(sentItems.map((row) => row.group_key))
			for (const row of response.payload.message) {
				assert(sentKeys.has(row.group_key), `Expense-head response returned unknown group_key ${row.group_key}`)
				assert("expense_head" in row, `Expense-head response row ${row.group_key} has no expense_head field`)
			}
			await waitForApp(page, ".purchase-invoice-editor__body")
			const currentUrl = new URL(page.url())
			assert(currentUrl.pathname.endsWith(`/${encodeURIComponent(invoiceName)}/edit`), "Expense-head action did not open the editor")
			assert(currentUrl.searchParams.get("fetchExpenseHead") === "1", "Expense-head editor route omitted fetchExpenseHead=1")
			const exit = await this.leavePurchaseInvoiceEditor(page, invoiceName)
			return `HTTP 200 from editor; ${exit}`
		} finally {
			await verifyNoMutations()
		}
	}

	async leavePurchaseInvoiceEditor(page, invoiceName) {
		await page.getByRole("button", { name: "Cancel", exact: true }).click()
		const dialog = page.locator(".p-dialog:visible").filter({ hasText: "Discard unsaved changes?" })
		const destination = `${SITE}/web/accounts/purchase-invoices/${encodeURIComponent(invoiceName)}`
		const outcome = await Promise.race([
			dialog.waitFor({ state: "visible", timeout: API_TIMEOUT }).then(() => "discard"),
			page.waitForURL(destination, { timeout: API_TIMEOUT }).then(() => "clean"),
		])
		if (outcome === "discard") {
			await dialog.getByRole("button", { name: "Discard Changes", exact: true }).click()
			await page.waitForURL(destination, { timeout: API_TIMEOUT })
		}
		await waitForApp(page, ".purchase-invoice-header")
		return outcome === "discard" ? "unsaved changes discarded" : "editor exited without unsaved changes"
	}

	async assertErpSubmitActionAvailable(page, context) {
		const invoice = context.real.erpSubmitEligiblePurchaseInvoice
		if (!invoice) return { incomplete: true, actual: ERP_SUBMIT_UNAVAILABLE }
		const eligibility = await getErpSubmitEligibility(context.sessions.accounts, invoice.name)
		assert(eligibility.isDocumentEligible, `${invoice.name} is no longer ERP-submit eligible`)
		assert(eligibility.capability.allowed === true, `${invoice.name} ERP-submit capability is no longer enabled`)
		await navigate(page, `${SITE}/web/accounts/purchase-invoices/${encodeURIComponent(invoice.name)}`)
		await waitForApp(page, ".purchase-invoice-header")
		const rendered = await this.isActionRendered(page, "Submit ERP Bill")
		assert(rendered, "Submit ERP Bill is hidden for a verified eligible invoice")
		return `Submit ERP Bill visible for eligible ${invoice.name}; action was not invoked`
	}

	async isActionRendered(page, action) {
		if (await page.getByRole("button", { name: action, exact: true }).count()) return true
		const more = page.locator(".document-action-strip__more--desktop:visible").first()
		if (!await more.count()) return false
		await more.click()
		const menu = page.locator(".document-action-menu:visible")
		await menu.waitFor({ state: "visible", timeout: API_TIMEOUT })
		const rendered = Boolean(await menu.getByRole("menuitem", { name: action, exact: true }).count())
		await page.keyboard.press("Escape")
		return rendered
	}

	async assertWorkOrderCloseUnavailable(page, context) {
		await navigate(page, `${SITE}/web/accounts/purchase-invoices/${encodeURIComponent(context.real.draftWorkOrderPurchaseInvoice.name)}`)
		await waitForApp(page, ".purchase-invoice-header")
		await page.getByRole("tab", { name: /^Verification/ }).click()
		const buttons = page.locator(".verification-work-order__header button")
		assert(await buttons.count() === 0, "A Work Order close action is visible without configured closing roles")
		return "Work Order close control absent because closing roles are intentionally unconfigured"
	}

	async openBillTracking(page, context) {
		const actual = await this.capture(page, context, () => navigate(
			page,
			`${SITE}/web/hr/bill-tracking/${encodeURIComponent(context.scenario.bill)}`,
		))
		await waitForApp(page, ".bill-tracking-header")
		return actual
	}

	async openBillTrackingEditor(page, context) {
		const actual = await this.capture(page, context, () => navigate(page, `${SITE}/web/hr/bill-tracking/new`))
		await waitForApp(page, ".bill-tracking-editor__body")
		return actual
	}

	async createSubmittedBill(page, context) {
		await navigate(page, `${SITE}/web/hr/bill-tracking/new`)
		await waitForApp(page, ".bill-tracking-editor__body")
		await this.fillBillEditor(page, context, "UI-SUBMIT")
		await page.getByRole("button", { name: "Save options", exact: true }).click()
		const actual = await this.capture(
			page,
			context,
			() => page.getByRole("menuitem", { name: "Save & Submit", exact: true }).click(),
		)
		await page.waitForURL(/\/web\/hr\/bill-tracking\/[^/?#]+$/, { timeout: API_TIMEOUT })
		return actual
	}

	async submitBillAndAssertDeleteHidden(page, context) {
		await navigate(page, `${SITE}/web/hr/bill-tracking/${encodeURIComponent(context.scenario.bill)}`)
		await waitForApp(page, ".bill-tracking-header")
		assert(!await page.getByRole("button", { name: "Delete", exact: true }).count(), "HR User can see Delete")
		const more = page.locator(".document-action-strip__more--desktop:visible").first()
		if (await more.count()) {
			await more.click()
			const menu = page.locator(".document-action-menu:visible")
			await menu.waitFor({ state: "visible", timeout: API_TIMEOUT })
			assert(!await menu.getByRole("menuitem", { name: "Delete", exact: true }).count(), "HR User menu contains Delete")
			await page.keyboard.press("Escape")
		}
		await openAction(page, "Submit")
		const dialog = page.locator(".document-confirmation-shell:visible")
		return this.capture(page, context, () => dialog.getByRole("button", { name: "Submit", exact: true }).click())
	}

	async assignBill(page, context) {
		await this.openBillForAction(page, context)
		await openAction(page, "Assign")
		const dialog = page.locator(".bill-tracking-assign-dialog:visible")
		await selectLink(dialog, "Department", context.fixtures.department)
		await dialog.getByRole("textbox", { name: "Remarks", exact: true }).fill("E2E-AHR API UI assignment")
		return this.capture(page, context, () => dialog.getByRole("button", { name: "Assign", exact: true }).click())
	}

	async acknowledgeBill(page, context) {
		await this.openBillForAction(page, context)
		await openAction(page, "Bill Received")
		const dialog = page.locator(".document-confirmation-shell:visible")
		return this.capture(page, context, () => dialog.getByRole("button", { name: "Bill Received", exact: true }).click())
	}

	async bulkAssignBills(page, context) {
		await navigate(page, `${SITE}/web/hr/bill-tracking`)
		await waitForApp(page, ".common-list-view")
		for (const name of [context.scenario.openBill, context.scenario.cancelledBill]) {
			const row = page.locator(".p-datatable-tbody tr").filter({ hasText: name })
			await row.waitFor({ state: "visible", timeout: API_TIMEOUT })
			await row.locator(".p-checkbox").click()
		}
		await page.getByRole("button", { name: "Assign Selected", exact: true }).click()
		const dialog = page.locator(".bill-tracking-assign-dialog:visible")
		await selectLink(dialog, "Department", context.fixtures.department)
		return this.capture(page, context, () => dialog.getByRole("button", { name: "Assign Selected", exact: true }).click())
	}

	async requestBillCancellation(page, context) {
		await this.openBillForAction(page, context)
		await openAction(page, "Request for Cancel")
		const dialog = page.locator(".document-confirmation-shell:visible")
		return this.capture(page, context, () => dialog.getByRole("button", { name: "Request Cancellation", exact: true }).click())
	}

	async approveBillCancellation(page, context) {
		await this.openBillForAction(page, context)
		await openAction(page, "Approve Cancel Request")
		const dialog = page.locator(".document-confirmation-shell:visible")
		return this.capture(page, context, () => dialog.getByRole("button", { name: "Approve Request", exact: true }).click())
	}

	async cancelBill(page, context) {
		await this.openBillForAction(page, context)
		await openAction(page, "Cancel")
		const dialog = page.locator(".bill-tracking-cancel-dialog:visible")
		await dialog.getByRole("textbox", { name: /Cancellation reason/ }).fill("E2E-AHR API UI verification")
		return this.capture(page, context, () => dialog.getByRole("button", { name: "Cancel Bill", exact: true }).click())
	}

	async showAssignedToMe(page, context) {
		await navigate(page, `${SITE}/web/hr/bill-tracking`)
		await waitForApp(page, ".common-list-view")
		return this.capture(page, context, () => page.getByRole("button", { name: "Assigned to me", exact: true }).click())
	}

	async searchDeliveryPeople(page, context) {
		await navigate(page, `${SITE}/web/hr/bill-tracking/new`)
		await waitForApp(page, ".bill-tracking-editor__body")
		return this.capture(page, context, () => selectLink(page, "Supplier", context.fixtures.supplier))
	}

	async generateReport(page, context) {
		const isAttendance = context.row.report === "attendance"
		const base = isAttendance ? "/web/hr/reports" : "/web/accounts/reports"
		const query = new URLSearchParams({ report: context.row.report })
		if (context.row.report === "sewing-dpr") query.set("supplier", context.real.sewingUnit)
		await navigate(page, `${SITE}${base}?${query}`)
		await waitForApp(page, isAttendance ? ".hr-reports__tabs" : ".accounts-reports__tabs")
		const report = page.locator(".p-tabpanel:visible").first()
		if (context.row.report === "stock-balance") {
			await selectLink(report, "Warehouse", context.real.stockWarehouse)
		}
		if (context.row.report === "cutting-dpr" && context.row.reportMode === "summary") {
			await report.locator(".report-mode button").filter({ hasText: "Summary" }).click()
			await report.getByLabel("From date", { exact: true }).fill(displayDate(context.today))
			await page.keyboard.press("Escape")
			await report.getByLabel("To date", { exact: true }).fill(displayDate(context.today))
			await page.keyboard.press("Escape")
		}
		if (context.row.report === "sewing-dpr" && context.row.reportMode === "summary") {
			await report.getByLabel("DPR Mode", { exact: true }).selectOption("range")
			await report.getByLabel("From Date", { exact: true }).fill(displayDate(context.today))
			await report.getByLabel("To Date", { exact: true }).fill(displayDate(context.today))
		} else if (context.row.report === "sewing-dpr") {
			await report.getByLabel("DPR Date", { exact: true }).fill(displayDate(context.today))
		}
		if (isAttendance) {
			await this.chooseTime(report, "From Time", "Previous Hour")
			await this.chooseTime(report, "To Time", "Next Hour")
		}
		return this.capture(
			page,
			context,
			() => report.getByRole("button", { name: "Generate", exact: true }).click(),
			context.row.uiExpected || context.row.positiveExpected,
		)
	}

	async openEditorFromScenario(page, context) {
		await navigate(
			page,
			`${SITE}/web/accounts/purchase-invoices/new?bill_tracking=${encodeURIComponent(context.scenario.bill)}`,
		)
		await waitForApp(page, ".purchase-invoice-editor__body")
	}

	async chooseTime(root, label, adjustment) {
		const field = root.getByLabel(label, { exact: true })
		await field.click()
		const panelId = await field.getAttribute("aria-controls")
		assert(panelId, `${label} did not open its time picker`)
		const panel = root.page().locator(`[id="${panelId}"]`)
		await panel.getByRole("button", { name: adjustment, exact: true }).click()
		await root.page().keyboard.press("Escape")
		assert(await field.inputValue(), `${label} did not retain a selected time`)
	}

	async selectPurchaseOrder(page) {
		await page.locator("#field-against-value").click()
		await page.getByRole("option", { name: "Purchase Order", exact: true }).click()
	}

	async openBillForAction(page, context) {
		await navigate(page, `${SITE}/web/hr/bill-tracking/${encodeURIComponent(context.scenario.bill)}`)
		await waitForApp(page, ".bill-tracking-header")
	}

	async fillBillEditor(page, context, label) {
		await selectLink(page, "Supplier", context.fixtures.supplier)
		await page.locator("#field-bill_no-value").fill(context.unique(label))
		await page.locator("#field-bill_date-value").fill(displayDate(context.today))
		await page.locator("#field-bill_date-value").press("Tab")
		await page.locator("#field-invoice_value-value").fill("1250")
		await page.locator("#field-received_via-value").click()
		await page.getByRole("option", { name: "HO", exact: true }).click()
	}
}

function apiPath(url) {
	const marker = "/api/method/"
	const pathname = new URL(url).pathname
	return pathname.includes(marker) ? decodeURIComponent(pathname.split(marker)[1]) : ""
}

function displayDate(value) {
	return value.split("-").reverse().join("-")
}

async function isReportListed(row, context, user) {
	const response = await context.sessions[user].call(row.capabilityPath, "GET")
	const label = `${row.capabilityPath} as ${user}`
	assertSuccess(response, label)
	const capabilities = requireKeys(response.payload.message, ["reports"], label)
	return capabilities.reports?.[row.capabilityReport]?.can_read === true
}

function reportExpectation(row, isListed) {
	const capability = `${row.capabilityPath} reports.${row.capabilityReport}`
	if (isListed) return `listed by ${capability}; ${row.positiveExpected}`
	if (row.knownOpen) return `KNOWN-OPEN: omitted by ${capability}; ${row.knownOpen}`
	return `omitted by ${capability}; PermissionError/403`
}

async function verifyReportForUser(row, context, user) {
	const isListed = await isReportListed(row, context, user)
	const expected = reportExpectation(row, isListed)
	const args = (row.positiveArgs || row.args)(context)
	const response = await context.sessions[user].call(row.path, row.httpMethod, args)
	const label = `${row.path} as ${user}`
	if (!isListed && !row.knownOpen) {
		validateResponse(response, "permission", context, label)
		return { result: true, expected, actual: responseSummary(response), status: "PASS", ok: true }
	}
	const outcome = validateResponse(response, row.positiveExpected, context, label)
	if (!isListed) {
		return { result: true, expected, actual: responseSummary(response), status: "KNOWN-OPEN", ok: true }
	}
	return {
		result: true,
		expected,
		actual: outcome?.actual || responseSummary(response),
		status: outcome?.incomplete ? outcome.actual : "PASS",
		ok: !outcome?.incomplete,
	}
}

async function runReportHttpRow(row, base, addResult) {
	const context = new VerificationContext({ ...base, row, mode: "http" })
	await context.prepare()
	for (const user of REPORT_USERS) {
		await addResult(row, "http-report", user, "derived from capabilities", () => (
			verifyReportForUser(row, context, user)
		))
	}
	await addResult(row, "http-positive", "administrator", row.positiveExpected, async () => {
		const args = (row.positiveArgs || row.args)(context)
		const response = await context.sessions.administrator.call(row.path, row.httpMethod, args)
		const outcome = validateResponse(response, row.positiveExpected, context, `${row.path} as administrator`)
		return outcome || responseSummary(response)
	})
}

async function runHttpRow(row, base, addResult) {
	if (row.report) {
		await runReportHttpRow(row, base, addResult)
		return
	}
	const context = new VerificationContext({ ...base, row, mode: "http" })
	try {
		await context.prepare()
		const positiveArgs = (row.positiveArgs || row.args)(context)
		const negativeArgs = (row.negativeArgs || row.args)(context)
		const positiveUsers = [row.positiveUser, ...(row.additionalPositiveUsers || [])].filter(Boolean)
		const runPositive = async (user) => {
			const response = await context.sessions[user].call(row.path, row.httpMethod, positiveArgs)
			const outcome = validateResponse(response, row.positiveExpected, context, `${row.path} as ${user}`)
			if (!outcome?.incomplete) await context.assertPositiveState(response)
			return outcome || responseSummary(response)
		}
		const runNegative = async () => {
			if (!row.negativeUser) return
			const expected = row.negativeExpected
			const httpMethod = row.negativeHttpMethod || row.httpMethod
			const response = await context.sessions[row.negativeUser].call(row.path, httpMethod, negativeArgs)
			validateResponse(response, expected, context, `${row.path} as ${row.negativeUser}`)
			await context.assertRejectedState(expected)
			return responseSummary(response)
		}
		if (row.negativeFirst && row.negativeUser) {
			await addResult(row, "http-negative", row.negativeUser, row.negativeExpected, runNegative)
		}
		for (const user of positiveUsers) {
			await addResult(row, "http-positive", user, row.positiveExpected, () => runPositive(user))
		}
		if (!row.negativeFirst && row.negativeUser) {
			await addResult(row, "http-negative", row.negativeUser, row.negativeExpected, runNegative)
		}
	} catch (error) {
		await addResult(row, "http-setup", "fixture", "scenario prepared", async () => { throw error })
	}
}

async function runUiRow(row, base, addResult) {
	if (!row.uiTrigger) return
	const context = new VerificationContext({ ...base, row, mode: "ui" })
	const user = row.uiUser || row.positiveUser || "accounts"
	let page
	try {
		await context.prepare()
		page = await context.sessions[user].newPage()
		await addResult(
			row,
			"ui",
			user,
			row.uiExpected || row.positiveExpected,
			() => row.uiTrigger(page, context),
		)
	} catch (error) {
		await addResult(row, "ui-setup", user, "scenario prepared", async () => { throw error })
	} finally {
		await page?.close().catch(() => {})
	}
}

async function assertNoFixtureRecords(admin, fixtures) {
	const checks = [
		[PURCHASE_INVOICE, [["supplier", "=", fixtures.supplier]]],
		[BILL_TRACKING, [["supplier", "=", fixtures.supplier]]],
		["Supplier", [["name", "=", fixtures.supplier]]],
		["Department", [["department_name", "=", fixtures.department]]],
		["User", [["name", "in", [fixtures.accounts_user, fixtures.hr_user, fixtures.hr_manager, fixtures.plain_user]]]],
	]
	for (const [doctype, filters] of checks) {
		const rows = await admin.resourceRows(doctype, { fields: ["name"], filters, limit: 20 })
		assert(!rows.length, `${doctype} fixture leftovers remain: ${rows.map((row) => row.name).join(", ")}`)
	}
}

function writeResults(results) {
	mkdirSync(RESULT_DIRECTORY, { recursive: true })
	writeFileSync(RESULT_FILE, `${JSON.stringify(results, null, 2)}\n`)
	console.table(results.map(({ row, path, mode, user, expected, actual, status, ok }) => ({
		row,
		path,
		mode,
		user,
		expected,
		actual,
		status,
		ok,
	})))
	console.log(`Results: ${RESULT_FILE}`)
}

async function loginSessions(browser, fixtures) {
	const [administrator, administratorPassword] = readFileSync(ADMIN_CREDENTIALS, "utf8").trim().split("\n")
	const users = {
		administrator: [administrator.trim(), administratorPassword.trim()],
		accounts: [fixtures.accounts_user, PASSWORD],
		hr: [fixtures.hr_user, PASSWORD],
		hrm: [fixtures.hr_manager, PASSWORD],
		plain: [fixtures.plain_user, PASSWORD],
	}
	const sessions = {}
	for (const [key, [user, password]] of Object.entries(users)) {
		sessions[key] = await FrappeSession.login(browser, user, password)
	}
	sessions.guest = await FrappeSession.guest(browser)
	return sessions
}

async function main() {
	const options = parseOptions()
	const selectedRows = accountsHrApiMatrix.filter((row) => options.row === null || row.row === options.row)
	assert(selectedRows.length, `No matrix row matches ${options.row}`)
	const results = []
	const failures = []
	const ui = new UiDriver(results)
	let browser
	let fixtures
	let sessions = {}
	let real
	let realBefore
	let setupStarted = false

	const addResult = async (row, mode, user, expected, operation) => {
		const result = { row: row.row, path: row.path, mode, user, expected, actual: "", status: "FAIL", ok: false }
		try {
			const outcome = await operation()
			if (outcome?.result) {
				result.expected = outcome.expected
				result.actual = outcome.actual
				result.status = outcome.status
				result.ok = outcome.ok
			} else if (outcome?.incomplete) {
				result.actual = outcome.actual
				result.status = outcome.actual
			} else {
				result.actual = outcome
				result.status = "PASS"
				result.ok = true
			}
		} catch (error) {
			result.actual = sanitizeSensitiveText(error?.message || error)
			failures.push(`Row ${row.row} ${mode} ${user}: ${result.actual}`)
		}
		results.push(result)
	}

	try {
		setupStarted = true
		fixtures = fixtureSetup()
		browser = await chromium.launch({ headless: true })
		sessions = await loginSessions(browser, fixtures)
		real = await discoverRealRecords(sessions, fixtures)
		realBefore = await snapshotRealRecords(sessions.administrator, real)
		const base = { fixtures, real, sessions, ui }
		for (const row of selectedRows) {
			if (options.runHttp) await runHttpRow(row, base, addResult)
			if (options.runUi) await runUiRow(row, base, addResult)
		}
		const fixtureInvoices = await sessions.administrator.resourceRows(PURCHASE_INVOICE, {
			fields: ["name"],
			filters: [["supplier", "=", fixtures.supplier]],
			limit: 20,
		})
		assert(!fixtureInvoices.length, `Fixture Purchase Invoices remain: ${fixtureInvoices.map((row) => row.name).join(", ")}`)
	} catch (error) {
		failures.push(sanitizeSensitiveText(error?.stack || error))
	} finally {
		if (setupStarted) {
			try {
				fixtureTeardown()
			} catch (error) {
				failures.push(`Fixture teardown: ${sanitizeSensitiveText(error?.message || error)}`)
			}
		}
		if (sessions.administrator && fixtures) {
			try {
				await assertNoFixtureRecords(sessions.administrator, fixtures)
				if (realBefore && real) {
					const realAfter = await snapshotRealRecords(sessions.administrator, real)
					assertSnapshotsEqual(realBefore, realAfter)
					console.log("Final guard: zero fixture leftovers; real-record snapshots unchanged")
				}
			} catch (error) {
				failures.push(`Final guard: ${sanitizeSensitiveText(error?.message || error)}`)
			}
		}
		for (const session of Object.values(sessions)) await session.close().catch(() => {})
		await browser?.close().catch(() => {})
		writeResults(results)
	}
	if (failures.length) {
		console.error(`\n${failures.length} failure(s):\n${failures.join("\n")}`)
		process.exitCode = 1
	}
}

main().catch((error) => {
	console.error(sanitizeSensitiveText(error?.stack || error))
	process.exitCode = 1
})
