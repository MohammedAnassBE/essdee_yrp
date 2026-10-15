#!/usr/bin/env node

import { mkdirSync, readFileSync } from "node:fs"
import { createRequire } from "node:module"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { fileURLToPath } from "node:url"
import { createServer } from "../frontend/node_modules/vite/dist/node/index.js"

const require = createRequire("/home/anas/.claude/playwright/package.json")
const { chromium } = require("playwright")
const SITE = process.env.ESSDEE_TEST_SITE || "http://erp-migration-test.site:8001"
const SHOT_DIR = process.env.FINISHING_SHOT_DIR || join(tmpdir(), "finishing-workspace-shots")
const WIDTHS = [1600, 1280, 900, 390]
const suite = process.argv[2] || "mocked"
const WORKSPACE = "essdee_yrp.finishing.web_workspace"
mkdirSync(SHOT_DIR, { recursive: true })

function assert(condition, message) { if (!condition) throw new Error(message) }

const SUPPLIER_WAREHOUSES = { "S-UNIT": ["WH-UNIT"], "S-TO": ["WH-TO-1", "WH-TO-2"], "S-EMPTY": [] }

function supplierWarehouseReply(method, args) {
	if (method === "essdee_yrp.finishing.dispatch_locations.get_supplier_warehouses") return SUPPLIER_WAREHOUSES[args.supplier] || []
	if (method !== "essdee_yrp.api.link_search.link_search") return undefined
	const names = args.doctype === "Supplier" ? Object.keys(SUPPLIER_WAREHOUSES) : args.filters?.disabled === 0 ? SUPPLIER_WAREHOUSES[args.filters.supplier] || [] : []
	return names.filter((name) => name.includes(args.txt || "")).map((name) => ({ name, label: name }))
}

async function chooseLink(root, label, value) {
	await root.getByRole("combobox", { name: label, exact: true }).fill(value)
	await root.page().locator(".p-autocomplete-overlay:visible .p-autocomplete-option").filter({ hasText: value }).first().click()
	await settle(root.page())
}

async function linkValue(root, label) {
	return root.getByRole("combobox", { name: label, exact: true }).inputValue()
}

async function settle(page) {
	await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))))
}

async function noOverflow(page, label) {
	const geometry = await page.evaluate(() => ({ viewport: innerWidth, page: document.documentElement.scrollWidth }))
	assert(geometry.page <= geometry.viewport + 1, `${label} page overflow: ${JSON.stringify(geometry)}`)
}

async function atEveryWidth(page, label, shotName = "") {
	for (const width of WIDTHS) {
		await page.setViewportSize({ width, height: 900 })
		await settle(page)
		await noOverflow(page, `${label} ${width}`)
		if (shotName) await page.screenshot({ path: join(SHOT_DIR, `${shotName}-${width}.png`), fullPage: true })
	}
	await page.setViewportSize({ width: 1280, height: 900 })
}

const sizes = ["S", "M"]
const detailValues = (cutting, delivered, received) => ({ cutting, delivered, received, cut_sew_diff: delivered - cutting, difference: received - delivered })
const tabPayloads = {
	details: {
		primary_values: sizes, process: "Stitching", is_set_item: 0, set_attr: null,
		data: {
			data: { Red: { part: null, values: { S: detailValues(10, 8, 9), M: detailValues(5, 5, 6) }, colour_total: { cutting: 15, delivered: 13, received: 15, cut_sew_diff: -2, difference: 2 } } },
			total: { item: { S: detailValues(10, 8, 9), M: detailValues(5, 5, 6) } },
			over_all: { item: { cutting: 15, delivered: 13, received: 15, cut_sew_diff: -2, difference: 2 } },
		},
	},
	inward: { primary_values: sizes, is_set_item: 0, data: { data: { Red: { values: { S: { accepted: 8, reworked: 1, rejected: 0, pending: 0 }, M: { accepted: 5, reworked: 0, rejected: 1, pending: -1 } }, colour_total: { accepted: 13, reworked: 1, rejected: 1, pending: -1 } } } } },
	rejection: { primary_values: sizes, is_set_item: 0, data: { "Oil Mark": { Red: { part: null, rework: { values: { S: 2 }, total: 2 }, rejection: { values: { M: 1 }, total: 1 } } } } },
}
const workspace = (status = "Dispatched") => ({
	record: { name: "FP-TEST-0001", lot: "LOT-1", item: "Thermal Kids Set", work_order: "WO-1", fp_status: status, modified: "2026-10-09 10:00:00", pieces_per_box: 5 },
	locked: false,
	actions: { request_audit: status === "Dispatched", fetch_rejected_quantity: true, cancel_linked_document: true, print_inward: true, view_p_and_l: false, manage_p_and_l: false, complete_audit: false, complete_ocr: false, fetch_old_lot: true },
	permissions: { can_read: true, can_write: true, can_print: true },
	print_formats: [{ label: "Standard Print", format: "Standard" }],
	primary_values: sizes,
	linked_documents: [{ key: "dc_list", label: "Delivery Challans", doctype: "YRP Delivery Challan", cancellable: true, documents: [{ name: "DC-1", date: "01-10-2026 10:00:00" }] }],
	dispatch_logs: [],
})
const capabilities = {
	sections: {
		plans: { label: "Finishing Plan", doctype: "SD YRP Finishing Plan", can_read: true, can_create: true, can_write: true },
		reports: { label: "Reports", can_read: true, can_create: false, reports: Object.fromEntries(["stock_balance", "packing_dpr", "dispatch_report", "ironing_dpr", "finishing_plan_report", "rejection_details", "rework_completion"].map((key) => [key, { can_read: true }])) },
		rework_details: { label: "Rework Details", can_read: true, can_write: true },
		rework_groups: { label: "Rework Grouped Details", can_read: true, can_write: true },
		dispatches: { label: "Finishing Plan Dispatch", doctype: "SD YRP Finishing Plan Dispatch", can_read: true, can_create: true, can_write: true, can_submit: true, can_cancel: true },
	},
}
const LAUNCHER_CARDS = ["Finishing Plan", "Reports", "Rework Details", "Rework Grouped Details", "Finishing Plan Dispatch"]
const REPORT_TABS = ["Stock Balance", "Packing DPR", "Dispatch Report", "Ironing DPR", "Finishing Plan Report", "Rejection Details", "Rework Completion"]

