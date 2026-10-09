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
	const geometry = await page.evaluate(() => ({
		viewport: innerWidth,
		page: document.documentElement.scrollWidth,
		offenders: [...document.querySelectorAll("body *")].flatMap(element => {
			const box = element.getBoundingClientRect()
			return box.right > innerWidth + 1 || box.left < -1 ? [{ tag: element.tagName, className: String(element.className || "").slice(0, 120), left: Math.round(box.left), right: Math.round(box.right), width: Math.round(box.width) }] : []
		}).slice(0, 8),
	}))
	assert(geometry.page <= geometry.viewport + 1, `${label} page overflow: ${JSON.stringify(geometry)}`)
}

async function oneLoadPopup(page, message) {
	await page.locator('.document-error-dialog').getByText(message, { exact: true }).waitFor()
	assert(await page.locator('.document-error-dialog').count() === 1, 'Load failure opened duplicate dialogs')
	assert(await page.getByText(message, { exact: true }).count() === 1, 'Load failure duplicated raw inline error')
	await page.getByRole('button', { name: 'OK', exact: true }).click()
	await page.locator('.document-error-dialog').waitFor({ state: 'hidden' })
}

// A dialog must keep both its message and acknowledgement reachable at every
// supported width. A page-only overflow check misses clipped fixed overlays.
async function dialogGeometry(page, label, selector = ".document-error-dialog") {
	const dialog = page.locator(selector)
	await dialog.waitFor()
	for (const width of [1600, 1280, 900, 390]) {
		await page.setViewportSize({ width, height: 900 })
		await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
		await noOverflow(page, `${label} dialog ${width}`)
		const geometry = await dialog.evaluate(element => {
			const box = element.getBoundingClientRect()
			return { left: box.left, right: box.right, top: box.top, bottom: box.bottom, width: innerWidth, height: innerHeight, scroll: element.scrollWidth, client: element.clientWidth }
		})
		assert(geometry.left >= -1 && geometry.right <= geometry.width + 1 && geometry.top >= -1 && geometry.bottom <= geometry.height + 1 && geometry.scroll <= geometry.client + 1, `${label} dialog clipped at ${width}: ${JSON.stringify(geometry)}`)
		assert(await dialog.getByRole("button").evaluateAll(buttons => buttons.every(button => { const box = button.getBoundingClientRect(); return box.width > 0 && box.bottom <= innerHeight && box.right <= innerWidth })), `${label} dialog action unreachable at ${width}`)
		if (process.env.ESSDEE_SEWING_SCREENSHOTS) await page.screenshot({ path: `${process.env.ESSDEE_SEWING_SCREENSHOTS}/sewing-${label}-dialog-${width}.png`, fullPage: true, animations: "disabled" })
	}
	await page.setViewportSize({ width: 1280, height: 900 })
}

async function sewingDialogGeometry(page, label, actionNames) {
	const dialog = page.locator(".sewing-plan-dialog:visible")
	await dialog.waitFor()
	const originalViewport = page.viewportSize()
	for (const width of [1600, 1280, 900, 390]) {
		await page.setViewportSize({ width, height: 900 })
		await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
		await noOverflow(page, `${label} ${width}`)
		const geometry = await dialog.evaluate(element => {
			const box = element.getBoundingClientRect()
			const footer = element.querySelector(".p-dialog-footer")?.getBoundingClientRect()
			const content = element.querySelector(".p-dialog-content")
			return {
				dialog: { left: box.left, right: box.right, top: box.top, bottom: box.bottom },
				footer: footer && { left: footer.left, right: footer.right, top: footer.top, bottom: footer.bottom },
				contentOwnsScroll: Boolean(content && content.scrollHeight > content.clientHeight ? getComputedStyle(content).overflowY !== "visible" : true),
			}
		})
		assert(geometry.dialog.left >= -1 && geometry.dialog.right <= width + 1 && geometry.dialog.top >= -1 && geometry.dialog.bottom <= 901, `${label} dialog clips at ${width}px: ${JSON.stringify(geometry)}`)
		assert(geometry.footer && geometry.footer.left >= -1 && geometry.footer.right <= width + 1 && geometry.footer.bottom <= 901, `${label} footer clips at ${width}px: ${JSON.stringify(geometry)}`)
		assert(geometry.contentOwnsScroll, `${label} content does not own vertical overflow at ${width}px`)
		for (const name of actionNames) {
			const action = dialog.getByRole("button", { name, exact: true })
			assert(await action.isVisible(), `${label} action ${name} is not reachable at ${width}px`)
			const box = await action.boundingBox()
			assert(box && box.x >= -1 && box.x + box.width <= width + 1 && box.y >= -1 && box.y + box.height <= 901, `${label} action ${name} clips at ${width}px: ${JSON.stringify(box)}`)
		}
	}
	if (originalViewport) await page.setViewportSize(originalViewport)
}

