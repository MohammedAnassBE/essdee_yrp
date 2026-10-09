#!/usr/bin/env node

import { createRequire } from "node:module"
import { readFileSync } from "node:fs"

const require = createRequire("/home/anas/.claude/playwright/package.json")
const { chromium } = require("playwright")

const SITE = process.env.ESSDEE_TEST_SITE || "http://erp-migration-test.site:8001"
const [username, password] = readFileSync("/home/anas/.frappe-debug-creds-mrp3", "utf8").trim().split("\n")
const ORDER = "**/api/method/essdee_yrp.cutting.order_workspace.*"
const DETAIL = "**/api/method/essdee_yrp.cutting.order_detail_editor.*"

function assert(condition, message) {
	if (!condition) throw new Error(message)
}

const groups = [{
	attributes: ["Colour"],
	primary_attribute: "Size",
	primary_attribute_values: ["S", "M"],
	items: [{
		_row_key: "g0:r0",
		name: "STYLE-001",
		attributes: { Colour: "Navy" },
		item_keys: { major_colour: "Navy" },
		values: { S: { qty: 12 }, M: { qty: 14 } },
		total_qty: 26,
	}],
	size_wise_total: { S: 12, M: 14 },
	total_sum: 26,
}]

function editorPayload({ name = null, docstatus = 0 } = {}) {
	return {
		record: {
			name,
			docstatus,
			modified: name ? "2026-10-03 12:00:00" : null,
			cutting_order_detail: "CO-STYLE-001-1",
			status: docstatus === 1 ? "Submitted" : "Draft",
			cutting_location: "Machine Cutting",
			item: "STYLE-001",
			maximum_no_of_plys: 100,
			maximum_allow_percent: 10,
			lay_no: 2,
		},
		detail: { name: "CO-STYLE-001-1", item: "STYLE-001", colours: ["Navy"], sizes: ["S", "M"], parts: [], is_set_item: false },
		matrix: { groups },
		permissions: { can_read: true, can_create: true, can_write: docstatus === 0, can_submit: docstatus === 0, can_cancel: docstatus === 1, can_amend: false, can_print: true },
		options: { cutting_locations: ["Machine Cutting", "Manual Cutting"] },
	}
}

function detailPayload() {
	return {
		record: {
			name: "CO-STYLE-001-1", modified: "2026-10-03 11:00:00", item: "STYLE-001", version: 1,
			primary_attribute: "Size", packing_attribute: "Colour", stiching_attribute: "Panel",
			attribute_no: 1, is_set_item: 0, set_item_attribute: "Part", major_attribute_value: "", major_panel_value: "Top", is_same_colour: 0,
		},
		attributes: [{ _row_key: "attr-1", attribute: "Size", mapping: "MAP-SIZE", values: ["S", "M"] }],
		colours: [{ _row_key: "colour-1", attribute_value: "Navy" }],
		panels: [{ _row_key: "panel-1", stiching_attribute_value: "Top", set_item_attribute_value: "", quantity: 1, is_default: 0 }],
		cloth_details: [],
		set_item_combination: { attributes: [], values: [] },
		stiching_combination: { attributes: ["Top"], values: [{ major_attribute: "Navy", val: { Top: "Navy" } }] },
		permissions: { can_read: true, can_create: true, can_write: true },
	}
}

