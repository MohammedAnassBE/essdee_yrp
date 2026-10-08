#!/usr/bin/env node

import { createRequire } from "node:module"
import { existsSync, readFileSync } from "node:fs"

const require = createRequire("/home/anas/.claude/playwright/package.json")
const { chromium } = require("playwright")

const SITE = process.env.ESSDEE_TEST_SITE || "http://erp-migration-test.site:8001"
const CREDENTIALS = "/home/anas/.frappe-debug-creds-mrp3"
const suite = process.argv[2] || "all"

class FixtureUnavailableError extends Error {
	constructor(message) {
		super(message)
		this.name = "FixtureUnavailableError"
	}
}

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
		if (response.status() === 404) continue
		assert(response.ok(), `Unable to load Cutting Plan ${name} (${response.status()})`)
		const data = (await response.json()).message || {}
		if (await predicate(data, name)) return { name, data }
	}

	throw new FixtureUnavailableError("No Cutting Plan fixture matched the requested state")
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
	const mainSource = readFileSync(new URL("../frontend/src/main.js", import.meta.url), "utf8")
	assert(mainSource.includes('@fontsource-variable/inter'), "The declared Inter UI font is not shipped with the application")
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
	assert(contract.controlRadius === "9px", "control radius is not locked")
	assert(contract.panelRadius === "14px", "panel radius is not locked")
	assert(contract.accent === "#059669", "emerald accent is not locked")
	assert(contract.minimumFontSize === "11px", "minimum text size is not locked")
	assert(contract.canvas === "rgb(247, 248, 250)", "stable canvas color is not applied")

	return contract
}

async function shellSuite(page) {
	await page.setViewportSize({ width: 1600, height: 1000 })
	await page.goto(`${SITE}/web/`, { waitUntil: "domcontentloaded" })
	await page.locator(".department-card-link").first().waitFor({ timeout: 20_000 })

	const destinations = page.locator(".department-card-link")
	assert(await destinations.count() === 10, "Administrator must show ten department destinations")
	assert(await page.getByText("Open workspace", { exact: true }).count() === 0, "Redundant workspace filler is visible")
	assert(await page.locator("body").evaluate((body) => getComputedStyle(body).backgroundColor) === "rgb(247, 248, 250)", "Shell canvas is not stable")

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
	await destinations.first().click()
	await page.waitForURL("**/web/cutting")
	await page.locator(".workspace-launcher").waitFor({ timeout: 20_000 })
	assert(
		(await page.locator(".department-page__nav .back-link").innerText()).trim() === "Workspaces",
		"Root department launchers do not identify their Workspaces destination",
	)
	assert(await page.evaluate(() => document.activeElement?.id) === "app-main", "Route navigation does not move focus to the new main content")
	assert((await page.title()).includes("Cutting"), `Route navigation does not update the document title: ${await page.title()}`)

	await page.goto(`${SITE}/web/fabric-store`, { waitUntil: "domcontentloaded" })
	const flatPanel = page.locator(".department-page__panel--flat")
	await flatPanel.waitFor({ timeout: 20_000 })
	const flatSurface = await flatPanel.evaluate((element) => {
		const style = getComputedStyle(element)
		return { background: style.backgroundColor, radius: style.borderRadius, shadow: style.boxShadow }
	})
	assert(flatSurface.background === "rgba(0, 0, 0, 0)", `Flat department surface is opaque: ${JSON.stringify(flatSurface)}`)
	assert(flatSurface.radius === "0px" && flatSurface.shadow === "none", `Flat department surface retains generic card chrome: ${JSON.stringify(flatSurface)}`)

	await page.setViewportSize({ width: 390, height: 844 })
	assert(await page.locator(".app-topbar__home").getAttribute("aria-label") === "Workspaces", "Mobile Workspaces link has no persistent accessible name")

	return { destinationCount: 10, columnCount, focusVisible, flatSurface }
}

async function cuttingEntrySuite(page, context) {
	await page.setViewportSize({ width: 1600, height: 1000 })
	await page.goto(`${SITE}/web/cutting`, { waitUntil: "domcontentloaded" })
	await page.locator(".workspace-launcher__card").first().waitFor({ timeout: 20_000 })

	const entries = page.locator(".workspace-launcher__card")
	assert(await entries.count() === 5, "Cutting must show the five permitted destinations")
	assert(await page.getByText("Manufacturing workspace", { exact: true }).count() === 0, "Decorative Cutting eyebrow is visible")
	assert(await page.locator(".erp-page-header__description").count() === 0, "Cutting introductory paragraph is still visible")
	assert(await page.locator(".workspace-card__label").count() === 0, "Redundant Cutting card category labels are visible")
	assert((await visibleTextBelowMinimum(page)).length === 0, "Cutting entry contains visible text below 11px")

	await page.setViewportSize({ width: 760, height: 900 })
	const columnCount = await page.locator(".workspace-launcher__grid").evaluate((element) =>
		getComputedStyle(element).gridTemplateColumns.split(" ").filter(Boolean).length,
	)
	assert(columnCount === 1, "Cutting destinations do not collapse to one column at 760px")

	const restrictedPage = await context.newPage()
	try {
		await restrictedPage.route("**/api/method/essdee_yrp.cutting.web_capabilities.get_capabilities*", (route) =>
			route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: {
				"cutting-plans": { can_read: false, can_create: false },
				"cutting-orders": { can_read: false, can_create: false },
				"bulk-lay-sheets": { can_read: false, can_create: false },
				"lay-sheet-planner": { can_read: false, can_create: false },
				reports: { can_read: false, can_create: false },
			} }) }),
		)
		await restrictedPage.goto(`${SITE}/web/cutting`, { waitUntil: "domcontentloaded" })
		await restrictedPage.locator(".workspace-launcher__empty").waitFor({ timeout: 20_000 })
		assert(await restrictedPage.locator(".workspace-launcher__card").count() === 0, "Restricted destinations remain visible")
		assert(await restrictedPage.locator(".workspace-launcher__empty").isVisible(), "No-permission state is not visible")
	} finally {
		await restrictedPage.close()
	}

	return { entryCount: await entries.count(), columnCount }
}

async function listSuite(page, context) {
	await page.setViewportSize({ width: 1600, height: 1000 })
	await page.route("**/api/resource/SD%20YRP%20Cutting%20Plan?*", async (route) => {
		const filters = new URL(route.request().url()).searchParams.get("filters") || ""
		const data = filters.includes("__no_matching_cutting_plan__") ? [] : [{
			name: "CP-UI-AUDIT-00001",
			lot: "LOT-WITH-A-LONG-VISIBLE-NAME-FOR-ELLIPSIS",
			item: "STYLE-UI-AUDIT",
			cp_status: "Draft",
			no_of_colours: 3,
			no_of_colours_completed: 1,
			modified: "2026-10-08 02:00:00",
		}]
		await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data }) })
	})
	await page.goto(`${SITE}/web/cutting/plans`, { waitUntil: "domcontentloaded" })
	await page.getByRole("button", { name: "Filters", exact: true }).waitFor({ timeout: 20_000 })
	await page.locator(".premium-list-table .p-datatable-tbody > tr").first().waitFor({ timeout: 20_000 })

	assert(await page.locator(".list-page-head").count() === 1, "List command header is duplicated")
	const listSurface = await page.locator(".cutting-list").boundingBox()
	assert(listSurface?.width >= 1520, `Cutting list does not use the shared full-width shell: ${JSON.stringify(listSurface)}`)
	const populatedFrameHeight = (await page.locator(".list-table-frame").boundingBox())?.height || 0
	assert(populatedFrameHeight > 300, `Populated desktop list no longer uses its viewport-bounded data region: ${populatedFrameHeight}`)
	assert(await page.getByText(/^\d+\s+records$/i).count() === 0, "Header record-count prose is visible")
	assert(await page.locator(".mobile-quick-filter-toggle:visible").count() === 0, "Mobile quick-filter control is visible on desktop")
	const openTarget = await page.locator(".list-row-open").first().boundingBox()
	assert(openTarget?.width >= 36 && openTarget?.height >= 36, `List open action has a small pointer target: ${JSON.stringify(openTarget)}`)
	const selectionTargets = await page.locator(".premium-list-table .p-checkbox").evaluateAll((elements) => elements.map((element) => element.getBoundingClientRect().toJSON()))
	assert(selectionTargets.every(({ width, height }) => width >= 36 && height >= 36), `List selection controls have small pointer targets: ${JSON.stringify(selectionTargets)}`)
	const statusRailStyle = await page.locator(".list-status-tabs").evaluate((element) => ({ overflowX: getComputedStyle(element).overflowX, maskImage: getComputedStyle(element).maskImage }))
	assert(["auto", "scroll"].includes(statusRailStyle.overflowX) && statusRailStyle.maskImage !== "none", `Status rail lacks a horizontal-scroll affordance: ${JSON.stringify(statusRailStyle)}`)
	const primaryButtonShadow = await page.locator(".list-toolbar__primary .p-button").first().evaluate((element) => getComputedStyle(element).boxShadow)
	assert(primaryButtonShadow === "none", "List primary action bypasses the shared flat command treatment")

	const toolbarControls = page.locator(".list-search input, .list-toolbar__primary > .p-button, .list-toolbar__secondary > .p-button")
	const controlHeights = await toolbarControls.evaluateAll((elements) =>
		elements.map((element) => Math.round(element.getBoundingClientRect().height)),
	)
	assert(controlHeights.length >= 5, "Expected list command controls are missing")
	assert(controlHeights.every((height) => height === 38), `List controls are not 38px: ${controlHeights.join(", ")}`)

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
	await filterDialog.waitFor({ state: "hidden" })

	await page.getByRole("button", { name: "Columns", exact: true }).click()
	const columnDialog = page.getByRole("dialog", { name: "Customize Columns" })
	await columnDialog.waitFor()
	assert(await columnDialog.locator(".column-drag-handle").count() > 0, "Column editor has no drag handles")
	await columnDialog.getByRole("button", { name: "Cancel", exact: true }).click()
	await columnDialog.waitFor({ state: "hidden" })

	const undersizedText = await visibleTextBelowMinimum(page)
	assert(undersizedText.length === 0, `List contains text below 11px: ${JSON.stringify(undersizedText.slice(0, 8))}`)

	const search = page.locator(".list-search input")
	await search.fill("__no_matching_cutting_plan__")
	await search.press("Enter")
	await page.locator(".list-empty").waitFor({ timeout: 20_000 })
	await page.waitForFunction(() => !document.querySelector('button[aria-label="Refresh"]')?.disabled)
	await page.locator(".p-datatable-mask").waitFor({ state: "hidden" })
	assert(await page.locator(".list-empty:visible").getByText("No records found", { exact: true }).isVisible(), "Empty search state is not intentional")
	const desktopEmptyFrameHeight = (await page.locator(".list-table-frame").boundingBox())?.height || 0
	assert(
		desktopEmptyFrameHeight >= 220 && desktopEmptyFrameHeight <= 300,
		`Empty desktop list does not collapse to a compact 220–300px data region: ${desktopEmptyFrameHeight}`,
	)
	await page.setViewportSize({ width: 390, height: 844 })
	const mobileCreateLabel = page.locator(".list-toolbar__primary .p-button-label")
	assert(
		await mobileCreateLabel.isVisible() && (await mobileCreateLabel.innerText()).trim().startsWith("Create"),
		"Mobile list hides the primary create action label",
	)
	const activeFilterBadge = page.getByRole("button", { name: /^Filters/ }).locator(".p-badge")
	assert(
		await activeFilterBadge.isVisible() && (await activeFilterBadge.innerText()).trim() === "1",
		"Mobile list does not expose the active query count on its Filters action",
	)
	const filterActionTreatment = await page.locator(".list-toolbar__secondary").evaluate((toolbar) => {
		const buttons = Array.from(toolbar.querySelectorAll("button"))
		const clear = buttons.find((button) => button.textContent.includes("Clear Filters"))
		const columns = buttons.find((button) => button.textContent.includes("Columns"))
		const treatment = (button) => {
			const style = getComputedStyle(button)
			return [style.color, style.backgroundColor, style.borderColor].join("|")
		}
		return { clear: treatment(clear), columns: treatment(columns), clearDisabled: clear.disabled }
	})
	assert(
		!filterActionTreatment.clearDisabled && filterActionTreatment.clear !== filterActionTreatment.columns,
		`Active Clear Filters action is not visually distinct: ${JSON.stringify(filterActionTreatment)}`,
	)
	const emptyStateSurface = await page.locator(".mobile-list-empty:visible").evaluate((element) => {
		const frame = element.closest(".list-table-frame")
		return {
			background: getComputedStyle(element).backgroundColor,
			color: getComputedStyle(element).color,
			frameBackground: getComputedStyle(frame).backgroundColor,
		}
	})
	assert(emptyStateSurface.frameBackground === "rgb(255, 255, 255)", `Mobile list empty state is not on the shared bright surface: ${JSON.stringify(emptyStateSurface)}`)
	const mobileEmptyState = await page.locator(".mobile-list-empty:visible").evaluate((emptyState) => {
		const frame = emptyState.closest(".list-table-frame")
		const message = emptyState.querySelector("strong")
		const frameRect = frame.getBoundingClientRect()
		const emptyRect = emptyState.getBoundingClientRect()
		const messageRect = message?.getBoundingClientRect()
		return {
			frame: { left: frameRect.left, right: frameRect.right },
			empty: { left: emptyRect.left, right: emptyRect.right },
			message: messageRect ? { left: messageRect.left, right: messageRect.right } : null,
			desktopDisplay: getComputedStyle(frame.querySelector(".premium-list-table")).display,
		}
	})
	await page.screenshot({ path: "/tmp/essdee-cutting-list-empty-mobile.png", fullPage: true })
	assert(
		mobileEmptyState.message
			&& mobileEmptyState.empty.left >= mobileEmptyState.frame.left
			&& mobileEmptyState.empty.right <= mobileEmptyState.frame.right
			&& mobileEmptyState.message.left >= mobileEmptyState.frame.left
			&& mobileEmptyState.message.right <= mobileEmptyState.frame.right
			&& mobileEmptyState.desktopDisplay === "none",
		`Mobile list empty state is outside the responsive record surface: ${JSON.stringify(mobileEmptyState)}`,
	)
	await page.setViewportSize({ width: 320, height: 720 })
	const narrowToolbarGeometry = await page.locator(".list-toolbar__actions").evaluate((toolbar) => {
		const search = toolbar.querySelector(".list-search").getBoundingClientRect()
		const create = toolbar.querySelector(".list-toolbar__primary .p-button").getBoundingClientRect()
		return {
			searchWidth: search.width,
			createWidth: create.width,
			createBelowSearch: create.top >= search.bottom,
		}
	})
	assert(
		narrowToolbarGeometry.searchWidth >= 250
			&& narrowToolbarGeometry.createWidth >= 250
			&& narrowToolbarGeometry.createBelowSearch,
		`Narrow mobile list commands crowd the search field: ${JSON.stringify(narrowToolbarGeometry)}`,
	)
	await page.getByRole("button", { name: "Clear Filters", exact: true }).click()
	await page.locator(".mobile-list-record").first().waitFor({ timeout: 20_000 })

	await page.setViewportSize({ width: 900, height: 760 })
	const quickFilterRows = await page.locator(".list-quick-filters .quick-filter-field").evaluateAll((elements) => new Set(elements.map((element) => Math.round(element.getBoundingClientRect().y))).size)
	assert(quickFilterRows === 1, `Cutting Plan quick filters leave an orphaned row at 900px: ${quickFilterRows}`)
	const tabletListSurface = await page.locator(".list-table-frame").evaluate((frame) => ({
		desktopDisplay: getComputedStyle(frame.querySelector(".premium-list-table")).display,
		recordDisplay: getComputedStyle(frame.querySelector(".mobile-list-records")).display,
	}))
	assert(
		tabletListSurface.desktopDisplay === "none" && tabletListSurface.recordDisplay === "grid",
		`Tablet list does not use the responsive record surface: ${JSON.stringify(tabletListSurface)}`,
	)
	await page.setViewportSize({ width: 1280, height: 900 })
	await page.locator(".premium-list-table .p-datatable-tbody > tr").first().waitFor({ timeout: 20_000 })
	const tableContainment = await page.locator(".p-datatable-table-container").evaluate((element) => ({
		clientWidth: element.clientWidth,
		scrollWidth: element.scrollWidth,
		overflowX: getComputedStyle(element).overflowX,
		role: element.getAttribute("role"),
		tabIndex: element.tabIndex,
		ariaLabel: element.getAttribute("aria-label"),
	}))
	assert(tableContainment.scrollWidth >= tableContainment.clientWidth, "List table does not retain horizontal containment")
	assert(["auto", "scroll"].includes(tableContainment.overflowX), "List table cannot scroll horizontally")
	assert(tableContainment.role === "region" && tableContainment.tabIndex === 0 && Boolean(tableContainment.ariaLabel), `List table scroller is not a named keyboard region: ${JSON.stringify(tableContainment)}`)

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

	return { controlHeights, headerPosition, numericAlignment, longValueTreatment, populatedFrameHeight, desktopEmptyFrameHeight, emptyStateSurface, tabletListSurface, tableContainment }
}

