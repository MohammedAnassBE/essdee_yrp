#!/usr/bin/env node

import { createRequire } from "node:module"
import { readFileSync } from "node:fs"

import { USER_LISTVIEW_ROUTE, fulfillUserListview } from "./listview_mock.mjs"

const require = createRequire("/home/anas/.claude/playwright/package.json")
const { chromium } = require("playwright")
const SITE = process.env.ESSDEE_TEST_SITE || "http://erp-migration-test.site:8001"
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
	const retry = page.getByRole("button", { name: "Retry", exact: true })
	assert(await retry.count() === 1, "Capability failure has no retry action")

	state.error = ""
	await retry.click()
	await page.locator(".box-sticker-prints .common-list-view").waitFor({ timeout: 20_000 })
	for (const width of [1600, 1280, 900, 390]) {
		await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
		await page.goto(`${SITE}/web/cut-panel-store`, { waitUntil: "domcontentloaded" })
		await launcher.waitFor({ timeout: 20_000 })
		await cards.nth(sectionDefinitions.length - 1).waitFor({ timeout: 20_000 })
		const geometry = await launcher.evaluate((element) => {
			const rect = element.getBoundingClientRect()
			return { left: rect.left, right: rect.right, viewport: window.innerWidth, pageWidth: document.documentElement.scrollWidth }
		})
		assert(geometry.left >= 0 && geometry.right <= geometry.viewport + 1, `Launcher escapes ${width}px viewport: ${JSON.stringify(geometry)}`)
		assert(geometry.pageWidth <= geometry.viewport + 1, `Launcher creates horizontal overflow at ${width}px: ${JSON.stringify(geometry)}`)
	}
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
	const movementMetaFields = [
		{ fieldname: "lot", label: "Lot", fieldtype: "Link", options: "SD YRP Lot", in_list_view: 1, in_standard_filter: 1 },
		{ fieldname: "item", label: "Item", fieldtype: "Link", options: "Item", in_list_view: 1 },
		{ fieldname: "from_warehouse", label: "From Warehouse", fieldtype: "Link", options: "Supplier", in_list_view: 1 },
		{ fieldname: "against", label: "Against", fieldtype: "Select", in_list_view: 1 },
		{ fieldname: "against_id", label: "Against ID", fieldtype: "Dynamic Link", options: "against", in_list_view: 1 },
		{ fieldname: "movement_date", label: "Movement Date", fieldtype: "Date", in_list_view: 1 },
	]
	await page.route("**/api/method/frappe.desk.form.load.getdoctype*", (route) => route.fulfill({
		status: 200,
		contentType: "application/json",
		body: JSON.stringify({ docs: [{
			name: "SD YRP Cut Panel Movement",
			is_submittable: 1,
			fields: movementMetaFields,
		}] }),
	}))
	await page.route(USER_LISTVIEW_ROUTE, (route) => fulfillUserListview(route, movementMetaFields, { isSubmittable: true }))
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
	await list.getByRole("columnheader", { name: "Lot", exact: true }).waitFor({ timeout: 20_000 })
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
	const movementList = page.locator(".cut-panel-movements .common-list-view")
	await movementList.waitFor({ timeout: 20_000 })
	assert(await movementList.locator(".list-load-error").count() === 0, `Movement list failed to load: ${await movementList.textContent()}`)
	const movementRow = movementList.locator(".premium-list-table").getByText("CPM-1", { exact: true })
	assert(await movementRow.count() === 1, `Submitted movement row is missing: ${await movementList.textContent()}`)
	await movementRow.click()
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
	await chooser.getByText("WO-CP-1", { exact: true }).waitFor({ timeout: 20_000 })
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
	const workOrderMetaFields = [
		{ fieldname: "supplier", label: "Supplier", fieldtype: "Link", options: "Supplier", in_list_view: 1 },
		{ fieldname: "item", label: "Item", fieldtype: "Link", options: "Item", in_list_view: 1 },
		{ fieldname: "lot", label: "Lot", fieldtype: "Link", options: "SD YRP Lot", in_list_view: 1 },
		{ fieldname: "status", label: "Status", fieldtype: "Data", in_list_view: 1 },
	]
	await page.route("**/api/method/frappe.desk.form.load.getdoctype*", (route) => route.fulfill({
		status: 200,
		contentType: "application/json",
		body: JSON.stringify({ docs: [{
			name: "YRP Work Order",
			is_submittable: 1,
			fields: workOrderMetaFields,
		}] }),
	}))
	await page.route(USER_LISTVIEW_ROUTE, (route) => fulfillUserListview(route, workOrderMetaFields, { isSubmittable: true }))
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
	await list.locator(".premium-list-table").getByText("WO-CP-ROUTE-1", { exact: true }).click()
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

function cutBundleEditorFixture() {
	const row = { lay_no: 1, bundle_no: 7, qty: 10, panel: "Front", set_combination: {}, shade: "A", size: "M", colour: "Navy", is_collapsed: false }
	return {
		context: { lot: "LOT-CP-1", warehouse: "CUT-STORE", item: "ITEM-CP-1" },
		defaults: { lot: "LOT-CP-1", warehouse: "CUT-STORE", item: "ITEM-CP-1", posting_date: "2026-10-07", posting_time: "12:00:00", selected_colour: "Navy" },
		permissions: { can_create: true, can_write: false, can_submit: false, can_cancel: true, can_print: true },
		record: {
			name: "CBE-CP-1", docstatus: 1, status: "Submitted", lot: "LOT-CP-1", warehouse: "CUT-STORE", item: "ITEM-CP-1", colour: "Navy",
			posting_date: "2026-10-07", posting_time: "12:00:00", printed_time: null, modified: "2026-10-07 12:00:00",
			inputs: [row], outputs: [{ ...row, bundle_no: 8 }], permissions: { can_write: false, can_submit: false, can_cancel: true, can_print: true },
		},
	}
}

async function mockCutBundleWorkspace(page) {
	await page.addInitScript(() => {
		window.sha256 = () => "signature"
		window.qz = {
			api: { setPromiseType() {}, setSha256Type() {} },
			websocket: { isActive: () => true, connect: async () => {} },
			printers: { find: async () => ["Zebra ZD220", "Zebra ZT230"] },
			configs: { create: (printer) => ({ printer }) },
			print: async () => true,
		}
	})
	await page.route("**/api/method/essdee_yrp.cut_panel_store.web_workspace.get_capabilities*", (route) => route.fulfill({
		status: 200, contentType: "application/json", body: JSON.stringify({ message: capabilities }),
	}))
	const cutBundleEditMetaFields = [
		{ fieldname: "lot", label: "Lot", fieldtype: "Link", options: "SD YRP Lot", in_list_view: 1 },
		{ fieldname: "item", label: "Item", fieldtype: "Link", options: "Item", in_list_view: 1 },
		{ fieldname: "warehouse", label: "Warehouse", fieldtype: "Link", options: "Supplier", in_list_view: 1 },
		{ fieldname: "posting_date", label: "Posting Date", fieldtype: "Date", in_list_view: 1 },
		{ fieldname: "printed_time", label: "Printed Time", fieldtype: "Datetime", in_list_view: 1 },
	]
	await page.route("**/api/method/frappe.desk.form.load.getdoctype*", (route) => route.fulfill({
		status: 200,
		contentType: "application/json",
		body: JSON.stringify({ docs: [{ name: "SD YRP Cut Bundle Edit", is_submittable: 1, fields: cutBundleEditMetaFields }] }),
	}))
	await page.route(USER_LISTVIEW_ROUTE, (route) => fulfillUserListview(route, cutBundleEditMetaFields, { isSubmittable: true }))
	await page.route("**/api/method/frappe.desk.reportview.get_count*", (route) => route.fulfill({
		status: 200, contentType: "application/json", body: JSON.stringify({ message: 1 }),
	}))
	await page.route("**/api/resource/SD%20YRP%20Cut%20Bundle%20Edit*", (route) => route.fulfill({
		status: 200, contentType: "application/json", body: JSON.stringify({ data: [{ name: "CBE-CP-1", lot: "LOT-CP-1", item: "ITEM-CP-1", warehouse: "CUT-STORE", posting_date: "2026-10-07", printed_time: null, docstatus: 1, modified: "2026-10-07 12:00:00" }] }),
	}))
	await page.route("**/api/method/essdee_yrp.cut_panel_store.cut_bundle_workspace.get_cut_bundle_editor*", (route) => route.fulfill({
		status: 200, contentType: "application/json", body: JSON.stringify({ message: cutBundleEditorFixture() }),
	}))
	await page.route("**/api/method/essdee_yrp.cut_panel_store.cut_bundle_workspace.get_cut_bundle_print_data*", (route) => route.fulfill({
		status: 200, contentType: "application/json", body: JSON.stringify({ message: { name: "CBE-CP-1", printer: "Zebra ZD220", zpl: "^XA^XZ", expected_modified: "2026-10-07 12:00:00", confirmation_token: "TOKEN" } }),
	}))
	await page.route("**/api/method/essdee_yrp.cut_panel_store.cut_bundle_workspace.confirm_cut_bundle_print*", (route) => route.fulfill({
		status: 200, contentType: "application/json", body: JSON.stringify({ message: { ...cutBundleEditorFixture().record, printed_time: "2026-10-07 12:30:00", permissions: { can_print: false } } }),
	}))
}