function workspacePayload() {
	return {
		...editorPayload({ name: "CTO-WEB-00001", docstatus: 1 }),
		details: [
			{ fieldname: "cutting_order_detail", label: "Cutting Order Detail", value: "CO-STYLE-001-1" },
			{ fieldname: "item", label: "Item", value: "STYLE-001" },
			{ fieldname: "maximum_no_of_plys", label: "Maximum No of Plys", value: 100 },
			{ fieldname: "maximum_allow_percent", label: "Maximum Allow Percent", value: 10 },
			{ fieldname: "cutting_location", label: "Cutting Location", value: "Machine Cutting" },
			{ fieldname: "lay_no", label: "Lay No", value: 2 },
		],
		completed_items: { attributes: ["Colour"], primary_attribute_values: ["S", "M"], items: [{ attributes: { Colour: "Navy" }, values: { S: 12, M: 14 }, completed: true }] },
		incomplete_items: { attributes: ["Colour"], primary_attribute_values: ["S", "M"], items: [] },
		planned_detail: { item_detail: [] },
		markers: [{ name: "CM-00001", marker_name: "Navy Marker", length: 4.2, width: 62, required_piece_weight: 0.12, calculated_parts: "Top", docstatus: 1 }],
		laysheets: [{ name: "CLS-00001", lay_no: 2, cutting_marker: "CM-00001", marker_name: "Navy Marker", status: "Bundles Generated", bundle_generated_date: "2026-10-03", printed_time: null }],
		permissions: { can_read: true, can_create: true, can_write: false, can_submit: false, can_cancel: true, can_amend: false, can_print: true, can_read_marker: true, can_create_marker: true, can_read_laysheet: true, can_create_laysheet: true },
		actions: { can_calculate_laysheets: true, can_get_completed: true, can_update_completed: true },
		print_formats: [{ label: "Cutting Order", value: "Essdee Cutting Order" }],
	}
}

const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
const page = await context.newPage()
const errors = []
let saved = false
let submitted = false
let savedBody = null
let failLifecycle = true
let delayLifecycle = false
let releaseDelayedLifecycle = null
let markDelayedLifecycleStarted = null
let lifecycleRequests = 0
const lifecycleRequestBodies = []
const delayedLifecycleStarted = new Promise((resolve) => { markDelayedLifecycleStarted = resolve })
page.on("pageerror", (error) => errors.push(`page: ${error.message}`))
page.on("console", (message) => { if (message.type() === "error") errors.push(`console: ${message.text()}`) })

await page.goto(`${SITE}/login`, { waitUntil: "domcontentloaded" })
await page.fill("#login_email", username.trim())
await page.fill("#login_password", password.trim())
await Promise.all([
	page.waitForNavigation({ waitUntil: "domcontentloaded", timeout: 20_000 }).catch(() => {}),
	page.click(".btn-login, button[type=submit]"),
])
errors.length = 0

