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

async function findEditableLaySheet(request, fixture) {
	const method = `${SITE}/api/method/essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet.sd_yrp_cutting_laysheet.get_web_laysheet`
	for (const summary of fixture.data.laysheets || []) {
		const response = await request.get(method, {
			params: { cutting_plan: fixture.name, cutting_laysheet: summary.name },
		})
		if (!response.ok()) continue
		const sheet = (await response.json()).message || {}
		if (sheet.permissions?.can_edit_details && sheet.cloth_details?.length) return sheet
	}
	throw new Error("No editable Lay Sheet with cloth details was found")
}

async function sidebarSuite(page, context) {
	await page.setViewportSize({ width: 1600, height: 700 })
	const fixture = await openPlan(page, (data) =>
		data.markers?.length && data.laysheets?.length && data.permissions?.can_create_marker && data.permissions?.can_create_laysheet,
	)
	await page.locator(".marker-card").first().waitFor({ timeout: 20_000 })

	const sections = page.locator(".operations-rail > .rail-section")
	const sectionHeights = await sections.evaluateAll((elements) => elements.map((element) => element.getBoundingClientRect().height))
	assert(sectionHeights.length === 2 && Math.abs(sectionHeights[0] - sectionHeights[1]) <= 2, `Rail sections are not 50/50: ${sectionHeights}`)
	for (const sectionName of ["marker-section", "laysheet-section"]) {
		const section = page.locator(`.${sectionName}`)
		assert(await section.getByRole("button", { name: "Create New", exact: true }).count() === 1, `${sectionName} is missing Create New`)
		assert(await section.locator(".rail-filter-button").count() === 1, `${sectionName} is missing its filter action`)
	}

	const marker = page.locator(".marker-card").first()
	for (const selector of [".rail-card__top strong", ".rail-card__top small", ".marker-metrics", ".panel-summary", ".marker-status"]) {
		assert(await marker.locator(selector).count() === 1, `Marker card is missing ${selector}`)
	}
	const laySheet = page.locator(".laysheet-card").first()
	for (const selector of [".lay-number", ".rail-card__top strong", ".panel-summary", ".lay-meta", ".lay-status", ".print-state"]) {
		assert(await laySheet.locator(selector).count() === 1, `Lay Sheet card is missing ${selector}`)
	}
	const displayedDates = await page.locator(".laysheet-card .lay-meta b").allTextContents()
	const concreteDates = displayedDates.filter((value) => /\d/.test(value))
	assert(concreteDates.every((value) => /^\d{2}-\d{2}-\d{4}(?: \d{2}:\d{2})?$/.test(value)), `Rail dates are not DD-MM-YYYY: ${concreteDates}`)
	const longNameContainment = await marker.locator(".rail-card__top strong").evaluate((element) => ({
		overflow: getComputedStyle(element).overflow,
		textOverflow: getComputedStyle(element).textOverflow,
		cardContained: element.closest(".rail-card").getBoundingClientRect().right <= element.closest(".rail-section").getBoundingClientRect().right + 1,
	}))
	assert(longNameContainment.overflow === "hidden" && longNameContainment.textOverflow === "ellipsis" && longNameContainment.cardContained, "Long rail names are not contained")
	assert(await page.locator(".rail-heading").evaluateAll((elements) => elements.every((element) => element.getBoundingClientRect().height > 0)), "Rail headers disappear at 700px height")
	const railUndersizedText = await visibleTextBelowMinimum(page.locator(".operations-rail"))
	assert(railUndersizedText.length === 0, `Rail contains text below 11px: ${JSON.stringify(railUndersizedText.slice(0, 8))}`)

	await page.locator(".marker-section .rail-filter-button").click()
	const filterDialog = page.getByRole("dialog", { name: "Filters" })
	await filterDialog.waitFor()
	const filterRow = filterDialog.locator(".filter-row").first()
	await filterRow.locator(".p-select").first().click()
	await page.getByRole("option", { name: "Marker Name", exact: true }).click()
	await filterRow.locator(".filter-row__value input").fill("__no_matching_marker__")
	await filterDialog.getByRole("button", { name: "Apply Filters", exact: true }).click()
	assert(await page.locator(".marker-section .rail-empty").isVisible(), "Filtered-empty marker state is missing")
	assert(await page.locator(".marker-section .rail-filter-button--active").count() === 1, "Active marker filters are not visible")

	const restrictedPage = await context.newPage()
	try {
		await restrictedPage.route("**get_web_view_data*", (route) => route.fulfill({
			status: 200,
			contentType: "application/json",
			body: JSON.stringify({ message: {
				...fixture.data,
				permissions: {
					...fixture.data.permissions,
					can_read_marker: false,
					can_create_marker: false,
					can_create_laysheet: false,
				},
			} }),
		}))
		await restrictedPage.goto(`${SITE}/web/cutting/plans/${encodeURIComponent(fixture.name)}`, { waitUntil: "domcontentloaded" })
		await restrictedPage.locator(".laysheet-section").waitFor({ timeout: 20_000 })
		assert(await restrictedPage.locator(".marker-section").count() === 0, "Unreadable Markers section remains visible")
		assert(await restrictedPage.locator(".laysheet-section .rail-filter-button").count() === 1, "Readable Lay Sheet filter is missing")
		assert(await restrictedPage.locator(".laysheet-section").getByRole("button", { name: "Create New", exact: true }).count() === 0, "Disallowed Lay Sheet create action remains visible")
	} finally {
		await restrictedPage.close()
	}

	const emptyPage = await context.newPage()
	try {
		await emptyPage.route("**get_web_view_data*", (route) => route.fulfill({
			status: 200,
			contentType: "application/json",
			body: JSON.stringify({ message: { ...fixture.data, markers: [], laysheets: [] } }),
		}))
		await emptyPage.goto(`${SITE}/web/cutting/plans/${encodeURIComponent(fixture.name)}`, { waitUntil: "domcontentloaded" })
		await emptyPage.locator(".rail-empty").first().waitFor({ timeout: 20_000 })
		assert(await emptyPage.locator(".rail-empty").count() === 2, "Rail does not show both deliberate empty states")
	} finally {
		await emptyPage.close()
	}

	return { plan: fixture.name, sectionHeights, concreteDates, longNameContainment }
}

