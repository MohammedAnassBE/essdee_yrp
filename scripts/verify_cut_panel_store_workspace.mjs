#!/usr/bin/env node

import { createRequire } from "node:module"
import { readFileSync } from "node:fs"

const require = createRequire("/home/anas/.claude/playwright/package.json")
const { chromium } = require("playwright")
const SITE = "http://erp-migration-test.site:8001"
const CREDENTIALS = "/home/anas/.frappe-debug-creds-mrp3"
const suite = process.argv[2] || "all"

function assert(condition, message) {
	if (!condition) throw new Error(message)
}

const sectionDefinitions = [
	["movements", "Cut Panel Movement", "/web/cut-panel-store/movements"],
	["work_orders", "Work Orders", "/web/cut-panel-store/work-orders"],
	["cut_bundle_edits", "Cut Bundle Edit", "/web/cut-panel-store/cut-bundle-edits"],
	["box_stickers", "Box Sticker Print", "/web/cut-panel-store/box-sticker-prints"],
	["excel_stickers", "Excel Sticker Print", "/web/cut-panel-store/excel-sticker-prints"],
	["reports", "Reports", "/web/cut-panel-store/reports"],
]

const capabilities = {
	sections: Object.fromEntries(sectionDefinitions.map(([key, label]) => [key, {
		label,
		doctype: key === "reports" ? undefined : key,
		can_read: true,
		can_create: true,
	}])),
}

async function login(page) {
	const [username, password] = readFileSync(CREDENTIALS, "utf8").trim().split("\n")
	await page.goto(`${SITE}/login`, { waitUntil: "domcontentloaded" })
	await page.fill("#login_email", username.trim())
	await page.fill("#login_password", password.trim())
	await Promise.all([
		page.waitForNavigation({ waitUntil: "domcontentloaded", timeout: 20_000 }).catch(() => {}),
		page.click(".btn-login, button[type=submit]"),
	])
}

async function installCapabilityMock(page, state) {
	await page.route("**/api/method/essdee_yrp.cut_panel_store.web_workspace.get_capabilities*", async (route) => {
		if (state.delay) await new Promise((resolve) => setTimeout(resolve, state.delay))
		if (state.error) {
			return route.fulfill({
				status: 500,
				contentType: "application/json",
				body: JSON.stringify({ message: state.error }),
			})
		}
		return route.fulfill({
			status: 200,
			contentType: "application/json",
			body: JSON.stringify({ message: state.payload }),
		})
	})
}

async function launcherSuite(page) {
	const state = { payload: capabilities, delay: 0, error: "" }
	await installCapabilityMock(page, state)
	await page.goto(`${SITE}/web/cut-panel-store`, { waitUntil: "domcontentloaded" })
	const launcher = page.locator(".workspace-launcher")
	await launcher.waitFor({ timeout: 20_000 })

	const cards = launcher.locator(".workspace-launcher__card")
	await cards.nth(sectionDefinitions.length - 1).waitFor({ timeout: 20_000 })
	const cardCount = await cards.count()
	assert(cardCount === sectionDefinitions.length, `Expected six Cut Panel Store cards, got ${cardCount}`)
	assert(
		JSON.stringify((await cards.locator("strong").allTextContents()).map((value) => value.trim()))
			=== JSON.stringify(sectionDefinitions.map(([, label]) => label)),
		`Unexpected Cut Panel Store cards: ${JSON.stringify(await cards.locator("strong").allTextContents())}`,
	)
	assert(await page.getByText("Raw Sticker Print", { exact: true }).count() === 0, "Raw Sticker Print must not be exposed")
	for (const [, label, href] of sectionDefinitions) {
		const link = page.getByRole("link", { name: new RegExp(`^${label}`) })
		assert(await link.count() === 1, `${label} card is missing`)
		assert(await link.getAttribute("href") === href, `${label} points to the wrong route`)
	}

	for (const [key, label, href] of sectionDefinitions) {
		await page.goto(`${SITE}${href}`, { waitUntil: "domcontentloaded" })
		const section = page.locator(".cut-panel-store-section")
		await section.waitFor({ timeout: 20_000 })
		assert(await section.getAttribute("aria-label") === label, `${key} route rendered the wrong section`)
	}

	state.payload = { sections: {} }
	await page.goto(`${SITE}/web/cut-panel-store/movements`, { waitUntil: "domcontentloaded" })
	await page.getByText("You do not have permission to view Cut Panel Movement.", { exact: true }).waitFor()

	state.payload = capabilities
	state.delay = 1_000
	const loadingNavigation = page.goto(`${SITE}/web/cut-panel-store/reports`, { waitUntil: "domcontentloaded" })
	await page.locator(".cut-panel-store-section__loading").waitFor({ timeout: 20_000 })
	await loadingNavigation
	state.delay = 0

	state.error = "Capability service unavailable"
	await page.goto(`${SITE}/web/cut-panel-store/box-sticker-prints`, { waitUntil: "domcontentloaded" })
	await page.getByText("Capability service unavailable", { exact: true }).waitFor({ timeout: 20_000 })
}