await page.route("**/api/method/essdee_yrp.cutting.web_capabilities.get_capabilities*", (route) => route.fulfill({
	status: 200, contentType: "application/json", body: JSON.stringify({ message: {
		"cutting-plans": { can_read: false, can_create: false },
		"cutting-orders": { can_read: true, can_create: true },
		"bulk-lay-sheets": { can_read: false, can_create: false },
		"lay-sheet-planner": { can_read: false, can_create: false },
		reports: { can_read: false, can_create: false },
	} }),
}))
await page.route("**/api/method/frappe.desk.form.load.getdoctype*", (route) => route.fulfill({
	status: 200, contentType: "application/json", body: JSON.stringify({ docs: [{ name: "SD YRP Cutting Order", is_submittable: 1, fields: [
		{ fieldname: "cutting_order_detail", label: "Cutting Order Detail", fieldtype: "Link", options: "SD YRP Cutting Order Detail", in_list_view: 1 },
		{ fieldname: "item", label: "Item", fieldtype: "Data", in_list_view: 1 },
		{ fieldname: "co_status", label: "Status", fieldtype: "Select", in_list_view: 1 },
	] }] }),
}))
await page.route("**/api/method/yrp.yrp.doctype.yrp_user_listview.yrp_user_listview.get_user_listview*", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: [] }) }))
await page.route("**/api/method/frappe.desk.reportview.get_count*", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: 1 }) }))
await page.route("**/api/resource/SD%20YRP%20Cutting%20Order*", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data: [{ name: "CTO-WEB-00001", cutting_order_detail: "CO-STYLE-001-1", item: "STYLE-001", co_status: "Submitted", modified: "2026-10-03 12:00:00" }] }) }))
await page.route("**/api/method/essdee_yrp.api.link_search.link_search*", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: [{ name: "CO-STYLE-001-1", label: "CO-STYLE-001-1 · STYLE-001" }] }) }))
await page.route("**/api/method/essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_marker.sd_yrp_cutting_marker.get_web_marker*", (route) => route.fulfill({
	status: 200, contentType: "application/json", body: JSON.stringify({ message: {
		marker: { name: "CM-00001", docstatus: 1, marker_name: "Navy Marker", length: 4.2, width: 62, required_piece_weight: 0.12, selected_type: "Machine", panels: ["Top"], ratio_items: [{ size: "S", ratio: 1 }, { size: "M", ratio: 1 }], group_items: [{ id: 1, selected: ["Top"] }], permissions: { can_write: false, can_submit: false, can_cancel: false, can_print: false } },
		context: { panels: ["Top"], sizes: ["S", "M"], can_create: true, can_submit: true },
	} }),
}))
await page.route("**/api/method/essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet.sd_yrp_cutting_laysheet.get_web_laysheet*", (route) => route.fulfill({
	status: 200, contentType: "application/json", body: JSON.stringify({ message: {
		name: "CLS-00001", docstatus: 0, cutting_order: "CTO-WEB-00001", cutting_marker: "CM-00001", marker_name: "Navy Marker", lay_no: 2, status: "Bundles Generated", ratios: [], cloth_details: [], accessory_details: [], bundles: [], permissions: { can_write: false, can_edit_details: false, can_generate: false, can_print_labels: false, can_cancel: false, can_print_laysheet: false },
	} }),
}))
await page.route(DETAIL, async (route) => {
	await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: detailPayload() }) })
})
await page.route(ORDER, async (route) => {
	const url = route.request().url()
	const body = JSON.parse(route.request().postData() || "{}")
	if (url.includes("get_order_workspace")) return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: workspacePayload() }) })
	if (url.includes("change_order_status")) { lifecycleRequests += 1; lifecycleRequestBodies.push(body) }
	if (url.includes("change_order_status") && failLifecycle) {
		failLifecycle = false
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ exc: "ValidationError", message: "The Cutting Order cannot be cancelled yet." }) })
	}
	if (url.includes("change_order_status") && delayLifecycle) {
		markDelayedLifecycleStarted()
		await new Promise((resolve) => { releaseDelayedLifecycle = resolve })
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: editorPayload({ name: "CTO-WEB-00001", docstatus: 2 }) }) })
	}
	if (url.includes("save_order")) {
		saved = true
		submitted = Boolean(body.submit)
		savedBody = body
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: editorPayload({ name: "CTO-WEB-00001", docstatus: submitted ? 1 : 0 }) }) })
	}
	return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: editorPayload({ name: saved || body.cutting_order ? "CTO-WEB-00001" : null, docstatus: submitted ? 1 : 0 }) }) })
})

await page.goto(`${SITE}/web/cutting/orders`, { waitUntil: "domcontentloaded" })
await page.getByRole("button", { name: "Create Cutting Order", exact: true }).waitFor({ timeout: 20_000 })
assert(await page.getByRole("button", { name: "Create Cutting Order", exact: true }).evaluate((element) => element.classList.contains("list-primary-action")), "Cutting Order create action is not styled as the list primary action")
await page.getByRole("button", { name: "Create Cutting Order", exact: true }).click()
await page.waitForURL("**/web/cutting/orders/new")
await page.getByRole("heading", { name: "New Cutting Order", exact: true }).waitFor({ timeout: 20_000 })
await page.getByRole("button", { name: "Create Detail", exact: true }).click()
const detailDialog = page.getByRole("dialog", { name: "Cutting Order Detail" })
await detailDialog.waitFor()
assert(await detailDialog.locator(".p-dialog-maximize-button").count() === 1, "Detail editor is not maximizable")
assert(await detailDialog.getByRole("button", { name: "Maximize dialog", exact: true }).count() === 1, "Detail editor maximize control has no accessible name")
await detailDialog.getByRole("button", { name: "Save Detail", exact: true }).click()
await detailDialog.locator("button").filter({ hasText: "Close" }).click()

