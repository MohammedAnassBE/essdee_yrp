#!/usr/bin/env node

import { createRequire } from "node:module"
import {
	existsSync,
	mkdirSync,
	mkdtempSync,
	readFileSync,
	rmSync,
	writeFileSync,
} from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"

const require = createRequire("/home/anas/.claude/playwright/package.json")
const { chromium } = require("playwright")
const SITE = process.env.ESSDEE_TEST_SITE || "http://erp-migration-test.site:8001"
const requestedSuite = process.argv[2] || "all"
const SCREEN_DIRECTORY = process.argv[3]
	|| process.env.ESSDEE_PD_SCREENSHOTS
	|| "/tmp/claude-1000/-home-anas-pilot-benches-frappe-16/348c72ab-5d72-4bcf-a023-b3fbf230e45a/scratchpad/screens/pd"
const WORKSPACE = "essdee_yrp.product_development.web_workspace"
const LOTWISE = "essdee_yrp.product_development.lotwise_workspace"
const PRODUCT_METHOD = "essdee_yrp.essdee_yrp.doctype.sd_yrp_product.sd_yrp_product"
const IMAGE_METHOD = "essdee_yrp.essdee_yrp.doctype.sd_yrp_product_image.sd_yrp_product_image"
const PRODUCT_TABS = [
	"Basic", "Silhouette", "Trims", "Colours", "Graphic Designs", "Accessories", "Measurement", "Costing", "Extras",
]
const RELEASE_TABS = PRODUCT_TABS.filter((tab) => !["Costing", "Extras"].includes(tab))
const TRANSPARENT_PNG = Buffer.from(
	"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
	"base64",
)
const LOTWISE_TOTALS = [
	"total_qty", "total_selling_value", "total_weight", "total_cloth_value", "cloth_value_per_piece",
	"production_cost_per_piece", "production_cost", "total_trade_discount", "total_other_cost", "gst_value",
	"cost_price", "avg_cost_per_piece", "avg_rate_per_piece", "profit", "profit_percent", "profit_percent_markdown",
]

function assert(condition, message) {
	if (!condition) throw new Error(message)
}

function requestArgs(request) {
	try { return JSON.parse(request.postData() || "{}") } catch { return {} }
}

function reply(route, message, status = 200) {
	return route.fulfill({
		status,
		contentType: "application/json",
		body: JSON.stringify(status >= 400 ? message : { message }),
	})
}

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

async function callMethod(page, method, args = {}) {
	return page.evaluate(async ({ methodName, values }) => {
		const response = await fetch(`/api/method/${methodName}`, {
			method: "POST",
			credentials: "include",
			headers: {
				Accept: "application/json",
				"Content-Type": "application/json",
				"X-Frappe-CSRF-Token": window.csrf_token || window.frappe?.csrf_token || "",
			},
			body: JSON.stringify(values),
		})
		return { status: response.status, body: await response.json().catch(() => ({})) }
	}, { methodName: method, values: args })
}

async function methodMessage(page, method, args = {}) {
	const response = await callMethod(page, method, args)
	assert(response.status < 400 && !response.body.exc, `${method} failed: HTTP ${response.status} ${JSON.stringify(response.body)}`)
	return response.body.message
}

async function resourceRows(page, doctype, { fields = ["name"], filters = [], limit = 500 } = {}) {
	return page.evaluate(async ({ type, selectedFields, selectedFilters, pageLength }) => {
		const query = new URLSearchParams({
			fields: JSON.stringify(selectedFields),
			filters: JSON.stringify(selectedFilters),
			limit_page_length: String(pageLength),
		})
		const response = await fetch(`/api/resource/${encodeURIComponent(type)}?${query}`, { credentials: "include" })
		return { status: response.status, body: await response.json().catch(() => ({})) }
	}, { type: doctype, selectedFields: fields, selectedFilters: filters, pageLength: limit }).then((response) => {
		assert(response.status < 400, `Could not query ${doctype}: HTTP ${response.status}`)
		return response.body.data || []
	})
}

async function assertResourceAbsent(page, doctype, name, label) {
	const response = await page.request.get(
		`${SITE}/api/resource/${encodeURIComponent(doctype)}/${encodeURIComponent(name)}`,
	)
	const body = await response.json().catch(() => ({}))
	const detail = JSON.stringify(body)
	assert(
		response.status() === 404 || body.exc_type === "DoesNotExistError" || detail.includes("DoesNotExistError"),
		`${label} still exists after deletion: HTTP ${response.status()} ${detail}`,
	)
}

async function deleteResource(page, doctype, name) {
	if (!name) return
	const response = await page.evaluate(async ({ type, recordName }) => {
		const request = await fetch(`/api/resource/${encodeURIComponent(type)}/${encodeURIComponent(recordName)}`, {
			method: "DELETE",
			credentials: "include",
			headers: { "X-Frappe-CSRF-Token": window.csrf_token || window.frappe?.csrf_token || "" },
		})
		return { status: request.status, body: await request.json().catch(() => ({})) }
	}, { type: doctype, recordName: name })
	if (response.status !== 404) assert(response.status < 400, `Cleanup failed for ${doctype} ${name}: ${JSON.stringify(response.body)}`)
}

function uniqueNames(rows, remembered = []) {
	return [...new Set([...rows.map((row) => row.name), ...remembered].filter(Boolean))]
}

async function cleanupRows(page, doctype, options, failures, label) {
	try {
		return await resourceRows(page, doctype, options)
	} catch (reason) {
		failures.push(`${label}: ${reason.message}`)
		return []
	}
}

async function discoverRunFixtures(page, identity, failures) {
	const productLinks = [["product", "like", `${identity.productPrefix}%`]]
	const [products, releases, lotwise, images] = await Promise.all([
		cleanupRows(page, "SD YRP Product", { filters: [["name", "like", `${identity.productPrefix}%`]] }, failures, "discover Products"),
		cleanupRows(page, "SD YRP Product Release", { filters: productLinks }, failures, "discover Releases"),
		cleanupRows(page, "SD YRP Lotwise Item Profit", { filters: productLinks }, failures, "discover costing sheets"),
		cleanupRows(page, "SD YRP Product Image", { filters: [["name", "like", `${identity.imagePrefix}%`]] }, failures, "discover images"),
	])
	const attachedNames = uniqueNames([...products, ...releases, ...lotwise, ...images], identity.rememberedNames)
	const files = attachedNames.length ? await cleanupRows(page, "File", {
		fields: ["name", "is_folder", "folder", "attached_to_name"],
		filters: [["attached_to_name", "in", attachedNames]],
	}, failures, "discover attached files") : []
	const folderFiles = await cleanupRows(page, "File", {
		fields: ["name", "is_folder", "folder", "attached_to_name"],
		filters: [["folder", "like", `${identity.productFolder}%`]],
	}, failures, "discover folder contents")
	const folders = await cleanupRows(page, "File", {
		fields: ["name", "is_folder", "folder", "attached_to_name"],
		filters: [["name", "like", `${identity.productFolder}%`]],
	}, failures, "discover Product folders")
	return { products, releases, lotwise, images, files: [...files, ...folderFiles], folders, attachedNames }
}

async function attemptCleanup(failures, label, operation) {
	try {
		await operation()
	} catch (reason) {
		failures.push(`${label}: ${reason.message}`)
	}
}

async function deleteDiscovered(page, doctype, names, failures) {
	for (const name of names) {
		await attemptCleanup(failures, `delete ${doctype} ${name}`, () => deleteResource(page, doctype, name))
	}
}

