#!/usr/bin/env node

import { createRequire } from "node:module"
import { readFileSync } from "node:fs"

const require = createRequire("/home/anas/.claude/playwright/package.json")
const { chromium } = require("playwright")

const SITE = "http://erp-migration-test.site:8001"
const [username, password] = readFileSync("/home/anas/.frappe-debug-creds-mrp3", "utf8").trim().split("\n")
const EDITOR = "**/api/method/essdee_yrp.cutting.plan_editor.get_editor*"
const LOAD_LOT = "**/api/method/essdee_yrp.cutting.plan_editor.load_lot_items*"
const SAVE = "**/api/method/essdee_yrp.cutting.plan_editor.save*"

function assert(condition, message) {
	if (!condition) throw new Error(message)
}

function editorPayload({ name = null, docstatus = 0, canSubmit = true, groups = [] } = {}) {
	return {
		record: {
			name,
			docstatus,
			modified: name ? "2026-10-03 12:00:00" : null,
			is_manual_entry: 0,
			lot: groups.length ? "LOT-001" : null,
			item: groups.length ? "STYLE-001" : null,
			production_detail: groups.length ? "IPD-001" : null,
			maximum_no_of_plys: 100,
			maximum_allow_percent: 10,
			cutting_location: "Manual Cutting",
			work_order: null,
			status: docstatus === 1 ? "Planned" : "Draft",
		},
		matrix: { groups },
		permissions: {
			can_read: true,
			can_create: true,
			can_write: docstatus === 0,
			can_submit: docstatus === 0 && canSubmit,
			can_cancel: docstatus === 1,
			can_amend: false,
		},
		fields: { show_work_order: true, can_edit_work_order: true },
		options: { cutting_locations: ["Machine Cutting", "Manual Cutting"] },
	}
}

const groups = [{
	attributes: ["Colour"],
	primary_attribute: "Size",
	primary_attribute_values: ["S", "M"],
	items: [{
		_row_key: "g0:r0",
		name: "STYLE-001",
		attributes: { Colour: "Navy", Stage: "Piece" },
		item_keys: { major_colour: "Navy" },
		primary_attribute: "Size",
		values: { S: { qty: 12 }, M: { qty: 14 } },
		total_qty: 26,
	}],
	size_wise_total: { S: 12, M: 14 },
	total_sum: 26,
}]

const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
const page = await context.newPage()
const errors = []
let saved = false
let canSubmit = true
let savedBody = null
page.on("pageerror", (error) => errors.push(`page: ${error.message}`))
page.on("console", (message) => { if (message.type() === "error") errors.push(`console: ${message.text()}`) })

await page.goto(`${SITE}/login`, { waitUntil: "domcontentloaded" })
await page.fill("#login_email", username.trim())
await page.fill("#login_password", password.trim())
await Promise.all([
	page.waitForNavigation({ waitUntil: "domcontentloaded", timeout: 20_000 }).catch(() => {}),
	page.click(".btn-login, button[type=submit]"),
])

await page.route("**/api/method/essdee_yrp.cutting.web_capabilities.get_capabilities*", (route) => route.fulfill({
	status: 200,
	contentType: "application/json",
	body: JSON.stringify({ message: {
		"cutting-plans": { can_read: true, can_create: true },
		"cutting-orders": { can_read: false, can_create: false },
		"bulk-lay-sheets": { can_read: false, can_create: false },
		"lay-sheet-planner": { can_read: false, can_create: false },
		reports: { can_read: false, can_create: false },
	} }),
}))
await page.route("**/api/method/frappe.desk.form.load.getdoctype*", (route) => route.fulfill({
	status: 200,
	contentType: "application/json",
	body: JSON.stringify({ docs: [{ name: "SD YRP Cutting Plan", is_submittable: 1, fields: [
		{ fieldname: "lot", label: "Lot", fieldtype: "Link", options: "SD YRP Lot", in_list_view: 1 },
		{ fieldname: "item", label: "Item", fieldtype: "Link", options: "Item", in_list_view: 1 },
		{ fieldname: "cp_status", label: "Status", fieldtype: "Select", in_list_view: 1 },
	] }] }),
}))
await page.route("**/api/method/yrp.yrp.doctype.yrp_user_listview.yrp_user_listview.get_user_listview*", (route) => route.fulfill({
	status: 200, contentType: "application/json", body: JSON.stringify({ message: [] }),
}))
await page.route("**/api/method/frappe.desk.reportview.get_count*", (route) => route.fulfill({
	status: 200, contentType: "application/json", body: JSON.stringify({ message: 0 }),
}))
await page.route("**/api/resource/SD%20YRP%20Cutting%20Plan*", (route) => route.fulfill({
	status: 200, contentType: "application/json", body: JSON.stringify({ data: [] }),
}))
await page.route("**/api/method/essdee_yrp.api.link_search.link_search*", async (route) => {
	const body = JSON.parse(route.request().postData() || "{}")
	const rows = body.doctype === "SD YRP Lot" ? [{ name: "LOT-001", label: "LOT-001" }] : []
	await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: rows }) })
})
await page.route(EDITOR, async (route) => {
	const body = JSON.parse(route.request().postData() || "{}")
	const existing = body.cutting_plan === "CP-WEB-NEW" || saved
	await route.fulfill({
		status: 200,
		contentType: "application/json",
		body: JSON.stringify({ message: editorPayload({ name: existing ? "CP-WEB-NEW" : null, canSubmit, groups: existing ? groups : [] }) }),
	})
})
await page.route(LOAD_LOT, (route) => route.fulfill({
	status: 200,
	contentType: "application/json",
	body: JSON.stringify({ message: { lot: "LOT-001", item: "STYLE-001", production_detail: "IPD-001", groups } }),
}))
await page.route(SAVE, async (route) => {
	savedBody = JSON.parse(route.request().postData() || "{}")
	saved = true
	await route.fulfill({
		status: 200,
		contentType: "application/json",
		body: JSON.stringify({ message: editorPayload({ name: "CP-WEB-NEW", canSubmit, groups }) }),
	})
})

