#!/usr/bin/env node

import { createRequire } from "node:module"
import { readFileSync } from "node:fs"

const require = createRequire("/home/anas/.claude/playwright/package.json")
const { chromium } = require("playwright")
const SITE = process.env.ESSDEE_TEST_SITE || "http://erp-migration-test.site:8001"
const suite = process.argv[2] || "launcher"

function assert(condition, message) { if (!condition) throw new Error(message) }

async function login(page) {
	const [username, password] = readFileSync("/home/anas/.frappe-debug-creds-mrp3", "utf8").trim().split("\n")
	await page.goto(`${SITE}/login`, { waitUntil: "domcontentloaded" })
	await page.fill("#login_email", username.trim())
	await page.fill("#login_password", password.trim())
	await Promise.all([
		page.waitForNavigation({ waitUntil: "domcontentloaded", timeout: 20_000 }).catch(() => {}),
		page.click(".btn-login, button[type=submit]"),
	])
}

async function noOverflow(page, label) {
	const geometry = await page.evaluate(() => ({
		viewport: innerWidth,
		page: document.documentElement.scrollWidth,
		containers: [".ppo-action-dialog", ".p-dialog-content", ".ppo-action-matrix", ".ppo-action-matrix table", ".fabric-document-workspace", ".fabric-document-workspace__content", ".fabric-document-workspace__columns", ".fabric-document-workspace__main", ".ppo-matrix__table-wrap"].map((selector) => {
			const element = document.querySelector(selector)
			if (!element) return { selector, missing: true }
			const box = element.getBoundingClientRect(), style = getComputedStyle(element)
			return { selector, left: Math.round(box.left), right: Math.round(box.right), width: Math.round(box.width), scrollWidth: element.scrollWidth, clientWidth: element.clientWidth, overflowX: style.overflowX, minWidth: style.minWidth, maxWidth: style.maxWidth }
		}),
		offenders: [...document.querySelectorAll("body *")].map((element) => {
			const box = element.getBoundingClientRect()
			return { tag: element.tagName, className: element.className?.toString?.() || "", left: Math.round(box.left), right: Math.round(box.right), scrollWidth: element.scrollWidth, clientWidth: element.clientWidth }
		}).filter((item) => item.right > innerWidth + 1 || item.left < -1).sort((left, right) => right.right - left.right).slice(0, 16),
	}))
	assert(geometry.page <= geometry.viewport + 1, `${label} overflows: ${JSON.stringify(geometry)}`)
}

function requestArgs(route) {
	try { return JSON.parse(route.request().postData() || "{}") } catch { return {} }
}

function reply(route, message, status = 200) {
	return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(status >= 400 ? message : { message }) })
}

function productionOrderWorkspace(overrides = {}) {
	const capabilities = Object.fromEntries([
		["save", "Edit"], ["request_ppo_approval", "Request PPO Approval"], ["approve_ppo", "Approve PPO"],
		["request_changes", "Request Changes"], ["update_quantity_ratio", "Update Quantity & Ratio"],
		["approve_quantity_ratio", "Approve Quantity & Ratio"], ["update_price", "Update Price"],
		["change_dates", "Change Dates"], ["change_status", "Change Status"], ["approve_status", "Approve Status"],
		["transfer_quantity", "Transfer Quantity"], ["approve_transfer", "Approve Transfer"],
		["create_lot", "Create Lot"], ["link_lot", "Link Lot"], ["reopen", "Reopen"],
		["cancel", "Cancel"], ["amend", "Amend"],
	].map(([key, label]) => [key, { allowed: true, label, reason: "" }]))
	capabilities.delete = { allowed: false, label: "Delete", reason: "Submitted Production Orders cannot be deleted." }
	return {
		fields: [
			{ fieldname: "production_term", label: "Production Term", fieldtype: "Link", value: "5 Piece Pack" },
			{ fieldname: "posting_date", label: "Posting Date", fieldtype: "Date", value: "2026-10-09" },
			{ fieldname: "delivery_date", label: "Delivery Date", fieldtype: "Date", value: "2026-10-20" },
			{ fieldname: "dont_deliver_after", label: "Don't Deliver After", fieldtype: "Date", value: "2026-10-25" },
			{ fieldname: "comments", label: "Comments", fieldtype: "Small Text", value: "Priority retail order" },
		],
		matrix: [
			{ size: "S", item_variant: "Premium Vest-S", quantity: 40, ratio: 1, prices: { mrp: 650, production_order_mrp: 640, wholesale_price: 410, retail_price: 720 } },
			{ size: "M", item_variant: "Premium Vest-M", quantity: 80, ratio: 2, prices: { mrp: 680, production_order_mrp: 670, wholesale_price: 430, retail_price: 750 } },
		],
		ordered: { S: 12, M: 18 }, linked_lots: ["LOT-26-0042"],
		histories: { dates: [{ date_field: "Delivery Date", previous_date: "2026-10-18", new_date: "2026-10-20", reason: "Customer revision" }], transfers: [] },
		permissions: { can_read: true, can_write: true, can_print: false }, capabilities,
		...overrides,
		record: {
			doctype: "YRP Production Order", name: "PPO-TEST-1", item: "Premium Vest",
			status: "Open", docstatus: 1, total_quantity: 120, posting_date: "2026-10-09",
			delivery_date: "2026-10-20", dont_deliver_after: "2026-10-25", lead_time_given: 11,
			modified: "2026-10-09 10:00:00", ...overrides.record,
		},
	}
}