async function verifyRunCleanup(page, identity, attachedNames, failures) {
	const checks = [
		["SD YRP Product", [["name", "like", `${identity.productPrefix}%`]]],
		["SD YRP Product Release", [["product", "like", `${identity.productPrefix}%`]]],
		["SD YRP Lotwise Item Profit", [["product", "like", `${identity.productPrefix}%`]]],
		["SD YRP Product Image", [["name", "like", `${identity.imagePrefix}%`]]],
		["File", [["name", "like", `${identity.productFolder}%`]]],
		["File", [["folder", "like", `${identity.productFolder}%`]]],
	]
	if (attachedNames.length) checks.push(["File", [["attached_to_name", "in", attachedNames]]])
	for (const [doctype, filters] of checks) {
		const rows = await cleanupRows(page, doctype, { filters }, failures, `verify ${doctype}`)
		if (rows.length) failures.push(`verify ${doctype}: ${JSON.stringify(rows)}`)
	}
}

async function cleanupRunFixtures(page, identity) {
	const failures = []
	const fixtures = await discoverRunFixtures(page, identity, failures)
	await deleteDiscovered(page, "SD YRP Product Release", uniqueNames(fixtures.releases), failures)
	await deleteDiscovered(page, "SD YRP Lotwise Item Profit", uniqueNames(fixtures.lotwise), failures)
	await deleteDiscovered(page, "SD YRP Product", uniqueNames(fixtures.products), failures)
	await deleteDiscovered(page, "SD YRP Product Image", uniqueNames(fixtures.images), failures)
	await deleteDiscovered(page, "File", uniqueNames(fixtures.files), failures)
	const remaining = await discoverRunFixtures(page, identity, failures)
	await deleteDiscovered(page, "File", uniqueNames(remaining.files), failures)
	const folders = uniqueNames([...fixtures.folders, ...remaining.folders])
		.sort((left, right) => right.length - left.length)
	await deleteDiscovered(page, "File", folders, failures)
	await verifyRunCleanup(page, identity, fixtures.attachedNames, failures)
	if (failures.length) throw new Error(`Cleanup failures:\n${failures.join("\n")}`)
	console.log(`OK ui-cleanup: ${identity.productPrefix} records, files and exact Product folders are absent`)
}

function mediaUrls(value, urls = new Set()) {
	if (Array.isArray(value)) {
		for (const item of value) mediaUrls(item, urls)
		return urls
	}
	if (value && typeof value === "object") {
		for (const item of Object.values(value)) mediaUrls(item, urls)
		return urls
	}
	if (typeof value === "string" && /^(?:https?:\/\/|\/files\/|\/private\/files\/)/.test(value)) urls.add(value)
	return urls
}

function observePage(page) {
	const state = { consoleErrors: [], pageErrors: [], failedResponses: [], resourceFailures: [], apiRequests: [] }
	page.on("request", (request) => {
		if (request.url().includes("/api/method/")) {
			state.apiRequests.push(`${request.method()} ${request.url()} ${request.postData() || ""}`)
			if (state.apiRequests.length > 20) state.apiRequests.shift()
		}
	})
	page.on("console", (entry) => {
		if (entry.type() === "error") {
			const location = entry.location()
			state.consoleErrors.push(`${entry.text()}${location.url ? ` (${location.url})` : ""}`)
		}
	})
	page.on("pageerror", (reason) => state.pageErrors.push(reason.message))
	page.on("response", (response) => {
		const url = response.url()
		if (response.status() >= 400 && !url.includes("/api/")) state.resourceFailures.push(`${response.status()} ${url}`)
		if (response.status() < 400 || !url.includes("/api/")) return
		const isStaleMock = response.status() === 417 && url.includes(`${WORKSPACE}.save_product`)
		if (!isStaleMock) state.failedResponses.push(`${response.status()} ${url}`)
	})
	return state
}

function assertPageClean(state, label) {
	const unexpectedConsoleErrors = state.consoleErrors.filter(
		(message) => !message.includes("status of 417 (Expectation Failed)"),
	)
	assert(
		!unexpectedConsoleErrors.length,
		`${label} console errors:\n${unexpectedConsoleErrors.join("\n")}\nResources:\n${state.resourceFailures.join("\n")}\nRecent API requests:\n${state.apiRequests.join("\n")}`,
	)
	assert(!state.pageErrors.length, `${label} page errors:\n${state.pageErrors.join("\n")}`)
	assert(!state.failedResponses.length, `${label} failed API responses:\n${state.failedResponses.join("\n")}`)
}

async function noOverflow(page, label) {
	const geometry = await page.evaluate(() => ({
		viewport: innerWidth,
		page: document.documentElement.scrollWidth,
		offenders: [...document.querySelectorAll("body *")].map((element) => {
			const box = element.getBoundingClientRect()
			return { tag: element.tagName, className: String(element.className || ""), left: Math.round(box.left), right: Math.round(box.right) }
		}).filter((item) => item.left < -1 || item.right > innerWidth + 1).slice(0, 12),
	}))
	assert(geometry.page <= geometry.viewport + 1, `${label} overflows: ${JSON.stringify(geometry)}`)
}

async function screenshot(page, name, locator = null) {
	mkdirSync(SCREEN_DIRECTORY, { recursive: true })
	const options = { path: join(SCREEN_DIRECTORY, name), animations: "disabled" }
	if (locator) await locator.screenshot(options)
	else await page.screenshot({ ...options, fullPage: true })
}

async function assertPdAccent(page, label, selector, property = "color", visibleToken = "--erp-accent") {
	await page.locator(selector).first().waitFor()
	const colours = await page.locator(".department-page").evaluate((element, options) => {
		const probe = document.createElement("span")
		probe.style[options.property] = `var(${options.visibleToken})`
		element.append(probe)
		const expected = getComputedStyle(probe)[options.property]
		probe.remove()
		return {
			accent: getComputedStyle(element).getPropertyValue("--erp-accent").trim().toLowerCase(),
			rootAccent: getComputedStyle(document.documentElement).getPropertyValue("--erp-accent").trim().toLowerCase(),
			expected,
			visible: getComputedStyle(document.querySelector(options.selector))[options.property],
		}
	}, { selector, property, visibleToken })
	assert(colours.accent === "#059669", `${label} --erp-accent is ${colours.accent}`)
	assert(colours.rootAccent === colours.accent, `${label} root accent is ${colours.rootAccent}; expected ${colours.accent}`)
	assert(colours.visible === colours.expected, `${label} visible accent is ${colours.visible}; expected ${colours.expected}`)
}

async function startRootAccentSampling(page) {
	await page.evaluate(() => {
		window.__pdAccentSamples = []
		window.__pdAccentTimer = window.setInterval(() => {
			window.__pdAccentSamples.push(
				getComputedStyle(document.documentElement).getPropertyValue("--erp-accent").trim().toLowerCase(),
			)
		}, 0)
	})
}

async function stopRootAccentSampling(page) {
	return page.evaluate(() => {
		window.clearInterval(window.__pdAccentTimer)
		return window.__pdAccentSamples || []
	})
}

