#!/usr/bin/env node

import { createRequire } from "node:module"
import { readFileSync } from "node:fs"

const require = createRequire("/home/anas/.claude/playwright/package.json")
const { chromium } = require("playwright")
const SITE = "http://erp-migration-test.site:8001"
const CREDENTIALS = "/home/anas/.frappe-debug-creds-mrp3"
const suite = process.argv[2] || "all"

function assert(condition, message) {
	if (!condition) throw new Error(message)
}

const sectionDefinitions = [
	["movements", "Cut Panel Movement", "/web/cut-panel-store/movements"],
	["work_orders", "Work Orders", "/web/cut-panel-store/work-orders"],
	["cut_bundle_edits", "Cut Bundle Edit", "/web/cut-panel-store/cut-bundle-edits"],
	["box_stickers", "Box Sticker Print", "/web/cut-panel-store/box-sticker-prints"],
	["excel_stickers", "Excel Sticker Print", "/web/cut-panel-store/excel-sticker-prints"],
	["reports", "Reports", "/web/cut-panel-store/reports"],
]

const capabilities = {
	sections: Object.fromEntries(sectionDefinitions.map(([key, label]) => [key, {
		label,
		doctype: key === "reports" ? undefined : key,
		can_read: true,
		can_create: true,
	}])),
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

async function installCapabilityMock(page, state) {
	await page.route("**/api/method/essdee_yrp.cut_panel_store.web_workspace.get_capabilities*", async (route) => {
		if (state.delay) await new Promise((resolve) => setTimeout(resolve, state.delay))
		if (state.error) {
			return route.fulfill({
				status: 500,
				contentType: "application/json",
				body: JSON.stringify({ message: state.error }),
			})
		}
		return route.fulfill({
			status: 200,
			contentType: "application/json",
			body: JSON.stringify({ message: state.payload }),
		})
	})
}

async function launcherSuite(page) {
	const state = { payload: capabilities, delay: 0, error: "" }
	await installCapabilityMock(page, state)
	await page.goto(`${SITE}/web/cut-panel-store`, { waitUntil: "domcontentloaded" })
	const launcher = page.locator(".workspace-launcher")
	await launcher.waitFor({ timeout: 20_000 })

	const cards = launcher.locator(".workspace-launcher__card")
	await cards.nth(sectionDefinitions.length - 1).waitFor({ timeout: 20_000 })
	const cardCount = await cards.count()
	assert(cardCount === sectionDefinitions.length, `Expected six Cut Panel Store cards, got ${cardCount}`)
	assert(
		JSON.stringify((await cards.locator("strong").allTextContents()).map((value) => value.trim()))
			=== JSON.stringify(sectionDefinitions.map(([, label]) => label)),
		`Unexpected Cut Panel Store cards: ${JSON.stringify(await cards.locator("strong").allTextContents())}`,
	)
	assert(await page.getByText("Raw Sticker Print", { exact: true }).count() === 0, "Raw Sticker Print must not be exposed")
	for (const [, label, href] of sectionDefinitions) {
		const link = page.getByRole("link", { name: new RegExp(`^${label}`) })
		assert(await link.count() === 1, `${label} card is missing`)
		assert(await link.getAttribute("href") === href, `${label} points to the wrong route`)
	}

	for (const [key, label, href] of sectionDefinitions) {
		await page.goto(`${SITE}${href}`, { waitUntil: "domcontentloaded" })
		const section = page.locator(".cut-panel-store-section")
		await section.waitFor({ timeout: 20_000 })
		assert(await section.getAttribute("aria-label") === label, `${key} route rendered the wrong section`)
	}

	state.payload = { sections: {} }
	await page.goto(`${SITE}/web/cut-panel-store/movements`, { waitUntil: "domcontentloaded" })
	await page.getByText("You do not have permission to view Cut Panel Movement.", { exact: true }).waitFor()

	state.payload = capabilities
	state.delay = 1_000
	const loadingNavigation = page.goto(`${SITE}/web/cut-panel-store/reports`, { waitUntil: "domcontentloaded" })
	await page.locator(".cut-panel-store-section__loading").waitFor({ timeout: 20_000 })
	await loadingNavigation
	state.delay = 0

	state.error = "Capability service unavailable"
	await page.goto(`${SITE}/web/cut-panel-store/box-sticker-prints`, { waitUntil: "domcontentloaded" })
	await page.getByText("Capability service unavailable", { exact: true }).waitFor({ timeout: 20_000 })
}

const suites = {
	launcher: launcherSuite,
}

const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
const page = await context.newPage()
const browserErrors = []
page.on("pageerror", (error) => browserErrors.push(error.message))

try {
	await login(page)
	if (suite === "all") {
		for (const run of Object.values(suites)) await run(page)
	} else {
		assert(suites[suite], `Unknown Cut Panel Store verification suite: ${suite}`)
		await suites[suite](page)
	}
	assert(browserErrors.length === 0, `Browser errors: ${browserErrors.join("; ")}`)
	console.log(JSON.stringify({ passed: true, suite, browserErrors }, null, 2))
} finally {
	await browser.close()
}