function groupItemCount(value) {
	const groups = normaliseItemGroups(value)
	return groups.reduce((total, group) => total + (group?.items?.length || 0), 0)
}

function normaliseItemGroups(value) {
	if (Array.isArray(value)) return value.filter((group) => group?.items)
	if (value?.items) return [value]
	return Object.values(value || {}).filter((group) => group?.items)
}

async function openPlan(page, predicate = () => true) {
	const fixture = await findCuttingPlan(page.request, predicate)
	await page.goto(`${SITE}/web/cutting/plans/${encodeURIComponent(fixture.name)}`, { waitUntil: "domcontentloaded" })
	await page.locator(".cutting-tabs").waitFor({ timeout: 20_000 })
	return fixture
}

async function invokeFormViewMethod(formView, method) {
	await formView.evaluate(async (element, methodName) => {
		const appContainer = Array.from(document.querySelectorAll("*")).find((candidate) => candidate.__vue_app__)
		const root = appContainer?.__vue_app__?._instance || appContainer?._vnode?.component
		const queue = root ? [root] : []
		const visited = new Set()
		const componentChain = []
		const enqueueVNode = (vnode) => {
			if (!vnode || typeof vnode !== "object") return
			if (Array.isArray(vnode)) {
				for (const child of vnode) enqueueVNode(child)
				return
			}
			if (vnode.component) queue.push(vnode.component)
			if (Array.isArray(vnode.children)) enqueueVNode(vnode.children)
			if (vnode.suspense?.activeBranch) enqueueVNode(vnode.suspense.activeBranch)
		}
		let instance = null
		while (queue.length) {
			const candidate = queue.shift()
			if (!candidate || visited.has(candidate)) continue
			visited.add(candidate)
			componentChain.push({
				name: candidate.type?.name || candidate.type?.__name || "anonymous",
				exposed: Object.keys(candidate.exposed || {}),
			})
			if (candidate.exposed?.[methodName] && candidate.subTree?.el === element) {
				instance = candidate
				break
			}
			enqueueVNode(candidate.subTree)
		}
		if (!instance) throw new Error(`FormView does not expose ${methodName}(): ${JSON.stringify({ appContainer: appContainer?.id || null, appKeys: Object.keys(appContainer?.__vue_app__ || {}), componentChain })}`)
		await instance.exposed[methodName]()
	}, method)
}

async function formLoadFailuresSuite(page, context) {
	await page.setViewportSize({ width: 1600, height: 1000 })
	const fixture = await findCuttingPlan(page.request)
	let metadataFailure = true
	let createMutations = 0

	await page.route("**/api/method/frappe.desk.form.load.getdoctype*", (route) => {
		if (!metadataFailure) return route.continue()
		return route.fulfill({
			status: 200,
			contentType: "application/json",
			body: JSON.stringify({ exc: "MetadataUnavailable", message: "Metadata unavailable" }),
		})
	})
	await page.route("**/api/resource/**", (route) => {
		if (!decodeURIComponent(route.request().url()).includes("/api/resource/SD YRP Cutting Plan")) return route.continue()
		if (route.request().method() === "GET") return route.continue()
		createMutations += 1
		return route.fulfill({
			status: 200,
			contentType: "application/json",
			body: JSON.stringify({ data: { name: "UNEXPECTED-FORM-CREATE" } }),
		})
	})

	await page.goto(`${SITE}/web/cutting/plans/${encodeURIComponent(fixture.name)}`, { waitUntil: "domcontentloaded" })
	const failedInitialForm = page.locator(".cutting-plan-frame > .common-form-view")
	await failedInitialForm.locator(".form-load-error").waitFor({ timeout: 20_000 })
	const initialActions = await failedInitialForm.locator(".form-toolbar__actions button").allTextContents()
	const initialFailureMessage = await failedInitialForm.locator(".form-load-error").innerText()
	await invokeFormViewMethod(failedInitialForm, "save")
	await page.waitForTimeout(100)
	assert(initialActions.length === 0, `Metadata load failure exposes form actions: ${JSON.stringify(initialActions)}`)
	assert(createMutations === 0, `Programmatic save created a document after metadata load failure: ${createMutations}`)
	assert(
		await failedInitialForm.locator(".form-load-error").innerText() === initialFailureMessage,
		"Programmatic save replaced the metadata load error state",
	)

	const reloadPage = await context.newPage()
	let documentFailure = false
	let reloadMutations = 0
	try {
		await reloadPage.route("**/api/resource/**", (route) => {
			const request = route.request()
			if (!decodeURIComponent(request.url()).includes("/api/resource/SD YRP Cutting Plan")) return route.continue()
			if (request.method() === "GET" && documentFailure) {
				return route.fulfill({
					status: 200,
					contentType: "application/json",
					body: JSON.stringify({ exc: "DocumentUnavailable", message: "Document unavailable" }),
				})
			}
			if (request.method() === "GET") return route.continue()
			reloadMutations += 1
			return route.fulfill({
				status: 200,
				contentType: "application/json",
				body: JSON.stringify({ data: { name: fixture.name } }),
			})
		})
		await reloadPage.goto(`${SITE}/web/cutting/plans/${encodeURIComponent(fixture.name)}`, { waitUntil: "domcontentloaded" })
		const formView = reloadPage.locator(".cutting-plan-frame > .common-form-view")
		await formView.getByRole("button", { name: "Edit", exact: true }).waitFor({ timeout: 20_000 })
		await formView.getByRole("button", { name: "Edit", exact: true }).click()
		await formView.getByRole("button", { name: "Save", exact: true }).waitFor()

		documentFailure = true
		await invokeFormViewMethod(formView, "reload")
		await formView.locator(".form-load-error").waitFor()
		const failedReloadActions = await formView.locator(".form-toolbar__actions button").allTextContents()
		const failedReloadIdentity = (await formView.locator(".form-toolbar__meta > small").innerText()).trim()
		const reloadFailureMessage = await formView.locator(".form-load-error").innerText()
		const toastCountBeforeSave = await reloadPage.locator(".p-toast-message").count()
		await invokeFormViewMethod(formView, "save")
		await reloadPage.waitForTimeout(100)

		assert(failedReloadActions.length === 0, `Document reload failure leaves stale actions: ${JSON.stringify(failedReloadActions)}`)
		assert(failedReloadIdentity !== fixture.name, `Document reload failure leaves stale record identity: ${failedReloadIdentity}`)
		assert(reloadMutations === 0, `Programmatic save mutated a document after document load failure: ${reloadMutations}`)
		assert(
			await formView.locator(".form-load-error").innerText() === reloadFailureMessage,
			"Programmatic save replaced the document load error state",
		)
		assert(
			await reloadPage.locator(".p-toast-message").count() === toastCountBeforeSave,
			"Programmatic save emitted validation feedback after document load failure",
		)

		documentFailure = false
		const recoveryDialog = reloadPage.locator(".document-error-dialog:visible")
		await recoveryDialog.getByRole("button", { name: "Retry", exact: true }).click()
		await formView.locator(".form-toolbar__meta > small").getByText(fixture.name, { exact: true }).waitFor()
		await formView.getByRole("button", { name: "Edit", exact: true }).waitFor()
		assert(
			(await formView.locator(".form-toolbar__meta > small").innerText()).trim() === fixture.name,
			"Retry did not restore the loaded document identity",
		)
	} finally {
		await reloadPage.close()
	}

	return { plan: fixture.name, metadataFailureGuarded: true, documentFailureGuarded: true }
}