async function cutBundleEditSuite(page) {
	await page.setViewportSize({ width: 1440, height: 900 })
	await mockCutBundleWorkspace(page)
	await page.goto(`${SITE}/web/cut-panel-store/cut-bundle-edits`, { waitUntil: "domcontentloaded" })
	const list = page.locator(".cut-bundle-edits .common-list-view")
	await list.waitFor({ timeout: 20_000 })
	for (const label of ["Lot", "Item", "Warehouse", "Posting Date", "Printed Time", "Status"]) {
		assert(await list.getByRole("columnheader", { name: label, exact: true }).count() === 1, `Cut Bundle Edit list omits ${label}`)
	}
	const statusTabs = list.getByRole("navigation", { name: "Status filters" })
	assert(await statusTabs.isVisible(), "Cut Bundle Edit list does not infer document status tabs")
	for (const status of ["All", "Draft", "Submitted", "Cancelled"]) {
		assert(await statusTabs.getByRole("button", { name: new RegExp(`^${status}\\s`) }).count() === 1, `Cut Bundle Edit status filters omit ${status}`)
	}
	assert(await page.getByRole("button", { name: "Create Cut Bundle Edit", exact: true }).count() === 1, "Cut Bundle Edit create action is missing")
	assert(await list.locator(".p-selection-column").count() === 0, "Cut Bundle Edit exposes unsafe generic bulk actions")
	await list.locator(".premium-list-table").getByText("CBE-CP-1", { exact: true }).click()
	const dialog = page.locator(".cut-bundle-edit-dialog:visible")
	await dialog.waitFor({ timeout: 20_000 })
	assert(await dialog.locator(".p-dialog-maximize-button").count() === 1, "Cut Bundle Edit popup is not maximizable")
	for (const label of ["Lot", "Warehouse", "Item", "Posting Date", "Posting Time", "Colour"]) {
		assert(await dialog.getByText(label, { exact: true }).count() >= 1, `Cut Bundle Edit omits ${label}`)
	}
	await dialog.getByRole("region", { name: "Input bundles", exact: true }).waitFor({ timeout: 20_000 })
	assert(await dialog.getByRole("region", { name: "Input bundles", exact: true }).count() === 1, "Cut Bundle Edit input table is missing")
	assert(await dialog.getByRole("region", { name: "Output bundles", exact: true }).count() === 1, "Cut Bundle Edit output table is missing")
	assert(await dialog.getByRole("button", { name: "Cancel Document", exact: true }).count() === 1, "Cut Bundle Edit cancel action is missing")
	await dialog.getByRole("button", { name: "Print Labels", exact: true }).click()
	const printer = page.locator(".cut-panel-printer-dialog:visible")
	await printer.waitFor()
	assert(await printer.getByText("Zebra ZD220", { exact: true }).count() >= 1, "QZ printers were not loaded")
	await printer.getByRole("button", { name: "Print", exact: true }).click()
	await dialog.getByText("07-10-2026 12:30", { exact: false }).waitFor()

	await page.setViewportSize({ width: 390, height: 844 })
	const geometry = await dialog.evaluate((element) => {
		const rect = element.getBoundingClientRect()
		return { left: rect.left, right: rect.right, viewport: window.innerWidth }
	})
	assert(geometry.left >= 0 && geometry.right <= geometry.viewport + 1, `Cut Bundle Edit popup escapes mobile viewport: ${JSON.stringify(geometry)}`)
	const source = readFileSync(new URL("../frontend/src/departments/cut-panel-store/CutBundleEditDialog.vue", import.meta.url), "utf8")
	assert(source.includes("DocumentErrorDialog"), "Cut Bundle Edit errors do not use the shared popup")
	assert(source.includes("Add output") && source.includes("Split panels"), "Cut Bundle Edit omits output add/split actions")
}

function boxStickerRows(printedQuantity = 0) {
	return [
		{ name: "BSP-ROW-S", size: "S", mrp: 125, quantity: 10, printed_quantity: printedQuantity, allow_excess_quantity: 0, allow_excess_percentage: 10, allowed_quantity: 11, remaining_quantity: 11 - printedQuantity },
		{ name: "BSP-ROW-M", size: "M", mrp: 135, quantity: 5, printed_quantity: 0, allow_excess_quantity: 1, allow_excess_percentage: 0, allowed_quantity: null, remaining_quantity: null },
	]
}

function boxStickerRecord({ name = "BSP-CP-1", docstatus = 1, printedQuantity = 0, fgItem = "FG-CP-1", displayName = "Finished Shirt", modified = "2026-10-07 14:00:00" } = {}) {
	const permissions = docstatus === 0
		? { can_write: true, can_submit: true, can_cancel: false, can_print: false }
		: docstatus === 1
			? { can_write: false, can_submit: false, can_cancel: true, can_print: true }
			: { can_write: false, can_submit: false, can_cancel: false, can_print: false }
	return {
		doctype: "SD YRP Box Sticker Print", name, docstatus,
		status: ({ 0: "Draft", 1: "Submitted", 2: "Cancelled" })[docstatus],
		lot: name === "BSP-NEW" ? "LOT-NEW" : "LOT-CP-1", fg_item: fgItem, size: "Trial", use_item_name: 0, display_name: displayName,
		print_format: "BOX-LABEL", piece_per_box: 10, modified,
		rows: boxStickerRows(printedQuantity), permissions,
	}
}