async function entityDialogsSuite(page) {
	await page.setViewportSize({ width: 1600, height: 760 })
	const fixture = await openPlan(page, (data) => data.markers?.length && data.laysheets?.length)
	await page.locator(".marker-card").first().waitFor({ timeout: 20_000 })
	const initialUrl = page.url()

	await page.locator(".marker-section").getByRole("button", { name: "Create New", exact: true }).click()
	const markerDialog = page.getByRole("dialog", { name: "Create New Marker" })
	await markerDialog.waitFor()
	assert(page.url() === initialUrl, "Opening a marker dialog navigates away from the Cutting Plan")
	await page.locator(".p-dialog-mask").click({ position: { x: 4, y: 4 } })
	await markerDialog.waitFor({ state: "hidden" })

	await page.locator(".laysheet-section").getByRole("button", { name: "Create New", exact: true }).click()
	const createDialog = page.getByRole("dialog", { name: "Create Lay Sheet" })
	await createDialog.waitFor()
	assert(await createDialog.getByText(/Start Date|End Date|Started Date|Ended Date/i).count() === 0, "Lay Sheet creation exposes system date-time fields")
	await createDialog.locator(".p-dialog-footer").getByRole("button", { name: "Close", exact: true }).click()

	await page.locator(".marker-card").first().click()
	const existingMarkerDialog = page.locator(".marker-dialog")
	await existingMarkerDialog.waitFor()
	const dialogScrollContract = await existingMarkerDialog.evaluate((dialog) => {
		const content = dialog.querySelector(".p-dialog-content")
		const footer = dialog.querySelector(".p-dialog-footer")
		const dialogBox = dialog.getBoundingClientRect()
		const footerBox = footer?.getBoundingClientRect()
		return {
			contentOverflow: content ? getComputedStyle(content).overflowY : "missing",
			contentScrollable: content ? content.scrollHeight >= content.clientHeight : false,
			footerVisible: Boolean(footerBox && footerBox.bottom <= dialogBox.bottom + 1),
		}
	})
	assert(["auto", "scroll"].includes(dialogScrollContract.contentOverflow) && dialogScrollContract.contentScrollable && dialogScrollContract.footerVisible, `Marker dialog scroll contract failed: ${JSON.stringify(dialogScrollContract)}`)
	const markerUndersizedText = await visibleTextBelowMinimum(existingMarkerDialog)
	assert(markerUndersizedText.length === 0, `Marker dialog contains text below 11px: ${JSON.stringify(markerUndersizedText.slice(0, 8))}`)
	await existingMarkerDialog.locator(".p-dialog-footer").getByRole("button", { name: "Close", exact: true }).click()

	const sheet = await findEditableLaySheet(page.request, fixture)
	await page.locator(".laysheet-card").filter({ hasText: sheet.name }).click()
	const laySheetDialog = page.getByRole("dialog", { name: new RegExp(sheet.name) })
	await laySheetDialog.waitFor()
	await laySheetDialog.getByRole("tab", { name: "Cloth Details", exact: true }).click()
	assert(await laySheetDialog.getByRole("button", { name: "Add Cloth", exact: true }).count() === 1, "Permitted Add Cloth action is missing")
	assert(await laySheetDialog.getByRole("button", { name: "Add Accessory", exact: true }).count() === 1, "Permitted Add Accessory action is missing")
	const laySheetUndersizedText = await visibleTextBelowMinimum(laySheetDialog)
	assert(laySheetUndersizedText.length === 0, `Lay Sheet dialog contains text below 11px: ${JSON.stringify(laySheetUndersizedText.slice(0, 8))}`)

	const rowsBefore = await laySheetDialog.locator(".editable-data-block").first().locator("tbody tr").count()
	await page.route("**save_web_laysheet_details*", async (route) => {
		const values = route.request().postDataJSON()
		await route.fulfill({
			status: 200,
			contentType: "application/json",
			body: JSON.stringify({ message: {
				...sheet,
				cloth_details: values.cloth_details || [],
				accessory_details: values.accessory_details || [],
			} }),
		})
	})
	page.once("dialog", (dialog) => dialog.accept())
	await laySheetDialog.getByRole("button", { name: "Delete cloth" }).first().click()
	await laySheetDialog.getByText("Cloth detail deleted.", { exact: true }).waitFor({ timeout: 10_000 })
	const rowsAfter = await laySheetDialog.locator(".editable-data-block").first().locator("tbody tr").count()
	assert(rowsAfter === rowsBefore - 1, `Delete success did not remove the rendered row: ${rowsBefore} -> ${rowsAfter}`)

	return { plan: fixture.name, sheet: sheet.name, dialogScrollContract, rowsBefore, rowsAfter }
}