async function formFieldAccessibilitySuite(page) {
	await page.setViewportSize({ width: 1600, height: 1000 })
	const fixtureName = "A11Y-FORM-CONTROLS"
	const fields = [
		{ fieldname: "is_manual_entry", label: "Required Toggle", fieldtype: "Check", reqd: 1, description: "Choose whether entry is manual." },
		{ fieldname: "no_of_colours", label: "Required Select", fieldtype: "Select", options: "One\nTwo", reqd: 1, description: "Choose one option." },
		{ fieldname: "maximum_no_of_plys", label: "Required Number", fieldtype: "Int", reqd: 1, description: "Enter a whole number." },
		{ fieldname: "cutting_start_date", label: "Required Date", fieldtype: "Date", reqd: 1, description: "Choose a date." },
		{ fieldname: "cutting_location", label: "Required Datetime", fieldtype: "Datetime", reqd: 1, description: "Choose a date and time." },
		{ fieldname: "cutting_end_date", label: "Required Time", fieldtype: "Time", reqd: 1, description: "Choose a time." },
	]
	let mutationCalls = 0

	await page.route("**/api/method/essdee_yrp.cutting.plan_editor.get_editor*", (route) => route.fulfill({
		status: 200,
		contentType: "application/json",
		body: JSON.stringify({ message: { record: { name: fixtureName, docstatus: 1 }, permissions: { can_write: true } } }),
	}))
	await page.route("**/api/method/frappe.desk.form.load.getdoctype*", (route) => route.fulfill({
		status: 200,
		contentType: "application/json",
		body: JSON.stringify({ docs: [{ name: "SD YRP Cutting Plan", label: "Cutting Plan", fields }] }),
	}))
	await page.route("**/api/resource/**", (route) => {
		if (!decodeURIComponent(route.request().url()).includes(`/api/resource/SD YRP Cutting Plan/${fixtureName}`)) return route.continue()
		if (route.request().method() === "GET") {
			return route.fulfill({
				status: 200,
				contentType: "application/json",
				body: JSON.stringify({ data: { name: fixtureName, docstatus: 1 } }),
			})
		}
		mutationCalls += 1
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data: { name: fixtureName } }) })
	})
	await page.route("**get_web_view_data*", (route) => route.fulfill({
		status: 200,
		contentType: "application/json",
		body: JSON.stringify({ message: { permissions: { can_write: true } } }),
	}))

	await page.goto(`${SITE}/web/cutting/plans/${fixtureName}`, { waitUntil: "domcontentloaded" })
	const formView = page.locator(".cutting-plan-frame > .common-form-view")
	await formView.getByRole("button", { name: "Edit", exact: true }).waitFor({ timeout: 20_000 })
	await formView.getByRole("button", { name: "Edit", exact: true }).click()
	await formView.getByRole("button", { name: "Save", exact: true }).click()

	const controls = [
		{ label: "Required Toggle", selector: ".p-toggleswitch-input", nativeRequired: true },
		{ label: "Required Select", selector: ".p-select-label", nativeRequired: false },
		{ label: "Required Number", selector: ".p-inputnumber-input", nativeRequired: true },
		{ label: "Required Date", selector: ".p-datepicker-input", nativeRequired: true },
		{ label: "Required Datetime", selector: ".p-datepicker-input", nativeRequired: true },
		{ label: "Required Time", selector: ".p-datepicker-input", nativeRequired: true },
	]
	const contracts = {}
	for (const control of controls) {
		const field = formView.locator(".form-field").filter({ hasText: control.label }).first()
		await field.locator(".form-field__error").waitFor()
		contracts[control.label] = await field.locator(control.selector).evaluate((element, expectsNativeRequired) => {
			const describedBy = element.getAttribute("aria-describedby") || ""
			const descriptionIds = describedBy.split(/\s+/).filter(Boolean)
			return {
				tag: element.tagName.toLowerCase(),
				required: element.hasAttribute("required"),
				expectsNativeRequired,
				ariaRequired: element.getAttribute("aria-required"),
				ariaInvalid: element.getAttribute("aria-invalid"),
				describedBy,
				descriptions: descriptionIds.map((id) => document.getElementById(id)?.textContent?.trim() || ""),
			}
		}, control.nativeRequired)
	}

	for (const [label, contract] of Object.entries(contracts)) {
		assert(contract.ariaRequired === "true", `${label} focus target is not aria-required: ${JSON.stringify(contract)}`)
		assert(contract.ariaInvalid === "true", `${label} focus target is not aria-invalid: ${JSON.stringify(contract)}`)
		assert(contract.descriptions.length === 2 && contract.descriptions.every(Boolean), `${label} focus target does not reference help and error text: ${JSON.stringify(contract)}`)
		if (contract.expectsNativeRequired) assert(contract.required, `${label} focus target is missing native required support: ${JSON.stringify(contract)}`)
	}
	assert(mutationCalls === 0, `Invalid FormField controls allowed a document mutation: ${mutationCalls}`)

	return { fixture: fixtureName, contracts }
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
	const recordFrameStyle = await main.evaluate((element) => ({ padding: getComputedStyle(element).padding, overflow: getComputedStyle(element).overflow }))
	const toolbarStyle = await main.locator(".form-toolbar").evaluate((element) => ({ borderRadius: getComputedStyle(element).borderRadius, boxShadow: getComputedStyle(element).boxShadow, borderTopWidth: getComputedStyle(element).borderTopWidth }))
	assert(recordFrameStyle.padding === "0px" && recordFrameStyle.overflow === "hidden", `Cutting Plan still nests a padded record card: ${JSON.stringify(recordFrameStyle)}`)
	assert(toolbarStyle.borderRadius === "0px" && toolbarStyle.boxShadow === "none" && toolbarStyle.borderTopWidth === "3px", `Cutting Plan toolbar still renders as a nested card: ${JSON.stringify(toolbarStyle)}`)

	const recordId = page.locator(".form-toolbar__meta > small")
	const status = page.locator(".form-toolbar__meta .cutting-plan-status")
	const [recordBox, statusBox] = await Promise.all([recordId.boundingBox(), status.boundingBox()])
	assert(recordBox && statusBox && Math.abs(recordBox.y - statusBox.y) < 8, "Status is not beside the record ID")
	const headerFactLabels = await page.locator(".cutting-plan-header-fact small").allTextContents()
	assert(
		JSON.stringify(headerFactLabels) === JSON.stringify(["Lot", "Item"]),
		`Cutting Plan identity facts are incomplete or out of order: ${JSON.stringify(headerFactLabels)}`,
	)
	assert(
		await page.locator(".cutting-plan-header-fact strong").evaluateAll((elements) =>
			elements.every((element) => Boolean(element.textContent.trim()) && element.getBoundingClientRect().width > 0),
		),
		"Lot and Item values are not immediately scannable in the header",
	)
	const headerFactType = await page.locator(".cutting-plan-header-fact").first().evaluate((element) => ({
		label: Number.parseFloat(getComputedStyle(element.querySelector("small")).fontSize),
		value: Number.parseFloat(getComputedStyle(element.querySelector("strong")).fontSize),
	}))
	assert(headerFactType.label >= 11.5 && headerFactType.value >= 13.5, `Lot and Item header facts are too small: ${JSON.stringify(headerFactType)}`)
	await page.locator(".form-toolbar__actions .form-edit-button").waitFor({ timeout: 20_000 })
	assert(await page.locator(".form-toolbar__actions .form-edit-button").count() === 1, "Edit is not a distinct header action")
	assert(await page.locator(".form-toolbar__actions").getByRole("button", { name: "More Actions", exact: true }).count() === 1, "Cutting Plan workflow actions are not available in the header")

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
	const pageViewport = await page.locator("html").evaluate((element) => {
		const layout = document.querySelector(".cutting-plan-layout")
		const departmentPage = document.querySelector(".department-page")
		return {
			clientHeight: element.clientHeight,
			scrollHeight: element.scrollHeight,
			layout: layout ? layout.getBoundingClientRect().toJSON() : null,
			departmentPage: departmentPage ? departmentPage.getBoundingClientRect().toJSON() : null,
		}
	})
	assert(
		pageViewport.scrollHeight <= pageViewport.clientHeight + 1,
		`Cutting Plan leaks its bounded workspace into browser-level vertical scrolling: ${JSON.stringify(pageViewport)}`,
	)

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

	await page.setViewportSize({ width: 390, height: 844 })
	const recordIdentity = await page.locator(".form-toolbar__meta > small").first().evaluate((element) => ({
		text: element.textContent.trim(),
		height: element.getBoundingClientRect().height,
		whiteSpace: getComputedStyle(element).whiteSpace,
	}))
	assert(recordIdentity.whiteSpace === "nowrap" && recordIdentity.height <= 22, `Cutting Plan identity wraps into fragments on mobile: ${JSON.stringify(recordIdentity)}`)

	return { plan: fixture.name, widthRatio, tabCount: await visibleTabs.count(), scrollResult }
}