const harness = `
import { createApp, h } from 'vue';
import { createRouter, createMemoryHistory, RouterView } from 'vue-router';
import PrimeVue from 'primevue/config';
import ConfirmationService from 'primevue/confirmationservice';
import ToastService from 'primevue/toastservice';
import ConfirmDialog from 'primevue/confirmdialog';
import Toast from 'primevue/toast';
import Aura from '@primeuix/themes/aura';
import '@fontsource-variable/inter'; import 'primeicons/primeicons.css';
import '/src/styles/main.css'; import '/src/styles/enterprise.css';
const routes = [
	{ path: '/finishing', component: () => import('/src/departments/Finishing.vue') },
	{ path: '/finishing/plans/:finishingPlanId', name: 'finishing-plan', component: () => import('/src/departments/finishing/FinishingPlan.vue') },
	{ path: '/finishing/reports', component: () => import('/src/departments/finishing/FinishingReports.vue') },
	{ path: '/finishing/plans', component: { render: () => h('p', 'Finishing Plans list') } },
	{ path: '/finishing/rework-details', component: () => import('/src/departments/finishing/FinishingReworkDetails.vue') },
	{ path: '/finishing/rework-groups', component: () => import('/src/departments/finishing/FinishingReworkGroups.vue') },
	{ path: '/finishing/dispatches/new', name: 'finishing-dispatch-new', component: () => import('/src/departments/finishing/FinishingDispatch.vue') },
	{ path: '/finishing/dispatches/:dispatchId', name: 'finishing-dispatch', component: () => import('/src/departments/finishing/FinishingDispatch.vue') },
	{ path: '/:pathMatch(.*)*', component: { render: () => null } },
];
const router = createRouter({ history: createMemoryHistory(), routes }); window.router = router;
await router.push(new URLSearchParams(location.search).get('path') || '/finishing');
createApp({ render: () => [h(RouterView), h(Toast), h(ConfirmDialog)] }).use(router).use(PrimeVue, { theme: { preset: Aura, options: { darkModeSelector: false } } }).use(ToastService).use(ConfirmationService).mount('#app');`

async function startHarness() {
	const server = await createServer({ root: fileURLToPath(new URL("../frontend", import.meta.url)), logLevel: "error", server: { host: "127.0.0.1", port: 0 }, plugins: [{
		name: "finishing-verifier",
		resolveId(id) { if (id === "/__finishing.js") return "\0finishing" },
		load(id) { if (id === "\0finishing") return harness },
		configureServer(viteServer) { viteServer.middlewares.use((request, response, next) => { if (!request.url.startsWith("/__finishing?")) return next(); response.setHeader("Content-Type", "text/html"); response.end('<!doctype html><html><body><div id="app"></div><script type="module" src="/__finishing.js"></script></body></html>') }) },
	}] })
	await server.listen()
	return server
}

async function mockedSuite(browser) {
	const server = await startHarness()
	const page = await browser.newPage({ viewport: { width: 1280, height: 900 } })
	page.setDefaultTimeout(10_000)
	const requests = [], errors = []
	const state = { status: "Dispatched" }
	page.on("pageerror", (error) => errors.push(error.message))
	await page.route("**/api/method/**", async (route) => {
		const method = route.request().url().split("/api/method/")[1].split("?")[0]
		const args = JSON.parse(route.request().postData() || "{}")
		requests.push({ method, args })
		const reply = (message) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ message }) })
		if (method === `${WORKSPACE}.get_capabilities`) return reply(capabilities)
		if (method === `${WORKSPACE}.get_plan_workspace`) return reply(workspace(state.status))
		if (method === `${WORKSPACE}.get_plan_tab`) return reply(tabPayloads[args.tab] || {})
		if (method === `${WORKSPACE}.execute_plan_command`) { state.status = "Ready for Audit"; return reply(workspace(state.status)) }
		return reply({})
	})
	const base = `http://127.0.0.1:${server.httpServer.address().port}/__finishing?path=`
	const tabRequests = () => requests.filter((request) => request.method.endsWith("get_plan_tab")).map((request) => request.args.tab)
	try {
		await page.goto(`${base}/finishing`)
		const cards = page.locator(".workspace-launcher__card")
		await cards.first().waitFor()
		assert(await cards.count() === LAUNCHER_CARDS.length, "Finishing launcher must show exactly five cards")
		assert((await cards.allInnerTexts()).every((text, index) => text.includes(LAUNCHER_CARDS[index])), `Launcher cards must be ${LAUNCHER_CARDS.join(", ")}`)
		await atEveryWidth(page, "launcher")
		console.log("PASS launcher: the five Finishing cards in order, no horizontal overflow")

		await page.goto(`${base}/finishing/plans/FP-TEST-0001`)
		await page.locator('[data-finishing-tab="details"] .finishing-table').waitFor()
		assert(JSON.stringify(tabRequests()) === '["details"]', `Only the active tab may fetch, got ${tabRequests()}`)
		const difference = page.locator('[data-finishing-tab="details"] tbody').first().locator("tr").nth(2)
		assert(await difference.locator("td.finishing-tone--negative").count() === 2, "Negative difference cells must be red")
		assert(await difference.locator("td.finishing-tone--zero").count() === 1, "Zero difference cells must be yellow")
		assert((await page.locator(".finishing-table__total-group").first().innerText()).includes("15"), "Totals block must show the plan total")
		await atEveryWidth(page, "plan details")
		const facts = await page.locator(".finishing-plan__meta").innerText()
		assert(/PCS \/ BOX\s*5/i.test(facts), `Header must show Pcs / Box: ${facts}`)

		await page.getByRole("tab", { name: "Inward", exact: true }).click()
		await page.locator('[data-finishing-tab="inward"] .finishing-table').waitFor()
		assert(await page.evaluate(() => window.router.currentRoute.value.query.tab) === "inward", "Active tab must persist in ?tab=")
		assert(await page.locator("td.finishing-tone--zero-inward").count() === 1 && await page.locator("td.finishing-tone--negative").count() === 2, "Inward pending uses teal for zero and red for negative")
		await page.getByRole("tab", { name: "Rejection", exact: true }).click()
		await page.getByText("Total Rejection").waitFor()
		assert(JSON.stringify(tabRequests()) === '["details","inward","rejection"]', `Tabs must fetch once on activation, got ${tabRequests()}`)
		await page.getByRole("tab", { name: "Details", exact: true }).click()
		await page.locator('[data-finishing-tab="details"] .finishing-table').waitFor()
		assert(tabRequests().length === 3, "Revisiting a loaded tab must not refetch")
		console.log("PASS plan tabs: active-only fetch, ?tab= persistence, F15 colour rules and totals")

		await page.getByRole("button", { name: "More Actions" }).click()
		await page.getByRole("menuitem", { name: "Audit Request" }).click()
		await page.locator(".p-confirmdialog").getByRole("button", { name: "Audit Request" }).click()
		await page.getByText("Status set to Ready for Audit.").waitFor()
		const command = requests.find((request) => request.method.endsWith("execute_plan_command"))
		assert(command?.args.command === "request_audit" && command.args.expected_modified === "2026-10-09 10:00:00", "Audit Request must send the command with expected_modified")
		assert((await page.locator(".finishing-plan__meta").innerText()).toUpperCase().includes("READY FOR AUDIT"), "Header status must refresh after a command")
		await page.getByRole("tab", { name: "Item Details", exact: true }).click()
		await page.getByRole("button", { name: "DC-1", exact: true }).click()
		const viewer = page.locator(".related-document-workspace-dialog")
		await viewer.waitFor()
		assert((await viewer.locator(".p-dialog-title").innerText()).includes("Delivery Challan · DC-1"), "DC must open in the shared Work Order DC/GRN viewer")
		assert(await page.locator(".document-transaction-dialog").count() === 0, "DC must not open in the generic transaction dialog")
		assert(requests.some((request) => request.method.includes("fabric_store.web_workspace.get_delivery_challan_workspace") && request.args.name === "DC-1"), "Shared viewer must load the Fabric Store DC workspace")
		await page.keyboard.press("Escape")
		await page.locator(".related-document-workspace-dialog").getByRole("button", { name: /Close|Back/ }).first().click().catch(() => {})
		await viewer.waitFor({ state: "hidden" }).catch(() => {})
		await page.getByRole("button", { name: "Cancel DC-1" }).click()
		assert(await page.locator(".p-confirmdialog").getByRole("button", { name: "Keep Document" }).isVisible(), "Destructive cancel must require confirmation")
		await page.locator(".p-confirmdialog").getByRole("button", { name: "Keep Document" }).click()
		console.log("PASS actions: confirmed audit request, header refresh, DC opens in shared Work Order viewer, destructive cancel confirmation")

		await page.goto(`${base}/finishing/reports`)
		await page.getByRole("heading", { name: "Stock Balance" }).waitFor()
		assert(JSON.stringify((await page.getByRole("tab").allInnerTexts()).map((text) => text.trim())) === JSON.stringify(REPORT_TABS), "Reports must list the seven Finishing reports in Frappe 15 order")
		assert(await page.getByRole("button", { name: "Generate" }).count() === 1, "Only the active report may be mounted")
		await atEveryWidth(page, "reports")
		assert(errors.length === 0, `Page errors: ${errors.join("\n")}`)
		console.log("PASS reports: seven report tabs, active-only mount, no horizontal overflow")
	} finally {
		await page.close()
		await server.close()
	}
}