function productionOrderEditor() {
	return {
		modified: "2026-10-09 10:00:00",
		fields: [
			{ fieldname: "naming_series", label: "Series", fieldtype: "Select", options: "PPO-\nPPO-.YYYY.-", value: "PPO-" },
			{ fieldname: "item", label: "Item", fieldtype: "Link", value: "Premium Vest" },
			{ fieldname: "production_detail", label: "Production Detail", fieldtype: "Link", value: "Premium Vest-1" },
			{ fieldname: "production_term", label: "Production Term", fieldtype: "Link", value: "5 Piece Pack" },
			{ fieldname: "delivery_date", label: "Delivery Date", fieldtype: "Date", value: "2026-10-20" },
			{ fieldname: "dont_deliver_after", label: "Don't Deliver After", fieldtype: "Date", value: "2026-10-25" },
			{ fieldname: "comments", label: "Comments", fieldtype: "Small Text", value: "Priority retail order" },
			{ fieldname: "skip_box_sticker_print", label: "Skip Box Sticker Print", fieldtype: "Check", value: 0 },
		],
		matrix: {
			item: "Premium Vest", primary_attribute: "Size", primary_values: ["S", "M"],
			items: {
				S: { qty: 40, ratio: 1, mrp: 650, wholesale: 410, retail: 720 },
				M: { qty: 80, ratio: 2, mrp: 680, wholesale: 430, retail: 750 },
			}, ordered: { S: 12, M: 18 },
		},
	}
}

function ppoReportFixture() {
	return {
		orders: [
			{
				name: "PPO-TEST-1", item: "Premium Vest", fabric: "Cotton Lycra", dia: "34 Dia", gsm: 180, production_detail: "Premium Vest-1",
				production_term: "5 Piece Pack", posting_date: "2026-10-09", delivery_date: "2026-10-20",
				dont_deliver_after: "2026-10-25", lead_time: 11, status: "Open", comments: "Priority retail order",
				group_label: "Mens", group_sizes: ["S", "M", "L"], qty_by_position: [40, 80, 0], total: 120,
			},
			{
				name: "PPO-TEST-2", item: "Junior Capri", fabric: "Single Jersey", dia: "30 Dia", gsm: 160, production_detail: "Junior Capri-2",
				production_term: "10 Piece Pack", posting_date: "2026-10-10", delivery_date: "2026-10-22",
				dont_deliver_after: "2026-10-28", lead_time: 12, status: "PPO Request", comments: "",
				group_label: "Kids", group_sizes: ["28", "30"], qty_by_position: [60, 40, 0], total: 100,
			},
		],
		size_groups: [
			{ label: "Mens", sizes: ["S", "M", "L"] },
			{ label: "Kids", sizes: ["28", "30"] },
		],
		max_columns: 3,
		summary: { total_orders: 2, total_quantity: 220, size_groups: 2 },
	}
}

async function chooseSelect(dialog, index, label) {
	await dialog.locator(".p-select").nth(index).click()
	await dialog.page().getByRole("option", { name: label, exact: true }).click()
}

async function openAction(page, label) {
	const direct = page.getByRole("button", { name: label, exact: true })
	if (await direct.count() && await direct.first().isVisible()) return direct.first().click()
	await page.getByRole("button", { name: "More", exact: true }).click()
	return page.getByRole("menuitem", { name: label, exact: true }).click()
}