const firstQuantity = page.locator(".quantity-cell input").first()
await firstQuantity.fill("18")
await page.getByRole("button", { name: "Save", exact: true }).click()
await page.waitForURL("**/web/cutting/orders/CTO-WEB-00001")
await page.getByRole("heading", { name: "Edit Cutting Order", exact: true }).waitFor()
assert(savedBody?.values?.item_details?.[0]?.items?.[0]?._row_key === "g0:r0", "Order save lost the authoritative matrix identity")
assert(!page.url().includes("/app/"), "Cutting Order redirected to Desk")
await page.getByRole("button", { name: "Save options", exact: true }).click()
await page.getByRole("menuitem", { name: "Save & Submit", exact: true }).click()
try {
	await page.getByRole("heading", { name: "Cutting Order", exact: true }).waitFor({ timeout: 20_000 })
} catch (reason) {
	await page.screenshot({ path: "/tmp/essdee-cutting-order-submit-timeout.png", fullPage: true })
	throw new Error(`Cutting Order did not leave the editor after submit: ${JSON.stringify({ url: page.url(), headings: await page.getByRole("heading").allTextContents(), errors })}`, { cause: reason })
}

await page.goto(`${SITE}/web/cutting/orders/CTO-WEB-00001`, { waitUntil: "domcontentloaded" })
await page.getByRole("heading", { name: "Cutting Order", exact: true }).waitFor({ timeout: 20_000 })
assert(await page.locator(".department-page__nav").count() === 0, "Saved Cutting Order retains the standalone Back row")
assert(await page.locator(".order-record-header .inline-page-navigation__back[aria-label='Back to Cutting Orders']").count() === 1, "Saved Cutting Order has no inline Back control beside its title")
const [orderNavigationBox, orderIdentityBox] = await Promise.all([
	page.locator(".order-record-header > .inline-page-navigation").boundingBox(),
	page.locator(".order-record-header > .order-record-identity").boundingBox(),
])
const orderIdentityGap = orderNavigationBox && orderIdentityBox ? orderIdentityBox.x - (orderNavigationBox.x + orderNavigationBox.width) : Number.POSITIVE_INFINITY
assert(orderIdentityGap >= 0 && orderIdentityGap <= 20, `Cutting Order title is not left-aligned beside document navigation: ${JSON.stringify({ orderNavigationBox, orderIdentityBox, orderIdentityGap })}`)
assert(await page.locator(".cutting-order-layout").count() === 1, "Cutting Order 80/20 workspace is missing")
const [mainBox, railBox] = await Promise.all([
	page.locator(".cutting-order-main").boundingBox(),
	page.locator(".operations-rail").boundingBox(),
])
assert(mainBox && railBox, "Cutting Order main or parent rail is missing")
const widthRatio = mainBox.width / railBox.width
assert(widthRatio >= 3.7 && widthRatio <= 4.3, `Cutting Order is not an 80/20 split: ${widthRatio}`)
assert(JSON.stringify(await page.getByRole("tab").allTextContents()) === JSON.stringify(["Details", "Summary", "Planned Detail"]), "Cutting Order tabs were renamed or reordered")
const tabContract = await page.locator(".cutting-order-tabs").evaluate((element) => {
	const list = element.querySelector(".p-tablist")
	const panels = element.querySelector(".p-tabpanels")
	return { listTop: list?.getBoundingClientRect().top, panelsTop: panels?.getBoundingClientRect().top, overflowY: panels ? getComputedStyle(panels).overflowY : "" }
})
assert(tabContract.listTop < tabContract.panelsTop && tabContract.overflowY === "auto", `Cutting Order tabs are not fixed above the scroll area: ${JSON.stringify(tabContract)}`)
assert(await page.locator(".order-header-fact--detail").getByText("CO-STYLE-001-1", { exact: true }).count() === 1, "Cutting Order Detail is not promoted to the header")
assert(await page.locator(".order-header-fact--item").getByText("STYLE-001", { exact: true }).count() === 1, "Cutting Order Item is not promoted to the header")
assert(await page.locator(".order-command-bar").count() === 0, "Cutting Order still renders the separate action strip")
for (const heading of ["Order identity", "Planning", "Schedule", "Status & notes"]) {
	assert(await page.getByRole("heading", { name: heading, exact: true }).count() === 1, `Cutting Order Details is missing ${heading}`)
}
assert(await page.locator(".order-detail-card").count() === 0, "Cutting Order still renders the old flat detail card")
const quantitySectionStyle = await page.locator(".data-section__header").first().evaluate((element) => ({ display: getComputedStyle(element).display, background: getComputedStyle(element).backgroundColor }))
assert(quantitySectionStyle.display === "flex" && quantitySectionStyle.background !== "rgba(0, 0, 0, 0)", `Cutting Order quantity section lost its card hierarchy: ${JSON.stringify(quantitySectionStyle)}`)
const quantityHeaderBackground = await page.locator(".data-table th").first().evaluate((element) => getComputedStyle(element).backgroundColor)
assert(quantityHeaderBackground !== "rgba(0, 0, 0, 0)", "Cutting Order quantity table header is visually unstructured")
await page.getByRole("button", { name: "More Actions", exact: true }).click()
for (const action of ["Calculate LaySheets", "Get Completed", "Update Completed"]) assert(await page.getByRole("menuitem", { name: action, exact: true }).count() === 1, `${action} action is missing from More Actions`)
assert(await page.getByRole("button", { name: "Copy", exact: true }).count() === 0, "Completed report opened unexpectedly")
await page.getByRole("menuitem", { name: "Get Completed", exact: true }).click()
const completedDialog = page.getByRole("dialog", { name: "Completed Cut Quantity" })
await completedDialog.getByRole("button", { name: "Copy", exact: true }).waitFor()
assert(await completedDialog.getByRole("button", { name: "Maximize dialog", exact: true }).count() === 1, "Completed Cut Quantity maximize control has no accessible name")
await completedDialog.locator("button").filter({ hasText: "Close" }).click()
assert(await page.getByRole("button", { name: "Filter markers" }).count() === 1, "Marker filters are missing")
assert(await page.getByRole("button", { name: "Filter Lay Sheets" }).count() === 1, "Lay Sheet filters are missing")
assert(await page.getByRole("button", { name: "Create New", exact: true }).count() === 2, "Cutting Order marker or Lay Sheet Create New action disappeared")
const workspaceUrl = page.url()
await page.locator(".marker-card").first().click()
await page.locator(".marker-dialog").waitFor()
assert(page.url() === workspaceUrl, "Opening an Order marker navigated away from the workspace")
await page.keyboard.press("Escape")
await page.locator(".laysheet-card").first().click()
const laySheetDialog = page.locator(".laysheet-dialog")
await laySheetDialog.waitFor()
assert(page.url() === workspaceUrl, "Opening an Order Lay Sheet navigated away from the workspace")
await page.keyboard.press("Escape")
await laySheetDialog.waitFor({ state: "hidden" })
assert(await page.getByRole("button", { name: "Print" }).count() >= 1, "Cutting Order print action is missing")
await page.getByRole("button", { name: "Cancel", exact: true }).click()
const cancellationConfirm = page.getByRole("alertdialog", { name: "Cancel Cutting Order?", exact: true })
await cancellationConfirm.getByRole("button", { name: "Cancel Cutting Order", exact: true }).click()
const lifecycleError = page.getByRole("dialog", { name: "Cutting Order action failed", exact: true })
await lifecycleError.getByText("The Cutting Order cannot be cancelled yet.", { exact: true }).waitFor()
assert(await page.getByRole("heading", { name: "Cutting Order", exact: true }).count() === 1, "Failed cancellation replaced the Cutting Order workspace")
await lifecycleError.getByRole("button", { name: "OK", exact: true }).click()

