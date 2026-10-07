#!/usr/bin/env node

import { createRequire } from "node:module"
import { readFileSync } from "node:fs"

const require = createRequire("/home/anas/.claude/playwright/package.json")
const { chromium } = require("playwright")

const SITE = process.env.ESSDEE_TEST_SITE || "http://erp-migration-test.site:8001"
const CREDENTIALS = "/home/anas/.frappe-debug-creds-mrp3"

function assert(condition, message) {
	if (!condition) throw new Error(message)
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

async function assertContained(page, label) {
	const dimensions = await page.locator("body").evaluate((body) => ({
		clientWidth: body.clientWidth,
		scrollWidth: body.scrollWidth,
	}))
	assert(dimensions.clientWidth === dimensions.scrollWidth, `${label} overflows the page: ${JSON.stringify(dimensions)}`)
}

const doctypes = {
	"SD YRP Cutting Plan": {
		row: { name: "CP-WEB-001", lot: "LOT-001", item: "STYLE-001", cp_status: "Ready to Cut", no_of_colours: 2, no_of_colours_completed: 1, modified: "2026-10-03 10:00:00" },
		fields: [["lot", "Lot", "Link"], ["item", "Item", "Link"], ["cp_status", "Status", "Select"], ["no_of_colours", "Colours", "Int"], ["no_of_colours_completed", "Completed Colours", "Int"]],
	},
	"SD YRP Cutting Order": {
		row: { name: "CO-WEB-001", cutting_order_detail: "COD-WEB-001", item: "STYLE-002", co_status: "Submitted", lay_no: 3, cutting_location: "Machine Cutting", modified: "2026-10-03 10:00:00" },
		fields: [["cutting_order_detail", "Cutting Order Detail", "Link"], ["item", "Item", "Data"], ["co_status", "Status", "Select"], ["lay_no", "Lay No", "Int"], ["cutting_location", "Cutting Location", "Select"]],
	},
	"SD YRP Cutting Bulk Lay Sheets": {
		row: { name: "CBLS-WEB-001", main_lot: "LOT-003", from_location: "CUTTING", posting_date: "2026-10-03", status: "In Progress", modified: "2026-10-03 10:00:00" },
		fields: [["main_lot", "Main Stock Lot", "Link"], ["from_location", "Stock Location", "Link"], ["posting_date", "Posting Date", "Date"], ["status", "Status", "Select"]],
	},
	"SD YRP Cutting Laysheet Planner": {
		row: { name: "CLP-WEB-001", description: "October order plan", lot: "LOT-004", item: "STYLE-004", optimization_status: "Completed", selected_strategy: "cp_sat", modified: "2026-10-03 10:00:00" },
		fields: [["description", "Description", "Small Text"], ["lot", "Lot", "Link"], ["item", "Item", "Link"], ["optimization_status", "Status", "Select"], ["selected_strategy", "Selected Strategy", "Select"]],
	},
}

let capabilities = Object.fromEntries([
	"cutting-plans",
	"cutting-orders",
	"bulk-lay-sheets",
	"lay-sheet-planner",
	"reports",
].map((key) => [key, { can_read: true, can_create: key !== "reports" }]))
let capabilityFailure = ""

const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
const page = await context.newPage()
const errors = []
const listRequests = []
page.on("pageerror", (error) => errors.push(`page: ${error.message}`))
page.on("console", (message) => { if (message.type() === "error") errors.push(`console: ${message.text()}`) })
page.on("response", (response) => { if (response.status() >= 500) errors.push(`http ${response.status()}: ${response.url()}`) })

await login(page)
errors.length = 0

await page.route("**/api/method/essdee_yrp.cutting.web_capabilities.get_capabilities*", (route) => route.fulfill(capabilityFailure ? {
	status: 503,
	contentType: "application/json",
	body: JSON.stringify({ message: capabilityFailure }),
} : {
	status: 200,
	contentType: "application/json",
	body: JSON.stringify({ message: capabilities }),
}))
await page.route("**/api/method/essdee_yrp.cutting.plan_editor.get_editor*", (route) => route.fulfill({
	status: 200,
	contentType: "application/json",
	body: JSON.stringify({ message: {
		record: { name: "CP-WEB-001", docstatus: 1, modified: "2026-10-03 10:00:00", status: "Ready to Cut" },
		matrix: { groups: [] },
		permissions: { can_read: true, can_write: false, can_submit: false, can_cancel: false, can_amend: false },
		fields: { show_work_order: false },
		options: { cutting_locations: [] },
	} }),
}))
await page.route("**/api/method/essdee_yrp.cutting.reports.get_report_permissions*", (route) => route.fulfill({
	status: 200,
	contentType: "application/json",
	body: JSON.stringify({ message: { "cutting-plans": true, "daily-production": true } }),
}))
await page.route("**/api/method/frappe.desk.form.load.getdoctype*", (route) => {
	const doctype = new URL(route.request().url()).searchParams.get("doctype")
	const fields = (doctypes[doctype]?.fields || []).map(([fieldname, label, fieldtype]) => ({
		fieldname, label, fieldtype, in_list_view: 1, in_standard_filter: 0,
	}))
	return route.fulfill({
		status: 200,
		contentType: "application/json",
		body: JSON.stringify({ docs: [{ name: doctype, is_submittable: 1, fields }] }),
	})
})
await page.route("**/api/method/yrp.yrp.doctype.yrp_user_listview.yrp_user_listview.get_user_listview*", (route) => route.fulfill({
	status: 200, contentType: "application/json", body: JSON.stringify({ message: [] }),
}))
await page.route("**/api/method/frappe.desk.reportview.get_count*", (route) => route.fulfill({
	status: 200, contentType: "application/json", body: JSON.stringify({ message: 1 }),
}))
await page.route("**/api/resource/**", (route) => {
	const url = new URL(route.request().url())
	const doctype = decodeURIComponent(url.pathname.split("/api/resource/")[1] || "")
	listRequests.push({ doctype, orderBy: url.searchParams.get("order_by") })
	return route.fulfill({
		status: 200,
		contentType: "application/json",
		body: JSON.stringify({ data: doctypes[doctype] ? [doctypes[doctype].row] : [] }),
	})
})

await page.goto(`${SITE}/web/cutting`, { waitUntil: "domcontentloaded" })
await page.locator(".workspace-launcher__grid").waitFor({ timeout: 20_000 })
const cardLabels = await page.locator(".workspace-launcher__card strong").allTextContents()
assert(JSON.stringify(cardLabels) === JSON.stringify(["Cutting Plans", "Cutting Orders", "Bulk LaySheets", "LaySheet Planner", "Reports"]), `Unexpected Cutting destinations: ${JSON.stringify(cardLabels)}`)

capabilities = { ...capabilities, "cutting-orders": { can_read: false, can_create: true } }
await page.reload({ waitUntil: "domcontentloaded" })
await page.locator(".workspace-launcher__grid").waitFor()
assert(await page.getByText("Cutting Orders", { exact: true }).count() === 0, "Unreadable Cutting Orders destination is still visible")
capabilities = { ...capabilities, "cutting-orders": { can_read: true, can_create: true } }

const capabilityFailureErrorStart = errors.length
capabilityFailure = "Cutting workspace temporarily unavailable"
await page.reload({ waitUntil: "domcontentloaded" })
await page.getByText("Cutting workspace temporarily unavailable", { exact: true }).waitFor({ timeout: 20_000 })
const retry = page.getByRole("button", { name: "Retry", exact: true })
assert(await retry.count() === 1, "Cutting capability failure has no retry action")
capabilityFailure = ""
await retry.click()
await page.locator(".workspace-launcher__card").first().waitFor({ timeout: 20_000 })
errors.splice(capabilityFailureErrorStart)

const lists = [
	{ path: "plans", title: "Cutting Plans", doctype: "SD YRP Cutting Plan", row: "CP-WEB-001", create: "Create Cutting Plan" },
	{ path: "orders", title: "Cutting Orders", doctype: "SD YRP Cutting Order", row: "CO-WEB-001", create: "Create Cutting Order" },
	{ path: "bulk-lay-sheets", title: "Bulk LaySheets", doctype: "SD YRP Cutting Bulk Lay Sheets", row: "CBLS-WEB-001", create: "Create Bulk LaySheets" },
	{ path: "lay-sheet-planner", title: "LaySheet Planner", doctype: "SD YRP Cutting Laysheet Planner", row: "CLP-WEB-001", create: "Create LaySheet Plan" },
]

for (const list of lists) {
	await page.goto(`${SITE}/web/cutting/${list.path}`, { waitUntil: "domcontentloaded" })
	await page.locator(".common-list-view").waitFor({ timeout: 20_000 })
	assert(await page.getByRole("heading", { name: list.title, exact: true }).count() === 1, `${list.title} heading is missing`)
	assert(await page.getByRole("button", { name: list.create, exact: true }).count() === 1, `${list.create} is missing`)
	if (list.path === "plans") {
		const createStyle = await page.getByRole("button", { name: list.create, exact: true }).evaluate((element) => ({
			backgroundColor: getComputedStyle(element).backgroundColor,
			color: getComputedStyle(element).color,
		}))
		assert(createStyle.backgroundColor !== "rgb(255, 255, 255)", `Create Cutting Plan still looks secondary: ${JSON.stringify(createStyle)}`)
		assert(createStyle.color === "rgb(255, 255, 255)", `Create Cutting Plan does not have primary-action contrast: ${JSON.stringify(createStyle)}`)
	}
	assert(await page.locator(".premium-list-table").getByText(list.row, { exact: true }).count() === 1, `${list.title} desktop row did not render`)
	assert(await page.locator(".mobile-list-records").getByText(list.row, { exact: true }).count() === 1, `${list.title} mobile record did not render`)
	assert(await page.locator(".list-row-chevron").count() === 1, `${list.title} rows are not clickable`)
	const request = listRequests.find((entry) => entry.doctype === list.doctype)
	assert(request?.orderBy === "modified desc", `${list.title} is not newest-first: ${JSON.stringify(request)}`)
	assert(!page.url().includes("/app/"), `${list.title} redirected to Desk`)
}

await page.goto(`${SITE}/web/cutting/plans`, { waitUntil: "domcontentloaded" })
await page.locator(".premium-list-table").getByText("CP-WEB-001", { exact: true }).click()
await page.waitForURL("**/web/cutting/plans/CP-WEB-001")
assert(!page.url().includes("/app/"), "Cutting Plan row redirected to Desk")

await page.goto(`${SITE}/web/cutting/orders`, { waitUntil: "domcontentloaded" })
await page.locator(".common-list-view").waitFor({ state: "visible", timeout: 20_000 })
await page.setViewportSize({ width: 1280, height: 800 })
await assertContained(page, "Cutting Order list at 1280px")
await page.setViewportSize({ width: 900, height: 760 })
await assertContained(page, "Cutting Order list at 900px")
const tabletSurface = await page.evaluate(() => ({
	desktopTable: document.querySelector(".premium-list-table") ? getComputedStyle(document.querySelector(".premium-list-table")).display : "absent",
	mobileRecords: document.querySelector(".mobile-list-records") ? getComputedStyle(document.querySelector(".mobile-list-records")).display : "absent",
}))
assert(tabletSurface.desktopTable === "none" && tabletSurface.mobileRecords !== "none" && tabletSurface.mobileRecords !== "absent", `Tablet list does not switch to readable record cards: ${JSON.stringify(tabletSurface)}`)
await page.setViewportSize({ width: 390, height: 844 })
await assertContained(page, "Cutting Order list at 390px")
const mobileSurface = await page.evaluate(() => ({
	desktopTable: document.querySelector(".premium-list-table") ? getComputedStyle(document.querySelector(".premium-list-table")).display : "absent",
	mobileRecords: document.querySelector(".mobile-list-records") ? getComputedStyle(document.querySelector(".mobile-list-records")).display : "absent",
	statusTabs: document.querySelector(".list-status-tabs") ? getComputedStyle(document.querySelector(".list-status-tabs")).display : "absent",
	statusSelect: document.querySelector(".list-status-select") ? getComputedStyle(document.querySelector(".list-status-select")).display : "absent",
	searchHeight: document.querySelector(".list-search input")?.getBoundingClientRect().height || 0,
}))
assert(mobileSurface.desktopTable === "none", `Desktop table remains visible or is missing on mobile: ${JSON.stringify(mobileSurface)}`)
assert(mobileSurface.mobileRecords !== "none" && mobileSurface.mobileRecords !== "absent", `Mobile records are hidden or missing: ${JSON.stringify(mobileSurface)}`)
assert(mobileSurface.searchHeight >= 44, `Mobile search control misses the 44px touch target: ${JSON.stringify(mobileSurface)}`)

assert(errors.length === 0, `Browser errors: ${JSON.stringify(errors)}`)
console.log(JSON.stringify({ passed: true, cardLabels, lists: lists.map((list) => list.title), listRequests, tabletSurface, mobileSurface }, null, 2))
await browser.close()