async function mockBoxStickerWorkspace(page) {
	let activeRecord = boxStickerRecord({ name: "BSP-NEW", docstatus: 0, fgItem: "FG-NEW", displayName: "New Shirt", modified: "2026-10-07 14:10:00" })
	let pendingPrintedQuantity = 0
	let sourcePreviewCount = 0
	let saveCount = 0
	let submitCount = 0
	let cancelCount = 0
	let reserveCount = 0
	let recoveryCount = 0
	let confirmCount = 0
	let rollbackCount = 0
	let failNextReserve = false
	let failNextConfirm = false
	let failNextRollback = false
	let activeReservation = null
	const reserveRequestIds = []
	let lastSave = null
	await page.addInitScript(() => {
		window.sha256 = () => "signature"
		window.__boxQzPrintCount = 0
		window.qz = {
			api: { setPromiseType() {}, setSha256Type() {} }, websocket: { isActive: () => true, connect: async () => {} },
			printers: { find: async () => ["Zebra ZD220", "Office Laser"] }, configs: { create: (printer) => ({ printer }) }, print: async () => { window.__boxQzPrintCount += 1; return true },
		}
	})
	await page.route("**/api/method/essdee_yrp.cut_panel_store.web_workspace.get_capabilities*", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: capabilities }) }))
	const boxStickerMetaFields = [
		{ fieldname: "lot", label: "Lot", fieldtype: "Link", options: "SD YRP Lot", in_list_view: 1 },
		{ fieldname: "fg_item", label: "Item", fieldtype: "Link", options: "SD YRP FG Item Master", in_list_view: 1 },
		{ fieldname: "print_format", label: "Print Format", fieldtype: "Link", options: "YRP ZPL Raw Print Format", in_list_view: 1 },
	]
	await page.route("**/api/method/frappe.desk.form.load.getdoctype*", (route) => route.fulfill({
		status: 200, contentType: "application/json", body: JSON.stringify({ docs: [{ name: "SD YRP Box Sticker Print", is_submittable: 1, fields: boxStickerMetaFields }] }),
	}))
	await page.route(USER_LISTVIEW_ROUTE, (route) => fulfillUserListview(route, boxStickerMetaFields, { isSubmittable: true }))
	await page.route("**/api/method/frappe.desk.reportview.get_count*", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: 1 }) }))
	await page.route("**/api/resource/SD%20YRP%20Box%20Sticker%20Print*", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data: [{ name: "BSP-CP-1", lot: "LOT-CP-1", fg_item: "FG-CP-1", print_format: "BOX-LABEL", docstatus: 1, modified: "2026-10-07 14:00:00" }] }) }))
	await page.route("**/api/method/essdee_yrp.api.link_search.link_search*", (route) => {
		const { doctype } = route.request().postDataJSON()
		const rows = doctype === "SD YRP FG Item Master"
			? [{ name: "FG-NEW", label: "New Shirt" }]
			: doctype === "SD YRP Lot"
				? [{ name: "LOT-NEW", label: "LOT-NEW" }]
				: [{ name: "BOX-LABEL", label: "BOX-LABEL" }]
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: rows }) })
	})
	await page.route("**/api/method/essdee_yrp.cut_panel_store.box_sticker_workspace.get_box_sticker_editor*", (route) => {
		const { name = "" } = route.request().postDataJSON()
		const record = name === "BSP-CP-1" ? boxStickerRecord() : name === "BSP-NEW" ? activeRecord : null
		const payload = record
			? { context: { lot: record.lot, fg_item: record.fg_item, display_name: record.display_name }, defaults: {}, permissions: { can_create: true }, record }
			: {
				context: { lot: "LOT-NEW", fg_item: "FG-OLD", display_name: "Old Shirt" },
				defaults: { lot: "LOT-NEW", fg_item: "FG-OLD", size: "", use_item_name: 0, print_format: "BOX-LABEL", rows: boxStickerRows() },
				permissions: { can_create: true }, record: null,
			}
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: payload }) })
	})
	await page.route("**/api/method/essdee_yrp.cut_panel_store.box_sticker_workspace.preview_box_sticker_source*", (route) => {
		sourcePreviewCount += 1
		const { fg_item: fgItem } = route.request().postDataJSON()
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: {
			context: { lot: "LOT-NEW", fg_item: fgItem, display_name: fgItem === "FG-NEW" ? "New Shirt" : "Old Shirt" },
			rows: boxStickerRows(), defaults: {},
		} }) })
	})
	await page.route("**/api/method/essdee_yrp.cut_panel_store.box_sticker_workspace.save_box_sticker*", (route) => {
		saveCount += 1
		lastSave = route.request().postDataJSON()
		activeRecord = boxStickerRecord({ name: "BSP-NEW", docstatus: 0, fgItem: lastSave.values.fg_item, displayName: "New Shirt", modified: "2026-10-07 14:10:00" })
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: activeRecord }) })
	})
	await page.route("**/api/method/essdee_yrp.cut_panel_store.box_sticker_workspace.execute_box_sticker_command*", (route) => {
		const { command } = route.request().postDataJSON()
		if (command === "submit") {
			submitCount += 1
			activeRecord = boxStickerRecord({ name: "BSP-NEW", docstatus: 1, fgItem: "FG-NEW", displayName: "New Shirt", modified: "2026-10-07 14:20:00" })
		} else if (command === "cancel") {
			cancelCount += 1
			activeRecord = boxStickerRecord({ name: "BSP-NEW", docstatus: 2, printedQuantity: activeRecord.rows[0].printed_quantity, fgItem: "FG-NEW", displayName: "New Shirt", modified: "2026-10-07 14:40:00" })
		}
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: activeRecord }) })
	})
	await page.route("**/api/method/essdee_yrp.cut_panel_store.box_sticker_workspace.get_box_sticker_preview*", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: { image_url: "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==", code: "^XA^XZ", width: 4, height: 6 } }) }))
	await page.route("**/api/method/essdee_yrp.cut_panel_store.box_sticker_workspace.get_configured_box_sticker_printers*", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: ["Zebra ZD220"] }) }))
	await page.route("**/api/method/essdee_yrp.cut_panel_store.box_sticker_workspace.reserve_box_sticker_print*", (route) => {
		reserveCount += 1
		const { request_id: requestId, rows } = route.request().postDataJSON()
		reserveRequestIds.push(requestId)
		pendingPrintedQuantity = activeRecord.rows[0].printed_quantity + Number(rows.find((row) => row.doc_name === "BSP-ROW-S")?.quantity || 0)
		activeReservation = { requestId, reservation: `BOX-TOKEN-${reserveCount}`, state: "Active", zpl: "^XA^XZ" }
		if (failNextReserve) {
			failNextReserve = false
			return route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ message: "Reservation response was interrupted" }) })
		}
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: { reservation: activeReservation.reservation, zpl: activeReservation.zpl, raw: activeReservation.zpl, expected_modified: activeRecord.modified, record: activeRecord } }) })
	})
	await page.route("**/api/method/essdee_yrp.cut_panel_store.box_sticker_workspace.get_box_sticker_print_recovery*", (route) => {
		recoveryCount += 1
		const { request_id: requestId } = route.request().postDataJSON()
		if (!activeReservation || activeReservation.requestId !== requestId) return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: { state: "Missing", reservation: requestId } }) })
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: { ...activeReservation, raw: activeReservation.zpl, record: activeRecord } }) })
	})
	await page.route("**/api/method/essdee_yrp.cut_panel_store.box_sticker_workspace.confirm_box_sticker_print*", (route) => {
		confirmCount += 1
		if (failNextConfirm) {
			failNextConfirm = false
			return route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ message: "Confirmation response was interrupted" }) })
		}
		activeRecord = boxStickerRecord({ name: "BSP-NEW", docstatus: 1, printedQuantity: pendingPrintedQuantity, fgItem: "FG-NEW", displayName: "New Shirt", modified: "2026-10-07 14:30:00" })
		if (activeReservation) activeReservation.state = "Confirmed"
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: { confirmed: true, already_confirmed: false, reservation: activeReservation?.reservation, record: activeRecord } }) })
	})
	await page.route("**/api/method/essdee_yrp.cut_panel_store.box_sticker_workspace.rollback_box_sticker_print*", (route) => {
		rollbackCount += 1
		if (failNextRollback) {
			failNextRollback = false
			return route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ message: "Rollback response was interrupted" }) })
		}
		pendingPrintedQuantity = activeRecord.rows[0].printed_quantity
		if (activeReservation) activeReservation.state = "Rolled Back"
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: { rolled_back: true, already_rolled_back: false, reservation: activeReservation?.reservation, record: activeRecord } }) })
	})
	return {
		sourcePreviewCount: () => sourcePreviewCount,
		saveCount: () => saveCount,
		submitCount: () => submitCount,
		cancelCount: () => cancelCount,
		reserveCount: () => reserveCount,
		recoveryCount: () => recoveryCount,
		confirmCount: () => confirmCount,
		rollbackCount: () => rollbackCount,
		reserveRequestIds: () => [...reserveRequestIds],
		failNextReserve: () => { failNextReserve = true },
		failNextConfirm: () => { failNextConfirm = true },
		failNextRollback: () => { failNextRollback = true },
		lastSave: () => lastSave,
	}
}

