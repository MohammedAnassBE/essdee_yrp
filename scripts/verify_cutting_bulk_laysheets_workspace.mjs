#!/usr/bin/env node

import { createRequire } from "node:module"
import { readFileSync } from "node:fs"

const require = createRequire("/home/anas/.claude/playwright/package.json")
const { chromium } = require("playwright")

const SITE = "http://erp-migration-test.site:8001"
const [username, password] = readFileSync("/home/anas/.frappe-debug-creds-mrp3", "utf8").trim().split("\n")
const API = "**/api/method/essdee_yrp.cutting.bulk_laysheets_workspace.*"

function assert(condition, message) {
	if (!condition) throw new Error(message)
}

assert(readFileSync("frontend/src/departments/CuttingBulkLaySheets.vue", "utf8").includes('class="list-primary-action"'), "Bulk LaySheets create action is not styled as the list primary action")

async function visibleTextBelowMinimum(page, minPx = 11) {
	return page.locator("body *").evaluateAll((elements, minimum) => elements.flatMap((element) => {
		if (!(element instanceof HTMLElement)) return []
		if (element.matches("script, style, svg, path, .pi, [aria-hidden='true']") || element.children.length) return []
		const text = (element.innerText || "").trim()
		const style = getComputedStyle(element)
		const rect = element.getBoundingClientRect()
		if (!text || style.display === "none" || style.visibility === "hidden" || !rect.width || !rect.height) return []
		const fontSize = Number.parseFloat(style.fontSize)
		return fontSize < minimum ? [{ text: text.slice(0, 60), fontSize }] : []
	}), minPx)
}

const rows = [
	{ name: "ROW-1", idx: 1, lot: "LOT-SPLIT-1", cutting_plan: "CP-001", cutting_marker: "CM-001", work_order: "WO-001", cutting_laysheet: "CLS-001", lot_transfer: null, delivery_challan: null, status: "Ready to Generate", actions: { can_activate: true, can_generate_bundles: true, can_create_lot_transfer: false, can_submit_lot_transfer: false, can_create_delivery_challan: false, can_submit_delivery_challan: false, can_approve_grammage: false, can_print_labels: false } },
	{ name: "ROW-2", idx: 2, lot: "LOT-SPLIT-2", cutting_plan: "CP-002", cutting_marker: "CM-002", work_order: "WO-002", cutting_laysheet: "CLS-002", lot_transfer: null, delivery_challan: null, status: "Enter Lay Details", actions: { can_activate: true, can_generate_bundles: false, can_create_lot_transfer: false, can_submit_lot_transfer: false, can_create_delivery_challan: false, can_submit_delivery_challan: false, can_approve_grammage: false, can_print_labels: false } },
]

function editorPayload(name = null) {
	return {
		record: {
			name, modified: name ? "2026-10-03 12:00:00" : null, docstatus: 0,
			main_lot: "LOT-MAIN", from_location: "CUTTING", posting_date: "2026-10-03",
			cutting_spreader: "SPREADER-1", cutter: "CUTTER-1", status: name ? "In Progress" : "Setup",
			active_cutting_laysheet: name ? "CLS-001" : null,
			lot_details: name ? rows : [],
		},
		permissions: { can_read: true, can_create: true, can_write: true, can_print: true },
		setup_locked: Boolean(name),
	}
}

