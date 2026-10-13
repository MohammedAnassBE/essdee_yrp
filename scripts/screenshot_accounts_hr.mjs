#!/usr/bin/env node

import { readdirSync, rmSync, mkdirSync, statSync, writeFileSync } from "node:fs"
import { createRequire } from "node:module"
import { join } from "node:path"
import { inflateSync } from "node:zlib"

import {
	PASSWORD,
	SITE,
	apiMethod,
	assert,
	assertMutationGuardPolicy,
	callMethod,
	fixtureSetup,
	fixtureTeardown,
	installRealRecordMutationGuard,
	login as loginAdministrator,
	loginAs,
	navigate,
	openAction,
	requestArgs,
	resourceList,
	sanitizeSensitiveText,
	selectLink,
	waitForApp,
} from "./verify_accounts_hr_workspace.mjs"

const require = createRequire("/home/anas/.claude/playwright/package.json")
const { chromium } = require("playwright")

const OUTPUT_DIRECTORY = (
	"/tmp/claude-1000/-home-anas-pilot-benches-frappe-16/"
	+ "348c72ab-5d72-4bcf-a023-b3fbf230e45a/scratchpad/screens/accounts_hr"
)
const DESKTOP = { width: 1440, height: 900 }
const MOBILE = { width: 390, height: 844 }
const MOCK_PURCHASE_INVOICE = "E2E-AHR-MOCK-PI"
const MOCK_WORK_ORDER = "E2E-AHR-MOCK-WO"
const PURCHASE_INVOICE_WORKSPACE = (
	"essdee_yrp.accounts.purchase_invoice_workspace.get_purchase_invoice_workspace"
)
const PURCHASE_INVOICE_EDITOR = (
	"essdee_yrp.accounts.purchase_invoice_editor.get_purchase_invoice_editor"
)
const WORK_ORDER_COMMAND = "essdee_yrp.fabric_store.web_workspace.execute_work_order_command"
const BILL_TRACKING_METHOD = "essdee_yrp.hr.web_workspace"
const BILL_TRACKING_ACTIONS = "yrp.yrp.doctype.yrp_bill_tracking.yrp_bill_tracking"
const BILL_TRACKING_OVERRIDE = "essdee_yrp.overrides.bill_tracking"
const DELIVERY_PEOPLE_METHOD = (
	"yrp.yrp.doctype.yrp_vendor_bill_delivery_person.yrp_vendor_bill_delivery_person"
	+ ".get_last_ten_delivery_persons"
)
const MINIMUM_SCREENSHOT_SIZE = 10 * 1024
const MINIMUM_PIXEL_STANDARD_DEVIATION = 5
const PURCHASE_INVOICE_COMMAND = `${PURCHASE_INVOICE_EDITOR.replace(".get_purchase_invoice_editor", "")}.execute_purchase_invoice_command`
const PURCHASE_INVOICE_SAVE = `${PURCHASE_INVOICE_EDITOR.replace(".get_purchase_invoice_editor", "")}.save_purchase_invoice`
const BILL_TRACKING_COMMAND = `${BILL_TRACKING_METHOD}.execute_bill_tracking_command`
const BILL_TRACKING_SAVE = `${BILL_TRACKING_METHOD}.save_bill_tracking`
const SEWING_DPR_METHOD = (
	"essdee_yrp.essdee_yrp.doctype.sd_yrp_sewing_plan.sd_yrp_sewing_plan.get_sewing_plan_dpr_data"
)
const ATTENDANCE_METHOD = (
	"essdee_yrp.essdee_yrp.doctype.sd_yrp_sewing_plan.sd_yrp_sewing_plan.get_worker_strength_report"
)
const FINISHING_REPORTS_METHOD = "essdee_yrp.finishing.web_reports"

function reply(route, message) {
	return route.fulfill({
		status: 200,
		contentType: "application/json",
		body: JSON.stringify({ message }),
	})
}