async function assertPdPrimeControls(page) {
	await page.goto(`${SITE}/web/pd/lotwise-item-profits/new`, { waitUntil: "domcontentloaded" })
	await page.getByRole("heading", { name: "New Costing Sheet", exact: true }).waitFor()

	const costingType = formField(page, "Lot Costing Type").locator(".p-select")
	await costingType.click()
	await page.getByRole("option", { name: "Planned Qty", exact: true }).click()
	await costingType.click()
	const selectedOption = page.getByRole("option", { name: "Planned Qty", exact: true })
	await selectedOption.waitFor()
	assert(await selectedOption.getAttribute("aria-selected") === "true", "Lot Costing Type did not select Planned Qty")
	const optionColours = await selectedOption.evaluate((element) => {
		const probe = document.createElement("span")
		probe.style.color = "var(--p-highlight-focus-color)"
		probe.style.backgroundColor = "var(--p-highlight-focus-background)"
		document.body.append(probe)
		const expected = getComputedStyle(probe)
		const visible = getComputedStyle(element)
		const result = {
			background: visible.backgroundColor,
			colour: visible.color,
			expectedBackground: expected.backgroundColor,
			expectedColour: expected.color,
			primary: getComputedStyle(document.documentElement).getPropertyValue("--p-primary-color").trim().toLowerCase(),
		}
		probe.remove()
		return result
	})
	assert(optionColours.primary === "#10b981", `PD PrimeVue primary is ${optionColours.primary}`)
	assert(
		optionColours.background === optionColours.expectedBackground,
		`Selected Lot Costing Type is ${optionColours.background}; expected ${optionColours.expectedBackground}`,
	)
	assert(
		optionColours.colour === optionColours.expectedColour,
		`Selected Lot Costing Type text is ${optionColours.colour}; expected ${optionColours.expectedColour}`,
	)
	await page.keyboard.press("Escape")

	const disabledSwitch = formField(page, "Disabled").locator(".p-toggleswitch")
	assert(await disabledSwitch.isEnabled(), "New costing Disabled switch is not enabled")
	await disabledSwitch.click()
	await disabledSwitch.waitFor()
	assert(await disabledSwitch.getAttribute("data-p-checked") === "true", "Disabled switch did not turn on")
	await page.mouse.move(0, 0)
	await page.waitForTimeout(250)
	const switchColours = await disabledSwitch.evaluate((element) => {
		const probe = document.createElement("span")
		probe.style.backgroundColor = "var(--p-primary-color)"
		document.body.append(probe)
		const expected = getComputedStyle(probe).backgroundColor
		probe.remove()
		return { expected, visible: getComputedStyle(element.querySelector(".p-toggleswitch-slider")).backgroundColor }
	})
	assert(
		switchColours.visible === switchColours.expected,
		`Enabled PD switch is ${switchColours.visible}; expected ${switchColours.expected}`,
	)
}

async function assertSalesSuccessBadge(page) {
	const routePattern = "**/api/resource/YRP%20Production%20Order**"
	const routeHandler = (route) => route.fulfill({
		contentType: "application/json",
		body: JSON.stringify({ data: [{
			name: "PPO-PALETTE-CHECK",
			item: "Palette Check",
			production_term: "Standard",
			delivery_date: "2026-10-12",
			status: "Submitted",
			docstatus: 1,
			modified: "2026-10-12 10:00:00",
		}] }),
	})
	await page.route(routePattern, routeHandler)
	try {
		await page.goto(`${SITE}/web/sales/production-orders`, { waitUntil: "domcontentloaded" })
		await page.getByRole("heading", { name: "Production Orders", exact: true }).waitFor()
		const badge = page.locator(".document-status-badge--success").filter({ hasText: "Submitted" }).first()
		await badge.waitFor()
		const colours = await badge.evaluate((element) => {
			const luminance = (colour) => {
				const channels = colour.match(/[\d.]+/g).slice(0, 3).map((channel) => Number(channel) / 255)
				const linear = channels.map((channel) => channel <= 0.04045
					? channel / 12.92
					: ((channel + 0.055) / 1.055) ** 2.4)
				return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722
			}
			const probe = document.createElement("span")
			probe.style.color = "var(--erp-success-text)"
			probe.style.backgroundColor = "var(--erp-success-soft)"
			document.body.append(probe)
			const expected = getComputedStyle(probe)
			const visible = getComputedStyle(element)
			const luminosities = [luminance(visible.color), luminance(visible.backgroundColor)].sort((left, right) => right - left)
			const result = {
				accent: getComputedStyle(document.documentElement).getPropertyValue("--erp-accent").trim().toLowerCase(),
				background: visible.backgroundColor,
				contrast: (luminosities[0] + 0.05) / (luminosities[1] + 0.05),
				colour: visible.color,
				expectedBackground: expected.backgroundColor,
				expectedColour: expected.color,
			}
			probe.remove()
			return result
		})
		assert(colours.accent === "#059669", `Sales root accent is ${colours.accent}`)
		assert(colours.colour === colours.expectedColour, `Sales Submitted badge is ${colours.colour}; expected ${colours.expectedColour}`)
		assert(colours.background === colours.expectedBackground, `Sales Submitted badge background is ${colours.background}; expected ${colours.expectedBackground}`)
		assert(colours.contrast >= 4.5, `Sales Submitted badge contrast is ${colours.contrast.toFixed(2)}:1`)
	} finally {
		await page.unroute(routePattern, routeHandler)
	}
}

async function openListTools(page, prefix) {
	await page.getByRole("button", { name: "Filters", exact: true }).click()
	const filters = page.getByRole("dialog", { name: "Filters", exact: true })
	await filters.waitFor()
	await assertPdAccent(
		page,
		`${prefix} filters dialog primary button`,
		".list-filter-dialog .p-dialog-footer .p-button:last-child",
		"backgroundColor",
		"--erp-accent-hover",
	)
	await screenshot(page, `${prefix}-dialog-filters.png`, filters)
	await filters.getByRole("button", { name: "Apply Filters", exact: true }).click()
	await page.getByRole("button", { name: "Columns", exact: true }).click()
	const columns = page.getByRole("dialog", { name: "Customize Columns", exact: true })
	await columns.waitFor()
	await screenshot(page, `${prefix}-dialog-columns.png`, columns)
	await columns.getByRole("button", { name: "Cancel", exact: true }).click()
	await page.getByRole("button", { name: "Refresh", exact: true }).click()
}

async function clickTabs(page, tabs, prefix) {
	for (const [index, tab] of tabs.entries()) {
		const tabButton = page.getByRole("tab", { name: tab, exact: true })
		await tabButton.click()
		await tabButton.waitFor()
		await page.waitForFunction((label) => {
			const selected = [...document.querySelectorAll('[role="tab"]')]
				.find((element) => element.textContent?.trim() === label)
			return selected?.getAttribute("aria-selected") === "true"
		}, tab)
		await screenshot(page, `${prefix}-${String(index + 1).padStart(2, "0")}-${tab.toLowerCase().replaceAll(" ", "-")}.png`)
	}
}

function sourceChecks() {
	const router = readFileSync("frontend/src/router/index.js", "utf8")
	const api = readFileSync("frontend/src/api/pd.js", "utf8")
	for (const route of [
		'path: "/pd/products"', 'path: "/pd/products/new"', 'path: "/pd/products/:productId/edit"',
		'path: "/pd/products/:productId"', 'path: "/pd/product-releases"',
		'path: "/pd/product-releases/:releaseId"', 'path: "/pd/lotwise-item-profits"',
		'path: "/pd/lotwise-item-profits/new"', 'path: "/pd/lotwise-item-profits/:profitId"',
	]) assert(router.includes(route), `PD router is missing ${route}`)
	for (const method of [
		"get_capabilities", "get_product_workspace", "get_new_product_defaults", "save_product",
		"delete_product", "get_size_range_sizes", "get_image_list", "create_product_image",
		"delete_and_update_file", "process_single_page_pdf", "upload_graphics_file",
		"process_pdf_to_images", "remove_graphic_image", "release_tech_pack",
		"get_product_release_workspace", "delete_product_release", "get_lotwise_workspace",
		"run_lotwise_command", "save_lotwise_item_profit", "delete_lotwise_item_profit",
	]) assert(api.includes(method), `PD API module is missing ${method}`)
}