async function enterPrimeNumber(page, input, value) {
	await input.click()
	await input.press("Control+A")
	await page.keyboard.type(String(value))
	await input.press("Tab")
}

async function boxStickerSuite(page) {
	await page.setViewportSize({ width: 1440, height: 900 })
	const calls = await mockBoxStickerWorkspace(page)
	await page.goto(`${SITE}/web/cut-panel-store/box-sticker-prints`, { waitUntil: "domcontentloaded" })
	const list = page.locator(".box-sticker-prints .common-list-view")
	await list.waitFor({ timeout: 20_000 })
	const headers = (await list.getByRole("columnheader").allTextContents()).map((label) => label.trim())
	for (const label of ["Lot", "Item", "Print Format", "Status"]) assert(headers.includes(label), `Box Sticker list omits ${label}; headers=${JSON.stringify(headers)}`)
	assert(await page.getByRole("button", { name: "Create Box Sticker Print", exact: true }).count() === 1, "Box Sticker create action is missing")
	await page.setViewportSize({ width: 390, height: 844 })
	const mobileRecord = list.locator(".mobile-list-record").filter({ hasText: "BSP-CP-1" })
	await mobileRecord.waitFor()
	assert(await mobileRecord.getByText("Submitted", { exact: true }).count() === 1, "Mobile Box Sticker card bypassed the document-status renderer")
	const mobileOpen = mobileRecord.getByRole("button", { name: "Open BSP-CP-1", exact: true })
	assert(await mobileOpen.count() === 1, "Mobile Box Sticker card has no accessible open action")
	await mobileOpen.click()
	await page.setViewportSize({ width: 1440, height: 900 })
	const dialog = page.locator(".box-sticker-print-dialog:visible")
	await dialog.waitFor({ timeout: 20_000 })
	assert(await dialog.locator(".p-dialog-maximize-button").count() === 1, "Box Sticker popup is not maximizable")
	for (const label of ["Lot", "FG Item", "Size", "Print Format", "Use Item Name", "Display Name"]) assert(await dialog.getByText(label, { exact: true }).count() >= 1, `Box Sticker editor omits ${label}`)
	assert(await dialog.getByRole("region", { name: "Box Sticker quantities" }).count() === 1, "Box Sticker size table is missing")
	assert(await dialog.getByRole("img", { name: /Label preview/ }).count() === 1, "Box Sticker preview image is missing")
	assert(await dialog.getByRole("button", { name: "Print Labels", exact: true }).isDisabled(), "Zero print quantity must keep Print Labels disabled")
	await dialog.locator(".p-dialog-footer").getByRole("button", { name: "Close", exact: true }).click()
	await dialog.waitFor({ state: "hidden" })

	await page.getByRole("button", { name: "Create Box Sticker Print", exact: true }).click()
	await dialog.waitFor({ timeout: 20_000 })
	await dialog.getByText("Draft", { exact: true }).waitFor()
	assert(await dialog.getByRole("button", { name: "Save", exact: true }).count() === 1, "New Box Sticker draft does not expose Save")
	assert(await dialog.getByRole("button", { name: "Print Labels", exact: true }).count() === 0, "Draft Box Sticker exposes printing")
	await dialog.locator(".box-sticker-field input").fill("Dirty close check")
	await dialog.locator(".p-dialog-footer").getByRole("button", { name: "Close", exact: true }).click()
	let confirmation = page.locator(".document-confirmation-shell:visible")
	await confirmation.getByText("Discard unsaved changes?", { exact: true }).waitFor()
	assert(await dialog.count() === 1, "Dirty close dismissed the Box Sticker dialog without confirmation")
	await confirmation.getByRole("button", { name: "Keep Document", exact: true }).click()
	await confirmation.waitFor({ state: "hidden" })

	await dialog.getByRole("button", { name: "Show FG Item options", exact: true }).click()
	await page.locator(".p-autocomplete-option").filter({ hasText: "New Shirt" }).click()
	confirmation = page.locator(".document-confirmation-shell:visible")
	await confirmation.getByText("Replace size rows?", { exact: true }).waitFor()
	await confirmation.getByRole("button", { name: "Replace Rows", exact: true }).click()
	await dialog.getByText("New Shirt", { exact: true }).waitFor()
	assert(await dialog.getByText("Old Shirt", { exact: true }).count() === 0, "Display Name remained stale after changing FG Item")
	assert(calls.sourcePreviewCount() === 1, `FG Item change refreshed source ${calls.sourcePreviewCount()} times instead of once`)

	const quantityControl = dialog.getByRole("spinbutton", { name: "Total quantity for S" })
	const excessControl = dialog.getByRole("spinbutton", { name: "Excess percentage for S" })
	assert(await quantityControl.isEnabled(), "Draft total quantity control is disabled")
	assert(await excessControl.isEnabled(), "Draft excess percentage control is disabled")
	assert(await dialog.getByRole("checkbox", { name: "Allow excess for S" }).isDisabled(), "Server-owned Allow Excess control is editable")
	assert(await dialog.getByRole("spinbutton", { name: "Excess percentage for M" }).isDisabled(), "Unlimited row exposes an irrelevant excess percentage")
	assert(await dialog.getByRole("spinbutton", { name: "Print quantity for S" }).isDisabled(), "Draft print quantity is editable")
	assert(await dialog.getByText("Unlimited", { exact: true }).count() === 2, "Unlimited authoritative limits are not rendered explicitly")
	await enterPrimeNumber(page, quantityControl, 12)
	await dialog.getByRole("button", { name: "Fetch Size Rows", exact: true }).click()
	confirmation = page.locator(".document-confirmation-shell:visible")
	await confirmation.getByRole("button", { name: "Refresh Rows", exact: true }).click()
	await page.waitForFunction(() => document.querySelector('[aria-label="Total quantity for S"]')?.value === "10")
	assert(calls.sourcePreviewCount() === 2, `Explicit source refresh called the server ${calls.sourcePreviewCount()} times in total`)

	await dialog.getByRole("button", { name: "Save", exact: true }).click()
	await dialog.getByText("BSP-NEW", { exact: false }).waitFor()
	assert(calls.saveCount() === 1, `Draft save ran ${calls.saveCount()} times`)
	const savedRows = calls.lastSave()?.values?.rows || []
	assert(savedRows.length === 2, "Draft save omitted authoritative size rows")
	assert(savedRows.every((row) => !("mrp" in row) && !("printed_quantity" in row) && !("allow_excess_quantity" in row)), "Draft save sent server-owned row fields")
	await dialog.getByRole("button", { name: "Submit", exact: true }).click()
	confirmation = page.locator(".document-confirmation-shell:visible")
	await confirmation.getByRole("button", { name: "Submit", exact: true }).click()
	await dialog.getByText("Submitted", { exact: true }).waitFor()
	assert(calls.submitCount() === 1, `Submit command ran ${calls.submitCount()} times`)
	const printButton = dialog.getByRole("button", { name: "Print Labels", exact: true })
	assert(await printButton.isDisabled(), "Zero print quantity enabled Print Labels after submit")

	await page.setViewportSize({ width: 390, height: 844 })
	const geometry = await dialog.evaluate((element) => {
		const rect = element.getBoundingClientRect()
		const table = element.querySelector(".box-sticker-table-wrap")?.getBoundingClientRect()
		return { left: rect.left, right: rect.right, tableLeft: table?.left, tableRight: table?.right, viewport: window.innerWidth }
	})
	assert(geometry.left >= 0 && geometry.right <= geometry.viewport + 1, `Box Sticker popup escapes mobile viewport: ${JSON.stringify(geometry)}`)
	assert(geometry.tableLeft >= geometry.left && geometry.tableRight <= geometry.right + 1, `Box Sticker table is not contained on mobile: ${JSON.stringify(geometry)}`)
	await page.setViewportSize({ width: 1440, height: 900 })

	let quantity = dialog.getByRole("spinbutton", { name: "Print quantity for S" })
	await enterPrimeNumber(page, quantity, 3)
	await printButton.waitFor()
	assert(await printButton.isEnabled(), "Positive print quantity did not enable Print Labels")
	calls.failNextReserve()
	await printButton.click()
	let printer = page.locator(".cut-panel-printer-dialog:visible")
	await printer.waitFor()
	await printer.getByText("Zebra ZD220", { exact: true }).waitFor({ timeout: 20_000 })
	assert(await printer.getByText("Zebra ZD220", { exact: true }).count() >= 1, "Configured Box Sticker printer is missing")
	assert(await printer.getByText("Office Laser", { exact: true }).count() === 0, "Unconfigured QZ printer was exposed")
	assert(await printer.getByText(/^Printer Resolution/).count() === 1, "Box Sticker resolution selection is missing")
	await printer.getByRole("button", { name: "Print", exact: true }).click()
	let errorDialog = page.locator(".document-error-dialog:visible")
	await errorDialog.waitFor({ timeout: 20_000 })
	assert(calls.reserveCount() === 1 && calls.confirmCount() === 0 && calls.rollbackCount() === 0, "Ambiguous reserve failure advanced the print transaction")
	await errorDialog.getByRole("button", { name: "OK", exact: true }).click()
	await dialog.getByRole("button", { name: "Print Labels", exact: true }).waitFor({ state: "detached" })
	const resumePrint = dialog.getByRole("button", { name: "Resume Print", exact: true })
	await resumePrint.waitFor()
	calls.failNextConfirm()
	await resumePrint.click()
	errorDialog = page.locator(".document-error-dialog:visible")
	await errorDialog.waitFor({ timeout: 20_000 })
	assert(calls.reserveCount() === 1 && calls.recoveryCount() === 1 && calls.confirmCount() === 1 && calls.rollbackCount() === 0, "Interrupted reservation recovery did not reuse the durable reservation")
	assert(await page.evaluate(() => window.__boxQzPrintCount) === 1, "The successful QZ job was not counted exactly once")
	const pendingConfirmations = await page.evaluate(() => Object.fromEntries(Object.entries(window.sessionStorage).filter(([key]) => key.startsWith("essdee-yrp:box-sticker-confirmation:"))))
	assert(Object.keys(pendingConfirmations).length === 1, `Ambiguous confirmation was not persisted for safe recovery: ${JSON.stringify(pendingConfirmations)}`)
	await errorDialog.getByRole("button", { name: "OK", exact: true }).click()
	await dialog.getByRole("button", { name: "Print Labels", exact: true }).waitFor({ state: "detached" })
	assert(await dialog.getByRole("button", { name: "Print Labels", exact: true }).count() === 0, "Print Labels remains available while confirmation is pending")
	const retryConfirmation = dialog.getByRole("button", { name: "Retry Confirmation", exact: true })
	await retryConfirmation.waitFor()
	await retryConfirmation.click()
	await dialog.getByText("Printed 3", { exact: false }).waitFor()
	const successfulRequestIds = calls.reserveRequestIds()
	assert(successfulRequestIds.length === 1 && successfulRequestIds[0], `Interrupted reserve created a second request: ${JSON.stringify(successfulRequestIds)}`)
	assert(await page.evaluate(() => window.__boxQzPrintCount) === 1, "Retry Confirmation physically printed the labels again")
	assert(calls.reserveCount() === 1 && calls.confirmCount() === 2 && calls.rollbackCount() === 0, `Successful Box Sticker recovery counts are reserve=${calls.reserveCount()}, confirm=${calls.confirmCount()}, rollback=${calls.rollbackCount()}`)

	quantity = dialog.getByRole("spinbutton", { name: "Print quantity for S" })
	await enterPrimeNumber(page, quantity, 2)
	assert(await printButton.isEnabled(), "Second positive print quantity did not enable Print Labels")
	await page.evaluate(() => { window.qz.print = async () => { throw new Error("QZ rejected job") } })
	calls.failNextRollback()
	await printButton.click()
	printer = page.locator(".cut-panel-printer-dialog:visible")
	await printer.waitFor()
	await printer.getByText("Zebra ZD220", { exact: true }).waitFor({ timeout: 20_000 })
	await printer.getByRole("button", { name: "Print", exact: true }).click()
	errorDialog = page.locator(".document-error-dialog:visible")
	await errorDialog.waitFor({ timeout: 20_000 })
	assert(calls.reserveCount() === 2, `Expected two reserve attempts, got ${calls.reserveCount()}`)
	assert(calls.confirmCount() === 2, `QZ failure unexpectedly added a confirmation; total=${calls.confirmCount()}`)
	assert(calls.rollbackCount() === 1, `QZ failure made ${calls.rollbackCount()} initial rollback attempts instead of once`)
	assert(calls.reserveRequestIds()[1] !== successfulRequestIds[0], "A new print intent reused the cleared request_id")
	await errorDialog.getByRole("button", { name: "OK", exact: true }).click()
	assert(await dialog.getByRole("button", { name: "Print Labels", exact: true }).count() === 0, "Print Labels is available while rollback is pending")
	const retryRollback = dialog.getByRole("button", { name: "Retry Rollback", exact: true })
	await retryRollback.waitFor()
	await retryRollback.click()
	assert(calls.rollbackCount() === 2, `Retry Rollback ran ${calls.rollbackCount()} total rollback attempts instead of two`)
	await printButton.waitFor()

	await dialog.getByRole("button", { name: "Cancel Document", exact: true }).click()
	confirmation = page.locator(".document-confirmation-shell:visible")
	await confirmation.getByRole("button", { name: "Cancel Document", exact: true }).click()
	await dialog.getByText("Cancelled", { exact: true }).waitFor()
	assert(calls.cancelCount() === 1, `Cancel command ran ${calls.cancelCount()} times`)
	assert(await dialog.getByRole("button", { name: "Print Labels", exact: true }).count() === 0, "Cancelled Box Sticker remains printable")

	await dialog.locator(".p-dialog-footer").getByRole("button", { name: "Close", exact: true }).click()
	await dialog.waitFor({ state: "hidden" })
	await page.evaluate(() => {
		window.sessionStorage.setItem("essdee-yrp:box-sticker-confirmation:BSP-CP-1", JSON.stringify({
			document: "BSP-CP-1", requestId: "request-manual-1234", reservation: "BOX-TOKEN-MANUAL",
			phase: "printing", rows: [{ doc_name: "BSP-ROW-S", quantity: 1 }],
			printer: "Zebra ZD220", printerType: "300dpi", expectedModified: "2026-10-07 14:00:00",
		}))
	})
	await list.locator(".premium-list-table").getByText("BSP-CP-1", { exact: true }).click()
	await dialog.waitFor({ timeout: 20_000 })
	await dialog.getByRole("button", { name: "Confirm Printed", exact: true }).click()
	confirmation = page.locator(".document-confirmation-shell:visible")
	await confirmation.getByText("Were the labels printed?", { exact: true }).waitFor()
	await confirmation.getByText(/cannot be undone/).waitFor()
	assert(calls.confirmCount() === 2, "Confirm Printed mutated the reservation before application confirmation")
	await confirmation.getByRole("button", { name: "Go Back", exact: true }).click()
	await dialog.getByRole("button", { name: "Release Reservation", exact: true }).click()
	confirmation = page.locator(".document-confirmation-shell:visible")
	await confirmation.getByText("Were the labels not printed?", { exact: true }).waitFor()
	await confirmation.getByText(/restores the reserved printed quantities/).waitFor()
	assert(calls.rollbackCount() === 2, "Release Reservation mutated quantities before application confirmation")
	await confirmation.getByRole("button", { name: "Go Back", exact: true }).click()
	await page.evaluate(() => window.sessionStorage.removeItem("essdee-yrp:box-sticker-confirmation:BSP-CP-1"))
	const source = readFileSync(new URL("../frontend/src/departments/cut-panel-store/BoxStickerPrintDialog.vue", import.meta.url), "utf8")
	assert(source.includes("DocumentErrorDialog") && !source.includes("window.confirm"), "Box Sticker errors/confirmations do not use application dialogs")
}