function workspacePayload(active = "CLS-001") {
	return {
		record: { ...editorPayload("CBLS-WEB-00001").record, lot_details: undefined, active_cutting_laysheet: active },
		setup_locked: true,
		rows,
		active_laysheet: {
			context: { name: active, status: active === "CLS-001" ? "Completed" : "Started", read_only: false, is_manual_entry: false },
			item_details: { cloth_items: [{ name: "CLOTH-1", cloth_item_variant: "FABRIC-NAVY-72", cloth_type: "MAIN FABRIC", colour: "Navy", actual_dia: "72 Dia", shade: "A", weight: 12, no_of_rolls: 1, no_of_bits: 10, used_weight: 11.5, balance_weight: 0.5 }] },
			item_accessories: [],
			bundles: [{ name: "BUNDLE-1", bundle_no: 1, size: "M", colour: "Navy", shade: "A", part: "Top", quantity: 25, is_moved: 0 }],
		},
		bundles: [{ name: "BUNDLE-1", bundle_no: 1, size: "M", colour: "Navy", shade: "A", part: "Top", quantity: 25, is_moved: 0 }],
		permissions: {
			can_read: true, can_create: true, can_write: true, can_print: true,
			laysheet: { can_read: true, can_create: true, can_write: true, can_submit: true, can_print: true },
			lot_transfer: { can_read: true, can_create: true, can_write: true, can_submit: true, can_print: true },
			delivery_challan: { can_read: true, can_create: true, can_write: true, can_submit: true, can_print: true },
		},
		bulk_actions: { can_create_laysheets: true, can_create_bulk_lot_transfer: false, can_submit_bulk_lot_transfer: false, shared_lot_transfer: null, can_create_bulk_delivery_challans: false },
	}
}

const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
const page = await context.newPage()
const errors = []
let active = "CLS-001"
let saveBody = null
page.on("pageerror", (error) => errors.push(`page: ${error.message}`))
page.on("console", (message) => { if (message.type() === "error") errors.push(`console: ${message.text()}`) })

await page.goto(`${SITE}/login`, { waitUntil: "domcontentloaded" })
await page.fill("#login_email", username.trim())
await page.fill("#login_password", password.trim())
await Promise.all([
	page.waitForNavigation({ waitUntil: "domcontentloaded", timeout: 20_000 }).catch(() => {}),
	page.click(".btn-login, button[type=submit]"),
])

await page.route("**/api/method/essdee_yrp.api.link_search.link_search*", async (route) => {
	const body = JSON.parse(route.request().postData() || "{}")
	const names = body.doctype === "SD YRP Lot" ? ["LOT-MAIN", "LOT-SPLIT-1", "LOT-SPLIT-2"]
		: body.doctype === "SD YRP Cutting Plan" ? ["CP-001", "CP-002"]
			: body.doctype === "SD YRP Cutting Marker" ? ["CM-001", "CM-002"]
				: ["CUTTING", "SPREADER-1", "CUTTER-1"]
	await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: names.map((name) => ({ name, label: name })) }) })
})
await page.route("**/api/method/essdee_yrp.cutting.web_capabilities.get_capabilities*", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: { "bulk-lay-sheets": { can_read: true, can_create: true } } }) }))
await page.route(API, async (route) => {
	const url = route.request().url()
	const body = JSON.parse(route.request().postData() || "{}")
	if (url.includes("get_editor")) return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: editorPayload(body.name || null) }) })
	if (url.includes("get_workspace")) return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: workspacePayload(active) }) })
	if (url.includes("save")) {
		saveBody = body
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: workspacePayload(active) }) })
	}
	if (url.includes("set_active_laysheet")) active = body.cutting_laysheet
	return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: { result: "OK", workspace: workspacePayload(active) } }) })
})

await page.goto(`${SITE}/web/cutting/bulk-lay-sheets/new`, { waitUntil: "domcontentloaded" })
await page.getByRole("heading", { name: "New Bulk LaySheets", exact: true }).waitFor({ timeout: 20_000 })
await page.getByRole("button", { name: "Add Split Lot", exact: true }).click()
assert(await page.locator(".bulk-setup-row").count() === 1, "Split-lot setup row was not added")
const setupRow = page.locator(".bulk-setup-row").first()
for (const [index, query] of [[0, "LOT-SPLIT-1"], [1, "CP-001"], [2, "CM-001"]]) {
	await setupRow.locator("input").nth(index).fill(query)
	await page.locator(".p-autocomplete-overlay:visible .p-autocomplete-option").first().click()
}
await page.getByRole("button", { name: "Save Setup", exact: true }).click()
assert(saveBody?.values?.lot_details?.length === 1, "Bulk setup did not save split rows")