async function readableReportDates(page, label) {
	const clipped = await page.locator(".report-filter-grid .erp-date-time-field input").evaluateAll(inputs => inputs.flatMap(input => {
		const style = getComputedStyle(input), canvas = document.createElement("canvas"), context = canvas.getContext("2d")
		context.font = style.font
		const text = input.value || input.placeholder
		const available = input.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight)
		return context.measureText(text).width > available + 1 ? [{ field: input.getAttribute("aria-label") || input.id, text, available, needed: context.measureText(text).width }] : []
	}))
	assert(!clipped.length, `${label} date text clipped: ${JSON.stringify(clipped)}`)
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
	await page.setViewportSize({ width: 1600, height: 900 })
	const launcherGeometry = await page.evaluate(() => {
		const shell = document.querySelector(".sewing-workspace-shell").getBoundingClientRect()
		const title = document.querySelector(".workspace-launcher__title h1").getBoundingClientRect()
		const picker = document.querySelector(".sewing-unit-picker").getBoundingClientRect()
		const grid = document.querySelector(".workspace-launcher__grid").getBoundingClientRect()
		return {
			shellLeft: shell.left,
			shellRight: innerWidth - shell.right,
			pickerRightOfTitle: picker.left > title.right,
			aligned: Math.abs((picker.top + picker.height / 2) - (title.top + title.height / 2)) <= 28,
			headerToCards: grid.top - Math.max(title.bottom, picker.bottom),
		}
	})
	assert(launcherGeometry.shellLeft <= 32 && launcherGeometry.shellRight <= 32, `Sewing launcher wastes horizontal space: ${JSON.stringify(launcherGeometry)}`)
	assert(launcherGeometry.pickerRightOfTitle && launcherGeometry.aligned, `Sewing Unit must share the desktop title row: ${JSON.stringify(launcherGeometry)}`)
	assert(launcherGeometry.headerToCards >= 0 && launcherGeometry.headerToCards <= 28, `Compact Sewing header leaves excessive space before cards: ${JSON.stringify(launcherGeometry)}`)
	assert(await page.locator(".department-page__nav").count() === 0, "Sewing must not render a separate back-navigation row")
	assert(await page.locator(".workspace-launcher__header").getByRole("link", { name: "Back to Workspaces", exact: true }).isVisible(), "Sewing title must own the compact back arrow")
	assert(!(await page.locator(".workspace-launcher__header").innerText()).includes("Department workspace"), "Sewing launcher retains the redundant workspace eyebrow")
	await page.setViewportSize({ width: 1280, height: 900 })
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
	await oneLoadPopup(page, state.error)
	assert(await page.getByRole("link", { name: "Back to Workspaces", exact: true }).isVisible(), "Capability failure must keep root navigation available")
	state.error = ""
	await page.getByRole("button", { name: "Retry", exact: true }).click()
	await cards.nth(2).waitFor()
	state.errorStatus = 403
	state.error = "Sewing access was denied. Please retry."
	await navigate(page, "/web/sewing")
	await oneLoadPopup(page, state.error)
	assert(await page.getByRole("link", { name: "Back to Workspaces", exact: true }).isVisible(), "HTTP 403 must keep root navigation available")
	assert(await cards.count() === 0, "HTTP 403 leaves Sewing cards visible")
	state.error = ""
	await page.getByRole("button", { name: "Retry", exact: true }).click()
	await cards.nth(2).waitFor()
	assert(await page.getByRole("alert").count() === 0, "HTTP 403 error remains after successful Retry")
	state.delay = 700
	await navigate(page, "/web/sewing")
	await page.getByRole("status").filter({ hasText: "Loading" }).waitFor()
	assert(await page.getByRole("link", { name: "Back to Workspaces", exact: true }).isVisible(), "Capability loading must keep root navigation available")
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
		await page.getByRole("link", { name: "Back to Sewing", exact: true }).click()
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
const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/sewing/plans', component: SewingPlans }, { path: '/sewing', component: { render: () => null } }] });
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
	function plan(name = "PLAN-A", lot = "LOT-A") {
		const data = { details: { item: "T-Shirt", lot, supplier: "UNIT-A", work_order: "WO-A", work_order_status: "Open", primary_values: sizes }, colours: { Navy: { colour: "Navy", variant_colour: "Navy", part: null, set_combination: { major_colour: "Navy" }, values: Object.fromEntries(sizes.map((size, i) => [size, { order_detail: `${name}-ROW-${i}`, item_variant: `UNTRUSTED-${size}`, order_qty: 100, sewing_in: 20, sewing_in_remaining: 80, sewing_out: 5, sewing_out_remaining: 15, data_entry: 0, pre_final: 2, final_inspection: 2 }])) } } }
		delete data.colours.Navy.values.S.sewing_in_remaining
		return data
	}
	const entry = { data: { "LOT-A": { "PLAN-A": plan(), "PLAN-OTHER": plan("PLAN-OTHER") }, "LOT-B": { "PLAN-B": plan("PLAN-B", "LOT-B") } }, input_types: ["Sewing In", "Sewing Out"], diff: { sewing_in: "order_qty", sewing_out: "sewing_in" }, allowances: { sewing_in: 5, sewing_out: 0 }, default_received_type: "" }
	const state = { dashboard: [{ input_type: "Sewing In", qty: 40 }, { input_type: "Sewing Out", qty: 15 }], dashboardError: "", dashboardDelay: 250, dashboardHold: null, entryError: "", entryHold: null, submitError: "", inspectionError: "", submitDelay: 0, loads: 0, authoritativeQty: 20 }
	page.on("pageerror", e => errors.push(e.message))
	await page.route("**/api/method/**", async route => {
		const method = route.request().url().split("/api/method/")[1], args = JSON.parse(route.request().postData() || "{}")
		requests.push({ method, args })
		let value = null, error = ""
		if (method.endsWith("get_capabilities")) value = { ...capabilities, plan_actions: { entry: { ...flags, can_create: true }, plan: { ...flags, can_write: true } } }
		else if (method.endsWith("get_dashboard_data")) { value = structuredClone(state.dashboard); error = state.dashboardError; if (state.dashboardHold) { const hold = state.dashboardHold; state.dashboardHold = null; await hold } else await new Promise(r => setTimeout(r, state.dashboardDelay)) }
		else if (method.endsWith("get_data_entry_data")) { state.loads++; value = structuredClone(entry); error = state.entryError; const xs = value.data["LOT-A"]["PLAN-A"].colours.Navy.values.XS; xs.sewing_in = state.authoritativeQty; xs.sewing_in_remaining = 100 - state.authoritativeQty; xs.sewing_out_remaining = state.authoritativeQty - xs.sewing_out; if (args.supplier === "UNIT-B") value.data = {}; if (state.entryHold) { const hold = state.entryHold; state.entryHold = null; await hold } }
		else if (method.endsWith("get_sewing_plan_entries")) value = {}
		else if (method.endsWith("submit_data_entry_log")) { await new Promise(r => setTimeout(r, state.submitDelay)); value = "ENTRY-SAVED"; error = state.submitError; if (!error) state.authoritativeQty += Number(args.payload.quantities.colours.Navy.values.XS.data_entry) }
		else if (method.endsWith("update_sewing_plan_data")) {
			await new Promise(r => setTimeout(r, state.submitDelay))
			value = "Success"; error = state.inspectionError
			const { lot, plan: planName, inspection_type: type, action, rows } = args.payload
			if (!error) for (const row of rows) for (const [size, quantities] of Object.entries(row.qty)) entry.data[lot][planName].colours[row.colour].values[size][type] = action === "revert" ? 0 : quantities[type]
		}
		else if (method.endsWith("link_search")) { error = state.linkError || ''; value = [{ name: args.doctype === "YRP Work Station" ? "Sewing Line 1" : "Good", label: args.doctype === "YRP Work Station" ? "Sewing Line 1" : "Good" }] }
		else throw new Error(`Unexpected plan request: ${method}`)
		await route.fulfill({ status: error ? 417 : 200, contentType: "application/json", body: JSON.stringify(error ? { _server_messages: JSON.stringify([JSON.stringify({ message: error })]), exc: "ValidationError" } : { message: value }) })
	})
	const select = async (name, option) => { await page.getByRole("combobox", { name, exact: true }).click(); await page.getByRole("option", { name: option, exact: true }).click() }
	const closeError = async (text) => { await page.locator(".document-error-dialog").getByText(text, { exact: false }).waitFor(); await page.getByRole("button", { name: "OK", exact: true }).click(); await page.locator(".document-error-dialog").waitFor({ state: "hidden" }) }
	const planCard = name => page.locator(`[data-sewing-plan-card='${name}']`)
	const openEntry = async name => { await planCard(name).getByRole("button", { name: `Record entry for ${name}`, exact: true }).click(); await page.locator(".sewing-plan-dialog").waitFor() }
	const closeEntry = async () => { await page.getByRole("button", { name: "Close entry", exact: true }).click(); await page.locator(".sewing-plan-dialog").waitFor({ state: "hidden" }) }
	const openInspection = async name => { await planCard(name).getByRole("button", { name: `Update inspection for ${name}`, exact: true }).click(); await page.locator(".sewing-plan-dialog").waitFor() }
	const closeInspection = async () => { await page.getByRole("button", { name: "Close inspection", exact: true }).click(); await page.locator(".sewing-plan-dialog").waitFor({ state: "hidden" }) }
	try {
		await page.goto(`http://127.0.0.1:${server.httpServer.address().port}/__plan-test`)
		await page.getByRole("tab", { name: "Dashboard", exact: true }).waitFor()
		assert(JSON.stringify(await page.getByRole("tab").allTextContents()) === JSON.stringify(["Dashboard", "Data Entry", "Entries", "Consumption", "Closed Work Order GRN"]), "Plan workspace must expose exactly the five approved tabs")
		const planHeader = await page.locator(".sewing-workspace-shell__header").evaluate(element => {
			const title = element.querySelector("h1").getBoundingClientRect(), picker = element.querySelector(".sewing-unit-picker").getBoundingClientRect()
			return { pickerRightOfTitle: picker.left > title.right, aligned: Math.abs((picker.top + picker.height / 2) - (title.top + title.height / 2)) <= 28 }
		})
		assert(planHeader.pickerRightOfTitle && planHeader.aligned, `Plan Sewing Unit must share the desktop title row: ${JSON.stringify(planHeader)}`)
		assert(await page.locator(".department-page__nav").count() === 0 && await page.locator(".sewing-workspace-shell__header").getByRole("link", { name: "Back to Sewing", exact: true }).isVisible(), "Plan header must use an inline back arrow")
		assert(!(await page.locator(".sewing-workspace-shell__header").innerText()).includes("Sewing workspace"), "Plan header retains the redundant workspace eyebrow")
		await page.getByRole("status").filter({ hasText: "Loading dashboard" }).waitFor()
		const dashboardCards = page.locator("[data-sewing-dashboard-card]")
		await dashboardCards.filter({ hasText: "Sewing In" }).waitFor()
		assert((await dashboardCards.filter({ hasText: "Sewing In" }).innerText()).includes("40"), "Dashboard lost configured stage quantities")
		assert(await dashboardCards.count() === 2 && await page.locator(".sewing-dashboard__table").count() === 0, "Open Work Order inputs must render as cards, not a table")
		assert(await page.locator("[data-sewing-plan-tab='dashboard'] h2").count() === 0 && !(await page.locator("[data-sewing-plan-tab='dashboard']").innerText()).includes("Recorded quantities by input type"), "Dashboard duplicates its tab title or selected Sewing Unit context")
		assert(!requests.some(r => r.method.endsWith("get_data_entry_data")), "Inactive Data Entry fetched")
		for (const width of [1600, 1280, 900, 390]) { await page.setViewportSize({ width, height: 900 }); await noOverflow(page, `Dashboard ${width}`); if (process.env.ESSDEE_SEWING_SCREENSHOTS) await page.screenshot({ path: `${process.env.ESSDEE_SEWING_SCREENSHOTS}/sewing-dashboard-${width}.png`, fullPage: true, animations: "disabled" }) }
		await page.setViewportSize({ width: 1280, height: 900 })
		let releaseRefresh
		state.dashboardHold = new Promise(resolve => { releaseRefresh = resolve })
		state.dashboardError = "Retained dashboard unavailable"
		await page.getByRole('button', { name: 'Refresh dashboard' }).click()
		assert(await dashboardCards.filter({ hasText: 'Sewing In' }).isVisible(), 'Dashboard refresh blanked useful results')
		assert(await page.getByRole('button', { name: 'Refresh dashboard' }).isDisabled(), 'Dashboard refresh allows duplicate requests')
		releaseRefresh(); await oneLoadPopup(page, state.dashboardError)
		assert(await dashboardCards.filter({ hasText: 'Sewing In' }).isVisible(), 'Dashboard failure lost useful results')
		state.dashboardError = ''
		state.dashboard = []; await page.getByRole("button", { name: "Refresh dashboard" }).click(); await page.getByText("No input quantities for open Work Orders.", { exact: true }).waitFor()
		state.dashboardError = "Dashboard unavailable"; await page.getByRole("button", { name: "Refresh dashboard" }).click(); await oneLoadPopup(page, state.dashboardError)
		state.dashboardError = ""; state.dashboard = [{ input_type: "Sewing In", qty: 41 }]; await page.getByRole("button", { name: "Retry", exact: true }).click(); await dashboardCards.filter({ hasText: "41" }).waitFor()
		const before = requests.length
		await page.getByRole("tab", { name: "Closed Work Order GRN", exact: true }).click(); await page.getByRole("combobox", { name: "Closed Work Order", exact: true }).waitFor()
		assert(await page.locator("[data-sewing-plan-tab]").count() === 1, "Inactive tab still mounted")
		assert(await page.locator("[data-sewing-plan-tab='closed-work-order-grn'] h2").count() === 0 && !(await page.locator("[data-sewing-plan-tab='closed-work-order-grn']").innerText()).includes("Create and submit a receipt for the selected Sewing Unit"), "Closed GRN duplicates its tab title or selected-unit explanation")
		assert(requests.length === before, "Closed GRN fetched without Work Order selection")
		state.entryError = "Entry data unavailable"
		await page.getByRole("tab", { name: "Data Entry", exact: true }).click()
		await oneLoadPopup(page, state.entryError)
		state.entryError = ""; await page.getByRole("button", { name: "Retry", exact: true }).click()
		await page.locator("[data-sewing-plan-card='PLAN-A']").waitFor()
		assert(await page.locator("[data-sewing-plan-tab='data-entry'] h2").count() === 0 && !(await page.locator("[data-sewing-plan-tab='data-entry']").innerText()).includes("Choose a Sewing Plan and record its production"), "Data Entry duplicates its tab title or instructional copy")
		assert(await page.locator("[data-sewing-plan-card]").count() === 3, "Data Entry must show available plan cards without requiring a filter")
		assert(await page.locator(".sewing-data-entry__lot").count() === 2, "Data Entry must group plans from different Lots")
		assert(await page.locator(".sewing-data-entry__lot").evaluateAll(groups => new Set(groups.map(group => group.getAttribute("aria-labelledby"))).size === groups.length), "Lot groups must use collision-safe heading IDs")
		assert(await page.locator(".sewing-data-entry__lot-header > div > span").count() === 0, "Lot groups waste space on a redundant Lot eyebrow")
		assert(await planCard("PLAN-A").locator(".sewing-data-entry__work-order").innerText() === "WO-A", "Plan card must lead with the Work Order")
		assert(await planCard("PLAN-A").locator(".sewing-data-entry__item").innerText() === "T-Shirt", "Plan card must show the Item below the Work Order")
		assert((await planCard("PLAN-A").locator(".sewing-data-entry__plan-reference").innerText()).includes("PLAN-A"), "Plan card must show the Sewing Plan as secondary context")
		const toolbarGeometry = await page.locator(".sewing-data-entry__toolbar").evaluate(element => {
			const field = element.querySelector(".common-field").getBoundingClientRect(), refresh = element.querySelector("button").getBoundingClientRect()
			return { adjacent: refresh.left >= field.right && refresh.left - field.right <= 20, aligned: Math.abs(refresh.bottom - field.bottom) <= 2 }
		})
		assert(toolbarGeometry.adjacent && toolbarGeometry.aligned && await page.locator(".sewing-data-entry__commands").count() === 0, `Lot and Refresh must share one compact row: ${JSON.stringify(toolbarGeometry)}`)
		for (const width of [1600, 1280, 900, 390]) {
			await page.setViewportSize({ width, height: 900 }); await noOverflow(page, `Data Entry cards ${width}`)
			const columns = await page.locator(".sewing-data-entry__cards").evaluateAll(elements => elements.map(element => getComputedStyle(element).gridTemplateColumns.split(" ").length))
			assert(columns.every(count => count === (width <= 760 ? 1 : 2)), `Data Entry card grid has ${columns.join(",")} columns at ${width}px`)
			const refreshBox = await page.getByRole("button", { name: "Refresh data entry", exact: true }).boundingBox()
			assert(refreshBox && refreshBox.x >= 0 && refreshBox.x + refreshBox.width <= width + 1, `Data Entry Refresh clips at ${width}px: ${JSON.stringify(refreshBox)}`)
			if (process.env.ESSDEE_SEWING_SCREENSHOTS) await page.screenshot({ path: `${process.env.ESSDEE_SEWING_SCREENSHOTS}/sewing-entry-cards-${width}.png`, fullPage: true, animations: "disabled" })
		}
		await page.setViewportSize({ width: 1280, height: 900 })
		assert(await page.locator("[data-sewing-plan-tab]").count() === 1, "Data Entry mounted alongside another tab")
		assert(requests.some(r => r.method.endsWith("get_data_entry_data") && r.args.supplier === "UNIT-A"), "Data Entry is not Supplier scoped")
		await page.getByRole("combobox", { name: "Lot", exact: true }).click(); assert(JSON.stringify(await page.getByRole("option").allTextContents()) === JSON.stringify(["LOT-A", "LOT-B"]), "Lot choices must come from current Supplier data"); await page.getByRole("option", { name: "LOT-B", exact: true }).click()
		assert(await page.locator("[data-sewing-plan-card='PLAN-B']").isVisible() && await page.locator("[data-sewing-plan-card='PLAN-A']").count() === 0, "Lot filter did not isolate the selected Lot")
		await page.locator(".p-select-clear-icon").click()
		assert(await page.locator("[data-sewing-plan-card]").count() === 3, "Clearing the Lot filter did not restore all plans")
		await page.getByRole("combobox", { name: "Lot", exact: true }).click(); await page.getByRole("option", { name: "LOT-A", exact: true }).click()
		await openEntry("PLAN-A")
		const quantity = page.getByRole("spinbutton", { name: "Navy XS Entry quantity", exact: true })
		assert(await quantity.inputValue() === "0", "Entry quantity must stay empty until an Input Type is selected")
		await select("Input Type", "Sewing In")
		assert(await quantity.inputValue() === "80", "Configured Sewing In remaining quantity was not prefilled")
		assert(await page.getByRole("spinbutton", { name: "Navy S Entry quantity", exact: true }).inputValue() === "0", "Missing server remaining balance must fail safe instead of prefilling a predecessor total")
		await quantity.fill("7")
		await closeEntry(); await openEntry("PLAN-OTHER"); assert(await quantity.inputValue() === "80", "Selected Input Type did not prefill another plan"); await quantity.fill("11"); await closeEntry(); await openEntry("PLAN-A")
		assert(await quantity.inputValue() === "7", "Changing plans lost the selected plan's edit")
		await closeEntry(); await page.getByRole("tab", { name: "Entries", exact: true }).click(); await page.getByRole("tab", { name: "Data Entry", exact: true }).click(); await planCard("PLAN-A").waitFor(); await openEntry("PLAN-A")
		assert(await quantity.inputValue() === '7', 'Tab switch discarded unsaved entry draft')
		assert(await page.locator(".sewing-plan-dialog").getByText("PLAN-A", { exact: false }).count() > 0, "Inactive-tab remount lost plan selection")
		await quantity.fill("7")
		await page.getByRole("button", { name: "Save entry", exact: true }).click(); await closeError("Complete all required entry fields.")
		assert(await quantity.inputValue() === "7", "Required-field validation lost quantity")
		await select("Input Type", "Sewing Out"); assert(await quantity.inputValue() === "15", "Configured Sewing Out remaining quantity was not prefilled")
		await quantity.fill("6"); await select("Input Type", "Sewing In"); assert(await quantity.inputValue() === "7", "Switching Input Type lost the Sewing In draft")
		await select("Input Type", "Sewing Out"); assert(await quantity.inputValue() === "6", "Switching Input Type lost the Sewing Out draft")
		await select("Input Type", "Sewing In")
		state.linkError = 'Work Station lookup unavailable'
		await page.getByRole('button', { name: 'Show Work Station options', exact: true }).click(); await oneLoadPopup(page, state.linkError)
		state.linkError = ''
		for (const [name, value] of [["Work Station", "Sewing Line 1"], ["Received Type", "Good"]]) { await page.getByRole("combobox", { name, exact: true }).fill(value); await page.getByRole("option", { name: value, exact: true }).click() }
		await closeEntry(); await page.getByRole("tab", { name: "Entries", exact: true }).click(); await page.getByRole("tab", { name: "Data Entry", exact: true }).click(); await planCard("PLAN-A").waitFor(); await openEntry("PLAN-A")
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
		await sewingDialogGeometry(page, "Entry editor", ["Close entry", "Save entry"])
		assert(await quantity.inputValue() === "7", "Resize lost quantity")
		assert(await page.getByRole("region", { name: "PLAN-A quantity matrix", exact: true }).evaluate(el => el.scrollWidth > el.clientWidth), "Matrix must own narrow overflow")
		await closeEntry(); await openInspection("PLAN-A")
		await sewingDialogGeometry(page, "Inspection editor", ["Close inspection", "Update inspection", "Revert inspection"])
		await closeInspection(); await openEntry("PLAN-A")
		const unsavedRequests = requests.filter(request => /submit_data_entry_log|update_sewing_plan_data/.test(request.method)).length
		await closeEntry(); await openInspection("PLAN-A"); await select("Inspection Type", "Final Inspection")
		await select("Inspection Type", "Pre Final"); await closeInspection(); await openEntry("PLAN-A")
		assert(await quantity.inputValue() === "7", "Changing inspection view discarded unsaved entry quantity")
		assert(await quantity.inputValue() === "7" && requests.filter(request => /submit_data_entry_log|update_sewing_plan_data/.test(request.method)).length === unsavedRequests, "Non-destructive view switch saved or discarded entry draft")
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
		assert(await quantity.inputValue() === "73", "Successful save did not prefill the refreshed remaining quantity")
		await select("Input Type", "Sewing Out"); assert(await quantity.inputValue() === "6", "Saving Sewing In cleared the unsaved Sewing Out draft"); await select("Input Type", "Sewing In")
		assert((await page.getByRole("region", { name: "PLAN-A quantity matrix", exact: true }).innerText()).includes("27"), "Authoritative stage values were not rendered after save")
		state.entryError = "Saved plan refresh unavailable"
		await quantity.fill("1"); await page.getByRole("button", { name: "Save entry", exact: true }).click(); await page.locator(".sewing-plan-dialog").getByText("Entry saved. Refresh the plan before recording more quantities.", { exact: true }).waitFor()
		await oneLoadPopup(page, state.entryError)
		assert(await page.getByRole("button", { name: "Save entry", exact: true }).isDisabled(), "Reload failure must block further writes until authoritative refresh")
		assert(await page.locator(".sewing-plan-dialog").getByText("Saved values could not be refreshed. Refresh this plan before recording more quantities.", { exact: true }).isVisible(), "Entry recovery reason is hidden behind the modal")
		state.entryError = ""; await page.locator(".sewing-plan-dialog").getByRole("button", { name: "Refresh plan", exact: true }).click(); await page.waitForFunction(() => !document.querySelector('button[aria-label="Save entry"]').disabled)
		await closeEntry(); await openInspection("PLAN-A"); await select("Inspection Type", "Pre Final")
		assert(await page.getByRole("spinbutton", { name: "Navy XS Inspection quantity", exact: true }).inputValue() === "2", "Inspection editor did not prefill the saved inspection total")
		await page.getByRole("spinbutton", { name: "Navy XS Inspection quantity", exact: true }).fill("9")
		await page.getByRole("button", { name: "Update inspection", exact: true }).click(); await page.getByText("Inspection updated.", { exact: true }).waitFor()
		assert(await page.getByRole("spinbutton", { name: "Navy XS Inspection quantity", exact: true }).inputValue() === "9", "Inspection update did not render authoritative total")
		await select("Inspection Type", "Final Inspection")
		const inspection = page.getByRole("spinbutton", { name: "Navy XS Inspection quantity", exact: true })
		assert(await inspection.inputValue() === "2", "Inspection recovery fixture needs the saved 2-unit total")
		state.entryError = "Inspection recovery unavailable"
		await page.getByRole("button", { name: "Revert inspection", exact: true }).click(); await page.locator(".sewing-plan-dialog").getByText("Inspection reverted. Refresh the plan before recording more quantities.", { exact: true }).waitFor()
		await oneLoadPopup(page, state.entryError)
		assert(await page.getByRole("button", { name: "Update inspection", exact: true }).isDisabled(), "Failed inspection refresh re-enabled stale Update draft")
		assert(await page.locator(".sewing-plan-dialog").getByText("Saved values could not be refreshed. Refresh this plan before recording more quantities.", { exact: true }).isVisible(), "Inspection recovery reason is hidden behind the modal")
		state.entryError = ""; await page.locator(".sewing-plan-dialog").getByRole("button", { name: "Refresh plan", exact: true }).click()
		await page.waitForFunction(() => !document.querySelector('button[aria-label="Update inspection"]').disabled)
		assert(await inspection.inputValue() === "0", "Acknowledged inspection revert recovery retained stale 2-unit draft instead of server zero")
		assert(requests.filter(r => r.method.endsWith("get_data_entry_data")).at(-1).args.lot === "LOT-A", "Inspection recovery lost acknowledged Supplier/Lot scope")
		const updates = requests.filter(r => r.method.endsWith("update_sewing_plan_data")).map(r => r.args.payload)
		assert(updates.length === 2 && updates[0].inspection_type === "pre_final" && updates[0].action === "update" && updates[1].inspection_type === "final_inspection" && updates[1].action === "revert", "Inspection update/revert contract mismatch")
		await inspection.fill("5"); state.inspectionError = "Inspection update rejected"
		await page.getByRole("button", { name: "Update inspection", exact: true }).click(); await closeError(state.inspectionError)
		assert(await inspection.inputValue() === "5", "Rejected inspection acknowledgement discarded user edit")
		state.inspectionError = ""; state.entryError = "Ordinary refresh unavailable"
		await closeInspection(); await page.getByRole("button", { name: "Refresh data entry" }).click(); await oneLoadPopup(page, state.entryError); await openInspection("PLAN-A")
		assert(await inspection.inputValue() === "5", "Ordinary load error discarded unsaved inspection edit")
		state.entryError = ""; await closeInspection()
		for (const scenario of ['entry-success', 'entry-rejection', 'inspection-success', 'inspection-rejection', 'revert-success', 'revert-rejection']) {
			const rejected = scenario.endsWith('rejection'), isEntry = scenario.startsWith('entry'), revert = scenario.startsWith('revert')
			state.submitError = isEntry && rejected ? 'Entry settlement rejected' : ''
			state.inspectionError = !isEntry && rejected ? 'Inspection settlement rejected' : ''
			state.submitDelay = 1200
			await openEntry('PLAN-A'); await quantity.fill('3'); await closeEntry()
			await openInspection('PLAN-A'); await inspection.fill('6'); await closeInspection()
			await page.getByRole('tab', { name: 'Entries', exact: true }).click()
			await page.getByRole('tab', { name: 'Data Entry', exact: true }).click(); await planCard('PLAN-A').waitFor()
			await openEntry('PLAN-A'); assert(await quantity.inputValue() === '3', `${scenario}: entry draft lost across tabs`); await closeEntry()
			await openInspection('PLAN-A'); assert(await inspection.inputValue() === '6', `${scenario}: inspection draft lost across tabs`)
			if (isEntry) { await closeInspection(); await openEntry('PLAN-A') }
			const method = isEntry ? 'submit_data_entry_log' : 'update_sewing_plan_data', beforeWrites = requests.filter(r => r.method.endsWith(method)).length
			const request = page.waitForRequest(r => r.url().endsWith(method))
			await page.getByRole('button', { name: isEntry ? 'Save entry' : revert ? 'Revert inspection' : 'Update inspection', exact: true }).click(); await request
			const beforeLoads = state.loads
			await page.evaluate(() => window.router.replace({ query: { ...window.router.currentRoute.value.query, tab: 'entries' } }))
			await page.locator("[data-sewing-plan-tab='entries']").waitFor()
			await page.evaluate(() => window.router.replace({ query: { ...window.router.currentRoute.value.query, tab: 'data-entry' } }))
			await planCard('PLAN-A').waitFor()
			assert(await planCard('PLAN-A').getByRole('button').evaluateAll(buttons => buttons.every(button => button.disabled)), `${scenario}: remount unlocked pending write`)
			assert(state.loads === beforeLoads, `${scenario}: remount fetched during mutation`)
			const response = page.waitForResponse(r => r.url().endsWith(method))
			await page.evaluate(() => window.router.replace({ query: { ...window.router.currentRoute.value.query, tab: 'entries' } })); await response
			assert(state.loads === beforeLoads, `${scenario}: inactive tab refreshed`)
			await page.evaluate(() => window.router.replace({ query: { ...window.router.currentRoute.value.query, tab: 'data-entry' } })); await planCard('PLAN-A').waitFor()
			if (rejected) {
				await closeError(isEntry ? state.submitError : state.inspectionError)
				await page.waitForFunction(() => document.querySelector('[data-sewing-plan-tab="data-entry"]').getAttribute('aria-busy') === 'false')
				await openEntry('PLAN-A'); assert(await quantity.inputValue() === '3', `${scenario}: rejection recovery erased entry edit`); await closeEntry()
				await openInspection('PLAN-A'); assert(await inspection.inputValue() === '6', `${scenario}: rejection recovery erased inspection edit`); await closeInspection()
			} else {
				await page.getByText(isEntry ? 'Entry saved.' : revert ? 'Inspection reverted.' : 'Inspection updated.', { exact: true }).waitFor()
				if (isEntry) { await openEntry('PLAN-A'); assert(Number(await quantity.inputValue()) > 0, `${scenario}: missing refreshed remaining-quantity prefill`); await closeEntry() }
				else { await openInspection('PLAN-A'); assert(await inspection.inputValue() === (revert ? '0' : '6'), `${scenario}: missing authoritative recovery`); await closeInspection() }
				await page.getByRole('button', { name: 'Dismiss save notice', exact: true }).click()
			}
			assert(state.loads === beforeLoads + 1 && requests.filter(r => r.method.endsWith(method)).length === beforeWrites + 1, `${scenario}: duplicate refresh or mutation`)
			await page.getByRole('tab', { name: 'Entries', exact: true }).click(); await page.getByRole('tab', { name: 'Data Entry', exact: true }).click(); await planCard('PLAN-A').waitFor()
			assert(await page.locator('.document-error-dialog').count() === 0 && await page.getByRole('button', { name: 'Dismiss save notice', exact: true }).count() === 0, `${scenario}: acknowledged outcome replayed`)
			console.log(`PASS Data Entry settlement ${scenario}`)
		}
		state.submitDelay = 0; state.submitError = ''; state.inspectionError = ''
		for (const rejected of [false, true]) {
			state.submitDelay = 700; state.submitError = rejected ? 'Discarded Supplier rejected' : ''
			await openEntry('PLAN-A'); await quantity.fill('4')
			const pending = page.waitForRequest(r => r.url().endsWith('submit_data_entry_log'))
			await page.getByRole('button', { name: 'Save entry', exact: true }).click(); await pending
			const settled = page.waitForResponse(r => r.url().endsWith('submit_data_entry_log'))
			await page.evaluate(() => window.router.replace('/sewing/plans?supplier=UNIT-B&tab=data-entry'))
			await page.getByText('No Sewing Plans for this Sewing Unit.', { exact: true }).waitFor(); await settled
			assert(await page.locator('.document-error-dialog').count() === 0 && await page.getByRole('button', { name: 'Dismiss save notice', exact: true }).count() === 0, 'Discarded Supplier delivered a late mutation outcome')
			await page.evaluate(() => window.router.replace('/sewing/plans?supplier=UNIT-A&tab=data-entry'))
			await planCard('PLAN-A').waitFor(); await openEntry('PLAN-A'); await select('Input Type', 'Sewing In')
			assert(Number(await quantity.inputValue()) > 0 && await quantity.inputValue() !== '4', 'Discarded Supplier draft leaked into new scope or remaining quantity was not prefilled')
			for (const [name, value] of [['Work Station', 'Sewing Line 1'], ['Received Type', 'Good']]) { await page.getByRole('combobox', { name, exact: true }).fill(value); await page.getByRole('option', { name: value, exact: true }).click() }
			await closeEntry()
		}
		state.submitDelay = 0; state.submitError = ''
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
		await page.locator("[data-sewing-dashboard-card]").filter({ hasText: "Current B stage" }).waitFor()
		const oldDashboard = page.waitForResponse(response => response.url().endsWith("get_dashboard_data") && response.request().postDataJSON().supplier === "UNIT-A")
		releaseDashboard(); await oldDashboard
		assert(await page.locator("[data-sewing-dashboard-card]").filter({ hasText: "Old A stage" }).count() === 0, "Delayed old Supplier dashboard overwrote current Supplier")
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
	const record = (date, cancellable) => ({ lot: "LOT-A", details: { Navy: { colour: "Navy", part: "Front", variant_colour: "Navy", set_combination: {}, total: 36, values: Object.fromEntries(sizes.map((size, i) => [size, i + 1])) }, Red: { colour: "Red", part: "Back", variant_colour: "Red", set_combination: {}, total: 44, values: Object.fromEntries(sizes.map((size, i) => [size, i + 2])) } }, work_station: "Line 1", input_type: "Sewing In", received_type: "Good", item_name: "T-Shirt", primary_values: sizes, is_set_item: 0, pack_attr: "Colour", set_attr: null, is_cancellable: cancellable, entry_date: date, entry_time: "09:30:00" })
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
		else if (method.endsWith("get_supplier_lots")) { error = state.lotError || ''; value = [[args.filters.supplier === "UNIT-B" ? "LOT-B" : "LOT-A", "T-Shirt"]]; if (state.lotHold) { const hold = state.lotHold; state.lotHold = null; await hold } }
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
		for (const scenario of ["cancel-success", "cancel-rejection", "cancel-rejection-recovery", "save-rejection", "cancel-rejection-inactive", "save-rejection-inactive", "save-rejection-supplier"]) {
			if (only !== "all" && only !== scenario) continue
			state.readOnly = false; state.cancelError = ""; state.saveError = ""; state.saveStatus = 417
			state.entries["ENTRY-A"] = record("2026-10-08", true)
			await page.goto(`http://127.0.0.1:${server.httpServer.address().port}/__operations-test`)
			await page.locator('[data-entry-id="ENTRY-A"]').waitFor()
			const isSave = scenario.startsWith("save-"), method = isSave ? "save_consumption_data" : "cancel_sewing_plan_entry"
			if (isSave) {
				await tab("consumption"); await selectLink("Lot", "LOT-A"); await quantity().fill("5")
				state.saveError = "You do not have permission to update consumption."; state.saveStatus = 403
			} else if (scenario !== "cancel-success") state.cancelError = "This entry is no longer eligible for cancellation."
			let release; const hold = new Promise(resolve => release = resolve)
			if (isSave) state.saveHold = hold; else state.cancelHold = hold
			const pendingRequest = page.waitForRequest(request => request.url().endsWith(method))
			if (isSave) await page.getByRole("button", { name: "Save consumption", exact: true }).click()
			else { await page.locator('[data-entry-id="ENTRY-A"]').getByRole("button", { name: /^Cancel entry from/ }).click(); await page.locator('.document-confirmation-shell').getByRole("button", { name: "Cancel entry", exact: true }).click() }
			await pendingRequest
			await tab(isSave ? "entries" : "consumption")
			if (isSave) await page.locator('[data-entry-id="ENTRY-B"]').waitFor()
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
				if (scenario === 'cancel-rejection-recovery') state.entryError = 'Cancellation recovery unavailable'
				release(); await settled
			}
			if (scenario === 'cancel-rejection-recovery') {
				await page.locator('.document-error-dialog').getByText(state.entryError, { exact: true }).waitFor()
				await page.getByRole('button', { name: 'OK', exact: true }).click()
				state.entryError = ''
			}
			if (scenario === "cancel-success") {
				await page.locator('[data-entry-id="ENTRY-B"]').waitFor({ timeout: 2500 }).catch(() => { throw new Error("Remounted Entries ignored successful cancellation settlement and remained falsely empty") })
				await page.getByText("Entry cancelled.", { exact: true }).waitFor()
				assert(await page.locator('[data-entry-id="ENTRY-A"]').count() === 0, "Remounted Entries retained cancelled record")
				assert(count("get_sewing_plan_entries") === beforeSettlementReads + 1, "Successful remounted cancellation must refresh exactly once")
			} else {
				const message = isSave ? state.saveError : state.cancelError
				await page.locator(".document-error-dialog").getByText(message, { exact: false }).waitFor({ timeout: 2500 }).catch(() => { throw new Error(`${scenario}: late rejection disappeared after remount`) })
				assert((await page.locator(".document-error-dialog").innerText()).includes(message), `${scenario}: shared rejection popup missing plain server message`)
				if (isSave) { assert(await quantity().inputValue() === "5", "Late 403 discarded consumption draft"); assert(await page.getByRole("button", { name: "Save consumption", exact: true }).isEnabled(), "Rejected consumption stayed locked after settlement"); assert(count("get_consumption_mapping_data") === beforeSettlementReads, "Rejected save reloaded away the draft") }
				else if (scenario !== 'cancel-rejection-recovery') { await page.locator('[data-entry-id="ENTRY-A"]').waitFor(); assert(count("get_sewing_plan_entries") === beforeSettlementReads + 1, "Rejected remounted cancellation failed to load retained entries") }
				await closeError(message)
				if (scenario === 'cancel-rejection-recovery') { await page.getByRole('button', { name: 'Retry', exact: true }).click(); await page.locator('[data-entry-id="ENTRY-A"]').waitFor() }
				await tab(isSave ? "entries" : "consumption"); await tab(isSave ? "consumption" : "entries")
				assert(await page.locator(".document-error-dialog").count() === 0, `${scenario}: acknowledged rejection repeated after another remount`)
			}
			console.log(`PASS settlement ${scenario}: navigation before response, active-only refresh, persistent outcome and acknowledgement`)
		}
		assert(errors.length === 0 && warnings.length === 0, `Settlement browser issues: ${[...errors, ...warnings].join("; ")}`)
	}
	try {
		if (settlementCase) { await settlementRegressions(settlementCase); return }
		state.entryError = 'Initial entries unavailable'
		await page.goto(`http://127.0.0.1:${server.httpServer.address().port}/__operations-test`)
		await page.locator("[data-sewing-plan-tab='entries']").waitFor()
		assert(await page.locator("[data-sewing-plan-tab='entries'] h2").count() === 0 && !(await page.locator("[data-sewing-plan-tab='entries']").innerText()).includes("Saved inputs grouped by entry date"), "Entries duplicates its tab title or explanatory copy")
		await oneLoadPopup(page, state.entryError)
		state.entryError = ''; await page.getByRole('button', { name: 'Retry', exact: true }).click()
		await page.getByRole("heading", { name: "08-10-2026", exact: true }).waitFor()
		assert(count("get_sewing_plan_entries") === 2 && count("get_consumption_mapping_data") === 0, "Initial active-only load/retry broken")
		assert(await page.locator("[data-entry-date]").first().getAttribute("data-entry-date") === "2026-10-08", "Newest entry date must appear first")
		assert(await page.locator("[data-entry-date='2026-10-08'] [data-entry-id]").count() === 2 && await page.locator("[data-entry-date='2026-10-01'] [data-entry-id]").count() === 1, "Entries not grouped by date")
		assert(await page.locator("[data-entry-id='ENTRY-A']").getByRole("spinbutton", { name: "Navy XS Quantity", exact: true }).inputValue() === "1", "Entry matrix lost numeric quantities")
		assert(await page.locator("[data-entry-id='ENTRY-A']").getByRole("spinbutton", { name: "Navy XS Quantity", exact: true }).isDisabled(), "Saved entry matrix became editable")
		const entryCard = page.locator("[data-entry-id='ENTRY-A']")
		const entryText = await entryCard.innerText()
		assert(!entryText.includes("ENTRY-A") && !entryText.includes("Quantities by colour and size"), "Entries exposes an internal document name or redundant matrix caption")
		assert(JSON.stringify(await entryCard.locator(".sewing-entries__meta--strong").allTextContents()) === JSON.stringify(["Line 1", "Sewing In", "Good"]), "Work Station, Input Type and Received Type are not the prominent entry metadata")
		assert((await entryCard.locator(".sewing-entries__meta--strong").evaluateAll(elements => elements.map(el => Number.parseInt(getComputedStyle(el).fontWeight, 10)).every(weight => weight >= 600))), "Prominent entry metadata is not visually stronger")
		assert(Number.parseFloat(await entryCard.locator(".sewing-quantity-matrix td").first().evaluate(el => getComputedStyle(el).fontSize)) >= 13, "Saved entry matrix text remains too small")
		const savedRowColours = await entryCard.locator(".sewing-quantity-matrix tbody tr").evaluateAll(rows => rows.slice(0, 2).map(row => getComputedStyle(row).backgroundColor))
		assert(savedRowColours.length > 1 && savedRowColours[0] !== savedRowColours[1], "Saved entry rows are visually indistinguishable")
		assert(await page.getByRole("button", { name: /^Cancel entry from 08-10-2026/ }).count() === 1, "Cancel must depend only on returned is_cancellable and expose contextual accessible text")
		state.lotError = 'Entry Lot lookup unavailable'
		await page.getByRole('button', { name: 'Show Lot options', exact: true }).click(); await oneLoadPopup(page, state.lotError)
		state.lotError = ''
		state.entryError = 'Entries refresh unavailable'
		await page.getByRole('button', { name: 'Refresh entries', exact: true }).click(); await oneLoadPopup(page, state.entryError)
		assert(await page.locator('[data-entry-id="ENTRY-A"]').isVisible(), 'Entries refresh failure lost rows')
		state.entryError = ''; const entryRetry = requests.length
		await page.getByRole('button', { name: 'Retry', exact: true }).click()
		await page.locator('[data-sewing-plan-tab="entries"][aria-busy="false"]').waitFor()
		assert(requests.slice(entryRetry).every(r => r.method.endsWith('get_sewing_plan_entries')), 'Entries retry fetched inactive tab')
		await selectLink("Work Station", "Line 1"); await selectLink("Input Type", "Sewing In"); await selectLink("Lot", "LOT-A")
		await page.waitForFunction(() => document.querySelector('[data-sewing-plan-tab="entries"]').getAttribute('aria-busy') === 'false')
		const filteredEntries = page.waitForResponse(r => r.url().endsWith("get_sewing_plan_entries") && r.request().postDataJSON().lot_name === "LOT-A")
		await page.getByRole("button", { name: "Refresh entries", exact: true }).click(); await filteredEntries
		const filters = requests.filter(r => r.method.endsWith("get_sewing_plan_entries")).at(-1).args
		assert(JSON.stringify(filters) === JSON.stringify({ supplier: "UNIT-A", work_station: "Line 1", input_type: "Sewing In", lot_name: "LOT-A" }), `Wrong Entries filters: ${JSON.stringify(filters)}`)
		await entryCard.getByRole("button", { name: /^Cancel entry from/ }).click()
		await page.locator(".document-confirmation-shell").waitFor()
		await dialogGeometry(page, "entry-confirmation", ".document-confirmation-shell")
		assert(count("cancel_sewing_plan_entry") === 0, "Cancel bypassed shared confirmation")
		await page.getByRole("button", { name: "Keep entry", exact: true }).click()
		assert(await page.locator("[data-entry-id='ENTRY-A']").count() === 1, "Dismissed cancel removed entry")
		state.cancelError = "This entry is no longer eligible for cancellation."
		await entryCard.getByRole("button", { name: /^Cancel entry from/ }).click()
		await page.locator(".document-confirmation-shell").getByRole("button", { name: "Cancel entry", exact: true }).click()
		await closeError(state.cancelError)
		assert(await page.locator("[data-entry-id='ENTRY-A']").count() === 1, "Server rejection optimistically removed entry")
		state.cancelError = ""; state.cancelDelay = 250
		const beforeCancelLoads = count("get_sewing_plan_entries"), beforeCancel = count("cancel_sewing_plan_entry")
		await entryCard.getByRole("button", { name: /^Cancel entry from/ }).click()
		await page.locator(".document-confirmation-shell").getByRole("button", { name: "Cancel entry", exact: true }).evaluate(el => { el.click(); el.click() })
		await page.getByText("Entry cancelled.", { exact: true }).waitFor()
		assert(count("cancel_sewing_plan_entry") === beforeCancel + 1 && count("get_sewing_plan_entries") === beforeCancelLoads + 1, "Cancel duplicate lock or authoritative refresh broken")
		assert(await page.locator("[data-entry-id='ENTRY-A']").count() === 0, "Successful cancellation did not reload entries")
		assert(requests.filter(r => r.method.endsWith("cancel_sewing_plan_entry")).at(-1).args.doc_id === "ENTRY-A", "Cancellation lost entry identity")
		await tab("consumption")
		assert(await page.locator("[data-sewing-plan-tab='consumption'] h2").count() === 0 && !(await page.locator("[data-sewing-plan-tab='consumption']").innerText()).includes("Record consumption for one Sewing Unit and Lot"), "Consumption duplicates its tab title or selected-unit explanation")
		assert(count("get_consumption_mapping_data") === 0, "Consumption fetched before Lot selection")
		state.lotError = 'Consumption Lot lookup unavailable'
		await page.getByRole('button', { name: 'Show Lot options', exact: true }).click(); await oneLoadPopup(page, state.lotError)
		state.lotError = ''
		state.mappingError = 'Initial consumption unavailable'
		await selectLink("Lot", "LOT-A")
		await oneLoadPopup(page, state.mappingError)
		state.mappingError = ''; const mappingRetry = requests.length
		await page.getByRole('button', { name: 'Retry', exact: true }).click()
		await quantity().waitFor()
		assert(requests.slice(mappingRetry).every(r => r.method.endsWith('get_consumption_mapping_data')), 'Consumption retry fetched inactive tab')
		const lotArgs = requests.filter(r => r.method.endsWith("get_supplier_lots")).at(-1).args
		assert(JSON.stringify(lotArgs) === JSON.stringify({ doctype: "SD YRP Lot", txt: "LOT-A", searchfield: "name", start: 0, page_len: 20, filters: { supplier: "UNIT-A" } }), `Lot query is not Supplier scoped: ${JSON.stringify(lotArgs)}`)
		assert(JSON.stringify(requests.filter(r => r.method.endsWith("get_consumption_mapping_data")).at(-1).args) === JSON.stringify({ supplier: "UNIT-A", lot: "LOT-A" }), "Consumption read lost explicit scope")
		assert((await page.locator("[data-sewing-plan-tab='consumption']").innerText()).includes("Kg") && (await page.locator("[data-sewing-plan-tab='consumption']").innerText()).includes("1.25"), "BOM/UOM context missing")
		assert(Number.parseFloat(await page.locator(".sewing-consumption-table td").first().evaluate(el => getComputedStyle(el).fontSize)) >= 13, "Consumption table text remains too small")
		const consumptionRowColours = await page.locator(".sewing-consumption-table tbody tr").first().locator("xpath=..//tr").evaluateAll(rows => rows.slice(0, 2).map(row => getComputedStyle(row).backgroundColor))
		assert(consumptionRowColours.length > 1 && consumptionRowColours[0] !== consumptionRowColours[1], "Consumption table rows are visually indistinguishable")
		await quantity().fill("4.25"); await weight().fill("1.5")
		state.mappingError = 'Consumption refresh unavailable'
		await page.getByRole('button', { name: 'Refresh consumption', exact: true }).click(); await oneLoadPopup(page, state.mappingError)
		assert(await quantity().inputValue() === '4.25' && await weight().inputValue() === '1.5', 'Consumption load failure lost drafts')
		state.mappingError = ''
		const beforeSwitch = count("get_consumption_mapping_data")
		await tab("entries"); await page.getByRole("heading", { name: "08-10-2026", exact: true }).waitFor()
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
		await oneLoadPopup(page, state.mappingError)
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
		await tab("entries"); await page.getByRole("heading", { name: "08-10-2026", exact: true }).waitFor()
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
			await tab("entries"); await page.getByRole("heading", { name: "08-10-2026", exact: true }).waitFor(); await noOverflow(page, `Entries ${width}`)
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
		await page.getByRole("heading", { name: "08-10-2026", exact: true }).waitFor()
		let releaseEntries; state.entryHold = new Promise(r => releaseEntries = r)
		const pendingEntries = page.waitForRequest(r => r.url().endsWith("get_sewing_plan_entries") && r.postDataJSON().supplier === "UNIT-A")
		await page.getByRole("button", { name: "Refresh entries", exact: true }).click(); await pendingEntries
		await page.evaluate(() => window.router.replace('/sewing/plans?supplier=UNIT-B&tab=entries'))
		await page.locator('[data-entry-id="ENTRY-UNIT-B"]').waitFor()
		const oldEntries = page.waitForResponse(r => r.url().endsWith("get_sewing_plan_entries") && r.request().postDataJSON().supplier === "UNIT-A")
		releaseEntries(); await oldEntries
		assert(await page.locator('[data-entry-id="ENTRY-OLD"]').count() === 0, "Delayed A entries overwrote B")
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

async function closedGrnSuite(browser) {
	const harness = `
import { createApp } from 'vue'; import { createRouter, createMemoryHistory, RouterView } from 'vue-router';
import PrimeVue from 'primevue/config'; import Aura from '@primeuix/themes/aura';
import SewingPlans from '/src/departments/sewing/SewingPlans.vue';
import '@fontsource-variable/inter'; import 'primeicons/primeicons.css'; import '/src/styles/main.css'; import '/src/styles/enterprise.css';
const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/sewing/plans', component: SewingPlans }, { path: '/sewing', component: { render: () => null } }] });
await router.push('/sewing/plans?supplier=UNIT-A&tab=closed-work-order-grn'); window.router = router;
createApp(RouterView).use(router).use(PrimeVue, { theme: { preset: Aura, options: { darkModeSelector: false } } }).mount('#app');`
	const server = await createServer({ root: fileURLToPath(new URL("../frontend", import.meta.url)), server: { host: "127.0.0.1", port: 0 }, plugins: [{
		name: "closed-grn-verifier", resolveId(id) { if (id === "/__closed-grn.js") return "\0closed-grn" }, load(id) { if (id === "\0closed-grn") return harness },
		configureServer(server) { server.middlewares.use((req, res, next) => { if (req.url !== "/__closed-grn") return next(); res.setHeader("Content-Type", "text/html"); res.end('<!doctype html><html><body><div id="app"></div><script type="module" src="/__closed-grn.js"></script></body></html>') }) },
	}] })
	await server.listen()
	const page = await browser.newPage({ viewport: { width: 1280, height: 900 } }); page.setDefaultTimeout(10_000)
	const requests = [], errors = [], warnings = [], sizes = ["XS", "S", "M", "L", "XL", "2XL", "3XL", "4XL"]
	const state = { create: true, submit: true, error: "", reloadError: "", hold: null, detailsHold: null, searchHold: null, saved: 0 }
	const groups = [{ primary_attribute: "Size", primary_attribute_values: sizes, attributes: ["Colour", "Part"], items: ["Good", "Reject"].map(type => ({ name: "T-Shirt", primary_attribute: "Size", attributes: { Colour: "Navy", Part: "Body" }, default_uom: "Nos", dimensions: { received_type: type, lot: "LOT-A" }, values: Object.fromEntries(sizes.map(size => [size, { qty: 0, pending_quantity: 10, max_receivable_quantity: 10.5, rate: 123, ref_doctype: "YRP Work Order Receivables", ref_docname: `ROW-${size}` }])) })) }]
	page.on("pageerror", e => errors.push(e.message)); page.on("console", m => { if (m.type() === "warning") warnings.push(m.text()) })
	await page.route("**/api/method/**", async route => {
		const method = new URL(route.request().url()).pathname.split("/api/method/")[1], args = JSON.parse(route.request().postData() || "{}")
		requests.push({ method, args }); let value = null, error = ""
		if (method.endsWith("get_capabilities")) value = { ...capabilities, plan_actions: { goods_received_note: { ...flags, can_create: state.create, can_submit: state.submit } } }
		else if (method.endsWith("getdoctype")) return route.fulfill({ contentType: "application/json", body: JSON.stringify({ docs: [{ name: "YRP Goods Received Note", fields: [{ fieldname: "naming_series", fieldtype: "Select", label: "Naming Series", options: "GRN-2627-\nGRN-TEST-", default: "GRN-2627-", reqd: 1 }] }] }) })
		else if (method.endsWith("get_closed_sewing_work_orders")) { value = [[args.filters.supplier === "UNIT-A" ? "WO-A" : "WO-B", "LOT-A", "T-Shirt", "Sewing"]]; error = state.reloadError; if (state.searchHold) { const hold = state.searchHold; state.searchHold = null; await hold } }
		else if (method.endsWith("get_closed_work_order_grn_details")) { error = state.detailsError || ''; value = { work_order: args.work_order, supplier: args.supplier, lot: args.supplier === "UNIT-A" ? "LOT-A" : "LOT-B", item: "T-Shirt", process: "Sewing", has_pending_items: true, item_details: structuredClone(groups) }; if (state.detailsHold) { const hold = state.detailsHold; state.detailsHold = null; await hold } }
		else if (method.endsWith("create_closed_work_order_grn")) { if (state.hold) { const hold = state.hold; state.hold = null; await hold } error = state.error; if (!error) value = { name: `GRN-SAVED-${++state.saved}`, docstatus: 1 } }
		else if (method.endsWith("get_sewing_plan_entries")) value = {}
		else if (method.endsWith("link_search")) value = []
		else throw new Error(`Unexpected Closed GRN request: ${method}`)
		return route.fulfill({ status: error ? 417 : 200, contentType: "application/json", body: JSON.stringify(error ? { _server_messages: JSON.stringify([JSON.stringify({ message: error })]), exc: "ValidationError" } : { message: value }) })
	})
	const count = suffix => requests.filter(r => r.method.endsWith(suffix)).length
	const picker = () => page.getByRole("combobox", { name: "Closed Work Order", exact: true })
	const qty = () => page.getByRole("spinbutton", { name: "Good row 1 XS received quantity", exact: true })
	const action = () => page.getByRole("button", { name: "Create & Submit GRN", exact: true })
	const selectWo = async (name = "WO-A") => { await picker().fill(name); await page.getByRole("option", { name, exact: true }).click(); await qty().waitFor() }
	const tab = name => page.evaluate(name => window.router.replace({ query: { ...window.router.currentRoute.value.query, tab: name } }), name)
	const fill = async () => { await selectWo(); await page.getByRole("textbox", { name: "Supplier Document Number", exact: true }).fill("SUP-007"); await page.getByRole("textbox", { name: "Vehicle Number", exact: true }).fill("KA-01-1234"); await page.getByRole("textbox", { name: "DC Number", exact: true }).fill("DC-007"); await page.getByRole("textbox", { name: "Comments", exact: true }).fill("Keep this receipt draft"); await qty().fill("2") }
	const closeError = async text => { await page.locator(".document-error-dialog").getByText(text, { exact: false }).waitFor(); await page.getByRole("button", { name: "OK", exact: true }).click(); await page.locator(".document-error-dialog").waitFor({ state: "hidden" }) }
	try {
		await page.goto(`http://127.0.0.1:${server.httpServer.address().port}/__closed-grn`)
		await picker().waitFor()
		assert(count("get_closed_work_order_grn_details") === 0, "Closed GRN fetched without selected WO")
		state.reloadError = 'Closed Work Order lookup unavailable'
		await page.getByRole('button', { name: 'Show Closed Work Order options', exact: true }).click(); await oneLoadPopup(page, state.reloadError)
		state.reloadError = ''
		state.detailsError = 'Initial receipt details unavailable'
		await picker().fill('WO-A'); await page.getByRole('option', { name: 'WO-A', exact: true }).click(); await oneLoadPopup(page, state.detailsError)
		state.detailsError = ''; const detailRetry = requests.length
		await page.getByRole('button', { name: 'Retry', exact: true }).click(); await qty().waitFor()
		assert(requests.slice(detailRetry).every(r => /get_closed_sewing_work_orders|get_closed_work_order_grn_details|getdoctype/.test(r.method)), 'Closed GRN retry fetched inactive tab')
		await fill()
		state.reloadError = 'Receipt refresh unavailable'
		await page.getByRole('button', { name: 'Refresh closed Work Orders', exact: true }).click(); await oneLoadPopup(page, state.reloadError)
		assert(await qty().inputValue() === '2' && await page.getByRole('textbox', { name: 'Comments', exact: true }).inputValue() === 'Keep this receipt draft', 'Closed GRN refresh failure lost draft')
		state.reloadError = ''; await page.getByRole('button', { name: 'Retry', exact: true }).click()
		await page.locator('[data-sewing-plan-tab="closed-work-order-grn"][aria-busy="false"]').waitFor()
		await qty().fill("-1"); await action().click(); await closeError("Enter a finite, non-negative quantity")
		assert(count("create_closed_work_order_grn") === 0, "Invalid negative quantity reached the server")
		await qty().fill("2")
		const entered = await page.locator('.closed-grn-editor input, .closed-grn-editor textarea').evaluateAll(elements => elements.map(el => [el.id, el.value]))
		for (const label of ["Naming Series", "Posting Date", "Posting Time", "Delivery Date", "Supplier Document Number", "Supplier Document Date", "Vehicle Number", "DC Number", "Comments"]) assert(await page.getByRole(/Series|Date|Time/.test(label) ? "combobox" : "textbox", { name: label, exact: true }).count() === 1, `Missing closed GRN field: ${label}`)
		assert((await page.locator(".closed-grn-editor").innerText()).includes("Received Type"), "Received Type buckets absent")
		assert(Number.parseFloat(await page.locator(".closed-grn-editor td").first().evaluate(el => getComputedStyle(el).fontSize)) >= 13, "Closed GRN table text remains too small")
		const grnRowColours = await page.locator(".closed-grn-editor tbody tr").first().locator("xpath=..//tr").evaluateAll(rows => rows.slice(0, 2).map(row => getComputedStyle(row).backgroundColor))
		assert(grnRowColours.length > 1 && grnRowColours[0] !== grnRowColours[1], "Closed GRN rows are visually indistinguishable")
		assert(await page.locator(".sewing-closed-grn__actions").evaluate(el => getComputedStyle(el).justifyContent) === "flex-end", "Create & Submit GRN is not aligned to the right")
		assert(requests.some(r => r.method.endsWith("get_closed_sewing_work_orders") && r.args.filters.supplier === "UNIT-A"), "Closed WO picker lost Supplier filter")
		for (const width of [390, 900, 1280, 1600]) {
			await page.setViewportSize({ width, height: 900 }); await noOverflow(page, `Closed GRN ${width}`)
			if (width === 390) assert(await page.locator(".closed-grn-editor__scroll").first().evaluate(el => el.scrollWidth > el.clientWidth && getComputedStyle(el).overflowX === "auto"), "Closed GRN matrix overflow is not contained")
			if (process.env.ESSDEE_SEWING_SCREENSHOTS) await page.screenshot({ path: `${process.env.ESSDEE_SEWING_SCREENSHOTS}/sewing-closed-grn-${width}.png`, fullPage: true, animations: "disabled" })
		}
		state.error = "Supplier reference rejected"; await action().click(); await dialogGeometry(page, "closed-grn"); await closeError(state.error)
		assert(JSON.stringify(await page.locator('.closed-grn-editor input, .closed-grn-editor textarea').evaluateAll(elements => elements.map(el => [el.id, el.value]))) === JSON.stringify(entered), "Server rejection changed one or more receipt fields")
		assert(await qty().inputValue() === "2" && await page.getByRole("textbox", { name: "Comments", exact: true }).inputValue() === "Keep this receipt draft" && await page.getByRole("textbox", { name: "Supplier Document Number", exact: true }).inputValue() === "SUP-007", "Server rejection discarded entered GRN values")
		const payload = requests.find(r => r.method.endsWith("create_closed_work_order_grn")).args
		assert(payload.work_order === "WO-A" && payload.supplier === "UNIT-A", "Receipt submitted with wrong scope")
		const serialized = JSON.stringify(payload.item_details)
		for (const forbidden of ['"rate"', '"default_uom"', '"lot"', '"item_variant"', '"max_receivable_quantity"']) assert(!serialized.includes(forbidden), `Receipt payload trusts ${forbidden}`)
		assert(payload.item_details[0].items[0].values.XS.ref_docname === "ROW-XS" && payload.item_details[0].items[0].values.XS.qty === 2 && payload.item_details[0].items[0].dimensions.received_type === "Good", "Grouped contract lost reference, quantity or Received Type")
		state.error = ""; let release; state.hold = new Promise(r => release = r)
		const before = count("create_closed_work_order_grn"), pending = page.waitForRequest(r => r.url().endsWith("create_closed_work_order_grn"))
		await action().click(); await pending; await action().evaluate(el => { el.click(); el.click() })
		assert(await action().isDisabled() && count("create_closed_work_order_grn") === before + 1, "Double click created duplicate GRNs")
		state.reloadError = "Eligibility unavailable"; release()
		await page.getByText(/GRN-SAVED-1.*Submitted/).waitFor()
		await oneLoadPopup(page, state.reloadError)
		assert(await qty().count() === 0 && await picker().inputValue() === "", "Acknowledged GRN did not reset editor")
		assert(await picker().isDisabled(), "Acknowledged receipt reload failure invites duplicate creation")
		state.reloadError = ""; await page.getByRole("button", { name: "Refresh closed Work Orders", exact: true }).click(); await fill()
		state.error = "Inactive rejection"; state.hold = new Promise(r => release = r)
		const rejected = page.waitForRequest(r => r.url().endsWith("create_closed_work_order_grn")); await action().click(); await rejected; await tab("entries"); await page.locator('[data-sewing-plan-tab="entries"]').waitFor()
		const reads = count("get_closed_sewing_work_orders"); const settled = page.waitForResponse(r => r.url().endsWith("create_closed_work_order_grn")); release(); await settled
		assert(count("get_closed_sewing_work_orders") === reads, "Inactive write fetched receipt records")
		await tab("closed-work-order-grn"); await closeError(state.error); assert(await qty().inputValue() === "2", "Inactive rejection lost draft")
		state.error = ""; state.hold = new Promise(r => release = r); const pendingSuccess = page.waitForRequest(r => r.url().endsWith("create_closed_work_order_grn")); await action().click(); await pendingSuccess
		await tab("entries"); await page.locator('[data-sewing-plan-tab="entries"]').waitFor(); const beforeSuccess = count("get_closed_sewing_work_orders"); const success = page.waitForResponse(r => r.url().endsWith("create_closed_work_order_grn")); release(); await success
		assert(count("get_closed_sewing_work_orders") === beforeSuccess, "Inactive acknowledgement fetched receipt records")
		await tab("closed-work-order-grn"); await page.getByText(/GRN-SAVED-2.*Submitted/).waitFor(); assert(await qty().count() === 0, "Inactive successful GRN retained resubmittable editor")
		await page.getByRole("button", { name: "Refresh closed Work Orders", exact: true }).click()
		let releaseDetails; state.detailsHold = new Promise(r => releaseDetails = r)
		const oldDetail = page.waitForRequest(r => r.url().endsWith("get_closed_work_order_grn_details")); await picker().fill("WO-A"); await page.getByRole("option", { name: "WO-A", exact: true }).click(); await oldDetail
		await page.evaluate(() => window.router.replace('/sewing/plans?supplier=UNIT-B&tab=closed-work-order-grn')); await picker().waitFor(); await selectWo("WO-B")
		const oldResponse = page.waitForResponse(r => r.url().endsWith("get_closed_work_order_grn_details") && r.request().postDataJSON().supplier === "UNIT-A"); releaseDetails(); await oldResponse
		assert(await picker().inputValue() === "WO-B" && await page.getByText("LOT-B", { exact: true }).count() > 0, "Old Supplier detail overwrote new Supplier")
		let releaseSearch; state.searchHold = new Promise(r => releaseSearch = r)
		const staleSearch = page.waitForRequest(r => r.url().endsWith("get_closed_sewing_work_orders") && r.postDataJSON().filters.supplier === "UNIT-B")
		await picker().fill("WO"); await staleSearch
		await page.evaluate(() => window.router.replace('/sewing/plans?supplier=UNIT-A&tab=closed-work-order-grn')); await picker().waitFor(); await fill()
		const searchResponse = page.waitForResponse(r => r.url().endsWith("get_closed_sewing_work_orders") && r.request().postDataJSON().filters.supplier === "UNIT-B"); releaseSearch(); await searchResponse
		assert(await picker().inputValue() === "WO-A" && await page.getByRole("option", { name: "WO-B", exact: true }).count() === 0, "Delayed Supplier lookup leaked into current picker")
		state.hold = new Promise(r => release = r); const departingWrite = page.waitForRequest(r => r.url().endsWith("create_closed_work_order_grn")); await action().click(); await departingWrite
		await page.evaluate(() => window.router.replace('/sewing/plans?supplier=UNIT-B&tab=closed-work-order-grn')); await picker().waitFor()
		const departingResponse = page.waitForResponse(r => r.url().endsWith("create_closed_work_order_grn")); release(); await departingResponse
		assert(await page.getByText(/GRN-SAVED-3/).count() === 0 && await picker().inputValue() === "", "Old Supplier receipt acknowledgement leaked into new Supplier")
		for (const permissions of [[false, true], [true, false]]) {
			[state.create, state.submit] = permissions; await page.reload(); await selectWo()
			assert(await action().isDisabled() && await qty().isDisabled(), `GRN creation needs both permissions: ${permissions}`)
		}
		await page.evaluate(() => window.router.replace('/sewing/plans?tab=closed-work-order-grn')); await page.getByText("Select a Sewing Unit to view Sewing Plan.", { exact: true }).waitFor()
		const withoutScope = requests.length; await page.waitForTimeout(350); assert(requests.length === withoutScope, "Missing Supplier issued Closed GRN requests")
		assert(errors.length === 0 && warnings.length === 0, `Closed GRN browser issues: ${[...errors, ...warnings].join("; ")}`)
		console.log("PASS closed-grn: scoped picker, grouped references-only payload, required posting/reference fields, both permissions, popup draft retention, double click lock, acknowledged ID/status and reload recovery, inactive rejection/success settlement, Supplier stale-details guard, four contained viewports")
	} catch (reason) { console.error("Closed GRN diagnostics:", JSON.stringify({ errors, warnings, body: (await page.locator("body").innerText()).slice(0, 2200) })); throw reason }
	finally { await page.close(); await server.close() }
}

// Catch missing active-report gating, wrong request contracts, locally invented
// balances, lost filters, hidden FI blockers, stale unit results and overflow.
async function primaryReportsSuite(browser) {
	const harness = `
import { createApp, h } from 'vue';
import { createRouter, createMemoryHistory, RouterView, useRoute } from 'vue-router';
import PrimeVue from 'primevue/config'; import Aura from '@primeuix/themes/aura';
import SewingReports from '/src/departments/sewing/SewingReports.vue';
import ReportShell from '/src/components/reports/ReportShell.vue';
import '@fontsource-variable/inter'; import 'primeicons/primeicons.css';
import '/src/styles/main.css'; import '/src/styles/enterprise.css';
const ShellLoadingFixture = { setup() { const route = useRoute(); return () => h(ReportShell, { title: 'Shared loading fixture', generated: true, loading: true, hasResults: true, ...(route.query.keep === 'yes' ? { keepResultsWhileLoading: true } : {}) }, () => h('p', 'Prior report rows')) } };
const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/sewing/reports', component: SewingReports }, { path: '/sewing', component: { render: () => null } }, { path: '/report-shell', component: ShellLoadingFixture }] });
await router.push('/sewing/reports?supplier=UNIT-A'); window.router = router;
createApp(RouterView).use(router).use(PrimeVue, { theme: { preset: Aura, options: { darkModeSelector: false } } }).mount('#app');`
	const server = await createServer({ root: fileURLToPath(new URL("../frontend", import.meta.url)), server: { host: "127.0.0.1", port: 0 }, plugins: [{
		name: "primary-reports-verifier", resolveId(id) { if (id === "/__reports.js") return "\0reports" }, load(id) { if (id === "\0reports") return harness },
		configureServer(server) { server.middlewares.use((req, res, next) => { if (req.url !== "/__reports") return next(); res.setHeader("Content-Type", "text/html"); res.end('<!doctype html><html><body><div id="app"></div><script type="module" src="/__reports.js"></script></body></html>') }) },
	}] })
	await server.listen()
	const page = await browser.newPage({ viewport: { width: 1280, height: 900 } })
	page.setDefaultTimeout(10_000)
	const requests = [], errors = [], warnings = []
	page.on("pageerror", e => errors.push(e.message))
	page.on("console", m => { if (m.type() === "warning") warnings.push(m.text()) })
	const headers = ["Order Qty", "Delivered Qty", "Sewing In", "Sewing Out", "Checking Reject", "Pre Final", "Final Inspection", "GRN Qty", "Line Stock", "Checking Stock", "GRN Pending"]
	const status = { header1: ["Item", "SD YRP Lot", "Colour", "Part", "FI Date", "Input Date", "Last Sewing Output", "Total Running Days"], header2: headers, header3: ["Ready for Checking", "Work Order Status"], data: [
		{ is_total: true, "Order Qty": 300, "Line Stock": -71 },
		{ item: "Shirt", lot: "LOT-A", colour: "Navy", part: "Front", input_date: "2026-10-01", "FI Date": "2026-09-30", "Input Date": "2026-10-01", "Last Sewing Output": "2026-10-05", "Total Running Days": 4, "Order Qty": 100, "Delivered Qty": 90, "Sewing In": 80, "Sewing Out": 60, "Checking Reject": 5, "Pre Final": 25, "Final Inspection": 20, "GRN Qty": 35, "Line Stock": -37, "Checking Stock": -15, "GRN Pending": 25, "Ready for Checking": "Under Checking", "Work Order Status": "Open" },
		{ item: "Trouser", lot: "LOT-B", colour: "Red", part: "Back", input_date: "2026-10-06", "Input Date": "2026-10-06", "Order Qty": 200, "Line Stock": -34, "Ready for Checking": "Ready", "Work Order Status": "Open" },
	] }
	const sizes = ["XS", "S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL", "6XL"]
	const daily = { date: "2026-10-08", status: "success", blocked: false, pending_fi: [], message: "", headers: ["Sewing Out", "Sewing In"], dpr_data: {
		"Sewing Out": { "LOT-A": { item: "Shirt", primary_values: sizes, is_set_item: 0, pack_attr: "Colour", set_attr: null, details: { "Sewing Line 1": { Good: { Navy: { colour: "Navy", part: "Front", variant_colour: "Navy", set_combination: {}, values: { XS: 3, S: 7 }, total: 10 } } } } } },
		"Sewing In": { "LOT-A": { item: "Shirt", primary_values: ["XS"], is_set_item: 0, pack_attr: "Colour", set_attr: null, details: { "Sewing Line 2": { Reject: { Red: { colour: "Red", part: "Back", variant_colour: "Red", set_combination: {}, values: { XS: 2 }, total: 2 } } } } } },
	} }
	const scr = { status: "success", item: "Shirt", primary_values: sizes, colours: ["Navy", "Red"], headers: ["Order Qty", "Delivered Qty", "Delivered - Input", "Sewing In", "Sewing In Balance", "Sewing Out", "Reject", "Sewing Out Total", "Sewing Out Balance"], balance_headers: ["Delivered - Input", "Sewing In Balance", "Sewing Out Balance"], is_set_item: 0, set_attr: null, data: {
		Navy: { colour: "Navy", part: "Front", variant_colour: "Navy", set_combination: {}, lines: ["Sewing Line 1", "Sewing Line 3"], values: { XS: { "Order Qty": 100, "Delivered Qty": 90, "Delivered - Input": 10, "Sewing In": 80, "Sewing In Balance": -20, "Sewing Out": 60, Reject: 5, "Sewing Out Total": 65, "Sewing Out Balance": -15 } }, type_wise_total: { "Order Qty": 100, "Delivered Qty": 90, "Delivered - Input": 10, "Sewing In": 80, "Sewing In Balance": -20, "Sewing Out": 60, Reject: 5, "Sewing Out Total": 65, "Sewing Out Balance": -15 } },
		Red: { colour: "Red", part: "Back", variant_colour: "Red", set_combination: {}, lines: [], values: { XS: { "Order Qty": 200 } }, type_wise_total: { "Order Qty": 200 } },
	} }
	const state = { error: "", blocked: false, hold: null }
	await page.route("**/api/method/**", async route => {
		const method = route.request().url().split("/api/method/")[1], args = JSON.parse(route.request().postData() || "{}")
		requests.push({ method, args })
		let value, error = ""
		if (method.endsWith("get_capabilities")) value = capabilities
		else if (method.endsWith("get_sp_status_summary")) { value = structuredClone(status); if (args.supplier === "UNIT-B") value.data = []; error = state.error; if (state.hold) { const hold = state.hold; state.hold = null; await hold } }
		else if (method.endsWith("get_sewing_plan_dpr_data") || method.endsWith("get_sewing_plan_dpr_summary")) {
			const report = state.blocked ? { ...daily, status: "pending_fi", blocked: true, message: "Set FI dates for the listed Lots, Colours and Parts to generate this report.", pending_fi: [{ lot: "LOT-BLOCKED", colour: "Olive", part: "Sleeve" }], dpr_data: {} } : daily
			value = method.endsWith("summary") ? { reports: [report, { ...daily, date: "2026-10-09" }], status: report.status, blocked: report.blocked, message: report.message, pending_fi: report.pending_fi } : report
		}
		else if (method.endsWith("get_supplier_lots")) value = [["LOT-A", "Shirt"]]
		else if (method.endsWith("get_scr_data")) value = scr
		else if (method.endsWith("link_search")) value = [{ name: args.doctype === "YRP Work Station" ? "Sewing Line 1" : "Sewing Out", label: args.doctype === "YRP Work Station" ? "Sewing Line 1" : "Sewing Out" }]
		else throw new Error(`Unexpected primary report request: ${method}`)
		await route.fulfill({ status: error ? 417 : 200, contentType: "application/json", body: JSON.stringify(error ? { _server_messages: JSON.stringify([JSON.stringify({ message: error })]), exc: "ValidationError" } : { message: value }) })
	})
	const count = suffix => requests.filter(r => r.method.endsWith(suffix)).length
	const last = suffix => requests.filter(r => r.method.endsWith(suffix)).at(-1)?.args
	const tab = name => page.getByRole("tab", { name, exact: true }).click()
	const generate = () => page.getByRole("button", { name: "Generate", exact: true }).click()
	const pick = async (name, option) => { await page.getByRole("combobox", { name, exact: true }).focus(); await page.keyboard.press("Space"); await page.getByRole("option", { name: option, exact: true }).click(); await page.keyboard.press("Escape"); await page.locator('.p-multiselect-overlay').waitFor({ state: 'hidden' }) }
	const date = async (label, value) => { await page.getByRole("dialog").waitFor({ state: "hidden" }); const input = page.getByRole("combobox", { name: label, exact: true }); await input.fill(value); await input.press("Tab"); assert(await input.inputValue() === value, `${label} date edit was discarded: ${await input.inputValue()} instead of ${value}`) }
	const responsive = async name => {
		await page.evaluate(async () => { await document.fonts.ready; await Promise.all(document.getAnimations().map(animation => animation.finished.catch(() => {}))) })
		for (const width of [390, 900, 1280, 1600]) {
			await page.setViewportSize({ width, height: width === 390 ? 500 : 900 })
			await noOverflow(page, `${name} ${width}`)
			await readableReportDates(page, `${name} ${width}`)
			const clipped = await page.locator(".report-shell__commands .p-button").evaluateAll(buttons => buttons.filter(button => { const label = button.querySelector('.p-button-label'); return label && (label.getBoundingClientRect().right > button.getBoundingClientRect().right + 1 || label.scrollWidth > label.clientWidth + 1) }).map(button => button.textContent))
			assert(!clipped.length, `${name} ${width} clips report actions: ${clipped.join(', ')}`)
			assert(await page.locator(`[data-sewing-report='${name}'] .sewing-report-matrix`).first().evaluate(el => getComputedStyle(el.querySelector('thead th')).position === 'sticky'), `${name} header is not sticky`)
			if (process.env.ESSDEE_SEWING_SCREENSHOTS) await page.screenshot({ path: `${process.env.ESSDEE_SEWING_SCREENSHOTS}/sewing-${name}-${width}.png`, fullPage: true, animations: "disabled" })
		}
		await page.setViewportSize({ width: 1280, height: 900 })
	}
	try {
		await page.goto(`http://127.0.0.1:${server.httpServer.address().port}/__reports`)
		await page.locator("[data-sewing-destination='reports']").waitFor()
		assert(await page.getByRole("tab").count() === 5, "Reports workspace is absent: expected five approved report tabs")
		assert(JSON.stringify(await page.getByRole("tab").allTextContents()) === JSON.stringify(["Status Summary", "DPR", "SCR", "Monthly Summary", "Item Summary"]), "Reports has incorrect or excluded tabs")
		await page.locator("[data-sewing-report='status-summary'] tbody tr").first().waitFor()
		assert(count("get_sp_status_summary") === 1 && count("get_scr_data") === 0 && count("get_sewing_plan_dpr_data") === 0, "Inactive report endpoint fetched")
		assert(last("get_sp_status_summary").supplier === "UNIT-A", "Status scope omitted")
		const statusRows = page.locator("[data-sewing-report='status-summary'] tbody tr")
		assert((await statusRows.first().innerText()).includes("-37"), "Status replaced server balance with a client calculation")
		await responsive("status-summary")
		for (const [label, option] of [["Lot", "LOT-A"], ["Item", "Shirt"], ["Colour", "Navy"], ["Part", "Front"]]) {
			await pick(label, option)
			assert(await statusRows.count() === 1 && (await statusRows.first().innerText()).includes("LOT-A"), `${label} filter not applied`)
			assert((await page.locator("[data-sewing-report='status-summary'] tfoot").innerText()).includes("-37"), `${label} visible totals not recomputed`)
			await page.getByRole("button", { name: "Reset", exact: true }).click()
		}
		await date("Input From Date", "01-10-2026"); await date("Input To Date", "03-10-2026")
		assert(await statusRows.count() === 1, "Status input-date bounds ignored")
		await pick("Lot", "LOT-A")
		await tab("DPR")
		assert(count("get_sewing_plan_dpr_data") === 0, "DPR fetched before Generate")
		await generate(); await page.getByRole("dialog").getByText("Choose a DPR Date.", { exact: true }).waitFor()
		assert(count("get_sewing_plan_dpr_data") === 0, "DPR sent an empty date")
		await page.getByRole("button", { name: "OK", exact: true }).click()
		await date("DPR Date", "08-10-2026")
		for (const [label, value] of [["Work Station", "Sewing Line 1"], ["Input Type", "Sewing Out"]]) { await page.getByRole("combobox", { name: label, exact: true }).fill(value); await page.getByRole("option", { name: value, exact: true }).click() }
		await generate()
		await page.locator("[data-sewing-report='dpr'] tbody tr").first().waitFor()
		assert(JSON.stringify(last("get_sewing_plan_dpr_data")) === JSON.stringify({ supplier: "UNIT-A", dpr_date: "2026-10-08", work_station: "Sewing Line 1", input_type: "Sewing Out" }), "Daily DPR must send one date and optional filters")
		assert((await page.locator("[data-sewing-report='dpr'] table").first().innerText()).includes("10"), "DPR server total missing")
		assert((await page.locator("[data-sewing-report='dpr'] h3").first().innerText()).startsWith("Sewing Out"), "DPR reordered server input stages")
		await responsive("dpr")
		await page.getByLabel("DPR Mode", { exact: true }).selectOption("range")
		await date("From Date", "09-10-2026"); await date("To Date", "08-10-2026")
		await generate(); await page.getByRole("dialog").getByText("From Date cannot be after To Date.", { exact: true }).waitFor()
		assert(count("get_sewing_plan_dpr_summary") === 0, "DPR sent a reversed range")
		await page.getByRole("button", { name: "OK", exact: true }).click()
		await date("From Date", "08-10-2026"); await date("To Date", "09-10-2026")
		await generate(); await page.getByRole("heading", { name: "2026-10-09", exact: true }).waitFor()
		assert(JSON.stringify(last("get_sewing_plan_dpr_summary")) === JSON.stringify({ supplier: "UNIT-A", from_date: "2026-10-08", to_date: "2026-10-09", work_station: "Sewing Line 1", input_type: "Sewing Out" }), `Range DPR arguments incorrect: ${JSON.stringify(last("get_sewing_plan_dpr_summary"))}`)
		state.blocked = true; await generate()
		await page.getByText("LOT-BLOCKED", { exact: true }).waitFor()
		assert((await page.locator("[data-sewing-report='dpr']").innerText()).includes("Olive") && (await page.locator("[data-sewing-report='dpr']").innerText()).includes("Sleeve"), "Pending FI blockers lack Colour/Part")
		assert(await page.locator("[data-sewing-report='dpr'] table").count() === 1, "Blocked range must expose blockers rather than partial production data")
		await tab("SCR"); await page.locator("[data-sewing-report='scr']").waitFor()
		await generate(); await page.getByRole("dialog").waitFor()
		assert(count("get_scr_data") === 0, "SCR fetched without required Lot")
		await page.getByRole("button", { name: "OK", exact: true }).click()
		await page.getByRole("combobox", { name: "Lot", exact: true }).fill("LOT-A"); await page.getByRole("option", { name: "LOT-A", exact: true }).click()
		assert(last("get_supplier_lots").filters.supplier === "UNIT-A", "SCR Lot search missing Supplier")
		await generate(); await page.getByRole("heading", { name: "Navy · Front", exact: true }).waitFor()
		assert(JSON.stringify(last("get_scr_data")) === JSON.stringify({ supplier: "UNIT-A", lot: "LOT-A" }), "SCR request unscoped")
		const matrix = page.locator("[data-sewing-report='scr'] table").first()
		assert(JSON.stringify(await matrix.locator("thead th").allTextContents()) === JSON.stringify(["Size", ...scr.headers]), "SCR reordered server stage headers")
		assert(JSON.stringify(await matrix.locator('tbody tr').first().locator('td').allTextContents()) === JSON.stringify(['XS', '100', '90', '10', '80', '-20', '60', '5', '65', '-15']), 'SCR dropped or recomputed signed stage values')
		assert((await matrix.locator('tfoot').innerText()).includes('-15'), 'SCR lost authoritative balance totals')
		assert((await page.locator("[data-sewing-report='scr']").innerText()).includes("Sewing Line 3"), "SCR work-station lines omitted")
		await pick("Colour", "Navy")
		assert(await page.getByRole("heading", { name: "Red · Back", exact: true }).count() === 0, "SCR Colour filter ignored")
		await responsive("scr")
		await page.setViewportSize({ width: 390, height: 500 })
		const scroll = await page.locator("[data-sewing-report='scr'] .sewing-report-matrix").first().evaluate(async el => {
			el.scrollTop = 100; el.scrollLeft = 150; await new Promise(requestAnimationFrame)
			return { width: el.clientWidth, scroll: el.scrollWidth, top: el.getBoundingClientRect().top, header: el.querySelector('thead th').getBoundingClientRect().top, y: el.scrollTop, x: el.scrollLeft }
		})
		assert(scroll.scroll > scroll.width && scroll.x > 0 && scroll.y > 0, "Narrow matrix does not own both scroll axes")
		assert(Math.abs(scroll.header - scroll.top) <= 2, "Header scrolled out of the narrow matrix")
		await page.setViewportSize({ width: 1280, height: 900 }); await tab("DPR")
		assert(await page.getByLabel("DPR Mode", { exact: true }).inputValue() === "range" && await page.getByRole("combobox", { name: "From Date", exact: true }).inputValue() === "08-10-2026", "DPR filters lost across tab switch")
		assert(await page.getByRole("combobox", { name: "Work Station", exact: true }).inputValue() === "Sewing Line 1" && await page.getByRole("combobox", { name: "Input Type", exact: true }).inputValue() === "Sewing Out", "DPR optional filters lost across tab switch")
		await tab("SCR")
		assert(await page.getByRole("combobox", { name: "Lot", exact: true }).inputValue() === "LOT-A", "SCR Lot lost across tab switch")
		await generate(); await page.getByRole("heading", { name: "Navy · Front", exact: true }).waitFor()
		assert(await page.getByRole("heading", { name: "Red · Back", exact: true }).count() === 0, "SCR colour lost across tab switch")
		const dprCount = count("get_sewing_plan_dpr_summary"); await tab("Status Summary")
		await statusRows.first().waitFor()
		assert(await statusRows.count() === 1, "Status date filters lost across tab switch")
		assert((await page.locator("[data-sewing-report='status-summary'] .p-multiselect").first().innerText()).includes("LOT-A"), "Status Lot lost across tab switch")
		assert(count("get_sewing_plan_dpr_summary") === dprCount, "Inactive DPR refetched")
		state.error = "Sewing report access has changed."; await generate(); await page.getByRole("dialog").getByText(state.error, { exact: true }).waitFor()
		await page.getByRole("button", { name: "OK", exact: true }).click()
		assert(await page.getByRole("combobox", { name: "Input From Date", exact: true }).inputValue() === "01-10-2026", "Report error discarded filters")
		state.error = ""
		let release; state.hold = new Promise(resolve => { release = resolve }); await generate()
		await page.getByRole("status").getByText("Refreshing report. Previously generated values remain visible.", { exact: true }).waitFor()
		assert(await statusRows.count() === 1, "Refreshing Status Summary blanks previously useful results")
		assert(await page.getByRole("button", { name: "Reset", exact: true }).isDisabled() && await page.getByRole("button", { name: "Copy Report", exact: true }).isDisabled(), "Refreshing report leaves conflicting actions enabled")
		await page.evaluate(() => window.router.replace({ query: { ...window.router.currentRoute.value.query, supplier: 'UNIT-B' } }))
		await page.getByText("No matching records", { exact: true }).waitFor(); release(); await page.waitForTimeout(150)
		assert(await statusRows.count() === 0, "Late Supplier A response overwrote Supplier B")
		await page.evaluate(() => window.router.replace('/report-shell'))
		await page.locator('.report-shell__loading').waitFor()
		assert(await page.getByText('Prior report rows', { exact: true }).count() === 0, "Shared ReportShell changed its default loading behavior")
		await page.evaluate(() => window.router.replace('/report-shell?keep=yes'))
		await page.getByText('Prior report rows', { exact: true }).waitFor()
		assert(await page.locator('.report-shell__loading').count() === 0, "Opt-in loading still hides prior rows behind skeletons")
		assert(errors.length === 0 && warnings.length === 0, `Report browser errors/warnings: ${[...errors, ...warnings].join('\n')}`)
		console.log("PASS primary-reports: five lazy tabs, Status identity/date filters and visible totals, authoritative balances, daily/range DPR contracts/validation and explicit FI blockers, Supplier-scoped SCR and colour filtering, all filter persistence, popup recovery, retained refresh results/action locks, stale Supplier rejection, 12 responsive matrix/action checks and actual narrow sticky-header scrolling")
	} finally { await page.close(); await server.close() }
}

// Catches skipped validation, changed server order/totals, lost filters, eager
// report fetches, unsafe array payloads and stale Supplier/options responses.
async function summaryReportsSuite(browser) {
	const harness = `
import { createApp } from 'vue'; import { createRouter, createMemoryHistory, RouterView } from 'vue-router';
import PrimeVue from 'primevue/config'; import Aura from '@primeuix/themes/aura';
import SewingReports from '/src/departments/sewing/SewingReports.vue';
import '@fontsource-variable/inter'; import 'primeicons/primeicons.css'; import '/src/styles/main.css'; import '/src/styles/enterprise.css';
const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/sewing/reports', component: SewingReports }, { path: '/sewing', component: { render: () => null } }] });
await router.push('/sewing/reports?supplier=UNIT-A&tab=monthly-summary'); window.router = router;
createApp(RouterView).use(router).use(PrimeVue, { theme: { preset: Aura, options: { darkModeSelector: false } } }).mount('#app');`
	const server = await createServer({ root: fileURLToPath(new URL("../frontend", import.meta.url)), server: { host: "127.0.0.1", port: 0 }, plugins: [{
		name: "summary-reports-verifier", resolveId(id) { if (id === "/__summary.js") return "\0summary" }, load(id) { if (id === "\0summary") return harness },
		configureServer(server) { server.middlewares.use((req, res, next) => { if (req.url !== "/__summary") return next(); res.setHeader("Content-Type", "text/html"); res.end('<!doctype html><html><body><div id="app"></div><script type="module" src="/__summary.js"></script></body></html>') }) },
	}] })
	await server.listen()
	const page = await browser.newPage({ viewport: { width: 1280, height: 900 } }); page.setDefaultTimeout(10_000)
	const requests = [], errors = [], warnings = []
	page.on("pageerror", error => errors.push(error.message)); page.on("console", message => { if (message.type() === "warning") warnings.push(message.text()) })
	const lot = 'LOT-A, "One"', item = 'Style & 1'
	const styles = ["Zebra (Back)", "Alpha", "Shirt", "Trouser", "Jacket", "Vest", "Dress", "Polo", "Tunic", "Coat"]
	const monthly = { styles, rows: [{ date: "2026-10-09", "Zebra (Back)": 3, Alpha: 5, total: 79 }, { date: "2026-10-08", "Zebra (Back)": 6, Alpha: 4, total: 91 }], grand_total: { "Zebra (Back)": 121, Alpha: 142, total: 903 } }
	const summary = { groups: [
		{ item, lot, headers: ["XL", "S", "M", "L", "2XL", "3XL", "4XL", "5XL"], has_part: 1, rows: [{ date: "2026-10-09", input_type: "Sewing Out", work_station: "Line 3", colour: "Navy", part: "Back", values: { XL: 2, S: 3 }, total: 89 }, { date: "2026-10-08", input_type: "Sewing In", work_station: "Line 1", colour: "Red", part: "Front", values: { XL: 9, S: 7 }, total: 97 }] },
		{ item: "Alpha", lot: "LOT-Z", headers: ["M"], has_part: 0, rows: [{ date: "2026-10-07", input_type: "Checking", work_station: "Line 2", colour: "Olive", part: "", values: { M: 11 }, total: 117 }] },
	] }
	const state = { error: "", optionsError: "", monthlyHold: null, itemHold: null, optionsHold: null, options: { lots: [lot, "LOT-REMOVE"], items: [item, "ITEM-REMOVE"] } }
	await page.route("**/api/method/**", async route => {
		const method = route.request().url().split("/api/method/")[1], args = JSON.parse(route.request().postData() || "{}"); requests.push({ method, args })
		let value, error = "", hold
		if (method.endsWith("get_capabilities")) value = capabilities
		else if (method.endsWith("get_monthly_summary_data")) { value = args.supplier === "UNIT-B" ? { styles: [], rows: [], grand_total: {} } : monthly; error = state.error; hold = state.monthlyHold; state.monthlyHold = null }
		else if (method.endsWith("get_item_summary_options")) { value = args.supplier === "UNIT-B" ? { lots: ["LOT-B"], items: ["ITEM-B"] } : structuredClone(state.options); error = state.optionsError; hold = state.optionsHold; state.optionsHold = null }
		else if (method.endsWith("get_item_summary_data")) { value = args.supplier === "UNIT-B" ? { groups: [] } : summary; error = state.error; hold = state.itemHold; state.itemHold = null }
		else if (method.endsWith("link_search")) value = [{ name: "Sewing Out", label: "Sewing Out" }]
		else throw new Error(`Unexpected summary report request: ${method}`)
		if (hold) await hold
		await route.fulfill({ status: error ? 417 : 200, contentType: "application/json", body: JSON.stringify(error ? { _server_messages: JSON.stringify([JSON.stringify({ message: error })]), exc: "ValidationError" } : { message: value }) })
	})
	const count = suffix => requests.filter(request => request.method.endsWith(suffix)).length
	const last = suffix => requests.filter(request => request.method.endsWith(suffix)).at(-1)?.args
	const generate = () => page.getByRole("button", { name: "Generate", exact: true }).click()
	const tab = name => page.getByRole("tab", { name, exact: true }).click()
	const unit = supplier => page.evaluate(supplier => window.router.replace({ query: { ...window.router.currentRoute.value.query, supplier } }), supplier)
	const dismiss = async text => { const dialog = page.getByRole("dialog").filter({ has: page.getByText(text, { exact: true }) }); await dialog.getByText(text, { exact: true }).waitFor(); assert(await dialog.count() === 1, "Summary error opened duplicate error popups"); await dialog.getByRole("button", { name: "OK", exact: true }).click(); await dialog.waitFor({ state: "hidden" }); await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))) }
	const date = async (label, value) => { const input = page.getByRole("combobox", { name: label, exact: true }); await input.fill(value); await input.press("Tab"); assert(await input.inputValue() === value, `${label} edit was lost`) }
	const open = async label => { const input = page.getByRole("combobox", { name: label, exact: true }); await page.waitForFunction(el => !el.disabled, await input.elementHandle()); await input.focus(); await page.keyboard.press("Space") }
	const close = async () => { await page.keyboard.press("Escape"); await page.locator('.p-multiselect-overlay').waitFor({ state: 'hidden' }) }
	const pick = async (label, option) => { await open(label); await page.getByRole("option", { name: option, exact: true }).click(); await close() }
	const responsive = async name => {
		await page.evaluate(async () => { await document.fonts.ready; await Promise.all(document.getAnimations().map(animation => animation.finished.catch(() => {}))) })
		for (const width of [390, 900, 1280, 1600]) {
			await page.setViewportSize({ width, height: width === 390 ? 500 : 900 }); await noOverflow(page, `${name} ${width}`)
			await readableReportDates(page, `${name} ${width}`)
			const clipped = await page.locator('.report-shell__commands .p-button').evaluateAll(buttons => buttons.filter(button => { const label = button.querySelector('.p-button-label'); return label && (label.scrollWidth > label.clientWidth + 1 || label.getBoundingClientRect().right > button.getBoundingClientRect().right + 1) }).map(button => button.textContent))
			assert(!clipped.length, `${name} ${width} clips actions: ${clipped}`)
			const matrix = page.locator('.sewing-report-matrix').first()
			assert(await matrix.evaluate(el => getComputedStyle(el.querySelector('thead th')).position === 'sticky'), `${name} headers are not sticky`)
			if (width === 390) assert(await matrix.evaluate(el => { el.scrollLeft = 100; return el.scrollLeft > 0 }), `${name} narrow matrix cannot scroll horizontally`)
			if (process.env.ESSDEE_SEWING_SCREENSHOTS) await page.screenshot({ path: `${process.env.ESSDEE_SEWING_SCREENSHOTS}/sewing-${name}-${width}.png`, fullPage: true, animations: "disabled" })
		}
		await page.setViewportSize({ width: 1280, height: 900 })
	}
	try {
		await page.goto(`http://127.0.0.1:${server.httpServer.address().port}/__summary`)
		await page.locator("[data-sewing-destination='reports']").waitFor()
		assert(await page.getByRole("tab").count() === 5, "Summary extension changed report tab count")
		await page.locator("[data-sewing-report='monthly-summary']").waitFor()
		assert(count("get_monthly_summary_data") === 0 && count("get_item_summary_options") === 0 && count("get_item_summary_data") === 0, "Summary reports fetched before activation/Generate")
		await generate(); await dismiss("Choose From Date and To Date."); assert(count("get_monthly_summary_data") === 0, "Missing dates sent a monthly request")
		await date("From Date", "09-10-2026"); await date("To Date", "08-10-2026"); await generate(); await dismiss("From Date cannot be after To Date."); assert(count("get_monthly_summary_data") === 0, "Reversed dates sent a monthly request")
		await date("From Date", "08-10-2026"); await date("To Date", "09-10-2026"); await generate(); await dismiss("Choose an Input Type or enable GRN mode."); assert(count("get_monthly_summary_data") === 0, "Non-GRN omitted required Input Type")
		await page.getByRole("combobox", { name: "Input Type", exact: true }).fill("Sewing"); await page.getByRole("option", { name: "Sewing Out", exact: true }).click(); await generate()
		await page.locator("[data-sewing-report='monthly-summary'] tbody tr").first().waitFor()
		assert(JSON.stringify(last("get_monthly_summary_data")) === JSON.stringify({ supplier: "UNIT-A", start_date: "2026-10-08", end_date: "2026-10-09", input_type: "Sewing Out", show_grn: 0 }), "Monthly request has wrong filters")
		assert(JSON.stringify(await page.locator('.sewing-report-matrix thead th').allTextContents()) === JSON.stringify(["Date", ...styles, "Total"]), "Monthly styles reordered")
		assert((await page.locator('.sewing-report-matrix tbody tr').first().innerText()).includes("2026-10-09") && (await page.locator('.sewing-report-matrix tbody tr').first().innerText()).endsWith("79"), "Monthly rows/totals reordered or derived")
		assert((await page.locator('.sewing-report-matrix tfoot').innerText()).includes("903"), "Monthly grand total derived instead of server value")
		await responsive("monthly-summary")
		await page.getByRole("button", { name: "Reset", exact: true }).click(); assert(await page.locator('.sewing-report-matrix').count() === 0 && await page.getByRole("combobox", { name: "From Date", exact: true }).inputValue() === "", "Monthly Reset retained results/filters")
		await date("From Date", "08-10-2026"); await date("To Date", "09-10-2026"); await page.getByRole("checkbox", { name: "GRN mode", exact: true }).check(); await generate(); await page.locator('.sewing-report-matrix').waitFor()
		assert(last("get_monthly_summary_data").show_grn === 1 && last("get_monthly_summary_data").input_type === "", "GRN mode required Input Type or sent wrong mode")
		state.error = "Monthly access changed."; await generate(); await dismiss(state.error); assert(await page.getByRole("checkbox", { name: "GRN mode", exact: true }).isChecked(), "Monthly error lost mode")
		assert(await page.getByRole("combobox", { name: "From Date", exact: true }).inputValue() === "08-10-2026" && await page.locator('.sewing-report-matrix').count() === 1, "Monthly error lost dates/results")
		state.error = ""; let releaseMonthly; state.monthlyHold = new Promise(resolve => { releaseMonthly = resolve }); await generate(); await page.getByText("Refreshing report. Previously generated values remain visible.", { exact: true }).waitFor()
		assert(await page.locator('.sewing-report-matrix tbody tr').count() === 2 && await page.getByRole("button", { name: "Reset", exact: true }).isDisabled() && await page.getByRole("button", { name: "Copy Report", exact: true }).isDisabled(), "Monthly refresh lost results/action locks")
		await tab("Item Summary"); releaseMonthly(); await page.locator("[data-sewing-report='item-summary']").waitFor(); await page.waitForFunction(() => !document.querySelector('[aria-label="Lot"]')?.disabled)
		await generate(); await dismiss("Select at least one Lot or Item."); assert(count("get_item_summary_data") === 0, "Item report fetched without selections")
		await pick("Lot", lot); await pick("Item", item); assert(count("get_item_summary_data") === 0, "Item selection generated a report without explicit Generate"); await generate(); await page.locator('.sewing-report-matrix').first().waitFor()
		assert(JSON.stringify(last("get_item_summary_data")) === JSON.stringify({ supplier: "UNIT-A", lots: [lot], items: [item] }), "Lot/Item intersection arrays not passed safely together")
		assert(JSON.stringify(await page.getByRole('heading', { level: 2 }).allTextContents()) === JSON.stringify([`${item} · ${lot}`, 'Alpha · LOT-Z']), "Item result groups reordered")
		assert(JSON.stringify(await page.locator('.sewing-report-matrix').first().locator('thead th').allTextContents()) === JSON.stringify(["Date", "Input Type", "Work Station", "Colour", "Part", "XL", "S", "M", "L", "2XL", "3XL", "4XL", "5XL", "Total"]), "Item dimensions/size order lost")
		assert((await page.locator('.sewing-report-matrix').first().locator('tbody tr').first().innerText()).endsWith("89") && (await page.locator('.sewing-report-matrix').nth(1).innerText()).includes("117"), "Item totals derived or groups omitted")
		assert(!((await page.locator('.sewing-report-matrix').nth(1).locator('thead').innerText()).includes("Part")), "Non-set Item displays a Part column")
		await responsive("item-summary")
		state.error = "Item access changed."; await generate(); await dismiss(state.error); assert((await page.locator('[data-sewing-report="item-summary"] .p-multiselect').first().innerText()).includes(lot), "Item error lost Lot filter")
		state.error = ""; const monthlyCount = count("get_monthly_summary_data"); await generate(); await page.locator('.report-shell[aria-busy="false"]').waitFor(); assert(count("get_monthly_summary_data") === monthlyCount, "Item retry fetched inactive Monthly"); assert(JSON.stringify(last("get_item_summary_data")) === JSON.stringify({ supplier: "UNIT-A", lots: [lot], items: [item] }), "Item retry discarded intersection filters")
		let releaseItem; state.itemHold = new Promise(resolve => { releaseItem = resolve }); await generate(); await page.getByText("Refreshing report. Previously generated values remain visible.", { exact: true }).waitFor(); assert(await page.locator('.sewing-report-matrix').count() === 2, "Item refresh blanks useful matrices"); await tab("Monthly Summary"); releaseItem()
		assert(await page.getByRole("checkbox", { name: "GRN mode", exact: true }).isChecked() && await page.getByRole("combobox", { name: "To Date", exact: true }).inputValue() === "09-10-2026", "Monthly filters lost across tab switch")
		state.options = { lots: ["LOT-NEW"], items: [item] }; await tab("Item Summary"); await open("Lot"); await page.getByRole("option", { name: "LOT-NEW", exact: true }).waitFor(); assert(await page.getByRole("option", { name: lot, exact: true }).count() === 0, "Invalid option remains"); await close()
		await generate(); await page.locator('.sewing-report-matrix').first().waitFor(); assert(JSON.stringify(last("get_item_summary_data").lots) === "[]" && JSON.stringify(last("get_item_summary_data").items) === JSON.stringify([item]), "Invalid Lot selection not cleared or valid Item lost")
		await page.getByRole("button", { name: "Reset", exact: true }).click(); await pick("Lot", "LOT-NEW"); await generate(); await page.locator('.sewing-report-matrix').first().waitFor(); assert(JSON.stringify(last("get_item_summary_data").items) === "[]", "Lot-only selection omitted or stale Item retained")
		await tab("Monthly Summary"); let releaseOptions; state.optionsHold = new Promise(resolve => { releaseOptions = resolve }); await tab("Item Summary"); const optionsCount = count("get_item_summary_options"); await page.waitForFunction(() => document.querySelector('[data-sewing-report="item-summary"]'))
		await unit("UNIT-B"); await open("Lot"); await page.getByRole("option", { name: "LOT-B", exact: true }).waitFor(); await close(); releaseOptions(); await page.waitForTimeout(150)
		await open("Lot"); assert(await page.getByRole("option", { name: "LOT-B", exact: true }).count() === 1 && await page.getByRole("option", { name: "LOT-NEW", exact: true }).count() === 0, "Late Supplier A options overwrote B"); await close()
		assert(count("get_item_summary_options") > optionsCount && last("get_item_summary_options").supplier === "UNIT-B", "Supplier change did not reload options")
		await generate(); await dismiss("Select at least one Lot or Item."); await pick("Lot", "LOT-B"); await generate(); await page.getByText("No matching records", { exact: true }).waitFor(); assert(last("get_item_summary_data").supplier === "UNIT-B", "Item report leaked Supplier scope")
		await unit("UNIT-A"); await pick("Lot", "LOT-NEW"); await generate(); await page.locator('.sewing-report-matrix').first().waitFor(); let releaseStaleItem; state.itemHold = new Promise(resolve => { releaseStaleItem = resolve }); await generate(); await page.getByText("Refreshing report. Previously generated values remain visible.", { exact: true }).waitFor(); await unit("UNIT-B"); await pick("Lot", "LOT-B"); await generate(); await page.getByText("No matching records", { exact: true }).waitFor(); releaseStaleItem(); await page.waitForTimeout(150); assert(await page.locator('.sewing-report-matrix').count() === 0, "Late Item data overwrote Supplier B")
		await tab("Monthly Summary"); await date("From Date", "08-10-2026"); await date("To Date", "09-10-2026"); await page.getByRole("checkbox", { name: "GRN mode", exact: true }).check(); await unit("UNIT-A"); await date("From Date", "08-10-2026"); await date("To Date", "09-10-2026"); await page.getByRole("checkbox", { name: "GRN mode", exact: true }).check(); let releaseStaleMonthly; state.monthlyHold = new Promise(resolve => { releaseStaleMonthly = resolve }); await generate(); await page.locator('.report-shell__loading').waitFor(); await unit("UNIT-B"); releaseStaleMonthly(); await page.waitForTimeout(150); assert(await page.locator('.sewing-report-matrix').count() === 0, "Late Monthly data overwrote Supplier B")
		state.optionsError = "Item options unavailable."; await tab("Item Summary"); await dismiss(state.optionsError); assert(await page.getByRole("button", { name: "Generate", exact: true }).isEnabled(), "Options failure left report locked"); state.optionsError = ""; await generate(); await open("Lot"); await page.getByRole("option", { name: "LOT-B", exact: true }).waitFor(); await close(); assert(count("get_monthly_summary_data") === monthlyCount + 1, "Options retry fetched inactive Monthly")
		assert(errors.length === 0 && warnings.length === 0, `Summary errors/warnings: ${[...errors, ...warnings].join('\n')}`)
		console.log("PASS summary-reports: lazy summaries, Monthly dates/Input Type/GRN validation, server order and grand total, Item options reload/pruning/stale protection, required/intersection/individual array filters, grouped matrices and authoritative totals, retained errors/results/filter state, active-only retries, Supplier data races, eight responsive/sticky/scroll checks")
	} finally { await page.close(); await server.close() }
}