await page.setViewportSize({ width: 900, height: 760 })
const tabletTitle = await page.getByRole("heading", { name: "Cutting Order", exact: true }).evaluate((element) => {
	const style = getComputedStyle(element)
	return {
		height: element.getBoundingClientRect().height,
		lineHeight: Number.parseFloat(style.lineHeight),
		whiteSpace: style.whiteSpace,
	}
})
const tabletHeader = await page.locator(".order-record-header").evaluate((element) => {
	const identity = element.querySelector(".order-record-identity")?.getBoundingClientRect()
	const actions = element.querySelector(".order-record-actions")?.getBoundingClientRect()
	return {
		flexDirection: getComputedStyle(element).flexDirection,
		identity: identity?.toJSON(),
		actions: actions?.toJSON(),
	}
})
await page.screenshot({ path: "/tmp/essdee-cutting-order-tablet.png", fullPage: true })
assert(tabletTitle.height <= tabletTitle.lineHeight * 1.25, `Cutting Order heading wraps at tablet width: ${JSON.stringify(tabletTitle)}`)
assert(tabletHeader.flexDirection === "column" && tabletHeader.actions?.y >= tabletHeader.identity?.bottom, `Cutting Order tablet identity and actions still compete in one row: ${JSON.stringify(tabletHeader)}`)