async function dialogGeometry(page, label) {
	const dialog = page.locator(".ppo-action-dialog:visible")
	for (const width of [390, 900, 1600]) {
		await page.setViewportSize({ width, height: 900 })
		await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))))
		await noOverflow(page, `${label} page at ${width}`)
		const geometry = await dialog.evaluate((element) => {
			const box = element.getBoundingClientRect()
			const footer = element.querySelector(".p-dialog-footer")?.getBoundingClientRect()
			return { left: box.left, right: box.right, top: box.top, bottom: box.bottom, footerBottom: footer?.bottom || 0 }
		})
		assert(geometry.left >= -1 && geometry.right <= width + 1 && geometry.top >= -1 && geometry.bottom <= 901 && geometry.footerBottom <= 901, `${label} clips at ${width}: ${JSON.stringify(geometry)}`)
	}
	await page.setViewportSize({ width: 1280, height: 900 })
}

function sourceChecks() {
	const router = readFileSync("frontend/src/router/index.js", "utf8")
	const list = router.indexOf('path: "/sales/production-orders"')
	const create = router.indexOf('path: "/sales/production-orders/new"')
	const edit = router.indexOf('path: "/sales/production-orders/:productionOrderId/edit"')
	const view = router.indexOf('path: "/sales/production-orders/:productionOrderId"', edit + 1)
	const reports = router.indexOf('path: "/sales/reports"')
	assert(list >= 0, "Sales Production Order list route is missing")
	if (!["launcher", "source"].includes(suite)) {
		assert(create > list && edit > create && view > edit, "Sales Production Order routes are missing or ordered unsafely")
	}
	if (["reports", "all"].includes(suite)) assert(reports >= 0, "Sales Reports route is missing")
	const api = readFileSync("frontend/src/api/sales.js", "utf8")
	for (const method of ["get_capabilities", "get_production_order_workspace", "get_production_order_editor", "save_production_order", "execute_production_order_command", "get_ppo_report", "get_ppo_dispatch_summary", "download_ppo_report"]) {
		assert(api.includes(method), `Sales API is missing ${method}`)
	}
}