function excelStickerRecord({ name = "ESP-CP-1", docstatus = 1, modified = "2026-10-07 15:00:00" } = {}) {
	const submitted = docstatus === 1
	return {
		doctype: "YRP Excel Sticker Print",
		name,
		docstatus,
		status: ({ 0: "Draft", 1: "Submitted", 2: "Cancelled" })[docstatus],
		excel_file: "/private/files/stickers.xlsx",
		print_format: "EXCEL-LABEL",
		modified,
		row_count: submitted ? 2 : 0,
		columns: submitted ? ["sku", "description", "print_quantity"] : [],
		sample_rows: submitted ? [
			{ sku: "SKU-001", description: "Navy / M", print_quantity: 3 },
			{ sku: "SKU-002", description: "Green / L", print_quantity: 1 },
		] : [],
		sample: {
			columns: submitted ? ["sku", "description", "print_quantity"] : [],
			rows: submitted ? [
				{ sku: "SKU-001", description: "Navy / M", print_quantity: 3 },
				{ sku: "SKU-002", description: "Green / L", print_quantity: 1 },
			] : [],
			truncated: false,
		},
		permissions: docstatus === 0
			? { can_write: true, can_submit: true, can_cancel: false, can_print: false }
			: docstatus === 1
				? { can_write: false, can_submit: false, can_cancel: false, can_print: true }
				: { can_write: false, can_submit: false, can_cancel: false, can_print: false },
	}
}