function movementFixture() {
	return {
		context: { lot: "LOT-CP-1", item: "ITEM-CP-1", source_supplier: "CUT-STORE", source_warehouse: "CUT-WH" },
		defaults: { lot: "LOT-CP-1", from_warehouse: "CUT-STORE", posting_date: "2026-10-07", posting_time: "10:30:00", edit_posting_date_and_time: 1 },
		permissions: { can_create: true, can_submit: true },
		record: null,
		movement_data: { panels: [], data: {}, collapsed_details: [], accessory_data: [], is_set_item: 0 },
	}
}

function generatedMovementFixture() {
	return {
		panels: ["Front"],
		is_set_item: 0,
		data: { Navy: { part: null, data: [{ lay_no: 1, bundle_no: 2, size: "M", shade: "A", Front: 10, Front_moved: false, bundle_moved: false }] } },
		collapsed_details: [{ colour: "Navy", size: "L", panel: "Back", shade: "A", lay_no: 3, bundle_no: 4, quantity: 6, moved: false, move_qty: 0 }],
		accessory_data: [{ cloth_name: "Tape", cloth_type: "Accessory", colour: "Navy", shade: "A", dia: "10 mm", weight: 4, moved_weight: 0 }],
	}
}

async function mockMovementWorkspace(page) {
	await page.route("**/api/method/essdee_yrp.cut_panel_store.web_workspace.get_capabilities*", (route) => route.fulfill({
		status: 200, contentType: "application/json", body: JSON.stringify({ message: capabilities }),
	}))
	await page.route("**/api/method/frappe.desk.form.load.getdoctype*", (route) => route.fulfill({
		status: 200,
		contentType: "application/json",
		body: JSON.stringify({ docs: [{
			name: "SD YRP Cut Panel Movement",
			is_submittable: 1,
			fields: [
				{ fieldname: "lot", label: "Lot", fieldtype: "Link", options: "SD YRP Lot", in_list_view: 1, in_standard_filter: 1 },
				{ fieldname: "item", label: "Item", fieldtype: "Link", options: "Item", in_list_view: 1 },
				{ fieldname: "from_warehouse", label: "From Warehouse", fieldtype: "Link", options: "Supplier", in_list_view: 1 },
				{ fieldname: "against", label: "Against", fieldtype: "Select", in_list_view: 1 },
				{ fieldname: "against_id", label: "Against ID", fieldtype: "Dynamic Link", options: "against", in_list_view: 1 },
				{ fieldname: "movement_date", label: "Movement Date", fieldtype: "Date", in_list_view: 1 },
			],
		}] }),
	}))
	await page.route("**/api/method/yrp.yrp.doctype.yrp_user_listview.yrp_user_listview.get_user_listview*", (route) => route.fulfill({
		status: 200, contentType: "application/json", body: JSON.stringify({ message: [] }),
	}))
	await page.route("**/api/method/frappe.desk.reportview.get_count*", (route) => route.fulfill({
		status: 200, contentType: "application/json", body: JSON.stringify({ message: 1 }),
	}))
	await page.route("**/api/resource/SD%20YRP%20Cut%20Panel%20Movement*", (route) => route.fulfill({
		status: 200,
		contentType: "application/json",
		body: JSON.stringify({ data: [{ name: "CPM-1", lot: "LOT-CP-1", item: "ITEM-CP-1", from_warehouse: "CUT-STORE", against: "", against_id: "", movement_date: "2026-10-07", docstatus: 0, modified: "2026-10-07 10:00:00" }] }),
	}))
	await page.route("**/api/method/essdee_yrp.cut_panel_store.movement_workspace.get_movement_editor*", (route) => route.fulfill({
		status: 200, contentType: "application/json", body: JSON.stringify({ message: movementFixture() }),
	}))
	await page.route("**/api/method/essdee_yrp.cut_panel_store.movement_workspace.generate_movement_bundles*", (route) => route.fulfill({
		status: 200, contentType: "application/json", body: JSON.stringify({ message: generatedMovementFixture() }),
	}))
	await page.route("**/api/method/essdee_yrp.api.link_search.link_search*", (route) => route.fulfill({
		status: 200, contentType: "application/json", body: JSON.stringify({ message: [] }),
	}))
}