async function liveSuite(browser) {
	const [username, password] = readFileSync("/home/anas/.frappe-debug-creds-mrp3", "utf8").trim().split("\n")
	const page = await browser.newPage({ viewport: { width: 1280, height: 900 } })
	page.setDefaultTimeout(30_000)
	const errors = []
	page.on("pageerror", (error) => errors.push(error.message))
	try {
		await page.goto(`${SITE}/login`, { waitUntil: "domcontentloaded" })
		await page.fill("#login_email", username.trim())
		await page.fill("#login_password", password.trim())
		await Promise.all([page.waitForNavigation({ waitUntil: "domcontentloaded" }).catch(() => {}), page.click(".btn-login, button[type=submit]")])
		await page.goto(`${SITE}/web/finishing`, { waitUntil: "networkidle" })
		assert(await page.locator(".workspace-launcher__card").count() === LAUNCHER_CARDS.length, "Live launcher must show the five Finishing cards")
		await atEveryWidth(page, "live launcher", "launcher")
		await page.locator(".workspace-launcher__card").first().click()
		await page.waitForURL(/\/web\/finishing\/plans$/)
		await page.locator(".finishing-list tbody tr").first().waitFor()
		await atEveryWidth(page, "live list", "list")
		await page.locator("tbody tr").first().click()
		await page.waitForURL(/\/web\/finishing\/plans\/.+/)
		await page.locator('[data-finishing-tab="details"]').waitFor()
		for (const tab of await page.getByRole("tab").allInnerTexts()) {
			await page.getByRole("tab", { name: tab, exact: true }).click()
			await page.waitForLoadState("networkidle")
			await page.locator(".finishing-tabs .p-skeleton").first().waitFor({ state: "detached" }).catch(() => {})
			assert(await page.locator(".workspace-load-error").count() === 0, `Live tab ${tab} failed to load`)
			await atEveryWidth(page, `live tab ${tab}`, `plan-${tab.toLowerCase().replace(/\W+/g, "-")}`)
		}
		assert(errors.length === 0, `Live page errors: ${errors.join("\n")}`)
		console.log(`PASS live: launcher, list and every plan tab render without overflow; screenshots in ${SHOT_DIR}`)
	} finally {
		await page.close()
	}
}


const quantityRows = (fields) => ({ data: { Red: { colour: "Red", part: null, check_value: true, values: Object.fromEntries(sizes.map((size, index) => [size, Object.fromEntries(fields.map(([field, base]) => [field, base + index]))])), colour_total: {} } }, total: {} })
const entryTabs = {
	item_details: { primary_values: sizes, is_set_item: 0, data: quantityRows([["accepted", 10], ["dc_qty", 6], ["balance", 4], ["return_qty", 1], ["pack_return", 0]]), rework_details: { data: {} } },
	grn: { primary_values: sizes, packed: { sizes: { S: { packed: 5, dispatched: 1 }, M: { packed: 3, dispatched: 0 } }, total_packed: 8, total_dispatched: 1 }, packing_config: { packing_combo: 5, colours: ["Red"] } },
	ironing_excess: { primary_values: sizes, is_set_item: 0, data: quantityRows([["ironing", 0], ["ironing_dc", 0]]) },
	pack_return: { primary_values: sizes, is_set_item: 0, data: quantityRows([["pack_returned_qty", 0], ["pack_return", 0]]) },
	old_lot: { given: { groups: [] }, received: { groups: [] }, available: { colours: ["Red"], data: [{ source_fp: "FP-OLD", lot: "LOT-OLD", warehouse: "WH-1", warehouse_name: "Unit", primary_values: sizes, is_set_item: 0, old_lot_inward: { data: { Red: { part: null, set_combination: null, values: { S: { balance_loose_piece: 3, balance_loose_piece_set: 0 }, M: { balance_loose_piece: 0, balance_loose_piece_set: 0 } }, colour_total: { balance_loose_piece: 3, balance_loose_piece_set: 0 } } } } }] } },
}
const entryResults = {
	create_delivery_challan: { doctype: "YRP Delivery Challan", name: "DC-NEW" },
	create_grn: { doctype: "YRP Goods Received Note", name: "GRN-NEW" },
	add_ironing_excess: { doctype: "YRP Stock Entry", name: "STE-NEW" },
	lot_transfer: { doctype: "SD YRP Lot Transfer", name: "LT-NEW" },
	update_alternative_quantity: { doctype: "YRP Work Order", name: "WO-ALT" },
	dispatch_box: { doctype: "YRP Stock Entry", name: "STE-DISPATCH" },
}