await page.goto(`${SITE}/web/cutting/plans`, { waitUntil: "domcontentloaded" })
await page.getByRole("button", { name: "Create Cutting Plan", exact: true }).waitFor({ timeout: 20_000 })
await page.getByRole("button", { name: "Create Cutting Plan", exact: true }).click()
await page.waitForURL("**/web/cutting/plans/new")
await page.getByRole("heading", { name: "New Cutting Plan", exact: true }).waitFor({ timeout: 20_000 })
assert(await page.locator("input[type=date], input[type=time], input[type=datetime-local]").count() === 0, "Cutting Plan editor uses native temporal inputs")

const lotField = page.locator(".cutting-plan-editor__field").filter({ hasText: "Lot" })
await lotField.locator(".p-autocomplete-input").fill("LOT")
await page.locator(".p-autocomplete-option").filter({ hasText: "LOT-001" }).click()
await page.getByRole("columnheader", { name: "S", exact: true }).waitFor()
assert(await page.locator(".quantity-attribute").filter({ hasText: "Navy" }).count() >= 1, "Lot matrix did not render the authoritative colour row")

await page.getByRole("button", { name: "Save Draft", exact: true }).click()
await page.waitForURL("**/web/cutting/plans/CP-WEB-NEW")
await page.getByRole("heading", { name: "Edit Cutting Plan", exact: true }).waitFor({ timeout: 20_000 })
assert(savedBody?.submit === false, `Draft save sent an unexpected lifecycle action: ${JSON.stringify(savedBody)}`)
assert(savedBody?.values?.item_details?.[0]?.items?.[0]?._row_key === "g0:r0", "Draft save lost the authoritative row key")
assert(!page.url().includes("/app/"), "Cutting Plan creation redirected to Desk")
assert(await page.getByRole("button", { name: "Save & Submit", exact: true }).count() === 1, "Permitted Save & Submit is missing")

canSubmit = false
saved = false
await page.goto(`${SITE}/web/cutting/plans/new`, { waitUntil: "domcontentloaded" })
await page.getByRole("heading", { name: "New Cutting Plan", exact: true }).waitFor()
assert(await page.getByRole("button", { name: "Save & Submit", exact: true }).count() === 0, "Save & Submit ignores submit permission")

const plies = page.getByLabel("Maximum No of Plys")
await plies.fill("110")
await page.getByRole("button", { name: "Cutting Plans", exact: true }).click()
const discardDialog = page.getByRole("dialog", { name: "Discard unsaved changes?" })
await discardDialog.waitFor()
await discardDialog.getByRole("button", { name: "Keep Editing", exact: true }).click()
assert(page.url().endsWith("/web/cutting/plans/new"), "Dirty editor navigated away without confirmation")
await page.getByRole("button", { name: "Cutting Plans", exact: true }).click()
await discardDialog.getByRole("button", { name: "Discard Changes", exact: true }).click()
await page.waitForURL("**/web/cutting/plans")

assert(errors.length === 0, `Browser errors: ${JSON.stringify(errors)}`)
console.log(JSON.stringify({ passed: true, savedName: "CP-WEB-NEW", matrixRows: 1, dirtyConfirmation: true }, null, 2))
await browser.close()
