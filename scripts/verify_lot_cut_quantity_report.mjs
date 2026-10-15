#!/usr/bin/env node

import { createRequire } from "node:module"
import { readFileSync } from "node:fs"

const require = createRequire("/home/anas/.claude/playwright/package.json")
const { chromium } = require("playwright")

const SITE = process.env.ESSDEE_TEST_SITE || "http://erp-migration-test.site:8001"
const CREDENTIALS = "/home/anas/.frappe-debug-creds-mrp3"
const REPORT_METHOD = "essdee_yrp.purchase.lot_cut_quantity.get_lot_cut_quantity"
const LOTS = ["LOT-A", "LOT-B", "LOT-C", "LOT-D"]
const GUARD_LOTS = Array.from({ length: 21 }, (_, index) => `LOT-GUARD-${String(index + 1).padStart(2, "0")}`)

function assert(condition, message) {
	if (!condition) throw new Error(message)
}

function parseBody(route) {
	try { return JSON.parse(route.request().postData() || "{}") } catch { return {} }
}

const fixtures = {
	"LOT-A": {
		lot: "LOT-A",
		cutting_plans: [
			{
				name: "CP-A-SM",
				item: "ITEM-NORMAL",
				version: "V1",
				completed_items: [{
					attributes: ["Colour"],
					primary_attribute_values: ["S", "M"],
					stiching_attr: "Panel",
					Panel: ["Front", "Back"],
					items: [{
						name: "ROW-A-COMPLETE",
						attributes: { Colour: "Navy" },
						values: { S: 4, M: 5 },
						completed: true,
					}],
				}],
			},
			{
				name: "CP-A-LXL",
				item: "ITEM-ALTERNATE",
				version: "V3",
				completed_items: [{
					attributes: ["Colour"],
					primary_attribute_values: ["L", "XL"],
					items: [{
						name: "ROW-A-PENDING",
						attributes: { Colour: "Red" },
						values: { L: 6, XL: 7 },
						completed: false,
					}],
				}],
			},
		],
	},
	"LOT-B": {
		lot: "LOT-B",
		cutting_plans: [{
			name: "CP-B-SET",
			item: "ITEM-SET",
			version: "V2",
			completed_items: [{
				is_set_item: true,
				set_item_attr: "Part",
				stiching_attr: "Panel",
				attributes: ["Colour", "Part"],
				primary_attribute_values: ["S", "M"],
				Panel: { Top: ["Front", "Back"], Bottom: ["Front Leg", "Back Leg"] },
				items: [
					{
						name: "ROW-B-TOP",
						attributes: { Colour: "Green", Part: "Top" },
						values: { S: 8, M: 9 },
						completed: true,
					},
					{
						name: "ROW-B-BOTTOM",
						attributes: { Colour: "Green", Part: "Bottom" },
						values: { S: 7, M: 8 },
						completed: false,
					},
				],
			}],
		}],
	},
	"LOT-C": { lot: "LOT-C", cutting_plans: [] },
	"LOT-D": {
		lot: "LOT-D",
		cutting_plans: [{
			name: "CP-D-EMPTY",
			item: "ITEM-EMPTY",
			version: "V1",
			completed_items: [],
		}],
	},
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

async function selectLot(page, report, name) {
	const input = report.getByRole("combobox", { name: "Lot", exact: true })
	await input.fill(name)
	const option = page.locator(".p-autocomplete-overlay:visible .p-autocomplete-option").filter({ hasText: name }).first()
	await option.waitFor({ timeout: 20_000 })
	await option.click()
}

async function tableHeaders(plan) {
	return plan.locator(".completed-report__table thead th").allTextContents().then((values) => values.map((value) => value.trim()))
}

const browser = await chromium.launch({ headless: true })
try {
	const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
	const page = await context.newPage()
	const errors = []
	const reportRequests = []
	page.on("pageerror", (error) => errors.push(`page: ${error.message}`))
	page.on("console", (message) => { if (message.type() === "error") errors.push(`console: ${message.text()}`) })

	await login(page)
	errors.length = 0

	await page.route("**/api/method/essdee_yrp.fabric_store.web_workspace.get_capabilities*", (route) => route.fulfill({
		status: 200,
		contentType: "application/json",
		body: JSON.stringify({ message: { sections: { reports: {
			label: "Reports",
			reports: {
				stock_balance: { label: "Stock Balance", can_read: true },
				purchase_order_itemwise: { label: "Purchase Order Itemwise", can_read: true },
				lot_cut_quantity: { label: "Lot Cut Quantity", can_read: true, can_read_cutting_plan: true },
			},
		} } } }),
	}))
	await page.route("**/api/method/essdee_yrp.api.link_search.link_search*", (route) => {
		const body = parseBody(route)
		const query = String(body.txt || "").toUpperCase()
		const names = [...LOTS, ...GUARD_LOTS].filter((name) => name.includes(query))
		return route.fulfill({
			status: 200,
			contentType: "application/json",
			body: JSON.stringify({ message: names.map((name) => ({ name, label: name })) }),
		})
	})
	await page.route(`**/api/method/${REPORT_METHOD}*`, (route) => {
		const body = parseBody(route)
		const lots = Array.isArray(body.lots) ? body.lots : []
		reportRequests.push(lots)
		return route.fulfill({
			status: 200,
			contentType: "application/json",
			body: JSON.stringify({ message: { lots: lots.map((name) => fixtures[name]).filter(Boolean) } }),
		})
	})

	await page.goto(`${SITE}/web/purchase/reports`, { waitUntil: "domcontentloaded" })
	const reports = page.locator(".fabric-reports")
	await reports.waitFor({ timeout: 20_000 })
	const reportTabs = reports.getByRole("tab")
	await reportTabs.nth(2).waitFor({ timeout: 20_000 })
	const reportTabLabels = (await reportTabs.allTextContents()).map((value) => value.trim())
	assert(reportTabLabels.includes("Lot Cut Quantity"), `Lot Cut Quantity tab is missing: ${JSON.stringify(reportTabLabels)}`)
	await reportTabs.filter({ hasText: "Lot Cut Quantity" }).click()
	const report = reports.locator(".lot-cut-quantity-report")
	await report.waitFor({ timeout: 20_000 })

	const generate = report.getByRole("button", { name: "Generate", exact: true })
	assert(await generate.isDisabled(), "Generate is enabled with zero selected Lots")

	const selectedOrder = ["LOT-B", "LOT-A", "LOT-D", "LOT-C"]
	for (const lot of selectedOrder) await selectLot(page, report, lot)
	assert(await report.locator(".p-autocomplete-chip").count() === selectedOrder.length, "The real multi-select did not retain all selected Lots")
	assert(!await generate.isDisabled(), "Generate remains disabled with valid Lot selections")
	await generate.click()
	await report.locator(".lot-cut-quantity-report__lot").nth(selectedOrder.length - 1).waitFor({ timeout: 20_000 })

	assert(JSON.stringify(reportRequests) === JSON.stringify([selectedOrder]), `Unexpected report requests: ${JSON.stringify(reportRequests)}`)
	const renderedOrder = (await report.locator(".lot-cut-quantity-report__lot-header h2").allTextContents()).map((value) => value.trim())
	assert(JSON.stringify(renderedOrder) === JSON.stringify(selectedOrder), `Lot blocks are not in selected order: ${JSON.stringify(renderedOrder)}`)

	const lotBlocks = report.locator(".lot-cut-quantity-report__lot")
	const lotA = lotBlocks.nth(renderedOrder.indexOf("LOT-A"))
	const plansA = lotA.locator(".lot-cut-quantity-report__plan")
	assert(await lotA.locator(".lot-cut-quantity-report__lot-header").getByText("ITEM-NORMAL", { exact: true }).count() === 1, "Lot A does not show its first plan item once in the Lot header")
	assert(await plansA.count() === 2, "Lot A does not render a separate matrix block for each Cutting Plan")
	const planSm = plansA.filter({ hasText: "CP-A-SM" })
	const planLxl = plansA.filter({ hasText: "CP-A-LXL" })
	assert(await planSm.locator(".lot-cut-quantity-report__plan-header").getByRole("link", { name: "CP-A-SM", exact: true }).count() === 1, "CP-A-SM is not linked from its plan header")
	assert(await planLxl.locator(".lot-cut-quantity-report__plan-header").getByRole("link", { name: "CP-A-LXL", exact: true }).count() === 1, "CP-A-LXL is not linked from its plan header")
	assert(JSON.stringify(await tableHeaders(planSm)) === JSON.stringify(["S.No.", "Colour", "S", "M", "Total", "Completed"]), `CP-A-SM has the wrong size headers: ${JSON.stringify(await tableHeaders(planSm))}`)
	assert(JSON.stringify(await tableHeaders(planLxl)) === JSON.stringify(["S.No.", "Colour", "L", "XL", "Total", "Completed"]), `CP-A-LXL has the wrong size headers: ${JSON.stringify(await tableHeaders(planLxl))}`)
	assert(await planSm.locator(".lot-cut-quantity-report__plan-header").getByText("ITEM-NORMAL", { exact: true }).count() === 0, "The first plan redundantly repeats the Lot item")
	assert(await planLxl.locator(".lot-cut-quantity-report__plan-header").getByText("ITEM-ALTERNATE", { exact: true }).count() === 1, "A plan whose item differs from the Lot item does not identify it")
	assert(!/\bV[123]\b/.test(await plansA.locator(".lot-cut-quantity-report__plan-header").allTextContents().then((values) => values.join(" "))), "Plan headers still render version text")
	const checkedRow = planSm.locator('input[type="checkbox"]')
	const uncheckedRow = planLxl.locator('input[type="checkbox"]')
	assert(await checkedRow.count() === 1 && await checkedRow.isChecked() && await checkedRow.isDisabled(), "The completed row is not rendered as a checked, read-only checkbox")
	assert(await uncheckedRow.count() === 1 && !await uncheckedRow.isChecked() && await uncheckedRow.isDisabled(), "The incomplete row is not rendered as an unchecked, read-only checkbox")

	const lotB = lotBlocks.nth(renderedOrder.indexOf("LOT-B"))
	assert(await lotB.locator(".completed-report__group").count() === 2, "Set item rows were not split into separate part tables")
	const parts = (await lotB.locator(".completed-report__part strong").allTextContents()).map((value) => value.trim())
	assert(JSON.stringify(parts) === JSON.stringify(["Top", "Bottom"]), `Set item part tables are wrong: ${JSON.stringify(parts)}`)

	const lotC = lotBlocks.nth(renderedOrder.indexOf("LOT-C"))
	assert(await lotC.getByText("No Cutting Plan for this Lot.", { exact: true }).count() === 1, "Lot C does not show the no-plan state")
	const lotD = lotBlocks.nth(renderedOrder.indexOf("LOT-D"))
	assert(await lotD.getByText("No completed cut quantity rows", { exact: true }).count() === 1, "Lot D does not show the no-rows state")

	const accessibility = await report.locator(".completed-report").evaluateAll((instances) => {
		const headings = instances.flatMap((instance) => [...instance.querySelectorAll(".completed-report__sr-only")])
		const ids = headings.map((heading) => heading.id)
		const references = instances.flatMap((instance) => [...instance.querySelectorAll("[aria-labelledby]")])
		return {
			ids,
			broken: references.map((element) => {
				const id = element.getAttribute("aria-labelledby")
				const target = document.getElementById(id)
				return !target || target.closest(".completed-report") !== element.closest(".completed-report") ? id : null
			}).filter(Boolean),
		}
	})
	assert(accessibility.ids.length === 4, `Unexpected completed matrix heading count: ${JSON.stringify(accessibility.ids)}`)
	assert(new Set(accessibility.ids).size === accessibility.ids.length, `Completed matrix heading IDs are duplicated: ${JSON.stringify(accessibility.ids)}`)
	assert(accessibility.broken.length === 0, `Completed matrix aria-labelledby references resolve outside their component: ${JSON.stringify(accessibility.broken)}`)

	await report.getByRole("button", { name: "Reset", exact: true }).click()
	assert(await generate.isDisabled(), "Generate is enabled after Reset clears the Lot selection")
	for (const lot of GUARD_LOTS) await selectLot(page, report, lot)
	assert(await report.locator(".p-autocomplete-chip").count() === 21, "The >20 guard setup did not select 21 Lots")
	assert(await generate.isDisabled(), "Generate is enabled with more than 20 selected Lots")
	assert(await report.getByText("Select no more than 20 Lots.", { exact: true }).count() === 1, "The >20 Lot validation message is missing")
	assert(reportRequests.length === 1, "The >20 Lot guard made an unexpected report request")
	assert(errors.length === 0, `Browser errors: ${errors.join(" | ")}`)

	console.log("Lot Cut Quantity browser report: OK")
} finally {
	await browser.close()
}