async function entriesSuite(browser) {
	const server = await startHarness()
	const page = await browser.newPage({ viewport: { width: 1280, height: 900 } })
	page.setDefaultTimeout(10_000)
	const commands = [], errors = []
	const state = { failNext: "" }
	page.on("pageerror", (error) => errors.push(error.message))
	const entryWorkspace = () => ({ ...workspace("Dispatched"), actions: { ...workspace("Dispatched").actions, create_entries: true, fetch_old_lot: true }, entry_options: { delivery_location: "S-UNIT", alternative_items: ["ALT"], alternate_lots: ["LOT-2"] } })
	await page.route("**/api/method/**", async (route) => {
		const method = route.request().url().split("/api/method/")[1].split("?")[0]
		const args = JSON.parse(route.request().postData() || "{}")
		const reply = (message) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ message }) })
		if (method === `${WORKSPACE}.get_capabilities`) return reply(capabilities)
		if (method === `${WORKSPACE}.get_plan_workspace`) return reply(entryWorkspace())
		if (method === `${WORKSPACE}.get_plan_tab`) return reply(entryTabs[args.tab] || tabPayloads[args.tab] || {})
		const locationReply = supplierWarehouseReply(method, args)
		if (locationReply) return reply(locationReply)
		if (method === `${WORKSPACE}.execute_plan_command`) {
			commands.push(args)
			if (state.failNext === args.command) {
				state.failNext = ""
				return route.fulfill({ status: 417, contentType: "application/json", body: JSON.stringify({ exc_type: "ValidationError", _server_messages: JSON.stringify([JSON.stringify({ message: "Work Order WO-1 must be submitted and open" })]) }) })
			}
			return reply({ ...entryWorkspace(), result: entryResults[args.command] || null })
		}
		return reply({})
	})
	const base = `http://127.0.0.1:${server.httpServer.address().port}/__finishing?path=`
	const dialog = page.locator(".finishing-entry-dialog")
	const lastCommand = () => commands.at(-1)
	const closeOverlays = async () => {
		const viewer = page.locator(".related-document-workspace-dialog")
		if (await viewer.count()) await viewer.getByRole("button", { name: "Close workspace" }).click()
		else await page.locator(".document-transaction-dialog .p-dialog-footer").getByRole("button", { name: "Close" }).click()
		await page.locator(".p-dialog-mask").first().waitFor({ state: "detached" }).catch(() => {})
		await settle(page)
	}
	try {
		await page.goto(`${base}/finishing/plans/FP-TEST-0001?tab=item-details`)
		const toolbar = page.getByRole("group", { name: "Item Details actions" })
		await toolbar.waitFor()
		assert(JSON.stringify(await toolbar.getByRole("button").allInnerTexts()) === '["Create DC","Return Item","Convert to Loose Piece"]', "Item Details must offer Create DC, Return Item and Convert to Loose Piece")
		await toolbar.getByRole("button", { name: "Create DC" }).click()
		await dialog.getByRole("button", { name: "Fill" }).click()
		assert(await dialog.getByLabel("Red S DC Qty").inputValue() === "4", "Fill must copy the Balance quantity")
		await dialog.getByRole("button", { name: "Create DC" }).click()
		await page.locator(".related-document-workspace-dialog .p-dialog-title", { hasText: "Delivery Challan · DC-NEW" }).waitFor()
		const dc = lastCommand()
		assert(dc.command === "create_delivery_challan" && dc.payload.selected_type === "balance" && dc.payload.from_location === "S-UNIT" && dc.payload.quantities.Red.sizes.S === 4 && dc.payload.quantities.Red.checked === true, `Create DC payload: ${JSON.stringify(dc)}`)
		await closeOverlays()
		console.log("PASS create DC: Fill copies Balance, server payload, result opens in shared DC viewer")
		assert(await page.locator('[data-finishing-tab="item-details"]').getByText("Pieces Per Box").count() === 0 && await page.locator('[data-finishing-tab="item-details"] .finishing-facts').count() === 0, "Item Details must not repeat Item or Pieces Per Box")

		await toolbar.getByRole("button", { name: "Return Item" }).click()
		await dialog.getByLabel("Red S Quantity").fill("2")
		await dialog.getByRole("button", { name: "Return" }).click()
		await page.locator(".document-error-dialog").getByText("Enter Received Type.").waitFor()
		await page.locator(".document-error-dialog").getByRole("button", { name: "OK" }).click()
		assert(await dialog.getByLabel("Red S Quantity").inputValue() === "2", "Validation popup must keep entered values")
		await dialog.locator(".p-dialog-footer").getByRole("button", { name: "Close" }).click()
		console.log("PASS return item: required Received Type popup keeps entered quantities")

		await toolbar.getByRole("button", { name: "Convert to Loose Piece" }).click()
		await dialog.getByLabel("Red M Quantity").fill("1")
		await dialog.getByRole("button", { name: "Convert" }).click()
		await dialog.waitFor({ state: "hidden" })
		assert(lastCommand().command === "convert_to_loose_piece" && lastCommand().payload.from_location === "S-UNIT" && lastCommand().payload.quantities.Red.sizes.M === 1, `Loose piece payload: ${JSON.stringify(lastCommand())}`)
		console.log("PASS convert to loose piece: From Location defaults to the plan location, payload")

		await page.getByRole("tab", { name: "GRN", exact: true }).click()
		await page.getByRole("group", { name: "GRN actions" }).getByRole("button", { name: "Make GRN" }).click()
		await dialog.getByLabel("S boxes").fill("3")
		state.failNext = "create_grn"
		await dialog.getByRole("button", { name: "Create GRN" }).click()
		await page.locator(".document-error-dialog").getByText("Work Order WO-1 must be submitted and open").waitFor()
		await page.locator(".document-error-dialog").getByRole("button", { name: "OK" }).click()
		assert(await dialog.getByLabel("S boxes").inputValue() === "3", "Server error must keep the GRN quantities")
		await dialog.getByRole("button", { name: "Create GRN" }).click()
		await page.locator(".related-document-workspace-dialog .p-dialog-title", { hasText: "Goods Received Note · GRN-NEW" }).waitFor()
		const [failedGrn, grn] = commands.filter((command) => command.command === "create_grn")
		assert(grn.payload.quantities.S === 3 && grn.payload.quantities.M === 0 && grn.payload.delivery_location === "S-UNIT" && grn.payload.request_id && grn.payload.request_id === failedGrn.payload.request_id, `Make GRN payload: ${JSON.stringify(grn)}`)
		await closeOverlays()
		console.log("PASS make GRN: one popup on failure keeps values, retry reuses request id, result opens in shared GRN viewer")

		await page.getByRole("group", { name: "GRN actions" }).getByRole("button", { name: "Dispatch Box" }).click()
		await dialog.getByLabel("M dispatch boxes").fill("2")
		await dialog.getByRole("combobox", { name: "From Warehouse", exact: true }).waitFor()
		await page.waitForTimeout(300)
		assert(await linkValue(dialog, "From Supplier") === "S-UNIT" && await linkValue(dialog, "From Warehouse") === "WH-UNIT", "Dispatch Box must prefill the only Warehouse of the default From Supplier")
		await dialog.getByRole("button", { name: "Dispatch" }).click()
		await page.locator(".document-error-dialog").getByText("Enter To Supplier, To Warehouse, Goods Value, Vehicle No.").waitFor()
		await page.locator(".document-error-dialog").getByRole("button", { name: "OK" }).click()
		assert(await dialog.getByLabel("M dispatch boxes").inputValue() === "2", "Dispatch validation must keep the entered boxes")
		await chooseLink(dialog, "To Supplier", "S-EMPTY")
		await page.locator(".document-error-dialog").getByText("Supplier S-EMPTY has no Warehouse. Create one from the Supplier.").waitFor()
		await page.locator(".document-error-dialog").getByRole("button", { name: "OK" }).click()
		await chooseLink(dialog, "To Supplier", "S-TO")
		assert(await linkValue(dialog, "To Warehouse") === "", "A Supplier with several Warehouses must not prefill one")
		await chooseLink(dialog, "To Warehouse", "WH-TO-2")
		await dialog.locator("#finishing-goods-value").fill("100")
		await dialog.getByLabel("Vehicle No").fill("TN01")
		await dialog.getByRole("button", { name: "Dispatch" }).click()
		await dialog.waitFor({ state: "hidden" })
		await page.getByText("Stock dispatched", { exact: true }).waitFor()
		const dispatched = lastCommand()
		assert(dispatched.command === "dispatch_box" && dispatched.payload.from_supplier === "S-UNIT" && dispatched.payload.from_warehouse === "WH-UNIT" && dispatched.payload.to_supplier === "S-TO" && dispatched.payload.to_warehouse === "WH-TO-2" && !("from_location" in dispatched.payload) && !("to_location" in dispatched.payload), `Dispatch Box payload: ${JSON.stringify(dispatched.payload)}`)
		assert(await page.locator(".document-transaction-dialog").count() === 0, "Dispatch Box must stay on the Finishing Plan")
		console.log("PASS dispatch box: supplier/warehouse pairs, prefill, payload, stays on Finishing Plan")

		await page.getByRole("tab", { name: "Ironing Excess", exact: true }).click()
		await page.getByRole("button", { name: "Add Ironing Excess Qty" }).click()
		await dialog.getByLabel("Red M Ironing Excess").fill("2")
		await dialog.getByRole("button", { name: "Create" }).click()
		await page.locator(".document-transaction-dialog").waitFor()
		assert(lastCommand().payload.quantities.Red.sizes.M === 2, "Ironing excess payload")
		await closeOverlays()
		console.log("PASS ironing excess: Stock Entry result opens in the unchanged Stock Entry viewer")

		await page.getByRole("tab", { name: "Pack Return", exact: true }).click()
		await page.getByRole("button", { name: "Return Pack" }).click()
		await dialog.getByLabel("Red M Pack Return").fill("1")
		await dialog.getByRole("button", { name: "Create" }).click()
		await dialog.waitFor({ state: "hidden" })
		assert(lastCommand().command === "return_pack" && lastCommand().payload.quantities.Red.sizes.M === 1, "Return Pack payload")
		console.log("PASS return pack: payload")

		await page.getByRole("tab", { name: "Fetch From Old Lot", exact: true }).click()
		await page.getByLabel("Transfer Loose Piece FP-OLD Red S").fill("2")
		await page.getByRole("button", { name: "Lot Transfer" }).click()
		await page.locator(".document-error-dialog").getByText("Please mention Set Colour").waitFor()
		await page.locator(".document-error-dialog").getByRole("button", { name: "OK" }).click()
		await page.getByRole("combobox", { name: "FP-OLD Red set colour" }).click()
		await page.getByRole("option", { name: "Red", exact: true }).click()
		await page.getByRole("button", { name: "Lot Transfer" }).click()
		await page.locator(".p-confirmdialog").getByRole("button", { name: "Transfer" }).click()
		await page.locator(".document-transaction-dialog").waitFor()
		const transfer = lastCommand().payload.transfers[0]
		assert(transfer.source_fp === "FP-OLD" && transfer.colours.Red.set_combination === "Red" && Number(transfer.colours.Red.sizes.S.loose_piece) === 2, `Lot transfer payload: ${JSON.stringify(transfer)}`)
		await closeOverlays()
		console.log("PASS lot transfer: Set Colour validation, confirmation, payload")

		await page.getByRole("button", { name: "More Actions" }).click()
		await page.getByRole("menuitem", { name: "Create Alternative Plan" }).click()
		await dialog.getByText("Lot Source", { exact: true }).waitFor()
		assert(await dialog.getByText("Lot Name", { exact: true }).count() === 1 && await dialog.getByText("Alternative Item", { exact: true }).count() === 1, "Alternative Plan must ask Lot Source, Lot Name and Alternative Item")
		await dialog.getByRole("button", { name: "Next" }).click()
		await page.locator(".document-error-dialog").getByText("Enter Alternative Item, Item Production Detail.").waitFor()
		await page.locator(".document-error-dialog").getByRole("button", { name: "OK" }).click()
		await dialog.locator(".p-dialog-footer").getByRole("button", { name: "Close" }).click()
		await page.getByRole("button", { name: "More Actions" }).click()
		await page.getByRole("menuitem", { name: "Update Quantity" }).click()
		await dialog.getByRole("combobox", { name: "Target Lot" }).click().catch(async () => dialog.locator(".p-select").first().click())
		await page.getByRole("option", { name: "LOT-2", exact: true }).click()
		await dialog.getByLabel("Red S Conversion Qty").fill("1")
		await dialog.getByRole("button", { name: "Update" }).click()
		await page.waitForFunction(() => window.router.currentRoute.value.path === "/fabric-store/work-orders/WO-ALT")
		assert(lastCommand().payload.target_lot === "LOT-2" && lastCommand().payload.quantities.Red.sizes.S === 1, "Update Quantity payload")
		console.log("PASS update quantity: More Actions entry, payload, routes to the resulting Work Order")
		assert(errors.length === 0, `Page errors: ${errors.join("\n")}`)
	} finally {
		await page.close()
		await server.close()
	}
}