async function planActionsSuite(page, context) {
	await page.setViewportSize({ width: 1600, height: 1000 })
	const fixture = await openPlan(page, (data) =>
		data.permissions?.can_run_plan_actions
		&& groupItemCount(data.completed_items) > 0
		&& normaliseItemGroups(data.completed_items).some((group) => group.is_set_item && (group.items || []).some((item) => item.completed))
		&& (
			data.permissions?.can_create_recut
			|| data.permissions?.can_create_lot_transfer
			|| data.permissions?.can_change_approval_grammage
		),
	)
	const headerActions = page.locator(".form-toolbar__actions")
	const moreActions = headerActions.getByRole("button", { name: "More Actions", exact: true })
	await moreActions.waitFor({ timeout: 20_000 })
	assert(await page.locator(".plan-command-bar").count() === 0, "The obsolete Cutting Plan action strip is still rendered")
	assert(await page.locator(".cutting-plan-main").evaluate((element) => getComputedStyle(element).gridTemplateRows.split(" ").length === 1), "The removed action strip still reserves a layout row")

	const printButton = headerActions.getByRole("button", { name: "Print", exact: true })
	const editButton = headerActions.getByRole("button", { name: "Edit", exact: true })
	const [printBox, moreBox, editBox] = await Promise.all([printButton.boundingBox(), moreActions.boundingBox(), editButton.boundingBox()])
	assert(
		printBox && moreBox && editBox
			&& Math.abs(printBox.y - moreBox.y) <= 3
			&& Math.abs(moreBox.y - editBox.y) <= 3
			&& printBox.x < moreBox.x
			&& moreBox.x < editBox.x,
		`More Actions is not placed between Print and Edit: ${JSON.stringify({ printBox, moreBox, editBox })}`,
	)

	await moreActions.click()
	const expectedMenuActions = [
		["Generate", fixture.data.permissions?.can_run_plan_actions],
		["Fetch Received Cloth", fixture.data.permissions?.can_run_plan_actions],
		["Calculate LaySheets", fixture.data.permissions?.can_run_plan_actions],
		["Get Completed", true],
		["Update Completed", fixture.data.permissions?.can_update_completed],
		["Update Recut", fixture.data.permissions?.can_create_recut],
		["Update Print Panel", fixture.data.permissions?.can_create_recut],
		["Lot Transfer", fixture.data.permissions?.can_create_lot_transfer],
		["Approval", fixture.data.permissions?.can_change_approval_grammage],
	].filter(([, allowed]) => allowed).map(([label]) => label)
	const menuActionLabels = await page.locator(".plan-actions-menu:visible .p-menu-item-link").allTextContents()
	assert(
		JSON.stringify(menuActionLabels.map((label) => label.trim())) === JSON.stringify(expectedMenuActions),
		`More Actions does not contain every permitted command in workflow order: ${JSON.stringify(menuActionLabels)}`,
	)
	await page.keyboard.press("Escape")

	const completedGroups = normaliseItemGroups(fixture.data.completed_items)
	const expectedCompletedRows = completedGroups.reduce(
		(total, group) => total + (group.items || []).filter((item) => item.completed).length,
		0,
	)
	const summaryTab = page.getByRole("tab", { name: "Summary", exact: true })
	assert(await summaryTab.getAttribute("aria-selected") !== "true", "Summary must not be active before Get Completed")
	await moreActions.click()
	await page.getByRole("menuitem", { name: "Get Completed", exact: true }).click()
	const completedDialog = page.getByRole("dialog", { name: "Completed Cut Quantity", exact: true })
	await completedDialog.waitFor({ timeout: 10_000 })
	assert(await summaryTab.getAttribute("aria-selected") !== "true", "Get Completed still redirects to the Summary tab")
	const reportMeta = completedDialog.locator(".completed-report__meta")
	assert(await reportMeta.getByText("Lot", { exact: true }).count() === 1, "Get Completed report is missing Lot metadata")
	assert(await reportMeta.getByText("Item", { exact: true }).count() === 1, "Get Completed report is missing Item metadata")
	assert(await reportMeta.getByText("Generated", { exact: true }).count() === 1, "Get Completed report is missing generated time")
	assert(
		/^\d{2}-\d{2}-\d{4} \u00b7 \d{2}:\d{2}:\d{2}$/.test((await completedDialog.locator(".completed-report__generated").textContent())?.trim() || ""),
		"Get Completed report does not use a clear date-time format",
	)
	assert(await completedDialog.locator(".completed-report__item-row").count() === expectedCompletedRows, "Get Completed report includes incomplete rows or omits completed rows")
	assert(await completedDialog.locator("input, .p-checkbox").count() === 0, "Get Completed report is editable")
	assert(await completedDialog.locator(".completed-report__total-row").count() > 0, "Get Completed report has no completion totals")
	assert(await completedDialog.getByRole("button", { name: "Copy", exact: true }).count() === 1, "Get Completed report has no Copy action")

	const setGroup = completedGroups.find((group) => group.is_set_item && (group.items || []).some((item) => item.completed))
	const firstCompletedSetItem = setGroup.items.find((item) => item.completed)
	const partAttribute = setGroup.set_item_attr || firstCompletedSetItem.set_attr
	const completedPart = firstCompletedSetItem.attributes?.[partAttribute]
	const partItems = setGroup.items.filter((item) => item.completed && item.attributes?.[partAttribute] === completedPart)
	const partSection = completedDialog.locator(".completed-report__group").filter({ hasText: completedPart }).first()
	assert(
		await partSection.locator(".completed-report__panels").count() === 0,
		`Set-item report exposes panel details for ${completedPart}, unlike the production_api report`,
	)
	const expectedPartTotals = [
		...(setGroup.primary_attribute_values || []).map((value) => partItems.reduce((total, item) => total + Number(item.values?.[value] || 0), 0)),
		partItems.reduce((total, item) => total + (setGroup.primary_attribute_values || []).reduce((sum, value) => sum + Number(item.values?.[value] || 0), 0), 0),
	].map(String)
	assert(
		JSON.stringify(await partSection.locator(".completed-report__total-row .number-cell").allTextContents()) === JSON.stringify(expectedPartTotals),
		`Set-item completion totals are incorrect for ${completedPart}`,
	)
	for (const table of await completedDialog.locator(".completed-report__table").all()) {
		const labelledBy = await table.getAttribute("aria-labelledby")
		assert(labelledBy && await completedDialog.locator(`#${labelledBy}`).count() === 1, "Completed quantity table has no programmatic section name")
	}

	await page.setViewportSize({ width: 700, height: 760 })
	const mediumDialogContract = await completedDialog.evaluate((dialog) => {
		const box = dialog.getBoundingClientRect()
		const content = dialog.querySelector(".p-dialog-content")
		const footer = dialog.querySelector(".p-dialog-footer")
		return {
			contained: box.left >= 0 && box.right <= window.innerWidth,
			contentOverflow: getComputedStyle(content).overflowY,
			footerVisible: footer.getBoundingClientRect().bottom <= box.bottom + 1,
		}
	})
	assert(
		mediumDialogContract.contained && ["auto", "scroll"].includes(mediumDialogContract.contentOverflow) && mediumDialogContract.footerVisible,
		`Get Completed dialog breaks at 700px: ${JSON.stringify(mediumDialogContract)}`,
	)

	await page.setViewportSize({ width: 390, height: 844 })
	const capture = completedDialog.locator(".completed-report-capture")
	await capture.waitFor()
	const captureContract = await completedDialog.evaluate((dialog) => {
		const captureElement = dialog.querySelector(".completed-report-capture")
		const tableWraps = Array.from(dialog.querySelectorAll(".completed-report__table-wrap"))
		const box = dialog.getBoundingClientRect()
		return {
			dialogContained: box.left >= 0 && box.right <= window.innerWidth,
			captureWidth: captureElement?.clientWidth || 0,
			widestTable: Math.max(0, ...tableWraps.map((element) => element.scrollWidth)),
			tablesScrollable: tableWraps.every((element) => ["auto", "scroll"].includes(getComputedStyle(element).overflowX)),
		}
	})
	assert(captureContract.dialogContained && captureContract.tablesScrollable, `Get Completed dialog is not contained on mobile: ${JSON.stringify(captureContract)}`)
	assert(captureContract.widestTable > captureContract.captureWidth, `Mobile fixture does not exercise a horizontally wide completion matrix: ${JSON.stringify(captureContract)}`)
	await page.evaluate(() => {
		window.__completedCopyDimensions = null
		class TestClipboardItem {
			constructor(items) { this.items = items }
		}
		Object.defineProperty(window, "ClipboardItem", { configurable: true, value: TestClipboardItem })
		Object.defineProperty(navigator, "clipboard", {
			configurable: true,
			value: {
				async write(items) {
					const image = await createImageBitmap(items[0].items["image/png"])
					const canvas = document.createElement("canvas")
					canvas.width = image.width
					canvas.height = image.height
					const context = canvas.getContext("2d")
					context.drawImage(image, 0, 0)
					const pixels = context.getImageData(0, 0, image.width, image.height).data
					let nonWhitePixels = 0
					for (let index = 0; index < pixels.length; index += 4) {
						if (pixels[index + 3] && (pixels[index] < 250 || pixels[index + 1] < 250 || pixels[index + 2] < 250)) nonWhitePixels += 1
					}
					window.__completedCopyDimensions = { width: image.width, height: image.height, nonWhitePixels }
					image.close()
				},
			},
		})
	})
	await completedDialog.getByRole("button", { name: "Copy", exact: true }).click()
	await completedDialog.getByText("Completed quantities copied to clipboard.", { exact: true }).waitFor({ timeout: 20_000 })
	const copiedDimensions = await page.evaluate(() => window.__completedCopyDimensions)
	assert(copiedDimensions?.width >= captureContract.widestTable, `Copied completion report truncates wide columns: ${JSON.stringify({ copiedDimensions, captureContract })}`)
	assert(copiedDimensions?.nonWhitePixels > 500, `Copied completion report is blank: ${JSON.stringify(copiedDimensions)}`)
	await completedDialog.locator(".p-dialog-footer").getByRole("button", { name: "Close", exact: true }).click()
	await page.setViewportSize({ width: 1600, height: 1000 })

	await page.setViewportSize({ width: 900, height: 760 })
	const compactHeaderContract = await headerActions.evaluate((element) => ({
		height: element.getBoundingClientRect().height,
		contained: element.getBoundingClientRect().right <= document.documentElement.clientWidth,
	}))
	assert(compactHeaderContract.height <= 40 && compactHeaderContract.contained, `Header actions do not stay compact at 900px: ${JSON.stringify(compactHeaderContract)}`)
	assert(await page.locator("html").evaluate((element) => element.scrollWidth <= element.clientWidth), "Action toolbar causes page-level horizontal overflow")

	const normalFixture = await findCuttingPlan(page.request, (data) =>
		normaliseItemGroups(data.completed_items).some((group) => !group.is_set_item && (group.items || []).some((item) => item.completed)),
	)
	await page.setViewportSize({ width: 1600, height: 1000 })
	await Promise.all([
		page.waitForResponse((response) => response.url().includes("get_web_view_data") && response.ok(), { timeout: 20_000 }),
		page.goto(`${SITE}/web/cutting/plans/${encodeURIComponent(normalFixture.name)}`, { waitUntil: "domcontentloaded" }),
	])
	await page.locator(".form-toolbar__actions").getByRole("button", { name: "More Actions", exact: true }).click()
	await page.getByRole("menuitem", { name: "Get Completed", exact: true }).click()
	const normalDialog = page.getByRole("dialog", { name: "Completed Cut Quantity", exact: true })
	await normalDialog.waitFor({ timeout: 10_000 })
	const normalGroup = normaliseItemGroups(normalFixture.data.completed_items).find((group) => !group.is_set_item && (group.items || []).some((item) => item.completed))
	const normalPanels = Array.from(normalGroup?.[normalGroup.stiching_attr] || [])
	assert(
		JSON.stringify(await normalDialog.locator(".completed-report__panel").allTextContents()) === JSON.stringify(normalPanels),
		"Normal-item completion report does not show its panels",
	)
	assert(
		await normalDialog.locator(".completed-report__item-row").count() === (normalGroup.items || []).filter((item) => item.completed).length,
		"Normal-item completion report includes incomplete rows or omits completed rows",
	)
	await normalDialog.locator(".p-dialog-footer").getByRole("button", { name: "Close", exact: true }).click()

	const emptyPage = await context.newPage()
	try {
		await emptyPage.route("**get_web_view_data*", (route) => route.fulfill({
			status: 200,
			contentType: "application/json",
			body: JSON.stringify({ message: { ...normalFixture.data, completed_items: [] } }),
		}))
		await emptyPage.goto(`${SITE}/web/cutting/plans/${encodeURIComponent(normalFixture.name)}`, { waitUntil: "domcontentloaded" })
		await emptyPage.locator(".form-toolbar__actions").getByRole("button", { name: "More Actions", exact: true }).click()
		await emptyPage.getByRole("menuitem", { name: "Get Completed", exact: true }).click()
		const emptyDialog = emptyPage.getByRole("dialog", { name: "Completed Cut Quantity", exact: true })
		await emptyDialog.getByText("No completed cut quantities", { exact: true }).waitFor({ timeout: 10_000 })
		assert(await emptyDialog.locator(".completed-report__table").count() === 0, "Empty Get Completed report renders an empty matrix")
	} finally {
		await emptyPage.close()
	}

	return { plan: fixture.name, normalPlan: normalFixture.name, menuActions: expectedMenuActions, compactHeaderContract, copiedDimensions }
}

async function planPrimaryTabsSuite(page) {
	await page.setViewportSize({ width: 1600, height: 1000 })
	const fixture = await openPlan(page, (data) =>
		groupItemCount(data.planned_detail?.item_detail) > 0 &&
		(data.cloth_details?.length || 0) > 0 &&
		(data.accessory_details?.length || 0) > 0,
	)

	const detailGrid = page.locator(".detail-read-grid")
	assert(await detailGrid.count() === 1, "Details does not use the compact read-only information grid")
	assert(await detailGrid.locator("input, button, .p-select").count() === 0, "Details still presents read-only values as disabled form controls")
	const detailColumnCount = await detailGrid.evaluate((element) => getComputedStyle(element).gridTemplateColumns.split(" ").filter(Boolean).length)
	assert(detailColumnCount === 4, `Details does not use a dense four-column desktop grid: ${detailColumnCount}`)
	const flatDetailLabels = await detailGrid.locator(".detail-read-field > span").allTextContents()
	for (const removedLabel of ["Lot", "Item", "CP Status", "Lay No"]) {
		assert(!flatDetailLabels.includes(removedLabel), `${removedLabel} is duplicated in the Details tab`)
	}
	for (const retainedLabel of ["Is Manual Entry", "Maximum No of Plys", "Maximum Allow Percent", "Piece Weight Tolerance (kg)", "Cutting Location", "Work Order", "No of Colours", "No of Colours Completed"]) {
		assert(flatDetailLabels.includes(retainedLabel), `Details is missing ${retainedLabel}`)
	}

	await page.locator(".cloth-requirement-group").first().waitFor({ timeout: 20_000 })
	const expectedClothGroups = new Set((fixture.data.cloth_details || []).map((row) => `${row.item || ""}\u0000${row.cloth_type || ""}`)).size
	const expectedAccessoryGroups = new Set((fixture.data.accessory_details || []).map((row) => `${row.accessory || ""}\u0000${row.item || ""}\u0000${row.cloth_type || ""}`)).size
	assert(await page.locator(".cloth-requirement-group").count() === expectedClothGroups, "Cloth rows are not grouped by template item and cloth type")
	assert(await page.locator(".accessory-requirement-group").count() === expectedAccessoryGroups, "Accessory rows are not grouped by accessory, template item, and cloth type")
	for (const sectionClass of ["cloth-details-section", "accessory-details-section"]) {
		const section = page.locator(`.${sectionClass}`)
		assert(await section.locator(".requirement-group__identity small").count() === 0, `${sectionClass} repeats an explanatory identity label`)
		const headings = await section.locator(".requirement-table th").first().locator("xpath=../th").allTextContents()
		assert(
			JSON.stringify(headings.map((label) => label.trim())) === JSON.stringify(["Colour", "Dia", "Required Weight", "Received Weight", "Used Weight", "Balance Weight"]),
			`${sectionClass} does not expose the low-dwell weight columns: ${JSON.stringify(headings)}`,
		)
		assert(await section.getByRole("columnheader", { name: "Cloth", exact: true }).count() === 0, `${sectionClass} still repeats the full variant name`)
	}

	await page.getByRole("tab", { name: "Summary", exact: true }).click()
	const summaryHeadings = await page.locator(".p-tabpanel[data-p-active='true'] .section-heading h3").allTextContents()
	for (const heading of ["Completed Cut Quantity", "Excess Cut Quantity", "Recut Summary", "Print Panel Summary"]) {
		assert(summaryHeadings.some((text) => text.includes(heading)), `Summary is missing ${heading}`)
	}
	const expectedCompletedSummaryRows = normaliseItemGroups(fixture.data.completed_items).reduce(
		(total, group) => total + (group.items || []).filter((item) => item.completed).length,
		0,
	)
	assert(
		await page.locator(".completed-quantity-section tbody tr:not(.total-row)").count() === expectedCompletedSummaryRows,
		"Completed Cut Quantity shows incomplete rows or omits completed rows",
	)
	const expectedExcessRows = normaliseItemGroups(fixture.data.incomplete_items).reduce(
		(total, group) => total + (group.items || []).filter((item) => Object.values(item.values || {}).some((value) => {
			if (value && typeof value === "object") return Object.values(value).some((quantity) => Number(quantity || 0) > 0)
			return Number(value || 0) > 0
		})).length,
		0,
	)
	assert(
		await page.locator(".excess-quantity-section tbody tr").count() === expectedExcessRows,
		"Excess Cut Quantity includes rows with no excess quantity or omits valid rows",
	)

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

	return { plan: fixture.name, detailColumnCount, summaryHeadings, totalNumberStyle, longIdContainment }
}

