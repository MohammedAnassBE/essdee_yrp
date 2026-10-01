#!/usr/bin/env node

import { createRequire } from "node:module"
import { readFileSync } from "node:fs"

const require = createRequire("/home/anas/.claude/playwright/package.json")
const { chromium } = require("playwright")

const SITE = "http://erp-migration-test.site:8001"
const CREDENTIALS = "/home/anas/.frappe-debug-creds-mrp3"
const suite = process.argv[2] || "all"

export function assert(condition, message) {
	if (!condition) throw new Error(message)
}

export async function login(page) {
	const [username, password] = readFileSync(CREDENTIALS, "utf8").trim().split("\n")
	await page.goto(`${SITE}/login`, { waitUntil: "domcontentloaded" })
	await page.fill("#login_email", username.trim())
	await page.fill("#login_password", password.trim())
	await Promise.all([
		page.waitForNavigation({ waitUntil: "domcontentloaded", timeout: 20_000 }).catch(() => {}),
		page.click(".btn-login, button[type=submit]"),
	])
}

export async function findCuttingPlan(request, predicate = () => true) {
	const listResponse = await request.get(`${SITE}/api/resource/SD%20YRP%20Cutting%20Plan`, {
		params: {
			fields: JSON.stringify(["name"]),
			order_by: "modified desc",
			limit_page_length: 100,
		},
	})
	assert(listResponse.ok(), "Unable to load Cutting Plan fixtures")

	for (const { name } of (await listResponse.json()).data || []) {
		const response = await request.get(
			`${SITE}/api/method/essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan.sd_yrp_cutting_plan.get_web_view_data`,
			{ params: { cutting_plan: name } },
		)
		if (!response.ok()) continue
		const data = (await response.json()).message || {}
		if (await predicate(data, name)) return { name, data }
	}

	throw new Error("No Cutting Plan fixture matched the requested state")
}

export function assertNoBrowserErrors(errors) {
	assert(errors.length === 0, `Browser errors detected:\n${errors.join("\n")}`)
}

export async function visibleTextBelowMinimum(root, minPx = 11) {
	return root.locator("*").evaluateAll((elements, minimum) => elements.flatMap((element) => {
		if (!(element instanceof HTMLElement)) return []
		if (element.matches("script, style, svg, path, .pi, [aria-hidden='true']")) return []
		if (element.children.length) return []
		const text = (element.innerText || "").trim()
		if (!text) return []
		const style = getComputedStyle(element)
		if (style.display === "none" || style.visibility === "hidden" || Number(style.opacity) === 0) return []
		const rect = element.getBoundingClientRect()
		if (!rect.width || !rect.height) return []
		const fontSize = Number.parseFloat(style.fontSize)
		if (fontSize >= minimum) return []
		return [{
			tag: element.tagName.toLowerCase(),
			className: element.className,
			text: text.slice(0, 80),
			fontSize,
		}]
	}), minPx)
}

async function tokensSuite(page) {
	await page.goto(`${SITE}/web/`, { waitUntil: "domcontentloaded" })
	await page.locator(".app-shell").waitFor({ timeout: 20_000 })
	const contract = await page.locator(".app-shell").evaluate((element) => {
		const style = getComputedStyle(element)
		return {
			fontFamily: style.getPropertyValue("--erp-font-family").trim(),
			controlRadius: style.getPropertyValue("--erp-control-radius").trim(),
			panelRadius: style.getPropertyValue("--erp-panel-radius").trim(),
			accent: style.getPropertyValue("--erp-accent").trim(),
			minimumFontSize: style.getPropertyValue("--erp-font-size-min").trim(),
			canvas: getComputedStyle(document.body).backgroundColor,
		}
	})

	assert(contract.fontFamily.includes("Segoe UI Variable"), "font token is missing")
	assert(contract.controlRadius === "8px", "control radius is not locked")
	assert(contract.panelRadius === "12px", "panel radius is not locked")
	assert(contract.accent === "#0a7f5a", "emerald accent is not locked")
	assert(contract.minimumFontSize === "11px", "minimum text size is not locked")
	assert(contract.canvas === "rgb(244, 247, 245)", "stable canvas color is not applied")

	return contract
}