async function reportSuite(page) {
	const reportRequests = []
	const dispatchRequests = []
	const downloads = []
	let reportResult = ppoReportFixture()
	let failNextReport = false
	await page.route("**/api/method/**", async (route) => {
		const method = new URL(route.request().url()).pathname.split("/api/method/")[1]
		const args = requestArgs(route)
		if (method === "essdee_yrp.sales.web_workspace.get_capabilities") {
			return reply(route, {
				sections: { reports: { label: "Reports", can_read: true, can_report: true } },
				reports: { ppo_report: { label: "PPO Report", can_read: true, can_export: true } },
			})
		}
		if (method === "essdee_yrp.sales.web_workspace.get_ppo_report") {
			reportRequests.push(args)
			if (failNextReport) {
				failNextReport = false
				return reply(route, { _server_messages: JSON.stringify([JSON.stringify({ message: "The PPO Report could not be generated for this period." })]) }, 500)
			}
			return reply(route, reportResult)
		}
		if (method === "essdee_yrp.sales.web_workspace.get_ppo_dispatch_summary") {
			dispatchRequests.push(args)
			return reply(route, { sizes: ["S", "M"], rows: [{ date: "2026-10-18", lot: "LOT-26-0042", sizes: { S: 10, M: 20 }, total: 30 }] })
		}
		if (method === "essdee_yrp.sales.web_workspace.download_ppo_report") {
			downloads.push(args)
			return route.fulfill({
				status: 200,
				headers: { "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "Content-Disposition": 'attachment; filename="PPO_Report_09-10-2026.xlsx"' },
				body: "sales-report",
			})
		}
		if (method === "essdee_yrp.api.link_search.link_search") return reply(route, [{ name: "Menswear", label: "Menswear" }])
		return route.continue()
	})

	await page.goto(`${SITE}/web/sales/reports`, { waitUntil: "domcontentloaded" })
	await page.getByRole("heading", { name: "PPO Report", exact: true }).waitFor()
	assert(await page.getByText("Set the report filters", { exact: true }).isVisible(), "Report must wait for an explicit Generate action")
	assert(reportRequests.length === 0, "PPO Report fetched before Generate")
	assert(await page.getByRole("tab").count() === 0, "A single Sales report must not add a redundant tab strip")

	await page.getByLabel("Status").click()
	await page.getByRole("option", { name: "Open", exact: true }).click()
	await page.getByRole("combobox", { name: "Product Category", exact: true }).fill("Mens")
	await page.getByRole("option", { name: "Menswear", exact: true }).click()
	await page.getByLabel("From Date").fill("01-10-2026")
	await page.getByLabel("From Date").press("Tab")
	await page.getByLabel("To Date").fill("31-10-2026")
	await page.getByLabel("To Date").press("Tab")
	await page.getByRole("button", { name: "Generate", exact: true }).click()
	await page.getByText("PPO-TEST-1", { exact: true }).waitFor()
	assert(reportRequests.length === 1, `Generate fetched ${reportRequests.length} times`)
	assert(JSON.stringify(reportRequests[0]?.filters) === JSON.stringify({ status: "Open", product_category: "Menswear", from_date: "2026-10-01", to_date: "2026-10-31" }), `Report filters are incomplete: ${JSON.stringify(reportRequests[0])}`)
	const report = page.locator(".ppo-report")
	const reportText = await report.innerText()
	assert(reportText.includes("2") && reportText.includes("220") && reportText.includes("2 size groups"), `Report summary is incomplete: ${reportText}`)
	const header = await report.locator(".ppo-report__matrix thead").innerText()
	for (const value of ["MENS", "S", "M", "L", "KIDS", "28", "30"]) assert(header.includes(value), `Mixed size header ${value} is missing: ${header}`)
	assert(reportText.includes("20-10-2026") && reportText.includes("25-10-2026") && !reportText.includes("2026-10-20"), "Report dates must use DD-MM-YYYY")
	assert((await report.locator("tfoot").innerText()).includes("220"), "Report totals row is missing")

	await report.getByRole("button", { name: "Show dispatch for PPO-TEST-1", exact: true }).click()
	await report.getByText("LOT-26-0042", { exact: true }).waitFor()
	assert(dispatchRequests.length === 1 && dispatchRequests[0]?.production_order === "PPO-TEST-1", `Dispatch summary request is wrong: ${JSON.stringify(dispatchRequests)}`)
	const dispatchText = await report.locator(".ppo-report__dispatch").innerText()
	assert(dispatchText.includes("18-10-2026") && dispatchText.includes("30"), `Dispatch summary is incomplete: ${dispatchText}`)

	const downloadEvent = page.waitForEvent("download")
	await page.getByRole("button", { name: "Download Excel", exact: true }).click()
	const download = await downloadEvent
	assert(download.suggestedFilename() === "PPO_Report_09-10-2026.xlsx", `Excel filename is wrong: ${download.suggestedFilename()}`)
	assert(JSON.stringify(downloads[0]) === JSON.stringify({ status: "Open", product_category: "Menswear", from_date: "2026-10-01", to_date: "2026-10-31" }), `Excel filters differ from generated report: ${JSON.stringify(downloads[0])}`)

	reportResult = { orders: [], size_groups: [], max_columns: 0, summary: { total_orders: 0, total_quantity: 0, size_groups: 0 } }
	await page.getByRole("button", { name: "Generate", exact: true }).click()
	await page.getByText("No matching records", { exact: true }).waitFor()
	failNextReport = true
	await page.getByRole("button", { name: "Generate", exact: true }).click()
	const errorDialog = page.locator(".document-error-dialog:visible")
	await errorDialog.waitFor()
	assert((await errorDialog.innerText()).includes("could not be generated for this period"), "Report failure is not explained in the standard error popup")
	await errorDialog.getByRole("button", { name: "OK", exact: true }).click()

	reportResult = ppoReportFixture()
	await page.getByRole("button", { name: "Generate", exact: true }).click()
	await page.getByText("PPO-TEST-1", { exact: true }).waitFor()
	for (const width of [390, 900, 1600]) {
		await page.setViewportSize({ width, height: 900 })
		await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))))
		await noOverflow(page, `PPO Report at ${width}`)
		const geometry = await page.locator(".ppo-report__matrix-wrap").evaluate((element) => ({ overflowX: getComputedStyle(element).overflowX, clientWidth: element.clientWidth, scrollWidth: element.scrollWidth }))
		assert(geometry.overflowX === "auto", `Wide PPO matrix lacks local horizontal flow at ${width}: ${JSON.stringify(geometry)}`)
		if (width === 1600 && process.env.ESSDEE_SALES_SCREENSHOTS) await page.screenshot({ path: `${process.env.ESSDEE_SALES_SCREENSHOTS}/ppo-report.png`, fullPage: true, animations: "disabled" })
	}
	console.log("PASS reports: explicit filters, mixed size matrix, totals, dispatch, dates, Excel, empty/error states, responsive flow")
}