// Mounts the real route and the reusable report in a separate workspace. Only the
// external Frappe HTTP boundary is mocked; all fields, tables and dialogs are real.
async function attendanceSuite(browser) {
	const harness = `
import { createApp } from 'vue'; import { createRouter, createMemoryHistory, RouterView } from 'vue-router';
import PrimeVue from 'primevue/config'; import Aura from '@primeuix/themes/aura';
import SewingAttendance from '/src/departments/sewing/SewingAttendance.vue';
import '@fontsource-variable/inter'; import 'primeicons/primeicons.css'; import '/src/styles/main.css'; import '/src/styles/enterprise.css';
const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/sewing/attendance', component: SewingAttendance }, { path: '/sewing', component: { render: () => null } }, { path: '/other-workspace', component: () => { const path = '/src/components/reports/AttendanceStrengthReport.vue'; return import(/* @vite-ignore */ path) } }] });
await router.push('/sewing/attendance'); window.router = router;
createApp(RouterView).use(router).use(PrimeVue, { theme: { preset: Aura, options: { darkModeSelector: false } } }).mount('#app');`
	const server = await createServer({ root: fileURLToPath(new URL("../frontend", import.meta.url)), server: { host: "127.0.0.1", port: 0 }, plugins: [{
		name: "attendance-verifier", resolveId(id) { if (id === "/__attendance.js") return "\0attendance" }, load(id) { if (id === "\0attendance") return harness },
		configureServer(server) { server.middlewares.use((req, res, next) => { if (req.url !== "/__attendance") return next(); res.setHeader("Content-Type", "text/html"); res.end('<!doctype html><html><body><div id="app"></div><script type="module" src="/__attendance.js"></script></body></html>') }) },
	}] })
	await server.listen()
	const page = await browser.newPage({ viewport: { width: 1280, height: 900 } }); page.setDefaultTimeout(10_000)
	const requests = [], errors = [], warnings = []
	page.on("pageerror", error => errors.push(error.message)); page.on("console", message => { if (message.type() === "warning") warnings.push(message.text()) })
	const columns = [{ fieldname: "department", label: "Department", fieldtype: "Data" }, { fieldname: "strength", label: "Strength", fieldtype: "Int" }, { fieldname: "notes", label: "Returned notes", fieldtype: "Data" }, ...Array.from({ length: 6 }, (_, index) => ({ fieldname: `stage_${index}`, label: `Returned stage ${index}`, fieldtype: "Int" })), { fieldname: "internal", label: "Hidden upstream column", hidden: 1 }]
	const data = { columns, rows: [{ department: '<img src=x onerror="window.attendanceUnsafe=true">', strength: 12, notes: '=HYPERLINK("unsafe")', internal: "hidden", stage_0: 3 }, ...Array.from({ length: 32 }, (_, index) => ({ department: `Group ${index}`, strength: 1 })), { department: "Total", strength: 901, notes: "Returned total" }], employee_punches: [{ employee: "EMP-001", employee_name: "Test Employee", department: "Sewing", designation: "Operator", manpower_agent: "Agent A", shift_type: "Shift B", first_punch: "08:05:00" }], shifts: ["Shift B", "Shift A"], add_total_row: 1 }
	const state = { data, error: "", hold: null }
	await page.route("**/api/method/**", async route => {
		const method = route.request().url().split("/api/method/")[1], args = JSON.parse(route.request().postData() || "{}"); requests.push({ method, args })
		if (method.endsWith("get_capabilities")) return route.fulfill({ contentType: "application/json", body: JSON.stringify({ message: capabilities }) })
		assert(method.endsWith("get_worker_strength_report"), `Unexpected attendance request: ${method}`)
		const value = structuredClone(state.data), error = state.error, hold = state.hold; state.hold = null
		if (hold) await hold
		await route.fulfill({ status: error ? 417 : 200, contentType: "application/json", body: JSON.stringify(error ? { _server_messages: JSON.stringify([JSON.stringify({ title: "HR connection timed out", message: error })]), exc: "ValidationError" } : { message: value }) })
	})
	const count = () => requests.filter(request => request.method.endsWith("get_worker_strength_report")).length
	const generate = () => page.getByRole("button", { name: "Generate", exact: true }).click()
	const date = page.getByRole("combobox", { name: "Date", exact: true })
	const setDate = async () => { await date.fill("08-10-2026"); await date.press("Tab") }
	const time = async label => {
		const input = page.getByRole("combobox", { name: label, exact: true }); await input.click()
		const panel = page.locator(`#${await input.getAttribute("aria-controls")}`)
		await panel.getByRole("button", { name: "Next Hour", exact: true }).click()
		await page.keyboard.press("Escape"); await panel.waitFor({ state: "hidden" })
		assert(/\d{2}:\d{2}:\d{2}/.test(await input.inputValue()), `${label} did not produce a time`)
	}
	const dismiss = async (message, title) => {
		const dialog = page.locator(".document-error-dialog"); await dialog.getByText(message, { exact: true }).waitFor()
		assert(await dialog.count() === 1 && await page.locator(".report-shell__message").count() === 0, "One attendance failure must produce one popup only")
		if (title) assert((await dialog.innerText()).includes(title), `Missing business error title ${title}`)
		await dialog.getByRole("button", { name: "OK", exact: true }).click(); await dialog.waitFor({ state: "hidden" })
		await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
		assert(await page.getByRole("button", { name: "Generate", exact: true }).isEnabled(), "Attendance failure locks the page")
	}
	try {
		await page.goto(`http://127.0.0.1:${server.httpServer.address().port}/__attendance`)
		await page.locator('[data-attendance-strength]').waitFor()
		assert(count() === 0, "Attendance fetched before Generate")
		assert(JSON.stringify((await page.locator('.report-filter-grid label').allTextContents()).map(label => label.trim())) === JSON.stringify(["Date", "From Time", "To Time"]), "Attendance exposes extra filters")
		for (const forbidden of ["Supplier", "Sewing Unit", "HR Department", "HR Location", "Designation", "Employee"]) assert(await page.getByRole("combobox", { name: forbidden, exact: true }).count() === 0, `Forbidden attendance selector: ${forbidden}`)
		await page.getByRole("button", { name: "Reset", exact: true }).click()
		await generate(); await dismiss("Choose a Date to generate the Strength Report.", "Date required"); assert(count() === 0, "Missing date requested HR")
		await setDate(); await generate(); await dismiss("Choose From Time to generate the Strength Report.", "From Time required"); assert(count() === 0, "Missing from time requested HR")
		await time("From Time"); await generate(); await dismiss("Choose To Time to generate the Strength Report.", "To Time required"); assert(count() === 0, "Missing to time requested HR")
		await time("To Time"); const from = await page.getByRole("combobox", { name: "From Time", exact: true }).inputValue(), to = await page.getByRole("combobox", { name: "To Time", exact: true }).inputValue()
		await generate(); await page.getByRole("region", { name: "Workers Strength Summary", exact: true }).waitFor()
		assert(JSON.stringify(requests.at(-1).args) === JSON.stringify({ report_date: "2026-10-08", from_time: from, to_time: to }), "Attendance must send only date/from/to, without Supplier or HR mapping")
		const summary = page.getByRole("region", { name: "Workers Strength Summary", exact: true })
		assert(JSON.stringify(await summary.locator("thead th").allTextContents()) === JSON.stringify(columns.filter(column => !column.hidden).map(column => column.label)), "Dynamic columns lost server order or hidden flag")
		assert((await summary.locator("tfoot").innerText()).includes("901"), "Attendance calculated its own total rather than using returned total")
		assert(await summary.locator("tbody tr").count() === 33, "Returned total duplicated among data rows")
		assert(await summary.locator("img").count() === 0 && !await page.evaluate(() => window.attendanceUnsafe), "Upstream HTML executed in a result cell")
		await page.getByText("Shifts: Shift B, Shift A", { exact: true }).waitFor(); await page.getByRole("region", { name: "Employee First Punch", exact: true }).getByText("08:05:00", { exact: true }).waitFor()
		assert(await page.getByRole("button", { name: "Copy Report", exact: true }).isEnabled(), "Attendance lacks shared report copy")
		for (const name of ["Export Strength", "Export Punches"]) {
			const pending = page.waitForEvent("download"); await page.getByRole("button", { name, exact: true }).click(); const download = await pending
			const csv = readFileSync(await download.path(), "utf8")
			assert(csv.includes(name === "Export Strength" ? "901" : "EMP-001"), `${name} does not export current returned rows`)
			if (name === "Export Strength") assert(csv.includes("'=HYPERLINK") && !csv.includes("Hidden upstream column"), "Strength export leaks hidden columns or unsafe spreadsheet formulas")
		}
		let release; state.hold = new Promise(resolve => { release = resolve }); await generate()
		await page.getByText("Refreshing report. Previously generated values remain visible.", { exact: true }).waitFor()
		assert(await summary.count() === 1 && await page.getByRole("button", { name: "Reset", exact: true }).isDisabled() && await page.getByRole("button", { name: "Export Strength", exact: true }).isDisabled(), "Refresh lost useful results or allows stale actions")
		release(); await page.locator('.report-shell[aria-busy="false"]').waitFor()
		state.error = "HR timed out. Please try again."; const beforeError = count(); await generate(); await dismiss(state.error, "Unable to generate Strength Report")
		assert(count() === beforeError + 1 && await summary.count() === 1 && await date.inputValue() === "08-10-2026" && await page.getByRole("combobox", { name: "From Time", exact: true }).inputValue() === from, "Endpoint failure duplicated request or discarded filters/results")
		state.error = ""; await generate(); await page.locator('.report-shell[aria-busy="false"]').waitFor()
		const beforeQuery = count(); await page.evaluate(() => window.router.replace('/sewing/attendance?supplier=IGNORED')); assert(count() === beforeQuery && await summary.count() === 1, "Global report is coupled to Supplier route state")
		for (const width of [390, 900, 1280, 1600]) {
			await page.setViewportSize({ width, height: 900 }); await noOverflow(page, `Attendance ${width}`)
			assert(await page.locator('.report-shell__commands .p-button').evaluateAll(buttons => buttons.every(button => { const label = button.querySelector('.p-button-label'); return label.getBoundingClientRect().right <= button.getBoundingClientRect().right - 4 })), `Attendance action label clipped at ${width}px`)
			if (width === 390) assert(await page.locator('.report-filter-grid input').evaluateAll(inputs => inputs.every(input => input.clientWidth >= 125)), "Narrow attendance date/time values are clipped")
			assert(await summary.locator("thead th").first().evaluate(el => getComputedStyle(el).position === "sticky"), "Attendance result headers are not sticky")
			if (width === 390) assert(await summary.evaluate(el => el.scrollWidth > el.clientWidth && getComputedStyle(el).overflowX === "auto"), "Attendance matrix lacks contained horizontal scrolling")
			assert(await page.getByRole("combobox", { name: "From Time", exact: true }).inputValue() === from, "Resizing loses time filter")
			if (process.env.ESSDEE_SEWING_SCREENSHOTS) await page.screenshot({ path: `${process.env.ESSDEE_SEWING_SCREENSHOTS}/sewing-attendance-${width}.png`, fullPage: true, animations: "disabled" })
		}
		state.data = { columns: [], rows: [], employee_punches: [], shifts: ["Shift A"], add_total_row: 0 }; await generate(); await page.getByText("No matching records", { exact: true }).waitFor()
		assert(await page.locator(".document-error-dialog").count() === 0, "Valid empty response is an error")
		state.data = { columns: [{ fieldname: "name", label: "Name" }, { fieldname: "count", label: "Count", fieldtype: "Int" }], rows: [["Array row", 7]], employee_punches: [], shifts: ["Shift A"], add_total_row: 0 }; await generate(); await summary.getByText("Array row", { exact: true }).waitFor(); assert(await summary.locator("tfoot").count() === 0, "False total flag invents a total")
		await page.getByRole("button", { name: "Reset", exact: true }).click(); await page.getByText("Set the report filters", { exact: true }).waitFor(); assert(await date.inputValue() === "" && await page.getByRole("combobox", { name: "To Time", exact: true }).inputValue() === "", "Reset retains stale filters")
		const beforeStandalone = requests.length; await page.evaluate(() => window.router.push('/other-workspace')); await page.locator('[data-attendance-strength]').waitFor(); assert(await page.locator('.sewing-workspace-shell').count() === 0 && requests.length === beforeStandalone, "Reusable report requires Sewing context or eager fetch")
		await setDate(); await time("From Time"); await time("To Time"); await generate(); await page.getByText("Array row", { exact: true }).waitFor()
		assert(errors.length === 0 && warnings.length === 0, `Attendance browser errors/warnings: ${[...errors, ...warnings].join('\n')}`)
		console.log("PASS attendance: global real route and reusable component, only date/time inputs, required-field popup/no-request guards, dynamic safe columns/array rows/server totals, punch/shift context, CSV exports/formula safety/copy, retained refresh/results/filter state, one-popup recovery, valid empty response, Supplier-query independence, four contained/sticky responsive viewports")
	} finally { await page.close(); await server.close() }
}