async function launcherSuite(page) {
	const monitor = observePage(page)
	await page.goto(`${SITE}/web/pd`, { waitUntil: "domcontentloaded" })
	const cards = page.locator(".workspace-launcher__card")
	await cards.nth(2).waitFor()
	await assertPdAccent(page, "PD launcher", ".workspace-launcher__icon")
	assert(JSON.stringify(await cards.locator("strong").allTextContents()) === JSON.stringify([
		"Products", "Product Releases", "Lotwise Item Profit",
	]), "PD launcher did not render exactly the three workspaces")
	await screenshot(page, "01-launcher.png")
	await startRootAccentSampling(page)
	await cards.filter({ hasText: "Products" }).click()
	await page.getByRole("heading", { name: "Products", exact: true }).waitFor()
	const accentSamples = await stopRootAccentSampling(page)
	assert(accentSamples.length, "PD route transition produced no accent samples")
	assert(
		accentSamples.every((accent) => accent === "#059669"),
		`PD route transition exposed non-theme accents: ${JSON.stringify([...new Set(accentSamples)])}`,
	)
	await page.goto(`${SITE}/web/pd`, { waitUntil: "domcontentloaded" })
	await cards.nth(2).waitFor()
	const pattern = `**/api/method/${WORKSPACE}.get_capabilities*`
	const handler = (route) => reply(route, {
		sections: {
			product_releases: { label: "Product Releases", can_read: true },
		},
	})
	await page.route(pattern, handler)
	await page.reload({ waitUntil: "domcontentloaded" })
	await cards.first().waitFor()
	assert(await cards.count() === 1, "A denied PD launcher tile remained visible")
	assert((await cards.first().innerText()).includes("Product Releases"), "The permitted Product Releases tile is missing")
	await screenshot(page, "02-launcher-release-only.png")
	await page.unroute(pattern, handler)
	assertPageClean(monitor, "launcher")
	console.log("OK launcher: three tiles, capability-based hiding and stable PD transition palette")
}

async function productsSuite(page) {
	const monitor = observePage(page)
	await page.goto(`${SITE}/web/pd/products`, { waitUntil: "domcontentloaded" })
	await page.getByRole("heading", { name: "Products", exact: true }).waitFor()
	await page.locator(".premium-list-table tbody tr").first().waitFor()
	await assertPdAccent(
		page,
		"Products",
		".list-toolbar__primary .p-button",
		"backgroundColor",
		"--erp-accent-hover",
	)
	await screenshot(page, "03-products-list.png")
	await openListTools(page, "04-products")
	const search = page.getByRole("textbox", { name: "Search Products…", exact: true })
	await search.fill("PNOCHO Shirt")
	await search.press("Enter")
	await page.getByText("PNOCHO Shirt", { exact: true }).first().waitFor()
	await page.getByRole("button", { name: "Open PNOCHO Shirt", exact: true }).click()
	await page.locator(".pd-product-workspace__header").waitFor()
	assert((await page.getByRole("tab").allTextContents()).join("|") === PRODUCT_TABS.join("|"), "Product tabs are incomplete")
	await clickTabs(page, PRODUCT_TABS, "05-product-view")
	const slashProducts = await resourceRows(page, "SD YRP Product", {
		filters: [["name", "like", "%/%"]],
		limit: 1,
	})
	assert(slashProducts[0]?.name, "No Product containing '/' exists for the deep-link check")
	const slashProduct = slashProducts[0].name
	await page.goto(`${SITE}/web/pd/products/${encodeURIComponent(slashProduct)}`, { waitUntil: "domcontentloaded" })
	await page.locator(".pd-product-workspace__eyebrow").filter({ hasText: slashProduct }).waitFor()
	assert(decodeURIComponent(new URL(page.url()).pathname).endsWith(`/pd/products/${slashProduct}`), "Slash Product deep link changed identity")
	for (const width of [1440, 390]) {
		await page.setViewportSize({ width, height: 900 })
		await noOverflow(page, `Product at ${width}px`)
	}
	await page.setViewportSize({ width: 1440, height: 1000 })
	await screenshot(page, "14-product-slash-deep-link.png")
	await assertSalesSuccessBadge(page)
	await assertPdPrimeControls(page)
	assertPageClean(monitor, "products")
	console.log("OK products: real list, PD and PrimeVue accents, accessible Sales success badge, PNOCHO tabs, encoded slash deep link and responsive layout")
}

function formField(page, label) {
	return page.locator(".form-field").filter({ has: page.locator(".form-field__label", { hasText: label }) }).first()
}

async function fillLink(page, label, value) {
	const input = formField(page, label).locator(".p-autocomplete-input")
	await input.fill(value)
	const option = page.locator(".p-autocomplete-option:visible").filter({ hasText: value }).first()
	await option.waitFor()
	await option.click()
}

function runIdentity(productName, imagePrefix = productName) {
	return {
		productPrefix: productName,
		productFolder: `Home/product/${productName.toLowerCase()}`,
		imagePrefix,
		rememberedNames: [productName],
	}
}

async function createWorkspaceProduct(page, productName, withSizes = false) {
	const groups = await resourceRows(page, "SD YRP Product Group", { limit: 1 })
	assert(groups[0]?.name, "No Product Group exists for throwaway Product creation")
	const values = {
		style_no: productName,
		item_name: productName,
		product_group: groups[0].name,
		description: "Throwaway Product created by verify_pd_workspace.mjs",
		fabric_details: "Cotton",
		is_set_item: 0,
	}
	if (withSizes) {
		const ranges = await resourceRows(page, "SD YRP FG Item Size Range", { limit: 1 })
		assert(ranges[0]?.name, "No FG Item Size Range exists for throwaway Product creation")
		values.size_range = ranges[0].name
		values.sizes = await methodMessage(page, `${WORKSPACE}.get_size_range_sizes`, { size_range: ranges[0].name })
		assert(values.sizes.length, `Size Range ${ranges[0].name} has no sizes`)
	}
	return methodMessage(page, `${WORKSPACE}.save_product`, { values, images: {} })
}

async function uploadAttachment(page, { buffer, filename, mimeType, doctype, docname, fieldname }) {
	const csrfToken = await page.evaluate(() => window.csrf_token || window.frappe?.csrf_token || "")
	const response = await page.request.post(`${SITE}/api/method/upload_file`, {
		headers: { "X-Frappe-CSRF-Token": csrfToken },
		multipart: {
			file: { name: filename, mimeType, buffer },
			is_private: "1",
			doctype,
			docname,
			fieldname,
		},
	})
	const body = await response.json().catch(() => ({}))
	assert(response.ok() && !body.exc, `Upload failed: HTTP ${response.status()} ${JSON.stringify(body)}`)
	return body.message
}

async function assertReachableImages(page, workspace, label) {
	const urls = [...mediaUrls(workspace)]
	assert(urls.length, `${label} has no media URL to verify`)
	for (const url of urls) {
		const response = await page.request.get(url.startsWith("http") ? url : `${SITE}${url}`)
		assert(response.status() === 200, `${label} media failed: HTTP ${response.status()} ${url}`)
		assert(
			String(response.headers()["content-type"] || "").startsWith("image/"),
			`${label} media is not an image: ${url}`,
		)
	}
}

async function assertForbiddenOnTabs(page, tabs, labels, documentLabel) {
	for (const tab of tabs) {
		const button = page.getByRole("tab", { name: tab, exact: true })
		await button.click()
		await page.waitForFunction((name) => [...document.querySelectorAll('[role="tab"]')]
			.some((element) => element.textContent?.trim() === name && element.getAttribute("aria-selected") === "true"), tab)
		for (const label of labels) {
			assert(await page.getByRole("button", { name: label, exact: true }).count() === 0, `${documentLabel} ${tab} exposed ${label}`)
		}
		assert(await page.locator('input[type="file"]').count() === 0, `${documentLabel} ${tab} exposed a file input`)
	}
}