async function liveEntriesSuite(browser) {
	const [username, password] = readFileSync("/home/anas/.frappe-debug-creds-mrp3", "utf8").trim().split("\n")
	const plan = process.env.FINISHING_LIVE_PLAN || "FP-2627-00140"
	const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })
	page.setDefaultTimeout(30_000)
	const errors = [], commands = []
	page.on("pageerror", (error) => errors.push(error.message))
	page.on("request", (request) => { if (request.url().includes("execute_plan_command")) commands.push(JSON.parse(request.postData() || "{}")) })
	const dialog = page.locator(".finishing-entry-dialog")
	try {
		await page.goto(`${SITE}/login`, { waitUntil: "domcontentloaded" })
		await page.fill("#login_email", username.trim())
		await page.fill("#login_password", password.trim())
		await Promise.all([page.waitForNavigation({ waitUntil: "domcontentloaded" }).catch(() => {}), page.click(".btn-login, button[type=submit]")])
		const flows = [["item-details", "Create DC"], ["item-details", "Return Item"], ["item-details", "Convert to Loose Piece"], ["grn", "Make GRN"], ["grn", "Dispatch Box"], ["ironing-excess", "Add Ironing Excess Qty"], ["pack-return", "Return Pack"]]
		for (const [tab, label] of flows) {
			await page.goto(`${SITE}/web/finishing/plans/${plan}?tab=${tab}`, { waitUntil: "networkidle" })
			await page.getByRole("button", { name: label, exact: true }).click()
			await dialog.locator(".finishing-table").first().waitFor()
			assert(await dialog.locator(".workspace-load-error").count() === 0, `${label} dialog failed to load live data`)
			for (const width of [1600, 390]) {
				await page.setViewportSize({ width, height: 1000 })
				await settle(page)
				await noOverflow(page, `live ${label} ${width}`)
				await dialog.screenshot({ path: join(SHOT_DIR, `entry-${label.toLowerCase().replace(/\W+/g, "-")}-${width}.png`) })
			}
			await page.setViewportSize({ width: 1600, height: 1000 })
			if (label === "Create DC" || label === "Return Pack") {
				await dialog.getByRole("button", { name: label === "Create DC" ? "Create DC" : "Create" }).click()
				await page.locator(".document-error-dialog").waitFor()
				assert(await page.locator(".document-error-dialog").count() === 1, `${label} server rejection must show one popup`)
				await page.locator(".document-error-dialog").getByRole("button", { name: "OK" }).click()
				assert(await dialog.isVisible(), `${label} dialog must stay open after a rejected submit`)
			}
			await dialog.locator(".p-dialog-footer").getByRole("button", { name: "Close" }).click()
		}
		assert(commands.every((command) => Object.values(command.payload?.quantities || {}).every((row) => Object.values(row.sizes || {}).every((value) => Number(value) === 0))), "Live verification must only submit zero quantities")
		assert(errors.length === 0, `Live entry page errors: ${errors.join("\n")}`)
		console.log(`PASS live entries: every create dialog loads real data, zero-quantity submits are rejected by the real services with one popup; screenshots in ${SHOT_DIR}`)
	} finally {
		await page.close()
	}
}

