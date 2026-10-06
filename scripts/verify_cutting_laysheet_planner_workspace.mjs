#!/usr/bin/env node

import { createRequire } from "node:module"
import { readFileSync } from "node:fs"

const require = createRequire("/home/anas/.claude/playwright/package.json")
const { chromium } = require("playwright")
const SITE = "http://erp-migration-test.site:8001"
const [username, password] = readFileSync("/home/anas/.frappe-debug-creds-mrp3", "utf8").trim().split("\n")
const API = "**/api/method/essdee_yrp.cutting.planner_workspace.*"

function assert(condition, message) { if (!condition) throw new Error(message) }

const plannerListSource = readFileSync("frontend/src/departments/CuttingLaySheetPlanners.vue", "utf8")
assert(plannerListSource.includes('class="list-primary-action"'), "LaySheet Planner create action is not styled as the list primary action")
assert(!readFileSync("frontend/src/departments/CuttingLaySheetPlanner.vue", "utf8").includes("pi pi-sparkles"), "Planner uses the decorative sparkle icon for a workflow action")

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

const successful = [{
	strategy: "direct_integer_search", strategy_description: "Deterministic integer search", status: "success",
	summary: { total_lays: 2, unique_markers: 2, avg_pieces_per_ply: 3.5, total_order: 75, total_cut: 76, overcut: 1, overcut_pct: 1.3, undercut: 0, undercut_pct: 0 },
	per_size: { S: { order: 25, cut: 26, diff: 1, pct: 4 }, M: { order: 50, cut: 50, diff: 0, pct: 0 } },
	lays: [
		{ lay_no: 1, plies: 25, ratio: { S: 1, M: 1 }, pieces_per_ply: 2, total_pieces: 50, cut_per_size: { S: 25, M: 25 } },
		{ lay_no: 2, plies: 25, ratio: { S: 0, M: 1 }, pieces_per_ply: 1, total_pieces: 25, cut_per_size: { S: 0, M: 25 } },
	],
}, {
	strategy: "minimum_deviation", strategy_description: "Minimum total size deviation", status: "success",
	summary: { total_lays: 3, unique_markers: 2, avg_pieces_per_ply: 3, total_order: 75, total_cut: 75, overcut: 0, overcut_pct: 0, undercut: 0, undercut_pct: 0 },
	per_size: { S: { order: 25, cut: 25, diff: 0, pct: 0 }, M: { order: 50, cut: 50, diff: 0, pct: 0 } },
	lays: [{ lay_no: 1, plies: 25, ratio: { S: 1, M: 2 }, pieces_per_ply: 3, total_pieces: 75, cut_per_size: { S: 25, M: 50 } }],
}]
const failed = [{ strategy: "cp_sat", status: "timeout", error: "Timed out" }]
for (let index = 1; index <= 5; index += 1) {
	successful.push({
		...structuredClone(successful[1]),
		strategy: `comparison_${index}`,
		strategy_description: `Comparison strategy ${index}`,
	})
}

function payload(status = "Not Started", name = "CLP-2026-00001") {
	const completed = status === "Completed"
	const active = ["Queued", "Running"].includes(status)
	return {
		record: {
			name, modified: "2026-10-03 12:00:00", docstatus: 0, lot: "LOT-001", item: "STYLE-001", description: "October cutting plan",
			max_plies: 100, max_pieces: 12, tolerance_pct: 3, max_lays: 8, tubular: 0,
			optimization_status: status, optimization_started_on: active ? "2026-10-03 12:01:00" : null, optimization_completed_on: completed ? "2026-10-03 12:01:04" : null,
			optimization_error: status === "Failed" ? "No feasible lay plan was found." : "", selected_strategy: completed ? "direct_integer_search" : null,
			summary: completed ? successful[0].summary : { total_lays: 0, total_order: 0, total_cut: 0, overcut: 0, overcut_pct: 0, undercut: 0, undercut_pct: 0 },
			order_details: [{ _row_key: "ORDER-1", name: "ORDER-1", size: "S", qty: 25 }, { _row_key: "ORDER-2", name: "ORDER-2", size: "M", qty: 50 }],
		},
		results: { successful: completed ? successful : [], failed: completed ? failed : [], optimizer_version: "4.1.0" },
		permissions: { can_read: true, can_create: true, can_write: true, can_print: true },
		actions: { can_edit_inputs: !active, can_optimize: !active && Boolean(name), can_retry: status === "Failed", can_select_result: completed, should_poll: active },
	}
}

