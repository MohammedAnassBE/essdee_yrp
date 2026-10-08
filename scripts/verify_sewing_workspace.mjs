#!/usr/bin/env node

import { createRequire } from "node:module"
import { readFileSync } from "node:fs"
import { fileURLToPath } from "node:url"
import { createServer } from "../frontend/node_modules/vite/dist/node/index.js"

const require = createRequire("/home/anas/.claude/playwright/package.json")
const { chromium } = require("playwright")
const SITE = process.env.ESSDEE_TEST_SITE || "http://erp-migration-test.site:8001"
const suite = process.argv[2] || "launcher"
const definitions = [
	["plans", "Sewing Plan", "/web/sewing/plans"],
	["reports", "Reports", "/web/sewing/reports"],
	["attendance", "Attendance Report", "/web/sewing/attendance"],
]
const flags = { can_read: true, can_create: false, can_write: false, can_delete: false, can_submit: false, can_report: true }
const capabilities = {
	sections: Object.fromEntries(definitions.map(([key, label]) => [key, { label, ...flags }])),
	plan_actions: {
		entry: { label: "Sewing Plan Entry", doctype: "SD YRP Sewing Plan Entry Detail", ...flags },
		plan: { label: "Sewing Plan", doctype: "SD YRP Sewing Plan", ...flags },
		goods_received_note: { label: "Goods Received Note", doctype: "YRP Goods Received Note", ...flags },
	},
	reports: Object.fromEntries(["status_summary", "dpr", "scr", "monthly_summary", "item_summary"].map((key) => [key, { ...flags }])),
}
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
async function navigate(page, path) {
	await page.goto(`${SITE}${path}`, { waitUntil: "domcontentloaded" })
}
async function selectUnit(page, value) {
	await page.getByRole("combobox", { name: "Sewing Unit", exact: true }).fill(value)
	await page.getByRole("option", { name: value, exact: true }).click()
	await page.waitForURL((url) => url.searchParams.get("supplier") === value)
}
async function noOverflow(page, label) {
	const geometry = await page.evaluate(() => ({ viewport: innerWidth, page: document.documentElement.scrollWidth }))
	assert(geometry.page <= geometry.viewport + 1, `${label} page overflow: ${JSON.stringify(geometry)}`)
}