async function launcherSuite(page) {
	let capabilities = {
		sections: {
			production_orders: { label: "Production Orders", can_read: true, can_create: true },
			reports: { label: "Reports", can_read: true, can_report: true },
		},
		reports: { ppo_report: { label: "PPO Report", can_read: true, can_export: true } },
	}
	const listRequests = []
	await page.route("**/api/resource/YRP%20Production%20Order**", async (route) => {
		listRequests.push(route.request().url())
		return route.fulfill({ contentType: "application/json", body: JSON.stringify({ data: [{ name: "PPO-TEST-1", item: "Premium Vest", production_term: "5 Piece Pack", delivery_date: "2026-10-20", status: "Open", modified: "2026-10-09 10:00:00", docstatus: 1 }] }) })
	})
	await page.route("**/api/method/**", async (route) => {
		const method = new URL(route.request().url()).pathname.split("/api/method/")[1]
		if (method === "essdee_yrp.sales.web_workspace.get_capabilities") {
			return route.fulfill({ contentType: "application/json", body: JSON.stringify({ message: capabilities }) })
		}
		if (method === "frappe.desk.form.load.getdoctype") {
			return route.fulfill({ contentType: "application/json", body: JSON.stringify({ docs: [{ name: "YRP Production Order", is_submittable: 1, fields: [
				{ fieldname: "item", label: "Item", fieldtype: "Link", options: "Item", in_list_view: 1 },
				{ fieldname: "production_term", label: "Production Term", fieldtype: "Link", options: "YRP Production Term", in_list_view: 1 },
				{ fieldname: "delivery_date", label: "Delivery Date", fieldtype: "Date", in_list_view: 1 },
				{ fieldname: "status", label: "Status", fieldtype: "Select", options: "Draft\nPPO Request\nOpen\nPending Request\nClosed", in_list_view: 1 },
			] }] }) })
		}
		if (method.endsWith("yrp_user_listview.get_user_listview")) {
			return route.fulfill({ contentType: "application/json", body: JSON.stringify({ message: [] }) })
		}
		if (method === "frappe.desk.reportview.get_count") {
			return route.fulfill({ contentType: "application/json", body: JSON.stringify({ message: 1 }) })
		}
		return route.continue()
	})

	await page.goto(`${SITE}/web/sales`, { waitUntil: "domcontentloaded" })
	const cards = page.locator(".workspace-launcher__card")
	await cards.nth(1).waitFor()
	assert(await cards.count() === 2, "Sales must show exactly two launcher cards")
	assert(JSON.stringify(await cards.locator("strong").allTextContents()) === JSON.stringify(["Production Orders", "Reports"]), "Sales launcher labels are incorrect")
	assert(await cards.nth(0).getAttribute("href") === "/web/sales/production-orders", "Production Orders card has wrong route")
	assert(await cards.nth(1).getAttribute("href") === "/web/sales/reports", "Reports card has wrong route")

	capabilities = { sections: { production_orders: capabilities.sections.production_orders }, reports: {} }
	await page.reload({ waitUntil: "domcontentloaded" })
	await cards.first().waitFor()
	assert(await cards.count() === 1 && await cards.first().innerText().then(text => text.includes("Production Orders")), "Denied report capability leaked its card")

	await page.goto(`${SITE}/web/sales/production-orders`, { waitUntil: "domcontentloaded" })
	await page.getByRole("heading", { name: "Production Orders", exact: true }).waitFor()
	await page.getByText("PPO-TEST-1", { exact: true }).first().waitFor()
	assert(listRequests.length === 1, `Production Order list loaded ${listRequests.length} times`)
	assert(await page.locator(".list-status-tabs").count() === 1, "Production Order statuses are not split into list tabs")
	assert(await page.getByRole("button", { name: /Create Production Order/ }).isVisible(), "Permitted create action is missing")
	for (const width of [390, 900, 1600]) {
		await page.setViewportSize({ width, height: 900 })
		await noOverflow(page, `Sales list at ${width}`)
	}
	console.log("PASS launcher: exact cards, capability hiding, compact status list, create action, responsive flow")
}

