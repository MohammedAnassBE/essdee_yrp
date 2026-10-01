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

export async function visibleTextBelowMinimum(page, minPx = 11) {
	return page.locator("body *").evaluateAll((elements, minimum) => elements.flatMap((element) => {
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

const suites = {
	tokens: tokensSuite,
	shell: shellSuite,
	"cutting-entry": cuttingEntrySuite,
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