const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
const page = await context.newPage()
const errors = []
let state = "Not Started"
let polls = 0
let savedValues = null
let selected = ""
page.on("pageerror", (error) => errors.push(`page: ${error.message}`))
page.on("console", (message) => { if (message.type() === "error") errors.push(`console: ${message.text()}`) })

await page.goto(`${SITE}/login`, { waitUntil: "domcontentloaded" })
await page.fill("#login_email", username.trim())
await page.fill("#login_password", password.trim())
await Promise.all([page.waitForNavigation({ waitUntil: "domcontentloaded", timeout: 20_000 }).catch(() => {}), page.click(".btn-login, button[type=submit]")])
await page.route("**/api/method/essdee_yrp.api.link_search.link_search*", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: [{ name: "LOT-001", label: "LOT-001" }, { name: "STYLE-001", label: "STYLE-001" }] }) }))
await page.route(API, async (route) => {
	const url = route.request().url()
	const body = JSON.parse(route.request().postData() || "{}")
	if (url.includes("get_editor")) {
		const message = body.name ? payload(state) : { ...payload("Not Started", null), record: { ...payload("Not Started", null).record, name: null, modified: null, lot: "", item: "", description: "", max_plies: null, max_pieces: null, order_details: [] }, actions: { can_edit_inputs: true, can_optimize: false, can_retry: false, can_select_result: false, should_poll: false } }
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message }) })
	}
	if (url.includes("save")) { savedValues = body.values; state = "Not Started"; return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: payload(state) }) }) }
	if (url.includes("start_optimization")) { state = "Queued"; polls = 0; return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: { status: "Queued", actions: { should_poll: true, can_optimize: false } } }) }) }
	if (url.includes("get_status")) { polls += 1; state = polls === 1 ? "Running" : "Completed"; return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: { status: state, terminal: state === "Completed", modified: "2026-10-03 12:00:00", error_message: "", actions: { should_poll: state === "Running", can_optimize: state === "Completed" } } }) }) }
	if (url.includes("select_result")) { selected = body.strategy; const next = payload("Completed"); next.record.selected_strategy = selected; return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: next }) }) }
})