async function findEditableLaySheet(request, fixture) {
	const method = `${SITE}/api/method/essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet.sd_yrp_cutting_laysheet.get_web_laysheet`
	for (const summary of fixture.data.laysheets || []) {
		const response = await request.get(method, {
			params: { cutting_plan: fixture.name, cutting_laysheet: summary.name },
		})
		if (response.status() === 404) continue
		assert(response.ok(), `Unable to load Cutting LaySheet ${summary.name} (${response.status()})`)
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
	for (const selector of [".lay-number", ".rail-card__top strong", ".lay-meta", ".lay-status--prominent"]) {
		assert(await laySheet.locator(selector).count() === 1, `Lay Sheet card is missing ${selector}`)
	}
	assert(await laySheet.locator(".panel-summary").count() === 0, "Lay Sheet cards still repeat Marker Panels")
	const statusSignals = await page.locator(".laysheet-card").evaluateAll((cards) => cards.map((card) => {
		const status = card.querySelector(".lay-status--prominent")
		return {
			label: status?.textContent.trim(),
			fontSize: status ? Number.parseFloat(getComputedStyle(status).fontSize) : 0,
			cardClass: Array.from(card.classList).find((name) => name.startsWith("laysheet-card--status-")),
		}
	}))
	assert(
		statusSignals.every((signal) => signal.label && signal.fontSize >= 12 && signal.cardClass),
		`Lay Sheet workflow status is not prominent and contrasted: ${JSON.stringify(statusSignals)}`,
	)
	assert(await page.getByText("Label Pending", { exact: true }).count() === 0, "Lay Sheet cards still invent a Label Pending state")
	assert(await page.locator(".print-status-badge").count() === 0, "Lay Sheet cards still render a redundant print-state badge")
	const printMetaValues = await page.locator(".laysheet-card .print-state b").allTextContents()
	assert(printMetaValues.every((value) => /^\d{2}-\d{2}-\d{4} \d{2}:\d{2}$/.test(value.trim())), `Lay Sheet print metadata contains a synthetic state: ${JSON.stringify(printMetaValues)}`)
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
					can_read_recut: false,
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
		await restrictedPage.getByRole("tab", { name: "Summary", exact: true }).click()
		assert(await restrictedPage.getByRole("heading", { name: "Recut Summary", exact: true }).count() === 0, "Unreadable Recut Summary remains visible")
		assert(await restrictedPage.getByRole("heading", { name: "Print Panel Summary", exact: true }).count() === 0, "Unreadable Print Panel Summary remains visible")
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
	await page.setViewportSize({ width: 1600, height: 700 })
	let editableLaySheet = null
	const fixture = await openPlan(page, async (data, name) => {
		if (!(
			data.markers?.length
			&& data.laysheets?.length
			&& data.permissions?.can_start_marker
			&& data.permissions?.can_start_laysheet
		)) return false

		try {
			editableLaySheet = await findEditableLaySheet(page.request, { name, data })
			return true
		} catch {
			return false
		}
	})
	await page.locator(".marker-card").first().waitFor({ timeout: 20_000 })
	const initialUrl = page.url()

	await page.locator(".marker-section").getByRole("button", { name: "Create New", exact: true }).click()
	const markerDialog = page.getByRole("dialog", { name: "Create New Marker" })
	await markerDialog.waitFor()
	const markerMaximize = markerDialog.getByRole("button", { name: "Maximize dialog", exact: true })
	assert(await markerMaximize.count() === 1, "Marker dialog maximize control has no accessible name")
	assert(await markerMaximize.getAttribute("title") === "Maximize dialog", "Marker dialog maximize control has no visible tooltip")
	await markerMaximize.click()
	const markerRestore = markerDialog.getByRole("button", { name: "Restore dialog", exact: true })
	assert(await markerRestore.count() === 1, "Maximized Marker dialog does not expose a Restore dialog control")
	await markerRestore.click()
	assert(page.url() === initialUrl, "Opening a marker dialog navigates away from the Cutting Plan")
	await page.locator(".p-dialog-mask").click({ position: { x: 4, y: 4 } })
	await markerDialog.waitFor({ state: "hidden" })

	await page.locator(".laysheet-section").getByRole("button", { name: "Create New", exact: true }).click()
	const createDialog = page.getByRole("dialog", { name: "Create Lay Sheet" })
	await createDialog.waitFor()
	const laySheetMaximize = createDialog.getByRole("button", { name: "Maximize dialog", exact: true })
	assert(await laySheetMaximize.count() === 1, "Lay Sheet dialog maximize control has no accessible name")
	assert(await laySheetMaximize.getAttribute("title") === "Maximize dialog", "Lay Sheet dialog maximize control has no visible tooltip")
	await laySheetMaximize.click()
	const laySheetRestore = createDialog.getByRole("button", { name: "Restore dialog", exact: true })
	assert(await laySheetRestore.count() === 1, "Maximized Lay Sheet dialog does not expose a Restore dialog control")
	await laySheetRestore.click()
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
	if (await existingMarkerDialog.getByText("Submitted", { exact: true }).count()) {
		assert(await existingMarkerDialog.locator("input:disabled, .p-disabled input").count() === 0, "Submitted Marker is rendered as a disabled editor instead of a readable view")
		assert(
			/^Updated \d{2}-\d{2}-\d{4} · \d{2}:\d{2}$/.test((await existingMarkerDialog.locator(".modified-text").textContent())?.trim() || ""),
			"Marker modified time is not formatted for users",
		)
	}
	await page.setViewportSize({ width: 390, height: 844 })
	const markerMobileColumns = await existingMarkerDialog.locator(".marker-read-grid").evaluate((element) => getComputedStyle(element).gridTemplateColumns.split(" ").filter(Boolean).length)
	assert(markerMobileColumns === 2, `Marker facts do not retain a compact two-column mobile grid: ${markerMobileColumns}`)
	assert(await existingMarkerDialog.getByRole("button", { name: "Maximize dialog", exact: true }).isHidden(), "Redundant dialog maximize control remains visible on mobile")
	await page.setViewportSize({ width: 1600, height: 700 })
	await existingMarkerDialog.locator(".p-dialog-footer").getByRole("button", { name: "Close", exact: true }).click()

	const sheet = editableLaySheet
	assert(sheet, "The selected dialog fixture has no editable Lay Sheet")
	await page.locator(".laysheet-card").filter({ hasText: sheet.name }).click()
	const laySheetDialog = page.getByRole("dialog", { name: new RegExp(sheet.name) })
	await laySheetDialog.waitFor()
	const laySheetTabList = laySheetDialog.locator(".p-tablist")
	assert(await laySheetTabList.evaluate((element) => getComputedStyle(element).position) === "sticky", "Lay Sheet tabs do not remain fixed while dialog data scrolls")
	await laySheetDialog.getByRole("tab", { name: "Details", exact: true }).click()
	for (const duplicateLabel of ["Cutting Marker", "Marker Name", "Lay No"]) {
		assert(await laySheetDialog.locator(".detail-grid > div > span").filter({ hasText: new RegExp(`^${duplicateLabel}$`) }).count() === 0, `Lay Sheet Details repeats ${duplicateLabel} already shown in the identity header`)
	}
	await laySheetDialog.getByRole("tab", { name: "Cloth Details", exact: true }).click()
	assert(await laySheetDialog.getByRole("button", { name: "Add Cloth", exact: true }).count() === 1, "Permitted Add Cloth action is missing")
	assert(await laySheetDialog.getByRole("button", { name: "Add Accessory", exact: true }).count() === 1, "Permitted Add Accessory action is missing")
	const materialActionColours = await laySheetDialog.getByRole("button", { name: /Add Cloth|Add Accessory/ }).evaluateAll((buttons) => buttons.map((button) => {
		const buttonColour = getComputedStyle(button).color
		const label = button.querySelector(".p-button-label")
		const icon = button.querySelector(".p-button-icon")
		return {
			label: button.textContent.trim(),
			buttonColour,
			labelColour: label ? getComputedStyle(label).color : buttonColour,
			iconColour: icon ? getComputedStyle(icon).color : buttonColour,
		}
	}))
	assert(
		materialActionColours.every(({ buttonColour, labelColour, iconColour }) => labelColour === buttonColour && iconColour === buttonColour),
		`Lay Sheet material action text/icon does not inherit the button contrast colour: ${JSON.stringify(materialActionColours)}`,
	)
	const expectedLaySheetClothGroups = new Set((sheet.cloth_details || []).map((row) => `${row.item || row.cloth_item_variant || ""}\u0000${row.cloth_type || ""}`)).size
	const laySheetClothGroups = laySheetDialog.locator(".laysheet-material-groups--cloth .material-requirement-group")
	assert(await laySheetClothGroups.count() === expectedLaySheetClothGroups, "Lay Sheet cloth rows are not grouped by Item and Cloth Type")
	assert(await laySheetDialog.locator(".laysheet-material-groups--cloth").getByRole("columnheader", { name: "Cloth", exact: true }).count() === 0, "Lay Sheet repeats the full cloth variant in every row")
	assert(await laySheetDialog.locator(".laysheet-material-groups--cloth").getByRole("columnheader", { name: "Cloth Type", exact: true }).count() === 0, "Lay Sheet repeats Cloth Type in every row")
	const laySheetTableScrolls = await laySheetDialog.locator(".material-requirement-table-wrap").evaluateAll((elements) => elements.map((element) => ({ clientHeight: element.clientHeight, scrollHeight: element.scrollHeight })))
	assert(laySheetTableScrolls.every(({ clientHeight, scrollHeight }) => scrollHeight <= clientHeight + 1), `Lay Sheet material tables have nested vertical scrolling: ${JSON.stringify(laySheetTableScrolls)}`)
	const laySheetScrollSemantics = await laySheetDialog.locator(".material-requirement-table-wrap").evaluateAll((elements) => elements.map((element) => ({ role: element.getAttribute("role"), tabIndex: element.tabIndex, label: element.getAttribute("aria-label") })))
	assert(laySheetScrollSemantics.every(({ role, tabIndex, label }) => role === "region" && tabIndex === 0 && Boolean(label)), `Lay Sheet material tables are not named keyboard-scroll regions: ${JSON.stringify(laySheetScrollSemantics)}`)
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
	await laySheetDialog.getByRole("button", { name: "Delete cloth" }).first().click()
	const deleteClothConfirmation = page.getByRole("alertdialog", { name: "Delete cloth detail?" })
	await deleteClothConfirmation.waitFor()
	const keepClothButton = deleteClothConfirmation.getByRole("button", { name: "Keep Cloth", exact: true })
	assert(await keepClothButton.evaluate((element) => element === document.activeElement), "Lay Sheet delete confirmation does not focus its safe action")
	assert(await laySheetDialog.locator(".editable-data-block").first().locator("tbody tr").count() === rowsBefore, "Lay Sheet delete ran before confirmation")
	await deleteClothConfirmation.getByRole("button", { name: "Delete Cloth", exact: true }).click()
	await laySheetDialog.getByText("Cloth detail deleted.", { exact: true }).waitFor({ timeout: 10_000 })
	const rowsAfter = await laySheetDialog.locator(".editable-data-block").first().locator("tbody tr").count()
	assert(rowsAfter === rowsBefore - 1, `Delete success did not remove the rendered row: ${rowsBefore} -> ${rowsAfter}`)
	await page.setViewportSize({ width: 390, height: 844 })
	const laySheetMobileOverflow = await laySheetDialog.locator(".p-dialog-content").evaluate((element) => ({ clientWidth: element.clientWidth, scrollWidth: element.scrollWidth }))
	assert(laySheetMobileOverflow.scrollWidth <= laySheetMobileOverflow.clientWidth + 1, `Lay Sheet tab strip leaks horizontal overflow into the mobile dialog: ${JSON.stringify(laySheetMobileOverflow)}`)
	assert(await laySheetDialog.getByRole("tab", { name: "Bundles", exact: true }).count() === 1, "Lay Sheet Bundles tab is clipped on mobile")
	const mobileEntityDialog = await laySheetDialog.evaluate((element) => {
		const box = element.getBoundingClientRect()
		return { width: box.width, height: box.height, x: box.x, y: box.y, borderRadius: getComputedStyle(element).borderRadius }
	})
	assert(mobileEntityDialog.width === 390 && mobileEntityDialog.height === 844 && mobileEntityDialog.x === 0 && mobileEntityDialog.y === 0 && mobileEntityDialog.borderRadius === "0px", `Cutting entity dialog does not use the shared mobile surface: ${JSON.stringify(mobileEntityDialog)}`)
	await laySheetDialog.getByRole("tab", { name: "Details", exact: true }).click()
	const laySheetMobileColumns = await laySheetDialog.locator(".detail-grid").evaluate((element) => getComputedStyle(element).gridTemplateColumns.split(" ").filter(Boolean).length)
	assert(laySheetMobileColumns === 2, `Lay Sheet facts do not retain a compact two-column mobile grid: ${laySheetMobileColumns}`)

	return { plan: fixture.name, sheet: sheet.name, dialogScrollContract, rowsBefore, rowsAfter, markerMobileColumns, laySheetMobileColumns }
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
		role: element.getAttribute("role"),
		tabIndex: element.tabIndex,
		label: element.getAttribute("aria-label"),
	}))
	assert(matrixScroll.scrollWidth >= matrixScroll.clientWidth && ["auto", "scroll"].includes(matrixScroll.overflowX), "CPM matrix does not preserve horizontal scrolling")
	assert(matrixScroll.role === "region" && matrixScroll.tabIndex === 0 && Boolean(matrixScroll.label), `CPM matrix is not a named keyboard-scroll region: ${JSON.stringify(matrixScroll)}`)
	const secondaryScrollSemantics = await dialog.locator(".erp-table-scroll").evaluateAll((elements) => elements.map((element) => ({ role: element.getAttribute("role"), tabIndex: element.tabIndex, label: element.getAttribute("aria-label") })))
	assert(secondaryScrollSemantics.every(({ role, tabIndex, label }) => role === "region" && tabIndex === 0 && Boolean(label)), `CPM secondary tables are not named keyboard-scroll regions: ${JSON.stringify(secondaryScrollSemantics)}`)

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

