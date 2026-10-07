#!/usr/bin/env node

import { createRequire } from "node:module"
import { readFileSync } from "node:fs"

const require = createRequire("/home/anas/.claude/playwright/package.json")
const { chromium } = require("playwright")

const SITE = process.env.SITE || "http://erp-migration-test.site:8001"
const CREDENTIALS = "/home/anas/.frappe-debug-creds-mrp3"
const WORK_ORDER = process.argv[2] || "YRP-WO-2026-00022"

function assert(condition, message) {
	if (!condition) throw new Error(message)
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

async function waitForForm(page, doctype, name) {
	await page.waitForFunction(
		([expectedDoctype, expectedName]) => (
			window.cur_frm
			&& cur_frm.doctype === expectedDoctype
			&& cur_frm.doc.name === expectedName
			&& !cur_frm.__isloading
		),
		[doctype, name],
		{ timeout: 60_000 },
	)
}

const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
const page = await context.newPage()
const pageErrors = []
const summaryFailures = []
page.on("pageerror", (error) => pageErrors.push(error.message))
page.on("console", (message) => {
	if (message.type() === "error") pageErrors.push(message.text())
})
page.on("response", (response) => {
	if (
		response.url().includes("get_work_order_summary")
		&& !response.ok()
	) {
		summaryFailures.push(`${response.status()} ${response.url()}`)
	}
})

try {
	await login(page)
	await page.goto(`${SITE}/app/yrp-work-order/${encodeURIComponent(WORK_ORDER)}`, {
		waitUntil: "domcontentloaded",
	})
	await waitForForm(page, "YRP Work Order", WORK_ORDER)
	await page.locator(".form-tabs .nav-link")
		.filter({ hasText: "Summary" })
		.click()
	const summary = page.locator(".essdee-work-order-summary")
	await summary.waitFor({ state: "visible", timeout: 30_000 })

	const state = await summary.evaluate((element) => {
		const text = element.textContent.replace(/\s+/g, " ").trim()
		const tables = [...element.querySelectorAll("table")].map((table) => ({
			headers: [...table.querySelectorAll("thead th")].map((cell) => cell.textContent.trim()),
			rows: table.querySelectorAll("tbody tr").length,
			painted: table.offsetParent !== null && table.getBoundingClientRect().width > 100,
		}))
		return {
			text,
			tables,
			panels: element.querySelectorAll(".summary-panel").length,
			sourceLinks: element.querySelectorAll('a[href*="yrp-goods-received-note"]').length,
			typePills: [...element.querySelectorAll(".type-pill")].map((node) => node.textContent.trim()),
			valuation: [...element.querySelectorAll(".valuation-flow strong")].map((node) => node.textContent.trim()),
		}
	})

	assert(state.panels >= 4, `Expected summary panels, got ${JSON.stringify(state)}`)
	for (const label of [
		"Issued",
		"Received",
		"Pending",
		"Planned process cost",
		"Posted valuation",
		"Input value",
		"Posted process value",
		"Output value",
		"Debits",
	]) {
		assert(state.text.includes(label), `Summary is missing '${label}'`)
	}
	assert(state.tables.length >= 2, "Movement tables did not render")
	assert(state.tables.every((table) => table.painted), `A summary table is not painted: ${JSON.stringify(state.tables)}`)
	assert(state.typePills.length > 0, "Received Type did not render")
	assert(state.valuation.length === 3, `Valuation flow is incomplete: ${JSON.stringify(state.valuation)}`)
	assert(summaryFailures.length === 0, `Summary request failures: ${JSON.stringify(summaryFailures)}`)
	assert(pageErrors.length === 0, `Desk page errors: ${JSON.stringify(pageErrors)}`)

	const screenshot = `/tmp/yrp-work-order-summary-${WORK_ORDER}.png`
	await page.screenshot({ path: screenshot, fullPage: true })
	console.log(JSON.stringify({
		passed: true,
		workOrder: WORK_ORDER,
		sourceLinks: state.sourceLinks,
		receivedTypes: state.typePills,
		valuation: state.valuation,
		screenshot,
	}, null, 2))
} finally {
	await context.close()
	await browser.close()
}