// These browser tests catch missing/wrong cards, capability leaks, missing retry,
// unfiltered Supplier searches, lost route context, eager data loads and overflow.
async function launcherSuite(page) {
	const state = { payload: capabilities, error: "", delay: 0 }
	const searchRequests = []
	const dataRequests = []
	const browserErrors = []
	page.on("pageerror", (error) => browserErrors.push(error.message))
	await page.route("**/api/method/**", async (route) => {
		const method = new URL(route.request().url()).pathname.split("/api/method/")[1]
		if (method === "essdee_yrp.sewing.web_workspace.get_capabilities") {
			if (state.delay) await new Promise((resolve) => setTimeout(resolve, state.delay))
			return route.fulfill({ status: state.error ? 500 : 200, contentType: "application/json", body: JSON.stringify({ message: state.error || state.payload }) })
		}
		if (method === "essdee_yrp.api.link_search.link_search") {
			searchRequests.push(JSON.parse(route.request().postData() || "{}"))
			return route.fulfill({ contentType: "application/json", body: JSON.stringify({ message: [{ name: "UNIT-A", label: "UNIT-A" }, { name: "UNIT-B", label: "UNIT-B" }] }) })
		}
		if (method.includes("sewing")) dataRequests.push(method)
		return route.continue()
	})
	page.on("request", (request) => {
		if (request.url().includes("/api/resource/") && /Sewing|sewing/.test(decodeURIComponent(request.url()))) dataRequests.push(request.url())
	})
	await navigate(page, "/web/sewing")
	await page.locator(".department-page").waitFor()
	await page.waitForTimeout(500)
	assert(await page.locator(".workspace-launcher").count() === 1, "Sewing launcher is absent; the department still renders its placeholder")
	const cards = page.locator(".workspace-launcher__card")
	await cards.nth(2).waitFor()
	assert(await cards.count() === 3, "Sewing must have exactly three launcher cards")
	assert(JSON.stringify(await cards.locator("strong").allTextContents()) === JSON.stringify(["Sewing Plan", "Reports", "Attendance Report"]), "Sewing launcher labels differ from the three approved destinations")
	for (const [, label, href] of definitions) {
		assert(await page.getByRole("link", { name: new RegExp(`^${label}`) }).getAttribute("href") === href, `${label} has wrong href`)
	}
	for (const forbidden of ["Open Work Orders", "Today Output", "Pending Inspections"]) {
		assert(!(await page.locator(".department-page").innerText()).includes(forbidden), `Forbidden launcher metric: ${forbidden}`)
	}
	await cards.first().focus()
	assert(await cards.first().evaluate((element) => getComputedStyle(element).outlineStyle !== "none"), "Launcher needs visible keyboard focus")
	await selectUnit(page, "UNIT-A")
	assert(searchRequests.some((request) => request.doctype === "Supplier" && request.filters?.is_company_location === 1), "Supplier search lacks company-location filter")
	for (const [, label, href] of definitions.slice(0, 2)) {
		assert(await page.getByRole("link", { name: new RegExp(`^${label}`) }).getAttribute("href") === `${href}?supplier=UNIT-A`, `${label} loses Supplier query`)
	}
	await cards.first().click()
	await page.waitForURL("**/web/sewing/plans?supplier=UNIT-A")
	await page.locator("[data-sewing-destination='plans']").waitFor()
	assert(await page.locator("[data-sewing-destination]").count() === 1, "Inactive destinations mounted")
	await page.reload({ waitUntil: "domcontentloaded" })
	await page.locator("[data-sewing-destination='plans']").waitFor()
	assert(await page.getByRole("combobox", { name: "Sewing Unit", exact: true }).inputValue() === "UNIT-A", "Reload loses Supplier selection")
	await selectUnit(page, "UNIT-B")
	await page.goBack()
	await page.waitForURL("**/web/sewing?supplier=UNIT-A")
	await cards.nth(2).waitFor()
	assert(await page.getByRole("combobox", { name: "Sewing Unit", exact: true }).inputValue() === "UNIT-A", "Back navigation loses Supplier selection")
	await page.locator(".sewing-unit-picker .p-autocomplete-clear-icon").click()
	await page.waitForURL((url) => !url.searchParams.has("supplier"))
	assert(await page.getByRole("link", { name: /^Sewing Plan/ }).getAttribute("href") === "/web/sewing/plans", "Clearing the picker leaves stale Supplier in scoped links")
	for (const key of ["plans", "reports"]) {
		dataRequests.length = 0
		await navigate(page, `/web/sewing/${key}`)
		await page.getByText(`Select a Sewing Unit to view ${key === "plans" ? "Sewing Plan" : "Reports"}.`, { exact: true }).waitFor()
		assert(await page.locator("[data-sewing-destination]").count() === 0, "Scoped content mounts without Supplier")
		assert(dataRequests.length === 0, `Missing Supplier issued data requests: ${dataRequests}`)
	}
	await navigate(page, "/web/sewing/attendance")
	await page.locator("[data-sewing-destination='attendance']").waitFor()
	assert(await page.getByRole("combobox", { name: "Sewing Unit", exact: true }).count() === 0, "Attendance must be global")
	state.payload = { ...capabilities, sections: { ...capabilities.sections, plans: { ...capabilities.sections.plans, can_read: false }, attendance: { ...capabilities.sections.attendance, can_read: false } } }
	await navigate(page, "/web/sewing")
	await cards.first().waitFor()
	assert(JSON.stringify(await cards.locator("strong").allTextContents()) === JSON.stringify(["Reports"]), "Explicit denied capabilities leaked cards")
	state.payload = { ...capabilities, sections: { attendance: capabilities.sections.attendance } }
	await navigate(page, "/web/sewing")
	await cards.first().waitFor()
	assert(JSON.stringify(await cards.locator("strong").allTextContents()) === JSON.stringify(["Attendance Report"]), "Permission-hidden cards leaked")
	await navigate(page, "/web/sewing/plans?supplier=UNIT-A")
	await page.getByText("You do not have permission to view Sewing Plan.", { exact: true }).waitFor()
	assert(await page.locator("[data-sewing-destination]").count() === 0, "Denied destination mounted")
	state.payload = { ...capabilities, sections: {} }
	await navigate(page, "/web/sewing")
	await page.getByText("No permitted Sewing workspaces", { exact: true }).waitFor()
	assert(await cards.count() === 0, "No-permission launcher leaks destinations")
	state.payload = capabilities
	state.error = "Capability service unavailable"
	await navigate(page, "/web/sewing")
	await page.getByText(state.error, { exact: true }).waitFor()
	state.error = ""
	await page.getByRole("button", { name: "Retry", exact: true }).click()
	await cards.nth(2).waitFor()
	state.delay = 700
	await navigate(page, "/web/sewing")
	await page.getByRole("status").filter({ hasText: "Loading" }).waitFor()
	await cards.nth(2).waitFor()
	state.delay = 0
	for (const width of [390, 900, 1280, 1600]) {
		await page.setViewportSize({ width, height: 900 })
		for (const path of ["/web/sewing", "/web/sewing/plans", "/web/sewing/reports?supplier=UNIT-A", "/web/sewing/attendance"]) {
			await navigate(page, path)
			await page.locator(".sewing-workspace-shell").waitFor()
			await page.locator(".sewing-workspace-shell[aria-busy='false']").waitFor()
			await page.evaluate(async () => {
				await document.fonts.ready
				await Promise.all(document.getAnimations().map((animation) => animation.finished.catch(() => {})))
			})
			await noOverflow(page, `${path} at ${width}px`)
			if (process.env.ESSDEE_SEWING_SCREENSHOTS && path === "/web/sewing") {
				await page.screenshot({ path: `${process.env.ESSDEE_SEWING_SCREENSHOTS}/sewing-launcher-${width}.png`, fullPage: true, animations: "disabled" })
			}
		}
	}
	assert(browserErrors.length === 0, `Sewing browser errors: ${browserErrors.join("\n")}`)
	console.log("PASS launcher: three cards, permissions, retry/loading, filtered Supplier search, query/reload/back, missing-selection guard, global attendance, active-only mount, 16 viewport checks")
}