async function getMethodFixture(request, method, args) {
	const response = await request.get(`${SITE}/api/method/${method}`, { params: args })
	assert(response.ok(), `Unable to load fixture from ${method}`)
	return (await response.json()).message || {}
}

async function cpmSuite(page, context) {
	await page.setViewportSize({ width: 1600, height: 900 })
	const fixture = await findCuttingPlan(page.request, (_, name) => name === "CP-2609-00007")
	const cpmMethod = "essdee_yrp.cutting.web_workspace."
	const workspace = await getMethodFixture(page.request, `${cpmMethod}get_workspace`, { cutting_plan: fixture.name })
	const generated = await getMethodFixture(page.request, `${cpmMethod}generate_movement_bundles`, { cutting_plan: fixture.name })
	generated.collapsed_details = [{
		size: "8-9", colour: "White", panel: "Front", lay_no: 1, bundle_no: 1, quantity: 2, moved: false, move_qty: 0,
	}]
	generated.accessory_data = [{
		cloth_name: "Accessory Fabric", cloth_type: "Folding", colour: "White", shade: "A", dia: "32 Dia", weight: 1, moved_weight: 0,
	}]

	await page.goto(`${SITE}/web/cutting/plans/${encodeURIComponent(fixture.name)}`, { waitUntil: "domcontentloaded" })
	await page.locator(".cutting-tabs").waitFor({ timeout: 20_000 })
	await page.getByRole("tab", { name: "CPM", exact: true }).click()
	const cpm = page.locator(".erp-cpm-workspace")
	await cpm.getByRole("heading", { name: "Cut Panel Movement", exact: true }).waitFor({ timeout: 20_000 })
	assert(await cpm.getByRole("heading", { name: "Cut Panel Movement", exact: true }).count() === 1, "CPM functional heading is duplicated")
	for (const filler of ["Generate and move the bundles created by this cutting plan", "Bundle movement", "Cutting origin movement", "newest first"]) {
		assert(await cpm.getByText(filler, { exact: false }).count() === 0, `CPM retains redundant copy: ${filler}`)
	}

	const cards = cpm.locator(".erp-record-card")
	assert(await cards.count() === workspace.movements.length, "CPM movement card count differs from workspace data")
	const firstCard = cards.first()
	for (const selector of ["header strong", ".erp-status", ".erp-movement-time", ".erp-record-metrics"]) {
		assert(await firstCard.locator(selector).count() === 1, `Movement card is missing ${selector}`)
	}
	const renderedNames = await cards.locator("header strong").allTextContents()
	const expectedNames = [...workspace.movements]
		.sort((left, right) => String(right.modified).localeCompare(String(left.modified)))
		.map((movement) => movement.name)
	assert(JSON.stringify(renderedNames) === JSON.stringify(expectedNames), `Movements are not newest first: ${renderedNames}`)
	const movementTimes = await cards.locator(".erp-movement-time strong").allTextContents()
	assert(movementTimes.every((value) => /^\d{2}-\d{2}-\d{4}(?: · \d{2}:\d{2})?$/.test(value)), `Movement dates are unclear: ${movementTimes}`)
	const cpmUndersizedText = await visibleTextBelowMinimum(cpm)
	assert(cpmUndersizedText.length === 0, `CPM workspace contains text below 11px: ${JSON.stringify(cpmUndersizedText.slice(0, 8))}`)

	await page.route("**generate_movement_bundles*", (route) => route.fulfill({
		status: 200,
		contentType: "application/json",
		body: JSON.stringify({ message: generated }),
	}))
	const initialUrl = page.url()
	await cpm.getByRole("button", { name: "Create Movement", exact: true }).click()
	const dialog = page.getByRole("dialog", { name: "Create Cut Panel Movement" })
	await dialog.waitFor()
	assert(page.url() === initialUrl, "Create Movement navigates away from the Cutting Plan")
	await dialog.getByRole("button", { name: "Generate Bundles", exact: true }).click()
	await dialog.locator(".erp-bundle-matrix").first().waitFor({ timeout: 20_000 })

	assert(await dialog.getByRole("heading", { name: "Collapsed bundles", exact: true }).count() === 1, "Collapsed selection section is missing")
	assert(await dialog.getByRole("heading", { name: "Accessory fabric", exact: true }).count() === 1, "Accessory selection section is missing")
	const matrixScroll = await dialog.locator(".erp-matrix-scroll").first().evaluate((element) => ({
		clientWidth: element.clientWidth,
		scrollWidth: element.scrollWidth,
		overflowX: getComputedStyle(element).overflowX,
	}))
	assert(matrixScroll.scrollWidth >= matrixScroll.clientWidth && ["auto", "scroll"].includes(matrixScroll.overflowX), "CPM matrix does not preserve horizontal scrolling")

	const selectionSummary = dialog.locator(".erp-selection-summary")
	const summaryBefore = await selectionSummary.innerText()
	const firstRow = dialog.locator(".erp-bundle-table tbody tr").first()
	const rowCheckbox = firstRow.locator(".erp-row-check input")
	const panelCheckboxes = firstRow.locator(".erp-panel-choice input")
	assert(await rowCheckbox.count() === 1 && await panelCheckboxes.count() > 0, "Bundle and panel selectors are not independently available")
	await rowCheckbox.click()
	const summaryAfterBundle = await selectionSummary.innerText()
	assert(summaryAfterBundle !== summaryBefore, "Selection totals did not update after selecting a bundle")
	const columnCheckbox = dialog.locator(".erp-column-check input").first()
	assert(await columnCheckbox.count() === 1, "Panel column selector is missing")
	assert(!await columnCheckbox.isChecked(), "Selecting one bundle incorrectly selects the full panel column")
	await panelCheckboxes.first().click()
	const summaryAfterPanel = await selectionSummary.innerText()
	assert(summaryAfterPanel !== summaryAfterBundle, "Selection totals did not update after changing an individual panel")
	const dialogUndersizedText = await visibleTextBelowMinimum(dialog)
	assert(dialogUndersizedText.length === 0, `CPM dialog contains text below 11px: ${JSON.stringify(dialogUndersizedText.slice(0, 8))}`)
	await dialog.locator(".p-dialog-footer").getByRole("button", { name: "Close", exact: true }).click()

	await firstCard.getByRole("button", { name: "View", exact: true }).click()
	const readonlyDialog = page.getByRole("dialog", { name: new RegExp(workspace.movements[0].name) })
	await readonlyDialog.waitFor()
	assert(await readonlyDialog.getByRole("button", { name: "Save Draft", exact: true }).count() === 0, "Submitted movement still exposes Save Draft")
	assert(await readonlyDialog.getByRole("button", { name: "Save & Submit", exact: true }).count() === 0, "Submitted movement still exposes Save & Submit")
	await readonlyDialog.locator(".p-dialog-footer").getByRole("button", { name: "Close", exact: true }).click()

	const statesPage = await context.newPage()
	try {
		const statePlan = await findCuttingPlan(statesPage.request, (_, name) => name === "CP-2609-00042")
		const stateWorkspace = await getMethodFixture(statesPage.request, `${cpmMethod}get_workspace`, { cutting_plan: statePlan.name })
		await statesPage.route("**cutting.web_workspace.get_workspace*", (route) => route.fulfill({
			status: 200, contentType: "application/json", body: JSON.stringify({ message: stateWorkspace }),
		}))
		await statesPage.goto(`${SITE}/web/cutting/plans/${encodeURIComponent(statePlan.name)}`, { waitUntil: "domcontentloaded" })
		await statesPage.getByRole("tab", { name: "CPM", exact: true }).click()
		await statesPage.locator(".erp-record-card").first().waitFor({ timeout: 20_000 })
		const statuses = await statesPage.locator(".erp-record-card .erp-status").allTextContents()
		assert(statuses.includes("Submitted") && statuses.includes("Cancelled"), `CPM state cards are incomplete: ${statuses}`)
	} finally {
		await statesPage.close()
	}

	const emptyPage = await context.newPage()
	try {
		await emptyPage.route("**cutting.web_workspace.get_workspace*", (route) => route.fulfill({
			status: 200, contentType: "application/json", body: JSON.stringify({ message: { ...workspace, movements: [] } }),
		}))
		await emptyPage.goto(`${SITE}/web/cutting/plans/${encodeURIComponent(fixture.name)}`, { waitUntil: "domcontentloaded" })
		await emptyPage.getByRole("tab", { name: "CPM", exact: true }).click()
		await emptyPage.getByText("No cut-panel movements yet", { exact: true }).waitFor({ timeout: 20_000 })
	} finally {
		await emptyPage.close()
	}

	return { plan: fixture.name, movementCount: renderedNames.length, movementTimes, matrixScroll, summaryBefore, summaryAfterBundle, summaryAfterPanel }
}

const suites = {
	tokens: tokensSuite,
	shell: shellSuite,
	"cutting-entry": cuttingEntrySuite,
	list: listSuite,
	"plan-frame": planFrameSuite,
	"plan-primary-tabs": planPrimaryTabsSuite,
	sidebar: sidebarSuite,
	"entity-dialogs": entityDialogsSuite,
	cpm: cpmSuite,
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
