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
	const geometry = await page.evaluate(() => ({ viewport: innerWidth, page: document.documentElement.scrollWidth }))
	assert(geometry.page <= geometry.viewport + 1, `${label} overflows: ${JSON.stringify(geometry)}`)
}

function sourceChecks() {
	const router = readFileSync("frontend/src/router/index.js", "utf8")
	const list = router.indexOf('path: "/sales/production-orders"')
	const create = router.indexOf('path: "/sales/production-orders/new"')
	const edit = router.indexOf('path: "/sales/production-orders/:productionOrderId/edit"')
	const view = router.indexOf('path: "/sales/production-orders/:productionOrderId"', edit + 1)
	assert(list >= 0, "Sales Production Order list route is missing")
	if (!["launcher", "source"].includes(suite)) {
		assert(create > list && edit > create && view > edit, "Sales Production Order routes are missing or ordered unsafely")
	}
	const api = readFileSync("frontend/src/api/sales.js", "utf8")
	for (const method of ["get_capabilities", "get_production_order_workspace", "get_production_order_editor", "save_production_order", "execute_production_order_command", "get_ppo_report", "get_ppo_dispatch_summary", "download_ppo_report"]) {
		assert(api.includes(method), `Sales API is missing ${method}`)
	}
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

sourceChecks()
if (suite === "source") process.exit(0)
const browser = await chromium.launch({ headless: true })
try {
	const page = await browser.newPage({ viewport: { width: 1280, height: 900 } })
	await login(page)
	await launcherSuite(page)
} finally {
	await browser.close()
}