async function shellSuite(page) {
	await page.setViewportSize({ width: 1600, height: 1000 })
	await page.goto(`${SITE}/web/`, { waitUntil: "domcontentloaded" })
	await page.locator(".department-card-link").first().waitFor({ timeout: 20_000 })

	const destinations = page.locator(".department-card-link")
	assert(await destinations.count() === 10, "Administrator must show ten department destinations")
	assert(await page.getByText("Open workspace", { exact: true }).count() === 0, "Redundant workspace filler is visible")
	assert(await page.locator("body").evaluate((body) => getComputedStyle(body).backgroundColor) === "rgb(244, 247, 245)", "Shell canvas is not stable")

	await destinations.first().focus()
	const focusVisible = await destinations.first().evaluate((element) => {
		const style = getComputedStyle(element)
		return style.outlineStyle !== "none" || style.boxShadow !== "none"
	})
	assert(focusVisible, "Department destinations have no visible keyboard focus")
	assert((await visibleTextBelowMinimum(page)).length === 0, "Administrator contains visible text below 11px")

	await page.setViewportSize({ width: 760, height: 900 })
	const columnCount = await page.locator(".department-grid").evaluate((element) =>
		getComputedStyle(element).gridTemplateColumns.split(" ").filter(Boolean).length,
	)
	assert(columnCount === 1, "Administrator does not collapse to one column at 760px")

	return { destinationCount: await destinations.count(), columnCount, focusVisible }
}

async function cuttingEntrySuite(page, context) {
	await page.setViewportSize({ width: 1600, height: 1000 })
	await page.goto(`${SITE}/web/cutting`, { waitUntil: "domcontentloaded" })
	await page.locator(".workspace-grid").waitFor({ timeout: 20_000 })

	const entries = page.locator(".workspace-card")
	assert(await entries.count() === 2, "Cutting must show the two permitted destinations")
	assert(await page.getByText("Manufacturing workspace", { exact: true }).count() === 0, "Decorative Cutting eyebrow is visible")
	assert(await page.locator(".erp-page-header__description").count() === 0, "Cutting introductory paragraph is still visible")
	assert(await page.locator(".workspace-card__label").count() === 0, "Redundant Cutting card category labels are visible")
	assert((await visibleTextBelowMinimum(page)).length === 0, "Cutting entry contains visible text below 11px")

	await page.setViewportSize({ width: 760, height: 900 })
	const columnCount = await page.locator(".workspace-grid").evaluate((element) =>
		getComputedStyle(element).gridTemplateColumns.split(" ").filter(Boolean).length,
	)
	assert(columnCount === 1, "Cutting destinations do not collapse to one column at 760px")

	const restrictedPage = await context.newPage()
	try {
		await restrictedPage.route("**/api/method/essdee_yrp.cutting.reports.get_report_permissions", (route) =>
			route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: {} }) }),
		)
		await restrictedPage.goto(`${SITE}/web/cutting`, { waitUntil: "domcontentloaded" })
		await restrictedPage.locator(".workspace-empty").waitFor({ timeout: 20_000 })
		assert(await restrictedPage.locator(".workspace-card").count() === 0, "Restricted destinations remain visible")
		assert(await restrictedPage.locator(".workspace-empty").isVisible(), "No-permission state is not visible")
	} finally {
		await restrictedPage.close()
	}

	return { entryCount: await entries.count(), columnCount }
}