async function runLotwiseAction(page, command, action) {
	const responsePromise = page.waitForResponse((response) => response.url().includes(`${LOTWISE}.run_lotwise_command`)
		&& requestArgs(response.request()).command === command).catch((reason) => {
		throw new Error(`${command} response was not received: ${reason.message}`)
	})
	const [, response] = await Promise.all([action(), responsePromise])
	const body = await response.json().catch(() => ({}))
	assert(response.ok() && !body.exc, `${command} failed: HTTP ${response.status()} ${JSON.stringify(body)}`)
	assert(body.message?.record, `${command} returned no costing record`)
	await page.waitForFunction(() => !document.querySelector(".lotwise-workspace .p-button-loading"))
	return body.message.record
}

async function runLotwiseButton(page, button, command, action = null) {
	await button.waitFor({ state: "visible" })
	assert(await button.count(), `Missing ${command} button`)
	assert(await button.isEnabled(), `${command} button is disabled unexpectedly`)
	assert(await button.getAttribute("aria-disabled") !== "true", `${command} has an unexpected disabled reason`)
	return runLotwiseAction(page, command, action || (() => button.click()))
}

function makeFixtures() {
	const fixture = "scripts/fixtures/pd-e2e.png"
	const directory = mkdtempSync(join(tmpdir(), "pd-e2e-"))
	const image = existsSync(fixture) ? fixture : join(directory, "pixel.png")
	const pdf = join(directory, "single-page.pdf")
	if (!existsSync(fixture)) writeFileSync(image, TRANSPARENT_PNG)
	writeFileSync(pdf, Buffer.from("JVBERi0xLjQKMSAwIG9iago8PCAvVHlwZSAvQ2F0YWxvZyAvUGFnZXMgMiAwIFIgPj4KZW5kb2JqCjIgMCBvYmoKPDwgL1R5cGUgL1BhZ2VzIC9LaWRzIFszIDAgUl0gL0NvdW50IDEgPj4KZW5kb2JqCjMgMCBvYmoKPDwgL1R5cGUgL1BhZ2UgL1BhcmVudCAyIDAgUiAvTWVkaWFCb3ggWzAgMCA3MiA3Ml0gPj4KZW5kb2JqCnhyZWYKMCA0CjAwMDAwMDAwMDAgNjU1MzUgZiAKMDAwMDAwMDAwOSAwMDAwMCBuIAowMDAwMDAwMDY2IDAwMDAwIG4gCjAwMDAwMDAxMjMgMDAwMDAgbiAKdHJhaWxlcgo8PCAvU2l6ZSA0IC9Sb290IDEgMCBSID4+CnN0YXJ0eHJlZgoxOTQKJSVFT0YK", "base64"))
	return { image, pdf, directory }
}

async function useFileButton(page, button, path) {
	const chooser = page.waitForEvent("filechooser")
	await button.click()
	await (await chooser).setFiles(path)
}

async function createPickerImage(page, panel, title, action, file, screenshotName) {
	await panel.getByRole("button", { name: "Create", exact: true }).click()
	const dialog = page.getByRole("dialog", { name: "Create Product Image", exact: true })
	await dialog.waitFor()
	await dialog.locator("label").filter({ hasText: "Image Title" }).locator("input").fill(title)
	await dialog.locator("label").filter({ hasText: "Title Header" }).locator("input").fill(`${title} Header`)
	await screenshot(page, screenshotName, dialog)
	if (action === "Save") await dialog.getByRole("button", { name: "Save", exact: true }).click()
	else await useFileButton(page, dialog.getByRole("button", { name: action, exact: true }), file)
	await dialog.waitFor({ state: "hidden" })
	await panel.locator(".product-image-picker__results button, .product-trim-combination__results button").first().waitFor()
	await panel.locator(".product-image-picker__results button, .product-trim-combination__results button").first().click()
}

async function openPrintAndCapture(page, name) {
	const popupPromise = page.waitForEvent("popup")
	await page.getByRole("button", { name: "Print", exact: true }).click()
	const popup = await popupPromise
	await popup.waitForLoadState("domcontentloaded")
	await screenshot(popup, name)
	await popup.close()
}