await page.goto(`${SITE}/web/cutting/lay-sheet-planner/new`, { waitUntil: "domcontentloaded" })
await page.getByRole("heading", { name: "New LaySheet Plan", exact: true }).waitFor({ timeout: 20_000 })
const compactInputs = await page.evaluate(() => {
	const grid = document.querySelector(".planner-inputs__grid")
	const description = grid?.querySelector("textarea")
	const matrix = document.querySelector(".planner-order-matrix")
	const metricFields = [...(grid?.querySelectorAll(".planner-field") || [])].slice(-4)
	const tubular = grid?.querySelector(".planner-check")
	if (!grid || !description || !matrix || metricFields.some((field) => !field) || !tubular) return null
	const gridBox = grid.getBoundingClientRect()
	const matrixBox = matrix.getBoundingClientRect()
	const metricBoxes = metricFields.map((field) => field.getBoundingClientRect())
	const tubularBox = tubular.getBoundingClientRect()
	return {
		gridHeight: gridBox.height,
		descriptionHeight: description.getBoundingClientRect().height,
		maxMetricWidth: Math.max(...metricBoxes.map((box) => box.width)),
		constraintBottomSpread: Math.max(...metricBoxes.map((box) => box.bottom), tubularBox.bottom) - Math.min(...metricBoxes.map((box) => box.bottom), tubularBox.bottom),
		matrixGap: matrixBox.top - gridBox.bottom,
	}
})
assert(compactInputs, "Planner input layout could not be measured")
assert(compactInputs.gridHeight <= 145, `Planner inputs still consume excessive vertical space: ${JSON.stringify(compactInputs)}`)
assert(compactInputs.descriptionHeight <= 44, `Planner description is still taller than a standard control: ${JSON.stringify(compactInputs)}`)
assert(compactInputs.maxMetricWidth <= 220, `Planner numeric fields still stretch across the page: ${JSON.stringify(compactInputs)}`)
assert(compactInputs.constraintBottomSpread <= 2, `Planner constraints do not share one compact row: ${JSON.stringify(compactInputs)}`)
assert(compactInputs.matrixGap <= 14, `Order Details starts too far below the planner inputs: ${JSON.stringify(compactInputs)}`)
await page.getByLabel("Description *").fill("October cutting plan")
for (const [label, value] of [["Maximum Plies *", "100"], ["Maximum Pieces Per Marker *", "12"]]) await page.getByLabel(label).fill(value)
await page.getByRole("button", { name: "Add Size", exact: true }).click()
await page.getByRole("button", { name: "Add Size", exact: true }).click()
const orderRows = page.locator(".planner-order-row")
await orderRows.nth(0).locator("input").nth(0).fill("S"); await orderRows.nth(0).locator("input").nth(1).fill("25")
await orderRows.nth(1).locator("input").nth(0).fill("M"); await orderRows.nth(1).locator("input").nth(1).fill("50")
const compactOrderTable = await orderRows.nth(0).evaluate((row) => {
	const table = row.closest("table")
	const matrix = row.closest(".planner-order-matrix")
	const inputs = row.querySelectorAll("input")
	if (!table || !matrix || inputs.length !== 2) return null
	const rowBox = row.getBoundingClientRect()
	const tableBox = table.getBoundingClientRect()
	const sizeBox = inputs[0].getBoundingClientRect()
	const quantityBox = inputs[1].getBoundingClientRect()
	return {
		matrixWidth: matrix.getBoundingClientRect().width,
		tableWidth: tableBox.width,
		rowHeight: rowBox.height,
		sizeWidth: sizeBox.width,
		quantityWidth: quantityBox.width,
		maxInputHeight: Math.max(sizeBox.height, quantityBox.height),
	}
})
assert(compactOrderTable, "Planner Order Details layout could not be measured")
assert(compactOrderTable.matrixWidth <= 680, `Order Details still leaves a large empty editing surface: ${JSON.stringify(compactOrderTable)}`)
assert(compactOrderTable.tableWidth <= 680, `Order Details still stretches across the page: ${JSON.stringify(compactOrderTable)}`)
assert(compactOrderTable.rowHeight <= 46, `Order Details rows still contain excessive vertical space: ${JSON.stringify(compactOrderTable)}`)
assert(compactOrderTable.sizeWidth <= 250, `Size inputs are still excessively wide: ${JSON.stringify(compactOrderTable)}`)
assert(compactOrderTable.quantityWidth <= 220, `Quantity inputs are still excessively wide: ${JSON.stringify(compactOrderTable)}`)
assert(compactOrderTable.maxInputHeight <= 34, `Order Details inputs are still taller than compact controls: ${JSON.stringify(compactOrderTable)}`)
await page.getByRole("button", { name: "Save Draft", exact: true }).click()
await page.waitForURL("**/web/cutting/lay-sheet-planner/CLP-2026-00001")
await page.getByRole("heading", { name: "LaySheet Planner", exact: true }).waitFor({ timeout: 20_000 })
assert(savedValues?.order_details?.length === 2, "Planner did not save explicit size rows")
assert(await page.locator(".planner-header-fact--lot").getByText("LOT-001", { exact: true }).count() === 1, "Planner Lot is not promoted to the header")
assert(await page.locator(".planner-header-fact--item").getByText("STYLE-001", { exact: true }).count() === 1, "Planner Item is not promoted to the header")
assert(await page.locator(".planner-status").count() === 0, "Planner still renders the redundant optimization status panel")
const headerSaveInputs = page.locator(".planner-record-actions").getByRole("button", { name: "Save Inputs", exact: true })
assert(await headerSaveInputs.count() === 1, "Save Inputs is not available in the planner header")
assert(await page.locator(".planner-inputs__footer").count() === 0, "Save Inputs is still rendered at the bottom of the Inputs tab")
assert(await headerSaveInputs.isEnabled(), "Valid planner inputs do not enable the header Save Inputs action")
await page.getByLabel("Description *").fill("Saved from the planner header")
const headerSaveResponse = page.waitForResponse((response) => response.url().includes("cutting.planner_workspace.save"))
await headerSaveInputs.click()
await headerSaveResponse
assert(savedValues?.description === "Saved from the planner header", "The header Save Inputs action did not submit the current form")