await page.goto(`${SITE}/web/cutting/bulk-lay-sheets/CBLS-WEB-00001`, { waitUntil: "domcontentloaded" })
await page.getByRole("heading", { name: "Bulk LaySheets", exact: true }).waitFor({ timeout: 20_000 })
assert(await page.locator(".bulk-header-fact--lot").getByText("LOT-MAIN", { exact: true }).count() === 1, "Main Lot is not promoted to the Bulk header")
assert(await page.locator(".bulk-header-fact--location").getByText("CUTTING", { exact: true }).count() === 1, "Location is not promoted to the Bulk header")
assert(await page.locator(".bulk-command-bar").count() === 0, "Bulk LaySheets still renders a separate action strip")
assert(await page.locator(".bulk-setup-summary").getByText("Main Stock Lot", { exact: true }).count() === 0, "Main Lot is duplicated in the setup summary")
assert(await page.locator(".bulk-setup-summary").getByText("Stock Location", { exact: true }).count() === 0, "Location is duplicated in the setup summary")
await page.getByRole("button", { name: "More Actions", exact: true }).click()
assert(await page.getByRole("menuitem", { name: "Create LaySheets", exact: true }).count() === 1, "Bulk action is missing from More Actions")
await page.keyboard.press("Escape")
const [mainBox, railBox] = await Promise.all([
	page.locator(".bulk-workspace-main").boundingBox(),
	page.locator(".bulk-workflow-rail").boundingBox(),
])
assert(mainBox && railBox, "Bulk 80/20 workspace is missing")
const widthRatio = mainBox.width / railBox.width
assert(widthRatio >= 3.6 && widthRatio <= 4.4, `Bulk workspace is not an 80/20 split: ${widthRatio}`)
assert(await page.locator(".bulk-workflow-card").count() === 2, "Workflow cards are missing")
assert(await page.getByText("Cloth Details", { exact: true }).count() === 1, "Active LaySheet editor is missing")
assert(await page.getByText("Generated Bundles", { exact: true }).count() === 1, "Bundle table is missing")
await page.locator(".bulk-workflow-card").nth(1).click()
await page.getByText("CLS-002", { exact: true }).waitFor()
assert(!page.url().includes("/app/"), "Bulk workflow navigated to Desk")

const responsiveLayouts = {}
for (const viewport of [{ width: 1600, height: 1000 }, { width: 1280, height: 800 }, { width: 900, height: 760 }, { width: 390, height: 844 }]) {
	await page.setViewportSize(viewport)
	const bodyWidth = await page.locator("body").evaluate((element) => ({ scrollWidth: element.scrollWidth, clientWidth: element.clientWidth }))
	assert(bodyWidth.scrollWidth === bodyWidth.clientWidth, `Bulk workspace overflows at ${viewport.width}px: ${JSON.stringify(bodyWidth)}`)
	const undersized = await visibleTextBelowMinimum(page)
	assert(undersized.length === 0, `Bulk workspace has text below 11px at ${viewport.width}px: ${JSON.stringify(undersized.slice(0, 8))}`)
	const columns = await page.locator(".bulk-workspace-layout").evaluate((element) => getComputedStyle(element).gridTemplateColumns.split(" ").filter(Boolean).length)
	assert(columns === (viewport.width <= 1100 ? 1 : 2), `Bulk workspace column collapse is incorrect at ${viewport.width}px: ${columns}`)
	responsiveLayouts[viewport.width] = columns
}
assert(errors.length === 0, `Browser errors: ${JSON.stringify(errors)}`)

console.log(JSON.stringify({ passed: true, workspace: "CBLS-WEB-00001", rows: 2, widthRatio, responsiveLayouts }, null, 2))
await browser.close()