async function productEditSuite(page) {
	const monitor = observePage(page)
	const fixtures = makeFixtures()
	const runId = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
	const productName = `PD-E2E-${runId}`
	const identity = runIdentity(productName)
	let releaseName = ""
	page.on("response", async (response) => {
		if (!response.ok() || !response.url().includes(`${IMAGE_METHOD}.create_product_image`)) return
		const body = await response.json().catch(() => ({}))
		if (body.message?.name) {
			identity.rememberedNames.push(body.message.name)
		}
	})
	try {
		const groups = await resourceRows(page, "SD YRP Product Group", { limit: 1 })
		const sizeRanges = await resourceRows(page, "SD YRP FG Item Size Range", { limit: 1 })
		assert(groups[0]?.name, "No Product Group exists for Product creation")
		assert(sizeRanges[0]?.name, "No FG Item Size Range exists for required size-range verification")
		await page.goto(`${SITE}/web/pd/products/new`, { waitUntil: "domcontentloaded" })
		await page.getByRole("heading", { name: "New Product", exact: true }).waitFor()
		await screenshot(page, "15-product-new.png")
		await formField(page, "Product Style No.").locator("input").fill(productName)
		await formField(page, "Item Name").locator("input").fill("PD E2E Product")
		await fillLink(page, "Product Group", groups[0].name)
		const sizeResponse = page.waitForResponse((response) => response.url().includes(`${WORKSPACE}.get_size_range_sizes`) && response.ok())
		await fillLink(page, "Size Range", sizeRanges[0].name)
		await sizeResponse
		await formField(page, "Description").locator("textarea").fill("Throwaway Product created by verify_pd_workspace.mjs")
		await formField(page, "Fabric Details").locator("input").fill("Cotton")
		await page.getByRole("button", { name: "Save", exact: true }).click()
		await page.waitForURL(new RegExp(`/web/pd/products/${encodeURIComponent(productName)}$`))
		await page.getByRole("heading", { name: "PD E2E Product", exact: true }).waitFor()
		await page.getByRole("button", { name: "Edit", exact: true }).click()
		await page.waitForURL(/\/edit$/)
		await screenshot(page, "16-product-edit.png")
		await formField(page, "Item Name").locator("input").fill("PD E2E Product Updated")
		await page.getByRole("button", { name: "Save", exact: true }).click()
		await page.waitForURL(new RegExp(`/web/pd/products/${encodeURIComponent(productName)}$`))
		await page.getByRole("heading", { name: "PD E2E Product Updated", exact: true }).waitFor()

		await page.getByRole("button", { name: "Edit", exact: true }).click()
		await formField(page, "Item Name").locator("input").fill("PD E2E Discard Check")
		await page.getByRole("button", { name: "Cancel", exact: true }).click()
		const discardDialog = page.getByRole("dialog", { name: "Discard unsaved changes?", exact: true })
		await discardDialog.waitFor()
		await screenshot(page, "16-dialog-discard-product.png", discardDialog)
		await discardDialog.getByRole("button", { name: "Keep Document", exact: true }).click()
		await discardDialog.waitFor({ state: "hidden" })
		await formField(page, "Item Name").locator("input").fill("PD E2E Stale Edit")
		const stalePattern = `**/api/method/${WORKSPACE}.save_product*`
		const staleHandler = (route) => reply(route, {
			exc_type: "TimestampMismatchError",
			_server_messages: JSON.stringify([JSON.stringify({
				message: `${productName} changed after you opened it. Refresh and try again.`,
			})]),
		}, 417)
		await page.route(stalePattern, staleHandler)
		await page.getByRole("button", { name: "Save", exact: true }).click()
		const staleDialog = page.getByRole("dialog", { name: "Product action could not be completed", exact: true })
		await staleDialog.waitFor()
		assert((await staleDialog.innerText()).includes("changed after you opened it"), "Stale Product save did not show a clear conflict")
		await screenshot(page, "16-dialog-stale-product.png", staleDialog)
		await page.unroute(stalePattern, staleHandler)
		await staleDialog.getByRole("button", { name: "Reload", exact: true }).click()
		await page.getByRole("button", { name: "Cancel", exact: true }).click()
		await page.waitForURL(new RegExp(`/web/pd/products/${encodeURIComponent(productName)}$`))

		await page.getByRole("tab", { name: "Silhouette", exact: true }).click()
		await useFileButton(page, page.getByRole("button", { name: "Add/Update Image", exact: true }), fixtures.image)
		const silhouette = page.locator(".product-silhouette__preview img")
		await silhouette.waitFor()
		const beforePdf = await methodMessage(page, `${WORKSPACE}.get_product_workspace`, { name: productName })
		const beforePdfUrl = beforePdf.record.product_image
		assert(beforePdfUrl, "Initial silhouette image was not persisted")
		if (fixtures.pdf) {
			const conversionResponse = page.waitForResponse((response) => response.url().includes(`${PRODUCT_METHOD}.process_single_page_pdf`))
			await useFileButton(page, page.getByRole("button", { name: "Upload PDF", exact: true }).first(), fixtures.pdf)
			const response = await conversionResponse
			const body = await response.json().catch(() => ({}))
			assert(response.ok() && !body.exc, `Silhouette conversion failed: HTTP ${response.status()} ${JSON.stringify(body)}`)
			const afterPdf = await methodMessage(page, `${WORKSPACE}.get_product_workspace`, { name: productName })
			const convertedUrl = afterPdf.record.product_image
			assert(convertedUrl && convertedUrl !== beforePdfUrl, "Silhouette PDF did not persist a replacement URL")
			const convertedImage = await page.request.get(`${SITE}${convertedUrl}`)
			assert(convertedImage.status() === 200, `Converted silhouette failed to load: HTTP ${convertedImage.status()}`)
			assert(String(convertedImage.headers()["content-type"] || "").startsWith("image/"), "Converted silhouette is not an image")
			await page.waitForFunction((url) => document.querySelector(".product-silhouette__preview img")?.src.includes(url), convertedUrl)
		}
		await screenshot(page, "17-product-silhouette-uploaded.png")

		await page.getByRole("button", { name: "Edit", exact: true }).click()
		await page.getByRole("tab", { name: "Silhouette", exact: true }).click()
		const placement = page.locator(".pd-media-panel").filter({ hasText: "Placement Images" })
		await createPickerImage(page, placement, `${productName}-placement`, "Save", null, "18-dialog-create-placement-image.png")
		await page.getByRole("tab", { name: "Trims", exact: true }).click()
		const trims = page.locator(".pd-media-panel").filter({ hasText: "Trims Images" })
		await createPickerImage(page, trims, `${productName}-trim`, "Save & Upload Image", fixtures.image, "19-dialog-create-trim-image.png")
		if (fixtures.pdf) {
			await page.getByRole("tab", { name: "Colours", exact: true }).click()
			const combination = page.locator(".pd-media-panel").filter({ hasText: "Trim Colour Combination" })
			await createPickerImage(page, combination, `${productName}-combination`, "Save & Upload PDF", fixtures.pdf, "20-dialog-create-combination-image.png")
		}
		await page.getByRole("button", { name: "Save", exact: true }).click()
		await page.waitForURL(new RegExp(`/web/pd/products/${encodeURIComponent(productName)}$`))

		await page.getByRole("tab", { name: "Graphic Designs", exact: true }).click()
		const graphics = page.locator(".pd-media-panel").filter({ hasText: "Product Graphics" })
		await useFileButton(page, graphics.getByRole("button", { name: "Upload images", exact: true }), fixtures.image)
		const graphicsDialog = page.getByRole("dialog", { name: "Upload Graphic Designs", exact: true })
		const graphicsRow = graphicsDialog.locator(".product-graphics-bulk__rows article").first()
		await graphicsRow.locator("label").filter({ hasText: "Upload Type" }).locator("input").fill("PD E2E Graphic")
		await graphicsDialog.getByRole("button", { name: "Upload images", exact: true }).click()
		await graphicsRow.locator(".product-graphics-bulk__status").getByText("Done", { exact: true }).waitFor()
		await graphicsDialog.locator(".p-dialog-footer").getByRole("button", { name: "Close", exact: true }).click()
		await graphicsDialog.waitFor({ state: "hidden" })
		await graphics.getByText("PD E2E Graphic", { exact: true }).waitFor()
		await graphics.getByRole("button", { name: "Remove", exact: true }).click()
		const removeGraphic = page.getByRole("dialog", { name: "Remove graphic?", exact: true })
		await screenshot(page, "21-dialog-remove-graphic.png", removeGraphic)
		await removeGraphic.getByRole("button", { name: "Remove", exact: true }).click()
		await useFileButton(page, graphics.getByRole("button", { name: "Upload PDF", exact: true }), fixtures.pdf)
		await graphics.getByText("Page 1", { exact: true }).waitFor()
		await graphics.getByRole("button", { name: "Remove", exact: true }).click()
		const removePdfGraphic = page.getByRole("dialog", { name: "Remove graphic?", exact: true })
		await removePdfGraphic.getByRole("button", { name: "Remove", exact: true }).click()

		await openPrintAndCapture(page, "22-product-print-popup.png")
		await page.getByRole("button", { name: "Release Tech Pack", exact: true }).click()
		const releaseDialog = page.getByRole("dialog", { name: "Release Tech Pack?", exact: true })
		await releaseDialog.waitFor()
		await screenshot(page, "23-dialog-release-confirm.png", releaseDialog)
		await releaseDialog.getByRole("button", { name: "Keep Document", exact: true }).click()
		await releaseDialog.waitFor({ state: "hidden" })
		await page.getByRole("button", { name: "Release Tech Pack", exact: true }).click()
		const releaseResponse = page.waitForResponse((response) => response.url().includes(`${PRODUCT_METHOD}.release_tech_pack`) && response.ok())
		await releaseDialog.getByRole("button", { name: "Release Tech Pack", exact: true }).click()
		releaseName = (await (await releaseResponse).json()).message
		identity.rememberedNames.push(releaseName)
		await page.waitForURL(new RegExp(`/web/pd/product-releases/${encodeURIComponent(releaseName)}$`))
		await page.locator(".pd-product-workspace__header").waitFor()
		await screenshot(page, "24-throwaway-product-release.png")

		const releaseDelete = page.getByRole("button", { name: "Delete", exact: true })
		await releaseDelete.waitFor()
		await releaseDelete.click()
		const dialog = page.getByRole("dialog", { name: "Delete Product Release?", exact: true })
		await screenshot(page, "25-dialog-delete-release.png", dialog)
		await dialog.getByRole("button", { name: "Delete Product Release", exact: true }).click()
		await page.waitForURL(/\/web\/pd\/product-releases$/)
		await assertResourceAbsent(page, "SD YRP Product Release", releaseName, "Product Release")
		releaseName = ""

		if (!new URL(page.url()).pathname.includes(`/pd/products/${encodeURIComponent(productName)}`)) {
			await page.goto(`${SITE}/web/pd/products/${encodeURIComponent(productName)}`, { waitUntil: "domcontentloaded" })
		}
		await page.getByRole("button", { name: "More", exact: true }).click()
		await page.getByRole("menuitem", { name: "Delete", exact: true }).click()
		const deleteDialog = page.getByRole("dialog", { name: "Delete Product?", exact: true })
		await screenshot(page, "26-dialog-delete-product.png", deleteDialog)
		await deleteDialog.getByRole("button", { name: "Delete Product", exact: true }).click()
		await page.waitForURL(/\/web\/pd\/products$/)
		await assertResourceAbsent(page, "SD YRP Product", productName, "Product")
		assertPageClean(monitor, "product-edit")
		console.log("OK product-edit: create/edit/stale conflict/media/image picker/release/delete with immediate absence checks")
	} finally {
		try {
			await cleanupRunFixtures(page, identity)
		} finally {
			if (fixtures.directory) rmSync(fixtures.directory, { recursive: true })
		}
	}
}