const WEB_REPORTS = "essdee_yrp.finishing.web_reports"
const WEB_DISPATCH = "essdee_yrp.finishing.web_dispatch"
const REWORK_ACTIONS = "essdee_yrp.essdee_yrp.doctype.sd_yrp_grn_rework_item.sd_yrp_grn_rework_item"
const workflowResponses = {
	[`${WEB_REPORTS}.get_packing_dpr`]: { data: [{ date: "2026-10-01", lot: "LOT-1", item: "TSHIRT", sizes: ["S", "M"], size_qty: { S: 10, M: 5 }, total_pieces: 15, pieces_per_box: 5, total_boxes: 3 }, { date: "2026-10-02", lot: "LOT-2", item: "POLO", sizes: ["S"], size_qty: { S: 20 }, total_pieces: 20, pieces_per_box: 10, total_boxes: 2 }], sizes: ["S", "M"] },
	[`${WEB_REPORTS}.get_dispatch_report`]: { data: [{ lot: "LOT-1", item: "TSHIRT", sizes: ["S", "M"], pieces_per_box: 5, packed_qty: { S: 10, M: 5 }, packed_total_boxes: 3, packed_total_pieces: 15, dispatched_qty: { S: 10 }, dispatched_total_boxes: 2, dispatched_total_pieces: 10 }] },
	[`${WEB_REPORTS}.get_rejection_details`]: { types: ["Oil Mark"], total_detail: { "Oil Mark": 4 }, total_sum: 4, report_detail: { "RW-1": { grn_number: "GRN-1", date: "2026-10-02 10:00:00", lot: "LOT-1", item: "TSHIRT", size: "Size", types: { "Oil Mark": 4 }, total: 4, rejection_detail: { "Oil Mark-Red": { items: [{ Size: "S", rejected_qty: 4 }] } } } } },
	"frappe.desk.query_report.run": { columns: [{ label: "Style", fieldname: "item", fieldtype: "Data" }, { label: "Description", fieldname: "description", fieldtype: "Data" }, { label: "Lot", fieldname: "lot", fieldtype: "Link" }, { label: "Pieces Per Box", fieldname: "pieces_per_box", fieldtype: "Data" }, { label: "Sewing Difference", fieldname: "sewing_diff", fieldtype: "Int" }], result: [{ item: "TSHIRT", description: "Top", lot: "LOT-1", pieces_per_box: 5, sewing_diff: -3 }] },
	[`${WEB_REPORTS}.get_rework_details`]: { types: ["Oil Mark"], total_detail: { "Oil Mark": 5 }, total_rejection_detail: { "Oil Mark": 1 }, total_sum: 5, total_rejection: 1, permissions: { can_read: true, can_write: true }, report_detail: { "RW-2": { grn_number: "GRN-2", date: "2026-10-03 08:00:00", lot: "LOT-1", item: "TSHIRT", warehouse: "S-0171", size: "Size", types: { "Oil Mark": 5 }, rejection_detail: { "Oil Mark": 1 }, total: 5, total_rejection: 1, rework_detail: { "Oil Mark-Red": { changed: 0, items: [{ Size: "S", rework_qty: 5, rejected: 1, rework: 0, row_name: "d1" }] } } } } },
	[`${WEB_REPORTS}.get_rework_groups`]: { permissions: { can_write: true }, groups: { "TSHIRT/LOT-1": { item: "TSHIRT", lot: "LOT-1", sizes: ["S", "M"], size_attr: "Size", is_set_item: 0, rows: [{ colour: "Red", part: null, grn_number: "GRN-3", received_type: "Stain", lot: "LOT-1", received: { S: 4, M: 2 }, rejection: { S: 0 }, reworked: {}, items: [{ Size: "S", rework_qty: 4, rejected: 0, rework: 0, row_name: "g1" }, { Size: "M", rework_qty: 2, rejected: 0, rework: 0, row_name: "g2" }] }] } } },
	[`${REWORK_ACTIONS}.update_rejected_quantity`]: { name: "RW-2" },
	[`${REWORK_ACTIONS}.update_partial_quantity`]: { name: "RW-2" },
}
const dispatchItems = [{ lot: "LOT-1", item: "TSHIRT", doc_name: "FP-1", uom: "Box", values: { S: { qty: 4, row_detail: "r1", dispatch_qty: 0 }, M: { qty: 2, row_detail: "r2", dispatch_qty: 0 } }, total: { total_qty: 6, total_dispatch: 0 }, primary_attribute: "Size", packing_config: {}, dynamic_ratio_packing: false, packing_batches: [], batch_dispatches: [] }]
const dispatchWorkspace = (record, permissions) => ({ record, items: structuredClone(dispatchItems), permissions, print_formats: [] })

