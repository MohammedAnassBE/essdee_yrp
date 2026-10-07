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

async function mockMovementWorkspace(page, options = {}) {
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
		status: 200, contentType: "application/json", body: JSON.stringify({ message: options.editor || movementFixture() }),
	}))
	await page.route("**/api/method/essdee_yrp.cut_panel_store.movement_workspace.generate_movement_bundles*", (route) => route.fulfill({
		status: 200, contentType: "application/json", body: JSON.stringify({ message: generatedMovementFixture() }),
	}))
	await page.route("**/api/method/essdee_yrp.api.link_search.link_search*", (route) => route.fulfill({
		status: 200, contentType: "application/json", body: JSON.stringify({ message: [] }),
	}))
	await page.route("**/api/method/essdee_yrp.cut_panel_store.movement_workspace.get_movement_linked_documents*", (route) => route.fulfill({
		status: 200, contentType: "application/json", body: JSON.stringify({ message: options.linked || { sections: {}, actions: {} } }),
	}))
	await page.route("**/api/method/essdee_yrp.cut_panel_store.movement_workspace.get_movement_work_orders*", (route) => route.fulfill({
		status: 200, contentType: "application/json", body: JSON.stringify({ message: [{ name: "WO-CP-1", lot: "LOT-CP-1", item: "ITEM-CP-1", supplier: "CUT-STORE" }] }),
	}))
}