async function movementSuite(page) {
	await mockMovementWorkspace(page)
	await page.goto(`${SITE}/web/cut-panel-store/movements`, { waitUntil: "domcontentloaded" })
	const list = page.locator(".cut-panel-movements .common-list-view")
	await list.waitFor({ timeout: 20_000 })
	assert(await page.getByRole("button", { name: "Create Movement", exact: true }).count() === 1, "Create Movement is missing")
	for (const label of ["Lot", "Item", "From Warehouse", "Against", "Against ID", "Movement Date"]) {
		assert(await list.getByRole("columnheader", { name: label, exact: true }).count() === 1, `Movement list omits ${label}`)
	}

	await page.getByRole("button", { name: "Create Movement", exact: true }).click()
	const dialog = page.locator(".erp-cut-panel-movement-dialog:visible")
	await dialog.waitFor({ timeout: 20_000 })
	assert(await dialog.locator(".p-dialog-maximize-button").count() === 1, "Movement popup is not maximizable")
	for (const label of ["Lot", "From Warehouse", "Posting Date", "Posting Time", "Edit Posting Date and Time"]) {
		const labelledControl = await dialog.getByLabel(label, { exact: false }).count()
		const visibleLabel = await dialog.getByText(label, { exact: true }).count()
		assert(labelledControl >= 1 || visibleLabel >= 1, `Movement editor omits ${label}`)
	}
	assert(await dialog.getByRole("button", { name: "Save", exact: true }).count() === 1, "Movement editor must have one primary Save action")
	await dialog.getByRole("button", { name: "Generate Bundles", exact: true }).click()
	await dialog.locator(".erp-bundle-matrix").waitFor()
	assert(await dialog.getByRole("region", { name: "Collapsed bundle quantities" }).count() === 1, "Collapsed movement matrix is missing")
	assert(await dialog.getByRole("region", { name: "Accessory fabric quantities" }).count() === 1, "Accessory movement matrix is missing")

	const before = await dialog.locator("input").first().inputValue().catch(() => "")
	await page.setViewportSize({ width: 390, height: 844 })
	const geometry = await dialog.evaluate((element) => {
		const rect = element.getBoundingClientRect()
		return { left: rect.left, right: rect.right, width: rect.width, viewport: window.innerWidth }
	})
	assert(geometry.left >= 0 && geometry.right <= geometry.viewport + 1, `Movement popup escapes the mobile viewport: ${JSON.stringify(geometry)}`)
	assert(await dialog.locator("input").first().inputValue().catch(() => "") === before, "Responsive layout discarded unsaved movement values")
}

const suites = {
	launcher: launcherSuite,
	movements: movementSuite,
}

const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
const page = await context.newPage()
const browserErrors = []
page.on("pageerror", (error) => browserErrors.push(error.message))

try {
	await login(page)
	if (suite === "all") {
		for (const run of Object.values(suites)) await run(page)
	} else {
		assert(suites[suite], `Unknown Cut Panel Store verification suite: ${suite}`)
		await suites[suite](page)
	}
	assert(browserErrors.length === 0, `Browser errors: ${browserErrors.join("; ")}`)
	console.log(JSON.stringify({ passed: true, suite, browserErrors }, null, 2))
} finally {
	await browser.close()
}