async function readOnlySuite(page) {
	const monitor = observePage(page)
	const runId = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
	const productName = `PD-E2E-READONLY-${runId}`
	const identity = runIdentity(productName)
	try {
		const realWorkspace = await createWorkspaceProduct(page, productName)
		const uploaded = await uploadAttachment(page, {
			buffer: TRANSPARENT_PNG,
			filename: `${productName}.png`,
			mimeType: "image/png",
			doctype: "SD YRP Product",
			docname: productName,
			fieldname: "product_image",
		})
		await methodMessage(page, `${PRODUCT_METHOD}.delete_and_update_file`, {
			file_url: null, fieldname: "product_image", doctype: "SD YRP Product",
			docname: productName, updated_url: uploaded.file_url, file_name: uploaded.name,
		})
		const releaseName = await methodMessage(page, `${PRODUCT_METHOD}.release_tech_pack`, { doc_name: productName })
		identity.rememberedNames.push(releaseName)
		const releaseWorkspace = await methodMessage(page, `${WORKSPACE}.get_product_release_workspace`, { name: releaseName })
		await assertReachableImages(page, releaseWorkspace, "Throwaway Product Release")

		const productPattern = `**/api/method/${WORKSPACE}.get_product_workspace*`
		const productHandler = (route) => reply(route, {
			...realWorkspace,
			record: { ...realWorkspace.record, product_image: uploaded.file_url },
			permissions: {
				can_read: true, can_create: false, can_write: false,
				can_delete: false, can_print: true, can_release: false,
			},
		})
		await page.route(productPattern, productHandler)
		await page.goto(`${SITE}/web/pd/products/${encodeURIComponent(productName)}`, { waitUntil: "domcontentloaded" })
		await page.locator(".pd-product-workspace__header").waitFor()
		await page.getByText("No rows.", { exact: true }).first().waitFor()
		assert(
			await page.getByText("Use Add Row to create the first line.", { exact: true }).count() === 0,
			"Read-only Product exposed the editable child-table hint",
		)
		const productForbidden = ["Edit", "Add/Update Image", "Upload PDF", "Remove", "Release Tech Pack", "Delete"]
		await assertForbiddenOnTabs(page, PRODUCT_TABS, productForbidden, "Read-only Product")
		await screenshot(page, "27-product-read-only.png")
		await page.unroute(productPattern, productHandler)

		await page.goto(`${SITE}/web/pd/product-releases`, { waitUntil: "domcontentloaded" })
		await page.getByRole("heading", { name: "Product Releases", exact: true }).waitFor()
		await page.locator(".premium-list-table tbody tr").first().waitFor()
		await screenshot(page, "28-product-releases-list.png")
		await openListTools(page, "29-product-releases")
		const releasePattern = `**/api/method/${WORKSPACE}.get_product_release_workspace*`
		const releaseHandler = (route) => reply(route, {
			...releaseWorkspace,
			permissions: {
				...releaseWorkspace.permissions,
				can_create: false, can_write: false, can_delete: false,
			},
		})
		await page.route(releasePattern, releaseHandler)
		await page.goto(`${SITE}/web/pd/product-releases/${encodeURIComponent(releaseName)}`, { waitUntil: "domcontentloaded" })
		await page.locator(".pd-product-workspace__header").waitFor()
		const releaseForbidden = ["Edit", "Add/Update Image", "Upload PDF", "Remove", "Release Tech Pack", "Delete"]
		await assertForbiddenOnTabs(page, RELEASE_TABS, releaseForbidden, "Read-only Product Release")
		assert(await page.getByRole("button", { name: "Print", exact: true }).count() === 1, "Product Release has no Print action")
		await clickTabs(page, RELEASE_TABS, "30-product-release")
		await openPrintAndCapture(page, "38-product-release-print-popup.png")
		await page.unroute(releasePattern, releaseHandler)
		assertPageClean(monitor, "read-only")
		console.log("OK read-only: every Product and Release tab hides mutations; valid throwaway media rendered without substitution")
	} finally {
		await cleanupRunFixtures(page, identity)
	}
}

async function applyLotwiseTemplate(page, config) {
	const rows = await resourceRows(page, config.doctype, { filters: config.filters || [], limit: 1 })
	const section = page.locator(".lotwise-section").filter({
		has: page.getByRole("heading", { name: config.section, exact: true }),
	})
	const button = section.getByRole("button", { name: "Set Template", exact: true })
	if (!rows[0]?.name) {
		assert(!await button.isEnabled(), `${config.section} Set Template is enabled without a fixture`)
		console.warn(`WARN lotwise: no ${config.section} template fixture; verified disabled Set Template reason`)
		return
	}
	await runLotwiseAction(page, "recalculate", () => fillLink(page, config.label, rows[0].name))
	const record = await runLotwiseButton(page, button, config.command)
	assert(Array.isArray(record[config.table]), `${config.command} returned no ${config.table} rows`)
}