async function listSuite(page, context) {
	await page.setViewportSize({ width: 1600, height: 1000 })
	await page.goto(`${SITE}/web/cutting/plans`, { waitUntil: "domcontentloaded" })
	await page.getByRole("button", { name: "Filters", exact: true }).waitFor({ timeout: 20_000 })
	await page.locator(".premium-list-table .p-datatable-tbody > tr").first().waitFor({ timeout: 20_000 })

	assert(await page.locator(".list-page-head").count() === 1, "List command header is duplicated")
	assert(await page.getByText(/^\d+\s+records$/i).count() === 0, "Header record-count prose is visible")
	assert(await page.getByText("Quick filters", { exact: true }).count() === 0, "Quick-filter explanation is visible")

	const toolbarControls = page.locator(".list-search input, .list-toolbar__actions > .p-button")
	const controlHeights = await toolbarControls.evaluateAll((elements) =>
		elements.map((element) => Math.round(element.getBoundingClientRect().height)),
	)
	assert(controlHeights.length >= 5, "Expected list command controls are missing")
	assert(controlHeights.every((height) => height === 36), `List controls are not 36px: ${controlHeights.join(", ")}`)

	const headerPosition = await page.locator(".premium-list-table .p-datatable-thead > tr > th").first().evaluate((element) =>
		getComputedStyle(element).position,
	)
	assert(headerPosition === "sticky", "List table header is not sticky")

	const headers = await page.locator(".premium-list-table .p-datatable-thead > tr > th").allTextContents()
	const numericHeaderIndex = headers.findIndex((label) => label.trim() === "Colours")
	assert(numericHeaderIndex >= 0, "Numeric Colours column is missing")
	const numericAlignment = await page.locator(".premium-list-table .p-datatable-tbody > tr").first().locator("td").nth(numericHeaderIndex).evaluate((element) =>
		getComputedStyle(element).textAlign,
	)
	assert(numericAlignment === "right", "Numeric list columns are not right aligned")

	const longValueTreatment = await page.locator(".list-link-value").first().evaluate((element) => {
		const style = getComputedStyle(element)
		return { overflow: style.overflow, textOverflow: style.textOverflow, whiteSpace: style.whiteSpace }
	})
	assert(
		longValueTreatment.overflow === "hidden" &&
			longValueTreatment.textOverflow === "ellipsis" &&
			longValueTreatment.whiteSpace === "nowrap",
		`Long list values are not safely truncated: ${JSON.stringify(longValueTreatment)}`,
	)

	await page.getByRole("button", { name: "Filters", exact: true }).click()
	const filterDialog = page.getByRole("dialog", { name: "Filters" })
	await filterDialog.waitFor()
	const filterControl = filterDialog.locator(".p-select").first()
	await filterControl.focus()
	const filterFocusVisible = await filterControl.evaluate((element) => {
		const style = getComputedStyle(element)
		return style.outlineStyle !== "none" || style.boxShadow !== "none" || style.borderColor === "rgb(10, 127, 90)"
	})
	assert(filterFocusVisible, "Filter controls have no visible keyboard focus")
	await page.keyboard.press("Escape")

	await page.getByRole("button", { name: "Columns", exact: true }).click()
	const columnDialog = page.getByRole("dialog", { name: "Customize Columns" })
	await columnDialog.waitFor()
	assert(await columnDialog.locator(".column-drag-handle").count() > 0, "Column editor has no drag handles")
	await columnDialog.getByRole("button", { name: "Cancel", exact: true }).click()

	const undersizedText = await visibleTextBelowMinimum(page)
	assert(undersizedText.length === 0, `List contains text below 11px: ${JSON.stringify(undersizedText.slice(0, 8))}`)

	const search = page.locator(".list-search input")
	await search.fill("__no_matching_cutting_plan__")
	await search.press("Enter")
	await page.locator(".list-empty").waitFor({ timeout: 20_000 })
	assert(await page.getByText("No records found", { exact: true }).isVisible(), "Empty search state is not intentional")
	await page.getByRole("button", { name: "Clear Filters", exact: true }).click()
	await page.locator(".premium-list-table .p-datatable-tbody > tr").first().waitFor({ timeout: 20_000 })

	await page.setViewportSize({ width: 900, height: 760 })
	const tableContainment = await page.locator(".p-datatable-table-container").evaluate((element) => ({
		clientWidth: element.clientWidth,
		scrollWidth: element.scrollWidth,
		overflowX: getComputedStyle(element).overflowX,
	}))
	assert(tableContainment.scrollWidth >= tableContainment.clientWidth, "List table does not retain horizontal containment")
	assert(["auto", "scroll"].includes(tableContainment.overflowX), "List table cannot scroll horizontally")

	const loadingPage = await context.newPage()
	try {
		await loadingPage.route("**/api/resource/SD%20YRP%20Cutting%20Plan?*", async (route) => {
			await new Promise((resolve) => setTimeout(resolve, 1_200))
			await route.continue()
		})
		await loadingPage.goto(`${SITE}/web/cutting/plans`, { waitUntil: "domcontentloaded" })
		await loadingPage.locator(".list-loading-skeleton").first().waitFor({ timeout: 20_000 })
		assert(await loadingPage.locator(".list-loading-skeleton").count() >= 4, "List loading skeleton does not match table geometry")
	} finally {
		await loadingPage.close()
	}

	return { controlHeights, headerPosition, numericAlignment, longValueTreatment, tableContainment }
}

function groupItemCount(value) {
	const groups = Array.isArray(value) ? value : value?.items ? [value] : Object.values(value || {})
	return groups.reduce((total, group) => total + (group?.items?.length || 0), 0)
}

async function openPlan(page, predicate = () => true) {
	const fixture = await findCuttingPlan(page.request, predicate)
	await page.goto(`${SITE}/web/cutting/plans/${encodeURIComponent(fixture.name)}`, { waitUntil: "domcontentloaded" })
	await page.locator(".cutting-tabs").waitFor({ timeout: 20_000 })
	return fixture
}