async function productionOrderSuite(page) {
	const commands = []
	const saves = []
	const pageErrors = []
	page.on("pageerror", (reason) => pageErrors.push(reason.message))
	let workspace = productionOrderWorkspace()
	let failNextCommand = false
	await page.route("**/api/method/**", async (route) => {
		const method = new URL(route.request().url()).pathname.split("/api/method/")[1]
		const args = requestArgs(route)
		if (method === "essdee_yrp.sales.web_workspace.get_production_order_workspace") return reply(route, workspace)
		if (method === "essdee_yrp.sales.web_workspace.get_production_order_editor") return reply(route, productionOrderEditor())
		if (method === "essdee_yrp.sales.web_workspace.save_production_order") {
			saves.push(args)
			return reply(route, workspace)
		}
		if (method === "essdee_yrp.sales.web_workspace.execute_production_order_command") {
			commands.push(args)
			if (failNextCommand) {
				failNextCommand = false
				return reply(route, { _server_messages: JSON.stringify([JSON.stringify({ message: "This Production Order changed after you opened it. Reload and try again." })]) }, 409)
			}
			workspace = productionOrderWorkspace({ record: { modified: `2026-10-09 10:00:0${commands.length}` } })
			return reply(route, workspace)
		}
		if (method === "essdee_yrp.api.link_search.link_search") return reply(route, [{ name: "PPO-TEST-2", label: "PPO-TEST-2" }])
		return route.continue()
	})

	await page.goto(`${SITE}/web/sales/production-orders/PPO-TEST-1`, { waitUntil: "domcontentloaded" })
	await page.getByRole("heading", { name: "Premium Vest", exact: true }).waitFor()
	assert(await page.getByText("Production order · PPO-TEST-1", { exact: true }).isVisible(), "Item must be the primary identity and PPO the secondary identity")
	const matrix = page.locator(".ppo-matrix")
	assert((await matrix.innerText()).includes("120 pcs") && (await matrix.innerText()).includes("Premium Vest-S"), "Size matrix did not render quantities and variants")
	assert((await matrix.locator("thead").innerText()).includes("PRODUCTION ORDER MRP"), "Size matrix did not expose Production Order MRP")
	assert((await page.locator(".ppo-page__metric").first().innerText()).includes("120"), "Total quantity metric is missing")
	const overviewText = await page.locator(".ppo-overview").innerText()
	assert(overviewText.includes("25-10-2026") && !overviewText.includes("2026-10-25"), `Overview dates must use DD-MM-YYYY: ${overviewText}`)
	assert(await page.getByRole("button", { name: "Delete", exact: true }).count() === 0, "Denied Delete capability leaked into the UI")

	await page.getByRole("button", { name: "More", exact: true }).click()
	const menuText = await page.locator(".document-action-menu:visible").innerText()
	for (const label of ["Update Price", "Change Dates", "Change Status", "Transfer Quantity", "Create Lot", "Link Lot", "Reopen", "Cancel", "Amend"]) {
		assert(menuText.includes(label), `Allowed action ${label} is missing from the action menu`)
	}
	assert(!menuText.includes("Delete"), "Denied Delete capability leaked into the action menu")
	await page.keyboard.press("Escape")
	await page.locator(".document-action-menu").waitFor({ state: "hidden" })

	await page.getByRole("button", { name: "Request PPO Approval", exact: true }).click()
	const confirmation = page.locator(".document-confirmation-shell:visible")
	await confirmation.getByRole("button", { name: "Request PPO Approval", exact: true }).click()
	await confirmation.waitFor({ state: "hidden" })
	assert(commands.at(-1)?.command === "request_ppo_approval", `PPO request sent wrong command: ${JSON.stringify(commands.at(-1))}`)
	assert(commands.at(-1)?.expected_modified === "2026-10-09 10:00:00", "PPO request omitted the original modified token")

	await openAction(page, "Update Quantity & Ratio")
	const quantityDialog = page.locator(".ppo-action-dialog:visible")
	await quantityDialog.waitFor()
	await page.locator(".document-action-menu").waitFor({ state: "hidden" })
	await dialogGeometry(page, "Quantity and ratio dialog")
	await chooseSelect(quantityDialog, 0, "Sales Team")
	await quantityDialog.locator("textarea").fill("Rebalanced to the confirmed assortment")
	await quantityDialog.locator("tbody tr").first().locator("input").first().fill("45")
	await quantityDialog.getByRole("button", { name: "Send Request", exact: true }).click()
	await quantityDialog.waitFor({ state: "hidden" })
	const quantityCommand = commands.at(-1)
	assert(quantityCommand.command === "update_quantity_ratio", `Quantity update sent wrong command: ${JSON.stringify(quantityCommand)}`)
	assert(quantityCommand.expected_modified === "2026-10-09 10:00:01", "Quantity update omitted refreshed modified token")
	assert(quantityCommand.payload?.size_quantities?.S === 45 && quantityCommand.payload?.size_ratios?.M === 2 && quantityCommand.payload?.requested_by === "Sales Team", `Quantity payload is incomplete: ${JSON.stringify(quantityCommand.payload)}`)

	failNextCommand = true
	await openAction(page, "Request Changes")
	const changesDialog = page.locator(".ppo-action-dialog:visible")
	await changesDialog.locator("textarea").fill("Confirm the customer delivery commitment")
	await changesDialog.getByRole("button", { name: "Request Changes", exact: true }).click()
	const errorDialog = page.locator(".document-error-dialog:visible")
	await errorDialog.waitFor()
	assert(await page.locator(".document-error-dialog:visible").count() === 1, "Command failure must open exactly one standard error dialog")
	assert((await errorDialog.innerText()).includes("changed after you opened it"), "Stale-write error was not explained clearly")
	await errorDialog.getByRole("button", { name: "OK", exact: true }).click()
	await errorDialog.waitFor({ state: "hidden" })

	for (const width of [390, 900, 1600]) {
		await page.setViewportSize({ width, height: 900 })
		await noOverflow(page, `Production Order view at ${width}`)
		if (width === 1600 && process.env.ESSDEE_SALES_SCREENSHOTS) await page.screenshot({ path: `${process.env.ESSDEE_SALES_SCREENSHOTS}/production-order-view.png`, fullPage: true, animations: "disabled" })
	}
	await page.setViewportSize({ width: 1280, height: 900 })

	await page.goto(`${SITE}/web/sales/production-orders/PPO-TEST-1/edit`, { waitUntil: "domcontentloaded" })
	await page.getByRole("heading", { name: "Edit Production Order", exact: true }).waitFor()
	const editorText = await page.locator(".ppo-editor").innerText()
	const editorMatrixText = await page.locator(".ppo-matrix").innerText()
	assert((await page.locator('.ppo-editor input[value="Premium Vest"]').count()) === 1 && editorMatrixText.includes("120 pcs"), `Editor did not load the existing fields and matrix: ${JSON.stringify({ editorText, editorMatrixText })}`)
	if (process.env.ESSDEE_SALES_SCREENSHOTS) await page.screenshot({ path: `${process.env.ESSDEE_SALES_SCREENSHOTS}/production-order-editor.png`, fullPage: true, animations: "disabled" })
	await Promise.all([
		page.waitForRequest((request) => request.url().includes("essdee_yrp.sales.web_workspace.save_production_order")),
		page.getByRole("button", { name: "Save", exact: true }).click(),
	])
	assert(saves.length === 1, `Draft editor saved ${saves.length} times`)
	assert(saves[0].name === "PPO-TEST-1" && saves[0].expected_modified === "2026-10-09 10:00:00" && saves[0].submit === false, `Draft save coordination is incomplete: ${JSON.stringify(saves[0])}`)
	assert(saves[0].values?.item_details?.[0]?.entries?.find((entry) => entry.attributes?.Size === "M")?.qty === 80, "Draft save did not preserve the complete variant matrix")
	await page.waitForURL(/\/web\/sales\/production-orders\/PPO-TEST-1$/)
	assert(pageErrors.length === 0, `Production Order page errors: ${pageErrors.join("\n")}`)
	console.log("PASS production-orders: identity, matrix, capabilities, lifecycle, workflow payloads, stale popup, editor save, responsive flow")
}

sourceChecks()
if (suite === "source") process.exit(0)
const browser = await chromium.launch({ headless: true })
try {
	for (const [name, run] of [["launcher", launcherSuite], ["production-orders", productionOrderSuite], ["reports", reportSuite]]) {
		if (![name, "all"].includes(suite)) continue
		const page = await browser.newPage({ viewport: { width: 1280, height: 900 } })
		await login(page)
		try { await run(page) } finally { await page.close() }
	}
} finally {
	await browser.close()
}