async function selectAutocompleteOption(page, field, value) {
	const input = field.locator(".p-autocomplete-input")
	await input.fill(value)
	const option = page.locator(".p-autocomplete-option:visible").filter({ hasText: value }).first()
	await option.waitFor({ timeout: 20_000 })
	await option.click()
}

async function stockTransfersSuite(page, context) {
	await page.setViewportSize({ width: 1600, height: 760 })
	const fixture = await findCuttingPlan(page.request, (_, name) => name === "CP-2609-00042")
	const cpmMethod = "essdee_yrp.cutting.web_workspace."
	const workspace = await getMethodFixture(page.request, `${cpmMethod}get_workspace`, { cutting_plan: fixture.name })

	await page.goto(`${SITE}/web/cutting/plans/${encodeURIComponent(fixture.name)}`, { waitUntil: "domcontentloaded" })
	await page.locator(".cutting-tabs").waitFor({ timeout: 20_000 })
	await page.getByRole("tab", { name: "Stock Transfers", exact: true }).click()
	const transfers = page.locator(".erp-transfer-workspace")
	await transfers.getByRole("heading", { name: "Stock Transfers", exact: true }).waitFor({ timeout: 20_000 })

	const operationCards = transfers.locator(".erp-activity-card")
	assert(await operationCards.count() === 5, "Stock Transfers must expose exactly five operation cards")
	assert(await transfers.locator(".p-tablist").count() === 0, "Duplicate operation tabs remain below the operation cards")
	const operationLabels = ["Stock Entry", "Stock Update", "Stock Reconciliation", "Lot Transfer", "Delivery Challan"]
	for (const label of operationLabels) {
		assert(await operationCards.filter({ hasText: label }).count() === 1, `Operation card is missing ${label}`)
	}

	const stockEntryCard = operationCards.filter({ hasText: "Stock Entry" })
	await stockEntryCard.click()
	assert(await transfers.getByRole("heading", { name: "Stock Entry", exact: true }).count() === 0, "Active operation heading is duplicated")
	const transactionCard = transfers.locator(".erp-transaction-card").first()
	if (await transactionCard.count()) {
		for (const selector of ["strong", "small", ".erp-status"]) assert(await transactionCard.locator(selector).count() > 0, `Transaction card is missing ${selector}`)
		const transactionMeta = await transfers.locator(".erp-transaction-card small").allTextContents()
		assert(transactionMeta.every((value) => /\d{2}-\d{2}-\d{4}/.test(value)), `Transaction dates are not clear: ${transactionMeta}`)
	}
	const workspaceUndersizedText = await visibleTextBelowMinimum(transfers)
	assert(workspaceUndersizedText.length === 0, `Stock Transfers workspace contains text below 11px: ${JSON.stringify(workspaceUndersizedText.slice(0, 8))}`)

	await transfers.getByRole("button", { name: "Plan Stock Entry", exact: true }).click()
	const stockEntryDialog = page.getByRole("dialog", { name: "Create Stock Entry" })
	await stockEntryDialog.waitFor()
	const purpose = stockEntryDialog.locator(".erp-operation-fields .p-select")
	await purpose.waitFor({ timeout: 20_000 })
	assert(await purpose.count() === 1, "Stock Entry Purpose is not a Select")
	await purpose.click()
	const purposeOptions = await page.locator(".p-select-overlay:visible .p-select-option").allTextContents()
	assert(JSON.stringify(purposeOptions) === JSON.stringify(["Material Issue", "Material Consumed", "Send to Warehouse"]), `Purpose options differ: ${purposeOptions}`)
	await page.keyboard.press("Escape")

	const itemField = stockEntryDialog.locator(".stock-composer__fields .common-field").filter({ hasText: "Item *" })
	const getItemButton = stockEntryDialog.getByRole("button", { name: "Get Item", exact: true })
	const [itemOrder, buttonOrder] = await Promise.all([
		itemField.evaluate((element) => Array.from(element.parentElement.children).indexOf(element)),
		getItemButton.evaluate((element) => Array.from(element.closest(".stock-composer__fields").children).indexOf(element.closest(".stock-composer__fetch"))),
	])
	assert(itemOrder < buttonOrder, "Item does not precede Get Item")
	await selectAutocompleteOption(page, itemField, "Test Item 1")
	await getItemButton.click()
	await stockEntryDialog.locator(".stock-composer__attribute-grid").waitFor({ timeout: 20_000 })
	const stageField = stockEntryDialog.locator(".stock-composer__attribute-grid .common-field").first()
	await selectAutocompleteOption(page, stageField, "Pack")
	await stockEntryDialog.locator(".stock-composer__quantity-grid").waitFor()
	assert(await stockEntryDialog.locator(".stock-composer__quantity-cell").count() >= 2, "Primary attribute values are not separated into quantity columns")
	assert(await stockEntryDialog.locator(".stock-composer__attribute-grid .common-field").count() >= 1, "Item attributes are not separated from primary values")
	await stockEntryDialog.locator(".p-dialog-footer").getByRole("button", { name: "Close", exact: true }).click()

	await operationCards.filter({ hasText: "Stock Update" }).click()
	await transfers.getByRole("button", { name: "New Stock Update", exact: true }).click()
	const updateDialog = page.getByRole("dialog", { name: "Create Stock Update" })
	await updateDialog.waitFor()
	const updateType = updateDialog.locator(".erp-operation-fields .p-select")
	await updateType.waitFor({ timeout: 20_000 })
	await updateType.click()
	const updateOptions = await page.locator(".p-select-overlay:visible .p-select-option").allTextContents()
	assert(updateOptions.includes("Add") && updateOptions.includes("Reduce"), `Stock Update does not support Add and Reduce: ${updateOptions}`)
	await page.keyboard.press("Escape")
	await updateDialog.locator(".p-dialog-footer").getByRole("button", { name: "Close", exact: true }).click()

	await operationCards.filter({ hasText: "Stock Reconciliation" }).click()
	await transfers.getByRole("button", { name: "New Reconciliation", exact: true }).click()
	const reconciliationDialog = page.getByRole("dialog", { name: "Create Stock Reconciliation" })
	await reconciliationDialog.waitFor()
	const reconciliationItem = reconciliationDialog.locator(".stock-composer__fields .common-field").filter({ hasText: "Item *" })
	await selectAutocompleteOption(page, reconciliationItem, "Test Item 1")
	await reconciliationDialog.getByRole("button", { name: "Get Item", exact: true }).click()
	await reconciliationDialog.locator(".stock-composer__attribute-grid").waitFor({ timeout: 20_000 })
	await selectAutocompleteOption(page, reconciliationDialog.locator(".stock-composer__attribute-grid .common-field").first(), "Pack")
	await reconciliationDialog.locator(".stock-composer__quantity-grid input").first().fill("0")
	await reconciliationDialog.getByRole("button", { name: "OK · Add Item", exact: true }).click()
	await reconciliationDialog.locator(".stock-composer__table-card").waitFor({ timeout: 10_000 })
	assert(await reconciliationDialog.locator(".stock-composer__total").first().textContent() === "0", "Zero-quantity reconciliation was not staged")
	const stagedItemTreatment = await reconciliationDialog.locator(".stock-composer tbody td > strong").first().evaluate((element) => {
		const style = getComputedStyle(element)
		return { overflow: style.overflow, textOverflow: style.textOverflow, whiteSpace: style.whiteSpace }
	})
	assert(stagedItemTreatment.overflow === "hidden" && stagedItemTreatment.textOverflow === "ellipsis", `Long staged item names are not contained: ${JSON.stringify(stagedItemTreatment)}`)
	const scrollContract = await reconciliationDialog.evaluate((dialog) => {
		const content = dialog.querySelector(".p-dialog-content")
		const footer = dialog.querySelector(".p-dialog-footer")
		return {
			contentOverflow: getComputedStyle(content).overflowY,
			footerVisible: footer.getBoundingClientRect().bottom <= dialog.getBoundingClientRect().bottom + 1,
		}
	})
	assert(["auto", "scroll"].includes(scrollContract.contentOverflow) && scrollContract.footerVisible, `Stock dialog scroll contract failed: ${JSON.stringify(scrollContract)}`)
	await reconciliationDialog.locator(".p-dialog-footer").getByRole("button", { name: "Close", exact: true }).click()

	await operationCards.filter({ hasText: "Lot Transfer" }).click()
	await transfers.getByRole("button", { name: "New Lot Transfer", exact: true }).click()
	const lotDialog = page.getByRole("dialog", { name: "Create Lot Transfer" })
	await lotDialog.waitFor()
	await lotDialog.getByText("From Lot *", { exact: true }).waitFor({ timeout: 20_000 })
	assert(await lotDialog.getByText("From Lot *", { exact: true }).count() === 1 && await lotDialog.getByText("To Lot *", { exact: true }).count() === 1, "Lot Transfer does not expose from/to lot dimensions")
	await lotDialog.locator(".p-dialog-footer").getByRole("button", { name: "Close", exact: true }).click()

	await operationCards.filter({ hasText: "Delivery Challan" }).click()
	assert(await transfers.getByRole("button", { name: "From CPM", exact: true }).count() === 1, "Movement-based Delivery Challan path is missing")
	await transfers.getByRole("button", { name: "From Work Order", exact: true }).click()
	const deliveryDialog = page.getByRole("dialog", { name: "Create Delivery Challan from Work Order" })
	await deliveryDialog.waitFor()
	await deliveryDialog.locator(".wo-delivery-matrix").first().waitFor({ timeout: 20_000 })
	assert(await deliveryDialog.getByLabel("Delivery Quantity").count() > 0, "Work Order delivery does not expose quantity entry")
	await page.setViewportSize({ width: 390, height: 844 })
	const mobileDeliveryEntry = await deliveryDialog.locator(".wo-delivery-matrix__scroll").first().evaluate((scroller) => {
		const input = scroller.querySelector('input[aria-label="Delivery Quantity"]')
		const scrollerBox = scroller.getBoundingClientRect()
		const inputBox = input?.getBoundingClientRect()
		return { scroller: scrollerBox.toJSON(), input: inputBox?.toJSON(), scrollLeft: scroller.scrollLeft }
	})
	assert(mobileDeliveryEntry.input && mobileDeliveryEntry.scrollLeft === 0 && mobileDeliveryEntry.input.left >= mobileDeliveryEntry.scroller.left && mobileDeliveryEntry.input.right <= mobileDeliveryEntry.scroller.right, `The first Work Order delivery input starts off-screen on mobile: ${JSON.stringify(mobileDeliveryEntry)}`)
	const mobileDeliveryAttributes = await deliveryDialog.locator(".wo-delivery-matrix__mobile-attributes").first().evaluate((element) => ({ display: getComputedStyle(element).display, text: element.textContent?.trim() }))
	assert(mobileDeliveryAttributes.display !== "none" && mobileDeliveryAttributes.text, `Hidden Work Order delivery attributes are not summarized on mobile: ${JSON.stringify(mobileDeliveryAttributes)}`)
	await page.setViewportSize({ width: 1600, height: 900 })
	await deliveryDialog.locator(".p-dialog-footer").getByRole("button", { name: "Close", exact: true }).click()

	const restrictedPage = await context.newPage()
	try {
		await restrictedPage.route("**cutting.web_workspace.get_workspace*", (route) => route.fulfill({
			status: 200,
			contentType: "application/json",
			body: JSON.stringify({ message: {
				...workspace,
				permissions: { ...workspace.permissions, stock_update: { ...workspace.permissions.stock_update, can_create: false } },
			} }),
		}))
		await restrictedPage.goto(`${SITE}/web/cutting/plans/${encodeURIComponent(fixture.name)}`, { waitUntil: "domcontentloaded" })
		await restrictedPage.getByRole("tab", { name: "Stock Transfers", exact: true }).click()
		await restrictedPage.locator(".erp-transfer-workspace .erp-activity-card").filter({ hasText: "Stock Update" }).click()
		assert(await restrictedPage.getByRole("button", { name: "New Stock Update", exact: true }).count() === 0, "Disallowed Stock Update create action remains visible")
	} finally {
		await restrictedPage.close()
	}

	return { plan: fixture.name, operationLabels, purposeOptions, updateOptions, stagedItemTreatment, scrollContract }
}