// A continuous journey through the built application catches wiring defects
// between cards/routes that isolated view harnesses cannot see. Individual suites
// above retain the populated matrices, mutation races and detailed contracts.
async function integratedSuite(browser) {
	const page = await browser.newPage({ viewport: { width: 1280, height: 900 } })
	page.setDefaultTimeout(15_000)
	await login(page)
	const requests = [], errors = []
	page.on("pageerror", error => errors.push(error.message))
	const state = { hrError: true }
	const responses = {
		get_dashboard_data: [{ input_type: "Sewing In", qty: 42 }],
		get_data_entry_data: { data: {}, input_types: [], diff: {}, allowances: {} },
		get_sewing_plan_entries: {},
		get_supplier_lots: [["LOT-INTEGRATION", "Shirt"]],
		get_consumption_mapping_data: { ipd: "IPD-INTEGRATION", sections: [], cloth_acc_data: [] },
		get_closed_sewing_work_orders: [["WO-INTEGRATION", "LOT-INTEGRATION", "Shirt", "Sewing"]],
		get_closed_work_order_grn_details: { work_order: "WO-INTEGRATION", supplier: "UNIT-A", lot: "LOT-INTEGRATION", item: "Shirt", process: "Sewing", has_pending_items: false, item_details: [] },
		get_sp_status_summary: { header1: [], header2: [], header3: [], data: [] },
		get_sewing_plan_dpr_data: { date: "2026-10-08", status: "success", blocked: false, pending_fi: [], headers: [], dpr_data: {} },
		get_scr_data: { colours: [], headers: [], data: {}, primary_values: [] },
		get_monthly_summary_data: { styles: [], rows: [], grand_total: {} },
		get_item_summary_options: { lots: ["LOT-INTEGRATION"], items: ["Shirt"] },
		get_item_summary_data: { groups: [] },
		get_worker_strength_report: { columns: [], rows: [], employee_punches: [], shifts: [], add_total_row: 0 },
	}
	await page.route("**/api/method/**", async route => {
		const method = new URL(route.request().url()).pathname.split("/api/method/")[1], key = method.split(".").at(-1), args = JSON.parse(route.request().postData() || "{}")
		if (key === "get_capabilities") return route.fulfill({ json: { message: capabilities } })
		if (key === "link_search") { const name = args.doctype === "Supplier" ? "UNIT-A" : "LOT-INTEGRATION"; return route.fulfill({ json: { message: [{ name, label: name }] } }) }
		if (key === "getdoctype") return route.fulfill({ json: { docs: [{ name: "YRP Goods Received Note", fields: [{ fieldname: "naming_series", fieldtype: "Select", label: "Naming Series", options: "GRN-TEST-", default: "GRN-TEST-", reqd: 1 }] }] } })
		if (!Object.hasOwn(responses, key)) {
			assert(!method.includes("sewing"), `Uncovered integrated Sewing request: ${method}`)
			return route.continue()
		}
		requests.push({ key, args })
		if (key !== "get_worker_strength_report") assert((args.supplier || args.filters?.supplier) === "UNIT-A", `Integrated request missing Supplier: ${key}`)
		if (key === "get_worker_strength_report" && state.hrError) return route.fulfill({ status: 417, json: { _server_messages: JSON.stringify([JSON.stringify({ title: "HR connection timed out", message: "HR is unavailable. Try again shortly." })]), exc: "ValidationError" } })
		return route.fulfill({ json: { message: responses[key] } })
	})
	const count = key => requests.filter(request => request.key === key).length
	const choose = async (label, option) => { await page.getByRole("combobox", { name: label, exact: true }).focus(); await page.keyboard.press("Space"); await page.getByRole("option", { name: option, exact: true }).click() }
	const tab = async (label, key, kind = "plan") => {
		await page.getByRole("tab", { name: label, exact: true }).click()
		await page.locator(`[data-sewing-${kind === "plan" ? "plan-tab" : "report"}='${key}']`).waitFor()
		assert(await page.locator(`[data-sewing-${kind === "plan" ? "plan-tab" : "report"}]`).count() === 1, `Integrated inactive ${kind} mounted`)
	}
	const setDate = async label => { const field = page.getByRole("combobox", { name: label, exact: true }); await field.fill("08-10-2026"); await field.press("Tab") }
	const generate = async key => {
		const before = count(key), response = page.waitForResponse(response => response.url().endsWith(key))
		await page.getByRole("button", { name: "Generate", exact: true }).click(); await response
		assert(count(key) === before + 1, `Integrated Generate failed/duplicated: ${key}`)
		await page.locator('.report-shell[aria-busy="false"]').waitFor()
		if (key !== 'get_worker_strength_report' || !state.hrError) await page.getByText('No matching records', { exact: true }).waitFor()
	}
	const forbidden = async () => {
		const labels = await page.locator(".sewing-workspace-shell [role='tab'], .sewing-workspace-shell label, .sewing-workspace-shell option").allTextContents()
		for (const text of ["FI Updates", "Input/Output", "Input Pending", "Output Pending", "HR Department", "HR Location", "Designation", "Employee"]) assert(!labels.some(label => label.trim() === text), `Excluded Sewing control: ${text}`)
	}
	try {
		await navigate(page, "/web/sewing")
		await page.locator(".workspace-launcher__card").nth(2).waitFor()
		await selectUnit(page, "UNIT-A")
		assert(requests.length === 0, "Launcher eagerly requested Sewing data")
		await page.getByRole("link", { name: /^Sewing Plan/ }).click()
		await page.locator("[data-sewing-dashboard-card]").filter({ hasText: "42" }).waitFor()
		assert(requests.length === 1 && count("get_dashboard_data") === 1, "Plan card fetched inactive views")
		await page.getByRole("button", { name: "Refresh dashboard", exact: true }).click()
		await page.waitForFunction(() => document.querySelector('[data-sewing-plan-tab="dashboard"][aria-busy="false"]'))
		assert(count("get_dashboard_data") === 2, "Dashboard refresh failed")
		await tab("Data Entry", "data-entry")
		await page.getByText("No Sewing Plans for this Sewing Unit.", { exact: true }).waitFor()
		await tab("Entries", "entries")
		await page.getByRole("combobox", { name: "Lot", exact: true }).fill("LOT-INTEGRATION")
		await page.getByRole("option", { name: "LOT-INTEGRATION", exact: true }).click()
		await tab("Consumption", "consumption")
		assert(count("get_consumption_mapping_data") === 0, "Consumption fetched before Lot selection")
		await page.getByRole("combobox", { name: "Lot", exact: true }).fill("LOT-INTEGRATION")
		await page.getByRole("option", { name: "LOT-INTEGRATION", exact: true }).click()
		await page.getByText("No consumption mappings for this Lot.", { exact: true }).waitFor()
		await tab("Entries", "entries")
		assert(await page.getByRole("combobox", { name: "Lot", exact: true }).inputValue() === "LOT-INTEGRATION", "Integrated tab switch loses entry filter")
		await tab("Closed Work Order GRN", "closed-work-order-grn")
		assert(count("get_closed_work_order_grn_details") === 0, "Receipt fetched before Work Order selection")
		await page.getByRole("combobox", { name: "Closed Work Order", exact: true }).fill("WO-INTEGRATION")
		await page.getByRole("option", { name: "WO-INTEGRATION", exact: true }).click()
		await page.getByText("No pending receivable quantities for this Work Order.", { exact: true }).waitFor()
		await forbidden()
		await page.getByRole("link", { name: "Back to Sewing", exact: true }).click()
		await page.getByRole("link", { name: /^Reports/ }).click()
		await page.locator('[data-sewing-report="status-summary"]').waitFor()
		await page.locator('.report-shell[aria-busy="false"]').waitFor()
		assert(count("get_sp_status_summary") === 1 && count("get_sewing_plan_dpr_data") === 0 && count("get_scr_data") === 0 && count("get_monthly_summary_data") === 0 && count("get_item_summary_options") === 0, "Reports card eagerly fetched inactive reports")
		await tab("DPR", "dpr", "report"); await setDate("DPR Date"); await generate("get_sewing_plan_dpr_data")
		await tab("SCR", "scr", "report")
		await page.getByRole("combobox", { name: "Lot", exact: true }).fill("LOT-INTEGRATION"); await page.getByRole("option", { name: "LOT-INTEGRATION", exact: true }).click(); await generate("get_scr_data")
		await tab("DPR", "dpr", "report")
		assert(await page.getByRole("combobox", { name: "DPR Date", exact: true }).inputValue() === "08-10-2026", "Integrated report switch loses date")
		await tab("Monthly Summary", "monthly-summary", "report"); await setDate("From Date"); await setDate("To Date"); await page.getByRole("checkbox", { name: "GRN mode", exact: true }).check(); await generate("get_monthly_summary_data")
		await tab("Item Summary", "item-summary", "report"); await choose("Lot", "LOT-INTEGRATION"); await page.keyboard.press("Escape"); await generate("get_item_summary_data")
		await forbidden()
		const direct = new URL(page.url()).pathname + new URL(page.url()).search
		await page.reload({ waitUntil: "domcontentloaded" }); await page.locator('[data-sewing-report="item-summary"]').waitFor()
		assert(new URL(page.url()).pathname + new URL(page.url()).search === direct && await page.getByRole("combobox", { name: "Sewing Unit", exact: true }).inputValue() === "UNIT-A", "Report reload loses unit/tab")
		await page.getByRole("link", { name: "Back to Sewing", exact: true }).click()
		await page.getByRole("link", { name: /^Attendance Report/ }).click(); await page.locator('[data-attendance-strength]').waitFor()
		assert(count("get_worker_strength_report") === 0 && await page.getByRole("combobox", { name: "Sewing Unit", exact: true }).count() === 0, "Attendance eagerly fetched or inherited Supplier")
		await setDate("Date")
		for (const label of ["From Time", "To Time"]) { const input = page.getByRole("combobox", { name: label, exact: true }); await input.click(); await page.locator(`#${await input.getAttribute("aria-controls")}`).getByRole("button", { name: "Next Hour", exact: true }).click(); await page.keyboard.press("Escape") }
		await generate("get_worker_strength_report"); await dialogGeometry(page, "hr-unavailable")
		await page.getByRole("button", { name: "OK", exact: true }).click()
		assert(await page.getByRole("combobox", { name: "Date", exact: true }).inputValue() === "08-10-2026", "HR error discarded filter")
		state.hrError = false; await generate("get_worker_strength_report"); await page.getByText("No matching records", { exact: true }).waitFor(); await forbidden()
		await page.goBack(); await page.locator(".workspace-launcher__card").nth(2).waitFor()
		await navigate(page, direct); await page.locator('[data-sewing-report="item-summary"]').waitFor()
		assert(await page.getByRole("combobox", { name: "Sewing Unit", exact: true }).inputValue() === "UNIT-A", "Direct reports URL loses Supplier")
		for (const key of Object.keys(responses)) assert(count(key) > 0, `Integrated journey omitted endpoint: ${key}`)
		assert(errors.length === 0, `Integrated browser errors: ${errors.join("; ")}`)
		console.log("PASS integrated: built-app Unit selection and all three cards, all ten scoped tabs and global Attendance, active-only requests, refresh/reload/back/direct routes, retained filters, HR popup recovery, excluded controls absent, four-width HR/GRN dialog geometry")
	} catch (reason) { console.error("Integrated diagnostics:", JSON.stringify({ url: page.url(), errors, requests: requests.map(request => request.key), body: (await page.locator("body").innerText()).slice(0, 1400) })); throw reason }
	finally { await page.close() }
}

