#!/usr/bin/env node

import { createRequire } from "node:module"
import { mkdirSync, readFileSync } from "node:fs"
import { resolve } from "node:path"

const require = createRequire("/home/anas/.claude/playwright/package.json")
const { chromium } = require("playwright")

const SITE = process.env.ESSDEE_TEST_SITE || "http://erp-migration-test.site:8001"
const CREDENTIALS = "/home/anas/.frappe-debug-creds-mrp3"
const CAPTURE_DIR = process.env.ESSDEE_CAPTURE_DIR ? resolve(process.env.ESSDEE_CAPTURE_DIR) : ""
if (CAPTURE_DIR) mkdirSync(CAPTURE_DIR, { recursive: true })

function assert(condition, message) {
	if (!condition) throw new Error(message)
}

async function capture(page, name) {
	if (CAPTURE_DIR) await page.screenshot({ path: resolve(CAPTURE_DIR, name), fullPage: true })
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

async function resourceNames(request, doctype) {
	const response = await request.get(`${SITE}/api/resource/${encodeURIComponent(doctype)}`, {
		params: { fields: JSON.stringify(["name"]), order_by: "modified desc", limit_page_length: 100 },
	})
	assert(response.ok(), `Unable to list ${doctype} fixtures (${response.status()})`)
	return ((await response.json()).data || []).map((row) => row.name)
}

async function method(request, path, params) {
	const response = await request.get(`${SITE}/api/method/${path}`, { params })
	if (!response.ok()) return null
	return (await response.json()).message || null
}

async function findCuttingPlan(request) {
	for (const name of await resourceNames(request, "SD YRP Cutting Plan")) {
		const data = await method(
			request,
			"essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan.sd_yrp_cutting_plan.get_web_view_data",
			{ cutting_plan: name },
		)
		if (data?.permissions?.can_read_marker && data?.permissions?.can_read_laysheet && data.markers?.length && data.laysheets?.length) return { name, data }
	}
	throw new Error("No Cutting Plan with Marker and Lay Sheet fixtures is available")
}

async function findWorkOrder(request) {
	for (const name of await resourceNames(request, "YRP Work Order")) {
		const data = await method(request, "essdee_yrp.fabric_store.web_workspace.get_work_order_workspace", { work_order: name })
		const deliveryChallans = data?.related?.delivery_challans || data?.delivery_challans || []
		const goodsReceivedNotes = data?.related?.goods_received_notes || data?.goods_received_notes || []
		if (data?.related_permissions?.delivery_challan?.can_read !== false && data?.related_permissions?.goods_received_note?.can_read !== false && deliveryChallans.length && goodsReceivedNotes.length) return { name, data }
	}
	throw new Error("No Work Order with DC and GRN fixtures is available")
}

function parseListFilters(request, doctype) {
	const url = new URL(request.url())
	if (!url.pathname.includes(`/api/resource/${encodeURIComponent(doctype)}`)) return null
	try { return JSON.parse(url.searchParams.get("filters") || "[]") } catch { return null }
}

async function cuttingSuite(page) {
	const fixture = await findCuttingPlan(page.request)
	const listRequests = []
	page.on("request", (request) => {
		for (const doctype of ["SD YRP Cutting Marker", "SD YRP Cutting LaySheet"]) {
			const filters = parseListFilters(request, doctype)
			if (filters) listRequests.push({ doctype, filters })
		}
	})

	await page.setViewportSize({ width: 1600, height: 1000 })
	await page.goto(`${SITE}/web/cutting/plans/${encodeURIComponent(fixture.name)}`, { waitUntil: "domcontentloaded" })
	const markerSection = page.locator(".marker-section")
	const laySheetSection = page.locator(".laysheet-section")
	await markerSection.getByRole("button", { name: "Expand Markers", exact: true }).waitFor({ timeout: 20_000 })
	if (CAPTURE_DIR) {
		await page.goto(`${SITE}/web/cutting/plans`, { waitUntil: "domcontentloaded" })
		await page.locator(".list-row-open").first().waitFor({ timeout: 20_000 })
		await page.locator(".list-row-open").first().click()
		await page.locator(".cutting-plan-frame").waitFor({ timeout: 20_000 })
		await page.locator(".operations-rail").waitFor({ timeout: 20_000 })
		await capture(page, "01-cutting-plan-navigation-and-expand.png")
		await page.goto(`${SITE}/web/cutting/plans/${encodeURIComponent(fixture.name)}`, { waitUntil: "domcontentloaded" })
		await markerSection.getByRole("button", { name: "Expand Markers", exact: true }).waitFor({ timeout: 20_000 })
	}

	for (const [section, expandLabel, filterLabel] of [
		[markerSection, "Expand Markers", "Filter markers"],
		[laySheetSection, "Expand Lay Sheets", "Filter Lay Sheets"],
	]) {
		const expandBox = await section.getByRole("button", { name: expandLabel, exact: true }).boundingBox()
		const filterBox = await section.getByRole("button", { name: filterLabel, exact: true }).boundingBox()
		assert(expandBox && filterBox && expandBox.x < filterBox.x, `${expandLabel} is not immediately before Filters`)
	}

	const markerExpand = markerSection.getByRole("button", { name: "Expand Markers", exact: true })
	await markerExpand.click()
	let dialog = page.getByRole("dialog", { name: "Markers", exact: true })
	await dialog.waitFor({ timeout: 20_000 })
	await dialog.locator(".premium-list-table .p-datatable-tbody > tr").first().waitFor({ timeout: 20_000 })
	await capture(page, "02-expanded-markers-list.png")
	assert(await dialog.locator(".inline-page-navigation").count() === 0, "Expanded Marker list exposes page navigation")
	assert(await dialog.locator(".p-selection-column").count() === 0, "Expanded Marker list exposes bulk selection")
	assert(listRequests.some((entry) => entry.doctype === "SD YRP Cutting Marker" && entry.filters.some((filter) => filter[0] === "cutting_plan" && filter[2] === fixture.name)), `Marker request omitted cutting_plan=${fixture.name}: ${JSON.stringify(listRequests)}`)

	const markerSearch = String(fixture.data.markers[0].name)
	await dialog.locator(".list-search input").fill(markerSearch)
	await dialog.locator(".list-search input").press("Enter")
	await dialog.getByText(markerSearch, { exact: true }).first().waitFor({ timeout: 20_000 })
	await dialog.locator(".list-row-open").first().click()
	const markerRecord = page.getByRole("dialog", { name: /Cutting Marker ·/ }).first()
	await markerRecord.waitFor({ timeout: 20_000 })
	await dialog.waitFor({ state: "hidden", timeout: 5_000 })
	await markerRecord.locator(".p-dialog-footer").getByRole("button", { name: "Close", exact: true }).click()
	dialog = page.getByRole("dialog", { name: "Markers", exact: true })
	await dialog.waitFor({ timeout: 20_000 })
	assert(await dialog.locator(".list-search input").inputValue() === markerSearch, "Expanded Marker search was lost after record handoff")
	await dialog.locator(".p-dialog-close-button").click()
	await markerExpand.focus()
	assert(await markerExpand.evaluate((element) => document.activeElement === element), "Marker Expand did not regain focus")

	const laySheetExpand = laySheetSection.getByRole("button", { name: "Expand Lay Sheets", exact: true })
	await laySheetExpand.click()
	dialog = page.getByRole("dialog", { name: "Lay Sheets", exact: true })
	await dialog.waitFor({ timeout: 20_000 })
	await dialog.locator(".premium-list-table .p-datatable-tbody > tr").first().waitFor({ timeout: 20_000 })
	assert(listRequests.some((entry) => entry.doctype === "SD YRP Cutting LaySheet" && entry.filters.some((filter) => filter[0] === "cutting_plan" && filter[2] === fixture.name)), `Lay Sheet request omitted cutting_plan=${fixture.name}: ${JSON.stringify(listRequests)}`)
	await dialog.locator(".p-dialog-close-button").click()

	return { cuttingPlan: fixture.name, listRequests: listRequests.length }
}

async function workOrderSuite(page) {
	const fixture = await findWorkOrder(page.request)
	const listRequests = []
	page.on("request", (request) => {
		for (const doctype of ["YRP Delivery Challan", "YRP Goods Received Note"]) {
			const filters = parseListFilters(request, doctype)
			if (filters) listRequests.push({ doctype, filters })
		}
	})

	for (const department of ["fabric-store", "cut-panel-store", "accessory-store"]) {
		await page.goto(`${SITE}/web/${department}/work-orders/${encodeURIComponent(fixture.name)}`, { waitUntil: "domcontentloaded" })
		await page.locator(".work-order-activity-rail").waitFor({ timeout: 20_000 })
		assert(await page.getByRole("button", { name: "Expand Delivery Challans", exact: true }).count() === 1, `${department} Work Order omits DC Expand`)
		assert(await page.getByRole("button", { name: "Expand Goods Received Notes", exact: true }).count() === 1, `${department} Work Order omits GRN Expand`)
	}

	if (CAPTURE_DIR) {
		await page.goto(`${SITE}/web/fabric-store/work-orders`, { waitUntil: "domcontentloaded" })
		await page.locator(".list-row-open").first().waitFor({ timeout: 20_000 })
		await page.locator(".list-row-open").first().click()
		await page.locator(".fabric-work-order-frame").waitFor({ timeout: 20_000 })
		await page.locator(".work-order-tabs").waitFor({ timeout: 20_000 })
		await page.locator(".work-order-activity-rail").waitFor({ timeout: 20_000 })
		await capture(page, "03-work-order-navigation-and-expand.png")
	}
	await page.goto(`${SITE}/web/fabric-store/work-orders/${encodeURIComponent(fixture.name)}`, { waitUntil: "domcontentloaded" })
	const dcExpand = page.getByRole("button", { name: "Expand Delivery Challans", exact: true })
	await dcExpand.waitFor({ timeout: 20_000 })
	await dcExpand.click()
	let dialog = page.getByRole("dialog", { name: "Delivery Challans", exact: true })
	await dialog.waitFor({ timeout: 20_000 })
	await dialog.locator(".premium-list-table .p-datatable-tbody > tr").first().waitFor({ timeout: 20_000 })
	await capture(page, "04-expanded-delivery-challans-list.png")
	assert(listRequests.some((entry) => entry.doctype === "YRP Delivery Challan" && entry.filters.some((filter) => filter[0] === "work_order" && filter[2] === fixture.name)), `DC request omitted work_order=${fixture.name}: ${JSON.stringify(listRequests)}`)
	await dialog.locator(".list-row-open").first().click()
	const recordDialog = page.getByRole("dialog", { name: /Delivery Challan ·/ }).first()
	await recordDialog.waitFor({ timeout: 20_000 })
	await recordDialog.getByRole("button", { name: "Close workspace", exact: true }).click()
	dialog = page.getByRole("dialog", { name: "Delivery Challans", exact: true })
	await dialog.waitFor({ timeout: 20_000 })
	await dialog.locator(".p-dialog-close-button").click()

	const grnExpand = page.getByRole("button", { name: "Expand Goods Received Notes", exact: true })
	await grnExpand.click()
	dialog = page.getByRole("dialog", { name: "Goods Received Notes", exact: true })
	await dialog.waitFor({ timeout: 20_000 })
	await dialog.locator(".premium-list-table .p-datatable-tbody > tr").first().waitFor({ timeout: 20_000 })
	assert(listRequests.some((entry) => entry.doctype === "YRP Goods Received Note" && entry.filters.some((filter) => filter[0] === "against" && filter[2] === "YRP Work Order") && entry.filters.some((filter) => filter[0] === "against_id" && filter[2] === fixture.name)), `GRN request omitted exact Work Order lineage: ${JSON.stringify(listRequests)}`)
	await dialog.locator(".p-dialog-close-button").click()

	const purchaseOrders = await resourceNames(page.request, "Purchase Order")
	if (purchaseOrders.length) {
		await page.goto(`${SITE}/web/fabric-store/purchase-orders/${encodeURIComponent(purchaseOrders[0])}`, { waitUntil: "domcontentloaded" })
		await page.locator(".fabric-purchase-order-frame").waitFor({ timeout: 20_000 })
		assert(await page.getByRole("button", { name: /^Expand / }).count() === 0, "Purchase Order unexpectedly received expanded GRN lists")
	}

	return { workOrder: fixture.name, listRequests: listRequests.length }
}

async function paginationSuite(page) {
	const fixture = await findWorkOrder(page.request)
	let mode = "normal"
	const requests = []
	await page.route("**/api/resource/YRP%20Delivery%20Challan?*", async (route) => {
		const url = new URL(route.request().url())
		const start = Number(url.searchParams.get("limit_start") || 0)
		const pageLength = Number(url.searchParams.get("limit_page_length") || 20)
		requests.push({
			filters: JSON.parse(url.searchParams.get("filters") || "[]"),
			orderBy: url.searchParams.get("order_by") || "",
			start,
			pageLength,
		})
		if (mode === "error") return route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ message: "Related list unavailable" }) })
		const total = mode === "empty" ? 0 : 501
		const data = Array.from({ length: Math.max(0, Math.min(pageLength, total - start)) }, (_, offset) => {
			const index = start + offset + 1
			return {
				name: `DC-MOCK-${String(index).padStart(4, "0")}`,
				work_order: fixture.name,
				item: "CLOTH-001",
				lot: "LOT-001",
				posting_date: "2026-10-08",
				posting_time: "10:00:00",
				docstatus: index % 2,
				modified: "2026-10-08 10:00:00",
			}
		})
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data }) })
	})
	await page.route("**/api/method/frappe.desk.reportview.get_count*", async (route) => {
		let body = {}
		try { body = route.request().postDataJSON() || {} } catch { /* pass through */ }
		if (body.doctype !== "YRP Delivery Challan") return route.continue()
		if (mode === "error") return route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ message: "Related count unavailable" }) })
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: mode === "empty" ? 0 : 501 }) })
	})

	await page.goto(`${SITE}/web/fabric-store/work-orders/${encodeURIComponent(fixture.name)}`, { waitUntil: "domcontentloaded" })
	await page.getByRole("button", { name: "Expand Delivery Challans", exact: true }).click()
	const dialog = page.getByRole("dialog", { name: "Delivery Challans", exact: true })
	await dialog.waitFor({ timeout: 20_000 })
	await dialog.getByText("DC-MOCK-0001", { exact: true }).first().waitFor({ timeout: 20_000 })

	await dialog.locator(".list-search input").fill("0501")
	await page.waitForTimeout(450)
	assert(requests.some((request) => request.filters.some((filter) => filter[0] === "name" && filter[1] === "like" && filter[2] === "%0501%")), `Expanded-list search did not reach the server: ${JSON.stringify(requests.slice(-3))}`)
	await dialog.getByRole("button", { name: "Clear Filters", exact: true }).click()
	await dialog.locator(".p-datatable-thead th").first().click()
	await page.waitForTimeout(250)
	assert(requests.some((request) => request.orderBy.startsWith("name asc")), `Expanded-list sort did not reach the server: ${JSON.stringify(requests.slice(-3))}`)

	await dialog.getByRole("button", { name: "Last Page", exact: true }).click()
	await dialog.getByText("DC-MOCK-0501", { exact: true }).first().waitFor({ timeout: 20_000 })
	assert(requests.some((request) => request.start === 500), `The 501st related record was not requested: ${JSON.stringify(requests.slice(-3))}`)

	mode = "empty"
	await dialog.getByRole("button", { name: "Refresh", exact: true }).click()
	await dialog.getByText("No records found", { exact: true }).first().waitFor({ timeout: 20_000 })

	mode = "error"
	await dialog.getByRole("button", { name: "Refresh", exact: true }).click()
	await dialog.getByText("Unable to load Delivery Challans", { exact: true }).waitFor({ timeout: 20_000 })
	mode = "normal"
	await dialog.getByRole("button", { name: "Retry", exact: true }).click()
	await dialog.getByText("DC-MOCK-0501", { exact: true }).first().waitFor({ timeout: 20_000 })

	await page.setViewportSize({ width: 390, height: 844 })
	const mobile = await dialog.evaluate((element) => ({
		left: element.getBoundingClientRect().left,
		right: element.getBoundingClientRect().right,
		viewport: window.innerWidth,
		pageOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
	}))
	assert(mobile.left >= 0 && mobile.right <= mobile.viewport + 1 && mobile.pageOverflow <= 1, `Expanded list overflows mobile: ${JSON.stringify(mobile)}`)

	return { workOrder: fixture.name, requestCount: requests.length, lastStart: Math.max(...requests.map((request) => request.start)), mobile }
}

const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({ viewport: { width: 1600, height: 1000 } })

try {
	const loginPage = await context.newPage()
	await login(loginPage)
	await loginPage.close()
	const results = {}
	for (const [name, suite] of [["cutting", cuttingSuite], ["work-order", workOrderSuite], ["pagination", paginationSuite]]) {
		const page = await context.newPage()
		const errors = []
		page.on("pageerror", (error) => errors.push(error.message))
		page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()) })
		try {
			results[name] = await suite(page)
			const unexpectedErrors = name === "pagination"
				? errors.filter((message) => !message.startsWith("Failed to load resource:"))
				: errors
			assert(!unexpectedErrors.length, `${name} browser errors:\n${unexpectedErrors.join("\n")}`)
		} finally {
			await page.close()
		}
	}
	console.log(JSON.stringify({ passed: true, suites: results }, null, 2))
} finally {
	await browser.close()
}