async function workflowsSuite(browser) {
	const server = await startHarness()
	const page = await browser.newPage({ viewport: { width: 1280, height: 900 } })
	page.setDefaultTimeout(30_000)
	const requests = [], errors = []
	page.on("pageerror", (error) => errors.push(error.message))
	await page.route("**/api/method/**", async (route) => {
		const method = route.request().url().split("/api/method/")[1].split("?")[0]
		const args = JSON.parse(route.request().postData() || "{}")
		requests.push({ method, args })
		const reply = (message) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ message }) })
		if (method === `${WORKSPACE}.get_capabilities`) return reply(capabilities)
		const locationReply = supplierWarehouseReply(method, args)
		if (locationReply) return reply(locationReply)
		if (method === `${WEB_REPORTS}.download_rejection_details`) return route.fulfill({ contentType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers: { "Content-Disposition": "attachment; filename=rejection_details.xlsx" }, body: "xlsx" })
		if (method === `${WEB_DISPATCH}.get_dispatch_workspace`) return reply(args.name ? dispatchWorkspace({ name: args.name, docstatus: 1, modified: "2026-10-09 10:00:00" }, { can_read: true, can_dispatch_stock: true, can_cancel: true, can_print: false }) : dispatchWorkspace({ name: "", docstatus: 0, naming_series: "FPD-2627-" }, { can_read: true, can_write: true, can_submit: true }))
		if (method === `${WEB_DISPATCH}.save_dispatch`) return reply(dispatchWorkspace({ name: "FPD-2627-00999", docstatus: args.submit ? 1 : 0, modified: "2026-10-09 11:00:00" }, { can_read: true, can_write: true, can_submit: true }))
		if (method === `${WEB_DISPATCH}.execute_dispatch_command`) return reply({ ...dispatchWorkspace({ name: args.name, docstatus: 1, stock_entry: "STE-9", modified: "2026-10-09 12:00:00" }, { can_read: true }), result: { doctype: "YRP Stock Entry", name: "STE-9" } })
		return reply(workflowResponses[method] ?? {})
	})
	const base = `http://127.0.0.1:${server.httpServer.address().port}/__finishing?path=`
	const called = (name) => requests.filter((request) => request.method.endsWith(name))
	const popup = page.locator(".document-error-dialog")
	const dismiss = async (text) => { await popup.getByText(text).waitFor(); await popup.getByRole("button", { name: "OK" }).click() }
	const generate = async () => { await page.locator(".report-shell").first().waitFor(); await page.getByRole("button", { name: "Generate", exact: true }).click(); await page.locator(".report-shell__results").first().waitFor() }
	const setDate = async (label, value) => { const input = page.getByRole("combobox", { name: label, exact: true }); await input.fill(value); await input.press("Tab"); await page.keyboard.press("Escape"); await settle(page) }
	try {
		await page.goto(`${base}/finishing/reports?report=packing-dpr`)
		await page.getByText("Summary", { exact: true }).click()
		await page.getByRole("button", { name: "Generate", exact: true }).click()
		await page.waitForTimeout(300)
		assert(called("get_packing_dpr").length === 0 && await page.locator("input:invalid").count() > 0, "Required Summary dates must block Generate")
		await setDate("From Date", "05-10-2026")
		await setDate("To Date", "02-10-2026")
		await page.getByRole("button", { name: "Generate", exact: true }).click()
		await dismiss("From Date cannot be after To Date")
		await setDate("From Date", "01-10-2026")
		await generate()
		assert(called("get_packing_dpr").at(-1).args.summary === 1 && called("get_packing_dpr").at(-1).args.from_date === "2026-10-01", "Packing DPR must send the Summary range")
		assert((await page.locator(".report-metrics").innerText()).includes("35") && await page.locator(".finishing-report-date").count() === 2, "Packing DPR must total pieces and head each date")
		await atEveryWidth(page, "packing dpr")
		console.log("PASS packing dpr: required range, From after To popup, range request, totals and date sections")

		await page.goto(`${base}/finishing/reports?report=dispatch-report`)
		await generate()
		assert(await page.locator("td.finishing-type--diff").filter({ hasText: /^5$/ }).count() === 2 && await page.locator("td.finishing-type--diff").filter({ hasText: /^1$/ }).count() === 1, "Dispatch Report diff row must show packed minus dispatched")
		assert((await page.locator(".report-metrics").innerText()).replace(/\s+/g, " ").includes("DIFF PIECES 5"), "Dispatch Report totals must include Diff Pieces")
		console.log("PASS dispatch report: Packed/Dispatched/Diff rows and totals")

		await page.goto(`${base}/finishing/reports?report=finishing-plan-report`)
		await generate()
		assert(await page.locator("td.finishing-value--negative").count() === 1, "Finishing Plan Report must colour negative differences red")
		assert(await page.locator("tbody td").first().evaluate((cell) => getComputedStyle(cell).position) === "sticky", "Finishing Plan Report must pin the identity columns")
		console.log("PASS finishing plan report: query report columns, pinned identity columns, red/green differences")

		await page.goto(`${base}/finishing/reports?report=rejection-details`)
		await generate()
		await page.getByRole("button", { name: "Expand RW-1" }).click()
		await page.getByText("Rejected Qty").waitFor()
		await page.getByRole("button", { name: "Download Excel" }).click()
		await page.waitForFunction(() => true)
		await page.waitForTimeout(300)
		const download = called("download_rejection_details").at(-1)
		assert(download && download.args.start_date && download.args.end_date, "Rejection export must be rebuilt from the applied filters")
		await page.getByRole("button", { name: "GRN-1" }).click()
		await page.locator(".related-document-workspace-dialog").waitFor()
		await page.locator(".related-document-workspace-dialog").getByRole("button", { name: "Close workspace" }).click().catch(() => page.keyboard.press("Escape"))
		console.log("PASS rejection details: expandable sizes, server-built Excel export, GRN opens in shared viewer")

		await page.goto(`${base}/finishing/reports?report=rework-completion`)
		await page.getByRole("button", { name: "Generate", exact: true }).click()
		await page.waitForTimeout(300)
		assert(called("get_rework_completion").length === 0 && await page.locator("input:invalid").count() > 0, "Rework Completion must require Lot and Process")
		console.log("PASS rework completion: Lot and Process are required")

		await page.goto(`${base}/finishing/rework-details`)
		await generate()
		await page.evaluate(() => { window.__opened = []; window.open = (url) => { window.__opened.push(url); return {} } })
		await page.getByRole("button", { name: "Print GRN-2" }).click()
		const pendingPrint = new URL((await page.evaluate(() => window.__opened)).at(-1), "http://localhost")
		assert(pendingPrint.pathname === "/printview" && pendingPrint.searchParams.get("doctype") === "YRP Goods Received Note" && pendingPrint.searchParams.get("name") === "GRN-2" && pendingPrint.searchParams.get("format") === "Essdee Rework Print", `Pending rework must print with Essdee Rework Print: ${pendingPrint}`)
		await page.getByText("Show Reworked", { exact: true }).click()
		await generate()
		await page.getByRole("button", { name: "Print GRN-2" }).click()
		assert(new URL((await page.evaluate(() => window.__opened)).at(-1), "http://localhost").searchParams.get("format") === "Essdee Reworked Print", "Reworked rows must print with Essdee Reworked Print")
		await page.getByText("Show Reworked", { exact: true }).click()
		await generate()
		await page.getByRole("button", { name: "Expand RW-2" }).click()
		await page.getByRole("button", { name: "Update Rejection Qty" }).click()
		await dismiss("There is nothing changed in this row.")
		await page.getByLabel("Oil Mark-Red S rejection").fill("2")
		await page.getByRole("button", { name: "Update Rejection Qty" }).click()
		await page.waitForFunction(() => true)
		await page.waitForTimeout(300)
		const rejection = called("update_rejected_quantity").at(-1)
		assert(rejection.args.completed === 0 && Number(rejection.args.rejection_data[0].rejected) === 2 && rejection.args.lot === "LOT-1", `Rejection payload: ${JSON.stringify(rejection.args)}`)
		assert(await page.getByRole("button", { name: "Collapse RW-2" }).count() === 1, "Refresh after an update must keep the source expanded")
		await page.getByRole("button", { name: "Update Reworked Piece" }).click()
		await dismiss("Enter at least one Reworked quantity.")
		await page.getByLabel("Oil Mark-Red S reworked").fill("9")
		await page.getByRole("button", { name: "Update Reworked Piece" }).click()
		await dismiss("Reworked quantity must be between 0 and the pending quantity.")
		assert(await page.getByLabel("Oil Mark-Red S reworked").inputValue() === "9", "Validation popup must keep the entered value")
		await page.getByLabel("Oil Mark-Red S reworked").fill("3")
		await page.getByRole("button", { name: "Update Reworked Piece" }).click()
		await page.locator(".p-confirmdialog").getByRole("button", { name: "Convert" }).click()
		await page.waitForTimeout(300)
		assert(Number(called("update_partial_quantity").at(-1).args.data[0].rework) === 3, "Reworked payload must carry the entered quantity")
		await atEveryWidth(page, "rework details")
		console.log("PASS rework details: row Print picks Rework/Reworked format, change check, range validation keeps values, confirmed conversion payloads")

		await page.goto(`${base}/finishing/rework-groups`)
		await generate()
		await page.getByLabel("GRN-3 Red M rejection").fill("1")
		await page.getByRole("button", { name: "Update Rejection Qty" }).click()
		await page.waitForTimeout(300)
		assert(JSON.stringify(called("update_rejected_quantity").at(-1).args.rejection_data.map((row) => [row.row_name, row.rejected])) === '[["g1",0],["g2",1]]', "Grouped rejection must map size inputs to source rows")
		await page.getByRole("button", { name: "Complete Rework" }).click()
		await page.locator(".p-confirmdialog").getByRole("button", { name: "Complete Rework" }).click()
		await page.waitForTimeout(300)
		assert(called("update_rejected_quantity").at(-1).args.completed === 1, "Complete Rework must finalise after confirmation")
		await atEveryWidth(page, "rework groups")
		console.log("PASS rework grouped details: size inputs map to source rows, confirmed completion")

		await page.goto(`${base}/finishing/dispatches/new`)
		await page.getByLabel("S dispatch boxes").fill("3")
		await page.getByRole("button", { name: "Save", exact: true }).click()
		await page.waitForFunction(() => window.router.currentRoute.value.path === "/finishing/dispatches/FPD-2627-00999")
		const saved = called("save_dispatch").at(-1).args
		assert(saved.items[0].values.S.dispatch_qty === 3 && saved.items[0].values.M.dispatch_qty === 0 && saved.submit === 0, `Dispatch save payload: ${JSON.stringify(saved.items[0].values)}`)
		await page.goto(`${base}/finishing/dispatches/FPD-2627-00999`)
		await page.getByRole("button", { name: "Dispatch Stock" }).click()
		await page.locator(".p-dialog").getByRole("button", { name: "Dispatch", exact: true }).click()
		await dismiss("Enter From Supplier, From Warehouse, To Supplier, To Warehouse, Goods Value, Vehicle No.")
		assert(called("execute_dispatch_command").length === 0, "Dispatch Stock must not run without its mandatory fields")
		const stockDialog = page.locator(".p-dialog").filter({ has: page.getByRole("combobox", { name: "From Supplier", exact: true }) })
		await chooseLink(stockDialog, "From Supplier", "S-UNIT")
		await page.waitForTimeout(300)
		assert(await linkValue(stockDialog, "From Warehouse") === "WH-UNIT", "Dispatch Stock must prefill the only Warehouse of the From Supplier")
		await chooseLink(stockDialog, "To Supplier", "S-TO")
		await chooseLink(stockDialog, "To Warehouse", "WH-TO-1")
		await chooseLink(stockDialog, "To Supplier", "S-EMPTY")
		await dismiss("Supplier S-EMPTY has no Warehouse. Create one from the Supplier.")
		assert(await linkValue(stockDialog, "To Warehouse") === "", "Changing the To Supplier must clear the To Warehouse")
		await chooseLink(stockDialog, "To Supplier", "S-TO")
		await chooseLink(stockDialog, "To Warehouse", "WH-TO-1")
		await stockDialog.getByLabel("Goods Value").fill("100")
		await stockDialog.getByLabel("Vehicle No").fill("TN01")
		await stockDialog.getByRole("button", { name: "Dispatch", exact: true }).click()
		await stockDialog.waitFor({ state: "hidden" })
		await page.getByText("Stock dispatched", { exact: true }).waitFor()
		const stockPayload = called("execute_dispatch_command").at(-1)?.args.payload || {}
		assert(stockPayload.from_supplier === "S-UNIT" && stockPayload.from_warehouse === "WH-UNIT" && stockPayload.to_supplier === "S-TO" && stockPayload.to_warehouse === "WH-TO-1" && !("from_location" in stockPayload), `Dispatch Stock payload: ${JSON.stringify(stockPayload)}`)
		assert(await page.locator(".document-transaction-dialog").count() === 0, "Dispatch Stock must stay on the Finishing Plan Dispatch")
		await atEveryWidth(page, "dispatch")
		console.log("PASS finishing plan dispatch: draft save, Dispatch Stock payload, refresh, toast, stays on dispatch")
		assert(errors.length === 0, `Page errors: ${errors.join("\n")}`)
	} finally {
		await page.close()
		await server.close()
	}
}