async function mockExcelStickerWorkspace(page) {
	let activeRecord = excelStickerRecord({ name: "ESP-NEW", docstatus: 0, modified: "2026-10-07 15:10:00" })
	let uploadCount = 0
	let saveCount = 0
	let submitCount = 0
	let printDataCount = 0
	let lastUpload = null
	let lastSave = null
	let lastPrintData = null
	let failNextSubmit = false
	await page.addInitScript(() => {
		window.sha256 = () => "signature"
		window.__excelQzPrintCount = 0
		window.qz = {
			api: { setPromiseType() {}, setSha256Type() {} },
			websocket: { isActive: () => true, connect: async () => {} },
			printers: { find: async () => ["Zebra ZD220", "Excel Office Printer"] },
			configs: { create: (printer) => ({ printer }) },
			print: async () => { window.__excelQzPrintCount += 1; return true },
		}
	})
	await page.route("**/api/method/essdee_yrp.cut_panel_store.web_workspace.get_capabilities*", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: capabilities }) }))
	const excelStickerMetaFields = [
		{ fieldname: "excel_file", label: "Excel File", fieldtype: "Attach", in_list_view: 1 },
		{ fieldname: "print_format", label: "Print Format", fieldtype: "Link", options: "YRP ZPL Raw Print Format", in_list_view: 1 },
		{ fieldname: "modified", label: "Modified", fieldtype: "Datetime", in_list_view: 1 },
	]
	await page.route("**/api/method/frappe.desk.form.load.getdoctype*", (route) => route.fulfill({
		status: 200, contentType: "application/json", body: JSON.stringify({ docs: [{ name: "YRP Excel Sticker Print", is_submittable: 1, fields: excelStickerMetaFields }] }),
	}))
	await page.route(USER_LISTVIEW_ROUTE, (route) => fulfillUserListview(route, excelStickerMetaFields, { isSubmittable: true }))
	await page.route("**/api/method/frappe.desk.reportview.get_count*", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: 1 }) }))
	await page.route("**/api/resource/YRP%20Excel%20Sticker%20Print*", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data: [{ name: "ESP-CP-1", excel_file: "/private/files/stickers.xlsx", print_format: "EXCEL-LABEL", docstatus: 1, modified: "2026-10-07 15:00:00" }] }) }))
	await page.route("**/api/method/essdee_yrp.api.link_search.link_search*", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: [{ name: "EXCEL-LABEL", label: "EXCEL-LABEL" }] }) }))
	await page.route("**/api/method/upload_file*", async (route) => {
		uploadCount += 1
		lastUpload = {
			headers: route.request().headers(),
			body: route.request().postDataBuffer()?.toString("utf8") || "",
		}
		await new Promise((resolve) => setTimeout(resolve, 450))
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: {
			name: "FILE-EXCEL-1", file_name: "stickers.xlsx", file_url: "/private/files/stickers.xlsx", is_private: 1,
		} }) })
	})
	await page.route("**/api/method/essdee_yrp.cut_panel_store.excel_sticker_workspace.get_excel_sticker_editor*", (route) => {
		const { name = "" } = route.request().postDataJSON()
		const record = name === "ESP-CP-1" ? excelStickerRecord() : name === "ESP-NEW" ? activeRecord : null
		const payload = record
			? { record, defaults: { excel_file: record.excel_file, print_format: record.print_format }, permissions: record.permissions }
			: {
				record: null,
				defaults: { excel_file: null, print_format: "EXCEL-LABEL", temporary_name: "new-yrp-excel-sticker-print-TESTTOKEN" },
				upload: { doctype: "YRP Excel Sticker Print", docname: "new-yrp-excel-sticker-print-TESTTOKEN", fieldname: "excel_file", is_private: 1 },
				permissions: { can_create: true, can_write: false, can_submit: false, can_cancel: false, can_print: false },
			}
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: payload }) })
	})
	await page.route("**/api/method/essdee_yrp.cut_panel_store.excel_sticker_workspace.save_excel_sticker*", (route) => {
		saveCount += 1
		lastSave = route.request().postDataJSON()
		activeRecord = excelStickerRecord({ name: "ESP-NEW", docstatus: 0, modified: "2026-10-07 15:10:00" })
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: activeRecord }) })
	})
	await page.route("**/api/method/essdee_yrp.cut_panel_store.excel_sticker_workspace.execute_excel_sticker_command*", (route) => {
		const { command } = route.request().postDataJSON()
		if (command === "submit") {
			submitCount += 1
			if (failNextSubmit) {
				failNextSubmit = false
				return route.fulfill({ status: 422, contentType: "application/json", body: JSON.stringify({ _server_messages: JSON.stringify([JSON.stringify({ message: "The Excel workbook could not be read. Upload a valid .xlsx file." })]) }) })
			}
			activeRecord = excelStickerRecord({ name: "ESP-NEW", docstatus: 1, modified: "2026-10-07 15:20:00" })
		}
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: activeRecord }) })
	})
	await page.route("**/api/method/essdee_yrp.cut_panel_store.excel_sticker_workspace.get_excel_sticker_preview*", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: {
		image_url: "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==", code: "^XA^XZ", width: 4, height: 6,
	} }) }))
	await page.route("**/api/method/essdee_yrp.cut_panel_store.excel_sticker_workspace.get_excel_sticker_print_data*", (route) => {
		printDataCount += 1
		lastPrintData = route.request().postDataJSON()
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: "^XA^FO10,10^FDExcel label^FS^XZ" }) })
	})
	return {
		uploadCount: () => uploadCount,
		saveCount: () => saveCount,
		submitCount: () => submitCount,
		printDataCount: () => printDataCount,
		lastUpload: () => lastUpload,
		lastSave: () => lastSave,
		lastPrintData: () => lastPrintData,
		failNextSubmit: () => { failNextSubmit = true },
	}
}