async function movementSuite(page) {
	await page.setViewportSize({ width: 1440, height: 900 })
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

function submittedMovementFixture() {
	const fixture = movementFixture()
	fixture.record = {
		name: "CPM-1", docstatus: 1, status: "Submitted", modified: "2026-10-07 10:00:00",
		lot: "LOT-CP-1", item: "ITEM-CP-1", from_warehouse: "CUT-STORE",
		permissions: { can_write: false, can_submit: false, can_cancel: true, can_print: true },
		movement_data: generatedMovementFixture(),
	}
	fixture.movement_data = generatedMovementFixture()
	return fixture
}

async function movementTransactionSuite(page) {
	await page.setViewportSize({ width: 1440, height: 900 })
	const linked = {
		sections: {
			stock_entries: [{ doctype: "YRP Stock Entry", name: "STE-CP-1", status: "Cancelled", docstatus: 2, posting_date: "2026-10-07", posting_time: "10:00:00" }],
			delivery_challans: [{ doctype: "YRP Delivery Challan", name: "DC-CP-1", status: "Submitted", docstatus: 1, posting_date: "2026-10-07", posting_time: "10:15:00" }],
			goods_received_notes: [{ doctype: "YRP Goods Received Note", name: "GRN-CP-1", status: "Draft", docstatus: 0, posting_date: "2026-10-07", posting_time: "10:30:00" }],
		},
		actions: {
			stock_entry: { label: "Create Stock Entry", eligible: true, can_create: true },
			delivery_challan: { label: "Create Delivery Challan", eligible: true, can_create: true },
			goods_received_note: { label: "Create Goods Received Note", eligible: true, can_create: true },
		},
	}
	await mockMovementWorkspace(page, { editor: submittedMovementFixture(), linked })
	await page.goto(`${SITE}/web/cut-panel-store/movements`, { waitUntil: "domcontentloaded" })
	await page.getByText("CPM-1", { exact: true }).click()
	const dialog = page.locator(".erp-cut-panel-movement-dialog:visible")
	await dialog.waitFor({ timeout: 20_000 })
	const layout = dialog.locator(".cut-panel-movement-layout")
	const rail = dialog.locator(".cut-panel-movement-rail")
	await rail.waitFor({ timeout: 20_000 })
	const ratio = await layout.evaluate((element) => {
		const children = [...element.children]
		return children[0].getBoundingClientRect().width / children[1].getBoundingClientRect().width
	})
	assert(ratio >= 3.2 && ratio <= 5.2, `Movement workspace is not approximately 80/20: ${ratio}`)
	for (const label of ["Stock Entries", "Delivery Challans", "Goods Received Notes"]) {
		assert(await rail.getByText(label, { exact: true }).count() >= 1, `Movement rail omits ${label}: ${await rail.textContent()}`)
	}
	for (const label of ["Create Stock Entry", "Create Delivery Challan", "Create Goods Received Note"]) {
		assert(await rail.getByRole("button", { name: label, exact: true }).count() === 1, `Movement rail omits ${label}`)
	}
	assert(await rail.getByText("STE-CP-1", { exact: true }).count() === 1, "Stock Entry history is missing")
	assert(await rail.getByText("DC-CP-1", { exact: true }).count() === 1, "Delivery Challan history is missing")
	assert(await rail.getByText("GRN-CP-1", { exact: true }).count() === 1, "Goods Received Note history is missing")

	await rail.getByRole("button", { name: "Create Delivery Challan", exact: true }).click()
	const chooser = page.locator(".cut-panel-transaction-create-dialog:visible")
	await chooser.waitFor()
	assert(await chooser.getByText("WO-CP-1", { exact: true }).count() === 1, "DC creation does not offer same-Lot Work Orders")

	await page.setViewportSize({ width: 760, height: 900 })
	const stacked = await layout.evaluate((element) => {
		const [main, side] = [...element.children].map((child) => child.getBoundingClientRect())
		return side.top >= main.bottom - 1
	})
	assert(stacked, "Movement linked rail does not move below the editor on a narrow viewport")

	const dialogSource = readFileSync(new URL("../frontend/src/departments/cut-panel-store/CutPanelMovementDialog.vue", import.meta.url), "utf8")
	const railSource = readFileSync(new URL("../frontend/src/departments/cut-panel-store/CutPanelMovementRail.vue", import.meta.url), "utf8")
	assert(dialogSource.includes("RelatedDocumentWorkspaceDialog"), "Movement dialog does not reuse the complete Fabric DC/GRN workspace")
	assert(dialogSource.includes("FabricStockOperationDialog"), "Movement dialog does not reuse the complete Stock Entry workspace")
	assert(dialogSource.includes("DocumentErrorDialog"), "Movement transaction errors do not use the shared popup")
	assert(railSource.includes("emit('open-document'"), "Movement rail rows do not open their linked documents")
}

async function workOrdersSuite(page) {
	await page.setViewportSize({ width: 1440, height: 900 })
	await page.route("**/api/method/essdee_yrp.cut_panel_store.web_workspace.get_capabilities*", (route) => route.fulfill({
		status: 200, contentType: "application/json", body: JSON.stringify({ message: capabilities }),
	}))
	await page.route("**/api/method/frappe.desk.form.load.getdoctype*", (route) => route.fulfill({
		status: 200,
		contentType: "application/json",
		body: JSON.stringify({ docs: [{
			name: "YRP Work Order",
			is_submittable: 1,
			fields: [
				{ fieldname: "supplier", label: "Supplier", fieldtype: "Link", options: "Supplier", in_list_view: 1 },
				{ fieldname: "item", label: "Item", fieldtype: "Link", options: "Item", in_list_view: 1 },
				{ fieldname: "lot", label: "Lot", fieldtype: "Link", options: "SD YRP Lot", in_list_view: 1 },
				{ fieldname: "status", label: "Status", fieldtype: "Data", in_list_view: 1 },
			],
		}] }),
	}))
	await page.route("**/api/method/yrp.yrp.doctype.yrp_user_listview.yrp_user_listview.get_user_listview*", (route) => route.fulfill({
		status: 200, contentType: "application/json", body: JSON.stringify({ message: [] }),
	}))
	await page.route("**/api/method/frappe.desk.reportview.get_count*", (route) => route.fulfill({
		status: 200, contentType: "application/json", body: JSON.stringify({ message: 1 }),
	}))
	await page.route("**/api/resource/YRP%20Work%20Order*", (route) => route.fulfill({
		status: 200,
		contentType: "application/json",
		body: JSON.stringify({ data: [{ name: "WO-CP-ROUTE-1", supplier: "CUT-PANEL-STORE", item: "ITEM-CP-1", lot: "LOT-CP-1", status: "Submitted", docstatus: 1, modified: "2026-10-07 12:00:00" }] }),
	}))
	await page.route("**/api/method/essdee_yrp.fabric_store.web_workspace.get_work_order_workspace*", (route) => route.fulfill({
		status: 200,
		contentType: "application/json",
		body: JSON.stringify({ message: {
			record: { doctype: "YRP Work Order", name: "WO-CP-ROUTE-1", supplier: "CUT-PANEL-STORE", item: "ITEM-CP-1", lot: "LOT-CP-1", status: "Submitted", docstatus: 1 },
			fields: [], dimensions: [], matrices: { deliverables: [], receivables: [] }, related: { delivery_challans: [], goods_received_notes: [] },
			capabilities: {}, permissions: { can_read: true, can_create: true }, related_permissions: {}, totals: [], summary: {},
		} }),
	}))

	await page.goto(`${SITE}/web/cut-panel-store/work-orders`, { waitUntil: "domcontentloaded" })
	const list = page.locator(".cut-panel-store-section .fabric-work-orders .common-list-view")
	await list.waitFor({ timeout: 20_000 })
	assert(await page.getByRole("button", { name: "Create Work Order", exact: true }).count() === 1, "Cut Panel Work Orders omit the permission-aware create action")
	await list.getByText("WO-CP-ROUTE-1", { exact: true }).click()
	await page.waitForURL("**/web/cut-panel-store/work-orders/WO-CP-ROUTE-1")
	await page.locator(".fabric-work-order-frame").waitFor({ timeout: 20_000 })
	assert(page.url().endsWith("/web/cut-panel-store/work-orders/WO-CP-ROUTE-1"), "Cut Panel Work Order escaped to the Fabric Store route")

	const routerSource = readFileSync(new URL("../frontend/src/router/index.js", import.meta.url), "utf8")
	const listSource = readFileSync(new URL("../frontend/src/departments/fabric-store/FabricWorkOrders.vue", import.meta.url), "utf8")
	const viewSource = readFileSync(new URL("../frontend/src/departments/FabricWorkOrder.vue", import.meta.url), "utf8")
	const editorSource = readFileSync(new URL("../frontend/src/departments/FabricWorkOrderEditorPage.vue", import.meta.url), "utf8")
	for (const routeName of ["cut-panel-work-order-new", "cut-panel-work-order-edit", "cut-panel-work-order"]) {
		assert(routerSource.includes(`name: "${routeName}"`), `Router omits ${routeName}`)
	}
	assert(listSource.includes("viewRouteName") && listSource.includes("newRouteName"), "Shared Work Order list is not route-context aware")
	assert(viewSource.includes("editRouteName") && viewSource.includes("newRouteName") && viewSource.includes("viewRouteName"), "Shared Work Order view is not route-context aware")
	assert(editorSource.includes("listRouteName") && editorSource.includes("viewRouteName"), "Shared Work Order editor is not route-context aware")
}

const suites = {
	launcher: launcherSuite,
	movements: movementSuite,
	"movement-transactions": movementTransactionSuite,
	"work-orders": workOrdersSuite,
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