// Optional read-only migrated-data inspection. It deliberately does not submit
// entries, receipts, consumption or an external HR report.
async function liveSuite(browser) {
	const supplier = process.env.ESSDEE_SEWING_LIVE_SUPPLIER
	assert(supplier, "live requires ESSDEE_SEWING_LIVE_SUPPLIER from the test site")
	const page = await browser.newPage({ viewport: { width: 1280, height: 900 } })
	page.setDefaultTimeout(20_000)
	const errors = [], reads = []
	page.on("pageerror", error => errors.push(error.message))
	page.on("response", response => { if (/get_dashboard_data|get_data_entry_data|get_sp_status_summary/.test(response.url())) reads.push({ method: response.url().split(".").at(-1), status: response.status() }) })
	try {
		await login(page)
		for (const [name, path, ready] of [
			["launcher", `/web/sewing?supplier=${encodeURIComponent(supplier)}`, ".workspace-launcher__card"],
			["dashboard", `/web/sewing/plans?supplier=${encodeURIComponent(supplier)}`, '[data-sewing-plan-tab="dashboard"][aria-busy="false"]'],
			["entry", `/web/sewing/plans?supplier=${encodeURIComponent(supplier)}&tab=data-entry`, '[data-sewing-plan-tab="data-entry"][aria-busy="false"]'],
			["status", `/web/sewing/reports?supplier=${encodeURIComponent(supplier)}`, '.report-shell[aria-busy="false"]'],
			["attendance", "/web/sewing/attendance", "[data-attendance-strength]"],
		]) {
			await navigate(page, path); await page.locator(ready).first().waitFor()
			for (const width of [1600, 1280, 900, 390]) {
				await page.setViewportSize({ width, height: 900 }); await noOverflow(page, `Migrated ${name} ${width}`)
				assert(!/Traceback \(most recent call last\)/.test(await page.locator(".sewing-workspace-shell").innerText()), `Raw error on migrated ${name}`)
				if (process.env.ESSDEE_SEWING_SCREENSHOTS) await page.screenshot({ path: `${process.env.ESSDEE_SEWING_SCREENSHOTS}/sewing-live-${name}-${width}.png`, fullPage: true, animations: "disabled" })
			}
			await page.setViewportSize({ width: 1280, height: 900 })
		}
		assert(reads.length >= 3 && reads.every(read => read.status === 200), `Migrated read failure: ${JSON.stringify(reads)}`)
		assert(errors.length === 0, `Migrated browser errors: ${errors.join("; ")}`)
		console.log(`PASS live: read-only migrated Supplier ${supplier}, launcher/dashboard/entry/status/attendance, 20 viewport checks; ${JSON.stringify(reads)}; no business mutation or HR call`)
	} catch (reason) { console.error("Live diagnostics:", JSON.stringify({ url: page.url(), errors, reads, body: (await page.locator("body").innerText()).slice(0, 1400) })); throw reason }
	finally { await page.close() }
}

