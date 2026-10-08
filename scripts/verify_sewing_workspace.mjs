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
	const state = { payload: capabilities, error: "", errorStatus: 500, delay: 0 }
	const searchRequests = []
	const dataRequests = []
	const browserErrors = []
	page.on("pageerror", (error) => browserErrors.push(error.message))
	await page.route("**/api/method/**", async (route) => {
		const method = new URL(route.request().url()).pathname.split("/api/method/")[1]
		if (method === "essdee_yrp.sewing.web_workspace.get_capabilities") {
			if (state.delay) await new Promise((resolve) => setTimeout(resolve, state.delay))
			const payload = state.error && state.errorStatus === 403
				? { exc_type: "PermissionError", exc: '["frappe.exceptions.PermissionError"]', _server_messages: JSON.stringify([JSON.stringify({ message: state.error, raise_exception: 1 })]) }
				: { message: state.error || state.payload }
			return route.fulfill({ status: state.error ? state.errorStatus : 200, contentType: "application/json", body: JSON.stringify(payload) })
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
	await page.goForward()
	await page.waitForURL("**/web/sewing/plans?supplier=UNIT-B")
	await page.locator("[data-sewing-destination='plans']").waitFor()
	assert(await page.getByRole("combobox", { name: "Sewing Unit", exact: true }).inputValue() === "UNIT-B", "Forward navigation loses Supplier selection")
	await page.goBack()
	await page.waitForURL("**/web/sewing?supplier=UNIT-A")
	await cards.nth(2).waitFor()
	await page.locator(".sewing-unit-picker .p-autocomplete-clear-icon").click()
	await page.waitForURL((url) => !url.searchParams.has("supplier"))
	assert(await page.getByRole("link", { name: /^Sewing Plan/ }).getAttribute("href") === "/web/sewing/plans", "Clearing the picker leaves stale Supplier in scoped links")
	for (const key of ["plans", "reports"]) {
		for (const query of ["", "?supplier", "?supplier=", "?supplier=UNIT-A&supplier=UNIT-B"]) {
			dataRequests.length = 0
			await navigate(page, `/web/sewing/${key}${query}`)
			await page.getByText(`Select a Sewing Unit to view ${key === "plans" ? "Sewing Plan" : "Reports"}.`, { exact: true }).waitFor()
			assert(await page.getByRole("combobox", { name: "Sewing Unit", exact: true }).inputValue() === "", `Invalid Supplier query populated picker: ${query}`)
			assert(await page.locator("[data-sewing-destination]").count() === 0, `Scoped content mounts with missing/malformed Supplier: ${query}`)
			assert(dataRequests.length === 0, `Missing/malformed Supplier issued data requests: ${query}: ${dataRequests}`)
		}
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
	state.errorStatus = 403
	state.error = "Sewing access was denied. Please retry."
	await navigate(page, "/web/sewing")
	await page.getByRole("alert").getByText(state.error, { exact: true }).waitFor()
	assert(await cards.count() === 0, "HTTP 403 leaves Sewing cards visible")
	state.error = ""
	await page.getByRole("button", { name: "Retry", exact: true }).click()
	await cards.nth(2).waitFor()
	assert(await page.getByRole("alert").count() === 0, "HTTP 403 error remains after successful Retry")
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
	console.log("PASS launcher: three cards, permissions, 500/403 Frappe retry/loading, filtered Supplier search, query/reload/back/forward, missing/blank/malformed Supplier guard, global attendance, active-only mount, 16 viewport checks")
}

// Execute the real composable and real Vue Router with deferred responses. This
// catches delayed old-unit results, failed-request invalidation, and unmount leaks
// without introducing data requests or test hooks into the production shell.
async function contextSuite(browser) {
	const harness = `
import { createApp, h, ref, watch } from 'vue';
import { createRouter, createMemoryHistory } from 'vue-router';
import PrimeVue from 'primevue/config';
import { useSewingContext } from '/src/departments/sewing/useSewingContext.js';
import SewingWorkspaceShell from '/src/departments/sewing/SewingWorkspaceShell.vue';
const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/sewing/:section?', component: { render: () => null } }] });
await router.push('/sewing/plans?keep=yes');
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
 return () => h('main', [h('button', { onClick: () => context.setSupplier('UNIT-A') }, 'A'), h('button', { onClick: () => context.setSupplier('UNIT-B') }, 'B'), h('output', result.value), h(SewingWorkspaceShell, { title: 'Sewing Plan', section: 'plans' }, () => h('p', 'Development shell content'))]);
}}).use(router).use(PrimeVue); window.app.mount('#app');
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
	const warnings = []
	page.on("console", (message) => { if (message.type() === "warning") warnings.push(message.text()) })
	try {
		await page.route("**/api/method/essdee_yrp.sewing.web_workspace.get_capabilities", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ message: capabilities }) }))
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
		await page.getByRole("button", { name: "Back to Sewing", exact: true }).click()
		await page.waitForFunction(() => window.router.currentRoute.value.path === "/sewing")
		assert(await page.evaluate(() => window.router.currentRoute.value.query.supplier) === "UNIT-B", "Development shell back navigation loses Supplier")
		assert(warnings.length === 0, `Development Sewing shell emits Vue warnings: ${warnings.join("\n")}`)
		assert(await page.evaluate(async () => { const generation = window.context.beginRequest(); await window.router.replace('/sewing?keep=yes'); return window.context.isCurrent(generation) }) === false, "Clearing Supplier did not reject stale response")
		assert(await page.evaluate(() => { const generation = window.context.beginRequest(); window.app.unmount(); return window.context.isCurrent(generation) }) === false, "Unmounted context still accepts a response")
		console.log("PASS context: real Vue/Router rapid A to B stale-response rejection, monotonic generation, query preservation, warning-free development shell, cleared selection and unmount invalidation")
	} finally { await page.close(); await server.close() }
}

// Render the actual route component, PrimeVue controls and API adapter. Only
// network boundaries are mocked: removing a tab, row ID, lock or reload breaks
// an observable assertion below.
async function planEntrySuite(browser) {
	const harness = `
import { createApp } from 'vue';
import { createRouter, createMemoryHistory, RouterView } from 'vue-router';
import PrimeVue from 'primevue/config';
import Aura from '@primeuix/themes/aura';
import SewingPlans from '/src/departments/sewing/SewingPlans.vue';
import '@fontsource-variable/inter'; import 'primeicons/primeicons.css';
import '/src/styles/main.css'; import '/src/styles/enterprise.css';
const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/sewing/plans', component: SewingPlans }] });
await router.push('/sewing/plans?supplier=UNIT-A'); window.router = router;
createApp(RouterView).use(router).use(PrimeVue, { theme: { preset: Aura, options: { darkModeSelector: false } } }).mount('#app');`
	const server = await createServer({
		root: fileURLToPath(new URL("../frontend", import.meta.url)), server: { host: "127.0.0.1", port: 0 },
		plugins: [{ name: "sewing-plan-verifier", resolveId(id) { if (id === "/__plan-test.js") return "\0plan-test" }, load(id) { if (id === "\0plan-test") return harness }, configureServer(server) { server.middlewares.use((req, res, next) => { if (req.url !== "/__plan-test") return next(); res.setHeader("Content-Type", "text/html"); res.end('<!doctype html><html><body><div id="app"></div><script type="module" src="/__plan-test.js"></script></body></html>') }) } }],
	})
	await server.listen()
	const page = await browser.newPage({ viewport: { width: 1280, height: 900 } })
	page.setDefaultTimeout(10_000)
	const requests = [], errors = []
	const sizes = ["XS", "S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL", "6XL"]
	function plan(name = "PLAN-A") { return { details: { item: "T-Shirt", lot: "LOT-A", supplier: "UNIT-A", work_order: "WO-A", work_order_status: "Open", primary_values: sizes }, colours: { Navy: { colour: "Navy", variant_colour: "Navy", part: null, set_combination: { major_colour: "Navy" }, values: Object.fromEntries(sizes.map((size, i) => [size, { order_detail: `${name}-ROW-${i}`, item_variant: `UNTRUSTED-${size}`, order_qty: 100, sewing_in: 20, sewing_in_remaining: 80, data_entry: 0, pre_final: 2, final_inspection: 2 }])) } } } }
	const entry = { data: { "LOT-A": { "PLAN-A": plan(), "PLAN-OTHER": plan("PLAN-OTHER") } }, input_types: ["Sewing In", "Sewing Out"], diff: { sewing_in: "order_qty", sewing_out: "sewing_in" }, allowances: { sewing_in: 5, sewing_out: 0 }, default_received_type: "" }
	const state = { dashboard: [{ input_type: "Sewing In", qty: 40 }, { input_type: "Sewing Out", qty: 15 }], dashboardError: "", dashboardDelay: 250, dashboardHold: null, entryError: "", entryHold: null, submitError: "", inspectionError: "", submitDelay: 0, loads: 0, authoritativeQty: 20 }
	page.on("pageerror", e => errors.push(e.message))
	await page.route("**/api/method/**", async route => {
		const method = route.request().url().split("/api/method/")[1], args = JSON.parse(route.request().postData() || "{}")
		requests.push({ method, args })
		let value = null, error = ""
		if (method.endsWith("get_capabilities")) value = { ...capabilities, plan_actions: { entry: { ...flags, can_create: true }, plan: { ...flags, can_write: true } } }
		else if (method.endsWith("get_dashboard_data")) { value = structuredClone(state.dashboard); error = state.dashboardError; if (state.dashboardHold) { const hold = state.dashboardHold; state.dashboardHold = null; await hold } else await new Promise(r => setTimeout(r, state.dashboardDelay)) }
		else if (method.endsWith("get_data_entry_data")) { state.loads++; value = structuredClone(entry); error = state.entryError; value.data["LOT-A"]["PLAN-A"].colours.Navy.values.XS.sewing_in = state.authoritativeQty; if (args.supplier === "UNIT-B") value.data = {}; if (state.entryHold) { const hold = state.entryHold; state.entryHold = null; await hold } }
		else if (method.endsWith("get_sewing_plan_entries")) value = {}
		else if (method.endsWith("submit_data_entry_log")) { await new Promise(r => setTimeout(r, state.submitDelay)); value = "ENTRY-SAVED"; error = state.submitError; if (!error) state.authoritativeQty += Number(args.payload.quantities.colours.Navy.values.XS.data_entry) }
		else if (method.endsWith("update_sewing_plan_data")) {
			value = "Success"; error = state.inspectionError
			const { lot, plan: planName, inspection_type: type, action, rows } = args.payload
			if (!error) for (const row of rows) for (const [size, quantities] of Object.entries(row.qty)) entry.data[lot][planName].colours[row.colour].values[size][type] = action === "revert" ? 0 : quantities[type]
		}
		else if (method.endsWith("link_search")) value = [{ name: args.doctype === "YRP Work Station" ? "Sewing Line 1" : "Good", label: args.doctype === "YRP Work Station" ? "Sewing Line 1" : "Good" }]
		else throw new Error(`Unexpected plan request: ${method}`)
		await route.fulfill({ status: error ? 417 : 200, contentType: "application/json", body: JSON.stringify(error ? { _server_messages: JSON.stringify([JSON.stringify({ message: error })]), exc: "ValidationError" } : { message: value }) })
	})
	const select = async (name, option) => { await page.getByRole("combobox", { name, exact: true }).click(); await page.getByRole("option", { name: option, exact: true }).click() }
	const closeError = async (text) => { await page.locator(".document-error-dialog").getByText(text, { exact: false }).waitFor(); await page.getByRole("button", { name: "OK", exact: true }).click(); await page.locator(".document-error-dialog").waitFor({ state: "hidden" }) }
	try {
		await page.goto(`http://127.0.0.1:${server.httpServer.address().port}/__plan-test`)
		await page.getByRole("tab", { name: "Dashboard", exact: true }).waitFor()
		assert(JSON.stringify(await page.getByRole("tab").allTextContents()) === JSON.stringify(["Dashboard", "Data Entry", "Entries", "Consumption", "Closed Work Order GRN"]), "Plan workspace must expose exactly the five approved tabs")
		await page.getByRole("status").filter({ hasText: "Loading dashboard" }).waitFor()
		await page.getByRole("row").filter({ hasText: "Sewing In" }).waitFor()
		assert((await page.getByRole("row").filter({ hasText: "Sewing In" }).innerText()).includes("40"), "Dashboard lost configured stage quantities")
		assert(!requests.some(r => r.method.endsWith("get_data_entry_data")), "Inactive Data Entry fetched")
		if (process.env.ESSDEE_SEWING_SCREENSHOTS) for (const width of [390, 1280]) { await page.setViewportSize({ width, height: 900 }); await noOverflow(page, `Dashboard ${width}`); await page.screenshot({ path: `${process.env.ESSDEE_SEWING_SCREENSHOTS}/sewing-dashboard-${width}.png`, fullPage: true, animations: "disabled" }) }
		state.dashboard = []; await page.getByRole("button", { name: "Refresh dashboard" }).click(); await page.getByText("No input quantities for open Work Orders.", { exact: true }).waitFor()
		state.dashboardError = "Dashboard unavailable"; await page.getByRole("button", { name: "Refresh dashboard" }).click(); await page.getByText(state.dashboardError, { exact: true }).waitFor()
		state.dashboardError = ""; state.dashboard = [{ input_type: "Sewing In", qty: 41 }]; await page.getByRole("button", { name: "Retry", exact: true }).click(); await page.getByRole("cell", { name: "41", exact: true }).waitFor()
		const before = requests.length
		for (const name of ["Closed Work Order GRN"]) { await page.getByRole("tab", { name, exact: true }).click(); await page.getByText(`${name} is not loaded yet.`, { exact: true }).waitFor(); assert(await page.locator("[data-sewing-plan-tab]").count() === 1, "Inactive tab still mounted") }
		assert(requests.length === before, "Future tabs issued requests")
		state.entryError = "Entry data unavailable"
		await page.getByRole("tab", { name: "Data Entry", exact: true }).click()
		await page.getByText(state.entryError, { exact: true }).waitFor()
		state.entryError = ""; await page.getByRole("button", { name: "Retry", exact: true }).click()
		await page.getByRole("combobox", { name: "Sewing Plan", exact: true }).waitFor()
		assert(await page.locator("[data-sewing-plan-tab]").count() === 1, "Data Entry mounted alongside another tab")
		assert(requests.some(r => r.method.endsWith("get_data_entry_data") && r.args.supplier === "UNIT-A"), "Data Entry is not Supplier scoped")
		await page.getByRole("combobox", { name: "Lot", exact: true }).click(); assert(JSON.stringify(await page.getByRole("option").allTextContents()) === JSON.stringify(["LOT-A"]), "Lot choices must come from current Supplier data"); await page.getByRole("option", { name: "LOT-A", exact: true }).click()
		await select("Sewing Plan", "PLAN-A")
		const quantity = page.getByRole("spinbutton", { name: "Navy XS Entry quantity", exact: true })
		await quantity.fill("7")
		await select("Sewing Plan", "PLAN-OTHER"); await quantity.fill("11"); await select("Sewing Plan", "PLAN-A")
		assert(await quantity.inputValue() === "7", "Changing plans lost the selected plan's edit")
		await page.getByRole("tab", { name: "Entries", exact: true }).click(); await page.getByRole("tab", { name: "Data Entry", exact: true }).click(); await quantity.waitFor()
		assert(await page.getByRole("combobox", { name: "Sewing Plan", exact: true }).textContent() === "PLAN-A", "Inactive-tab remount lost plan filter")
		await quantity.fill("7")
		await page.getByRole("button", { name: "Save entry", exact: true }).click(); await closeError("Complete all required entry fields.")
		assert(await quantity.inputValue() === "7", "Required-field validation lost quantity")
		await select("Input Type", "Sewing In")
		for (const [name, value] of [["Work Station", "Sewing Line 1"], ["Received Type", "Good"]]) { await page.getByRole("combobox", { name, exact: true }).fill(value); await page.getByRole("option", { name: value, exact: true }).click() }
		await page.getByRole("tab", { name: "Entries", exact: true }).click(); await page.getByRole("tab", { name: "Data Entry", exact: true }).click(); await quantity.waitFor()
		assert(await page.getByRole("combobox", { name: "Work Station", exact: true }).inputValue() === "Sewing Line 1", "Inactive-tab remount lost entry filters")
		assert(await page.getByRole("combobox", { name: "Date", exact: true }).inputValue(), "Date control is missing")
		assert(await page.getByRole("combobox", { name: "Time", exact: true }).inputValue(), "Time control is missing")
		await quantity.fill("-1"); await page.getByRole("button", { name: "Save entry", exact: true }).click(); await closeError("Quantities must be finite and non-negative."); assert(await quantity.inputValue() === "-1", "Negative validation lost edit")
		state.submitError = "Only 3 remains from Order Qty after allowance."
		const beforeRejectionLoads = state.loads
		await quantity.fill("500"); await page.getByRole("button", { name: "Save entry", exact: true }).click(); await closeError(state.submitError); assert(await quantity.inputValue() === "500", "Server rejection lost edit")
		assert(state.loads === beforeRejectionLoads + 1, "Acknowledged server rejection must refresh authoritative context and preserve edits")
		const rejected = requests.filter(r => r.method.endsWith("submit_data_entry_log")).at(-1).args.payload
		assert(rejected.quantities.colours.Navy.values.XS.order_detail === "PLAN-A-ROW-0", "Save lost authoritative order_detail")
		assert(!JSON.stringify(rejected).includes("item_variant") && !JSON.stringify(rejected).includes("UNTRUSTED"), "Browser-authored variant identity sent")
		assert(["plan", "input_type", "work_station", "received_type", "date", "time", "supplier"].every(k => rejected[k]), "Required controls absent from payload")
		await quantity.fill("7")
		for (const width of [390, 900, 1600, 1280]) { await page.setViewportSize({ width, height: 900 }); await noOverflow(page, `Data Entry ${width}`); assert(await quantity.inputValue() === "7", "Resize lost quantity"); if (width === 390) assert(await page.getByRole("region", { name: "PLAN-A quantity matrix", exact: true }).evaluate(el => el.scrollWidth > el.clientWidth), "Matrix must own narrow overflow"); if (process.env.ESSDEE_SEWING_SCREENSHOTS) await page.screenshot({ path: `${process.env.ESSDEE_SEWING_SCREENSHOTS}/sewing-entry-${width}.png`, fullPage: true }) }
		state.submitError = ""; state.submitDelay = 800
		const count = requests.filter(r => r.method.endsWith("submit_data_entry_log")).length, loads = state.loads
		// Retyping a selected Link schedules PrimeVue's 300ms completion. Save
		// starts before that timer fires and completes after it: a lookup must
		// never invalidate the acknowledged write or invite a duplicate save.
		await page.getByRole("combobox", { name: "Work Station", exact: true }).fill("Sewing Line 1")
		await page.getByRole("button", { name: "Save entry", exact: true }).click()
		assert(await page.getByRole("button", { name: "Save entry", exact: true }).isDisabled(), "Save not locked in flight")
		await page.getByRole("button", { name: "Save entry", exact: true }).evaluate(el => { el.click(); el.click() })
		await page.getByText("Entry saved.", { exact: true }).waitFor({ timeout: 2500 }).catch(() => { throw new Error("Delayed Link lookup discarded acknowledged Save: missing authoritative reload/success") })
		assert(requests.filter(r => r.method.endsWith("submit_data_entry_log")).length === count + 1, "Double submission escaped lock")
		assert(state.loads === loads + 1 && requests.filter(r => r.method.endsWith("get_data_entry_data")).at(-1).args.lot === "LOT-A", "Saved plan was not authoritatively reloaded")
		assert(await quantity.inputValue() === "0", "Successful save did not reset entry quantities")
		assert((await page.getByRole("region", { name: "PLAN-A quantity matrix", exact: true }).innerText()).includes("27"), "Authoritative stage values were not rendered after save")
		state.entryError = "Saved plan refresh unavailable"
		await quantity.fill("1"); await page.getByRole("button", { name: "Save entry", exact: true }).click(); await page.getByText("Entry saved. Refresh the plan before recording more quantities.", { exact: true }).waitFor()
		assert(await page.getByRole("button", { name: "Save entry", exact: true }).isDisabled(), "Reload failure must block further writes until authoritative refresh")
		state.entryError = ""; await page.getByRole("button", { name: "Refresh data entry" }).click(); await page.getByRole("button", { name: "Save entry", exact: true }).waitFor({ state: "visible" }); await page.waitForFunction(() => !document.querySelector('button[aria-label="Save entry"]').disabled)
		await select("Inspection Type", "Pre Final")
		await page.getByRole("spinbutton", { name: "Navy XS Inspection quantity", exact: true }).fill("9")
		await page.getByRole("button", { name: "Update inspection", exact: true }).click(); await page.getByText("Inspection updated.", { exact: true }).waitFor()
		assert(await page.getByRole("spinbutton", { name: "Navy XS Inspection quantity", exact: true }).inputValue() === "9", "Inspection update did not render authoritative total")
		await select("Inspection Type", "Final Inspection")
		const inspection = page.getByRole("spinbutton", { name: "Navy XS Inspection quantity", exact: true })
		assert(await inspection.inputValue() === "2", "Inspection recovery fixture needs the saved 2-unit total")
		state.entryError = "Inspection recovery unavailable"
		await page.getByRole("button", { name: "Revert inspection", exact: true }).click(); await page.getByText("Inspection reverted. Refresh the plan before recording more quantities.", { exact: true }).waitFor()
		assert(await page.getByRole("button", { name: "Update inspection", exact: true }).isDisabled(), "Failed inspection refresh re-enabled stale Update draft")
		state.entryError = ""; await page.getByRole("button", { name: "Refresh data entry" }).click()
		await page.waitForFunction(() => !document.querySelector('button[aria-label="Update inspection"]').disabled)
		assert(await inspection.inputValue() === "0", "Acknowledged inspection revert recovery retained stale 2-unit draft instead of server zero")
		assert(requests.filter(r => r.method.endsWith("get_data_entry_data")).at(-1).args.lot === "LOT-A", "Inspection recovery lost acknowledged Supplier/Lot scope")
		const updates = requests.filter(r => r.method.endsWith("update_sewing_plan_data")).map(r => r.args.payload)
		assert(updates.length === 2 && updates[0].inspection_type === "pre_final" && updates[0].action === "update" && updates[1].inspection_type === "final_inspection" && updates[1].action === "revert", "Inspection update/revert contract mismatch")
		await inspection.fill("5"); state.inspectionError = "Inspection update rejected"
		await page.getByRole("button", { name: "Update inspection", exact: true }).click(); await closeError(state.inspectionError)
		assert(await inspection.inputValue() === "5", "Rejected inspection acknowledgement discarded user edit")
		state.inspectionError = ""; state.entryError = "Ordinary refresh unavailable"
		await page.getByRole("button", { name: "Refresh data entry" }).click(); await page.locator(".p-message").filter({ hasText: state.entryError }).waitFor()
		assert(await inspection.inputValue() === "5", "Ordinary load error discarded unsaved inspection edit")
		state.entryError = ""
		await page.evaluate(() => window.router.replace('/sewing/plans?supplier=UNIT-B&tab=data-entry'))
		await page.getByText("No Sewing Plans for this Sewing Unit.", { exact: true }).waitFor()
		await page.getByRole("combobox", { name: "Lot", exact: true }).click(); assert(await page.getByRole("option", { name: "LOT-A", exact: true }).count() === 0, "Old Supplier Lots leaked")
		let releaseEntry
		state.entryHold = new Promise(resolve => { releaseEntry = resolve })
		const entryCount = requests.filter(r => r.method.endsWith("get_data_entry_data")).length
		await page.evaluate(() => window.router.replace('/sewing/plans?supplier=UNIT-A&tab=data-entry'))
		await page.waitForFunction(() => document.querySelector('[data-sewing-plan-tab="data-entry"][aria-busy="true"]'))
		while (requests.filter(r => r.method.endsWith("get_data_entry_data")).length === entryCount) await page.waitForTimeout(10)
		await page.evaluate(() => window.router.replace('/sewing/plans?supplier=UNIT-B&tab=data-entry'))
		await page.getByText("No Sewing Plans for this Sewing Unit.", { exact: true }).waitFor()
		const oldEntry = page.waitForResponse(response => response.url().endsWith("get_data_entry_data") && response.request().postDataJSON().supplier === "UNIT-A")
		releaseEntry(); await oldEntry
		assert(await page.getByText("No Sewing Plans for this Sewing Unit.", { exact: true }).isVisible(), "Delayed old Supplier entry data overwrote current Supplier")
		let releaseDashboard
		state.dashboardHold = new Promise(resolve => { releaseDashboard = resolve }); state.dashboard = [{ input_type: "Old A stage", qty: 3 }]
		const dashboardCount = requests.filter(r => r.method.endsWith("get_dashboard_data")).length
		await page.evaluate(() => window.router.replace('/sewing/plans?supplier=UNIT-A&tab=dashboard'))
		while (requests.filter(r => r.method.endsWith("get_dashboard_data")).length === dashboardCount) await page.waitForTimeout(10)
		state.dashboard = [{ input_type: "Current B stage", qty: 99 }]
		await page.evaluate(() => window.router.replace('/sewing/plans?supplier=UNIT-B&tab=dashboard'))
		await page.getByRole("row").filter({ hasText: "Current B stage" }).waitFor()
		const oldDashboard = page.waitForResponse(response => response.url().endsWith("get_dashboard_data") && response.request().postDataJSON().supplier === "UNIT-A")
		releaseDashboard(); await oldDashboard
		assert(await page.getByRole("row").filter({ hasText: "Old A stage" }).count() === 0, "Delayed old Supplier dashboard overwrote current Supplier")
		assert(errors.length === 0, `Browser errors: ${errors.join("; ")}`)
		console.log("PASS plan-entry: five active-only tabs, dashboard states/retry/refresh, Supplier Lots, required controls, trusted-row payload, preserved validation/server rejection, delayed Link/save isolation, submit lock, authoritative reload/recovery, inspection revert recovery and rejected-edit retention, restricted inspection actions, stale Supplier rejection, tab-filter retention, four contained viewports with resize retention")
	} catch (reason) {
		console.error("Plan-entry browser diagnostics:", JSON.stringify({ errors, body: (await page.locator("body").innerText()).slice(0, 1500) }))
		throw reason
	} finally { await page.close(); await server.close() }
}

// These tests catch wrong filter/payload scope, client-invented cancellation
// eligibility, optimistic deletion, metadata loss, duplicate writes, stale
// Supplier results, lost drafts, and mapping overflow in the real Vue views.
async function entriesConsumptionSuite(browser, settlementCase = "") {
	const harness = `
import { createApp } from 'vue';
import { createRouter, createMemoryHistory, RouterView } from 'vue-router';
import PrimeVue from 'primevue/config'; import Aura from '@primeuix/themes/aura';
import SewingPlans from '/src/departments/sewing/SewingPlans.vue';
import '@fontsource-variable/inter'; import 'primeicons/primeicons.css';
import '/src/styles/main.css'; import '/src/styles/enterprise.css';
const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/sewing/plans', component: SewingPlans }, { path: '/sewing', component: { render: () => null } }] });
await router.push('/sewing/plans?supplier=UNIT-A&tab=entries'); window.router = router;
createApp(RouterView).use(router).use(PrimeVue, { theme: { preset: Aura, options: { darkModeSelector: false } } }).mount('#app');`
	const server = await createServer({
		root: fileURLToPath(new URL("../frontend", import.meta.url)), server: { host: "127.0.0.1", port: 0 },
		plugins: [{ name: "sewing-operations-verifier", resolveId(id) { if (id === "/__operations-test.js") return "\0operations-test" }, load(id) { if (id === "\0operations-test") return harness }, configureServer(server) { server.middlewares.use((req, res, next) => { if (req.url !== "/__operations-test") return next(); res.setHeader("Content-Type", "text/html"); res.end('<!doctype html><html><body><div id="app"></div><script type="module" src="/__operations-test.js"></script></body></html>') }) } }],
	})
	await server.listen()
	const page = await browser.newPage({ viewport: { width: 1280, height: 900 } })
	page.setDefaultTimeout(10_000)
	const requests = [], errors = [], warnings = []
	const sizes = ["XS", "S", "M", "L", "XL", "2XL", "3XL", "4XL"]
	const record = (date, cancellable) => ({ lot: "LOT-A", details: { Navy: { colour: "Navy", part: "Front", variant_colour: "Navy", set_combination: {}, total: 36, values: Object.fromEntries(sizes.map((size, i) => [size, i + 1])) } }, work_station: "Line 1", input_type: "Sewing In", received_type: "Good", item_name: "T-Shirt", primary_values: sizes, is_set_item: 0, pack_attr: "Colour", set_attr: null, is_cancellable: cancellable, entry_date: date, entry_time: "09:30:00" })
	const mapping = { ipd: "IPD-A", sections: [
		{ item: "Thread", item_attributes: ["item_Colour", "bom_Size", "bom_Colour", "bom_Length", "bom_Twist"], rows: [{ index: 3, values: { item_Colour: "Navy", bom_Size: "Fine", bom_Colour: "Black", bom_Length: "Long", bom_Twist: "Soft" }, quantity: 2, item_bom_qty: 1.25, future_row: { ids: [7, 4], enabled: false } }, { index: 9, values: { item_Colour: "White" }, quantity: 0, item_bom_qty: 0, unknown: null }], attribute_in_item: ["Colour"], item_bom_uom: "Kg", future_section: ["preserve", { version: 2 }] },
		{ item: "Elastic", item_attributes: ["Item"], rows: [{ index: 0, values: { Item: "Elastic" }, quantity: 0, item_bom_qty: 3 }], attribute_in_item: [], item_bom_uom: "Metre" },
	], cloth_acc_data: [{ accessory_type: ["Tape"], attributes: ["Accessory", "Dia", "Weight", "Colour", "Size", "Length"], columns: [{ Accessory: "Tape", Dia: "20", Weight: 8, Colour: "Navy", Size: "M", Length: "Long", "Consumption Weight": 0.5, extra: { sequence: [3, 1], nullable: null } }, { Accessory: "Tape", Dia: "22", Weight: 9, Colour: "White", "Consumption Weight": 0 }], att_iv_check: ["Colour", "Size", "Length"], future_group: [false, "x"] }] }
	const state = { entries: { "ENTRY-OLD": record("2026-10-01", false), "ENTRY-A": record("2026-10-08", true), "ENTRY-B": record("2026-10-08", false) }, entryError: "", cancelError: "", cancelDelay: 0, cancelHold: null, entryHold: null, mapping: structuredClone(mapping), mappingError: "", mappingHold: null, saveError: "", saveStatus: 417, saveDelay: 0, saveHold: null, lotHold: null, readOnly: false }
	page.on("pageerror", e => errors.push(e.message))
	page.on("console", m => { if (m.type() === "warning") warnings.push(m.text()) })
	await page.route("**/api/method/**", async route => {
		const method = route.request().url().split("/api/method/")[1], args = JSON.parse(route.request().postData() || "{}")
		requests.push({ method, args })
		let value = null, error = ""
		if (method.endsWith("get_capabilities")) value = { ...capabilities, plan_actions: { entry: { ...flags, can_delete: false }, plan: { ...flags, can_write: !state.readOnly } } }
		else if (method.endsWith("get_sewing_plan_entries")) { value = args.supplier === "UNIT-B" ? { "ENTRY-UNIT-B": record("2026-10-09", false) } : structuredClone(state.entries); error = state.entryError; if (state.entryHold) { const hold = state.entryHold; state.entryHold = null; await hold } }
		else if (method.endsWith("cancel_sewing_plan_entry")) { if (state.cancelHold) { const hold = state.cancelHold; state.cancelHold = null; await hold } else await new Promise(r => setTimeout(r, state.cancelDelay)); error = state.cancelError; if (!error) delete state.entries[args.doc_id] }
		else if (method.endsWith("get_supplier_lots")) { value = [[args.filters.supplier === "UNIT-B" ? "LOT-B" : "LOT-A", "T-Shirt"]]; if (state.lotHold) { const hold = state.lotHold; state.lotHold = null; await hold } }
		else if (method.endsWith("get_consumption_mapping_data")) { value = structuredClone(state.mapping); if (args.supplier === "UNIT-B") value.ipd = "IPD-B"; error = state.mappingError; if (state.mappingHold) { const hold = state.mappingHold; state.mappingHold = null; await hold } }
		else if (method.endsWith("save_consumption_data")) { if (state.saveHold) { const hold = state.saveHold; state.saveHold = null; await hold } else await new Promise(r => setTimeout(r, state.saveDelay)); error = state.saveError; value = { status: "success", message: "Consumption data saved successfully" }; if (!error) { state.mapping.sections[0].rows[0].quantity = 6.75; state.mapping.cloth_acc_data[0].columns[0]["Consumption Weight"] = 1.75 } }
		else if (method.endsWith("link_search")) value = [{ name: args.doctype === "YRP Work Station" ? "Line 1" : "Sewing In", label: args.doctype === "YRP Work Station" ? "Line 1" : "Sewing In" }]
		else throw new Error(`Unexpected operations request: ${method}`)
		await route.fulfill({ status: error ? method.endsWith("save_consumption_data") ? state.saveStatus : 417 : 200, contentType: "application/json", body: JSON.stringify(error ? { _server_messages: JSON.stringify([JSON.stringify({ message: error })]), exc: "ValidationError" } : { message: value }) })
	})
	const count = suffix => requests.filter(r => r.method.endsWith(suffix)).length
	const selectLink = async (name, value) => { await page.getByRole("combobox", { name, exact: true }).fill(value); await page.getByRole("option", { name: value, exact: true }).click() }
	const tab = async name => { await page.evaluate(name => window.router.replace({ query: { ...window.router.currentRoute.value.query, tab: name } }), name); await page.locator(`[data-sewing-plan-tab='${name}']`).waitFor(); assert(await page.locator("[data-sewing-plan-tab]").count() === 1, "Inactive tab mounted") }
	const closeError = async text => { await page.locator(".document-error-dialog").getByText(text, { exact: false }).waitFor(); await page.getByRole("button", { name: "OK", exact: true }).click(); await page.locator(".document-error-dialog").waitFor({ state: "hidden" }) }
	const quantity = () => page.getByRole("spinbutton", { name: "Thread row 3 quantity", exact: true })
	const weight = () => page.getByRole("spinbutton", { name: "Cloth accessories 1 row 1 Consumption Weight", exact: true })
	// Removing shell-owned mutation settlement or observing only the departed
	// instance must fail these navigation-before-response regressions.
	async function settlementRegressions(only = "all") {
		for (const scenario of ["cancel-success", "cancel-rejection", "save-rejection", "cancel-rejection-inactive", "save-rejection-inactive", "save-rejection-supplier"]) {
			if (only !== "all" && only !== scenario) continue
			state.readOnly = false; state.cancelError = ""; state.saveError = ""; state.saveStatus = 417
			state.entries["ENTRY-A"] = record("2026-10-08", true)
			await page.goto(`http://127.0.0.1:${server.httpServer.address().port}/__operations-test`)
			await page.getByText("ENTRY-A", { exact: true }).waitFor()
			const isSave = scenario.startsWith("save-"), method = isSave ? "save_consumption_data" : "cancel_sewing_plan_entry"
			if (isSave) {
				await tab("consumption"); await selectLink("Lot", "LOT-A"); await quantity().fill("5")
				state.saveError = "You do not have permission to update consumption."; state.saveStatus = 403
			} else if (scenario !== "cancel-success") state.cancelError = "This entry is no longer eligible for cancellation."
			let release; const hold = new Promise(resolve => release = resolve)
			if (isSave) state.saveHold = hold; else state.cancelHold = hold
			const pendingRequest = page.waitForRequest(request => request.url().endsWith(method))
			if (isSave) await page.getByRole("button", { name: "Save consumption", exact: true }).click()
			else { await page.getByRole("button", { name: "Cancel ENTRY-A", exact: true }).click(); await page.getByRole("button", { name: "Cancel entry", exact: true }).click() }
			await pendingRequest
			await tab(isSave ? "entries" : "consumption")
			if (isSave) await page.getByText("ENTRY-B", { exact: true }).waitFor()
			const readsWhileInactive = count(isSave ? "get_consumption_mapping_data" : "get_sewing_plan_entries")
			await page.waitForTimeout(50)
			assert(count(isSave ? "get_consumption_mapping_data" : "get_sewing_plan_entries") === readsWhileInactive, `${scenario}: inactive view fetched before settlement`)
			const beforeSettlementReads = count(isSave ? "get_consumption_mapping_data" : "get_sewing_plan_entries")
			const settled = page.waitForResponse(response => response.url().endsWith(method))
			if (scenario.endsWith("-supplier")) {
				await page.evaluate(() => window.router.replace('/sewing/plans?supplier=UNIT-B&tab=consumption'))
				await page.getByRole("combobox", { name: "Lot", exact: true }).waitFor()
				release(); await settled
				assert(await quantity().count() === 0 && await page.getByRole("combobox", { name: "Lot", exact: true }).inputValue() === "", "Late write rejection leaked foreign draft into Supplier B")
				assert(await page.locator(".document-error-dialog").count() === 0, "Late write rejection leaked popup into Supplier B")
				await page.evaluate(() => window.router.replace('/sewing/plans?supplier=UNIT-A&tab=consumption'))
				await page.getByRole("combobox", { name: "Lot", exact: true }).waitFor()
				assert(await page.locator(".document-error-dialog").count() === 0, "Old Supplier-keyed outcome leaked into a fresh Supplier A workspace")
				console.log(`PASS settlement ${scenario}: discarded scope cannot leak a draft or late rejection`)
				continue
			}
			if (scenario.endsWith("-inactive")) {
				release(); await settled
				assert(await page.locator(".document-error-dialog").count() === 0, `${scenario}: failure popup leaked into the other tab`)
				assert(count(isSave ? "get_consumption_mapping_data" : "get_sewing_plan_entries") === beforeSettlementReads, `${scenario}: inactive settlement fetched records`)
				await tab(isSave ? "consumption" : "entries")
			} else {
				await tab(isSave ? "consumption" : "entries")
				assert(await page.getByRole("button", { name: isSave ? "Save consumption" : "Refresh entries", exact: true }).isDisabled(), `${scenario}: mutation lock lost on remount`)
				release(); await settled
			}
			if (scenario === "cancel-success") {
				await page.getByText("ENTRY-B", { exact: true }).waitFor({ timeout: 2500 }).catch(() => { throw new Error("Remounted Entries ignored successful cancellation settlement and remained falsely empty") })
				await page.getByText("Entry cancelled.", { exact: true }).waitFor()
				assert(await page.getByText("ENTRY-A", { exact: true }).count() === 0, "Remounted Entries retained cancelled record")
				assert(count("get_sewing_plan_entries") === beforeSettlementReads + 1, "Successful remounted cancellation must refresh exactly once")
			} else {
				const message = isSave ? state.saveError : state.cancelError
				await page.locator(".document-error-dialog").getByText(message, { exact: false }).waitFor({ timeout: 2500 }).catch(() => { throw new Error(`${scenario}: late rejection disappeared after remount`) })
				assert((await page.locator(".document-error-dialog").innerText()).includes(message), `${scenario}: shared rejection popup missing plain server message`)
				if (isSave) { assert(await quantity().inputValue() === "5", "Late 403 discarded consumption draft"); assert(await page.getByRole("button", { name: "Save consumption", exact: true }).isEnabled(), "Rejected consumption stayed locked after settlement"); assert(count("get_consumption_mapping_data") === beforeSettlementReads, "Rejected save reloaded away the draft") }
				else { await page.getByText("ENTRY-A", { exact: true }).waitFor(); assert(count("get_sewing_plan_entries") === beforeSettlementReads + 1, "Rejected remounted cancellation failed to load retained entries") }
				await closeError(message)
				await tab(isSave ? "entries" : "consumption"); await tab(isSave ? "consumption" : "entries")
				assert(await page.locator(".document-error-dialog").count() === 0, `${scenario}: acknowledged rejection repeated after another remount`)
			}
			console.log(`PASS settlement ${scenario}: navigation before response, active-only refresh, persistent outcome and acknowledgement`)
		}
		assert(errors.length === 0 && warnings.length === 0, `Settlement browser issues: ${[...errors, ...warnings].join("; ")}`)
	}
	try {
		if (settlementCase) { await settlementRegressions(settlementCase); return }
		await page.goto(`http://127.0.0.1:${server.httpServer.address().port}/__operations-test`)
		await page.getByRole("heading", { name: "Entries", exact: true }).waitFor()
		await page.getByRole("heading", { name: "2026-10-08", exact: true }).waitFor()
		assert(count("get_sewing_plan_entries") === 1 && count("get_consumption_mapping_data") === 0, "Initial active-only load broken")
		assert(await page.locator("[data-entry-date]").first().getAttribute("data-entry-date") === "2026-10-08", "Newest entry date must appear first")
		assert(await page.locator("[data-entry-date='2026-10-08'] [data-entry-id]").count() === 2 && await page.locator("[data-entry-date='2026-10-01'] [data-entry-id]").count() === 1, "Entries not grouped by date")
		assert(await page.locator("[data-entry-id='ENTRY-A']").getByRole("spinbutton", { name: "Navy XS Quantity", exact: true }).inputValue() === "1", "Entry matrix lost numeric quantities")
		assert(await page.locator("[data-entry-id='ENTRY-A']").getByRole("spinbutton", { name: "Navy XS Quantity", exact: true }).isDisabled(), "Saved entry matrix became editable")
		assert(await page.getByRole("button", { name: /^Cancel ENTRY-/ }).count() === 1, "Cancel must depend only on returned is_cancellable")
		await selectLink("Work Station", "Line 1"); await selectLink("Input Type", "Sewing In"); await selectLink("Lot", "LOT-A")
		await page.waitForFunction(() => document.querySelector('[data-sewing-plan-tab="entries"]').getAttribute('aria-busy') === 'false')
		const filteredEntries = page.waitForResponse(r => r.url().endsWith("get_sewing_plan_entries") && r.request().postDataJSON().lot_name === "LOT-A")
		await page.getByRole("button", { name: "Refresh entries", exact: true }).click(); await filteredEntries
		const filters = requests.filter(r => r.method.endsWith("get_sewing_plan_entries")).at(-1).args
		assert(JSON.stringify(filters) === JSON.stringify({ supplier: "UNIT-A", work_station: "Line 1", input_type: "Sewing In", lot_name: "LOT-A" }), `Wrong Entries filters: ${JSON.stringify(filters)}`)
		await page.getByRole("button", { name: "Cancel ENTRY-A", exact: true }).click()
		await page.locator(".document-confirmation-shell").waitFor()
		assert(count("cancel_sewing_plan_entry") === 0, "Cancel bypassed shared confirmation")
		await page.getByRole("button", { name: "Keep entry", exact: true }).click()
		assert(await page.locator("[data-entry-id='ENTRY-A']").count() === 1, "Dismissed cancel removed entry")
		state.cancelError = "This entry is no longer eligible for cancellation."
		await page.getByRole("button", { name: "Cancel ENTRY-A", exact: true }).click()
		await page.getByRole("button", { name: "Cancel entry", exact: true }).click()
		await closeError(state.cancelError)
		assert(await page.locator("[data-entry-id='ENTRY-A']").count() === 1, "Server rejection optimistically removed entry")
		state.cancelError = ""; state.cancelDelay = 250
		const beforeCancelLoads = count("get_sewing_plan_entries"), beforeCancel = count("cancel_sewing_plan_entry")
		await page.getByRole("button", { name: "Cancel ENTRY-A", exact: true }).click()
		await page.getByRole("button", { name: "Cancel entry", exact: true }).evaluate(el => { el.click(); el.click() })
		await page.getByText("Entry cancelled.", { exact: true }).waitFor()
		assert(count("cancel_sewing_plan_entry") === beforeCancel + 1 && count("get_sewing_plan_entries") === beforeCancelLoads + 1, "Cancel duplicate lock or authoritative refresh broken")
		assert(await page.locator("[data-entry-id='ENTRY-A']").count() === 0, "Successful cancellation did not reload entries")
		assert(requests.filter(r => r.method.endsWith("cancel_sewing_plan_entry")).at(-1).args.doc_id === "ENTRY-A", "Cancellation lost entry identity")
		await tab("consumption")
		assert(count("get_consumption_mapping_data") === 0, "Consumption fetched before Lot selection")
		await selectLink("Lot", "LOT-A")
		await quantity().waitFor()
		const lotArgs = requests.filter(r => r.method.endsWith("get_supplier_lots")).at(-1).args
		assert(JSON.stringify(lotArgs) === JSON.stringify({ doctype: "SD YRP Lot", txt: "LOT-A", searchfield: "name", start: 0, page_len: 20, filters: { supplier: "UNIT-A" } }), `Lot query is not Supplier scoped: ${JSON.stringify(lotArgs)}`)
		assert(JSON.stringify(requests.filter(r => r.method.endsWith("get_consumption_mapping_data")).at(-1).args) === JSON.stringify({ supplier: "UNIT-A", lot: "LOT-A" }), "Consumption read lost explicit scope")
		assert((await page.locator("[data-sewing-plan-tab='consumption']").innerText()).includes("Kg") && (await page.locator("[data-sewing-plan-tab='consumption']").innerText()).includes("1.25"), "BOM/UOM context missing")
		await quantity().fill("4.25"); await weight().fill("1.5")
		const beforeSwitch = count("get_consumption_mapping_data")
		await tab("entries"); await page.getByRole("heading", { name: "2026-10-08", exact: true }).waitFor()
		assert(await page.getByRole("combobox", { name: "Work Station", exact: true }).inputValue() === "Line 1" && await page.getByRole("combobox", { name: "Input Type", exact: true }).inputValue() === "Sewing In" && await page.getByRole("combobox", { name: "Lot", exact: true }).inputValue() === "LOT-A", "Entries filters lost across tabs")
		assert(count("get_consumption_mapping_data") === beforeSwitch, "Inactive Consumption fetched")
		await tab("consumption"); assert(await quantity().inputValue() === "4.25" && await weight().inputValue() === "1.5", "Consumption drafts lost across tabs")
		state.saveError = "Consumption rejected by server."
		await page.getByRole("button", { name: "Save consumption", exact: true }).click(); await closeError(state.saveError)
		assert(await quantity().inputValue() === "4.25" && await weight().inputValue() === "1.5", "Rejected save lost edits")
		const expected = structuredClone(mapping); expected.sections[0].rows[0].quantity = 4.25; expected.cloth_acc_data[0].columns[0]["Consumption Weight"] = 1.5
		const sent = requests.filter(r => r.method.endsWith("save_consumption_data")).at(-1).args
		assert(JSON.stringify(sent) === JSON.stringify({ supplier: "UNIT-A", lot: "LOT-A", sections: expected.sections, cloth_acc_data: expected.cloth_acc_data }), `Consumption round-trip lost unknown metadata: ${JSON.stringify(sent)}`)
		state.saveError = ""; state.saveDelay = 250
		const beforeSave = count("save_consumption_data"), beforeMapping = count("get_consumption_mapping_data")
		// A delayed Lot lookup must not invalidate a business mutation.
		let releaseLot; state.lotHold = new Promise(r => releaseLot = r)
		const delayedLot = page.waitForRequest(r => r.url().endsWith("get_supplier_lots"))
		await page.getByRole("button", { name: "Show Lot options", exact: true }).click(); await delayedLot
		await page.keyboard.press("Escape")
		await page.getByRole("button", { name: "Save consumption", exact: true }).evaluate(el => { el.click(); el.click() })
		releaseLot()
		await page.getByText("Consumption saved.", { exact: true }).waitFor()
		assert(count("save_consumption_data") === beforeSave + 1 && count("get_consumption_mapping_data") === beforeMapping + 1, "Save duplicate lock, lookup isolation or refresh broken")
		assert(await quantity().inputValue() === "6.75" && await weight().inputValue() === "1.75", "Save failed to replace drafts with authoritative values")
		await quantity().fill("8")
		state.mappingError = "Saved mapping unavailable"
		await page.getByRole("button", { name: "Save consumption", exact: true }).click()
		await page.getByText(state.mappingError, { exact: false }).waitFor()
		assert(await page.getByRole("button", { name: "Save consumption", exact: true }).isDisabled(), "Acknowledged save can be resubmitted before refresh recovery")
		assert(await quantity().inputValue() === "8", "Refresh failure lost visible draft")
		await tab("entries"); await tab("consumption")
		assert(await page.getByRole("button", { name: "Save consumption", exact: true }).isDisabled(), "Tab switch bypassed acknowledged-save recovery")
		state.mappingError = ""; await page.getByRole("button", { name: "Refresh consumption", exact: true }).click()
		await page.waitForFunction(() => document.querySelector('[aria-label="Thread row 3 quantity"]').value === '6.75')
		assert(await page.getByRole("button", { name: "Save consumption", exact: true }).isEnabled(), "Successful refresh did not unlock consumption")
		// A save acknowledged after its tab unmounts must retain its recovery lock
		// without fetching inactive records or allowing the draft to be resubmitted.
		await quantity().fill("7")
		let releaseSave; state.saveHold = new Promise(r => releaseSave = r)
		const inactiveSaveRequest = page.waitForRequest(r => r.url().endsWith("save_consumption_data"))
		await page.getByRole("button", { name: "Save consumption", exact: true }).click(); await inactiveSaveRequest
		await tab("entries"); await page.getByRole("heading", { name: "2026-10-08", exact: true }).waitFor()
		const beforeInactiveSave = count("get_consumption_mapping_data")
		const inactiveSaveResponse = page.waitForResponse(r => r.url().endsWith("save_consumption_data"))
		releaseSave(); await inactiveSaveResponse
		await tab("consumption")
		assert(count("get_consumption_mapping_data") === beforeInactiveSave, "Acknowledged inactive save fetched records")
		assert(await quantity().inputValue() === "7" && await page.getByRole("button", { name: "Save consumption", exact: true }).isDisabled(), "Inactive save bypassed acknowledgement recovery")
		await page.getByRole("button", { name: "Refresh consumption", exact: true }).click()
		await page.waitForFunction(() => document.querySelector('[aria-label="Thread row 3 quantity"]').value === '6.75')
		for (const width of [390, 900, 1280, 1600]) {
			await page.setViewportSize({ width, height: 900 }); await noOverflow(page, `Consumption ${width}`)
			if (width === 390) assert(await page.locator(".sewing-consumption-table__scroll").first().evaluate(el => el.scrollWidth > el.clientWidth && getComputedStyle(el).overflowX === "auto"), "Wide mappings lack contained horizontal scrolling")
			if (process.env.ESSDEE_SEWING_SCREENSHOTS) await page.screenshot({ path: `${process.env.ESSDEE_SEWING_SCREENSHOTS}/sewing-consumption-${width}.png`, fullPage: true, animations: "disabled" })
			await tab("entries"); await page.getByRole("heading", { name: "2026-10-08", exact: true }).waitFor(); await noOverflow(page, `Entries ${width}`)
			if (process.env.ESSDEE_SEWING_SCREENSHOTS) await page.screenshot({ path: `${process.env.ESSDEE_SEWING_SCREENSHOTS}/sewing-entries-${width}.png`, fullPage: true, animations: "disabled" })
			await tab("consumption")
		}
		let releaseMapping; state.mappingHold = new Promise(r => releaseMapping = r)
		const pendingMapping = page.waitForRequest(r => r.url().endsWith("get_consumption_mapping_data") && r.postDataJSON().supplier === "UNIT-A")
		await page.getByRole("button", { name: "Refresh consumption", exact: true }).click(); await pendingMapping
		await page.evaluate(() => window.router.replace('/sewing/plans?supplier=UNIT-B&tab=consumption'))
		await page.getByRole("combobox", { name: "Lot", exact: true }).waitFor()
		assert(await page.getByRole("combobox", { name: "Lot", exact: true }).inputValue() === "", "Supplier change retained foreign Lot")
		assert(await quantity().count() === 0, "Supplier change retained foreign mapping")
		await selectLink("Lot", "LOT-B"); await page.getByText("IPD-B", { exact: true }).waitFor()
		const oldMapping = page.waitForResponse(r => r.url().endsWith("get_consumption_mapping_data") && r.request().postDataJSON().supplier === "UNIT-A")
		releaseMapping(); await oldMapping
		assert(await page.getByText("IPD-A", { exact: true }).count() === 0, "Delayed A mapping overwrote B")
		let releaseOldLot; state.lotHold = new Promise(r => releaseOldLot = r)
		const oldLotRequest = page.waitForRequest(r => r.url().endsWith("get_supplier_lots") && r.postDataJSON().filters.supplier === "UNIT-B")
		await page.getByRole("button", { name: "Show Lot options", exact: true }).click(); await oldLotRequest
		await page.evaluate(() => window.router.replace('/sewing/plans?supplier=UNIT-A&tab=consumption'))
		await selectLink("Lot", "LOT-A"); await page.getByText("IPD-A", { exact: true }).waitFor()
		const oldLotResponse = page.waitForResponse(r => r.url().endsWith("get_supplier_lots") && r.request().postDataJSON().filters.supplier === "UNIT-B")
		releaseOldLot(); await oldLotResponse
		assert(await page.getByRole("option", { name: "LOT-B", exact: true }).count() === 0 && await page.getByRole("combobox", { name: "Lot", exact: true }).inputValue() === "LOT-A", "Delayed old Supplier Lot lookup leaked into current selection")
		await page.evaluate(() => window.router.replace('/sewing/plans?supplier=UNIT-A&tab=entries'))
		await page.getByRole("heading", { name: "2026-10-08", exact: true }).waitFor()
		let releaseEntries; state.entryHold = new Promise(r => releaseEntries = r)
		const pendingEntries = page.waitForRequest(r => r.url().endsWith("get_sewing_plan_entries") && r.postDataJSON().supplier === "UNIT-A")
		await page.getByRole("button", { name: "Refresh entries", exact: true }).click(); await pendingEntries
		await page.evaluate(() => window.router.replace('/sewing/plans?supplier=UNIT-B&tab=entries'))
		await page.getByText("ENTRY-UNIT-B", { exact: true }).waitFor()
		const oldEntries = page.waitForResponse(r => r.url().endsWith("get_sewing_plan_entries") && r.request().postDataJSON().supplier === "UNIT-A")
		releaseEntries(); await oldEntries
		assert(await page.getByText("ENTRY-OLD", { exact: true }).count() === 0, "Delayed A entries overwrote B")
		state.readOnly = true; await page.reload(); await tab("consumption"); await selectLink("Lot", "LOT-A"); await quantity().waitFor()
		assert(await page.getByRole("button", { name: "Save consumption", exact: true }).isDisabled() && await quantity().isDisabled(), "Read-only plan exposes consumption mutation")
		await page.evaluate(() => window.router.replace('/sewing/plans?tab=consumption'))
		await page.getByText("Select a Sewing Unit to view Sewing Plan.", { exact: true }).waitFor()
		const noScope = requests.length; await page.waitForTimeout(350); assert(requests.length === noScope, "Missing Supplier issued consumption requests")
		await settlementRegressions()
		assert(errors.length === 0 && warnings.length === 0, `Browser issues: ${[...errors, ...warnings].join("; ")}`)
		console.log("PASS entries-consumption: exact filters, grouped dates/matrices, server-only cancellation eligibility, shared confirmation/rejection/locks/refresh, scoped Lot query and selection guards, complete metadata round-trip, retained drafts/errors, authoritative save/recovery, lookup isolation, read-only permissions, Supplier A/B stale rejection, eight contained viewports")
	} catch (reason) {
		console.error("Entries-consumption diagnostics:", JSON.stringify({ errors, warnings, body: (await page.locator("body").innerText()).slice(0, 1800) }))
		throw reason
	} finally { await page.close(); await server.close() }
}

assert(["launcher", "plan-entry", "entries-consumption", "entries-consumption-settlement", "all"].includes(suite), `Unknown Sewing suite: ${suite}`)
const browser = await chromium.launch({ headless: true })
try {
	if (suite === "launcher" || suite === "all") {
		const page = await browser.newPage()
		page.setDefaultTimeout(20_000)
		await login(page)
		await launcherSuite(page)
		await contextSuite(browser)
	}
	if (suite === "plan-entry" || suite === "all") await planEntrySuite(browser)
	if (suite === "entries-consumption" || suite === "all") await entriesConsumptionSuite(browser)
	if (suite === "entries-consumption-settlement") await entriesConsumptionSuite(browser, process.argv[3] || "all")
} finally { await browser.close() }