async function planFrameSuite(page, context) {
	await page.setViewportSize({ width: 1600, height: 1000 })
	const fixture = await openPlan(page, (data) =>
		data.permissions?.can_read_marker &&
		data.permissions?.can_read_laysheet &&
		data.permissions?.can_read_movement &&
		data.permissions?.can_read_stock_transfers,
	)
	await page.locator(".cutting-plan-frame").waitFor({ timeout: 5_000 })

	const main = page.locator(".cutting-plan-frame > .common-form-view")
	const sidebar = page.locator(".cutting-plan-frame > .operations-rail")
	const [mainBox, sidebarBox] = await Promise.all([main.boundingBox(), sidebar.boundingBox()])
	assert(mainBox && sidebarBox, "Cutting Plan main or sidebar surface is missing")
	const widthRatio = mainBox.width / sidebarBox.width
	assert(widthRatio >= 3.7 && widthRatio <= 4.3, `Cutting Plan is not an 80/20 split: ${widthRatio}`)

	const recordId = page.locator(".form-toolbar__meta > small")
	const status = page.locator(".form-toolbar__meta .cutting-plan-status")
	const [recordBox, statusBox] = await Promise.all([recordId.boundingBox(), status.boundingBox()])
	assert(recordBox && statusBox && Math.abs(recordBox.y - statusBox.y) < 8, "Status is not beside the record ID")
	assert(await page.locator(".form-toolbar__actions .form-edit-button").count() === 1, "Edit is not a distinct header action")
	assert(await page.locator(".plan-command-bar .primary-command").count() === 1, "Primary plan command is not identifiable")

	const visibleTabs = page.locator(".cutting-tabs .p-tab:visible")
	assert(await visibleTabs.count() === 5, "Expected five permission-visible Cutting Plan tabs")
	const tabList = page.locator(".cutting-tabs .p-tablist")
	const panels = page.locator(".cutting-tabs .p-tabpanels")
	const tabTopBefore = (await tabList.boundingBox())?.y
	const scrollResult = await panels.evaluate((element) => {
		element.scrollTop = Math.min(420, Math.max(0, element.scrollHeight - element.clientHeight))
		return { scrollTop: element.scrollTop, clientHeight: element.clientHeight, scrollHeight: element.scrollHeight }
	})
	const tabTopAfter = (await tabList.boundingBox())?.y
	assert(tabTopBefore === tabTopAfter, "Tab list moves with active content")
	assert(scrollResult.scrollHeight >= scrollResult.clientHeight, "Tab content has no bounded scroll region")
	assert(await page.locator("html").evaluate((element) => element.scrollWidth <= element.clientWidth), "Cutting Plan has page-level horizontal overflow")

	const loadingPage = await context.newPage()
	try {
		await loadingPage.route("**get_web_view_data*", async (route) => {
			await new Promise((resolve) => setTimeout(resolve, 1_200))
			await route.continue()
		})
		await loadingPage.goto(`${SITE}/web/cutting/plans/${encodeURIComponent(fixture.name)}`, { waitUntil: "domcontentloaded" })
		await loadingPage.locator(".p-tabpanel[data-p-active='true'] .loading-state").waitFor({ timeout: 20_000 })
	} finally {
		await loadingPage.close()
	}

	const errorPage = await context.newPage()
	try {
		await errorPage.route("**get_web_view_data*", (route) => route.fulfill({
			status: 500,
			contentType: "application/json",
			body: JSON.stringify({ message: "Workspace unavailable" }),
		}))
		await errorPage.goto(`${SITE}/web/cutting/plans/${encodeURIComponent(fixture.name)}`, { waitUntil: "domcontentloaded" })
		await errorPage.locator(".p-tabpanel[data-p-active='true'] .p-message-error").waitFor({ timeout: 20_000 })
	} finally {
		await errorPage.close()
	}

	const readonlyPage = await context.newPage()
	try {
		await readonlyPage.route("**get_web_view_data*", (route) => route.fulfill({
			status: 200,
			contentType: "application/json",
			body: JSON.stringify({
				message: {
					...fixture.data,
					permissions: { ...fixture.data.permissions, can_write: false },
				},
			}),
		}))
		await readonlyPage.goto(`${SITE}/web/cutting/plans/${encodeURIComponent(fixture.name)}`, { waitUntil: "domcontentloaded" })
		await readonlyPage.locator(".cutting-tabs").waitFor({ timeout: 20_000 })
		assert(await readonlyPage.getByRole("button", { name: "Edit", exact: true }).count() === 0, "Read-only plan still shows Edit")
		const actionGap = await readonlyPage.locator(".form-toolbar__actions").evaluate((element) => element.getBoundingClientRect().height)
		assert(actionGap <= 40, "Read-only header leaves an empty action gap")
	} finally {
		await readonlyPage.close()
	}

	await page.setViewportSize({ width: 1050, height: 900 })
	const [collapsedMain, collapsedSidebar] = await Promise.all([main.boundingBox(), sidebar.boundingBox()])
	assert(
		collapsedMain && collapsedSidebar && collapsedSidebar.y >= collapsedMain.y + collapsedMain.height - 1,
		"Sidebar does not move below the main surface at 1050px",
	)

	return { plan: fixture.name, widthRatio, tabCount: await visibleTabs.count(), scrollResult }
}