async function lotwiseSuite(page) {
	const monitor = observePage(page)
	const runId = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
	const productName = `PD-E2E-LOTWISE-${runId}`
	const identity = runIdentity(productName)
	try {
		await createWorkspaceProduct(page, productName, true)
		await page.goto(`${SITE}/web/pd/lotwise-item-profits`, { waitUntil: "domcontentloaded" })
		await page.getByRole("heading", { name: "Lotwise Item Profit", exact: true }).waitFor()
		await screenshot(page, "40-lotwise-list.png")
		await openListTools(page, "41-lotwise")

		const lots = await resourceRows(page, "SD YRP Lot", { limit: 1 })
		assert(lots[0]?.name, "No Lot exists for the throwaway costing sheet")
		await page.goto(`${SITE}/web/pd/lotwise-item-profits/new`, { waitUntil: "domcontentloaded" })
		await page.getByRole("heading", { name: "New Costing Sheet", exact: true }).waitFor()
		const initial = await runLotwiseButton(
			page,
			page.getByRole("button", { name: "Recalculate", exact: true }),
			"recalculate",
		)
		assert(Number(initial.total_qty || 0) === 0, "New-sheet recalculation did not return zero")
		await screenshot(page, "42-lotwise-zero-totals.png")
		await runLotwiseAction(page, "load_product_sizes", () => fillLink(page, "Product", productName))
		await page.locator(".lotwise-section").filter({ hasText: "Qty and Rate" }).locator("tbody tr").first().waitFor()
		await fillLink(page, "Lot", lots[0].name)
		const typeField = formField(page, "Lot Costing Type")
		await typeField.locator(".p-select").click()
		await page.getByRole("option", { name: "Planned Qty", exact: true }).click()
		const saveResponse = page.waitForResponse((response) => response.url().includes(`${LOTWISE}.save_lotwise_item_profit`) && response.ok())
		await page.getByRole("button", { name: "Save", exact: true }).click()
		const saved = (await (await saveResponse).json()).message
		const createdName = saved.record.name
		identity.rememberedNames.push(createdName)
		await page.waitForURL(new RegExp(`/web/pd/lotwise-item-profits/${encodeURIComponent(createdName)}$`))

		const recalculated = await runLotwiseButton(
			page,
			page.getByRole("button", { name: "Recalculate", exact: true }),
			"recalculate",
		)
		for (const field of LOTWISE_TOTALS) {
			assert(Number.isFinite(Number(recalculated[field] || 0)), `${field} is not finite after recalculation`)
		}
		assert(!((await page.locator("body").innerText()).match(/NaN|Infinity/)), "Zero costing rendered NaN or Infinity")

		const rateButton = page.getByRole("button", { name: "Calculate Rate", exact: true }).first()
		await rateButton.click()
		const rateDialog = page.getByRole("dialog", { name: "Calculate Rate", exact: true })
		await rateDialog.waitFor()
		await screenshot(page, "43-dialog-calculate-rate.png", rateDialog)
		const rateInput = rateDialog.locator("input")
		const confirmRate = rateDialog.getByRole("button", { name: "Calculate Rate", exact: true })
		await rateInput.fill("10")
		await rateInput.press("Tab")
		await confirmRate.click({ trial: true })
		const calculatedRate = await runLotwiseAction(page, "calculate_rate", () => confirmRate.click())
		assert(calculatedRate.qty_rate_chart.every((row) => Number.isFinite(Number(row.rate))), "Calculate Rate returned a non-finite rate")

		await runLotwiseButton(page, page.getByRole("button", { name: "Add Rate", exact: true }), "add_rate")
		await runLotwiseButton(page, page.getByRole("button", { name: "Get Size × Cloth Combination", exact: true }), "build_piece_cloth_weight")
		await runLotwiseButton(page, page.getByRole("button", { name: "Calculate Cloth Qty", exact: true }), "calculate_cloth_qty")
		await applyLotwiseTemplate(page, {
			section: "Production Cost", label: "Production Cost Template", table: "cmt",
			doctype: "SD YRP Lotwise Item Profit Breakup Template", command: "apply_production_cost_template",
		})
		await applyLotwiseTemplate(page, {
			section: "Trade Discounts", label: "Trade Discounts Template", table: "trade_discounts",
			doctype: "SD YRP Lotwise Item Profit Additional Cost Template", filters: [["type", "=", "Discounts"]],
			command: "apply_discount_template",
		})
		await applyLotwiseTemplate(page, {
			section: "Other Costs", label: "Other Costs Template", table: "other_costs",
			doctype: "SD YRP Lotwise Item Profit Additional Cost Template", filters: [["type", "=", "Other"]],
			command: "apply_other_cost_template",
		})
		const fetched = await runLotwiseButton(
			page,
			page.getByRole("button", { name: "Fetch Lot Qty", exact: true }),
			"fetch_lot_qty",
		)
		assert(fetched.lot === lots[0].name, "Fetch Lot Qty returned the wrong throwaway sheet")
		await screenshot(page, "45-lotwise-view.png")

		await screenshot(page, "48-lotwise-created.png")
		await page.getByRole("button", { name: "Delete", exact: true }).click()
		const deleteCreated = page.getByRole("dialog", { name: "Delete Lotwise Item Profit?", exact: true })
		await screenshot(page, "49-dialog-delete-created-lotwise.png", deleteCreated)
		await deleteCreated.getByRole("button", { name: "Delete Costing Sheet", exact: true }).click()
		await page.waitForURL(/\/web\/pd\/lotwise-item-profits$/)
		await assertResourceAbsent(page, "SD YRP Lotwise Item Profit", createdName, "Lotwise Item Profit")
	} finally {
		await cleanupRunFixtures(page, identity)
	}
	assertPageClean(monitor, "lotwise")
	console.log("OK lotwise: throwaway create/delete with immediate absence, finite zero totals and every available command response asserted")
}

function setItemWorkspace() {
	return {
		record: {
			doctype: "SD YRP Product", name: "PD-E2E-SET-MOCK", style_no: "PD-E2E-SET-MOCK",
			item_name: "PD E2E Set", product_group: "Mock", description: "Mock", fabric_details: "Cotton",
			is_set_item: 1, tech_pack_no: 0, sizes: [], product_fabric_composition_details: [],
			product_colours: [],
			product_set_colours: [{ top_colour: "Red", top_colour_code: "#ff0000", bottom_colour: "Blue", bottom_colour_code: "#0000ff" }],
			product_info_extras: [], product_designs: [], product_box_details: [],
		},
		modified: "2026-10-12 10:00:00",
		permissions: { can_read: true, can_write: true, can_create: true, can_delete: false, can_print: true, can_release: true },
		images: { placement: [], trims: [], combination: [], accessories: [] },
		measurement: { groups: {}, images: [] },
		colours: {
			is_set_item: true,
			top: [{ colour: "Red", colour_code: "#ff0000", image: "" }],
			bottom: [{ colour: "Blue", colour_code: "#0000ff", image: "" }],
			all: [],
		},
		costing: [], releases: [], print_formats: ["Essdee Product Tech Pack"], link_filters: {},
	}
}

async function setItemSuite(page) {
	const monitor = observePage(page)
	await page.route("**/api/method/**", async (route) => {
		const method = new URL(route.request().url()).pathname.split("/api/method/")[1]
		if (method === `${WORKSPACE}.get_product_workspace`) return reply(route, setItemWorkspace())
		if (method === `${IMAGE_METHOD}.get_image_list`) {
			return reply(route, [{ image_name: "PD-E2E-TRIM", image_title: "Mock Trim", image_url: "" }])
		}
		return route.continue()
	})
	await page.goto(`${SITE}/web/pd/products/PD-E2E-SET-MOCK/edit`, { waitUntil: "domcontentloaded" })
	await page.getByRole("tab", { name: "Colours", exact: true }).click()
	const panel = page.locator(".pd-media-panel").filter({ hasText: "Trim Colour Combination" })
	await panel.getByPlaceholder("Enter at least 2 characters").fill("tr")
	await panel.locator(".product-trim-combination__results button").first().click()
	await panel.getByText("Bottom", { exact: true }).click()
	const colours = await panel.locator(".product-colour-option__chip").allTextContents()
	assert(JSON.stringify(colours) === JSON.stringify(["Blue"]), `Bottom part exposed the wrong colours: ${JSON.stringify(colours)}`)
	assert(await panel.getByText("Red", { exact: true }).count() === 0, "Top colour remained selectable for Bottom")
	await screenshot(page, "50-set-item-bottom-colours.png")
	assertPageClean(monitor, "set-item")
	console.log("OK set-item: Bottom trim mapping offers only the Bottom colour")
}

sourceChecks()
if (requestedSuite === "source") process.exit(0)
const suiteNames = ["launcher", "products", "product-edit", "read-only", "lotwise", "set-item"]
assert([...suiteNames, "all", "screens"].includes(requestedSuite), `Unknown suite: ${requestedSuite}`)
const browser = await chromium.launch({ headless: true })
let failure

try {
	for (const [name, run] of [
		["launcher", launcherSuite],
		["products", productsSuite],
		["product-edit", productEditSuite],
		["read-only", readOnlySuite],
		["lotwise", lotwiseSuite],
		["set-item", setItemSuite],
	]) {
		if (![name, "all", "screens"].includes(requestedSuite)) continue
		const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
		const page = await context.newPage()
		try {
			await login(page)
			await run(page)
		} catch (reason) {
			failure = new Error(`${name}: ${reason.message}`)
			break
		} finally {
			await context.close()
		}
	}
} finally {
	await browser.close()
}

if (failure) throw failure
if (requestedSuite === "screens") console.log(`OK screens: captured PD pages and dialogs in ${SCREEN_DIRECTORY}`)