delayLifecycle = true
await page.getByRole("button", { name: "Cancel", exact: true }).click()
await page.getByRole("alertdialog", { name: "Cancel Cutting Order?", exact: true }).getByRole("button", { name: "Cancel Cutting Order", exact: true }).click()
await delayedLifecycleStarted
await page.evaluate(() => {
	window.history.pushState({}, "", "/web/cutting/orders")
	window.dispatchEvent(new PopStateEvent("popstate", { state: window.history.state }))
})
await page.waitForURL((url) => url.pathname === "/web/cutting/orders")
await page.getByRole("button", { name: "Create Cutting Order", exact: true }).waitFor()
const delayedLifecycleResponse = page.waitForResponse((response) => response.url().includes("change_order_status"))
releaseDelayedLifecycle()
await delayedLifecycleResponse
await page.waitForTimeout(250)
assert(new URL(page.url()).pathname === "/web/cutting/orders", `A stale lifecycle response navigated back to the old Cutting Order: ${page.url()}`)

await page.goto(`${SITE}/web/cutting/orders/CTO-WEB-00001`, { waitUntil: "domcontentloaded" })
await page.getByRole("heading", { name: "Cutting Order", exact: true }).waitFor()
const requestsBeforeStaleConfirmation = lifecycleRequests
await page.getByRole("button", { name: "Cancel", exact: true }).click()
const staleConfirmation = page.getByRole("alertdialog", { name: "Cancel Cutting Order?", exact: true })
await staleConfirmation.waitFor()
await page.evaluate(() => {
	window.history.pushState({}, "", "/web/cutting/orders")
	window.dispatchEvent(new PopStateEvent("popstate", { state: window.history.state }))
})
await page.getByRole("button", { name: "Create Cutting Order", exact: true }).waitFor()
await staleConfirmation.getByRole("button", { name: "Cancel Cutting Order", exact: true }).click()
await page.waitForTimeout(250)
assert(lifecycleRequests === requestsBeforeStaleConfirmation, `A stale confirmation acted after navigation: ${JSON.stringify(lifecycleRequestBodies)}`)
assert(errors.length === 0, `Browser errors: ${JSON.stringify(errors)}`)

console.log(JSON.stringify({ passed: true, workspace: "CTO-WEB-00001", detail: "CO-STYLE-001-1", matrixRows: 1, widthRatio, tabletTitle }, null, 2))
await browser.close()