// Execute the real composable and real Vue Router with deferred responses. This
// catches delayed old-unit results, failed-request invalidation, and unmount leaks
// without introducing data requests or test hooks into the production shell.
async function contextSuite(browser) {
	const harness = `
import { createApp, h, ref, watch } from 'vue';
import { createRouter, createMemoryHistory } from 'vue-router';
import { useSewingContext } from '/src/departments/sewing/useSewingContext.js';
const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/sewing', component: { render: () => null } }] });
await router.push('/sewing?keep=yes');
window.pending = {};
window.app = createApp({ setup() {
 const context = useSewingContext(); window.context = context; window.router = router;
 const result = ref('');
 watch(context.supplier, async (supplier) => {
  if (!supplier) return;
  const generation = context.beginRequest();
  const value = await new Promise(resolve => window.pending[supplier] = resolve);
  if (context.isCurrent(generation)) result.value = value;
 }, { flush: 'sync' });
 return () => h('main', [h('button', { onClick: () => context.setSupplier('UNIT-A') }, 'A'), h('button', { onClick: () => context.setSupplier('UNIT-B') }, 'B'), h('output', result.value)]);
}}).use(router); window.app.mount('#app');
`
	const html = '<!doctype html><html><body><div id="app"></div><script type="module" src="/__sewing-context-test.js"></script></body></html>'
	const server = await createServer({
		root: fileURLToPath(new URL("../frontend", import.meta.url)),
		server: { host: "127.0.0.1", port: 0 },
		plugins: [{
			name: "sewing-context-verifier",
			resolveId(id) { if (id === "/__sewing-context-test.js") return "\0sewing-context-test" },
			load(id) { if (id === "\0sewing-context-test") return harness },
			configureServer(server) {
				server.middlewares.use((request, response, next) => {
					if (request.url !== "/__sewing-context-test") return next()
					response.setHeader("Content-Type", "text/html")
					response.end(html)
				})
			},
		}],
	})
	await server.listen()
	const page = await browser.newPage()
	try {
		await page.goto(`http://127.0.0.1:${server.httpServer.address().port}/__sewing-context-test`)
		await page.getByRole("button", { name: "A", exact: true }).click()
		await page.waitForFunction(() => Boolean(window.pending["UNIT-A"]))
		const oldGeneration = await page.evaluate(() => window.context.requestGeneration.value)
		await page.getByRole("button", { name: "B", exact: true }).click()
		await page.waitForFunction(() => Boolean(window.pending["UNIT-B"]))
		assert(await page.evaluate(() => window.context.requestGeneration.value) > oldGeneration, "Supplier change must monotonically invalidate requests")
		await page.evaluate(() => window.pending["UNIT-B"]("Current B response"))
		await page.getByText("Current B response", { exact: true }).waitFor()
		await page.evaluate(() => window.pending["UNIT-A"]("Stale A response"))
		assert(await page.locator("output").textContent() === "Current B response", "Delayed A response overwrote B")
		assert(await page.evaluate(() => window.router.currentRoute.value.query.keep) === "yes", "Supplier selection discarded unrelated query")
		assert(await page.evaluate(() => window.context.isCurrent(window.context.beginRequest())) === true, "New request must be current")
		assert(await page.evaluate(async () => { const generation = window.context.beginRequest(); await window.router.replace('/sewing?keep=yes'); return window.context.isCurrent(generation) }) === false, "Clearing Supplier did not reject stale response")
		assert(await page.evaluate(() => { const generation = window.context.beginRequest(); window.app.unmount(); return window.context.isCurrent(generation) }) === false, "Unmounted context still accepts a response")
		console.log("PASS context: real Vue/Router rapid A to B stale-response rejection, monotonic generation, query preservation, cleared selection and unmount invalidation")
	} finally { await page.close(); await server.close() }
}

assert(["launcher", "all"].includes(suite), `Unknown Sewing suite: ${suite}`)
const browser = await chromium.launch({ headless: true })
try {
	const page = await browser.newPage()
	page.setDefaultTimeout(20_000)
	await login(page)
	await launcherSuite(page)
	await contextSuite(browser)
} finally { await browser.close() }