for (const tab of ["Inputs", "Plan"]) assert(await page.getByRole("tab", { name: tab, exact: true }).count() === 1, `${tab} tab is missing`)
assert(await page.getByRole("tab", { name: "Strategies", exact: true }).count() === 0, "Strategies still requires a separate tab")
assert(await page.getByRole("tab", { name: "Lay Plan", exact: true }).count() === 0, "Lay Plan still requires a separate tab")
await page.getByRole("button", { name: "Optimize", exact: true }).click()
const statusBadge = page.locator(".planner-record-meta .p-tag")
await statusBadge.getByText("Queued", { exact: true }).waitFor()
await statusBadge.getByText("Running", { exact: true }).waitFor({ timeout: 5_000 }).catch(() => {})
await statusBadge.getByText("Completed", { exact: true }).waitFor({ timeout: 8_000 })
assert(await page.getByRole("tab", { name: "Plan", exact: true }).getAttribute("aria-selected") === "true", "Completed optimization did not open the unified Plan workspace")
assert(await page.locator(".planner-strategy-card").count() === 8, "Strategy outcomes are missing")
await page.getByText("Detailed Lay Plan", { exact: true }).waitFor()
assert(await page.locator(".planner-lay-plan__header h2").textContent() === "Direct Integer Search", "The selected strategy and its lay plan are not visible together")
await page.setViewportSize({ width: 1280, height: 700 })
const planTabPanels = page.locator(".planner-tabs .p-tabpanels")
const strategyPane = page.locator(".planner-plan-workspace__strategies")
const resultPane = page.locator(".planner-plan-workspace__result")
const initialScrollLayout = await page.evaluate(() => {
	const metrics = (selector) => {
		const element = document.querySelector(selector)
		return { clientHeight: element.clientHeight, scrollHeight: element.scrollHeight, scrollTop: element.scrollTop, overflowY: getComputedStyle(element).overflowY }
	}
	return {
		tabs: metrics(".planner-tabs .p-tabpanels"),
		strategies: metrics(".planner-plan-workspace__strategies"),
		result: metrics(".planner-plan-workspace__result"),
	}
})
assert(initialScrollLayout.tabs.overflowY === "hidden", `Plan tab body still owns the page scrollbar: ${JSON.stringify(initialScrollLayout)}`)
assert(["auto", "scroll"].includes(initialScrollLayout.strategies.overflowY) && initialScrollLayout.strategies.scrollHeight > initialScrollLayout.strategies.clientHeight, `Strategies is not independently scrollable: ${JSON.stringify(initialScrollLayout)}`)
assert(["auto", "scroll"].includes(initialScrollLayout.result.overflowY) && initialScrollLayout.result.scrollHeight > initialScrollLayout.result.clientHeight, `Selected Strategy is not independently scrollable: ${JSON.stringify(initialScrollLayout)}`)
await strategyPane.evaluate((element) => { element.scrollTop = 120 })
const strategyScrollTop = await strategyPane.evaluate((element) => element.scrollTop)
assert(strategyScrollTop > 0, "Strategies scrollbar did not move")
assert(await resultPane.evaluate((element) => element.scrollTop) === 0, "Scrolling Strategies moved Selected Strategy")
await resultPane.evaluate((element) => { element.scrollTop = 140 })
assert(await resultPane.evaluate((element) => element.scrollTop) > 0, "Selected Strategy scrollbar did not move")
assert(await strategyPane.evaluate((element) => element.scrollTop) === strategyScrollTop, "Scrolling Selected Strategy moved Strategies")
assert(await planTabPanels.evaluate((element) => element.scrollTop) === 0, "Independent pane scrolling moved the complete Plan tab")
const strategyPanelBox = await page.locator(".planner-plan-workspace__strategies").boundingBox()
const resultPanelBox = await page.locator(".planner-plan-workspace__result").boundingBox()
assert(strategyPanelBox && resultPanelBox && strategyPanelBox.x < resultPanelBox.x, "Planner does not use the Desk-style strategy-left/result-right layout")
await page.getByText("Minimum Deviation", { exact: true }).click()
assert(selected === "minimum_deviation", "Strategy selection was not persisted")
await page.locator(".planner-lay-plan__header h2").getByText("Minimum Deviation", { exact: true }).waitFor()
assert(await page.getByText("Size Deviation", { exact: true }).count() === 1, "Deviation analysis is missing")
const matrixOverflow = await page.locator(".planner-lay-table-wrap").evaluate((element) => getComputedStyle(element).overflowX)
assert(["auto", "scroll"].includes(matrixOverflow), `Lay matrix is not horizontally contained: ${matrixOverflow}`)