function replyError(route, message) {
	return route.fulfill({
		status: 417,
		contentType: "application/json",
		body: JSON.stringify({
			exc_type: "ValidationError",
			exc: `frappe.exceptions.ValidationError: ${message}`,
			_server_messages: JSON.stringify([JSON.stringify({ message })]),
		}),
	})
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

async function createSession(browser, signIn) {
	const context = await browser.newContext({ viewport: DESKTOP })
	const page = await context.newPage()
	await signIn(page)
	return { context, page }
}

async function settle(page, selector) {
	await waitForApp(page, selector)
	await page.evaluate(() => document.fonts?.ready)
	await page.waitForTimeout(250)
}

class ScreenshotGallery {
	constructor(directory) {
		this.directory = directory
		this.entries = []
	}

	async capture(page, filename, description) {
		await page.evaluate(() => document.fonts?.ready)
		await page.waitForTimeout(120)
		const buffer = await page.screenshot({ type: "png", animations: "disabled" })
		this.validate(filename, buffer)
		writeFileSync(join(this.directory, filename), buffer)
		this.entries.push({ filename, description, standardDeviation: pixelStandardDeviation(buffer) })
		console.log(`CAPTURE ${filename}`)
	}

	async capturePage(page, filename, description, mobile = false) {
		await page.setViewportSize(DESKTOP)
		await this.capture(page, filename, description)
		if (!mobile) return
		await page.setViewportSize(MOBILE)
		await page.waitForTimeout(180)
		const mobileName = filename.replace(/\.png$/, "-mobile.png")
		await this.capture(page, mobileName, `${description} at 390×844`)
		await page.setViewportSize(DESKTOP)
	}

	validate(filename, buffer) {
		assert(buffer.length > MINIMUM_SCREENSHOT_SIZE, `${filename} is only ${buffer.length} bytes`)
		const standardDeviation = pixelStandardDeviation(buffer)
		assert(
			standardDeviation > MINIMUM_PIXEL_STANDARD_DEVIATION,
			`${filename} is blank or nearly blank (pixel stddev ${standardDeviation.toFixed(2)})`,
		)
	}

	writeIndex() {
		const lines = [...this.entries]
			.sort((left, right) => left.filename.localeCompare(right.filename))
			.map(({ filename, description }) => `${filename} — ${description}`)
		writeFileSync(join(this.directory, "INDEX.txt"), `${lines.join("\n")}\n`)
	}

	verify(expectedNames) {
		const actualNames = readdirSync(this.directory).filter((name) => name.endsWith(".png")).sort()
		assert(JSON.stringify(actualNames) === JSON.stringify([...expectedNames].sort()), [
			"Screenshot set does not match the required names.",
			`Expected: ${JSON.stringify([...expectedNames].sort())}`,
			`Actual: ${JSON.stringify(actualNames)}`,
		].join("\n"))
		for (const name of actualNames) {
			assert(statSync(join(this.directory, name)).size > MINIMUM_SCREENSHOT_SIZE, `${name} is too small`)
		}
	}
}

async function captureListDialogs(gallery, page, prefix, description) {
	await page.getByRole("button", { name: "Filters", exact: true }).click()
	let dialog = page.locator(".list-filter-dialog:visible")
	await dialog.waitFor()
	await gallery.capture(page, `${prefix}-filters.png`, `${description} Filters dialog`)
	await page.keyboard.press("Escape")
	await dialog.waitFor({ state: "hidden" })

	await page.getByRole("button", { name: "Columns", exact: true }).click()
	dialog = page.locator(".p-dialog:visible").filter({ hasText: "Customize Columns" })
	await dialog.waitFor()
	await gallery.capture(page, `${prefix}-customize-columns.png`, `${description} Customize Columns dialog`)
	await dialog.getByRole("button", { name: "Cancel", exact: true }).click()
}

function pixelStandardDeviation(buffer) {
	const image = decodePng(buffer)
	let count = 0
	let mean = 0
	let sumSquares = 0
	for (let offset = 0; offset < image.pixels.length; offset += image.channels * 13) {
		const red = image.pixels[offset]
		const green = image.channels === 1 ? red : image.pixels[offset + 1]
		const blue = image.channels === 1 ? red : image.pixels[offset + 2]
		const alpha = image.channels === 2 ? image.pixels[offset + 1]
			: image.channels === 4 ? image.pixels[offset + 3] : 255
		const luminance = ((0.2126 * red + 0.7152 * green + 0.0722 * blue) * alpha
			+ 255 * (255 - alpha)) / 255
		count += 1
		const difference = luminance - mean
		mean += difference / count
		sumSquares += difference * (luminance - mean)
	}
	return Math.sqrt(sumSquares / Math.max(1, count - 1))
}

function decodePng(buffer) {
	assert(buffer.subarray(0, 8).equals(Buffer.from("89504e470d0a1a0a", "hex")), "Invalid PNG signature")
	let offset = 8
	let header = null
	const compressed = []
	while (offset < buffer.length) {
		const length = buffer.readUInt32BE(offset)
		const type = buffer.toString("ascii", offset + 4, offset + 8)
		const data = buffer.subarray(offset + 8, offset + 8 + length)
		if (type === "IHDR") header = parsePngHeader(data)
		if (type === "IDAT") compressed.push(data)
		if (type === "IEND") break
		offset += length + 12
	}
	assert(header && compressed.length, "PNG has no header or image data")
	return unfilterPng(header, inflateSync(Buffer.concat(compressed)))
}

function parsePngHeader(data) {
	const colorChannels = { 0: 1, 2: 3, 4: 2, 6: 4 }
	const header = {
		width: data.readUInt32BE(0),
		height: data.readUInt32BE(4),
		bitDepth: data[8],
		colorType: data[9],
		interlace: data[12],
	}
	header.channels = colorChannels[header.colorType]
	assert(header.bitDepth === 8 && header.channels && header.interlace === 0, "Unsupported PNG format")
	return header
}

function unfilterPng(header, raw) {
	const stride = header.width * header.channels
	const pixels = Buffer.alloc(stride * header.height)
	for (let row = 0; row < header.height; row += 1) {
		const rawStart = row * (stride + 1)
		const outputStart = row * stride
		const filter = raw[rawStart]
		for (let column = 0; column < stride; column += 1) {
			const value = raw[rawStart + 1 + column]
			const left = column >= header.channels ? pixels[outputStart + column - header.channels] : 0
			const above = row ? pixels[outputStart + column - stride] : 0
			const upperLeft = row && column >= header.channels
				? pixels[outputStart + column - stride - header.channels] : 0
			pixels[outputStart + column] = unfilterByte(filter, value, left, above, upperLeft)
		}
	}
	return { ...header, pixels }
}

function unfilterByte(filter, value, left, above, upperLeft) {
	if (filter === 0) return value
	if (filter === 1) return (value + left) & 255
	if (filter === 2) return (value + above) & 255
	if (filter === 3) return (value + Math.floor((left + above) / 2)) & 255
	if (filter === 4) return (value + paeth(left, above, upperLeft)) & 255
	throw new Error(`Unsupported PNG filter ${filter}`)
}

function paeth(left, above, upperLeft) {
	const prediction = left + above - upperLeft
	const leftDistance = Math.abs(prediction - left)
	const aboveDistance = Math.abs(prediction - above)
	const upperLeftDistance = Math.abs(prediction - upperLeft)
	if (leftDistance <= aboveDistance && leftDistance <= upperLeftDistance) return left
	return aboveDistance <= upperLeftDistance ? above : upperLeft
}

async function findWorkspace(page, rows, predicate, label) {
	for (const row of rows) {
		const workspace = await callMethod(page, PURCHASE_INVOICE_WORKSPACE, { name: row.name })
		if (predicate(workspace)) return { name: row.name, workspace }
	}
	throw new Error(`No ${label} is available for screenshots`)
}

async function discoverPurchaseInvoices(page) {
	const submittedRows = await resourceList(page, "YRP Purchase Invoice", [
		["docstatus", "=", 1], ["against", "=", "YRP Work Order"],
	], ["name", "erp_inv_name", "erp_inv_docstatus"], 20)
	const submitted = await findWorkspace(
		page,
		submittedRows,
		(workspace) => workspace.verification?.length && workspace.grns?.length,
		"submitted Work Order Purchase Invoice with verification and GRNs",
	)
	const draftRows = await resourceList(page, "YRP Purchase Invoice", [
		["docstatus", "=", 0], ["against", "=", "YRP Work Order"], ["approved_by", "is", "not set"],
	], ["name"], 20)
	const draft = await findWorkspace(
		page,
		draftRows,
		(workspace) => workspace.verification?.length,
		"draft Work Order Purchase Invoice with verification",
	)
	const migratedDraftRows = await resourceList(page, "YRP Purchase Invoice", [
		["docstatus", "=", 0], ["against", "=", "Purchase Order"],
	], ["name"], 20)
	const migratedDraft = await findWorkspace(
		page,
		migratedDraftRows,
		(workspace) => workspace.grns?.length && workspace.items?.length,
		"draft migrated Purchase Invoice with GRNs and grouped items",
	)
	const erpRows = await resourceList(page, "YRP Purchase Invoice", [
		["docstatus", "=", 1], ["erp_inv_name", "is", "set"],
	], ["name", "erp_inv_name", "erp_inv_docstatus"], 20)
	assert(erpRows.length, "No submitted Purchase Invoice with an ERP invoice is available")
	return {
		submitted,
		draft,
		migratedDraft,
		erp: erpRows[0],
	}
}

async function createBill(page, fixtures, label, submit) {
	const workspace = await callMethod(page, `${BILL_TRACKING_METHOD}.save_bill_tracking`, {
		values: {
			supplier: fixtures.supplier,
			bill_no: `E2E-AHR-SCREEN-${label}-${Date.now()}`,
			bill_date: localToday(),
			invoice_value: 1250,
			received_date: localToday(),
			received_via: "HO",
			receive_comment: "E2E-AHR screenshot fixture",
			delivery_mob_no: "",
		},
		submit,
	})
	assert(workspace?.record?.name, `Bill fixture ${label} returned no name`)
	return workspace.record.name
}

async function createBillScenarios(hrPage, managerPage, fixtures) {
	const names = {
		draft: await createBill(hrPage, fixtures, "DRAFT", false),
		open: await createBill(hrPage, fixtures, "OPEN", true),
		assigned: await createBill(hrPage, fixtures, "ASSIGNED", true),
		pending: await createBill(hrPage, fixtures, "PENDING", true),
		approved: await createBill(hrPage, fixtures, "APPROVED", true),
		bulkOpen: await createBill(hrPage, fixtures, "BULK-OPEN", true),
		bulkPending: await createBill(hrPage, fixtures, "BULK-PENDING", true),
	}
	await callMethod(hrPage, `${BILL_TRACKING_ACTIONS}.assign_vendor_bill`, {
		name: names.assigned,
		assigned_to: fixtures.department,
		remarks: "E2E-AHR screenshot assignment",
	})
	for (const name of [names.pending, names.approved, names.bulkPending]) {
		await callMethod(hrPage, `${BILL_TRACKING_OVERRIDE}.request_bill_cancellation`, { name })
	}
	await callMethod(managerPage, `${BILL_TRACKING_OVERRIDE}.approve_bill_cancellation`, {
		name: names.approved,
	})
	return names
}

async function captureLaunchers(gallery, administrator) {
	await navigate(administrator, `${SITE}/web/`)
	await settle(administrator, ".department-card-link")
	assert(await administrator.locator(".department-card-link").count() === 13, "Launcher does not show 13 departments")
	await gallery.capturePage(
		administrator,
		"01-administrator-13-departments.png",
		"Administrator launcher with all 13 departments",
		true,
	)
	await navigate(administrator, `${SITE}/web/accounts`)
	await settle(administrator, ".workspace-launcher__card")
	await gallery.capturePage(administrator, "02-accounts-launcher.png", "Accounts workspace launcher", true)
}

async function capturePurchaseInvoicePages(gallery, page, records) {
	await navigate(page, `${SITE}/web/accounts/purchase-invoices`)
	await settle(page, ".common-list-view")
	await gallery.capturePage(page, "03-accounts-purchase-invoice-list.png", "Purchase Invoice list", true)
	await captureListDialogs(gallery, page, "03a-dialog-pi-list", "Purchase Invoice list")
	await navigate(page, `${SITE}/web/accounts/purchase-invoices/${encodeURIComponent(records.submitted.name)}`)
	await settle(page, ".purchase-invoice-header")
	await gallery.capture(page, "04-accounts-purchase-invoice-submitted-details.png", "Submitted Purchase Invoice details")
	for (const [tab, filename, description] of [
		["Items", "05-accounts-purchase-invoice-items-tab.png", "Submitted Purchase Invoice grouped items"],
		["GRNs", "06-accounts-purchase-invoice-grns-tab.png", "Submitted Purchase Invoice linked GRNs"],
		["Verification", "07-accounts-purchase-invoice-verification-tab.png", "Work Order verification matrix"],
	]) {
		await page.getByRole("tab", { name: new RegExp(`^${tab}`) }).click()
		await page.waitForTimeout(180)
		await gallery.capture(page, filename, description)
	}
	await navigate(page, `${SITE}/web/accounts/purchase-invoices/${encodeURIComponent(records.draft.name)}`)
	await settle(page, ".purchase-invoice-header")
	await gallery.capture(page, "08-accounts-purchase-invoice-draft-wo.png", "Draft Work Order Purchase Invoice")
}

async function capturePurchaseInvoiceDialogs(gallery, pages, records) {
	const accounts = pages.accounts
	const administrator = pages.administrator
	await navigate(accounts, `${SITE}/web/accounts/purchase-invoices/${encodeURIComponent(records.draft.name)}`)
	await settle(accounts, ".purchase-invoice-header")
	await openAction(accounts, "Approve Invoice")
	await accounts.locator(".purchase-invoice-approve-dialog:visible").waitFor()
	await gallery.capture(accounts, "09-dialog-pi-approve-invoice.png", "Approve Invoice comments dialog")
	await accounts.getByRole("button", { name: "Cancel", exact: true }).click()
	await captureWorkOrderCloseMock(gallery, administrator, records.draft)

	await navigate(accounts, `${SITE}/web/accounts/purchase-invoices/${encodeURIComponent(records.draft.name)}`)
	await settle(accounts, ".purchase-invoice-header")
	await openAction(accounts, "Submit")
	await accounts.locator(".document-confirmation-shell:visible").waitFor()
	await gallery.capture(accounts, "11-dialog-pi-submit-confirm.png", "Purchase Invoice submit confirmation")
	await accounts.getByRole("button", { name: "Keep Document", exact: true }).click()

	await captureCancelWithoutErpMock(gallery, administrator, records.submitted)

	await navigate(administrator, `${SITE}/web/accounts/purchase-invoices/${encodeURIComponent(records.erp.name)}`)
	await settle(administrator, ".purchase-invoice-header")
	await openAction(administrator, "Cancel")
	const erpCancel = administrator.locator(".purchase-invoice-cancel-dialog:visible")
	await erpCancel.getByText("Cancel without cancelling ERP invoice", { exact: true }).waitFor()
	await gallery.capture(
		administrator,
		"13-dialog-pi-cancel-with-erp-option.png",
		"Purchase Invoice cancellation with ERP invoice option",
	)
	await administrator.keyboard.press("Escape")

	await navigate(administrator, `${SITE}/web/accounts/purchase-invoices/${encodeURIComponent(records.draft.name)}`)
	await settle(administrator, ".purchase-invoice-header")
	await openAction(administrator, "Delete")
	await administrator.locator(".document-confirmation-shell:visible").waitFor()
	await gallery.capture(administrator, "14-dialog-pi-delete-confirm.png", "Purchase Invoice delete confirmation")
	await administrator.getByRole("button", { name: "Keep Document", exact: true }).click()
	await captureSubmitErpMock(gallery, administrator, records.erp.name)
	await capturePurchaseInvoiceActionErrorMock(gallery, accounts, records.draft)
	await captureRelatedGrn(gallery, administrator, records.submitted.name)
}

async function captureCancelWithoutErpMock(gallery, page, submitted) {
	const workspace = structuredClone(submitted.workspace)
	workspace.record.erp_inv_name = ""
	workspace.details = (workspace.details || []).filter((field) => field.fieldname !== "erp_inv_name")
	const handler = async (route) => apiMethod(route.request()) === PURCHASE_INVOICE_WORKSPACE
		? reply(route, workspace) : route.fallback()
	await page.route("**/api/method/**", handler)
	try {
		await navigate(page, `${SITE}/web/accounts/purchase-invoices/${encodeURIComponent(submitted.name)}`)
		await settle(page, ".purchase-invoice-header")
		await openAction(page, "Cancel")
		const dialog = page.locator(".purchase-invoice-cancel-dialog:visible")
		await dialog.waitFor()
		assert(!await dialog.getByText("Cancel without cancelling ERP invoice", { exact: true }).count(), (
			"Generic cancel dialog unexpectedly shows the ERP cancellation option"
		))
		await gallery.capture(page, "12-dialog-pi-cancel-mock.png", "Mocked Purchase Invoice cancel dialog")
		await page.keyboard.press("Escape")
	} finally {
		await page.unroute("**/api/method/**", handler)
	}
}

async function chooseWorkOrderCloseReason(page, dialog) {
	const field = dialog.locator("label").filter({ hasText: "Close reason *" })
	await field.locator(".p-select").click()
	await page.getByRole("option", { name: "Order completed", exact: true }).click()
}

function mockedDraftWorkspace(draft) {
	const source = draft.workspace
	const verification = source.verification?.[0]
	assert(source.record && verification, "Draft invoice has no record or verification data")
	return {
		...structuredClone(source),
		record: {
			...source.record,
			name: MOCK_PURCHASE_INVOICE,
			bill_no: "E2E-AHR-MOCK-BILL",
			modified: "2026-10-12 10:00:00.000000",
		},
		details: [],
		items: [],
		grns: [],
		verification: [{ ...structuredClone(verification), work_order: MOCK_WORK_ORDER, bills: [] }],
		debit_summary: [],
		approvals: [],
		work_orders: [{
			name: MOCK_WORK_ORDER,
			open_status: "Open",
			modified: "2026-10-12 10:00:00.000000",
			expected_delivery_date: localToday(),
			close_mode: "close",
		}],
		capabilities: {
			...source.capabilities,
			submit: { allowed: true, label: "Submit", reason: "" },
		},
		print_formats: [],
		erp_sync_enabled: false,
	}
}

async function captureWorkOrderCloseMock(gallery, page, draft) {
	const workspace = mockedDraftWorkspace(draft)
	const handler = async (route) => {
		const method = apiMethod(route.request())
		const args = requestArgs(route.request())
		if (method === PURCHASE_INVOICE_WORKSPACE) {
			assert(args.name === MOCK_PURCHASE_INVOICE, `Unexpected mocked workspace request for ${args.name}`)
			return reply(route, workspace)
		}
		if (method === WORK_ORDER_COMMAND && requestArgs(route.request()).command === "get_close_context") {
			assert(args.name === MOCK_WORK_ORDER, `Unexpected mocked Work Order context for ${args.name}`)
			return reply(route, {
				reason_options: ["Order completed", "Others"],
				can_create_debit: true,
				can_approve_debit: false,
				debits: [],
			})
		}
		if (method === WORK_ORDER_COMMAND && requestArgs(route.request()).command === "close") {
			assert(args.name === MOCK_WORK_ORDER, `Unexpected mocked Work Order close for ${args.name}`)
			return replyError(route, "Mocked Work Order close failure")
		}
		return route.fallback()
	}
	await page.route("**/api/method/**", handler)
	try {
		await navigate(page, `${SITE}/web/accounts/purchase-invoices/${MOCK_PURCHASE_INVOICE}`)
		await settle(page, ".purchase-invoice-header")
		await page.getByRole("tab", { name: /^Verification/ }).click()
		const section = page.locator(".verification-work-order").filter({ hasText: MOCK_WORK_ORDER })
		await section.getByRole("button", { name: "Close", exact: true }).click()
		const dialog = page.locator(".work-order-action-panel:visible")
		await dialog.getByText("Close reason *", { exact: true }).waitFor()
		await gallery.capture(page, "10-dialog-pi-work-order-close-mock.png", "Mocked Work Order close panel")
		await chooseWorkOrderCloseReason(page, dialog)
		await dialog.getByRole("button", { name: "Cancel", exact: true }).click()
		const discard = page.locator(".p-dialog:visible").filter({ hasText: "Discard action changes?" })
		await discard.waitFor()
		await gallery.capture(
			page,
			"10a-dialog-pi-work-order-close-discard-mock.png",
			"Mocked Work Order close discard confirmation",
		)
		await discard.getByRole("button", { name: "Keep Editing", exact: true }).click()
		await dialog.getByRole("button", { name: "Close Work Order", exact: true }).click()
		const error = page.locator(".document-error-dialog:visible")
		await error.getByText("Mocked Work Order close failure", { exact: true }).waitFor()
		await gallery.capture(
			page,
			"10b-dialog-pi-work-order-close-error-mock.png",
			"Mocked Work Order close error dialog",
		)
		await error.getByRole("button", { name: "OK", exact: true }).click()
		await dialog.getByRole("button", { name: "Cancel", exact: true }).click()
		await discard.getByRole("button", { name: "Discard Changes", exact: true }).click()
	} finally {
		await page.unroute("**/api/method/**", handler)
	}
}

async function captureSubmitErpMock(gallery, page, name) {
	const workspace = await callMethod(page, PURCHASE_INVOICE_WORKSPACE, { name })
	workspace.erp_sync_enabled = true
	workspace.capabilities.submit_erp_bill = { allowed: true, label: "Submit ERP Bill", reason: "" }
	const handler = async (route) => apiMethod(route.request()) === PURCHASE_INVOICE_WORKSPACE
		? reply(route, workspace) : route.fallback()
	await page.route("**/api/method/**", handler)
	try {
		await navigate(page, `${SITE}/web/accounts/purchase-invoices/${encodeURIComponent(name)}`)
		await settle(page, ".purchase-invoice-header")
		await openAction(page, "Submit ERP Bill")
		await page.locator(".document-confirmation-shell:visible").waitFor()
		await gallery.capture(page, "15-dialog-pi-submit-erp-bill-mock.png", "Mocked Submit ERP Bill confirmation")
		await page.getByRole("button", { name: "Keep Document", exact: true }).click()
	} finally {
		await page.unroute("**/api/method/**", handler)
	}
}

async function capturePurchaseInvoiceActionErrorMock(gallery, page, draft) {
	const workspace = mockedDraftWorkspace(draft)
	const handler = async (route) => {
		const method = apiMethod(route.request())
		const args = requestArgs(route.request())
		if (method === PURCHASE_INVOICE_WORKSPACE) {
			assert(args.name === MOCK_PURCHASE_INVOICE, `Unexpected mocked workspace request for ${args.name}`)
			return reply(route, workspace)
		}
		if (method === PURCHASE_INVOICE_COMMAND) {
			assert(args.name === MOCK_PURCHASE_INVOICE, `Unexpected mocked Purchase Invoice action for ${args.name}`)
			assert(args.command === "submit", `Unexpected mocked Purchase Invoice command ${args.command}`)
			return replyError(route, "Mocked Purchase Invoice submit failure")
		}
		return route.fallback()
	}
	await page.route("**/api/method/**", handler)
	try {
		await navigate(page, `${SITE}/web/accounts/purchase-invoices/${MOCK_PURCHASE_INVOICE}`)
		await settle(page, ".purchase-invoice-header")
		await openAction(page, "Submit")
		const confirmation = page.locator(".document-confirmation-shell:visible")
		await confirmation.getByRole("button", { name: "Submit", exact: true }).click()
		const error = page.locator(".document-error-dialog:visible")
		await error.getByText("Mocked Purchase Invoice submit failure", { exact: true }).waitFor()
		await gallery.capture(
			page,
			"15a-dialog-pi-action-error-mock.png",
			"Mocked Purchase Invoice action error dialog",
		)
		await error.getByRole("button", { name: "OK", exact: true }).click()
	} finally {
		await page.unroute("**/api/method/**", handler)
	}
}

async function captureRelatedGrn(gallery, page, name) {
	await navigate(page, `${SITE}/web/accounts/purchase-invoices/${encodeURIComponent(name)}`)
	await settle(page, ".purchase-invoice-header")
	await page.getByRole("tab", { name: /^GRNs/ }).click()
	await page.locator(".purchase-invoice-link").first().click()
	const dialog = page.locator(".related-document-workspace-dialog:visible")
	await dialog.waitFor({ state: "visible", timeout: 30_000 })
	await dialog.locator(".goods-received-note-workspace").waitFor({ state: "visible", timeout: 30_000 })
	await dialog.getByRole("tab", { name: "Overview", exact: true }).waitFor({ state: "visible", timeout: 30_000 })
	await gallery.capture(page, "16-dialog-pi-grn-related-document.png", "Related Goods Received Note workspace dialog")
	await dialog.getByRole("button", { name: "Close workspace", exact: true }).click()
}

function mockedPurchaseInvoiceEditor(fixtures) {
	return {
		values: {
			supplier: fixtures.supplier,
			against: "Purchase Order",
			posting_date: localToday(),
			due_date: localToday(),
			bill_no: "E2E-AHR-SCREEN-MOCK",
			billing_supplier: fixtures.supplier,
			bill_date: localToday(),
			eligibility_for_itc: "All Other ITC",
			debit_type: "",
			debit_no: "",
			debit_value: 0,
			remarks: "",
			bill_tracking: "",
		},
		schema: {},
		grns: [],
		items: [],
		modified: "2026-10-12 10:00:00.000000",
		docstatus: 0,
		is_rate_only: false,
		erp_sync_enabled: false,
		permissions: { can_submit: true },
	}
}

function mockedFetchedGrns() {
	return {
		additional_field_values: {
			essdee_rate_table_source: "yrp_grn_v1",
			essdee_items: [
				{ group_key: "E2E-AHR-GROUP-1", item: "Cotton Jersey", lot: "LOT-A", qty: 24, uom: "Kg", source_rate: 245, rate: 250, tax: "GST 5", tax_rate: 5, amount: 6000 },
				{ group_key: "E2E-AHR-GROUP-2", item: "Rib Fabric", lot: "LOT-B", qty: 12, uom: "Kg", source_rate: 180, rate: 185, tax: "GST 5", tax_rate: 5, amount: 2220 },
			],
		},
		tax_rates: { "GST 5": 5 },
	}
}

async function capturePurchaseInvoiceEditors(gallery, page, fixtures, records, billName) {
	await navigate(page, `${SITE}/web/accounts/purchase-invoices/new`)
	await settle(page, ".purchase-invoice-editor__body")
	await gallery.capture(page, "17-accounts-purchase-invoice-editor-new.png", "New Purchase Invoice editor")
	await navigate(
		page,
		`${SITE}/web/accounts/purchase-invoices/new?bill_tracking=${encodeURIComponent(billName)}`,
	)
	await settle(page, ".purchase-invoice-editor__body")
	await gallery.capture(
		page,
		"18-accounts-purchase-invoice-editor-from-bill-tracking.png",
		"Purchase Invoice editor prefilled from Bill Tracking",
	)
	await navigate(page, `${SITE}/web/accounts/purchase-invoices/${encodeURIComponent(records.migratedDraft.name)}/edit`)
	await settle(page, ".purchase-invoice-editor__body")
	await page.locator(".purchase-invoice-editor__grn-row").scrollIntoViewIfNeeded()
	await gallery.capture(page, "19-accounts-purchase-invoice-editor-grn-picker.png", "Purchase Invoice GRN picker")
	await captureFetchedItemsMock(gallery, page, fixtures)
	await captureMigratedRefetch(gallery, page, records.migratedDraft.name)
	await capturePurchaseInvoiceDiscard(gallery, page)
	await capturePurchaseInvoiceEditorErrorMock(gallery, page, records.migratedDraft.name)
}

async function captureFetchedItemsMock(gallery, page, fixtures) {
	const editor = mockedPurchaseInvoiceEditor(fixtures)
	const eligibleGrn = {
		name: "E2E-AHR-GRN-001",
		posting_date: localToday(),
		against_id: "E2E-AHR-PO-001",
		supplier_document_no: "GRN-SCREEN",
		total: 8220,
	}
	const handler = async (route) => {
		const method = apiMethod(route.request())
		if (method === PURCHASE_INVOICE_EDITOR) return reply(route, editor)
		if (method.endsWith("get_eligible_grns")) return reply(route, [eligibleGrn])
		if (method.endsWith("fetch_grn_details")) return reply(route, mockedFetchedGrns())
		return route.fallback()
	}
	await page.route("**/api/method/**", handler)
	try {
		await navigate(page, `${SITE}/web/accounts/purchase-invoices/E2E-AHR-MOCK/edit`)
		await settle(page, ".purchase-invoice-editor__body")
		const input = page.locator("input[placeholder='Search GRN, order or supplier document…']")
		await input.fill("E2E-AHR")
		await page.getByRole("option", { name: /E2E-AHR-GRN-001/ }).click()
		await page.getByRole("button", { name: "Fetch GRN", exact: true }).click()
		const items = page.locator(".purchase-invoice-editor__items")
		await items.getByText("Grouped Items (2)", { exact: true }).waitFor()
		await items.scrollIntoViewIfNeeded()
		await gallery.capture(
			page,
			"20-accounts-purchase-invoice-editor-fetched-items-mock.png",
			"Mocked fetched GRNs with grouped items and totals",
		)
	} finally {
		await page.unroute("**/api/method/**", handler)
	}
}

async function captureMigratedRefetch(gallery, page, name) {
	await navigate(page, `${SITE}/web/accounts/purchase-invoices/${encodeURIComponent(name)}/edit`)
	await settle(page, ".purchase-invoice-editor__body")
	await page.getByRole("button", { name: "Fetch GRN", exact: true }).click()
	const dialog = page.locator(".document-confirmation-shell:visible")
	await dialog.getByText("Fetching GRNs replaces the migrated rows. Continue?", { exact: true }).waitFor()
	await gallery.capture(page, "21-dialog-pi-refetch-migrated-confirm.png", "Migrated-row GRN refetch confirmation")
	await dialog.getByRole("button", { name: "Keep Rows", exact: true }).click()
}

async function capturePurchaseInvoiceDiscard(gallery, page) {
	await navigate(page, `${SITE}/web/accounts/purchase-invoices/new`)
	await settle(page, ".purchase-invoice-editor__body")
	await page.locator("#field-remarks-value").fill("E2E-AHR unsaved screenshot change")
	await page.getByRole("button", { name: "Cancel", exact: true }).click()
	const dialog = page.locator(".document-confirmation-shell:visible")
	await dialog.getByText("Your unsaved Purchase Invoice changes will be lost.", { exact: true }).waitFor()
	await gallery.capture(page, "22-dialog-pi-editor-discard-changes.png", "Purchase Invoice unsaved-changes dialog")
	await dialog.getByRole("button", { name: "Discard Changes", exact: true }).click()
}

async function capturePurchaseInvoiceEditorErrorMock(gallery, page, name) {
	await navigate(page, `${SITE}/web/accounts/purchase-invoices/${encodeURIComponent(name)}/edit`)
	await settle(page, ".purchase-invoice-editor__body")
	const remarks = page.locator("#field-remarks-value")
	await remarks.fill(`${await remarks.inputValue()} E2E-AHR mocked save error`.trim())
	const handler = async (route) => apiMethod(route.request()) === PURCHASE_INVOICE_SAVE
		? replyError(route, "Mocked Purchase Invoice editor failure") : route.fallback()
	await page.route("**/api/method/**", handler)
	try {
		await page.getByRole("button", { name: "Save", exact: true }).click()
		const error = page.locator(".document-error-dialog:visible")
		await error.getByText("Mocked Purchase Invoice editor failure", { exact: true }).waitFor()
		await gallery.capture(
			page,
			"22a-dialog-pi-editor-error-mock.png",
			"Mocked Purchase Invoice editor error dialog",
		)
		await error.getByRole("button", { name: "OK", exact: true }).click()
	} finally {
		await page.unroute("**/api/method/**", handler)
	}
	await page.getByRole("button", { name: "Cancel", exact: true }).click()
	await page.locator(".document-confirmation-shell:visible")
		.getByRole("button", { name: "Discard Changes", exact: true }).click()
}

async function captureAccountsReports(gallery, page) {
	const reports = [
		["stock-balance", "23-accounts-reports-stock-balance.png", "Stock Balance report", ".accounts-reports__tabs", true],
		["cutting-dpr", "24-accounts-reports-cutting-dpr.png", "Cutting daily production report", ".accounts-reports__tabs", false],
		["sewing-dpr", "25-accounts-reports-sewing-dpr-no-unit.png", "Sewing DPR without a selected unit", ".accounts-sewing-dpr", false],
		["finishing-dispatch", "27-accounts-reports-finishing-dispatch.png", "Finishing dispatch report", "[data-finishing-report='dispatch-report']", false],
		["ironing-dpr", "28-accounts-reports-ironing-dpr.png", "Finishing ironing DPR", "[data-finishing-report='ironing-dpr']", false],
	]
	for (const [report, filename, description, selector, mobile] of reports) {
		await navigate(page, `${SITE}/web/accounts/reports?report=${report}`)
		await settle(page, selector)
		await gallery.capturePage(page, filename, description, mobile)
	}
	const units = await resourceList(page, "Supplier", [
		["is_company_location", "=", 1], ["disabled", "=", 0],
	], ["name"], 1)
	assert(units.length, "No enabled Sewing Unit is available")
	await navigate(
		page,
		`${SITE}/web/accounts/reports?report=sewing-dpr&supplier=${encodeURIComponent(units[0].name)}`,
	)
	await settle(page, ".accounts-sewing-dpr")
	await page.locator(".accounts-sewing-dpr").getByRole("button", { name: "Generate", exact: true }).waitFor()
	await gallery.capture(page, "26-accounts-reports-sewing-dpr-with-unit.png", "Sewing DPR with a selected unit")
	await captureAccountsReportErrors(gallery, page, units[0].name)
}

async function captureReportErrorMock(gallery, page, options) {
	await navigate(page, options.url)
	await settle(page, options.selector)
	const handler = async (route) => apiMethod(route.request()) === options.method
		? replyError(route, options.message) : route.fallback()
	await page.route("**/api/method/**", handler)
	try {
		if (options.prepare) await options.prepare()
		await page.getByRole("button", { name: "Generate", exact: true }).click()
		const dialog = page.locator(".document-error-dialog:visible")
		await dialog.getByText(options.message, { exact: true }).waitFor()
		await gallery.capture(page, options.filename, options.description)
		await dialog.getByRole("button", { name: "OK", exact: true }).click()
	} finally {
		await page.unroute("**/api/method/**", handler)
	}
}

async function captureAccountsReportErrors(gallery, page, sewingUnit) {
	const base = `${SITE}/web/accounts/reports?report=`
	await captureReportErrorMock(gallery, page, {
		url: `${base}sewing-dpr&supplier=${encodeURIComponent(sewingUnit)}`,
		selector: ".accounts-sewing-dpr",
		method: SEWING_DPR_METHOD,
		message: "Mocked Sewing DPR failure",
		filename: "25a-dialog-accounts-sewing-dpr-error-mock.png",
		description: "Mocked Sewing DPR error dialog",
		prepare: () => page.getByLabel("DPR Date", { exact: true }).fill(displayDate(localToday())),
	})
	for (const report of [
		["finishing-dispatch", "[data-finishing-report='dispatch-report']", "get_dispatch_report", "Dispatch Report"],
		["ironing-dpr", "[data-finishing-report='ironing-dpr']", "get_ironing_dpr", "Ironing DPR"],
	]) {
		const [routeName, selector, methodName, label] = report
		await captureReportErrorMock(gallery, page, {
			url: `${base}${routeName}`,
			selector,
			method: `${FINISHING_REPORTS_METHOD}.${methodName}`,
			message: `Mocked ${label} failure`,
			filename: `${routeName === "finishing-dispatch" ? "27a" : "28a"}-dialog-accounts-${routeName}-error-mock.png`,
			description: `Mocked ${label} error dialog`,
		})
	}
}

function displayDate(value) {
	const [year, month, day] = value.split("-")
	return `${day}-${month}-${year}`
}

async function captureHrPages(gallery, pages, bills) {
	const administrator = pages.administrator
	const hr = pages.hr
	await navigate(administrator, `${SITE}/web/hr`)
	await settle(administrator, ".workspace-launcher__card")
	await gallery.capturePage(administrator, "30-hr-launcher.png", "HR workspace launcher", true)
	await navigate(administrator, `${SITE}/web/hr/bill-tracking`)
	await settle(administrator, ".common-list-view")
	await gallery.capture(administrator, "31-hr-bill-tracking-list.png", "Bill Tracking list")
	await captureListDialogs(gallery, administrator, "31a-dialog-bt-list", "Bill Tracking list")

	await navigate(hr, `${SITE}/web/hr/bill-tracking`)
	await settle(hr, ".common-list-view")
	await hr.getByRole("button", { name: "Assigned to me", exact: true }).click()
	await hr.locator(".p-datatable-tbody tr").filter({ hasText: bills.assigned }).waitFor({ timeout: 30_000 })
	await gallery.capture(hr, "32-hr-bill-tracking-list-assigned-to-me.png", "Bill Tracking assigned-to-me filter")

	await navigate(administrator, `${SITE}/web/hr/bill-tracking/${encodeURIComponent(bills.assigned)}`)
	await settle(administrator, ".bill-tracking-header")
	await gallery.capture(administrator, "33-hr-bill-tracking-record-details.png", "Bill Tracking record details")
	await administrator.getByRole("tab", { name: /^History/ }).click()
	await administrator.locator(".bill-tracking-history__table").waitFor()
	await gallery.capture(administrator, "34-hr-bill-tracking-history-tab.png", "Bill Tracking history")
}

async function captureHrDialogs(gallery, pages, fixtures, bills) {
	const hr = pages.hr
	const manager = pages.manager
	await openBillAction(hr, bills.open, "Assign")
	await hr.locator(".bill-tracking-assign-dialog:visible").waitFor()
	await gallery.capture(hr, "35-dialog-bt-assign.png", "Bill Tracking assignment dialog")
	await hr.getByRole("button", { name: "Cancel", exact: true }).click()
	await captureBulkAssign(gallery, hr, fixtures, bills)
	await openBillAction(hr, bills.assigned, "Bill Received")
	await gallery.capture(hr, "38-dialog-bt-bill-received-confirm.png", "Bill received confirmation")
	await hr.getByRole("button", { name: "Keep", exact: true }).click()
	await openBillAction(hr, bills.open, "Request for Cancel")
	await gallery.capture(hr, "39-dialog-bt-request-cancel-confirm.png", "Bill cancellation request confirmation")
	await hr.getByRole("button", { name: "Keep", exact: true }).click()
	await openBillAction(manager, bills.pending, "Approve Cancel Request")
	await gallery.capture(manager, "40-dialog-bt-approve-cancel-confirm.png", "Bill cancellation approval confirmation")
	await manager.getByRole("button", { name: "Keep", exact: true }).click()
	await openBillAction(hr, bills.approved, "Cancel")
	await hr.locator(".bill-tracking-cancel-dialog:visible").waitFor()
	await gallery.capture(hr, "41-dialog-bt-cancel-reason.png", "Bill Tracking cancellation reason dialog")
	await hr.getByRole("button", { name: "Keep Bill", exact: true }).click()
	await captureBillTrackingDocumentDialogs(gallery, hr, pages.administrator, bills.draft)
}

async function captureBillTrackingDocumentDialogs(gallery, hrPage, administrator, name) {
	await openBillAction(hrPage, name, "Submit")
	await gallery.capture(hrPage, "41a-dialog-bt-submit-confirm.png", "Bill Tracking submit confirmation")
	await hrPage.getByRole("button", { name: "Keep", exact: true }).click()
	await captureBillTrackingActionErrorMock(gallery, hrPage, name)
	await openBillAction(administrator, name, "Delete")
	await gallery.capture(administrator, "41b-dialog-bt-delete-confirm.png", "Bill Tracking delete confirmation")
	await administrator.getByRole("button", { name: "Keep", exact: true }).click()
}

async function captureBillTrackingActionErrorMock(gallery, page, name) {
	const handler = async (route) => apiMethod(route.request()) === BILL_TRACKING_COMMAND
		? replyError(route, "Mocked Bill Tracking submit failure") : route.fallback()
	await page.route("**/api/method/**", handler)
	try {
		await openBillAction(page, name, "Submit")
		const confirmation = page.locator(".document-confirmation-shell:visible")
		await confirmation.getByRole("button", { name: "Submit", exact: true }).click()
		const error = page.locator(".document-error-dialog:visible")
		await error.getByText("Mocked Bill Tracking submit failure", { exact: true }).waitFor()
		await gallery.capture(
			page,
			"41c-dialog-bt-action-error-mock.png",
			"Mocked Bill Tracking action error dialog",
		)
		await error.getByRole("button", { name: "OK", exact: true }).click()
	} finally {
		await page.unroute("**/api/method/**", handler)
	}
}

async function openBillAction(page, name, action) {
	await navigate(page, `${SITE}/web/hr/bill-tracking/${encodeURIComponent(name)}`)
	await settle(page, ".bill-tracking-header")
	await openAction(page, action)
	await page.locator(".p-dialog:visible").waitFor({ state: "visible", timeout: 30_000 })
}

async function selectBillRows(page, names) {
	for (const name of names) {
		const row = page.locator(".p-datatable-tbody tr").filter({ hasText: name })
		await row.waitFor({ state: "visible", timeout: 30_000 })
		const checkbox = row.locator(".p-checkbox")
		if ((await checkbox.getAttribute("data-p-checked")) !== "true") await checkbox.click()
	}
}

async function captureBulkAssign(gallery, page, fixtures, bills) {
	await navigate(page, `${SITE}/web/hr/bill-tracking`)
	await settle(page, ".common-list-view")
	await selectBillRows(page, [bills.bulkOpen, bills.bulkPending])
	await page.getByRole("button", { name: "Assign Selected", exact: true }).click()
	let dialog = page.locator(".bill-tracking-assign-dialog:visible")
	await dialog.waitFor()
	await gallery.capture(page, "36-dialog-bt-bulk-assign.png", "Bulk Bill Tracking assignment dialog")
	await dialog.getByRole("button", { name: "Cancel", exact: true }).click()
	await dialog.waitFor({ state: "hidden" })
	await page.locator(".common-list-view").getByRole("button", { name: "Assign Selected", exact: true }).click()
	dialog = page.locator(".bill-tracking-assign-dialog:visible")
	await selectLink(dialog, "Department", fixtures.department)
	await dialog.getByRole("button", { name: "Assign Selected", exact: true }).click()
	await page.getByText(/Assigned 1 bill\. Skipped 1:/).waitFor({ timeout: 30_000 })
	await gallery.capture(page, "37-dialog-bt-bulk-assign-summary.png", "Bulk assignment partial-success summary")
	await captureBulkAssignErrorMock(gallery, page, fixtures, bills.open)
}

async function captureBulkAssignErrorMock(gallery, page, fixtures, name) {
	await navigate(page, `${SITE}/web/hr/bill-tracking`)
	await settle(page, ".common-list-view")
	await selectBillRows(page, [name])
	await page.getByRole("button", { name: "Assign Selected", exact: true }).click()
	const assignment = page.locator(".bill-tracking-assign-dialog:visible")
	await selectLink(assignment, "Department", fixtures.department)
	const method = `${BILL_TRACKING_ACTIONS}.bulk_assign_bills`
	const handler = async (route) => apiMethod(route.request()) === method
		? replyError(route, "Mocked bulk assignment failure") : route.fallback()
	await page.route("**/api/method/**", handler)
	try {
		await assignment.getByRole("button", { name: "Assign Selected", exact: true }).click()
		const error = page.locator(".document-error-dialog:visible")
		await error.getByText("Mocked bulk assignment failure", { exact: true }).waitFor()
		await gallery.capture(
			page,
			"37a-dialog-bt-bulk-assign-error-mock.png",
			"Mocked bulk Bill Tracking assignment error dialog",
		)
		await error.getByRole("button", { name: "OK", exact: true }).click()
	} finally {
		await page.unroute("**/api/method/**", handler)
	}
	await assignment.getByRole("button", { name: "Cancel", exact: true }).click()
}

async function captureHrEditorsAndReports(gallery, page, fixtures, bills) {
	await navigate(page, `${SITE}/web/hr/bill-tracking/new`)
	await settle(page, ".bill-tracking-editor__body")
	await gallery.capture(page, "42-hr-bill-tracking-editor-new.png", "New Bill Tracking editor")
	await captureExistingBillEditor(gallery, page, bills.draft)
	const suggestions = [
		{ delivery_person: "E2E-AHR Courier", delivery_mob_no: "9000000001" },
		{ delivery_person: "E2E-AHR Office Runner", delivery_mob_no: "9000000002" },
	]
	const handler = async (route) => apiMethod(route.request()) === DELIVERY_PEOPLE_METHOD
		? reply(route, suggestions) : route.fallback()
	await page.route("**/api/method/**", handler)
	try {
		await navigate(page, `${SITE}/web/hr/bill-tracking/new`)
		await settle(page, ".bill-tracking-editor__body")
		await selectLink(page, "Supplier", fixtures.supplier)
		await page.getByText("E2E-AHR Courier", { exact: true }).waitFor()
		await gallery.capture(
			page,
			"43-hr-bill-tracking-editor-delivery-suggestions-mock.png",
			"Mocked Bill Tracking delivery-person suggestions",
		)
		await page.getByRole("button", { name: "Create delivery person", exact: true }).click()
		await page.locator(".delivery-person-suggestion__create").waitFor()
		await gallery.capture(
			page,
			"44-hr-bill-tracking-editor-create-delivery-person-mock.png",
			"Mocked Administrator delivery-person quick-entry form",
		)
	} finally {
		await page.unroute("**/api/method/**", handler)
	}
	await navigate(page, `${SITE}/web/hr/reports?report=attendance`)
	await settle(page, "[data-attendance-strength]")
	await gallery.capture(page, "45-hr-reports-attendance.png", "HR attendance strength report")
	await captureAttendanceErrorMock(gallery, page)
}

async function captureExistingBillEditor(gallery, page, name) {
	await navigate(page, `${SITE}/web/hr/bill-tracking/${encodeURIComponent(name)}/edit`)
	await settle(page, ".bill-tracking-editor__body")
	await gallery.capture(page, "42a-hr-bill-tracking-editor-existing.png", "Existing Bill Tracking editor")
	const billNumber = page.locator("#field-bill_no-value")
	await billNumber.fill(`${await billNumber.inputValue()}-EDIT`)
	await page.getByRole("button", { name: "Cancel", exact: true }).click()
	let dialog = page.locator(".document-confirmation-shell:visible")
	await dialog.getByText("Your unsaved Bill Tracking changes will be lost.", { exact: true }).waitFor()
	await gallery.capture(page, "42b-dialog-bt-editor-discard-changes.png", "Bill Tracking discard confirmation")
	await dialog.getByRole("button", { name: "Keep Editing", exact: true }).click()
	await captureBillTrackingEditorErrorMock(gallery, page)
	dialog = page.locator(".document-confirmation-shell:visible")
	await dialog.getByRole("button", { name: "Discard Changes", exact: true }).click()
}

async function captureBillTrackingEditorErrorMock(gallery, page) {
	const handler = async (route) => apiMethod(route.request()) === BILL_TRACKING_SAVE
		? replyError(route, "Mocked Bill Tracking editor failure") : route.fallback()
	await page.route("**/api/method/**", handler)
	try {
		await page.getByRole("button", { name: "Save", exact: true }).click()
		const error = page.locator(".document-error-dialog:visible")
		await error.getByText("Mocked Bill Tracking editor failure", { exact: true }).waitFor()
		await gallery.capture(
			page,
			"42c-dialog-bt-editor-error-mock.png",
			"Mocked Bill Tracking editor error dialog",
		)
		await error.getByRole("button", { name: "OK", exact: true }).click()
	} finally {
		await page.unroute("**/api/method/**", handler)
	}
	await page.getByRole("button", { name: "Cancel", exact: true }).click()
}

async function chooseTime(page, label, button) {
	const input = page.getByRole("combobox", { name: label, exact: true })
	await input.click()
	const panel = page.locator(`#${await input.getAttribute("aria-controls")}`)
	await panel.getByRole("button", { name: button, exact: true }).click()
	await page.keyboard.press("Escape")
	await panel.waitFor({ state: "hidden" })
}

async function captureAttendanceErrorMock(gallery, page) {
	await captureReportErrorMock(gallery, page, {
		url: `${SITE}/web/hr/reports?report=attendance`,
		selector: "[data-attendance-strength]",
		method: ATTENDANCE_METHOD,
		message: "Mocked Attendance report failure",
		filename: "45a-dialog-hr-attendance-error-mock.png",
		description: "Mocked HR attendance error dialog",
		prepare: async () => {
			await chooseTime(page, "From Time", "Previous Hour")
			await chooseTime(page, "To Time", "Next Hour")
		},
	})
}

async function capturePlainReadOnly(gallery, page, billName) {
	await navigate(page, `${SITE}/web/hr/bill-tracking/${encodeURIComponent(billName)}`)
	await settle(page, ".bill-tracking-header")
	await gallery.capture(page, "46-hr-bill-tracking-read-only-plain-user.png", "Bill Tracking read-only view for a plain user")
}

async function captureRealPurchaseInvoicePhases(gallery, pages, fixtures, billName) {
	const guards = await Promise.all([
		installRealRecordMutationGuard(pages.administrator, "Accounts/HR screenshot Administrator PI phases"),
		installRealRecordMutationGuard(pages.accounts, "Accounts/HR screenshot Accounts User PI phases"),
	])
	try {
		const records = await discoverPurchaseInvoices(pages.administrator)
		await capturePurchaseInvoicePages(gallery, pages.administrator, records)
		await capturePurchaseInvoiceDialogs(gallery, pages, records)
		await capturePurchaseInvoiceEditors(gallery, pages.administrator, fixtures, records, billName)
	} finally {
		await Promise.all(guards.map((verifyNoMutations) => verifyNoMutations()))
	}
}

function expectedNames() {
	const desktop = [
		"01-administrator-13-departments.png",
		"02-accounts-launcher.png",
		"03-accounts-purchase-invoice-list.png",
		"03a-dialog-pi-list-filters.png",
		"03a-dialog-pi-list-customize-columns.png",
		"04-accounts-purchase-invoice-submitted-details.png",
		"05-accounts-purchase-invoice-items-tab.png",
		"06-accounts-purchase-invoice-grns-tab.png",
		"07-accounts-purchase-invoice-verification-tab.png",
		"08-accounts-purchase-invoice-draft-wo.png",
		"09-dialog-pi-approve-invoice.png",
		"10-dialog-pi-work-order-close-mock.png",
		"10a-dialog-pi-work-order-close-discard-mock.png",
		"10b-dialog-pi-work-order-close-error-mock.png",
		"11-dialog-pi-submit-confirm.png",
		"12-dialog-pi-cancel-mock.png",
		"13-dialog-pi-cancel-with-erp-option.png",
		"14-dialog-pi-delete-confirm.png",
		"15-dialog-pi-submit-erp-bill-mock.png",
		"15a-dialog-pi-action-error-mock.png",
		"16-dialog-pi-grn-related-document.png",
		"17-accounts-purchase-invoice-editor-new.png",
		"18-accounts-purchase-invoice-editor-from-bill-tracking.png",
		"19-accounts-purchase-invoice-editor-grn-picker.png",
		"20-accounts-purchase-invoice-editor-fetched-items-mock.png",
		"21-dialog-pi-refetch-migrated-confirm.png",
		"22-dialog-pi-editor-discard-changes.png",
		"22a-dialog-pi-editor-error-mock.png",
		"23-accounts-reports-stock-balance.png",
		"24-accounts-reports-cutting-dpr.png",
		"25-accounts-reports-sewing-dpr-no-unit.png",
		"25a-dialog-accounts-sewing-dpr-error-mock.png",
		"26-accounts-reports-sewing-dpr-with-unit.png",
		"27-accounts-reports-finishing-dispatch.png",
		"27a-dialog-accounts-finishing-dispatch-error-mock.png",
		"28-accounts-reports-ironing-dpr.png",
		"28a-dialog-accounts-ironing-dpr-error-mock.png",
		"30-hr-launcher.png",
		"31-hr-bill-tracking-list.png",
		"31a-dialog-bt-list-filters.png",
		"31a-dialog-bt-list-customize-columns.png",
		"32-hr-bill-tracking-list-assigned-to-me.png",
		"33-hr-bill-tracking-record-details.png",
		"34-hr-bill-tracking-history-tab.png",
		"35-dialog-bt-assign.png",
		"36-dialog-bt-bulk-assign.png",
		"37-dialog-bt-bulk-assign-summary.png",
		"37a-dialog-bt-bulk-assign-error-mock.png",
		"38-dialog-bt-bill-received-confirm.png",
		"39-dialog-bt-request-cancel-confirm.png",
		"40-dialog-bt-approve-cancel-confirm.png",
		"41-dialog-bt-cancel-reason.png",
		"41a-dialog-bt-submit-confirm.png",
		"41b-dialog-bt-delete-confirm.png",
		"41c-dialog-bt-action-error-mock.png",
		"42-hr-bill-tracking-editor-new.png",
		"42a-hr-bill-tracking-editor-existing.png",
		"42b-dialog-bt-editor-discard-changes.png",
		"42c-dialog-bt-editor-error-mock.png",
		"43-hr-bill-tracking-editor-delivery-suggestions-mock.png",
		"44-hr-bill-tracking-editor-create-delivery-person-mock.png",
		"45-hr-reports-attendance.png",
		"45a-dialog-hr-attendance-error-mock.png",
		"46-hr-bill-tracking-read-only-plain-user.png",
	]
	const mobileBases = new Set([
		"01-administrator-13-departments.png",
		"02-accounts-launcher.png",
		"03-accounts-purchase-invoice-list.png",
		"23-accounts-reports-stock-balance.png",
		"30-hr-launcher.png",
	])
	return [...desktop, ...desktop.filter((name) => mobileBases.has(name)).map((name) => (
		name.replace(/\.png$/, "-mobile.png")
	))]
}

async function runCaptures(browser, fixtures, gallery) {
	const sessions = {
		administrator: await createSession(browser, loginAdministrator),
		accounts: await createSession(browser, (page) => loginAs(page, fixtures.accounts_user)),
		hr: await createSession(browser, (page) => loginAs(page, fixtures.hr_user)),
		manager: await createSession(browser, (page) => loginAs(page, fixtures.hr_manager)),
		plain: await createSession(browser, (page) => loginAs(page, fixtures.plain_user)),
	}
	const pages = Object.fromEntries(Object.entries(sessions).map(([key, value]) => [key, value.page]))
	try {
		const bills = await createBillScenarios(pages.hr, pages.manager, fixtures)
		await captureLaunchers(gallery, pages.administrator)
		await captureRealPurchaseInvoicePhases(gallery, pages, fixtures, bills.open)
		await captureAccountsReports(gallery, pages.administrator)
		await captureHrPages(gallery, pages, bills)
		await captureHrDialogs(gallery, pages, fixtures, bills)
		await captureHrEditorsAndReports(gallery, pages.administrator, fixtures, bills)
		await capturePlainReadOnly(gallery, pages.plain, bills.assigned)
	} finally {
		await Promise.all(Object.values(sessions).map(({ context }) => context.close()))
	}
}

async function main() {
	assertMutationGuardPolicy()
	rmSync(OUTPUT_DIRECTORY, { recursive: true, force: true })
	mkdirSync(OUTPUT_DIRECTORY, { recursive: true })
	const gallery = new ScreenshotGallery(OUTPUT_DIRECTORY)
	let fixtures
	const browser = await chromium.launch({ headless: true })
	try {
		fixtures = fixtureSetup()
		await runCaptures(browser, fixtures, gallery)
		gallery.writeIndex()
		gallery.verify(expectedNames())
		console.log(`OK ${gallery.entries.length} screenshots; index ${join(OUTPUT_DIRECTORY, "INDEX.txt")}`)
	} finally {
		await browser.close()
		fixtureTeardown()
	}
}

main().catch((error) => {
	console.error(sanitizeSensitiveText(error?.stack || error))
	process.exitCode = 1
})