function productionReportFixture() {
	return {
		bundle_generated: 4,
		label_printed: 3,
		created: 2,
		report_data: [{
			style_no: "Flame Thermal Pyjama Womens Extra Long Enterprise Style Name",
			lot_no: "LOT-2026-09-VERY-LONG-TRACEABILITY-NAME",
			location: "Machine Cutting",
			attributes: ["Colour"],
			primary_attribute_values: ["S", "M"],
			total_sum: 8,
			total_planned_sum: 10,
			total_received_sum: 8,
			items: [{ attributes: { Colour: "Navy" }, cutter: "Cutter One", values: { S: 3, M: 5 }, total_qty: 8, planned: 10, cumulative: 8 }],
		}],
	}
}

function completionReportFixture() {
	return [{
		attributes: ["Colour"],
		primary_attribute_values: ["S", "M"],
		is_set_item: false,
		stiching_attr: "panels",
		panels: ["Front", "Back"],
		total_qty: { S: 3, M: 2 },
		items: [{ attributes: { Colour: "Navy" }, values: { S: 3, M: 2 }, total_qty: 5 }],
	}]
}

async function reportsSuite(page) {
	const sharedStockReportPath = "frontend/src/components/reports/StockBalanceReport.vue"
	const sharedStockApiPath = "frontend/src/api/stockReports.js"
	assert(existsSync(sharedStockReportPath), "Stock Balance is not a shared report component")
	assert(existsSync(sharedStockApiPath), "Stock Balance API is not shared outside Cutting")
	const cuttingReportsSource = readFileSync("frontend/src/departments/CuttingReports.vue", "utf8")
	const sharedStockSource = readFileSync(sharedStockReportPath, "utf8")
	const sharedStockApiSource = readFileSync(sharedStockApiPath, "utf8")
	assert(
		cuttingReportsSource.includes('../components/reports/StockBalanceReport.vue'),
		"Cutting does not consume the shared Stock Balance component",
	)
	assert(sharedStockSource.includes('DateField'), "Shared Stock Balance does not use the custom Date field")
	assert(sharedStockSource.includes('@generate="generate"'), "Shared Stock Balance is not generated on command")
	for (const filterName of ["from_date", "to_date", "parent_item", "remove_zero_balance_item", "show_variant_attributes", "show_stock_ageing_data", "show_inward_date_split"]) {
		assert(sharedStockSource.includes(filterName), `Shared Stock Balance changed API filter ${filterName}`)
	}
	assert(sharedStockApiSource.includes('report_name: "YRP Stock Balance"'), "Shared Stock Balance API changed the report contract")

	await page.setViewportSize({ width: 1600, height: 1000 })
	const calls = { production: 0, cutSheet: 0, multiCcr: 0, detail: 0, stock: 0 }
	const requestedDates = { production: "", cutSheet: "" }
	let emptyStockResult = false
	const production = productionReportFixture()
	const completion = completionReportFixture()
	const clothRows = [{ cloth_item_variant: "Fabric-Navy-68 Dia", cloth_type: "Main Fabric", colour: "Navy", dia: "68 Dia", required_weight: 4.2, weight: 5, used_weight: 4.1, balance_weight: 0.9 }]
	const clothTotal = { required: 4.2, received: 5, used: 4.1, balance: 0.9 }

	await page.route("**/api/method/essdee_yrp.cutting.reports.get_report_permissions*", (route) => route.fulfill({
		status: 200,
		contentType: "application/json",
		body: JSON.stringify({ message: {
			"cutting-plans": true,
			"daily-production": true,
			"daily-cut-sheet": true,
			"multi-ccr": true,
			"cutting-detail": true,
			"stock-balance": true,
		} }),
	}))
	await page.route("**/api/method/essdee_yrp.cutting.reports.get_daily_production_report*", (route) => {
		calls.production += 1
		requestedDates.production = JSON.parse(route.request().postData() || "{}").date || ""
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: production }) })
	})
	await page.route("**/api/method/essdee_yrp.cutting.reports.get_cut_sheet_report*", (route) => {
		calls.cutSheet += 1
		requestedDates.cutSheet = JSON.parse(route.request().postData() || "{}").date || ""
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: [{
			style_no: production.report_data[0].style_no,
			lot_no: production.report_data[0].lot_no,
			location: "Machine Cutting",
			attributes: ["Colour"],
			primary_attribute_values: ["S", "M"],
			items: [{ attributes: { Colour: "Navy" }, cutter: "Cutter One", values: { S: { Front: 3, Back: 3 }, M: { Front: 2, Back: 2 } }, total_panel_qty: { Front: 5, Back: 5 } }],
		}] }) })
	})
	await page.route("**/api/method/essdee_yrp.cutting.reports.get_multiccr*", (route) => {
		calls.multiCcr += 1
		const itemName = production.report_data[0].style_no
		const lotName = production.report_data[0].lot_no
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: {
			output_lots: [lotName],
			output_items: [itemName],
			item_data: { [itemName]: { total_qty: 5, completed_json: completion, cloth_details: clothRows, cloth_total: clothTotal, average_piece_weight_by_colour: { Navy: 0.1 }, average_required_weight_by_colour: { Navy: 0.11 } } },
			data: { [lotName]: { item: itemName, total_qty: 5, completed_json: completion, cloth_details: clothRows, cloth_total: clothTotal, panel_groups: [{ panels: "Front, Back", cutting_plan: "CP-2609-00042", sizes: ["S", "M"], rows: [{ colour: "Navy", cloth_type: "Main Fabric", received_weight: 5, used_weight: 4.1, balance_weight: 0.9, sizes: { S: 3, M: 2 }, total_pieces: 5, piece_weight: 0.1, required_weight: 0.5 }], totals: { received_weight: 5, used_weight: 4.1, balance_weight: 0.9, sizes: { S: 3, M: 2 }, total_pieces: 5, piece_weight: 0.1, required_weight: 0.5 } }] } },
		} }) })
	})
	await page.route("**/api/method/essdee_yrp.cutting.reports.get_cutting_detail_report*", (route) => {
		calls.detail += 1
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: production }) })
	})
	await page.route("**/api/method/frappe.desk.query_report.run*", (route) => {
		calls.stock += 1
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: {
			columns: [
				{ fieldname: "item_code", label: "Item", fieldtype: "Link" },
				{ fieldname: "lot", label: "Lot", fieldtype: "Link" },
				{ fieldname: "in_qty", label: "In Qty", fieldtype: "Float" },
				{ fieldname: "out_qty", label: "Out Qty", fieldtype: "Float" },
				{ fieldname: "bal_qty", label: "Balance Qty", fieldtype: "Float" },
			],
			result: emptyStockResult ? [] : [{ item_code: production.report_data[0].style_no, lot: production.report_data[0].lot_no, in_qty: 10, out_qty: 2, bal_qty: 8 }],
		} }) })
	})

	async function assertSharedReportResult(shell, reportName) {
		assert(await shell.locator(".report-metric").count() >= 4, `${reportName} summary strip is missing`)
		const header = shell.locator("table thead th").first()
		assert(await header.evaluate((element) => getComputedStyle(element).position) === "sticky", `${reportName} table headers are not sticky`)
		const wrap = shell.locator(".erp-table-wrap, .production-table-wrap").first()
		const containment = await wrap.evaluate((element) => ({ overflowX: getComputedStyle(element).overflowX, clientWidth: element.clientWidth, scrollWidth: element.scrollWidth }))
		assert(["auto", "scroll"].includes(containment.overflowX) && containment.scrollWidth >= containment.clientWidth, `${reportName} table is not horizontally contained: ${JSON.stringify(containment)}`)
		const undersized = await visibleTextBelowMinimum(shell)
		assert(undersized.length === 0, `${reportName} contains text below 11px: ${JSON.stringify(undersized.slice(0, 12))}`)
		return containment
	}

	await page.goto(`${SITE}/web/cutting/reports`, { waitUntil: "domcontentloaded" })
	await page.locator(".report-tabs__list").waitFor({ timeout: 20_000 })
	const tabs = page.getByRole("tab")
	const expectedTabs = ["Daily Production", "Daily Cut Sheet", "Multi CCR", "Cutting Detail", "Stock Balance"]
	assert(await tabs.count() === 5, `Expected five report tabs, found ${await tabs.count()}`)
	assert(JSON.stringify(await tabs.allTextContents()) === JSON.stringify(expectedTabs), `Unexpected report tabs: ${await tabs.allTextContents()}`)
	assert(await page.getByText("Manufacturing intelligence", { exact: true }).count() === 0, "Decorative reports introduction is visible")
	assert(await page.locator(".report-shell h1, .report-shell h2").count() === 0, "Report title is duplicated inside the active tab")
	assert(await page.locator(".report-tabs__list").evaluate((element) => getComputedStyle(element).position) === "sticky", "Report tabs are not fixed")

	for (const tabName of expectedTabs) {
		await tabs.filter({ hasText: tabName }).click()
		const shell = page.locator(".report-shell:visible")
		await shell.waitFor()
		assert(await shell.locator('input[type="date"], input[type="time"], input[type="datetime-local"]').count() === 0, `${tabName} still uses a browser-native date or time input`)
		assert(await shell.getByText("Set the report filters", { exact: true }).isVisible(), `${tabName} does not have an intentional initial state`)
		assert(await shell.getByRole("button", { name: "Generate", exact: true }).count() === 1, `${tabName} has no explicit Generate action`)
	}
	assert(Object.values(calls).every((count) => count === 0), `Reports requested data before Generate: ${JSON.stringify(calls)}`)

	await tabs.filter({ hasText: "Daily Production" }).click()
	let shell = page.locator(".report-shell:visible")
	const productionDate = shell.getByRole("combobox", { name: "Date", exact: true })
	assert(await productionDate.count() === 1, "Daily Production does not expose an accessible shared date picker")
	const expectedToday = await page.evaluate(() => {
		const today = new Date()
		const pad = (value) => String(value).padStart(2, "0")
		return `${pad(today.getDate())}-${pad(today.getMonth() + 1)}-${today.getFullYear()}`
	})
	assert(await productionDate.inputValue() === expectedToday, `Daily Production date does not default to today in DD-MM-YYYY format: ${await productionDate.inputValue()}`)
	await productionDate.click()
	const datePanel = page.locator(".erp-date-time-panel:visible")
	await datePanel.waitFor()
	const panelContract = await datePanel.evaluate((element) => {
		const style = getComputedStyle(element)
		const selected = element.querySelector(".p-datepicker-day-selected")
		const selectedStyle = selected ? getComputedStyle(selected) : null
		const rect = element.getBoundingClientRect()
		return {
			borderRadius: style.borderRadius,
			background: style.backgroundColor,
			selectedBackground: selectedStyle?.backgroundColor || "",
			selectedColor: selectedStyle?.color || "",
			viewportContained: rect.left >= 0 && rect.right <= window.innerWidth,
		}
	})
	assert(
		panelContract.borderRadius === "14px"
			&& panelContract.background === "rgb(255, 255, 255)"
			&& panelContract.selectedBackground === "rgb(5, 150, 105)"
			&& panelContract.selectedColor === "rgb(255, 255, 255)"
			&& panelContract.viewportContained,
		`Shared date panel is not using the isolated ERP presentation: ${JSON.stringify(panelContract)}`,
	)
	await page.keyboard.press("Escape")
	await productionDate.fill("24-09-2026")
	await productionDate.press("Tab")
	await shell.getByRole("button", { name: "Generate", exact: true }).click()
	await shell.locator(".production-card").waitFor()
	assert(requestedDates.production === "2026-09-24", `Daily Production changed the API date contract: ${requestedDates.production}`)
	assert(await shell.getByText("24-09-2026", { exact: true }).count() >= 1, "Daily Production date is not DD-MM-YYYY")
	assert(await shell.getByRole("button", { name: "Copy Report", exact: true }).count() === 1, "Daily Production Copy Report is missing")
	await assertSharedReportResult(shell, "Daily Production")
	const productionTotal = await shell.locator(".production-table tfoot td").first().evaluate((element) => ({ fontWeight: Number(getComputedStyle(element).fontWeight), background: getComputedStyle(element).backgroundColor }))
	assert(productionTotal.fontWeight >= 700 && productionTotal.background !== "rgba(0, 0, 0, 0)", `Daily Production total row is not emphasized: ${JSON.stringify(productionTotal)}`)

	const longNameTreatment = await shell.locator(".production-card__identity h3").evaluate((element) => {
		const style = getComputedStyle(element)
		return { overflow: style.overflow, textOverflow: style.textOverflow, whiteSpace: style.whiteSpace }
	})
	assert(longNameTreatment.overflow === "hidden" && longNameTreatment.textOverflow === "ellipsis", `Long report names are not contained: ${JSON.stringify(longNameTreatment)}`)

	await tabs.filter({ hasText: "Daily Cut Sheet" }).click()
	shell = page.locator(".report-shell:visible")
	const cutSheetDate = shell.getByRole("combobox", { name: "Date", exact: true })
	assert(await cutSheetDate.count() === 1, "Daily Cut Sheet does not expose an accessible shared date picker")
	await cutSheetDate.fill("24-09-2026")
	await cutSheetDate.press("Tab")
	await shell.getByRole("button", { name: "Generate", exact: true }).click()
	await shell.locator(".cut-sheet-card").waitFor()
	assert(requestedDates.cutSheet === "2026-09-24", `Daily Cut Sheet changed the API date contract: ${requestedDates.cutSheet}`)
	assert(await shell.getByText("24-09-2026", { exact: true }).count() === 1, "Daily Cut Sheet date is not DD-MM-YYYY")
	assert(await shell.getByRole("button", { name: "Copy Report", exact: true }).count() === 1, "Daily Cut Sheet Copy Report is missing")
	await assertSharedReportResult(shell, "Daily Cut Sheet")

	for (const tabName of ["Multi CCR", "Cutting Detail", "Stock Balance"]) {
		await tabs.filter({ hasText: tabName }).click()
		shell = page.locator(".report-shell:visible")
		await shell.getByRole("button", { name: "Generate", exact: true }).click()
		await shell.locator(".report-shell__results").waitFor()
		assert(await shell.getByRole("button", { name: "Copy Report", exact: true }).count() === 0, `${tabName} unexpectedly exposes Copy Report`)
		await assertSharedReportResult(shell, tabName)
	}

	assert(Object.values(calls).every((count) => count === 1), `Expected one request per report: ${JSON.stringify(calls)}`)
	const activeShell = page.locator(".report-shell:visible")
	const tableHeader = activeShell.locator("table thead th").first()
	const numericCell = activeShell.locator("tbody .erp-number").first()
	assert(await numericCell.evaluate((element) => getComputedStyle(element).textAlign) === "right", "Report numeric columns are not right aligned")
	const tableContainment = await activeShell.locator(".erp-table-wrap").first().evaluate((element) => ({ overflowX: getComputedStyle(element).overflowX, clientWidth: element.clientWidth, scrollWidth: element.scrollWidth }))
	assert(await tableHeader.evaluate((element) => getComputedStyle(element).position) === "sticky", "Stock Balance table header is not sticky")

	emptyStockResult = true
	await activeShell.getByRole("button", { name: "Reset", exact: true }).click()
	await activeShell.getByRole("button", { name: "Generate", exact: true }).click()
	await activeShell.getByText("No matching records", { exact: true }).waitFor()
	assert(await activeShell.getByText("No matching records", { exact: true }).isVisible(), "Generated-empty report state is not intentional")

	return { tabs: expectedTabs, calls, requestedDates, panelContract, longNameTreatment, productionTotal, tableContainment }
}