assert(["launcher", "plan-entry", "entries-consumption", "entries-consumption-settlement", "closed-grn", "primary-reports", "summary-reports", "attendance", "integrated", "live", "all"].includes(suite), `Unknown Sewing suite: ${suite}`)
const browser = await chromium.launch({ headless: true })
try {
	if (suite === "launcher" || suite === "all") {
		const page = await browser.newPage()
		page.setDefaultTimeout(20_000)
		await login(page)
		const startupFailures = []
		page.on('requestfailed', request => startupFailures.push({ path: new URL(request.url()).pathname, failure: request.failure()?.errorText }))
		page.on('console', message => { if (message.type() === 'error') startupFailures.push({ console: message.text() }) })
		try { await launcherSuite(page) }
		catch (reason) { console.error('Launcher diagnostics:', JSON.stringify({ url: page.url(), failures: startupFailures.slice(-12), body: (await page.locator('body').innerText()).slice(0, 2000) })); throw reason }
		await contextSuite(browser)
	}
	if (suite === "plan-entry" || suite === "all") await planEntrySuite(browser)
	if (suite === "entries-consumption" || suite === "all") await entriesConsumptionSuite(browser)
	if (suite === "entries-consumption-settlement") await entriesConsumptionSuite(browser, process.argv[3] || "all")
	if (suite === "closed-grn" || suite === "all") await closedGrnSuite(browser)
	if (suite === "primary-reports" || suite === "all") await primaryReportsSuite(browser)
	if (suite === "summary-reports" || suite === "all") await summaryReportsSuite(browser)
	if (suite === "attendance" || suite === "all") await attendanceSuite(browser)
	if (suite === "integrated" || suite === "all") await integratedSuite(browser)
	if (suite === "live") await liveSuite(browser)
} finally { await browser.close() }