async function liveReportsSuite(browser) {
	const [username, password] = readFileSync("/home/anas/.frappe-debug-creds-mrp3", "utf8").trim().split("\n")
	const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })
	page.setDefaultTimeout(60_000)
	const errors = []
	page.on("pageerror", (error) => errors.push(error.message))
	page.on("request", (request) => { if (/update_|save_dispatch|execute_dispatch_command|execute_plan_command/.test(request.url())) errors.push(`Unexpected write ${request.url()}`) })
	const generate = async () => { await page.getByRole("button", { name: "Generate", exact: true }).click(); await page.waitForTimeout(300); await page.locator(".report-shell__results, .report-shell__empty").first().waitFor(); await page.locator(".report-shell__loading").waitFor({ state: "detached" }).catch(() => {}) }
	const setDate = async (label, value) => { const input = page.getByRole("combobox", { name: label, exact: true }); await input.fill(value); await input.press("Tab") }
	try {
		await page.goto(`${SITE}/login`, { waitUntil: "domcontentloaded" })
		await page.fill("#login_email", username.trim())
		await page.fill("#login_password", password.trim())
		await Promise.all([page.waitForNavigation({ waitUntil: "domcontentloaded" }).catch(() => {}), page.click(".btn-login, button[type=submit]")])
		const flows = [
			["packing-dpr", async () => { await page.getByText("Summary", { exact: true }).click(); await setDate("From Date", "01-09-2026"); await setDate("To Date", "03-09-2026") }],
			["dispatch-report", async () => { await setDate("From Date", "01-09-2026"); await setDate("To Date", "05-09-2026") }],
			["ironing-dpr", async () => setDate("Date", "01-09-2026")],
			["rejection-details", async () => {}],
		]
		for (const [report, prepare] of flows) {
			await page.goto(`${SITE}/web/finishing/reports?report=${report}`, { waitUntil: "networkidle" })
			await prepare()
			await generate()
			assert(await page.locator(".report-shell__results").count() === 1, `Live ${report} returned no results`)
			await atEveryWidth(page, `live ${report}`, `report-${report}`)
		}
		for (const path of ["/web/finishing", "/web/finishing/rework-details", "/web/finishing/rework-groups", "/web/finishing/dispatches"]) {
			await page.goto(`${SITE}${path}`, { waitUntil: "networkidle" })
			if (path.includes("rework")) await generate()
			await atEveryWidth(page, `live ${path}`, path.split("/").pop())
		}
		assert(errors.length === 0, `Live report errors: ${errors.join("\n")}`)
		console.log(`PASS live reports: Packing, Dispatch, Ironing and Rejection on real data; rework and dispatch pages read-only; screenshots in ${SHOT_DIR}`)
	} finally {
		await page.close()
	}
}

const browser = await chromium.launch({ headless: true })
try {
	if (suite === "mocked" || suite === "all") await mockedSuite(browser)
	if (suite === "entries" || suite === "all") await entriesSuite(browser)
	if (suite === "workflows" || suite === "all") await workflowsSuite(browser)
	if (suite === "live" || suite === "all") await liveSuite(browser)
	if (suite === "live-entries" || suite === "all") await liveEntriesSuite(browser)
	if (suite === "live-reports" || suite === "all") await liveReportsSuite(browser)
} finally {
	await browser.close()
}