async function responsiveAuditSuite(page) {
	const fixture = await findCuttingPlan(page.request)
	const routes = [
		"/",
		"/cutting",
		"/fabric-store",
		"/cut-panel-store",
		"/accessory-store",
		"/sewing",
		"/finishing",
		"/merch",
		"/purchase",
		"/sales",
		"/planning",
		"/cutting/plans",
		"/cutting/reports",
		`/cutting/plans/${encodeURIComponent(fixture.name)}`,
	]
	const viewports = [
		{ width: 1600, height: 1000 },
		{ width: 1280, height: 800 },
		{ width: 900, height: 760 },
		{ width: 390, height: 844 },
	]
	const audited = []

	for (const viewport of viewports) {
		await page.setViewportSize(viewport)
		for (const path of routes) {
			await page.goto(`${SITE}/web${path}`, { waitUntil: "domcontentloaded" })
			await page.locator(".app-shell").waitFor({ timeout: 20_000 })
			if (path === "/cutting/plans") await page.locator(".premium-list-table, .list-empty").first().waitFor({ timeout: 20_000 })
			if (path === "/cutting/reports") await page.locator(".report-tabs__list").waitFor({ timeout: 20_000 })
			if (path.includes("/cutting/plans/")) await page.locator(".cutting-plan-frame").waitFor({ timeout: 20_000 })

			const bodyWidth = await page.locator("body").evaluate((element) => ({ scrollWidth: element.scrollWidth, clientWidth: element.clientWidth }))
			assert(bodyWidth.scrollWidth === bodyWidth.clientWidth, `${path} overflows at ${viewport.width}px: ${JSON.stringify(bodyWidth)}`)

			const undersized = await visibleTextBelowMinimum(page)
			assert(undersized.length === 0, `${path} has text below 11px at ${viewport.width}px: ${JSON.stringify(undersized.slice(0, 8))}`)

			await page.keyboard.press("Tab")
			const focusState = await page.evaluate(() => {
				const active = document.activeElement
				if (!active || active === document.body) return { visible: false, element: "body" }
				const style = getComputedStyle(active)
				return {
					visible: style.outlineStyle !== "none" || style.boxShadow !== "none",
					element: `${active.tagName.toLowerCase()}.${String(active.className || "").replaceAll(" ", ".")}`,
					outlineStyle: style.outlineStyle,
					boxShadow: style.boxShadow,
				}
			})
			assert(focusState.visible, `${path} has no visible keyboard focus at ${viewport.width}px: ${JSON.stringify(focusState)}`)
			audited.push(`${viewport.width}x${viewport.height}:${path}`)
		}
	}

	await page.setViewportSize({ width: 1600, height: 1000 })
	await page.goto(`${SITE}/web/cutting/reports`, { waitUntil: "domcontentloaded" })
	await page.locator(".report-tabs__list").waitFor({ timeout: 20_000 })
	const reportStickyContract = await page.evaluate(() => {
		const tabs = document.querySelector(".report-tabs__list")
		const panels = document.querySelector(".report-tabs__panels")
		return { tabsBottom: tabs?.getBoundingClientRect().bottom || 0, panelsTop: panels?.getBoundingClientRect().top || 0 }
	})
	assert(reportStickyContract.tabsBottom <= reportStickyContract.panelsTop + 1, `Report tabs overlap content: ${JSON.stringify(reportStickyContract)}`)

	await page.goto(`${SITE}/web/cutting/plans/${encodeURIComponent(fixture.name)}`, { waitUntil: "domcontentloaded" })
	await page.locator(".cutting-plan-frame").waitFor({ timeout: 20_000 })
	await page.locator(".cutting-tabs .p-tablist").waitFor({ timeout: 20_000 })
	const planStickyContract = await page.evaluate(() => {
		const tabs = document.querySelector(".cutting-tabs .p-tablist")
		const panels = document.querySelector(".cutting-tabs .p-tabpanels")
		return { tabsBottom: tabs?.getBoundingClientRect().bottom || 0, panelsTop: panels?.getBoundingClientRect().top || 0 }
	})
	assert(planStickyContract.tabsBottom > 0 && planStickyContract.panelsTop > 0 && planStickyContract.tabsBottom <= planStickyContract.panelsTop + 1, `Cutting Plan tabs overlap content: ${JSON.stringify(planStickyContract)}`)
	const statusText = await page.locator(".cutting-plan-status:visible, .marker-status:visible, .lay-status:visible, .erp-status:visible").allTextContents()
	assert(statusText.length > 0 && statusText.every((value) => value.trim()), `Status meaning is not available as text: ${JSON.stringify(statusText)}`)
	return { routeCount: routes.length, viewportCount: viewports.length, fixture: fixture.name, reportStickyContract, planStickyContract }
}

const suites = {
	tokens: tokensSuite,
	shell: shellSuite,
	"cutting-entry": cuttingEntrySuite,
	list: listSuite,
	"form-field-a11y": formFieldAccessibilitySuite,
	"form-load-failures": formLoadFailuresSuite,
	"plan-frame": planFrameSuite,
	"plan-actions": planActionsSuite,
	"plan-primary-tabs": planPrimaryTabsSuite,
	sidebar: sidebarSuite,
	"entity-dialogs": entityDialogsSuite,
	cpm: cpmSuite,
	"stock-transfers": stockTransfersSuite,
	reports: reportsSuite,
	"responsive-audit": responsiveAuditSuite,
}

const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({ viewport: { width: 1600, height: 1000 } })

try {
	const loginPage = await context.newPage()
	await login(loginPage)
	await loginPage.close()
	const selectedSuites = suite === "all" ? Object.keys(suites) : [suite]
	const results = {}
	for (const suiteName of selectedSuites) {
		assert(suites[suiteName], `Unknown suite: ${suiteName}`)
		const page = await context.newPage()
		const errors = []
		page.on("pageerror", (error) => errors.push(`page: ${error.message}`))
		page.on("console", (message) => {
			if (message.type() === "error") errors.push(`console: ${message.text()}`)
		})
		try {
			results[suiteName] = await suites[suiteName](page, context)
			assertNoBrowserErrors(errors)
		} catch (error) {
			if (!(error instanceof FixtureUnavailableError)) throw error
			results[suiteName] = { skipped: true, reason: error.message }
		} finally {
			await page.close()
		}
	}
	console.log(JSON.stringify({ passed: true, suites: results }, null, 2))
} finally {
	await browser.close()
}