async function planPrimaryTabsSuite(page) {
	await page.setViewportSize({ width: 1600, height: 1000 })
	const fixture = await openPlan(page, (data) => groupItemCount(data.planned_detail?.item_detail) > 0)

	const detailColumns = page.locator(".detail-field-column")
	assert(await detailColumns.count() === 2, "Details does not use two Desk-aligned columns")
	const detailWidths = await detailColumns.evaluateAll((elements) => elements.map((element) => element.getBoundingClientRect().width))
	assert(Math.abs(detailWidths[0] - detailWidths[1]) <= 2, `Details columns are unbalanced: ${detailWidths.join(", ")}`)
	const detailLabels = await detailColumns.evaluateAll((elements) => elements.map((element) =>
		Array.from(element.querySelectorAll(".form-field__label")).map((label) => label.textContent.replace("*", "").trim()),
	))
	assert(
		JSON.stringify(detailLabels[0].slice(0, 4)) === JSON.stringify(["Is Manual Entry", "Lot", "Maximum No of Plys", "Lay No"]),
		`Left Details column is not in Desk order: ${JSON.stringify(detailLabels[0])}`,
	)
	assert(detailLabels[1][0] === "Item", `Right Details column must start with Item: ${JSON.stringify(detailLabels[1])}`)

	await page.getByRole("tab", { name: "Summary", exact: true }).click()
	const summaryHeadings = await page.locator(".p-tabpanel[data-p-active='true'] .section-heading h3").allTextContents()
	for (const heading of ["Completed Cut Quantity", "Excess Cut Quantity", "Recut Summary", "Print Panel Summary"]) {
		assert(summaryHeadings.some((text) => text.includes(heading)), `Summary is missing ${heading}`)
	}

	await page.getByRole("tab", { name: "Planned Detail", exact: true }).click()
	await page.locator(".planned-row").first().waitFor({ timeout: 10_000 })
	assert(await page.locator(".planned-row").count() > 0, "Planned rows are not visually identified")
	assert(await page.locator(".completed-row").count() > 0, "Completed rows are not visually identified")
	const totalNumberStyle = await page.locator(".total-row .number-cell").first().evaluate((element) => getComputedStyle(element).fontVariantNumeric)
	assert(totalNumberStyle.includes("tabular-nums"), "Totals do not use tabular numbers")
	const longIdContainment = await page.locator(".data-table td").first().evaluate((element) => ({
		overflowWrap: getComputedStyle(element).overflowWrap,
		pageContained: document.documentElement.scrollWidth <= document.documentElement.clientWidth,
	}))
	assert(longIdContainment.overflowWrap === "anywhere" && longIdContainment.pageContained, "Long tabular IDs are not contained")
	const undersizedText = await visibleTextBelowMinimum(page.locator(".cutting-plan-main"))
	assert(undersizedText.length === 0, `Primary tabs contain text below 11px: ${JSON.stringify(undersizedText.slice(0, 8))}`)

	return { plan: fixture.name, detailWidths, summaryHeadings, totalNumberStyle, longIdContainment }
}

const suites = {
	tokens: tokensSuite,
	shell: shellSuite,
	"cutting-entry": cuttingEntrySuite,
	list: listSuite,
	"plan-frame": planFrameSuite,
	"plan-primary-tabs": planPrimaryTabsSuite,
}

const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({ viewport: { width: 1600, height: 1000 } })
const page = await context.newPage()
const errors = []

page.on("pageerror", (error) => errors.push(`page: ${error.message}`))
page.on("console", (message) => {
	if (message.type() === "error") errors.push(`console: ${message.text()}`)
})

try {
	await login(page)
	const selectedSuites = suite === "all" ? Object.keys(suites) : [suite]
	const results = {}
	for (const suiteName of selectedSuites) {
		assert(suites[suiteName], `Unknown suite: ${suiteName}`)
		results[suiteName] = await suites[suiteName](page, context)
	}
	assertNoBrowserErrors(errors)
	console.log(JSON.stringify({ passed: true, suites: results }, null, 2))
} finally {
	await browser.close()
}