async function excelStickerSuite(page) {
	await page.setViewportSize({ width: 1440, height: 900 })
	const calls = await mockExcelStickerWorkspace(page)
	await page.goto(`${SITE}/web/cut-panel-store/excel-sticker-prints`, { waitUntil: "domcontentloaded" })
	const list = page.locator(".excel-sticker-prints .common-list-view")
	await list.waitFor({ timeout: 20_000 })
	const headers = (await list.getByRole("columnheader").allTextContents()).map((label) => label.trim())
	for (const label of ["Excel File", "Print Format", "Status", "Modified"]) assert(headers.includes(label), `Excel Sticker list omits ${label}; headers=${JSON.stringify(headers)}`)
	assert(await page.getByRole("button", { name: "Create Excel Sticker Print", exact: true }).count() === 1, "Excel Sticker create action is missing")

	await list.locator(".premium-list-table").getByText("ESP-CP-1", { exact: true }).click()
	const dialog = page.locator(".excel-sticker-print-dialog:visible")
	await dialog.waitFor({ timeout: 20_000 })
	assert(await dialog.locator(".p-dialog-maximize-button").count() === 1, "Excel Sticker popup is not maximizable")
	assert(await dialog.getByText("2 rows", { exact: true }).count() >= 1, "Submitted Excel row count is missing")
	for (const label of ["sku", "description", "print_quantity"]) assert(await dialog.getByRole("columnheader", { name: label, exact: true }).count() === 1, `Excel sample omits ${label}`)
	assert(await dialog.getByRole("img", { name: /Label preview/ }).count() === 1, "Submitted Excel preview image is missing")
	assert(await dialog.getByRole("button", { name: "Print Labels", exact: true }).count() === 1, "Submitted Excel document is not printable")
	assert(await dialog.getByRole("button", { name: "Cancel Document", exact: true }).count() === 0, "Excel Sticker exposes cancellation that its authoritative DocType does not permit")
	await dialog.locator(".p-dialog-footer").getByRole("button", { name: "Close", exact: true }).click()
	await dialog.waitFor({ state: "hidden" })

	await page.getByRole("button", { name: "Create Excel Sticker Print", exact: true }).click()
	await dialog.waitFor({ timeout: 20_000 })
	assert(await dialog.getByText("Excel File", { exact: true }).count() >= 1, "Excel File control is missing")
	assert(await dialog.getByText("Print Format", { exact: true }).count() >= 1, "Print Format control is missing")
	const saveButton = dialog.getByRole("button", { name: "Save", exact: true })
	assert(await saveButton.isDisabled(), "New Excel Sticker can be saved before upload")
	const fileInput = dialog.locator('input[type="file"]')
	const uploadPromise = fileInput.setInputFiles({ name: "stickers.xlsx", mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", buffer: Buffer.from("mock xlsx") })
	await dialog.locator(".excel-upload__progress").waitFor({ timeout: 5_000 })
	assert(await saveButton.isDisabled(), "Save remained enabled while Excel upload was in progress")
	await uploadPromise
	await dialog.locator(".excel-upload-field__control strong").getByText("stickers.xlsx", { exact: true }).waitFor()
	assert(calls.uploadCount() === 1, `Excel file uploaded ${calls.uploadCount()} times`)
	const upload = calls.lastUpload()
	assert(String(upload.headers["content-type"] || "").startsWith("multipart/form-data; boundary="), `Excel upload did not use multipart FormData: ${JSON.stringify(upload.headers)}`)
	assert(upload.headers["x-frappe-csrf-token"] !== undefined, "Excel upload omitted the CSRF header")
	for (const value of ["YRP Excel Sticker Print", "new-yrp-excel-sticker-print-TESTTOKEN", "excel_file"]) assert(upload.body.includes(value), `Excel upload omitted ${value}`)
	assert(upload.body.includes('name="is_private"') && upload.body.includes("1"), "Excel upload was not private")

	await saveButton.click()
	await dialog.getByText(/ESP-NEW/).waitFor()
	assert(calls.saveCount() === 1, `Excel draft save ran ${calls.saveCount()} times`)
	assert(calls.lastSave()?.values?.temporary_name === "new-yrp-excel-sticker-print-TESTTOKEN", "Excel draft save omitted its server-issued temporary name")
	assert(calls.lastSave()?.values?.excel_file === "/private/files/stickers.xlsx", "Excel draft save omitted the uploaded private file URL")

	calls.failNextSubmit()
	await dialog.getByRole("button", { name: "Submit", exact: true }).click()
	let confirmation = page.locator(".document-confirmation-shell:visible")
	await confirmation.getByRole("button", { name: "Submit", exact: true }).click()
	let errorDialog = page.locator(".document-error-dialog:visible")
	await errorDialog.getByText("The Excel workbook could not be read. Upload a valid .xlsx file.", { exact: true }).waitFor()
	assert(calls.submitCount() === 1, "Malformed Excel submit did not reach the lifecycle endpoint")
	assert(await dialog.getByText("Draft", { exact: true }).count() >= 1, "Malformed submit did not preserve the saved Draft")
	assert(await dialog.getByText("stickers.xlsx", { exact: true }).count() >= 1, "Malformed submit discarded the uploaded file")
	await errorDialog.getByRole("button", { name: "OK", exact: true }).click()

	await dialog.getByRole("button", { name: "Submit", exact: true }).click()
	confirmation = page.locator(".document-confirmation-shell:visible")
	await confirmation.getByRole("button", { name: "Submit", exact: true }).click()
	await dialog.getByText("Submitted", { exact: true }).waitFor()
	assert(calls.submitCount() === 2, `Excel submit retried ${calls.submitCount()} total times`)
	await dialog.getByLabel("Excel data sample").getByText("2 rows", { exact: true }).waitFor()

	await page.setViewportSize({ width: 390, height: 844 })
	const geometry = await dialog.evaluate((element) => {
		const rect = element.getBoundingClientRect()
		const table = element.querySelector(".excel-sticker-sample__wrap")?.getBoundingClientRect()
		return { left: rect.left, right: rect.right, tableLeft: table?.left, tableRight: table?.right, viewport: window.innerWidth }
	})
	assert(geometry.left >= 0 && geometry.right <= geometry.viewport + 1, `Excel Sticker popup escapes mobile viewport: ${JSON.stringify(geometry)}`)
	assert(geometry.tableLeft >= geometry.left && geometry.tableRight <= geometry.right + 1, `Excel sample is not contained on mobile: ${JSON.stringify(geometry)}`)
	await page.setViewportSize({ width: 1440, height: 900 })

	await dialog.getByRole("button", { name: "Print Labels", exact: true }).click()
	const printer = page.locator(".cut-panel-printer-dialog:visible")
	await printer.waitFor()
	assert(await printer.getByText(/^Printer Resolution/).count() === 1, "Excel Sticker resolution selection is missing")
	await printer.getByRole("button", { name: "Print", exact: true }).click()
	await printer.waitFor({ state: "hidden" })
	assert(calls.printDataCount() === 1, `Excel print data requested ${calls.printDataCount()} times`)
	assert(calls.lastPrintData()?.printer_type === "300dpi", `Excel print used the wrong resolution: ${JSON.stringify(calls.lastPrintData())}`)
	assert(await page.evaluate(() => window.__excelQzPrintCount) === 1, "Excel ZPL was not sent to QZ exactly once")

	const apiSource = readFileSync(new URL("../frontend/src/api/frappe.js", import.meta.url), "utf8")
	const source = readFileSync(new URL("../frontend/src/departments/cut-panel-store/ExcelStickerPrintDialog.vue", import.meta.url), "utf8")
	assert(apiSource.includes("FormData") && apiSource.includes("withCredentials") && !apiSource.includes('multipart/form-data"'), "Upload helper does not preserve the browser-generated multipart boundary")
	assert(source.includes("DocumentErrorDialog") && source.includes("DocumentConfirmationDialog") && !source.includes("window.confirm"), "Excel Sticker errors/confirmations do not use application dialogs")
}

async function reportSuite(page) {
	await page.setViewportSize({ width: 1440, height: 900 })
	const reportCapabilities = structuredClone(capabilities)
	reportCapabilities.sections.reports = {
		label: "Reports",
		can_read: true,
		can_create: false,
		reports: {
			stock_balance: { label: "Stock Balance", can_read: true },
			cut_bundle_balance: { label: "Cut Bundle Balance", can_read: true },
		},
	}
	let stockRuns = 0
	let bundleRuns = 0
	let lastBundleFilters = null
	await page.route("**/api/method/essdee_yrp.cut_panel_store.web_workspace.get_capabilities*", (route) => route.fulfill({
		status: 200, contentType: "application/json", body: JSON.stringify({ message: reportCapabilities }),
	}))
	await page.route("**/api/method/essdee_yrp.api.link_search.link_search*", (route) => route.fulfill({
		status: 200, contentType: "application/json", body: JSON.stringify({ message: [] }),
	}))
	await page.route("**/api/method/frappe.desk.query_report.run*", (route) => {
		stockRuns += 1
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: {
			columns: [
				{ fieldname: "item_code", label: "Item", fieldtype: "Link" },
				{ fieldname: "warehouse", label: "Warehouse", fieldtype: "Link" },
				{ fieldname: "bal_qty", label: "Balance Qty", fieldtype: "Float" },
			],
			result: [{ item_code: "CUT-PANEL-1", warehouse: "CUT-PANEL-STORE", bal_qty: 24 }],
		} }) })
	})
	await page.route("**/api/method/essdee_yrp.cut_panel_store.report_workspace.get_cut_bundle_balance*", (route) => {
		bundleRuns += 1
		lastBundleFilters = route.request().postDataJSON()?.filters
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: {
			columns: [
				{ fieldname: "name", label: "Name", fieldtype: "Link" },
				{ fieldname: "lot", label: "Lot", fieldtype: "Link" },
				{ fieldname: "supplier_name", label: "Supplier Name", fieldtype: "Data" },
				{ fieldname: "item", label: "Item", fieldtype: "Link" },
				{ fieldname: "size", label: "Size", fieldtype: "Data" },
				{ fieldname: "colour", label: "Colour", fieldtype: "Data" },
				{ fieldname: "panel", label: "Panel", fieldtype: "Data" },
				{ fieldname: "qty", label: "Quantity", fieldtype: "Int" },
			],
			result: [
				{ name: "CBML-1", lot: "LOT-CP-1", supplier_name: "Cut Panel Unit", item: "SHIRT-1", size: "M", colour: "Navy", panel: "Front", qty: 18 },
				{ name: "CBML-2", lot: "LOT-CP-1", supplier_name: "Cut Panel Unit", item: "SHIRT-1", size: "L", colour: "Navy", panel: "Back", qty: 12 },
			],
			summary: { rows: 2, quantity: 30 },
		} }) })
	})

	await page.goto(`${SITE}/web/cut-panel-store/reports`, { waitUntil: "domcontentloaded" })
	const reports = page.locator(".cut-panel-store-reports")
	await reports.waitFor({ timeout: 20_000 })
	const tabs = reports.getByRole("tab")
	assert(await tabs.count() === 2, `Expected exactly two Cut Panel Store report tabs, got ${await tabs.count()}`)
	const stockTab = tabs.filter({ hasText: "Stock Balance" })
	const bundleTab = tabs.filter({ hasText: "Cut Bundle Balance" })
	assert(await stockTab.count() === 1, "Stock Balance tab is missing")
	assert(await bundleTab.count() === 1, "Cut Bundle Balance tab is missing")
	await reports.getByLabel("Stock Balance").getByRole("button", { name: "Generate", exact: true }).click()
	await reports.getByText("CUT-PANEL-1", { exact: true }).waitFor()
	assert(stockRuns === 1, `Stock Balance ran ${stockRuns} times instead of once`)

	await bundleTab.click()
	const bundleReport = reports.getByLabel("Cut Bundle Balance")
	await bundleReport.getByRole("button", { name: "Generate", exact: true }).click()
	await bundleReport.getByText("CBML-1", { exact: true }).waitFor()
	assert(bundleRuns === 1, `Cut Bundle Balance ran ${bundleRuns} times instead of once`)
	assert(JSON.stringify(lastBundleFilters) === JSON.stringify({ lot: "", supplier: "" }), `Unexpected Cut Bundle filters: ${JSON.stringify(lastBundleFilters)}`)
	assert(await bundleReport.getByText("30", { exact: true }).count() >= 1, "Cut Bundle quantity metric is missing")
	for (const column of ["Name", "Lot", "Supplier Name", "Item", "Size", "Colour", "Panel", "Quantity"]) {
		assert(await bundleReport.getByRole("columnheader", { name: column, exact: true }).count() === 1, `Cut Bundle table omits ${column}`)
	}

	await page.setViewportSize({ width: 390, height: 844 })
	const geometry = await reports.evaluate((element) => {
		const rect = element.getBoundingClientRect()
		const table = element.querySelector(".cut-bundle-balance__table-wrap")?.getBoundingClientRect()
		return { left: rect.left, right: rect.right, tableLeft: table?.left, tableRight: table?.right, viewport: window.innerWidth, pageWidth: document.documentElement.scrollWidth }
	})
	assert(geometry.left >= 0 && geometry.right <= geometry.viewport + 1, `Reports workspace escapes mobile viewport: ${JSON.stringify(geometry)}`)
	assert(geometry.tableLeft >= geometry.left && geometry.tableRight <= geometry.right + 1, `Cut Bundle table is not contained on mobile: ${JSON.stringify(geometry)}`)
	assert(geometry.pageWidth <= geometry.viewport + 1, `Reports create page-level horizontal overflow: ${JSON.stringify(geometry)}`)
}

const suites = {
	launcher: launcherSuite,
	movements: movementSuite,
	"movement-transactions": movementTransactionSuite,
	"work-orders": workOrdersSuite,
	"cut-bundle-edit": cutBundleEditSuite,
	"box-stickers": boxStickerSuite,
	"excel-stickers": excelStickerSuite,
	reports: reportSuite,
}

const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
const page = await context.newPage()
const browserErrors = []
page.on("pageerror", (error) => browserErrors.push(error.message))

try {
	await login(page)
	if (suite === "all") {
		for (const run of Object.values(suites)) {
			await page.unrouteAll({ behavior: "wait" })
			await run(page)
		}
	} else {
		assert(suites[suite], `Unknown Cut Panel Store verification suite: ${suite}`)
		await suites[suite](page)
	}
	assert(browserErrors.length === 0, `Browser errors: ${browserErrors.join("; ")}`)
	console.log(JSON.stringify({ passed: true, suite, browserErrors }, null, 2))
} finally {
	await browser.close()
}