state = "Failed"
await page.reload({ waitUntil: "domcontentloaded" })
await page.getByText("No feasible lay plan was found.", { exact: true }).waitFor({ timeout: 20_000 })
assert(await page.getByRole("button", { name: "Retry Optimization", exact: true }).count() === 1, "Retry action is missing after failure")
assert(!page.url().includes("/app/"), "Planner navigated to Desk")

state = "Completed"
await page.reload({ waitUntil: "domcontentloaded" })
await page.getByText("Detailed Lay Plan", { exact: true }).waitFor({ timeout: 20_000 })
assert(await page.getByRole("tab", { name: "Plan", exact: true }).getAttribute("aria-selected") === "true", "A completed planner did not reopen on the unified Plan workspace")
const responsiveLayouts = {}
for (const viewport of [{ width: 1600, height: 1000 }, { width: 1280, height: 800 }, { width: 900, height: 760 }, { width: 390, height: 844 }]) {
	await page.setViewportSize(viewport)
	const bodyWidth = await page.locator("body").evaluate((element) => ({ scrollWidth: element.scrollWidth, clientWidth: element.clientWidth }))
	assert(bodyWidth.scrollWidth === bodyWidth.clientWidth, `Planner workspace overflows at ${viewport.width}px: ${JSON.stringify(bodyWidth)}`)
	const undersized = await visibleTextBelowMinimum(page)
	assert(undersized.length === 0, `Planner workspace has text below 11px at ${viewport.width}px: ${JSON.stringify(undersized.slice(0, 8))}`)
	const summaryColumns = await page.locator(".planner-summary-grid").evaluate((element) => getComputedStyle(element).gridTemplateColumns.split(" ").filter(Boolean).length)
	responsiveLayouts[viewport.width] = summaryColumns
}
assert(errors.length === 0, `Browser errors: ${JSON.stringify(errors)}`)

console.log(JSON.stringify({ passed: true, planner: "CLP-2026-00001", polls, selected, matrixOverflow, responsiveLayouts }, null, 2))
await browser.close()
