#!/usr/bin/env node

import { createRequire } from "node:module"
import { existsSync, readFileSync } from "node:fs"

const require = createRequire("/home/anas/.claude/playwright/package.json")
const { chromium } = require("playwright")

const SITE = process.env.ESSDEE_TEST_SITE || "http://erp-migration-test.site:8001"
const CREDENTIALS = "/home/anas/.frappe-debug-creds-mrp3"
const suite = process.argv[2] || "all"

function assert(condition, message) {
	if (!condition) throw new Error(message)
}

async function visibleTextBelowMinimum(root, minPx = 11) {
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
		return [{ tag: element.tagName.toLowerCase(), className: element.className, text: text.slice(0, 80), fontSize }]
	}), minPx)
}

async function assertNoPageOverflow(page, label) {
	const width = await page.locator("body").evaluate((element) => ({
		clientWidth: element.clientWidth,
		scrollWidth: element.scrollWidth,
	}))
	assert(width.clientWidth === width.scrollWidth, `${label} overflows the page: ${JSON.stringify(width)}`)
}

async function navigateWithinSpa(page, pathname) {
	await page.evaluate((nextPathname) => {
		window.history.pushState({}, "", nextPathname)
		window.dispatchEvent(new PopStateEvent("popstate", { state: window.history.state }))
	}, pathname)
	await page.waitForURL((url) => url.pathname === pathname)
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

async function missingLiveFixtures(page, fixtures) {
	const missing = []
	for (const [doctype, name] of fixtures) {
		const response = await page.context().request.get(
			`${SITE}/api/resource/${encodeURIComponent(doctype)}/${encodeURIComponent(name)}`,
		)
		if (response.status() === 404) missing.push(`${doctype} ${name}`)
		else assert(response.ok(), `Unable to inspect live fixture ${doctype} ${name} (${response.status()})`)
	}
	return missing
}

const capabilities = {
	sections: {
		work_orders: { label: "Work Orders", doctype: "YRP Work Order", can_read: true, can_create: false },
		purchase_orders: { label: "Purchase Orders", doctype: "Purchase Order", can_read: true, can_create: true },
		stock_transfers: {
			label: "Stock Transfers",
			operations: {
				stock_entry: { label: "Stock Entry", doctype: "YRP Stock Entry", can_read: true, can_create: true },
				stock_reconciliation: { label: "Stock Reconciliation", doctype: "YRP Stock Reconciliation", can_read: true, can_create: true },
				stock_update: { label: "Stock Update", doctype: "YRP Stock Update", can_read: true, can_create: true },
				lot_transfer: { label: "Lot Transfer", doctype: "SD YRP Lot Transfer", can_read: true, can_create: true },
			},
		},
		reports: { label: "Reports", reports: { stock_balance: { label: "Stock Balance", can_read: true } } },
	},
	related_documents: {},
}

const rows = {
	"YRP Work Order": { name: "WO-FAB-001", supplier: "FABRIC-STORE", item: "STYLE-001", lot: "LOT-001", status: "Open", docstatus: 1, modified: "2026-10-03 10:00:00" },
	"Purchase Order": { name: "PO-FAB-001", supplier: "SUPPLIER-001", transaction_date: "2026-10-03", status: "To Receive", grand_total: 12000, currency: "INR", docstatus: 1, modified: "2026-10-03 10:00:00" },
	"YRP Stock Entry": { name: "STE-FAB-001", purpose: "Material Issue", posting_date: "2026-10-03", docstatus: 0, modified: "2026-10-03 10:00:00" },
	"YRP Stock Reconciliation": { name: "SRC-FAB-001", purpose: "Stock Reconciliation", posting_date: "2026-10-03", docstatus: 0, modified: "2026-10-03 10:00:00" },
	"YRP Stock Update": { name: "STU-FAB-001", update_type: "Add", posting_date: "2026-10-03", docstatus: 0, modified: "2026-10-03 10:00:00" },
	"SD YRP Lot Transfer": { name: "LT-FAB-001", posting_date: "2026-10-03", docstatus: 0, modified: "2026-10-03 10:00:00" },
}

const fields = [
	["supplier", "Supplier", "Link"], ["item", "Item", "Link"], ["lot", "Lot", "Link"],
	["status", "Status", "Select"], ["transaction_date", "Date", "Date"], ["grand_total", "Grand Total", "Currency"],
	["purpose", "Purpose", "Select"], ["posting_date", "Posting Date", "Date"], ["update_type", "Update Type", "Select"],
].map(([fieldname, label, fieldtype]) => ({
	fieldname,
	label,
	fieldtype,
	in_list_view: 1,
	in_standard_filter: ["supplier", "status"].includes(fieldname) ? 1 : 0,
}))

function requestBody(route) {
	try { return JSON.parse(route.request().postData() || "{}") } catch { return {} }
}

async function selectAutocompleteOption(page, field, value) {
	const input = field.locator(".p-autocomplete-input")
	await input.fill(value)
	const option = page.locator(".p-autocomplete-option:visible").filter({ hasText: value }).first()
	await option.waitFor({ timeout: 20_000 })
	await option.click()
}

async function mockWorkspace(page, listRequests) {
	await page.route("**/api/method/essdee_yrp.fabric_store.web_workspace.get_capabilities*", (route) => route.fulfill({
		status: 200, contentType: "application/json", body: JSON.stringify({ message: capabilities }),
	}))
	await page.route("**/api/method/frappe.desk.form.load.getdoctype*", (route) => {
		const doctype = new URL(route.request().url()).searchParams.get("doctype")
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ docs: [{ name: doctype, is_submittable: 1, fields }] }) })
	})
	await page.route("**/api/method/yrp.yrp.doctype.yrp_user_listview.yrp_user_listview.get_user_listview*", (route) => route.fulfill({
		status: 200, contentType: "application/json", body: JSON.stringify({ message: [] }),
	}))
	await page.route("**/api/method/essdee_yrp.fabric_store.web_workspace.get_purchase_order_workspace*", (route) => route.fulfill({
		status: 200, contentType: "application/json", body: JSON.stringify({ message: {
			record: { doctype: "Purchase Order", ...rows["Purchase Order"], permissions: { can_read: true, can_print: false } },
			details: [], item_groups: [], item_row_count: 0,
			permissions: { can_read: true, can_print: false }, print_formats: [],
			grn: { can_create: false, reason: "No pending quantities remain to receive." },
		} }),
	}))
	await page.route("**/api/method/essdee_yrp.fabric_store.web_workspace.get_work_order_workspace*", (route) => route.fulfill({
		status: 200, contentType: "application/json", body: JSON.stringify({ message: {
			record: { doctype: "YRP Work Order", ...rows["YRP Work Order"] },
			details: [], deliverables: [], receivables: [], summary: {},
			delivery_challans: [], goods_received_notes: [], permissions: { can_read: true },
			related_permissions: {
				delivery_challan: { can_read: true, can_create: false },
				goods_received_note: { can_read: true, can_create: false },
			},
		} }),
	}))
	await page.route("**/api/method/frappe.desk.reportview.get_count*", (route) => {
		const body = requestBody(route)
		listRequests.push({ kind: "count", doctype: body.doctype, filters: body.filters })
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: 1 }) })
	})
	await page.route("**/api/resource/**", (route) => {
		const url = new URL(route.request().url())
		const doctype = decodeURIComponent(url.pathname.split("/api/resource/")[1] || "")
		listRequests.push({ kind: "list", doctype, filters: JSON.parse(url.searchParams.get("filters") || "[]") })
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data: rows[doctype] ? [rows[doctype]] : [] }) })
	})
}

async function shellSuite(page) {
	const listRequests = []
	await mockWorkspace(page, listRequests)
	await page.setViewportSize({ width: 1600, height: 1000 })
	await page.goto(`${SITE}/web/fabric-store`, { waitUntil: "domcontentloaded" })
	await page.locator(".workspace-launcher").waitFor({ timeout: 20_000 })

	const expectedCards = ["Work Orders", "Purchase Orders", "Stock Transfers", "Reports"]
	const cards = page.locator(".workspace-launcher__card")
	await cards.nth(expectedCards.length - 1).waitFor()
	assert(await cards.count() === expectedCards.length, `Unexpected Fabric Store card count: ${await cards.count()}`)
	assert(JSON.stringify((await cards.locator("strong").allTextContents()).map((label) => label.trim())) === JSON.stringify(expectedCards), `Unexpected Fabric Store cards: ${await cards.locator("strong").allTextContents()}`)
	assert(await page.locator(".fabric-store-tabs").count() === 0, "The obsolete Fabric Store tab shell is still rendered")
	await cards.first().focus()
	const focusVisible = await cards.first().evaluate((element) => {
		const style = getComputedStyle(element)
		return style.outlineStyle !== "none" || style.boxShadow !== "none"
	})
	assert(focusVisible, "Fabric Store launcher cards have no visible keyboard focus")
	const undersizedText = await visibleTextBelowMinimum(page.locator(".workspace-launcher"))
	assert(undersizedText.length === 0, `Fabric Store contains visible text below 11px: ${JSON.stringify(undersizedText)}`)

	await page.getByRole("link", { name: /Work Orders/ }).click()
	await page.waitForURL("**/web/fabric-store/work-orders")
	await page.locator(".fabric-work-orders .common-list-view").waitFor({ timeout: 20_000 })
	const workOrderListCount = await page.locator(".fabric-work-orders .common-list-view").count()
	const focusedWorkspaceText = (await page.locator("main").innerText()).slice(0, 500)
	assert(workOrderListCount === 1, `Work Orders do not use the common ListView. URL=${page.url()} content=${JSON.stringify(focusedWorkspaceText)}`)
	const workOrderListGeometry = await page.locator(".fabric-work-orders .common-list-view").evaluate((list) => {
		const frame = list.querySelector(".list-table-frame")
		const tableRoot = list.querySelector(".premium-list-table")
		const tableContainer = list.querySelector(".p-datatable-table-container")
		return {
			viewportBounded: list.classList.contains("common-list-view--viewport-bounded"),
			height: list.getBoundingClientRect().height,
			frameHeight: frame?.getBoundingClientRect().height || 0,
			tableHeight: tableRoot?.getBoundingClientRect().height || 0,
			overflowY: tableContainer ? getComputedStyle(tableContainer).overflowY : "missing",
		}
	})
	assert(
		workOrderListGeometry.viewportBounded
			&& workOrderListGeometry.height < 900
			&& workOrderListGeometry.tableHeight <= workOrderListGeometry.frameHeight + 1
			&& ["auto", "scroll"].includes(workOrderListGeometry.overflowY),
		`Work Order list does not keep records in a bounded dashboard scroller: ${JSON.stringify(workOrderListGeometry)}`,
	)
	for (const label of ["Filters", "Columns", "Clear Filters"]) {
		assert(await page.getByRole("button", { name: label, exact: true }).count() >= 1, `Work Order ${label} action is missing`)
	}
	assert(await page.getByRole("button", { name: "Create Work Order", exact: true }).count() === 0, "Work Order list exposes Create without create permission")
	const workOrderStatusSelect = page.getByRole("combobox", { name: "Status filter" })
	assert(await workOrderStatusSelect.count() === 1, "Work Order status filters do not collapse into the compact selector")
	await workOrderStatusSelect.click()
	for (const status of ["Draft", "Submitted", "Partially Received", "Fully Received", "Closed", "Cancelled"]) {
		assert(await page.getByRole("option", { name: new RegExp(`^${status}\\s`) }).count() === 1, `Work Order status filters omit ${status}`)
	}
	assert(await page.getByRole("option", { name: /^In Progress\s/ }).count() === 0, "Work Order status filters still expose an unsupported status")
	await page.keyboard.press("Escape")
	const workOrderListRequests = listRequests.filter((request) => request.kind === "list" && request.doctype === "YRP Work Order")
	assert(
		workOrderListRequests.length > 0 && workOrderListRequests.every((request) => Array.isArray(request.filters) && request.filters.length === 0),
		`Work Order row requests contain an implicit Fabric Store filter: ${JSON.stringify(workOrderListRequests)}`,
	)
	await page.setViewportSize({ width: 320, height: 568 })
	const shortMobileList = await page.locator(".fabric-work-orders .common-list-view").evaluate((list) => {
		const frame = list.querySelector(".list-table-frame")
		const records = list.querySelector(".mobile-list-records")
		return {
			listOverflowY: getComputedStyle(list).overflowY,
			frameHeight: frame?.getBoundingClientRect().height || 0,
			recordsHeight: records?.getBoundingClientRect().height || 0,
		}
	})
	assert(
		shortMobileList.listOverflowY === "visible"
			&& shortMobileList.frameHeight >= shortMobileList.recordsHeight
			&& shortMobileList.recordsHeight >= 150,
		`Short mobile viewport collapses the record list: ${JSON.stringify(shortMobileList)}`,
	)
	await page.setViewportSize({ width: 390, height: 844 })
	const workOrderMobileQuickFilters = page.getByRole("button", { name: "Quick filters", exact: true })
	await workOrderMobileQuickFilters.click()
	await page.locator(".fabric-work-orders .list-quick-filters").waitFor()
	const expandedMobileList = await page.locator(".fabric-work-orders .common-list-view").evaluate((list) => {
		const statusSelect = list.querySelector(".list-status-select")
		const frame = list.querySelector(".list-table-frame")
		const records = list.querySelector(".mobile-list-records")
		return {
			listOverflowY: getComputedStyle(list).overflowY,
			statusSelectHeight: statusSelect?.getBoundingClientRect().height || 0,
			frameHeight: frame?.getBoundingClientRect().height || 0,
			recordsHeight: records?.getBoundingClientRect().height || 0,
		}
	})
	assert(
		expandedMobileList.listOverflowY === "visible"
			&& expandedMobileList.statusSelectHeight >= 44
			&& expandedMobileList.frameHeight >= expandedMobileList.recordsHeight
			&& expandedMobileList.recordsHeight > 0,
		`Expanded mobile quick filters make status tabs or records inaccessible: ${JSON.stringify(expandedMobileList)}`,
	)
	await workOrderMobileQuickFilters.click()
	await page.setViewportSize({ width: 1600, height: 1000 })

	await page.locator(".fabric-work-orders .premium-list-table").getByText("WO-FAB-001", { exact: true }).click()
	await page.waitForURL("**/web/fabric-store/work-orders/WO-FAB-001")
	assert(page.url().endsWith("/web/fabric-store/work-orders/WO-FAB-001"), "Work Order did not navigate to its routed workspace")

	await page.goto(`${SITE}/web/fabric-store/purchase-orders`, { waitUntil: "domcontentloaded" })
	await page.getByRole("button", { name: "Create Purchase Order", exact: true }).waitFor()
	assert(await page.getByRole("button", { name: "Create Purchase Order", exact: true }).count() === 1, "Purchase Order list does not expose the permission-controlled create action")
	await page.locator(".premium-list-table").getByText("PO-FAB-001", { exact: true }).waitFor({ timeout: 20_000 })
	const formattedDateCount = await page.getByText("03-10-2026", { exact: true }).count()
	const formattedCurrencyCount = await page.getByText("INR 12,000", { exact: true }).count()
	assert(formattedDateCount >= 1, `Purchase Order list does not format dates like its document view (found ${formattedDateCount})`)
	assert(formattedCurrencyCount >= 1, `Purchase Order list does not format currency with code and grouping (found ${formattedCurrencyCount})`)
	await page.setViewportSize({ width: 390, height: 844 })
	const mobileQuickFilters = page.getByRole("button", { name: "Quick filters", exact: true })
	await mobileQuickFilters.waitFor()
	assert(await mobileQuickFilters.getAttribute("aria-expanded") === "false", "Mobile quick filters are expanded by default")
	assert(!(await page.locator(".list-quick-filters").isVisible()), "Mobile quick filters consume the first viewport while collapsed")
	const mobileFirstRow = await page.locator(".mobile-list-records").getByText("PO-FAB-001", { exact: true }).boundingBox()
	assert(mobileFirstRow && mobileFirstRow.y < 844, `Mobile Purchase Order rows start below the first viewport: ${JSON.stringify(mobileFirstRow)}`)
	const mobileCreateBox = await page.getByRole("button", { name: "Create Purchase Order", exact: true }).boundingBox()
	assert(
		mobileCreateBox && mobileCreateBox.width >= 250 && mobileCreateBox.width <= 360,
		`Mobile primary list action is not a clear full-width command: ${JSON.stringify(mobileCreateBox)}`,
	)
	await page.setViewportSize({ width: 1600, height: 1000 })
	await page.locator(".premium-list-table").getByText("PO-FAB-001", { exact: true }).click()
	await page.waitForURL("**/web/fabric-store/purchase-orders/PO-FAB-001")
	await page.locator(".fabric-purchase-order-frame").waitFor()
	assert(await page.locator(".fabric-purchase-order-frame").count() === 1, "Purchase Order did not navigate to its routed workspace")

	await page.goto(`${SITE}/web/fabric-store/stock-transfers`, { waitUntil: "domcontentloaded" })
	const stock = page.locator(".fabric-stock-transfers")
	await stock.locator(".stock-operation-card").first().waitFor({ timeout: 20_000 })
	assert(await stock.locator(".stock-operation-card").count() === 4, "Stock Transfer operation selectors are incomplete")
	assert(await stock.getByRole("tab").count() === 0, "Stock Transfers repeat a second tab strip")
	assert(await stock.locator(".common-list-view").count() === 1, "Stock Transfers render more than one active list")
	await stock.getByRole("button", { name: /Stock Update/ }).click()
	await stock.locator(".premium-list-table").getByText("STU-FAB-001", { exact: true }).waitFor()

	await page.goto(`${SITE}/web/fabric-store/reports`, { waitUntil: "domcontentloaded" })
	await page.locator(".fabric-reports .report-shell").waitFor({ timeout: 20_000 })
	assert(await page.locator(".fabric-reports .report-shell").count() === 1, "Fabric Store does not reuse the shared Stock Balance report")
	assert(await page.getByRole("heading", { name: "Stock Balance", exact: true }).count() === 1, "Fabric Store report has no visible report identity")
	assert(await page.locator(".fabric-reports input[type=date]").count() === 0, "Fabric Store report uses a native date input")
	await page.setViewportSize({ width: 1280, height: 800 })
	await assertNoPageOverflow(page, "Fabric Store at 1280px")
	await page.setViewportSize({ width: 390, height: 844 })
	await assertNoPageOverflow(page, "Fabric Store at 390px")
	const reportCheckTargets = await page.locator(".stock-checks label").evaluateAll((labels) => labels.map((label) => label.getBoundingClientRect().height))
	assert(reportCheckTargets.length === 4 && reportCheckTargets.every((height) => height >= 43.9), `Stock report checkbox targets are too small: ${JSON.stringify(reportCheckTargets)}`)

	return { cards: expectedCards, listRequestCount: listRequests.length, focusVisible }
}

async function mobileRecordDetailsSuite(page) {
	await page.setViewportSize({ width: 390, height: 844 })
	await mockWorkspace(page, [])
	const workOrderWorkspaceRoute = "**/api/method/essdee_yrp.fabric_store.web_workspace.get_work_order_workspace*"
	const purchaseOrderWorkspaceRoute = "**/api/method/essdee_yrp.fabric_store.web_workspace.get_purchase_order_workspace*"
	const fields = [
		{ fieldname: "packing_instructions", label: "Packing Instructions", fieldtype: "Small Text", value: "Fold in pairs" },
		{ fieldname: "handling_instructions", label: "Handling Instructions", fieldtype: "Small Text", value: "Keep dry" },
		{ fieldname: "supplier_address_display", label: "Supplier Address Details", fieldtype: "Small Text", value: "Line one<br>Line two" },
		{ fieldname: "comments", label: "Comments", fieldtype: "Small Text", value: "Keep the finished cartons away from the loading bay until collection." },
		{ fieldname: "special_note", label: "Special Note", fieldtype: "Long Text", value: "UNINTERRUPTEDMOBILERECORDREFERENCETHATMUSTWRAPINSIDETHEDETAILGRIDWITHOUTCLIPPINGORHORIZONTALOVERFLOW" },
	]
	const measureFacts = (root, fieldSelector) => root.evaluate((element, selector) => {
		const rows = [...element.querySelectorAll(selector)]
		const byLabel = (label) => {
			const row = rows.find((candidate) => candidate.querySelector("span")?.textContent?.trim() === label)
			if (!row) return null
			const value = row.querySelector("strong")
			return {
				...row.getBoundingClientRect().toJSON(),
				valueClientWidth: value?.clientWidth || 0,
				valueScrollWidth: value?.scrollWidth || 0,
				valueText: value?.textContent || "",
			}
		}
		return {
			columns: getComputedStyle(element).gridTemplateColumns.split(" ").filter(Boolean).length,
			packing: byLabel("Packing Instructions"),
			handling: byLabel("Handling Instructions"),
			address: byLabel("Supplier Address Details"),
			comments: byLabel("Comments"),
			note: byLabel("Special Note"),
		}
	}, fieldSelector)
	const assertCompactFacts = (geometry, label) => assert(
		geometry.columns === 2
			&& geometry.packing
			&& geometry.handling
			&& Math.abs(geometry.packing.y - geometry.handling.y) < 2
			&& geometry.address?.width > geometry.packing.width * 1.7
			&& geometry.address.valueText === "Line one\nLine two"
			&& geometry.comments?.width > geometry.packing.width * 1.7
			&& geometry.note?.width > geometry.packing.width * 1.7
			&& geometry.note.valueScrollWidth <= geometry.note.valueClientWidth + 1,
		`${label} mobile facts do not retain paired compact fields with only long address/comment rows spanning: ${JSON.stringify(geometry)}`,
	)

	await page.unroute(workOrderWorkspaceRoute)
	await page.route(workOrderWorkspaceRoute, (route) => route.fulfill({
		status: 200,
		contentType: "application/json",
		body: JSON.stringify({ message: {
			record: { doctype: "YRP Work Order", name: "WO-MOBILE-001", docstatus: 1, status: "Open", supplier: "FABRIC-STORE", supplier_name: "Fabric Store" },
			fields, totals: [], matrices: { deliverables: [], receivables: [] }, summary: {}, related: {},
			permissions: { can_read: true }, capabilities: {}, related_permissions: {}, print_formats: [],
		} }),
	}))
	await page.goto(`${SITE}/web/fabric-store/work-orders/WO-MOBILE-001`, { waitUntil: "domcontentloaded" })
	const workOrderFacts = page.locator(".work-order-fields")
	await workOrderFacts.waitFor({ timeout: 20_000 })
	const workOrderGeometry = await measureFacts(workOrderFacts, ":scope > .work-order-field")
	assertCompactFacts(workOrderGeometry, "Work Order")
	await assertNoPageOverflow(page, "Work Order record at 390px")

	await page.unroute(purchaseOrderWorkspaceRoute)
	await page.route(purchaseOrderWorkspaceRoute, (route) => route.fulfill({
		status: 200,
		contentType: "application/json",
		body: JSON.stringify({ message: {
			record: { doctype: "Purchase Order", name: "PO-MOBILE-001", docstatus: 1, status: "To Receive", supplier: "SUPPLIER-001", supplier_name: "Fabric Supplier", transaction_date: "2026-10-03", grand_total: 12000, currency: "INR" },
			fields, totals: [], matrices: { items: [] }, related: {},
			permissions: { can_read: true }, capabilities: {}, print_formats: [], grn: {},
		} }),
	}))
	await page.goto(`${SITE}/web/fabric-store/purchase-orders/PO-MOBILE-001`, { waitUntil: "domcontentloaded" })
	const purchaseOrderFacts = page.locator(".purchase-order-page__details")
	await purchaseOrderFacts.waitFor({ timeout: 20_000 })
	const purchaseOrderGeometry = await measureFacts(purchaseOrderFacts, ":scope > div")
	assertCompactFacts(purchaseOrderGeometry, "Purchase Order")
	await assertNoPageOverflow(page, "Purchase Order record at 390px")

	return { workOrder: workOrderGeometry, purchaseOrder: purchaseOrderGeometry }
}

function workOrderGroup() {
	return {
		attributes: ["Colour"], primary_attribute: "Size", primary_attribute_values: ["S", "M"], pack_attr: "Colour",
		items: [{
			name: "STYLE-001", dimensions: { lot: "LOT-001" }, attributes: { Colour: "Navy" }, values: {
				S: { qty: 10, delivered: 8, received: 6, pending_qty: 2 },
				M: { qty: 5, delivered: 4, received: 3, pending_qty: 0 },
			},
			total_qty: 15, total_delivered: 12, total_received: 9, default_uom: "Pieces",
		}, {
			name: "STYLE-001", dimensions: { lot: "LOT-001" }, attributes: { Colour: "Wine" }, values: {
				S: { qty: 2, delivered: 1, received: 1, pending_qty: -1 },
				M: { qty: 2, delivered: 1, received: 1, pending_qty: 1 },
			},
			total_qty: 4, total_delivered: 2, total_received: 2, default_uom: "Pieces",
		}],
		total_details: { S: { planned: 10, delivered: 8, received: 6 }, M: { planned: 5, delivered: 4, received: 3 } },
		overall_planned: 15, overall_delivered: 12, overall_received: 9,
	}
}

async function workOrderSuite(page) {
	const group = workOrderGroup()
	const receivableGroup = structuredClone(group)
	for (const item of receivableGroup.items) {
		item.process_cost = "PC-KNITTING-001"
		for (const cell of Object.values(item.values || {})) {
			cell.cost = 12.5
			cell.total_cost = Number(cell.qty || 0) * cell.cost
		}
	}
	const summaryGroup = structuredClone(group)
	summaryGroup.items[1].values.S.pending_qty = 1
	const payload = {
		record: {
			doctype: "YRP Work Order", name: "WO-FAB-001", docstatus: 1, status: "Partially Delivered", open_status: "Open",
			supplier: "FABRIC-STORE", supplier_name: "Fabric Store", process_name: "Knitting", item: "STYLE-001", lot: "LOT-001", production_detail: "IPD-001",
			modified: "2026-10-03 10:00:00", permissions: { can_read: true, can_write: true, can_print: true },
		},
		details: [
			{ fieldname: "wo_date", label: "WO Date", fieldtype: "Date", value: "2026-10-03" },
			{ fieldname: "supplier", label: "Supplier", fieldtype: "Link", value: "FABRIC-STORE" },
			{ fieldname: "process_name", label: "Process Name", fieldtype: "Link", value: "Knitting" },
			{ fieldname: "item", label: "Item", fieldtype: "Link", value: "STYLE-001" },
			{ fieldname: "lot", label: "Lot", fieldtype: "Link", value: "LOT-001" },
			{ fieldname: "production_detail", label: "Production Detail", fieldtype: "Link", value: "IPD-001" },
		],
		fields: [
			{ fieldname: "wo_date", label: "WO Date", fieldtype: "Date", value: "2026-10-03" },
			{ fieldname: "supplier", label: "Supplier", fieldtype: "Link", value: "FABRIC-STORE" },
			{ fieldname: "process_name", label: "Process Name", fieldtype: "Link", value: "Knitting" },
			{ fieldname: "item", label: "Item", fieldtype: "Link", value: "STYLE-001" },
			{ fieldname: "lot", label: "Lot", fieldtype: "Link", value: "LOT-001" },
			{ fieldname: "production_detail", label: "Production Detail", fieldtype: "Link", value: "IPD-001" },
			{ fieldname: "internal_notes", label: "Internal Notes", fieldtype: "Small Text", value: "   " },
		],
		dimensions: [{ fieldname: "received_type", label: "Received Type", fieldtype: "Link", value: "Accepted" }],
		totals: [
			{ fieldname: "planned_quantity", label: "Planned Quantity", value: 19 },
			{ fieldname: "total_quantity", label: "Total Quantity", value: 19 },
		],
		deliverables: [group], receivables: [receivableGroup],
		matrices: { deliverables: [group], receivables: [receivableGroup] },
		summary: { item_detail: [summaryGroup], deliverables: [summaryGroup], work_order_docstatus: 1 },
		delivery_challans: [
			{ name: "DC-002", docstatus: 1, status: "Submitted", posting_date: "2026-10-03", posting_time: "12:30:00", supplier: "FABRIC-STORE", total_delivered_qty: 12 },
			{ name: "DC-001", docstatus: 0, status: "Draft", posting_date: "2026-10-02", posting_time: "10:00:00", supplier: "FABRIC-STORE" },
		],
		goods_received_notes: [
			{ name: "GRN-001", docstatus: 1, status: "Submitted", posting_date: "2026-10-03", posting_time: "14:15:00", supplier: "FABRIC-STORE" },
		],
		permissions: { can_read: true, can_write: true, can_cancel: true, can_print: true },
		capabilities: {
			cancel: { label: "Cancel Document" }, close: { label: "Close" },
			create_debit: { label: "Create Debit" }, create_rework: { label: "Create Rework" },
			change_delivery_date: { label: "Change Delivery Date" }, change_item: { label: "Change Item" },
			create_cutting_plan: { label: "Make Cutting Plan", source_context: { work_order: "WO-FAB-001", lot: "LOT-001", item: "STYLE-001" } },
			create_delivery_challan: { label: "Make DC", source_context: { work_order: "WO-FAB-001" } },
			create_goods_received_note: { label: "Make GRN", requires_delivery_challan: false, source_context: { work_order: "WO-FAB-001" } },
			create_material_issue: { label: "Material Issue", source_context: { work_order: "WO-FAB-001", purpose: "Material Issue", against: "YRP Work Order", against_id: "WO-FAB-001", from_warehouse: "FABRIC-WH", from_supplier: "FABRIC-STORE", to_supplier: "FABRIC-STORE" } },
			create_recut: { label: "Create Recut", source_context: { work_order: "WO-FAB-001", lot: "LOT-001" } },
			create_sewing_plan: { label: "Create Sewing Plan" },
		},
		related_permissions: {
			delivery_challan: { can_read: true, can_create: true },
			goods_received_note: { can_read: true, can_create: true },
		},
	}

	let workspaceLoads = 0
	let returnSave = null
	let lifecycleAction = ""
	let workOrderCommand = null
	let cuttingPlanRequest = null
	let failDeliveryDate = true
	let workOrderEditorLoadFailures = 0
	let stockOperationSave = null
	let selectionContextDelayMs = 0
	await page.route("**/api/method/essdee_yrp.fabric_store.web_workspace.get_work_order_workspace*", (route) => {
		workspaceLoads += 1
		return route.fulfill({
		status: 200, contentType: "application/json", body: JSON.stringify({ message: payload }),
		})
	})
	await page.route("**/api/method/essdee_yrp.api.link_search.link_search*", (route) => {
		const doctype = requestBody(route).doctype
		const value = doctype === "YRP Process" ? "Dyeing" : doctype === "SD YRP Lot" ? "LOT-002" : "TEST-VALUE"
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: [{ name: value, label: value }] }) })
	})
	await page.route("**/api/method/essdee_yrp.api.work_order.get_work_order_selection_context*", async (route) => {
		if (selectionContextDelayMs) await new Promise((resolve) => setTimeout(resolve, selectionContextDelayMs))
		return route.fulfill({
			status: 200, contentType: "application/json", body: JSON.stringify({ message: { process_is_cloth_process: false, options: [{ item: "STYLE-001", production_detail: "IPD-001" }], item_options: ["STYLE-001"] } }),
		})
	})
	await page.route("**/api/method/essdee_yrp.fabric_store.web_workspace.get_work_order_editor*", (route) => {
		const name = requestBody(route).name || ""
		if (name === "WO-EDITOR-LOAD-ERROR" && workOrderEditorLoadFailures++ === 0) {
			return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ exc: "TemporaryError", message: "Work Order editor is temporarily unavailable." }) })
		}
		const fabricCalculation = name === "WO-FAB-KNIT"
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: {
			doctype: "YRP Work Order", name, modified: "2026-10-03 10:00:00",
			values: { supplier: "FABRIC-STORE", process_name: "Knitting", lot: "LOT-001", item: "STYLE-001", production_detail: "IPD-001", wo_date: "2026-10-03", no_receivables: 0, expected_delivery_date: "2026-10-10", planned_start_date: "2026-10-03", planned_end_date: "2026-10-08", supplier_address: "", delivery_address: "", edit_wo_date: 0 },
			deliverable_details: name ? [group] : [], receivable_details: name ? [group] : [], calculated_items: name ? [{ name: "CALC-1", item_variant: "STYLE-001-S", quantity: 10, uom: "Pieces" }] : [],
			selection_context: { process_is_cloth_process: false, options: [{ item: "STYLE-001", production_detail: "IPD-001" }], item_options: ["STYLE-001"] },
			calculation_contexts: fabricCalculation ? { fabric: { rows: [{ fabric_row: "FABRIC-ROW-1", cloth_item: "CLOTH-001", production_detail: "IPD-001", kind: "knitting", has_colour: true, reference_routed: false, greige_colour: "Greige", colour_options: ["Greige", "Melange"], ratio: 1, yarns: [{ yarn_item: "YARN-001", ratio: 100 }], qty_rows: [{ key: "MATRIX-1:0", label: "30 Dia", out_attrs: { Dia: "30" }, prefill: 12 }] }] } } : name ? { garment: { process: "Knitting", rows: [{ source_row: "LOT-ROW-1", item_variant: "STYLE-001-S", attributes: { Colour: "Navy", Size: "S" }, available_qty: 10, qty: 10 }] } } : {},
			fields: [
				{ fieldname: "supplier", label: "Supplier", fieldtype: "Link", reqd: true, read_only: false },
				{ fieldname: "process_name", label: "Process", fieldtype: "Link", reqd: true, read_only: false },
				{ fieldname: "lot", label: "Lot", fieldtype: "Link", reqd: true, read_only: false },
				{ fieldname: "item", label: "Item", fieldtype: "Link", reqd: true, read_only: false },
				{ fieldname: "production_detail", label: "Production Detail", fieldtype: "Link", reqd: true, read_only: true },
				{ fieldname: "wo_date", label: "WO Date", fieldtype: "Date", reqd: true, read_only: false, read_only_depends_on: "eval: !doc.edit_wo_date" },
				{ fieldname: "planned_start_date", label: "Planned Start Date", fieldtype: "Date", reqd: true, read_only: false },
				{ fieldname: "planned_end_date", label: "Planned End Date", fieldtype: "Date", reqd: true, read_only: false },
				{ fieldname: "expected_delivery_date", label: "Expected Delivery Date", fieldtype: "Date", reqd: true, read_only: false },
				{ fieldname: "supplier_address", label: "Supplier Address", fieldtype: "Link", options: "Address", reqd: true, read_only: false },
				{ fieldname: "delivery_address", label: "Delivery Address", fieldtype: "Link", options: "Address", reqd: true, read_only: false },
			],
			condition_values: { edit_wo_date: 0 },
			dimensions: [{ fieldname: "lot", label: "Lot", fieldtype: "Link", options: "SD YRP Lot", mandatory: 1, value: "LOT-001" }], permissions: { can_create: true, can_write: true, can_submit: false },
		} }) })
	})
	await page.route("**/api/method/essdee_yrp.fabric_store.web_workspace.execute_work_order_command*", (route) => {
		workOrderCommand = requestBody(route)
		if (workOrderCommand.command === "prepare_recut") {
			const recutGroup = structuredClone(group)
			for (const row of recutGroup.items) for (const value of Object.values(row.values || {})) value.qty = 0
			return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: { lot: "LOT-001", item_details: [recutGroup], can_submit: true } }) })
		}
		if (workOrderCommand.command === "create_sewing_plan") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: { name: "SEW-PLAN-001" } }) })
		if (workOrderCommand.command === "get_close_context") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: { permission: { is_close_manager: true }, debits: [], reason_options: ["NA", "Cutting Shortage", "Printing Shortage", "Sewing Shortage", "Sewing Missing", "Others"], close_reason: "Sewing Shortage", close_other_reason: "", close_remarks: "Short receipt approved" } }) })
		if (workOrderCommand.command === "get_rework_context") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: { rows: [{ source_key: "SRC-1", source_label: "GRN-001", item_variant: "STYLE-001-S", available_qty: 3, received_type: "Rejected" }] } }) })
		if (workOrderCommand.command === "get_change_item_context") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: { supported: true, items: [{ row_name: "ROW-1", item_variant: "BUTTON-OLD", branch: "Knitting", qty: 2, uom: "Nos" }] } }) })
		if (workOrderCommand.command === "preview_change_item") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: { changes: [{ selection_id: "ROW-1", old_variant: "BUTTON-OLD", new_variant: "BUTTON-NEW" }] } }) })
		if (workOrderCommand.command === "change_delivery_date" && failDeliveryDate) {
			failDeliveryDate = false
			return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ exc: "ValidationError", message: "The delivery date could not be updated." }) })
		}
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: payload }) })
	})
	await page.route("**/api/method/essdee_yrp.fabric_store.web_workspace.get_stock_operation_editor*", (route) => route.fulfill({
		status: 200, contentType: "application/json", body: JSON.stringify({ message: {
			operation: "stock_entry", doctype: "YRP Stock Entry", dimensions: [], default_dimensions: {}, locked_dimensions: [], name: "", modified: null,
			defaults: { purpose: "Material Issue", against: "YRP Work Order", against_id: "WO-FAB-001", from_warehouse: "FABRIC-WH", from_supplier: "FABRIC-STORE", to_supplier: "FABRIC-STORE", posting_date: "2026-10-06", posting_time: "10:00:00" },
			item_groups: [group], purpose_options: ["Material Issue", "Material Consumed", "Send to Warehouse"], item_filters: { is_stock_item: 1 }, permissions: { can_create: true, can_submit: false },
		} }),
	}))
	await page.route("**/api/method/essdee_yrp.fabric_store.web_workspace.save_stock_operation*", (route) => {
		stockOperationSave = requestBody(route)
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: { record: { doctype: "YRP Stock Entry", name: "STE-MI-001", docstatus: 0 } } }) })
	})
	await page.route("**/api/method/essdee_yrp.cutting.plan_editor.get_editor*", (route) => {
		cuttingPlanRequest = requestBody(route)
		const seeded = cuttingPlanRequest.lot === "LOT-001"
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: {
			record: { name: "", lot: seeded ? "LOT-001" : "", item: seeded ? "STYLE-001" : "", production_detail: seeded ? "IPD-001" : "", work_order: seeded ? "WO-FAB-001" : "", maximum_no_of_plys: 20, maximum_allow_percent: 5, cutting_location: "Machine Cutting", modified: "" },
			matrix: { groups: seeded ? [group] : [] }, permissions: { can_create: true, can_write: false, can_submit: false }, fields: { show_work_order: true, can_edit_work_order: true }, options: { cutting_locations: ["Machine Cutting", "Manual Cutting"] },
		} }) })
	})
	for (const [method, doctype, root] of [
		["get_delivery_challan_workspace", "YRP Delivery Challan", "delivery"],
		["get_goods_received_note_workspace", "YRP Goods Received Note", "goods"],
	]) await page.route(`**/api/method/essdee_yrp.fabric_store.web_workspace.${method}*`, (route) => {
		const body = requestBody(route)
		const name = body.name || ""
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: {
				record: {
					doctype, name, docstatus: 0, status: "Draft", modified: "2026-10-03 12:00:00",
					work_order: "WO-FAB-001", process_name: "Knitting", item: "STYLE-001", lot: "LOT-001", supplier: "FABRIC-STORE",
				},
			fields: [{ fieldname: "posting_date", label: "Posting Date", fieldtype: "Date", value: "2026-10-03" }], totals: [], matrices: {}, related: {},
			permissions: { can_read: true, can_create: !name, can_write: Boolean(name), can_submit: false, can_print: false }, capabilities: {}, print_formats: [], root,
		} }) })
	})
	await page.route("**/api/method/essdee_yrp.fabric_store.web_workspace.get_document*", (route) => {
		const body = requestBody(route)
		const isReturn = body.name === "GRN-RET-001"
		return route.fulfill({
			status: 200, contentType: "application/json", body: JSON.stringify({ message: isReturn ? {
				record: { doctype: "YRP Goods Received Note", name: "GRN-RET-001", docstatus: 0, status: "Draft", modified: "2026-10-03 15:10:00", is_return: 1 },
				context: { work_order: "WO-FAB-001", item: "STYLE-001", lot: "LOT-001" },
				permissions: { can_read: true, can_write: true, can_submit: true, can_print: false },
				details: [
					{ fieldname: "naming_series", label: "Series", fieldtype: "Select", value: "GRN-" },
					{ fieldname: "against", label: "Against", fieldtype: "Link", value: "YRP Work Order" },
					{ fieldname: "against_id", label: "Against ID", fieldtype: "Dynamic Link", value: "WO-FAB-001" },
					{ fieldname: "item", label: "Item", fieldtype: "Link", value: "STYLE-001" },
					{ fieldname: "total_received_quantity", label: "Total Received Quantity", fieldtype: "Float", value: 2 },
					{ fieldname: "total", label: "Total", fieldtype: "Currency", value: 120 },
				], item_groups: [group], item_row_count: 2,
				print_formats: [], actions: {},
			} : {
				record: { doctype: "YRP Delivery Challan", name: "DC-002", docstatus: 1, status: "Submitted", modified: "2026-10-03 12:30:00" },
				context: { work_order: "WO-FAB-001", item: "STYLE-001", lot: "LOT-001" },
				permissions: { can_read: true, can_cancel: true, can_print: true },
				details: [
					{ fieldname: "naming_series", label: "Series", fieldtype: "Select", value: "DC-" },
					{ fieldname: "work_order", label: "Work Order", fieldtype: "Link", value: "WO-FAB-001" },
					{ fieldname: "item", label: "Item", fieldtype: "Link", value: "STYLE-001" },
					{ fieldname: "lot", label: "Lot", fieldtype: "Link", value: "LOT-001" },
					{ fieldname: "process_name", label: "Process Name", fieldtype: "Link", value: "Knitting" },
					{ fieldname: "total_delivered_qty", label: "Total Delivered Qty", fieldtype: "Float", value: 12 },
					{ fieldname: "stock_value", label: "Stock Value", fieldtype: "Currency", value: 345.5 },
				], item_groups: [group], item_row_count: 2,
				print_formats: [{ label: "Delivery Challan", format: "Essdee Delivery Challan" }], actions: { can_return: true, can_complete_transfer: false },
			} }),
		})
	})
	await page.route("**/api/method/essdee_yrp.fabric_store.web_workspace.get_delivery_challan_return_editor*", (route) => route.fulfill({
		status: 200, contentType: "application/json", body: JSON.stringify({ message: {
			delivery_challan: "DC-002", has_received_type: false, default_received_type: "", permissions: { can_create: true },
			items: [{ delivery_challan_item: "DCI-001", item_variant: "STYLE-001-S", uom: "Pieces", delivered_quantity: 10, consumed_quantity: 3, already_returned: 1, returnable_quantity: 6, return_quantity: 0 }],
		} }),
	}))
	await page.route("**/api/method/essdee_yrp.fabric_store.web_workspace.create_delivery_challan_return*", (route) => {
		returnSave = requestBody(route)
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: {
			record: { doctype: "YRP Goods Received Note", name: "GRN-RET-001", docstatus: 0, status: "Draft", modified: "2026-10-03 15:10:00", is_return: 1 },
			permissions: { can_read: true, can_write: true, can_submit: true, can_print: false }, details: [], item_groups: [group], item_row_count: 2, print_formats: [], actions: {},
		} }) })
	})
	await page.route("**/api/method/essdee_yrp.fabric_store.web_workspace.change_document_status*", (route) => {
		lifecycleAction = requestBody(route).action
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: {
			record: { doctype: "YRP Delivery Challan", name: lifecycleAction === "amend" ? "DC-003" : "DC-002", docstatus: lifecycleAction === "cancel" ? 2 : 0, status: lifecycleAction === "cancel" ? "Cancelled" : "Draft", modified: "2026-10-03 15:30:00" },
			permissions: lifecycleAction === "cancel" ? { can_read: true, can_amend: true, can_print: true } : { can_read: true, can_submit: true, can_print: true },
			details: [], item_groups: [group], item_row_count: 2, print_formats: [{ label: "Delivery Challan", format: "Essdee Delivery Challan" }],
		} }) })
	})
	await page.setViewportSize({ width: 1600, height: 1000 })
	await page.goto(`${SITE}/web/fabric-store/work-orders/WO-FAB-001`, { waitUntil: "domcontentloaded" })
	const frame = page.locator(".fabric-work-order-frame")
	await frame.waitFor({ timeout: 20_000 })
	assert(await frame.locator(".fabric-document-workspace").count() === 1, "Work Order does not use the shared full-page document workspace")
	const pageViewport = await page.locator("html").evaluate((element) => {
		const workspace = document.querySelector(".fabric-document-workspace--page")
		const departmentPage = document.querySelector(".department-page")
		return {
			clientHeight: element.clientHeight,
			scrollHeight: element.scrollHeight,
			workspace: workspace ? workspace.getBoundingClientRect().toJSON() : null,
			departmentPage: departmentPage ? departmentPage.getBoundingClientRect().toJSON() : null,
		}
	})
	assert(
		pageViewport.scrollHeight <= pageViewport.clientHeight + 1,
		`Work Order leaks its bounded workspace into browser-level vertical scrolling: ${JSON.stringify(pageViewport)}`,
	)
	const commandbar = frame.locator(".fabric-document-workspace__commandbar")
	assert(await commandbar.count() === 1, "Work Order has no top document command strip")
	assert(await commandbar.getByRole("button", { name: "Make DC", exact: true }).count() === 1, "Work Order Make DC is not in the top command strip")
	assert(await commandbar.getByRole("button", { name: "Make GRN", exact: true }).count() === 1, "Work Order Make GRN is not in the top command strip")
	assert(await commandbar.locator(".document-action-strip").count() === 1, "Work Order does not use the compact shared action strip")
	assert(await commandbar.getByRole("button", { name: "Make GRN", exact: true }).getAttribute("data-pc-severity") === null, "Work Order primary action is not filled")
	assert(await commandbar.getByRole("button", { name: "More", exact: true }).count() === 1, "Work Order has no overflow menu")
	assert(await commandbar.locator(".document-action-strip__secondary:visible").count() <= 2, "Work Order exposes more than two secondary actions")
	assert((await commandbar.boundingBox()).height <= 64, "Work Order command strip wraps onto multiple rows")
	await commandbar.getByRole("button", { name: "More", exact: true }).click()
	const workOrderMoreMenu = page.locator(".document-action-menu:visible")
	assert(await workOrderMoreMenu.getByText("Close", { exact: true }).count() === 1, "Work Order overflow menu omits Close")
	assert(await workOrderMoreMenu.getByText("Cancel Document", { exact: true }).count() === 1, "Work Order overflow menu omits its permitted lifecycle action")
	assert(await workOrderMoreMenu.getByText("Create Debit", { exact: true }).count() === 1, "Work Order overflow menu omits Create Debit")
	assert(await workOrderMoreMenu.getByText("Change Delivery Date", { exact: true }).count() === 1, "Work Order overflow menu omits Change Delivery Date")
	for (const action of ["Material Issue", "Create Recut", "Create Sewing Plan"]) assert(await workOrderMoreMenu.getByText(action, { exact: true }).count() === 1, `Work Order overflow menu omits ${action}`)
	await commandbar.getByRole("button", { name: "More", exact: true }).click()
	assert(await frame.locator(".fabric-document-workspace__footer").count() === 0, "Work Order still pushes lifecycle actions to a bottom footer")
	assert(await frame.locator(".work-order-page__actions").count() === 0, "Work Order still pushes operations into a bottom panel")
	assert(await page.getByText("Process", { exact: true }).count() === 1, "Work Order repeats Process outside its authoritative header fact")
	assert(await page.getByText("Item", { exact: true }).count() === 1, "Work Order repeats Item outside its authoritative header fact")
	assert(await page.getByText("Lot", { exact: true }).count() === 1, "Work Order repeats Lot outside its authoritative header fact")
	assert(await page.getByRole("heading", { name: "Work Order", exact: true }).count() === 1, "Work Order title is missing")
	assert(await page.getByText("WO-FAB-001", { exact: true }).count() === 1, "Work Order ID is missing")
	assert(await page.getByText("Partially Delivered", { exact: true }).count() >= 1, "Work Order status is missing")
	const headerFacts = page.locator(".work-order-header__facts")
	assert(await headerFacts.getByText("Fabric Store", { exact: true }).count() === 1, "Work Order header does not expose Supplier")
	assert(await headerFacts.getByText("Knitting", { exact: true }).count() === 1, "Work Order header does not expose Process")
	assert(await headerFacts.getByText("STYLE-001", { exact: true }).count() === 1, "Work Order header does not expose Item")
	assert(await headerFacts.getByText("LOT-001", { exact: true }).count() === 1, "Work Order header does not expose Lot")
	const workspaceColumns = page.locator(".fabric-document-workspace__columns")
	const columns = await workspaceColumns.evaluate((element) => getComputedStyle(element).gridTemplateColumns.split(" ").map(Number.parseFloat))
	assert(columns.length === 2 && columns[0] / columns[1] > 3.4 && columns[0] / columns[1] < 4.6, `Work Order is not 80/20: ${columns}`)
	const undersizedText = await visibleTextBelowMinimum(frame)
	assert(undersizedText.length === 0, `Work Order contains visible text below 11px: ${JSON.stringify(undersizedText)}`)

	const tabs = page.locator(".work-order-tabs").getByRole("tab")
	assert(JSON.stringify(await tabs.allTextContents()) === JSON.stringify(["Details", "Summary"]), `Unexpected Work Order tabs: ${await tabs.allTextContents()}`)
	assert(await page.locator(".work-order-tablist").evaluate((element) => getComputedStyle(element).position) === "sticky", "Work Order tabs are not fixed")
	assert(await page.getByText("WO Date", { exact: true }).isVisible(), "Work Order details are missing")
	assert(await page.locator(".work-order-tabs .work-order-fields").count() === 1, "Work Order details sit outside the tab hierarchy")
	assert(await page.locator(".work-order-fields").getByText("Supplier", { exact: true }).count() === 0, "Work Order detail grid repeats Supplier")
	assert(await page.locator(".work-order-fields").getByText("Production Detail", { exact: true }).count() === 1, "Work Order detail grid hides Production Detail")
	assert(await page.locator(".work-order-fields").getByText("Received Type", { exact: true }).count() === 1, "Work Order detail grid omits dynamic stock dimensions")
	assert(await page.getByText("Internal Notes", { exact: true }).count() === 0, "Work Order shows an empty read-only field")
	assert(await page.locator(".work-order-fields").getByText("Item", { exact: true }).count() === 0, "Work Order detail grid repeats Item")
	const workOrderFactColumns = await page.locator(".work-order-fields").evaluate((element) => getComputedStyle(element).gridTemplateColumns.split(" ").filter(Boolean).length)
	assert(workOrderFactColumns === 4, `Work Order operational facts are not a compact four-column ledger: ${workOrderFactColumns}`)
	assert(await page.locator(".work-order-item-matrix").count() >= 2, "Deliverable and receivable matrices are missing")
	assert(await page.locator(".work-order-details .work-order-item-group").count() === 2, "Work Order rows are not consolidated by Item and Lot")
	assert(await page.locator(".work-order-item-matrix").getByRole("columnheader", { name: "Item", exact: true }).count() === 0, "Work Order matrices repeat Item per row")
	const deliverablesMatrix = page.locator(".work-order-details .work-order-section").filter({ has: page.getByRole("heading", { name: "Deliverables", exact: true }) }).locator(".work-order-item-matrix")
	assert(await deliverablesMatrix.locator("tbody > tr").count() === 4, "Deliverables do not render Quantity and Pending as stage rows per combination")
	assert(JSON.stringify(await deliverablesMatrix.getByRole("columnheader").allTextContents()) === JSON.stringify(["Colour", "Details", "S", "M", "Total"]), `Deliverable primary-attribute headers repeat stage columns: ${await deliverablesMatrix.getByRole("columnheader").allTextContents()}`)
	assert(await deliverablesMatrix.locator(".matrix-stage--planned").count() === 2, "Deliverables omit Quantity stage rows")
	assert(await deliverablesMatrix.locator(".matrix-stage--pending").count() === 2, "Deliverables omit Pending stage rows")
	assert(JSON.stringify((await deliverablesMatrix.locator(".matrix-stage--pending").first().locator("td").allTextContents()).map((value) => value.trim())) === JSON.stringify(["Pending", "2", "0", "2"]), "Deliverables do not keep zero Pending values visible in the stage row")
	assert((await deliverablesMatrix.locator(".matrix-stage--pending").nth(1).locator("td").nth(1).textContent()).trim() === "-1", "Deliverables do not preserve negative Pending quantities")
	const receivablesMatrix = page.locator(".work-order-details .work-order-section").filter({ has: page.getByRole("heading", { name: "Receivables", exact: true }) }).locator(".work-order-item-matrix")
	assert(await receivablesMatrix.locator(".matrix-stage--cost").count() === 2, "Receivables hide their Unit cost stage rows")
	assert(await receivablesMatrix.locator(".matrix-stage--total_cost").count() === 2, "Receivables hide their Total cost stage rows")
	const matrixScrolls = await page.locator(".work-order-item-matrix__scroll").evaluateAll((elements) => elements.map((element) => ({ clientHeight: element.clientHeight, scrollHeight: element.scrollHeight })))
	assert(matrixScrolls.every(({ clientHeight, scrollHeight }) => scrollHeight <= clientHeight + 1), `Work Order matrices have nested vertical scrolling: ${JSON.stringify(matrixScrolls)}`)

	const railSections = page.locator(".work-order-activity-section")
	assert(await railSections.count() === 2, "DC and GRN rail sections are incomplete")
	const railHeights = await railSections.evaluateAll((elements) => elements.map((element) => Math.round(element.getBoundingClientRect().height)))
	assert(Math.abs(railHeights[0] - railHeights[1]) <= 2, `DC and GRN rail sections are not 50/50: ${railHeights}`)
	assert(await page.locator(".activity-list").evaluateAll((elements) => elements.every((element) => ["auto", "scroll"].includes(getComputedStyle(element).overflowY))), "Rail lists do not scroll independently")
	assert(await page.getByRole("button", { name: /Filter Delivery Challans/ }).count() === 1, "Delivery Challan filter is missing")
	assert(await page.getByRole("button", { name: /Filter Goods Received Notes/ }).count() === 1, "Goods Received Note filter is missing")
	for (const label of ["Delivery Challans", "Goods Received Notes"]) {
		const filterButton = page.getByRole("button", { name: `Filter ${label}`, exact: true })
		assert(await filterButton.getAttribute("aria-expanded") === "false", `${label} filter does not expose its collapsed state`)
		await filterButton.click()
		assert(await filterButton.getAttribute("aria-expanded") === "true", `${label} filter does not expose its expanded state`)
		assert(await page.getByRole("searchbox", { name: `Search ${label}`, exact: true }).isVisible(), `${label} filter did not reveal its search field`)
		await filterButton.click()
		assert(await filterButton.getAttribute("aria-expanded") === "false", `${label} filter does not expose its restored collapsed state`)
	}
	assert(await page.getByRole("button", { name: "Calculate Items", exact: true }).count() === 0, "Submitted Work Order exposes a calculation action without a server capability")
	assert(await page.getByRole("button", { name: "Submit", exact: true }).count() === 0, "Work Order exposes unauthorized Submit")
	await commandbar.getByRole("button", { name: "More", exact: true }).click()
	await page.locator(".document-action-menu:visible").getByText("Close", { exact: true }).click()
	const closePanel = page.getByRole("dialog", { name: "Close Work Order" })
	await closePanel.waitFor()
	const closeReason = closePanel.locator("label").filter({ hasText: "Close reason" })
	assert((await closeReason.locator(".p-select-label").textContent()).trim() === "Sewing Shortage", "Close approval does not preserve the requester's close reason")
	assert(await closePanel.getByLabel(/Remarks/).inputValue() === "Short receipt approved", "Close approval does not preserve the requester's close remarks")
	assert(await closePanel.locator("label").filter({ hasText: "Other reason" }).count() === 0, "Close form shows the conditional Other Reason field for a fixed close reason")
	await closeReason.locator(".p-select").click()
	assert(JSON.stringify(await page.locator(".p-select-overlay:visible .p-select-option").allTextContents()) === JSON.stringify(["NA", "Cutting Shortage", "Printing Shortage", "Sewing Shortage", "Sewing Missing", "Others"]), "Close form does not use the Essdee close-reason vocabulary")
	await page.locator(".p-select-overlay:visible .p-select-option").filter({ hasText: "Others" }).click()
	assert(await closePanel.locator("label").filter({ hasText: "Other reason" }).count() === 1, "Close form does not require the conditional Other Reason value")
	assert(await closePanel.getByRole("button", { name: "Close Work Order", exact: true }).isDisabled(), "Close form allows Others without its mandatory reason")
	await closePanel.getByRole("button", { name: "Cancel", exact: true }).click()
	const discardActionDialog = page.getByRole("dialog", { name: "Discard action changes?" })
	await discardActionDialog.waitFor()
	assert(await closePanel.count() === 1, "Work Order action popup discarded edited values without confirmation")
	await discardActionDialog.getByRole("button", { name: "Discard Changes", exact: true }).click()

	const parentUrl = page.url()
	await page.getByRole("button", { name: "Make DC", exact: true }).click()
	let relatedDialog = page.getByRole("dialog", { name: /Delivery Challan.*New/ })
	await relatedDialog.waitFor()
	assert(await relatedDialog.locator(".delivery-challan-workspace").count() === 1, "WO does not launch the shared Delivery Challan workspace")
	assert(await relatedDialog.locator(".p-dialog-maximize-button").count() === 1, "WO Delivery Challan workspace is not maximizable")
	assert(page.url() === parentUrl, "Opening a Work Order Delivery Challan navigated away from the parent")
	assert(await relatedDialog.getByRole("button", { name: "Submit", exact: true }).count() === 0, "Embedded Delivery Challan exposes unauthorized Submit")
	const embeddedFactsLayout = await relatedDialog.locator(".delivery-challan-header__facts").evaluate((element) => {
		const items = [...element.children].map((child) => child.getBoundingClientRect())
		const header = element.closest(".fabric-document-workspace__header")?.getBoundingClientRect()
		return {
			display: getComputedStyle(element).display,
			headerHeight: header?.height || 0,
			itemTops: items.map((item) => Math.round(item.top)),
		}
	})
	assert(
		embeddedFactsLayout.display === "flex"
			&& embeddedFactsLayout.headerHeight <= 58
			&& new Set(embeddedFactsLayout.itemTops).size === 1,
		`Embedded Delivery Challan facts are not a compact horizontal identity strip: ${JSON.stringify(embeddedFactsLayout)}`,
	)
	await page.setViewportSize({ width: 390, height: 844 })
	assert(await relatedDialog.locator(".delivery-challan-header__identity h1").count() === 0, "Embedded Delivery Challan repeats the outer dialog title")
	const embeddedMobileFill = await relatedDialog.evaluate((dialog) => {
		const content = dialog.querySelector(".p-dialog-content")?.getBoundingClientRect()
		const workspace = dialog.querySelector(".fabric-document-workspace--embedded")?.getBoundingClientRect()
		return {
			contentHeight: content?.height || 0,
			workspaceHeight: workspace?.height || 0,
			contentWidth: content?.width || 0,
			workspaceWidth: workspace?.width || 0,
		}
	})
	assert(
		Math.abs(embeddedMobileFill.contentHeight - embeddedMobileFill.workspaceHeight) <= 2
			&& Math.abs(embeddedMobileFill.contentWidth - embeddedMobileFill.workspaceWidth) <= 2,
		`Embedded Delivery Challan leaves dead space inside the mobile dialog: ${JSON.stringify(embeddedMobileFill)}`,
	)
	const embeddedHeader = await relatedDialog.locator(".fabric-document-workspace__header").boundingBox()
	const embeddedFirstField = await relatedDialog.locator(".delivery-challan-field-group .form-field").first().boundingBox()
	assert(embeddedHeader?.height <= 58 && embeddedFirstField?.y < 340, `Embedded Delivery Challan wastes mobile space before its first field: ${JSON.stringify({ embeddedHeader, embeddedFirstField })}`)
	const embeddedMain = await relatedDialog.locator(".fabric-document-workspace__main").boundingBox()
	const embeddedRail = await relatedDialog.locator(".fabric-document-workspace__rail").boundingBox()
	assert(embeddedMain && embeddedRail && embeddedMain.y < embeddedRail.y, `New embedded Delivery Challan front-loads totals before its form: ${JSON.stringify({ embeddedMain, embeddedRail })}`)
	await page.setViewportSize({ width: 1600, height: 1000 })
	await relatedDialog.getByLabel("Posting Date", { exact: true }).fill("04-10-2026")
	await relatedDialog.getByRole("button", { name: "Close workspace", exact: true }).click()
	const discardDialog = page.getByRole("dialog", { name: "Discard unsaved changes?" })
	await discardDialog.waitFor()
	assert(await relatedDialog.count() === 1, "Outer related-document close bypassed the unsaved-change guard")
	await discardDialog.getByRole("button", { name: "Keep Editing", exact: true }).click()
	await relatedDialog.getByRole("button", { name: "Close workspace", exact: true }).click()
	await page.getByRole("dialog", { name: "Discard unsaved changes?" }).getByRole("button", { name: "Discard Changes", exact: true }).click()
	await relatedDialog.waitFor({ state: "detached" })

	await page.getByRole("button", { name: "Make GRN", exact: true }).click()
	const grnSourceDialog = page.getByRole("dialog", { name: "Create Goods Received Note" })
	await grnSourceDialog.waitFor()
	assert(await grnSourceDialog.getByRole("combobox", { name: "Delivery Challan", exact: true }).inputValue() === "DC-002", "WO GRN chooser did not preselect its only submitted Delivery Challan")
	await grnSourceDialog.getByRole("button", { name: "Continue to GRN", exact: true }).click()
	relatedDialog = page.getByRole("dialog", { name: /Goods Received Note.*New/ })
	await relatedDialog.waitFor()
	assert(await relatedDialog.locator(".goods-received-note-workspace").count() === 1, "WO does not launch the shared GRN workspace")
	assert(page.url() === parentUrl, "Opening a Work Order GRN navigated away from the parent")
	await relatedDialog.getByRole("button", { name: "Close workspace", exact: true }).click()

	await railSections.first().getByText("DC-002", { exact: true }).click()
	relatedDialog = page.getByRole("dialog", { name: /Delivery Challan.*DC-002/ })
	await relatedDialog.waitFor()
	assert(await relatedDialog.locator(".delivery-challan-workspace").count() === 1, "Existing related documents do not reuse the embedded domain workspace")
	assert(page.url() === parentUrl, "Opening an existing Work Order document navigated away from the parent")
	await relatedDialog.getByRole("button", { name: "Close workspace", exact: true }).click()

	await page.getByRole("button", { name: "Make Cutting Plan", exact: true }).click()
	await page.waitForURL("**/web/cutting/plans/new?**")
	await page.locator(".cutting-plan-editor").waitFor()
	assert(cuttingPlanRequest?.lot === "LOT-001", `Cutting Plan did not load the Work Order Lot source: ${JSON.stringify(cuttingPlanRequest)}`)
	assert(await page.locator(".cutting-plan-editor").getByText("STYLE-001", { exact: true }).count() >= 1, "Cutting Plan did not derive the source Item")
	const cuttingWorkOrder = page.locator(".cutting-plan-editor__field").filter({ hasText: "Work Order" })
	assert(await cuttingWorkOrder.locator(".p-autocomplete-input").inputValue() === "WO-FAB-001", "Cutting Plan did not preserve the source Work Order")

	await page.goto(`${SITE}/web/fabric-store/work-orders/WO-FAB-001`, { waitUntil: "domcontentloaded" })
	await page.locator(".fabric-work-order-frame").waitFor()
	await commandbar.getByRole("button", { name: "More", exact: true }).click()
	await page.locator(".document-action-menu:visible").getByText("Change Delivery Date", { exact: true }).click()
	const actionPanel = page.getByRole("dialog", { name: "Change Delivery Date", exact: true })
	await actionPanel.waitFor()
	await actionPanel.getByLabel(/Delivery date/).fill("12-10-2026")
	await actionPanel.getByLabel(/Reason/).fill("Customer requested a revised date")
	await actionPanel.getByRole("button", { name: "Change Delivery Date", exact: true }).click()
	const actionError = page.getByRole("dialog", { name: "Change Delivery Date could not be completed", exact: true })
	await actionError.getByText("The delivery date could not be updated.", { exact: true }).waitFor()
	assert(await actionPanel.getByLabel(/Delivery date/).inputValue() === "12-10-2026", "Work Order action error discarded the entered delivery date")
	assert(await actionPanel.getByLabel(/Reason/).inputValue() === "Customer requested a revised date", "Work Order action error discarded the entered reason")
	assert(workOrderCommand?.command === "change_delivery_date", `Work Order action did not use the named command service: ${JSON.stringify(workOrderCommand)}`)
	await actionError.getByRole("button", { name: "OK", exact: true }).click()
	await page.keyboard.press("Escape")
	const discardFailedAction = page.getByRole("dialog", { name: "Discard action changes?" })
	await discardFailedAction.waitFor()
	const activeActionPanelCount = await page.locator(".work-order-action-panel:visible").count()
	assert(activeActionPanelCount === 1, `Work Order action error values were discarded without confirmation (active panels: ${activeActionPanelCount})`)
	await discardFailedAction.getByRole("button", { name: "Discard Changes", exact: true }).click()
	await actionPanel.waitFor({ state: "detached" })

	await commandbar.getByRole("button", { name: "More", exact: true }).click()
	await page.locator(".document-action-menu:visible").getByText("Material Issue", { exact: true }).click()
	const materialIssueDialog = page.getByRole("dialog", { name: "Create Stock Entry" })
	await materialIssueDialog.waitFor()
	assert((await materialIssueDialog.locator(".fabric-select-field").filter({ hasText: "Purpose" }).locator(".p-select-label").textContent()).trim() === "Material Issue", "WO Material Issue popup did not preserve its source purpose")
	await materialIssueDialog.getByRole("button", { name: "Save", exact: true }).click()
	await materialIssueDialog.waitFor({ state: "detached" })
	assert(stockOperationSave?.values?.against_id === "WO-FAB-001" && stockOperationSave?.values?.purpose === "Material Issue", `WO Material Issue lost its source context: ${JSON.stringify(stockOperationSave)}`)

	await commandbar.getByRole("button", { name: "More", exact: true }).click()
	await page.locator(".document-action-menu:visible").getByText("Create Recut", { exact: true }).click()
	const recutDialog = page.getByRole("dialog", { name: "Create Work Order Recut" })
	await recutDialog.waitFor()
	await recutDialog.locator(".work-order-recut-row .p-inputnumber-input").first().fill("2")
	await recutDialog.getByRole("button", { name: "Create Recut", exact: true }).click()
	await recutDialog.waitFor({ state: "detached" })
	assert(workOrderCommand?.command === "create_recut" && workOrderCommand.payload?.item_details?.[0]?.items?.some((row) => Object.values(row.values || {}).some((value) => value.qty === 2)), `WO Recut payload is incomplete: ${JSON.stringify(workOrderCommand)}`)

	await commandbar.getByRole("button", { name: "More", exact: true }).click()
	await page.locator(".document-action-menu:visible").getByText("Create Sewing Plan", { exact: true }).click()
	const sewingDialog = page.getByRole("dialog", { name: "Create Sewing Plan" })
	await sewingDialog.waitFor()
	await sewingDialog.getByRole("button", { name: "Create Sewing Plan", exact: true }).click()
	await sewingDialog.waitFor({ state: "detached" })
	assert(workOrderCommand?.command === "create_sewing_plan", `WO Sewing Plan action used the wrong command: ${JSON.stringify(workOrderCommand)}`)

	await tabs.filter({ hasText: "Summary" }).click()
	assert(await page.getByText("Planned", { exact: true }).count() >= 1, "Planned summary row is missing")
	assert(await page.getByText("Delivered", { exact: true }).count() >= 1, "Delivered summary row is missing")
	assert(await page.getByText("Received", { exact: true }).count() >= 1, "Received summary row is missing")
	assert(await page.getByText("Pending", { exact: true }).count() >= 1, "Pending summary row is missing")
	assert(await page.getByText("15", { exact: true }).count() >= 1, "Summary total is missing")
	assert(await page.getByRole("heading", { name: "Additional Deliverables", exact: true }).count() === 0, "Summary shows ordinary inputs as Additional Deliverables")

	await page.goto(`${SITE}/web/fabric-store/work-orders/WO-FAB-001/edit`, { waitUntil: "domcontentloaded" })
	const workOrderEditor = page.locator(".work-order-editor")
	await workOrderEditor.waitFor()
	assert(await workOrderEditor.getByRole("heading", { name: "Edit Work Order", exact: true }).count() === 1, "Work Order edit route does not render the editor")
	assert(await workOrderEditor.getByRole("button", { name: "Calculate Items", exact: true }).count() === 1, "Draft Work Order calculation does not follow the server calculation context")
	assert(await workOrderEditor.getByRole("button", { name: "Save & Submit", exact: true }).count() === 0, "Work Order editor exposes Save & Submit without submit permission")
	assert(await workOrderEditor.locator("label").filter({ hasText: /^Lot/ }).count() === 1, "Work Order editor renders Lot twice through its dynamic dimensions")
	assert(await workOrderEditor.getByLabel(/WO Date/).isDisabled(), "Work Order date ignores its effective read-only dependency")
	assert(await workOrderEditor.getByText("Planned Start Date *", { exact: true }).count() === 1, "Work Order editor does not expose required planned-start metadata")
	assert(await workOrderEditor.getByText("Supplier Address *", { exact: true }).count() === 1, "Work Order editor does not expose required supplier-address metadata")
	for (const label of ["Process *", "Lot *", "Item *", "Supplier Address *", "Delivery Address *"]) {
		assert(await workOrderEditor.getByRole("combobox", { name: label, exact: true }).getAttribute("aria-required") === "true", `Work Order editor does not expose ${label} as required to assistive technology`)
	}
	assert(await workOrderEditor.getByRole("button", { name: "Save", exact: true }).isDisabled(), "Work Order editor allows save with missing effective mandatory addresses")
	const processField = workOrderEditor.locator(".common-field").filter({ hasText: "Process *" })
	await selectAutocompleteOption(page, processField, "Dyeing")
	const workOrderSourceDialog = page.getByRole("dialog", { name: "Change Process?" })
	await workOrderSourceDialog.waitFor()
	const keepCurrentProcess = workOrderSourceDialog.getByRole("button", { name: "Keep Current Value", exact: true })
	await page.waitForFunction(() => document.activeElement?.textContent?.trim() === "Keep Current Value", null, { timeout: 2_000 })
	assert(await keepCurrentProcess.evaluate((element) => element === document.activeElement), "Source confirmation does not initially focus its safe action")
	await keepCurrentProcess.click()
	assert(await processField.locator(".p-autocomplete-input").inputValue() === "Knitting", "Rejected Work Order source change discarded the committed Process")
	await page.waitForFunction(() => document.activeElement?.id === "field-process_name-value", null, { timeout: 2_000 })
	assert(await processField.locator(".p-autocomplete-input").evaluate((element) => element === document.activeElement), "Closing a source confirmation does not restore focus to its initiating field")
	selectionContextDelayMs = 180
	await selectAutocompleteOption(page, processField, "Dyeing")
	const confirmedSourceDialog = page.getByRole("dialog", { name: "Change Process?" })
	await confirmedSourceDialog.waitFor()
	await confirmedSourceDialog.getByRole("button", { name: "Clear Rows & Continue", exact: true }).click()
	await page.waitForFunction(() => document.querySelector("#field-process_name-value")?.value === "Dyeing", null, { timeout: 3_000 })
	await page.waitForFunction(() => document.activeElement?.id === "field-process_name-value", null, { timeout: 3_000 })
	assert(await processField.locator(".p-autocomplete-input").evaluate((element) => element === document.activeElement), "Confirmed async source change loses focus after remounting its field")
	selectionContextDelayMs = 0

	await page.goto(`${SITE}/web/fabric-store/work-orders/WO-FAB-KNIT/edit`, { waitUntil: "domcontentloaded" })
	const fabricEditor = page.locator(".work-order-editor")
	await fabricEditor.waitFor()
	await fabricEditor.getByRole("button", { name: "Calculate Fabric Deliverables", exact: true }).click()
	const fabricPanel = page.getByRole("dialog", { name: "Calculate Fabric Deliverables" })
	await fabricPanel.waitFor()
	const fabricInputs = fabricPanel.locator(".work-order-fabric-row__quantities input")
	assert(await fabricInputs.count() === 2, "Fabric calculation cannot enter separate Dia × Colour quantities")
	assert(await fabricPanel.getByText("Greige · 30 Dia", { exact: true }).count() === 1, "Fabric calculation does not identify the Greige quantity")
	assert(await fabricPanel.getByText("Melange · 30 Dia", { exact: true }).count() === 1, "Fabric calculation does not identify the Melange quantity")
	await fabricInputs.nth(1).fill("5")
	await fabricPanel.getByRole("button", { name: "Calculate", exact: true }).click()
	assert(workOrderCommand?.command === "calculate_fabric", `Fabric calculation did not use its named command: ${JSON.stringify(workOrderCommand)}`)
	assert(JSON.stringify(workOrderCommand.payload.rows[0].entries.map((entry) => [entry.colour, entry.qty])) === JSON.stringify([["Greige", 12], ["Melange", 5]]), `Fabric calculation discarded colour-split quantities: ${JSON.stringify(workOrderCommand.payload)}`)

	await page.goto(`${SITE}/web/fabric-store/work-orders/new`, { waitUntil: "domcontentloaded" })
	await page.locator(".work-order-editor").waitFor()
	assert(await page.getByRole("heading", { name: "New Work Order", exact: true }).count() === 1, "Work Order new route does not render the editor")
	assert(await page.getByRole("button", { name: "Save", exact: true }).count() === 1, "Work Order new route does not expose the permission-controlled Save action")
	assert(await page.getByRole("button", { name: "Save & Submit", exact: true }).count() === 0, "New Work Order exposes Save & Submit without submit permission")
	await page.setViewportSize({ width: 390, height: 844 })
	const workOrderMobileHeader = await page.locator(".work-order-editor__header").evaluate((element) => ({ height: element.getBoundingClientRect().height, scrollWidth: element.scrollWidth, clientWidth: element.clientWidth }))
	assert(workOrderMobileHeader.height <= 60 && workOrderMobileHeader.scrollWidth === workOrderMobileHeader.clientWidth, `Work Order mobile header is oversized or overflows: ${JSON.stringify(workOrderMobileHeader)}`)
	assert(await page.locator(".work-order-editor__matrix-prompt").count() === 1 && await page.locator(".work-order-editor__matrix-section").count() === 0, "Blank Work Order still renders empty quantity matrices")
	const workOrderScheduleBoxes = await page.locator(".work-order-editor__schedule-field").evaluateAll((elements) => elements.map((element) => element.getBoundingClientRect().toJSON()))
	assert(workOrderScheduleBoxes.length === 4 && Math.abs(workOrderScheduleBoxes[0].bottom - workOrderScheduleBoxes[1].bottom) < 2 && Math.abs(workOrderScheduleBoxes[2].bottom - workOrderScheduleBoxes[3].bottom) < 2, `Work Order planning dates do not use compact paired mobile rows: ${JSON.stringify(workOrderScheduleBoxes)}`)
	await page.setViewportSize({ width: 1600, height: 1000 })

	await page.goto(`${SITE}/web/fabric-store/work-orders/WO-EDITOR-LOAD-ERROR/edit`, { waitUntil: "domcontentloaded" })
	const failedEditor = page.locator(".work-order-editor")
	await failedEditor.getByText("Work Order could not be loaded", { exact: true }).waitFor()
	await failedEditor.getByText("Work Order editor is temporarily unavailable.", { exact: true }).waitFor()
	assert(await page.getByRole("dialog", { name: "Work Order could not be loaded" }).count() === 0, "Failed Work Order load duplicates the same error in a popup")
	assert(await failedEditor.locator(".work-order-editor__body").count() === 0, "Failed Work Order load leaves an unusable empty form visible")
	await failedEditor.getByRole("button", { name: "Retry", exact: true }).click()
	await failedEditor.getByRole("heading", { name: "Edit Work Order", exact: true }).waitFor()
	assert(workOrderEditorLoadFailures === 2, `Work Order Retry did not reload exactly once: ${workOrderEditorLoadFailures}`)

	await page.setViewportSize({ width: 900, height: 760 })
	await page.goto(`${SITE}/web/fabric-store/work-orders/WO-FAB-001`, { waitUntil: "domcontentloaded" })
	await page.locator(".fabric-work-order-frame").waitFor()
	const responsiveColumns = await page.locator(".fabric-document-workspace__columns").evaluate((element) => getComputedStyle(element).gridTemplateColumns.split(" ").filter(Boolean).length)
	assert(responsiveColumns === 1, "Work Order does not collapse below desktop width")
	const responsiveMain = await page.locator(".fabric-document-workspace__main").boundingBox()
	const responsiveRail = await page.locator(".fabric-document-workspace__rail").boundingBox()
	assert(responsiveMain && responsiveRail && responsiveMain.y < responsiveRail.y, `Work Order buries primary content below the activity rail on compact screens: ${JSON.stringify({ responsiveMain, responsiveRail })}`)
	await page.setViewportSize({ width: 390, height: 844 })
	const bodyWidth = await page.locator("body").evaluate((element) => ({ clientWidth: element.clientWidth, scrollWidth: element.scrollWidth }))
	assert(bodyWidth.clientWidth === bodyWidth.scrollWidth, `Work Order overflows on mobile: ${JSON.stringify(bodyWidth)}`)
	const mobileDocumentChrome = await page.locator(".fabric-document-workspace--page").evaluate((workspace) => {
		const header = workspace.querySelector(".fabric-document-workspace__header")
		const facts = workspace.querySelector(".work-order-header__facts")
		const commandbar = workspace.querySelector(".fabric-document-workspace__commandbar")
		return {
			headerHeight: header?.getBoundingClientRect().height || 0,
			factsHeight: facts?.getBoundingClientRect().height || 0,
			commandClientWidth: commandbar?.clientWidth || 0,
			commandScrollWidth: commandbar?.scrollWidth || 0,
		}
	})
	assert(
		mobileDocumentChrome.headerHeight <= 128
			&& mobileDocumentChrome.factsHeight <= 48
			&& mobileDocumentChrome.commandScrollWidth <= mobileDocumentChrome.commandClientWidth + 1,
		`Work Order mobile chrome consumes or clips the document viewport: ${JSON.stringify(mobileDocumentChrome)}`,
	)
	const mobileViewport = await page.locator("html").evaluate((element) => {
		const workspace = document.querySelector(".fabric-document-workspace--page")
		const departmentPage = document.querySelector(".department-page")
		return {
			clientHeight: element.clientHeight,
			scrollHeight: element.scrollHeight,
			workspace: workspace?.getBoundingClientRect().toJSON(),
			departmentPage: departmentPage?.getBoundingClientRect().toJSON(),
		}
	})
	assert(
		mobileViewport.scrollHeight <= mobileViewport.clientHeight + 1,
		`Work Order leaks its bounded workspace into browser-level mobile scrolling: ${JSON.stringify(mobileViewport)}`,
	)

	return { desktopColumns: columns, railHeights, responsiveColumns }
}

async function purchaseOrderSuite(page) {
	const listRequests = []
	const group = workOrderGroup()
	for (const item of group.items) {
		for (const value of Object.values(item.values || {})) {
			value.rate = 125
			value.amount = Number(value.qty || 0) * value.rate
			value.total_amount = value.amount
		}
	}
	await mockWorkspace(page, listRequests)
	let currentName = "PO-FAB-001"
	let currentDocstatus = 1
	let workspaceLoads = 0
	let purchaseOrderSave = null
	let purchaseOrderSaveAttempts = 0
	let lifecycleAction = ""
	let purchaseOrderCommand = null
	let purchaseOrderMode = "submitted"
	let openStatus = "Open"
	let purchaseOrderEditorLoadFailures = 0
	let linkedLots = ["LOT-001"]
	let priceValidationEnabled = true
	let resolvedPurchaseOrderPrice = { rates: { S: 125, M: 130 }, tax: "GST 5", tax_rate: 5 }
	await page.route("**/api/method/essdee_yrp.api.link_search.link_search*", (route) => {
		const body = requestBody(route)
		const doctype = body.doctype
		const value = doctype === "Item" ? "STYLE-001" : doctype === "Supplier" ? (body.txt || "TEST-VALUE") : "TEST-VALUE"
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: [{ name: value, label: value }] }) })
	})
	const purchaseOrderCapabilities = () => {
		if (purchaseOrderMode === "request") return {
			save: { label: "Edit" }, send_approval_request: { label: "Send Request" },
		}
		if (purchaseOrderMode === "approver") return {
			save: { label: "Edit" }, approve: { label: "Approve PO" }, reject: { label: "Reject PO" },
		}
		if (currentDocstatus === 2) return { amend: { label: "Amend" } }
		if (currentDocstatus === 0) return { save: { label: "Edit" }, submit: { label: "Submit" } }
		return {
			cancel: { label: "Cancel Document" }, refresh_status: { label: "Refresh Status" },
			[openStatus === "Open" ? "close" : "reopen"]: { label: openStatus === "Open" ? "Close" : "Reopen" },
			update_linked_lots: { label: "Manage Linked Lots" },
			create_delivery_challan: { label: "Create Delivery Challan", work_order_required: true, source_context: { purchase_order: currentName } },
			create_goods_received_note: { label: "Create GRN", source_context: { purchase_order: currentName } },
		}
	}
	const purchaseOrderPayload = () => ({
		record: {
			doctype: "Purchase Order", name: currentName, docstatus: currentDocstatus,
			status: currentDocstatus === 2 ? "Cancelled" : currentDocstatus === 0 ? (purchaseOrderMode === "submitted" ? "Draft" : "Pending Approval") : "To Receive",
			open_status: openStatus, is_yrp_managed: 1, supplier: "SUPPLIER-001", supplier_name: "Fabric Supplier",
			transaction_date: "2026-10-03", schedule_date: "2026-10-08", set_warehouse: "FABRIC-WH",
			currency: "INR", total: 12000, grand_total: 12000, modified: "2026-10-03 10:00:00",
		},
		fields: [
			{ fieldname: "supplier", label: "Supplier", fieldtype: "Link", value: "SUPPLIER-001" },
			{ fieldname: "transaction_date", label: "Date", fieldtype: "Date", value: "2026-10-03" },
			{ fieldname: "schedule_date", label: "Required By", fieldtype: "Date", value: "2026-10-08" },
			{ fieldname: "set_warehouse", label: "Warehouse", fieldtype: "Link", value: "FABRIC-WH" },
			{ fieldname: "company", label: "Company", fieldtype: "Link", value: "Essdee" },
			{ fieldname: "comments", label: "Comments", fieldtype: "Small Text", value: "Deliver before noon" },
			{ fieldname: "internal_notes", label: "Internal Notes", fieldtype: "Small Text", value: "   " },
		],
		details: [],
		totals: [
			{ fieldname: "total_qty", label: "Total Qty", value: 19 },
			{ fieldname: "total", label: "Total", value: 12000 },
			{ fieldname: "total_discount", label: "Discount", value: 0 },
			{ fieldname: "total_tax", label: "Tax", value: 600 },
			{ fieldname: "grand_total", label: "Grand Total", value: 12600 },
		],
		matrices: { items: [group] }, item_groups: [group], item_row_count: 2,
		permissions: purchaseOrderMode === "submitted" && currentDocstatus === 1
			? { can_read: true, can_cancel: true, can_print: true }
			: currentDocstatus === 2
				? { can_read: true, can_amend: true, can_print: true }
				: { can_read: true, can_write: true, can_submit: true, can_print: true },
		capabilities: purchaseOrderCapabilities(),
		approval: { pending_approval: purchaseOrderMode !== "submitted", live_request: purchaseOrderMode === "approver" ? { name: "REQ-1", status: "Pending" } : null },
		linked_lots: linkedLots,
		related: currentDocstatus === 1 ? {
			delivery_challans: [{ name: "DC-PO-001", docstatus: 1, posting_date: "2026-10-04" }],
			goods_received_notes: [{ name: "GRN-PO-001", docstatus: 0, posting_date: "2026-10-05" }],
		} : {},
		print_formats: [{ label: "Purchase Order", format: "Essdee Purchase Order" }],
		grn: { can_create: currentDocstatus === 1, reason: currentDocstatus === 1 ? "" : "Submit this Purchase Order first." },
	})

	await page.route("**/api/method/essdee_yrp.fabric_store.web_workspace.get_purchase_order_workspace*", (route) => {
		workspaceLoads += 1
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: purchaseOrderPayload() }) })
	})
	await page.route("**/api/method/essdee_yrp.fabric_store.web_workspace.get_goods_received_note_workspace*", (route) => route.fulfill({
		status: 200, contentType: "application/json", body: JSON.stringify({ message: {
			record: { doctype: "YRP Goods Received Note", name: "", docstatus: 0, status: "Draft", modified: "" },
			fields: [
				{ fieldname: "posting_date", label: "Posting Date", fieldtype: "Date", value: "2026-10-03", reqd: true },
				{ fieldname: "supplier", label: "Supplier", fieldtype: "Link", options: "Supplier", value: "SUPPLIER-001", read_only: true },
			],
			totals: [{ fieldname: "total_received_quantity", label: "Total Received Quantity", value: 0 }],
			permissions: { can_read: true, can_create: true, can_write: false, can_submit: false, can_print: false },
			capabilities: {}, print_formats: [], matrices: {}, related: {},
		} }),
	}))
	await page.route("**/api/method/essdee_yrp.fabric_store.web_workspace.get_purchase_order_editor*", (route) => {
		const name = requestBody(route).purchase_order || ""
		if (name === "PO-EDITOR-LOAD-ERROR" && purchaseOrderEditorLoadFailures++ === 0) {
			return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ exc: "TemporaryError", message: "Purchase Order editor is temporarily unavailable." }) })
		}
		return route.fulfill({
		status: 200, contentType: "application/json", body: JSON.stringify({ message: {
			doctype: "Purchase Order", name, modified: "2026-10-03 10:00:00",
			values: {
				supplier: "SUPPLIER-001", transaction_date: "2026-10-03", schedule_date: "2026-10-08",
				set_warehouse: "FABRIC-WH", default_delivery_location: "", deliver_to_supplier: 0,
				currency: "INR", company: "Essdee", comments: "",
			},
			item_groups: [], dimensions: [], locked_dimensions: [], default_dimensions: {},
			item_filters: { has_variants: 1, disabled: 0 }, price_validation_enabled: priceValidationEnabled,
			permissions: { can_create: true, can_write: true, can_submit: true },
		} }),
	}) })
	await page.route("**/api/method/essdee_yrp.fabric_store.web_workspace.get_purchase_order_item_schema*", (route) => route.fulfill({
		status: 200, contentType: "application/json", body: JSON.stringify({ message: {
			item: "STYLE-001", attributes: [], primary_attribute: "Size", primary_attribute_values: ["S", "M"], default_uom: "Pieces", secondary_uom: "", attribute_values: {},
		} }),
	}))
	const purchaseOrderPriceRequests = []
	await page.route("**/api/method/essdee_yrp.fabric_store.web_workspace.get_purchase_order_item_price*", (route) => {
		purchaseOrderPriceRequests.push(requestBody(route))
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: resolvedPurchaseOrderPrice }) })
	})
	await page.route("**/api/method/essdee_yrp.fabric_store.web_workspace.save_purchase_order", (route) => {
		purchaseOrderSaveAttempts += 1
		purchaseOrderSave = requestBody(route)
		if (purchaseOrderSaveAttempts === 1) return route.fulfill({
			status: 200,
			contentType: "application/json",
			body: JSON.stringify({ exc: "ValidationError", exception: "frappe.exceptions.ValidationError: Delivery warehouse is no longer available." }),
		})
		currentName = "PO-FAB-NEW"
		currentDocstatus = purchaseOrderSave.submit ? 1 : 0
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: purchaseOrderPayload() }) })
	})
	await page.route("**/api/method/essdee_yrp.fabric_store.web_workspace.change_document_status*", (route) => {
		lifecycleAction = requestBody(route).action
		if (lifecycleAction === "submit") currentDocstatus = 1
		if (lifecycleAction === "cancel") currentDocstatus = 2
		if (lifecycleAction === "amend") { currentDocstatus = 0; currentName = "PO-FAB-002" }
		const payload = purchaseOrderPayload()
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: payload }) })
	})
	await page.route("**/api/method/essdee_yrp.fabric_store.web_workspace.execute_purchase_order_command*", (route) => {
		purchaseOrderCommand = requestBody(route)
		if (purchaseOrderCommand.command === "close") openStatus = "Close"
		if (purchaseOrderCommand.command === "reopen") openStatus = "Open"
		if (purchaseOrderCommand.command === "update_linked_lots") {
			linkedLots = linkedLots.filter((lot) => !(purchaseOrderCommand.payload?.remove_lots || []).includes(lot))
			linkedLots.push(...(purchaseOrderCommand.payload?.add_lots || []))
		}
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: purchaseOrderPayload() }) })
	})

	await page.setViewportSize({ width: 1440, height: 900 })
	await page.goto(`${SITE}/web/fabric-store/purchase-orders/PO-FAB-001`, { waitUntil: "domcontentloaded" })
	const workspace = page.locator(".fabric-purchase-order-frame")
	await workspace.waitFor()
	await workspace.locator(".item-matrix").waitFor({ timeout: 20_000 })
	assert(await workspace.locator(".item-matrix").count() === 1, "Purchase Order item matrix is missing")
	assert(await workspace.locator(".item-matrix__price").filter({ hasText: /^Rate / }).count() > 0, "Purchase Order workspace hides item rates")
	assert(await workspace.locator(".item-matrix__received").count() === 0, "Purchase Order item rows still show Received")
	assert(await workspace.locator(".item-matrix__price").filter({ hasText: /^Amount / }).count() === 0, "Purchase Order item rows still show Amount")
	assert(await workspace.locator(".item-matrix__pending").count() > 0, "Purchase Order item rows hide Pending")
	assert(await workspace.locator(".item-matrix__group-header small").count() === 0, "Purchase Order repeats Lot below item titles")
	assert(await workspace.locator(".item-matrix__scroll th").filter({ hasText: /^Lot$/ }).count() > 0, "Purchase Order does not show Lot as a table column")
	assert(await workspace.locator(".item-matrix__scroll td").filter({ hasText: /^LOT-001$/ }).count() > 0, "Purchase Order Lot column has no values")
	assert(await workspace.getByText(/Pending -/).count() === 0, "Purchase Order exposes a negative pending quantity")
	assert(await workspace.getByText(/Over-received 1/).count() >= 1, "Purchase Order does not explain over-received quantities")
	const purchaseMatrixScroller = workspace.locator(".item-matrix__scroll").first()
	assert(await purchaseMatrixScroller.getAttribute("role") === "region" && await purchaseMatrixScroller.getAttribute("tabindex") === "0", "Purchase Order attribute matrix is not keyboard-scrollable")
	assert(Boolean(await purchaseMatrixScroller.getAttribute("aria-label")), "Purchase Order attribute matrix has no accessible name")
	const poQuantityLines = await workspace.locator(".item-matrix__qty").first().locator(":scope > strong, :scope > small").allTextContents()
	assert(poQuantityLines[1]?.startsWith("Rate ") && poQuantityLines[2]?.startsWith("Pending "), `Purchase Order quantity details are not ordered Quantity, Rate, Pending: ${JSON.stringify(poQuantityLines)}`)
	assert(await workspace.getByText("Supplier", { exact: true }).count() === 1, "Purchase Order repeats Supplier in the header and detail grid")
	for (const label of ["Required By", "Warehouse", "Company", "Comments"]) {
		assert(await workspace.getByText(label, { exact: true }).count() === 1, `Purchase Order field is missing: ${label}`)
	}
	assert(await workspace.getByText("Internal Notes", { exact: true }).count() === 0, "Purchase Order shows an empty read-only field")
	assert(await workspace.locator(".purchase-order-page__total").count() === 5, "Purchase Order does not render the server total rail")
	await page.setViewportSize({ width: 900, height: 760 })
	const compactTotals = await workspace.locator(".purchase-order-page__total").evaluateAll((elements) => elements.map((element) => element.getBoundingClientRect().toJSON()))
	assert(compactTotals.at(-1)?.width > compactTotals[0]?.width * 1.7, `Purchase Order final KPI does not deliberately span the compact rail: ${JSON.stringify(compactTotals)}`)
	const compactMain = await workspace.locator(".fabric-document-workspace__main").boundingBox()
	const compactRail = await workspace.locator(".fabric-document-workspace__rail").boundingBox()
	assert(compactMain && compactRail && compactMain.y < compactRail.y, `Purchase Order buries item details below the summary rail on compact screens: ${JSON.stringify({ compactMain, compactRail })}`)
	await page.setViewportSize({ width: 1440, height: 900 })
	assert(await workspace.locator(".purchase-order-related").getByText("DC-PO-001", { exact: true }).count() === 1, "Purchase Order does not show its related Delivery Challans")
	assert(await workspace.locator(".purchase-order-related").getByText("GRN-PO-001", { exact: true }).count() === 1, "Purchase Order does not show its related Goods Received Notes")
	await workspace.getByRole("button", { name: "Print", exact: true }).waitFor()
	assert(await workspace.getByRole("button", { name: "Create GRN", exact: true }).count() === 1, "Eligible Purchase Order does not expose Create GRN")
	assert(await workspace.getByRole("button", { name: "Submit", exact: true }).count() === 0, "Purchase Order renders unauthorized Submit")
	assert(await workspace.getByRole("button", { name: "Close", exact: true }).count() === 1, "Open submitted Purchase Order does not expose Close")
	assert(await workspace.getByRole("button", { name: "Manage Linked Lots", exact: true }).count() === 1, "Submitted Purchase Order does not expose linked-Lot management")

	await workspace.getByRole("button", { name: "Manage Linked Lots", exact: true }).click()
	const lotDialog = page.getByRole("dialog", { name: "Manage Linked Lots" })
	await lotDialog.waitFor()
	assert(await lotDialog.getByText("Reason *", { exact: true }).count() === 1, "Linked-Lot editor does not require a reason")
	await lotDialog.getByRole("button", { name: "Remove LOT-001", exact: true }).click()
	assert(await lotDialog.getByRole("button", { name: "Save Changes", exact: true }).isDisabled(), "Linked-Lot changes can be saved without a reason")
	await lotDialog.getByLabel("Reason *").fill("Correct supplier lot")
	await lotDialog.getByRole("button", { name: "Save Changes", exact: true }).click()
	await lotDialog.waitFor({ state: "hidden" })
	assert(purchaseOrderCommand?.command === "update_linked_lots", `Linked-Lot command was not sent: ${JSON.stringify(purchaseOrderCommand)}`)

	await workspace.getByRole("button", { name: "Close", exact: true }).click()
	const closeDialog = page.getByRole("dialog", { name: "Close Purchase Order?" })
	await closeDialog.waitFor()
	await closeDialog.getByRole("button", { name: "Close Purchase Order", exact: true }).click()
	await workspace.getByRole("button", { name: "Reopen", exact: true }).waitFor()
	assert(purchaseOrderCommand?.command === "close", "Purchase Order close command did not use the domain service")
	await workspace.getByRole("button", { name: "Reopen", exact: true }).click()
	await workspace.getByRole("button", { name: "Close", exact: true }).waitFor()
	assert(purchaseOrderCommand?.command === "reopen", "Purchase Order reopen command did not use the domain service")

	const parentUrl = page.url()
	await workspace.getByRole("button", { name: "Create GRN", exact: true }).click()
	const relatedDialog = page.getByRole("dialog", { name: /Goods Received Note.*New/ })
	await relatedDialog.waitFor()
	assert(await relatedDialog.locator(".goods-received-note-workspace").count() === 1, "PO does not launch the reusable GRN workspace")
	assert(await relatedDialog.locator(".p-dialog-maximize-button").count() === 1, "PO GRN workspace is not maximizable")
	assert(page.url() === parentUrl, "Opening the PO GRN workspace navigated away from the Purchase Order")
	await relatedDialog.getByRole("button", { name: "Close workspace", exact: true }).click()

	purchaseOrderMode = "request"
	currentDocstatus = 0
	await page.reload({ waitUntil: "domcontentloaded" })
	await page.locator(".fabric-purchase-order-frame").waitFor()
	await page.getByRole("button", { name: "Send Request", exact: true }).waitFor()
	assert(await page.getByRole("button", { name: "Send Request", exact: true }).count() === 1, "Pending PO without a live request does not expose Send Request")
	assert(await page.getByRole("button", { name: "Approve PO", exact: true }).count() === 0, "Non-approver PO state exposes Approve")
	assert(await page.getByRole("button", { name: "Submit", exact: true }).count() === 0, "Pending PO exposes unauthorized Submit")
	await page.getByRole("button", { name: "Send Request", exact: true }).click()
	assert(purchaseOrderCommand?.command === "send_approval_request", `PO approval request used the wrong command: ${JSON.stringify(purchaseOrderCommand)}`)
	purchaseOrderMode = "approver"
	await page.reload({ waitUntil: "domcontentloaded" })
	await page.locator(".fabric-purchase-order-frame").waitFor()
	await page.getByRole("button", { name: "Approve PO", exact: true }).waitFor()
	assert(await page.getByRole("button", { name: "Send Request", exact: true }).count() === 0, "PO with a live request still exposes Send Request")
	assert(await page.getByRole("button", { name: "Approve PO", exact: true }).count() === 1, "Approver PO state does not expose Approve")
	await page.getByRole("button", { name: "More", exact: true }).click()
	assert(await page.locator(".document-action-menu:visible").getByText("Reject PO", { exact: true }).count() === 1, "Approver PO state does not expose Reject")
	await page.locator(".document-action-menu:visible").getByText("Reject PO", { exact: true }).click()
	const rejectionDialog = page.getByRole("dialog", { name: "Reject Purchase Order" })
	await rejectionDialog.waitFor()
	assert(await rejectionDialog.getByRole("button", { name: "Reject Purchase Order", exact: true }).isDisabled(), "PO rejection is allowed without an audit reason")
	await rejectionDialog.getByLabel("Rejection reason *").fill("Rate exceeds the approved budget")
	await rejectionDialog.getByRole("button", { name: "Reject Purchase Order", exact: true }).click()
	await rejectionDialog.waitFor({ state: "hidden" })
	assert(purchaseOrderCommand?.command === "reject" && purchaseOrderCommand?.payload?.reason === "Rate exceeds the approved budget", `PO rejection did not send its audit reason: ${JSON.stringify(purchaseOrderCommand)}`)
	purchaseOrderMode = "submitted"
	currentDocstatus = 1
	await page.reload({ waitUntil: "domcontentloaded" })
	await page.locator(".fabric-purchase-order-frame").waitFor()

	await workspace.getByRole("button", { name: "More", exact: true }).click()
	await page.locator(".document-action-menu:visible").getByText("Cancel Document", { exact: true }).click()
	const cancelDialog = page.getByRole("dialog", { name: "Cancel Purchase Order?" })
	await cancelDialog.waitFor()
	await cancelDialog.getByRole("button", { name: "Cancel Purchase Order", exact: true }).click()
	await workspace.getByText("Cancelled", { exact: true }).waitFor()
	assert(lifecycleAction === "cancel", "Purchase Order cancel action did not run")
	await workspace.getByRole("button", { name: "Amend", exact: true }).click()
	const amendDialog = page.getByRole("dialog", { name: "Amend Purchase Order?" })
	await amendDialog.waitFor()
	await amendDialog.getByRole("button", { name: "Create Amendment", exact: true }).click()
	await page.waitForURL("**/web/fabric-store/purchase-orders/PO-FAB-002")
	await workspace.getByText("Draft", { exact: true }).waitFor()
	assert(lifecycleAction === "amend", "Purchase Order amend action did not run")
	await page.setViewportSize({ width: 390, height: 844 })
	const mobilePurchaseOrderButtonState = await workspace.locator(".fabric-document-workspace__commandbar").evaluate((element) => ({
		innerWidth: window.innerWidth,
		compact: window.matchMedia("(max-width: 899px)").matches,
		buttons: [...element.querySelectorAll("button")].map((button) => ({ text: button.textContent?.trim(), label: button.getAttribute("aria-label"), className: button.className, display: getComputedStyle(button).display })),
	}))
	assert(await workspace.getByRole("button", { name: "More", exact: true }).count() === 1, `Draft Purchase Order hides its secondary actions on mobile: ${JSON.stringify(mobilePurchaseOrderButtonState)}`)
	const mobilePurchaseOrderActions = await workspace.locator(".fabric-document-workspace__commandbar").evaluate((element) => ({ clientWidth: element.clientWidth, scrollWidth: element.scrollWidth }))
	assert(mobilePurchaseOrderActions.scrollWidth <= mobilePurchaseOrderActions.clientWidth + 1, `Draft Purchase Order actions require horizontal scrolling: ${JSON.stringify(mobilePurchaseOrderActions)}`)

	await page.goto(`${SITE}/web/fabric-store/purchase-orders`, { waitUntil: "domcontentloaded" })
	await page.getByRole("button", { name: "Create Purchase Order", exact: true }).click()
	await page.waitForURL("**/web/fabric-store/purchase-orders/new")
	const purchaseOrderEditor = page.locator(".purchase-order-editor")
	await purchaseOrderEditor.waitFor()
	await page.setViewportSize({ width: 390, height: 844 })
	const purchaseOrderMobileHeader = await page.locator(".purchase-order-editor__header").evaluate((element) => ({ height: element.getBoundingClientRect().height, scrollWidth: element.scrollWidth, clientWidth: element.clientWidth }))
	assert(purchaseOrderMobileHeader.height <= 60 && purchaseOrderMobileHeader.scrollWidth === purchaseOrderMobileHeader.clientWidth, `Purchase Order mobile header is oversized or overflows: ${JSON.stringify(purchaseOrderMobileHeader)}`)
	const companyInput = purchaseOrderEditor.getByRole("combobox", { name: "Company", exact: true })
	const companyValue = await companyInput.inputValue()
	assert(!companyValue || await companyInput.getAttribute("title") === companyValue, "Committed Company LinkField value has no full-value title affordance")
	const purchaseOrderDateBoxes = await page.locator(".purchase-order-editor__date").evaluateAll((elements) => elements.map((element) => element.getBoundingClientRect().toJSON()))
	assert(purchaseOrderDateBoxes.length === 2 && Math.abs(purchaseOrderDateBoxes[0].y - purchaseOrderDateBoxes[1].y) < 2, `Purchase Order dates do not use one compact mobile row: ${JSON.stringify(purchaseOrderDateBoxes)}`)
	await page.setViewportSize({ width: 320, height: 568 })
	const narrowPurchaseOrderDateBoxes = await page.locator(".purchase-order-editor__date").evaluateAll((elements) => elements.map((element) => element.getBoundingClientRect().toJSON()))
	assert(narrowPurchaseOrderDateBoxes.length === 2 && Math.abs(narrowPurchaseOrderDateBoxes[0].y - narrowPurchaseOrderDateBoxes[1].y) >= 40 && narrowPurchaseOrderDateBoxes.every((box) => box.width >= 220), `Purchase Order dates are truncated instead of stacking on narrow phones: ${JSON.stringify(narrowPurchaseOrderDateBoxes)}`)
	assert(await purchaseOrderEditor.locator(".stock-composer__step-number").count() === 3, "Purchase Order item builder does not expose the three workflow steps clearly")
	await page.setViewportSize({ width: 1600, height: 1000 })
	for (const label of ["Supplier *", "Delivery warehouse *"]) {
		assert(await purchaseOrderEditor.getByRole("combobox", { name: label, exact: true }).getAttribute("aria-required") === "true", `Purchase Order editor does not expose ${label} as required to assistive technology`)
	}
	const deliverToSupplierControl = purchaseOrderEditor.locator(".purchase-order-editor__check")
	const deliveryLocationControl = purchaseOrderEditor.locator(".common-field").filter({ hasText: "Delivery location" })
	assert(await deliverToSupplierControl.evaluate((control, location) => Boolean(control.compareDocumentPosition(location) & Node.DOCUMENT_POSITION_FOLLOWING), await deliveryLocationControl.elementHandle()), "Purchase Order delivery mode appears after the fields it controls")
	assert(!(await purchaseOrderEditor.innerText()).includes("* *"), "Purchase Order editor repeats required-field indicators")
	assert(await purchaseOrderEditor.locator('input[type="date"], input[type="time"], input[type="datetime-local"]').count() === 0, "Purchase Order editor uses native temporal inputs")
	const purchaseItem = purchaseOrderEditor.locator(".stock-composer__fields .common-field").filter({ hasText: "Item *" })
	await selectAutocompleteOption(page, purchaseItem, "STYLE-001")
	await purchaseOrderEditor.getByRole("button", { name: "Get Item", exact: true }).click()
	await purchaseOrderEditor.locator(".stock-composer__quantity-grid input").first().fill("2")
	await purchaseOrderEditor.getByRole("button", { name: "OK · Add Item", exact: true }).click()
	await purchaseOrderEditor.locator(".stock-composer__price").getByText("Rate INR 125", { exact: true }).waitFor()
	const purchaseEditorTableFlow = await purchaseOrderEditor.locator(".stock-composer__table-scroll").evaluate((element) => ({
		maxHeight: getComputedStyle(element).maxHeight,
		clientHeight: element.clientHeight,
		scrollHeight: element.scrollHeight,
	}))
	assert(purchaseEditorTableFlow.maxHeight === "none" && purchaseEditorTableFlow.scrollHeight <= purchaseEditorTableFlow.clientHeight + 1, `Purchase Order Added items still uses a nested vertical scroller: ${JSON.stringify(purchaseEditorTableFlow)}`)
	const supplierField = purchaseOrderEditor.locator(".common-field").filter({ hasText: "Supplier *" })
	await selectAutocompleteOption(page, supplierField, "TEST-VALUE")
	const purchaseOrderSourceDialog = page.getByRole("dialog", { name: "Change Supplier?" })
	await purchaseOrderSourceDialog.waitFor()
	await purchaseOrderSourceDialog.getByRole("button", { name: "Keep Current Supplier", exact: true }).click()
	assert(await supplierField.locator(".p-autocomplete-input").inputValue() === "SUPPLIER-001", "Rejected source change discarded the committed supplier")
	await supplierField.locator(".p-autocomplete-input").fill("")
	await supplierField.locator(".p-autocomplete-input").press("Tab")
	let clearSupplierDialog = page.getByRole("dialog", { name: "Clear Supplier?" })
	await clearSupplierDialog.waitFor()
	await clearSupplierDialog.getByRole("button", { name: "Keep Current Supplier", exact: true }).click()
	assert(await supplierField.locator(".p-autocomplete-input").inputValue() === "SUPPLIER-001", "Cancelling a supplier clear did not restore the committed supplier")
	await supplierField.locator(".p-autocomplete-input").fill("")
	await supplierField.locator(".p-autocomplete-input").press("Tab")
	clearSupplierDialog = page.getByRole("dialog", { name: "Clear Supplier?" })
	await clearSupplierDialog.waitFor()
	await clearSupplierDialog.getByRole("button", { name: "Clear Supplier", exact: true }).click()
	assert(await supplierField.locator(".p-autocomplete-input").inputValue() === "", "Confirmed supplier clear restored the old Supplier")
	await purchaseOrderEditor.locator(".stock-composer__price").getByText("Rate INR 0", { exact: true }).first().waitFor()
	assert(await purchaseOrderEditor.getByRole("button", { name: "Save", exact: true }).isDisabled(), "Purchase Order remains saveable without its required Supplier")
	await selectAutocompleteOption(page, supplierField, "SUPPLIER-001")
	const restoreSupplierDialog = page.getByRole("dialog", { name: "Change Supplier?" })
	await restoreSupplierDialog.waitFor()
	await restoreSupplierDialog.getByRole("button", { name: "Change & Reprice", exact: true }).click()
	await purchaseOrderEditor.locator(".stock-composer__price").getByText("Rate INR 125", { exact: true }).first().waitFor()
	assert(purchaseOrderPriceRequests.at(-1)?.supplier === "SUPPLIER-001", `Purchase Order repriced with the wrong Supplier: ${JSON.stringify(purchaseOrderPriceRequests.at(-1))}`)
	assert(await purchaseOrderEditor.getByRole("button", { name: "Save & Submit", exact: true }).count() === 0, "Purchase Order editor still exposes Save & Submit")
	await purchaseOrderEditor.getByRole("button", { name: "Save", exact: true }).click()
	const purchaseSaveError = page.getByRole("dialog", { name: "Purchase Order could not be saved" })
	await purchaseSaveError.getByText("Delivery warehouse is no longer available.", { exact: true }).waitFor()
	assert(await purchaseOrderEditor.locator(".p-message-error").count() === 0, "Purchase Order duplicates the save error inline")
	assert(await page.locator(".p-toast-message-error").count() === 0, "Purchase Order duplicates the save error as a toast")
	assert(await page.getByText("Request failed with status 500", { exact: true }).count() === 0, "Purchase Order hides the server validation behind a generic status")
	await purchaseSaveError.getByRole("button", { name: "OK", exact: true }).click()
	await purchaseOrderEditor.getByRole("button", { name: "Save", exact: true }).click()
	await page.waitForURL("**/web/fabric-store/purchase-orders/PO-FAB-NEW")
	assert(purchaseOrderSave?.submit === false, `Purchase Order editor did not save a Draft first: ${JSON.stringify(purchaseOrderSave)}`)
	assert(purchaseOrderSave?.values?.item_details?.[0]?.items?.[0]?.values?.S?.rate === 125, `Purchase Order did not post the authoritative Item Price: ${JSON.stringify(purchaseOrderSave)}`)
	await page.locator(".fabric-purchase-order-frame").waitFor()
	await page.getByRole("button", { name: "Submit", exact: true }).click()
	await page.getByText("To Receive", { exact: true }).waitFor()
	assert(lifecycleAction === "submit", "Purchase Order saved Draft was not submitted from the form view")

	priceValidationEnabled = false
	resolvedPurchaseOrderPrice = {}
	await page.goto(`${SITE}/web/fabric-store/purchase-orders`, { waitUntil: "domcontentloaded" })
	await page.getByRole("button", { name: "Create Purchase Order", exact: true }).click()
	await page.waitForURL("**/web/fabric-store/purchase-orders/new")
	const zeroPriceEditor = page.locator(".purchase-order-editor")
	await zeroPriceEditor.waitFor()
	const zeroPriceItem = zeroPriceEditor.locator(".stock-composer__fields .common-field").filter({ hasText: "Item *" })
	await selectAutocompleteOption(page, zeroPriceItem, "STYLE-001")
	await zeroPriceEditor.getByRole("button", { name: "Get Item", exact: true }).click()
	await zeroPriceEditor.locator(".stock-composer__quantity-grid input").first().fill("2")
	await zeroPriceEditor.getByRole("button", { name: "OK · Add Item", exact: true }).click()
	await zeroPriceEditor.locator(".stock-composer__price").getByText("Rate INR 0", { exact: true }).first().waitFor()

	priceValidationEnabled = true
	await page.reload({ waitUntil: "domcontentloaded" })
	const strictPriceEditor = page.locator(".purchase-order-editor")
	const strictPriceItem = strictPriceEditor.locator(".stock-composer__fields .common-field").filter({ hasText: "Item *" })
	await selectAutocompleteOption(page, strictPriceItem, "STYLE-001")
	await strictPriceEditor.getByRole("button", { name: "Get Item", exact: true }).click()
	await strictPriceEditor.locator(".stock-composer__quantity-grid input").first().fill("2")
	await strictPriceEditor.getByRole("button", { name: "OK · Add Item", exact: true }).click()
	await strictPriceEditor.locator(".stock-composer__price").getByText("Rate INR 0", { exact: true }).first().waitFor()
	assert(await strictPriceEditor.locator(".stock-composer__tables").count() === 1, "Missing Item Price blocked the Purchase Order while it was still being created")
	assert(await strictPriceEditor.getByText(/No matching Item Price slab was found/).count() === 0, "Missing Item Price validation ran before Purchase Order submission")

	await page.goto(`${SITE}/web/fabric-store/purchase-orders/PO-EDITOR-LOAD-ERROR/edit`, { waitUntil: "domcontentloaded" })
	const failedEditor = page.locator(".purchase-order-editor")
	await failedEditor.getByText("Purchase Order could not be loaded", { exact: true }).waitFor()
	await failedEditor.getByText("Purchase Order editor is temporarily unavailable.", { exact: true }).waitFor()
	assert(await page.getByRole("dialog", { name: "Purchase Order could not be loaded" }).count() === 0, "Failed Purchase Order load duplicates the same error in a popup")
	assert(await failedEditor.locator(".purchase-order-editor__body").count() === 0, "Failed Purchase Order load leaves an unusable empty form visible")
	await failedEditor.getByRole("button", { name: "Retry", exact: true }).click()
	await failedEditor.getByRole("heading", { name: "Edit Purchase Order", exact: true }).waitFor()
	assert(purchaseOrderEditorLoadFailures === 2, `Purchase Order Retry did not reload exactly once: ${purchaseOrderEditorLoadFailures}`)
	return { workspaceLoads, lifecycleAction, purchaseOrderCreated: currentName, purchaseOrderSaveAttempts }
}

async function stockTransfersSuite(page) {
	const listRequests = []
	await mockWorkspace(page, listRequests)
	let savedTransaction = null
	const savedTransactions = []
	await page.route("**/api/method/essdee_yrp.api.link_search.link_search*", (route) => {
		const doctype = requestBody(route).doctype
		const value = doctype === "Item" ? "TEST-ITEM" : doctype === "Warehouse" ? "FABRIC-WH" : "TEST-VALUE"
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: [{ name: value, label: value }] }) })
	})
	await page.route("**/api/method/essdee_yrp.fabric_store.web_workspace.get_stock_operation_editor*", (route) => {
		const operation = requestBody(route).operation || "stock_entry"
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: {
			operation, doctype: capabilities.sections.stock_transfers.operations[operation].doctype,
			dimensions: operation === "lot_transfer" ? [
				{ fieldname: "from_lot", label: "From Lot", options: "SD YRP Lot", mandatory: 1 },
				{ fieldname: "to_lot", label: "To Lot", options: "SD YRP Lot", mandatory: 1 },
				{ fieldname: "warehouse", label: "Warehouse", options: "Warehouse", mandatory: 1 },
				{ fieldname: "received_type", label: "Received Type", options: "YRP Received Type", mandatory: 1 },
			] : operation === "stock_entry" ? [
				{ fieldname: "received_type", label: "Received Type", options: "YRP Received Type", mandatory: 0 },
			] : [],
			default_dimensions: {}, locked_dimensions: [], defaults: { purpose: operation === "stock_reconciliation" ? "Stock Reconciliation" : "", update_type: "" },
			purpose_options: operation === "stock_entry" ? ["Material Issue", "Material Consumed", "Send to Warehouse"] : operation === "stock_reconciliation" ? ["Stock Reconciliation", "Opening Stock"] : [],
			update_type_options: operation === "stock_update" ? ["Add", "Reduce"] : [],
			item_filters: { is_stock_item: 1, disabled: 0 }, permissions: { can_create: true, can_submit: true },
		} }) })
	})
	await page.route("**/api/method/essdee_yrp.fabric_store.web_workspace.get_stock_item_schema*", (route) => {
		const operation = requestBody(route).operation
		return route.fulfill({
			status: 200, contentType: "application/json", body: JSON.stringify({ message: {
				item: "TEST-ITEM", attributes: operation === "stock_reconciliation" ? ["Size"] : [], primary_attribute: operation === "stock_reconciliation" ? "Size" : "", primary_attribute_values: operation === "stock_reconciliation" ? ["S", "M"] : [], default_uom: "Kg", secondary_uom: "", attribute_values: {},
			} }),
		})
	})
	await page.route("**/api/method/essdee_yrp.fabric_store.web_workspace.save_stock_operation*", (route) => {
		savedTransaction = requestBody(route)
		savedTransactions.push(savedTransaction)
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: {
			record: { doctype: "YRP Stock Entry", name: "STE-FAB-NEW", docstatus: 1, status: "Submitted" },
		} }) })
	})
	await page.route("**/api/method/essdee_yrp.fabric_store.web_workspace.get_document*", (route) => route.fulfill({
		status: 200, contentType: "application/json", body: JSON.stringify({ message: {
			record: { doctype: "YRP Stock Entry", name: "STE-FAB-001", docstatus: 0, status: "Draft", modified: "2026-10-03 10:00:00" },
			permissions: { can_read: true, can_submit: true, can_print: true }, details: [], item_groups: [], item_row_count: 0,
			print_formats: [{ label: "Stock Entry", format: "Essdee Stock Entry" }],
		} }),
	}))

	await page.setViewportSize({ width: 1440, height: 900 })
	await page.goto(`${SITE}/web/fabric-store/stock-transfers`, { waitUntil: "domcontentloaded" })
	const transfers = page.locator(".fabric-stock-transfers")
	await transfers.getByRole("button", { name: "Create New", exact: true }).click()
	const entryDialog = page.getByRole("dialog", { name: "Create Stock Entry" })
	await entryDialog.waitFor()
	assert(await entryDialog.locator('input[type="date"], input[type="time"], input[type="datetime-local"]').count() === 0, "Fabric stock editor uses native date/time controls")
	const purpose = entryDialog.locator(".fabric-operation-fields .p-select")
	await purpose.click()
	const purposeOptions = await page.locator(".p-select-overlay:visible .p-select-option").allTextContents()
	assert(JSON.stringify(purposeOptions) === JSON.stringify(["Material Issue", "Material Consumed", "Send to Warehouse"]), `Fabric Stock Entry purpose options differ: ${purposeOptions}`)
	await page.locator(".p-select-overlay:visible .p-select-option").filter({ hasText: "Material Consumed" }).click()
	const receivedType = entryDialog.locator(".stock-composer__fields .common-field").filter({ hasText: "Received Type" }).locator("input")
	assert(await receivedType.isEnabled(), "Material Consumed incorrectly locks the required Received Type dimension")
	await purpose.click()
	await page.locator(".p-select-overlay:visible .p-select-option").filter({ hasText: "Material Issue" }).click()
	const warehouseField = entryDialog.locator(".fabric-operation-fields .common-field").filter({ hasText: "From warehouse *" })
	await selectAutocompleteOption(page, warehouseField, "FABRIC-WH")
	const itemField = entryDialog.locator(".stock-composer__fields .common-field").filter({ hasText: "Item *" })
	await selectAutocompleteOption(page, itemField, "TEST-ITEM")
	await entryDialog.getByRole("button", { name: "Get Item", exact: true }).click()
	const quantity = entryDialog.locator(".stock-composer__single-quantity input").first()
	await quantity.fill("2")
	await entryDialog.getByRole("button", { name: "OK · Add Item", exact: true }).click()
	await entryDialog.getByRole("button", { name: "Save options", exact: true }).click()
	await page.getByRole("menuitem", { name: "Save & Submit", exact: true }).click()
	await entryDialog.waitFor({ state: "hidden" })
	assert(savedTransaction?.operation === "stock_entry" && savedTransaction?.submit === true, `Fabric Stock Entry save payload is wrong: ${JSON.stringify(savedTransaction)}`)

	await transfers.locator(".premium-list-table").getByText("STE-FAB-001", { exact: true }).click()
	const existingEditor = page.getByRole("dialog", { name: /Edit Stock Entry.*STE-FAB-001/ })
	await existingEditor.waitFor()
	await existingEditor.locator(".p-dialog-close-button").click()

	await transfers.getByRole("button", { name: /Stock Reconciliation/ }).click()
	await transfers.getByRole("button", { name: "Create New", exact: true }).click()
	const reconciliationDialog = page.getByRole("dialog", { name: "Create Stock Reconciliation" })
	await reconciliationDialog.waitFor()
	const reconciliationWarehouse = reconciliationDialog.locator(".fabric-operation-fields .common-field").filter({ hasText: "Warehouse *" })
	await selectAutocompleteOption(page, reconciliationWarehouse, "FABRIC-WH")
	const reconciliationItem = reconciliationDialog.locator(".stock-composer__fields .common-field").filter({ hasText: "Item *" })
	await selectAutocompleteOption(page, reconciliationItem, "TEST-ITEM")
	await reconciliationDialog.getByRole("button", { name: "Get Item", exact: true }).click()
	const countedCells = reconciliationDialog.locator(".stock-composer__quantity-grid input")
	await countedCells.first().fill("0")
	await reconciliationDialog.getByRole("button", { name: "OK · Add Item", exact: true }).click()
	await reconciliationDialog.getByRole("button", { name: "Save", exact: true }).click()
	await reconciliationDialog.waitFor({ state: "hidden" })
	const reconciliationSave = savedTransactions.findLast((entry) => entry.operation === "stock_reconciliation")
	const reconciliationValues = reconciliationSave?.values?.item_details?.[0]?.items?.[0]?.values || {}
	assert(Object.keys(reconciliationValues).length === 1 && Object.hasOwn(reconciliationValues, "S") && reconciliationValues.S.qty === 0, `Untouched reconciliation cells were posted: ${JSON.stringify(reconciliationSave)}`)

	await transfers.getByRole("button", { name: /Stock Update/ }).click()
	await transfers.getByRole("button", { name: "Create New", exact: true }).click()
	const updateDialog = page.getByRole("dialog", { name: "Create Stock Update" })
	await updateDialog.waitFor()
	await updateDialog.locator(".fabric-operation-fields .p-select").click()
	const updateOptions = await page.locator(".p-select-overlay:visible .p-select-option").allTextContents()
	assert(JSON.stringify(updateOptions) === JSON.stringify(["Add", "Reduce"]), `Fabric Stock Update options differ: ${updateOptions}`)
	await page.keyboard.press("Escape")
	await updateDialog.locator(".p-dialog-close-button").click()

	await transfers.getByRole("button", { name: /Lot Transfer/ }).click()
	await transfers.getByRole("button", { name: "Create New", exact: true }).click()
	const lotDialog = page.getByRole("dialog", { name: "Create Lot Transfer" })
	await lotDialog.waitFor()
	assert(await lotDialog.getByText("From Lot *", { exact: true }).count() === 1, "Context-free Lot Transfer is missing From Lot")
	assert(await lotDialog.getByText("To Lot *", { exact: true }).count() === 1, "Context-free Lot Transfer is missing To Lot")
	assert(await lotDialog.getByText("Warehouse *", { exact: true }).count() === 1, "Context-free Lot Transfer is missing Warehouse")
	for (const label of ["From Lot *", "To Lot *", "Warehouse *", "Received Type *"]) {
		const field = lotDialog.locator(".stock-composer__fields .common-field").filter({ hasText: label })
		await selectAutocompleteOption(page, field, label.includes("Warehouse") ? "FABRIC-WH" : "TEST-VALUE")
	}
	const lotItem = lotDialog.locator(".stock-composer__fields .common-field").filter({ hasText: "Item *" })
	await selectAutocompleteOption(page, lotItem, "TEST-ITEM")
	await lotDialog.getByRole("button", { name: "Get Item", exact: true }).click()
	await lotDialog.locator(".stock-composer__single-quantity input").first().fill("2")
	await lotDialog.getByRole("button", { name: "OK · Add Item", exact: true }).click()
	await lotDialog.getByRole("button", { name: "Save", exact: true }).click()
	await lotDialog.waitFor({ state: "hidden" })
	const lotSave = savedTransactions.findLast((entry) => entry.operation === "lot_transfer")
	const lotRow = lotSave?.values?.item_details?.[0]?.items?.[0] || {}
	for (const key of ["from_lot", "to_lot", "warehouse", "received_type"]) assert(lotRow[key], `Lot Transfer omitted ${key}: ${JSON.stringify(lotSave)}`)
	return { purposeOptions, updateOptions }
}

async function documentDialogSuite(page) {
	const componentPath = "frontend/src/components/documents/DocumentTransactionDialog.vue"
	assert(existsSync(componentPath), "Common document transaction dialog is missing")
	assert(readFileSync(componentPath, "utf8").includes("closeConfirmationVisible"), "Editable dialogs have no dirty-close confirmation")
	await mockWorkspace(page, [])
	rows["YRP Stock Entry"].docstatus = 1
	let documentPayload = {
		record: { doctype: "YRP Stock Entry", name: "STE-FAB-001", docstatus: 1, status: "Submitted", modified: "2026-10-03 10:00:00" },
		details: [{ fieldname: "purpose", label: "Purpose", fieldtype: "Select", value: "Material Issue" }],
		item_groups: [workOrderGroup()], item_row_count: 2,
		permissions: { can_read: true, can_write: false, can_submit: false, can_cancel: true, can_amend: false, can_print: true },
		print_formats: [{ label: "Standard Print", format: "Standard" }],
	}
	let lifecycleAction = ""
	await page.route("**/api/method/essdee_yrp.fabric_store.web_workspace.get_document*", (route) => route.fulfill({
		status: 200, contentType: "application/json", body: JSON.stringify({ message: documentPayload }),
	}))
	await page.route("**/api/method/essdee_yrp.fabric_store.web_workspace.change_document_status*", (route) => {
		lifecycleAction = requestBody(route).action
		documentPayload = {
			...documentPayload,
			record: { ...documentPayload.record, docstatus: 2, status: "Cancelled", modified: "2026-10-03 10:05:00" },
			permissions: { ...documentPayload.permissions, can_cancel: false, can_amend: true },
		}
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: documentPayload }) })
	})

	await page.goto(`${SITE}/web/fabric-store/stock-transfers`, { waitUntil: "domcontentloaded" })
	await page.locator(".premium-list-table").getByText("STE-FAB-001", { exact: true }).click()
	const dialog = page.getByRole("dialog", { name: /YRP Stock Entry.*STE-FAB-001/ })
	await dialog.waitFor()
	assert(await dialog.locator(".p-dialog-content").evaluate((element) => ["auto", "scroll"].includes(getComputedStyle(element).overflowY)), "Document dialog does not have a single scroll-contained content owner")
	assert(await dialog.locator(".document-transaction-dialog__content").evaluate((element) => getComputedStyle(element).overflowY === "visible"), "Document dialog content still creates a nested vertical scrollbar")
	assert(await dialog.getByRole("button", { name: "Submit", exact: true }).count() === 0, "Submitted document exposes Submit")
	assert(await dialog.getByRole("button", { name: "Cancel Document", exact: true }).count() === 1, "Submitted Cancel action is missing")
	assert(await dialog.getByRole("button", { name: "Print", exact: true }).count() === 1, "Permitted Print action is missing")
	await dialog.getByRole("button", { name: "Cancel Document", exact: true }).click()
	const cancelConfirmation = page.getByRole("alertdialog", { name: "Cancel YRP Stock Entry?" })
	await cancelConfirmation.waitFor()
	const keepDocumentButton = cancelConfirmation.getByRole("button", { name: "Keep Document", exact: true })
	assert(await keepDocumentButton.evaluate((element) => element === document.activeElement), "Document cancellation confirmation does not focus its safe action")
	assert(lifecycleAction === "", "Document cancellation ran before confirmation")
	await cancelConfirmation.getByRole("button", { name: "Cancel Document", exact: true }).click()
	await dialog.getByText("Cancelled", { exact: true }).waitFor()
	assert(lifecycleAction === "cancel", `Unexpected lifecycle action: ${lifecycleAction}`)
	assert(await dialog.getByRole("button", { name: "Amend", exact: true }).count() === 1, "Cancelled Amend action is missing")

	return { lifecycleAction }
}

async function documentsSuite(page) {
	const shellPath = "frontend/src/departments/fabric-store/FabricDocumentWorkspace.vue"
	const hostPath = "frontend/src/departments/fabric-store/RelatedDocumentWorkspaceDialog.vue"
	const deliveryPath = "frontend/src/departments/FabricDeliveryChallan.vue"
	const receiptPath = "frontend/src/departments/FabricGoodsReceivedNote.vue"
	for (const path of [shellPath, hostPath, deliveryPath, receiptPath]) {
		assert(existsSync(path), `Reusable document workspace file is missing: ${path}`)
	}

	const routerSource = readFileSync("frontend/src/router/index.js", "utf8")
	for (const path of [
		"/fabric-store/delivery-challans/new",
		"/fabric-store/delivery-challans/:deliveryChallanId",
		"/fabric-store/goods-received-notes/new",
		"/fabric-store/goods-received-notes/:goodsReceivedNoteId",
	]) assert(routerSource.includes(path), `Fabric document route is missing: ${path}`)

	const shellSource = readFileSync(shellPath, "utf8")
	for (const slot of ["header", "fields", "matrix", "rail", "panel"]) {
		assert(shellSource.includes(`name="${slot}"`), `Fabric document shell is missing the ${slot} slot`)
	}
	assert(shellSource.includes("discardVisible"), "Fabric document shell has no unsaved-change confirmation")

	const hostSource = readFileSync(hostPath, "utf8")
	assert(hostSource.includes("maximizable"), "Related document host is not maximizable")
	assert(!/(router\.(push|replace)|window\.location|<iframe)/.test(hostSource), "Related document host can navigate away from its parent")
	assert(hostSource.includes("FabricDeliveryChallan") && hostSource.includes("FabricGoodsReceivedNote"), "Related document host does not reuse both routed domain components")

	const deliverySource = readFileSync(deliveryPath, "utf8")
	const receiptSource = readFileSync(receiptPath, "utf8")
	assert(deliverySource.includes("delivery-challan-workspace"), "Delivery Challan lacks a shared domain root")
	assert(receiptSource.includes("goods-received-note-workspace"), "Goods Received Note lacks a shared domain root")

	const basePayload = {
		fields: [{ fieldname: "posting_date", label: "Posting Date", fieldtype: "Date", value: "2026-10-06", read_only: true }],
		totals: [{ fieldname: "total_quantity", label: "Total Quantity", value: 12 }],
		permissions: { can_read: true, can_write: false, can_submit: false, can_cancel: false, can_amend: false, can_print: false },
		capabilities: {}, print_formats: [], matrices: {}, related: {},
	}
	await page.route("**/api/method/essdee_yrp.fabric_store.web_workspace.get_delivery_challan_workspace*", (route) => route.fulfill({
		status: 200, contentType: "application/json", body: JSON.stringify({ message: {
			...basePayload,
			record: { doctype: "YRP Delivery Challan", name: "DC-FAB-001", docstatus: 0, status: "Draft", modified: "2026-10-06 10:00:00" },
		} }),
	}))
	await page.route("**/api/method/essdee_yrp.fabric_store.web_workspace.get_goods_received_note_workspace*", (route) => route.fulfill({
		status: 200, contentType: "application/json", body: JSON.stringify({ message: {
			...basePayload,
			record: { doctype: "YRP Goods Received Note", name: "GRN-FAB-001", docstatus: 0, status: "Draft", modified: "2026-10-06 10:00:00" },
		} }),
	}))

	await page.goto(`${SITE}/web/fabric-store/delivery-challans/DC-FAB-001`, { waitUntil: "domcontentloaded" })
	const deliveryRoot = page.locator(".delivery-challan-workspace")
	await deliveryRoot.waitFor({ timeout: 20_000 })
	assert(await deliveryRoot.getByRole("button", { name: "Submit", exact: true }).count() === 0, "Unauthorized Delivery Challan Submit is rendered")

	await page.goto(`${SITE}/web/fabric-store/goods-received-notes/GRN-FAB-001`, { waitUntil: "domcontentloaded" })
	const receiptRoot = page.locator(".goods-received-note-workspace")
	await receiptRoot.waitFor({ timeout: 20_000 })
	assert(await receiptRoot.getByRole("button", { name: "Submit", exact: true }).count() === 0, "Unauthorized Goods Received Note Submit is rendered")

	return { routes: ["delivery-challan", "goods-received-note"], sharedEmbeddedComponents: true }
}

async function deliveryChallanSuite(page) {
	const componentPath = "frontend/src/departments/fabric-store/DeliveryChallanWorkspace.vue"
	const returnPath = "frontend/src/departments/fabric-store/DeliveryChallanReturnPanel.vue"
	const routePath = "frontend/src/departments/FabricDeliveryChallan.vue"
	const hostPath = "frontend/src/departments/fabric-store/RelatedDocumentWorkspaceDialog.vue"
	const workOrderPath = "frontend/src/departments/FabricWorkOrder.vue"
	const purchaseOrderPath = "frontend/src/departments/FabricPurchaseOrder.vue"
	for (const path of [componentPath, returnPath, routePath, hostPath, workOrderPath, purchaseOrderPath]) {
		assert(existsSync(path), `Complete Delivery Challan workspace file is missing: ${path}`)
	}
	const componentSource = readFileSync(componentPath, "utf8")
	const routeSource = readFileSync(routePath, "utf8")
	const hostSource = readFileSync(hostPath, "utf8")
	assert(componentSource.includes("delivery-challan-workspace"), "Delivery Challan domain component lacks its stable root")
	assert(routeSource.includes("DeliveryChallanWorkspace"), "Delivery Challan route does not use the complete domain component")
	assert(hostSource.includes("FabricDeliveryChallan"), "Embedded host does not reuse the routed Delivery Challan component")
	assert(!/(router\.(push|replace)|window\.location|<iframe)/.test(hostSource), "Delivery Challan popup host can navigate away from its parent")
	for (const parentPath of [workOrderPath, purchaseOrderPath]) {
		const source = readFileSync(parentPath, "utf8")
		assert(source.includes('@changed="relatedChanged"'), `${parentPath} does not refresh after a related Delivery Challan mutation`)
	}

	const normalGroup = {
		attributes: ["Colour"], primary_attribute: "Size", primary_attribute_values: ["S", "M"],
		items: [{
			name: "FABRIC-001", attributes: { Colour: "Navy" }, dimensions: { lot: "LOT-001", received_type: "Accepted" },
			values: {
				S: { qty: 4, pending_qty: 6, secondary_qty: 2, secondary_uom: "Roll" },
				M: { qty: 3, pending_qty: 5, secondary_qty: 0, secondary_uom: "Roll" },
			},
			default_uom: "Kg", row_index: 0, item_variant: "FABRIC-001-NAVY", total_qty: 7,
		}],
	}
	const correctionGroup = structuredClone(normalGroup)
	correctionGroup.items[0].name = "FABRIC-CORRECTION"
	correctionGroup.items[0].item_variant = "FABRIC-CORRECTION-NAVY"
	correctionGroup.items[0].values.S.qty = 1
	const noSecondaryGroup = structuredClone(normalGroup)
	noSecondaryGroup.items[0].name = "FABRIC-WITHOUT-SECONDARY"
	for (const value of Object.values(noSecondaryGroup.items[0].values)) {
		delete value.secondary_qty
		delete value.secondary_uom
	}
	const fields = [
		{ fieldname: "work_order", label: "Work Order", fieldtype: "Link", options: "YRP Work Order", value: "WO-FAB-001", reqd: true },
		{ fieldname: "posting_date", label: "Posting Date", fieldtype: "Date", value: "2026-10-06", reqd: true, read_only_depends_on: "eval: !doc.edit_posting_date_and_time" },
		{ fieldname: "posting_time", label: "Posting Time", fieldtype: "Time", value: "10:30:00.123456", reqd: true, read_only_depends_on: "eval: !doc.edit_posting_date_and_time" },
		{ fieldname: "edit_posting_date_and_time", label: "Edit Posting Date and Time", fieldtype: "Check", value: 0, depends_on: "eval:doc.docstatus==0" },
		{ fieldname: "from_location", label: "From Location", fieldtype: "Link", options: "Supplier", value: "" },
		{ fieldname: "supplier", label: "Receiver", fieldtype: "Link", options: "Supplier", value: "CUTTING-UNIT" },
		{ fieldname: "from_warehouse", label: "From Warehouse", fieldtype: "Link", options: "Warehouse", value: "" },
		{ fieldname: "to_warehouse", label: "To Warehouse", fieldtype: "Link", options: "Warehouse", value: "CUTTING-WH" },
		{ fieldname: "from_address", label: "From Address", fieldtype: "Link", options: "Address", value: "" },
		{ fieldname: "supplier_address", label: "Receiver Address", fieldtype: "Link", options: "Address", value: "CUTTING-UNIT-Billing" },
		{ fieldname: "supplier_address_details", label: "Receiver Address Details", fieldtype: "Small Text", value: "Line one<br>Line two", read_only: true },
		{ fieldname: "vehicle_no", label: "Vehicle No", fieldtype: "Data", value: "TN-01-AA-1001" },
		{ fieldname: "comments", label: "Comments", fieldtype: "Small Text", value: "" },
		{ fieldname: "allow_non_bundle", label: "Allow Non Bundle", fieldtype: "Check", value: 0 },
		{ fieldname: "is_rework", label: "Is Rework", fieldtype: "Check", value: 0 },
		{ fieldname: "includes_packing", label: "Includes Packing", fieldtype: "Check", value: 0 },
		{ fieldname: "additional_goods_value", label: "Additional Goods Value", fieldtype: "Currency", value: 15 },
		{ fieldname: "is_internal_unit", label: "Is Internal Unit", fieldtype: "Check", value: 0 },
		{ fieldname: "transfer_complete", label: "Transfer Complete", fieldtype: "Check", value: 0 },
		{ fieldname: "ste_transferred", label: "STE Transferred", fieldtype: "Float", value: 0, read_only: true },
		{ fieldname: "ste_transferred_percent", label: "STE Transferred (%)", fieldtype: "Percent", value: 0, read_only: true },
	]
	const draftPayload = (name = null) => ({
		record: {
			doctype: "YRP Delivery Challan", name, docstatus: 0, status: "Draft", modified: name ? "2026-10-06 10:45:00" : null,
			work_order: "WO-FAB-001", process_name: "Knitting", item: "FABRIC-001", lot: "LOT-001", supplier: "CUTTING-UNIT",
		},
		fields: structuredClone(fields), values: Object.fromEntries(fields.map((field) => [field.fieldname, field.value])),
		totals: [
			{ fieldname: "total_delivered_qty", label: "Total Delivered Quantity", value: 8 },
			{ fieldname: "stock_value", label: "Stock Value", value: 420.5 },
			{ fieldname: "additional_goods_value", label: "Additional Goods Value", value: 15 },
			{ fieldname: "total_value", label: "Total Value", value: 435.5 },
		],
		matrices: {
			items: [structuredClone(normalGroup), structuredClone(noSecondaryGroup)],
			correction_items: [{ work_order_correction: "WOC-001", title: "Correction WOC-001", item_details: [structuredClone(correctionGroup)] }],
		},
		dimensions: [{ fieldname: "received_type", label: "Received Type", fieldtype: "Link", options: "YRP Received Type", value: "Accepted", locked: false }],
		permissions: { can_read: true, can_create: !name, can_write: Boolean(name), can_submit: true, can_cancel: false, can_amend: false, can_print: false },
		capabilities: { save: { label: "Save" }, submit: { label: "Submit" } },
		return_context: {}, special_source: { active: false, modes: [], read_only: false }, related: {}, print_formats: [],
	})
	const submittedPayload = (transferComplete = false) => ({
		...draftPayload("DC-FAB-001"),
		record: {
			...draftPayload("DC-FAB-001").record, docstatus: 1, status: "Submitted", is_internal_unit: 1,
			transfer_complete: transferComplete ? 1 : 0, ste_transferred_percent: transferComplete ? 100 : 45,
		},
		permissions: { can_read: true, can_write: false, can_submit: false, can_cancel: true, can_amend: false, can_print: true },
		capabilities: {
			cancel: { label: "Cancel" }, return: { label: "Return" },
			...(transferComplete ? {} : { complete_transfer: { label: "Complete Transfer" } }),
		},
		return_context: {
			has_received_type: true, default_received_type: "Accepted",
			items: [{ delivery_challan_item: "DCI-001", item_variant: "FABRIC-001-NAVY", uom: "Kg", delivered_quantity: 8, consumed_quantity: 2, already_returned: 1, returnable_quantity: 5, return_quantity: 0 }],
			variants: { normal: true, whole_bundle: true, cut_panel_movement_filters: { docstatus: 1, lot: "LOT-001", against_id: ["is", "not set"] } },
		},
	})
	const restrictedPayload = {
		...draftPayload("DC-RESTRICTED"),
		permissions: { can_read: true, can_write: false, can_submit: false, can_cancel: false, can_amend: false, can_print: false },
		capabilities: {},
	}
	const specialPayload = {
		...draftPayload("DC-SPECIAL"),
		special_source: { active: true, modes: ["cut_panel_movement", "pack_piece_dc"], read_only: true },
	}

	let sourcePreviewCalls = 0
	let saveCalls = 0
	let savePayload = null
	let parentLoads = 0
	let command = null
	let loadRetryCalls = 0
	const linkSearchRequests = []
	const linkedDocumentRequests = []
	await page.route("**/api/method/essdee_yrp.api.link_search.link_search*", (route) => {
		const body = requestBody(route)
		linkSearchRequests.push(body)
		const name = body.doctype === "YRP Work Order" ? "WO-FAB-002" : body.doctype === "YRP Received Type" ? "Accepted" : body.doctype === "Supplier" ? "FABRIC-STORE" : body.doctype === "Warehouse" ? "FABRIC-WH" : "TEST-VALUE"
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: [{ name, label: name }] }) })
	})
	await page.route("**/api/method/essdee_yrp.api.link_search.linked_document_search*", (route) => {
		const body = requestBody(route)
		linkedDocumentRequests.push(body)
		const name = `${body.link_name}-Billing`
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: [{ name, label: name }] }) })
	})
	await page.route("**/api/method/essdee_yrp.fabric_store.web_workspace.get_delivery_challan_workspace*", (route) => {
		const name = requestBody(route).name || ""
		if (name === "DC-LOAD-ERROR") {
			loadRetryCalls += 1
			if (loadRetryCalls === 1) return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ exc: "ValidationError", message: "Delivery Challan could not be loaded." }) })
		}
		const payload = name === "DC-FAB-001" ? submittedPayload() : name === "DC-LOAD-ERROR" ? draftPayload(name) : name === "DC-RESTRICTED" ? restrictedPayload : name === "DC-SPECIAL" ? specialPayload : draftPayload()
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: payload }) })
	})
	await page.route("**/api/method/essdee_yrp.fabric_store.web_workspace.preview_delivery_challan_source*", (route) => {
		sourcePreviewCalls += 1
		const payload = draftPayload()
		payload.record.work_order = "WO-FAB-002"
		payload.values.work_order = "WO-FAB-002"
		payload.fields.find((field) => field.fieldname === "work_order").value = "WO-FAB-002"
		payload.matrices.items[0].items[0].values.S.qty = 2
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: payload }) })
	})
	await page.route("**/api/method/essdee_yrp.fabric_store.web_workspace.save_delivery_challan*", (route) => {
		saveCalls += 1
		savePayload = requestBody(route)
		if (saveCalls === 1) return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ exc: "ValidationError", message: "Stock is no longer available." }) })
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: draftPayload("DC-NEW") }) })
	})
	await page.route("**/api/method/essdee_yrp.fabric_store.web_workspace.execute_delivery_challan_command*", (route) => {
		command = requestBody(route)
		const message = command.command === "complete_transfer"
			? { workspace: submittedPayload(true), created: { doctype: "YRP Stock Entry", name: "STE-COMPLETE-001" } }
			: command.command === "return"
				? { workspace: submittedPayload(), created: { doctype: "YRP Goods Received Note", name: "GRN-RETURN-001" } }
			: submittedPayload()
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message }) })
	})
	await page.route("**/api/method/essdee_yrp.fabric_store.web_workspace.get_goods_received_note_workspace*", (route) => route.fulfill({
		status: 200, contentType: "application/json", body: JSON.stringify({ message: {
			record: { doctype: "YRP Goods Received Note", name: requestBody(route).name, docstatus: 0, status: "Draft", modified: "2026-10-06 12:10:00" },
			fields: [], values: {}, totals: [], matrices: {}, dimensions: [], permissions: { can_read: true, can_write: true, can_submit: false }, capabilities: {}, special_source: { active: false }, inspection: {}, related: {}, print_formats: [],
		} }),
	}))
	await page.route("**/api/method/essdee_yrp.fabric_store.web_workspace.get_stock_operation_editor*", (route) => {
		const body = requestBody(route)
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: {
			operation: "stock_entry", doctype: "YRP Stock Entry", name: body.name, modified: "2026-10-06 12:00:00",
			defaults: { purpose: "DC Completion", from_warehouse: "FABRIC-WH", to_warehouse: "UNIT-WH" },
			purpose_options: ["DC Completion", "Send to Warehouse"], dimensions: [], default_dimensions: {}, locked_dimensions: [], item_filters: {},
			item_groups: [structuredClone(normalGroup)], purpose_locked: true, protected_completion: true, permissions: { can_write: true, can_submit: true },
		} }) })
	})
	await page.route("**/api/method/essdee_yrp.fabric_store.web_workspace.get_work_order_workspace*", (route) => {
		parentLoads += 1
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: {
			record: { doctype: "YRP Work Order", name: "WO-FAB-001", docstatus: 1, status: "Open", process_name: "Knitting", item: "FABRIC-001", lot: "LOT-001", modified: "2026-10-06 09:00:00" },
			fields: [], details: [], totals: [], matrices: { deliverables: [], receivables: [] }, summary: {}, related: { delivery_challans: [], goods_received_notes: [] },
			permissions: { can_read: true, can_write: false, can_print: false }, related_permissions: { delivery_challan: { can_read: true, can_create: true }, goods_received_note: { can_read: true, can_create: false } },
			capabilities: { create_delivery_challan: { label: "Make DC", source_context: { work_order: "WO-FAB-001" } } }, print_formats: [],
		} }) })
	})

	await page.setViewportSize({ width: 1600, height: 1000 })
	await page.goto(`${SITE}/web/fabric-store/delivery-challans/new?work_order=WO-FAB-001`, { waitUntil: "domcontentloaded" })
	const draftRoot = page.locator(".delivery-challan-workspace")
	await draftRoot.waitFor({ timeout: 20_000 })
	await draftRoot.locator('.delivery-challan-field-group[data-group="document"]').waitFor({ timeout: 20_000 })
	assert(await draftRoot.locator('.delivery-challan-field-group[data-group="document"]').count() === 1, "Delivery Challan document fields are not grouped")
	assert(await draftRoot.locator('.delivery-challan-field-group[data-group="movement"]').count() === 1, "Delivery Challan movement fields are not grouped")
	assert(await draftRoot.locator('.delivery-challan-field-group[data-group="document"]').getByText("Allow Non Bundle", { exact: true }).count() === 1, "Allow Non Bundle is not kept in Document & posting")
	const dcMovementLabels = (await draftRoot.locator('.delivery-challan-field-group[data-group="movement"] .form-field__label').allTextContents()).map((label) => label.replace("*", "").trim())
	assert(JSON.stringify(dcMovementLabels.slice(0, 6)) === JSON.stringify(["From Location", "From Warehouse", "From Address", "Receiver", "To Warehouse", "Receiver Address"]), `Delivery Challan route fields do not follow their dependencies: ${JSON.stringify(dcMovementLabels)}`)
	const fromWarehouseField = draftRoot.locator(".form-field").filter({ hasText: "From Warehouse" })
	const fromAddressField = draftRoot.locator(".form-field").filter({ hasText: "From Address" })
	const requiredLinkField = draftRoot.locator(".form-field").filter({ hasText: "Work Order" })
	assert(await requiredLinkField.locator(".p-autocomplete-input").getAttribute("aria-required") === "true", "Required link fields do not expose their required state")
	assert(Boolean(await fromWarehouseField.locator(".p-autocomplete-dropdown").getAttribute("aria-label")), "Link-field dropdown trigger has no accessible name")
	assert(await fromWarehouseField.locator(".p-autocomplete-input").isDisabled(), "From Warehouse is enabled before From Location is selected")
	assert(await fromAddressField.locator(".p-autocomplete-input").isDisabled(), "From Address is enabled before From Location is selected")
	await selectAutocompleteOption(page, draftRoot.locator(".form-field").filter({ hasText: "From Location" }), "FABRIC-STORE")
	assert(!await fromWarehouseField.locator(".p-autocomplete-input").isDisabled(), "From Warehouse remains disabled after selecting From Location")
	await selectAutocompleteOption(page, fromWarehouseField, "FABRIC-WH")
	await selectAutocompleteOption(page, fromAddressField, "FABRIC-STORE-Billing")
	const warehouseRequest = linkSearchRequests.find((body) => body.doctype === "Warehouse")
	assert(warehouseRequest?.filters?.supplier === "FABRIC-STORE" && Number(warehouseRequest?.filters?.disabled) === 0, `From Warehouse was not filtered by From Location: ${JSON.stringify(warehouseRequest)}`)
	const addressRequest = linkedDocumentRequests.find((body) => body.doctype === "Address")
	assert(addressRequest?.link_doctype === "Supplier" && addressRequest?.link_name === "FABRIC-STORE", `From Address was not filtered by From Location: ${JSON.stringify(addressRequest)}`)
	const workOrderPopupPromise = page.waitForEvent("popup")
	await draftRoot.getByRole("button", { name: "Open WO-FAB-001", exact: true }).click()
	const workOrderPopup = await workOrderPopupPromise
	await workOrderPopup.waitForLoadState("domcontentloaded").catch(() => {})
	assert(new URL(workOrderPopup.url()).pathname === "/web/fabric-store/work-orders/WO-FAB-001", `Work Order link escaped the web app: ${workOrderPopup.url()}`)
	await workOrderPopup.close()
	const unavailablePopupPromise = page.waitForEvent("popup")
	await draftRoot.getByRole("button", { name: "Open FABRIC-STORE", exact: true }).first().click()
	const unavailablePopup = await unavailablePopupPromise
	await unavailablePopup.waitForLoadState("domcontentloaded").catch(() => {})
	const unavailableUrl = new URL(unavailablePopup.url())
	assert(unavailableUrl.pathname === "/web/document-unavailable" && unavailableUrl.searchParams.get("doctype") === "Supplier", `Unsupported link escaped the web app: ${unavailablePopup.url()}`)
	await unavailablePopup.close()
	assert(await draftRoot.locator(".delivery-challan-matrix--items").count() === 1, "Delivery Challan normal matrix is missing")
	assert(await draftRoot.locator(".delivery-challan-matrix--corrections").count() === 1, "Delivery Challan correction matrix is missing")
	assert(await draftRoot.getByText(/Pending/, { exact: true }).count() >= 1, "Delivery Challan matrix does not expose pending quantities")
	const secondaryGroup = draftRoot.locator(".delivery-challan-matrix__group").filter({ hasText: "FABRIC-001" }).first()
	const noSecondarySection = draftRoot.locator(".delivery-challan-matrix__group").filter({ hasText: "FABRIC-WITHOUT-SECONDARY" })
	assert(await secondaryGroup.locator(".delivery-challan-matrix__secondary-inline").count() === 2, "Delivery Challan hides actual secondary-UOM inputs")
	assert(await noSecondarySection.locator(".delivery-challan-matrix__secondary-inline, .delivery-challan-matrix__secondary").count() === 0, "Delivery Challan shows Secondary inputs for an item without a secondary UOM")
	assert(await draftRoot.getByLabel("Posting Date", { exact: true }).count() === 1, "Delivery Challan editable headers are missing")
	assert(await draftRoot.getByLabel("Posting Date", { exact: true }).isDisabled(), "Posting Date ignores its effective read-only dependency")
	const postingToggle = draftRoot.locator(".form-field").filter({ hasText: "Edit Posting Date and Time" }).locator(".p-toggleswitch")
	await postingToggle.click()
	assert(!await draftRoot.getByLabel("Posting Date", { exact: true }).isDisabled(), "Posting Date remains disabled after its dependency is enabled")
	assert(await draftRoot.locator(".form-field").filter({ hasText: "Received Type" }).count() === 0, "Delivery Challan still shows the global Received Type field")
	assert(await draftRoot.getByLabel("Posting Time", { exact: true }).inputValue() === "10:30:00", "Delivery Challan does not display Frappe's fractional posting time")
	assert(await draftRoot.locator(".delivery-challan-matrix__group > header span").count() === 0, "Delivery Challan repeats Lot below every item title")
	const dcTail = draftRoot.locator(".delivery-challan-after-matrix")
	assert(await dcTail.count() === 1, "Delivery Challan final fields are not placed below Delivery quantities")
	for (const label of ["Is Internal Unit", "Includes Packing", "Additional Goods Value", "STE Transferred", "STE Transferred (%)", "Is Rework"]) {
		assert(await dcTail.getByText(label, { exact: true }).count() === 1, `Delivery Challan final field is missing: ${label}`)
	}
	assert(await draftRoot.locator('.delivery-challan-field-group[data-group="transfer"]').getByText("STE Transferred (%)", { exact: true }).count() === 0, "Delivery Challan still places STE Transferred (%) above the table")
	const dcMatrixBox = await draftRoot.locator(".fabric-document-workspace__matrix").boundingBox()
	const dcTailBox = await dcTail.boundingBox()
	assert(dcMatrixBox && dcTailBox && dcTailBox.y >= dcMatrixBox.y + dcMatrixBox.height, `Delivery Challan final fields are not below the table: ${JSON.stringify({ dcMatrixBox, dcTailBox })}`)
	assert(await draftRoot.locator(".form-field").filter({ hasText: "Receiver Address Details" }).locator("textarea").inputValue() === "Line one\nLine two", "Delivery Challan address details expose raw <br> tags")
	assert(await draftRoot.locator(".delivery-challan-total--primary").filter({ hasText: "Total Delivered Quantity" }).count() === 1, "Delivered quantity is not highlighted")
	assert(await draftRoot.locator(".delivery-challan-total--primary").filter({ hasText: "Stock Value" }).count() === 1, "Stock value is not highlighted")

	await page.setViewportSize({ width: 900, height: 760 })
	const tabletRail = await draftRoot.locator(".fabric-document-workspace__rail").boundingBox()
	const tabletMain = await draftRoot.locator(".fabric-document-workspace__main").boundingBox()
	const tabletHeader = await draftRoot.locator(".fabric-document-workspace__header").boundingBox()
	assert(tabletRail && tabletMain && tabletMain.y < tabletRail.y, `New Delivery Challan front-loads totals before its tablet form: ${JSON.stringify({ tabletRail, tabletMain })}`)
	assert(tabletHeader?.height <= 76, `Delivery Challan header wraps unnecessarily at tablet width: ${JSON.stringify(tabletHeader)}`)
	await page.setViewportSize({ width: 390, height: 844 })
	const mobileRail = await draftRoot.locator(".fabric-document-workspace__rail").evaluate((element) => ({ tabIndex: element.tabIndex, maskImage: getComputedStyle(element).maskImage }))
	const mobileNewRailBox = await draftRoot.locator(".fabric-document-workspace__rail").boundingBox()
	const mobileNewMainBox = await draftRoot.locator(".fabric-document-workspace__main").boundingBox()
	assert(mobileNewMainBox && mobileNewRailBox && mobileNewMainBox.y < mobileNewRailBox.y && mobileRail.tabIndex === -1 && mobileRail.maskImage === "none", `New Delivery Challan totals should follow the form instead of using the existing-document ribbon: ${JSON.stringify({ mobileNewMainBox, mobileNewRailBox, mobileRail })}`)
	const mobileFacts = await draftRoot.locator(".delivery-challan-header__facts").boundingBox()
	assert(mobileFacts?.width >= 280, `Delivery Challan mobile header facts are clipped: ${JSON.stringify(mobileFacts)}`)
	const mobileDocumentHeader = await draftRoot.locator(".fabric-document-workspace__header").boundingBox()
	assert(mobileDocumentHeader?.height <= 128 && mobileFacts?.height <= 48, `Delivery Challan mobile identity wastes vertical space: ${JSON.stringify({ mobileDocumentHeader, mobileFacts })}`)
	const mobileCommandbar = await draftRoot.locator(".fabric-document-workspace__commandbar").boundingBox()
	assert(mobileCommandbar?.height <= 64, `Delivery Challan mobile command bar wraps unnecessarily: ${JSON.stringify(mobileCommandbar)}`)
	assert(await draftRoot.locator(".document-action-strip__primary").getByText("Save", { exact: true }).count() === 1, "Delivery Challan hides Save inside More on mobile")
	await assertNoPageOverflow(page, "Delivery Challan at 390px")
	await page.setViewportSize({ width: 1600, height: 1000 })

	const quantityInput = draftRoot.locator(".delivery-challan-matrix--items .p-inputnumber-input").first()
	assert((await quantityInput.getAttribute("aria-label"))?.startsWith("Deliver "), "Delivery Challan quantity input has no contextual accessible name")
	const deliveryMatrixScroller = draftRoot.locator(".delivery-challan-matrix__scroll").first()
	assert(await deliveryMatrixScroller.getAttribute("role") === "region" && await deliveryMatrixScroller.getAttribute("tabindex") === "0", "Delivery Challan matrix is not a keyboard-scrollable region")
	assert(Boolean(await deliveryMatrixScroller.getAttribute("aria-label")), "Delivery Challan matrix region has no accessible name")
	await quantityInput.fill("7")
	await draftRoot.locator("#field-vehicle_no-value").fill("TN-KEEP")
	await draftRoot.getByRole("button", { name: "Save", exact: true }).click()
	const deliveryErrorDialog = page.getByRole("dialog", { name: "Delivery Challan could not be completed" })
	await deliveryErrorDialog.getByText("Stock is no longer available.", { exact: true }).waitFor()
	assert(await draftRoot.locator(".p-message-error").count() === 0, "Delivery Challan duplicates the save error inline")
	assert(savePayload?.values?.received_type === "Accepted", `Delivery Challan save omitted its stock dimension: ${JSON.stringify(savePayload)}`)
	assert(await quantityInput.inputValue() === "7", "Failed Delivery Challan save discarded an entered quantity")
	assert(await draftRoot.locator("#field-vehicle_no-value").inputValue() === "TN-KEEP", "Failed Delivery Challan save discarded an entered header value")
	await deliveryErrorDialog.getByRole("button", { name: "OK", exact: true }).click()

	const workOrderField = draftRoot.locator(".form-field").filter({ hasText: "Work Order" })
	await workOrderField.locator(".p-autocomplete-input").fill("")
	await workOrderField.locator(".p-autocomplete-input").press("Tab")
	let deliverySourceDialog = page.getByRole("dialog", { name: "Change Work Order?" })
	await deliverySourceDialog.waitFor()
	await deliverySourceDialog.getByRole("button", { name: "Keep Current Work Order", exact: true }).click()
	assert(await workOrderField.locator(".p-autocomplete-input").inputValue() === "WO-FAB-001", "Cancelling a cleared Work Order did not restore the committed source")

	await selectAutocompleteOption(page, workOrderField, "WO-FAB-002")
	deliverySourceDialog = page.getByRole("dialog", { name: "Change Work Order?" })
	await deliverySourceDialog.waitFor()
	await deliverySourceDialog.getByRole("button", { name: "Replace Source", exact: true }).evaluate((element) => element.click())
	await page.waitForFunction(() => document.querySelector(".delivery-challan-workspace")?.textContent?.includes("WO-FAB-002"))
	assert(sourcePreviewCalls === 1, `Dirty Delivery Challan source change did not preview exactly once: ${sourcePreviewCalls}`)
	await draftRoot.locator("#field-vehicle_no-value").fill("TN-CLEAR")
	await workOrderField.locator(".p-autocomplete-input").fill("")
	await workOrderField.locator(".p-autocomplete-input").press("Tab")
	deliverySourceDialog = page.getByRole("dialog", { name: "Change Work Order?" })
	await deliverySourceDialog.waitFor()
	await deliverySourceDialog.getByRole("button", { name: "Replace Source", exact: true }).evaluate((element) => element.click())
	assert(await workOrderField.locator(".p-autocomplete-input").inputValue() === "", "Confirmed Work Order clear did not clear the source field")
	assert(await draftRoot.locator(".delivery-challan-matrix--items").count() === 0, "Confirmed Work Order clear retained stale delivery quantities")
	assert(sourcePreviewCalls === 1, "Clearing a Work Order made an invalid source preview request")

	await page.goto(`${SITE}/web/fabric-store/delivery-challans/DC-FAB-001`, { waitUntil: "domcontentloaded" })
	const failedLoadRoot = page.locator(".delivery-challan-workspace")
	await failedLoadRoot.getByText("DC-FAB-001", { exact: true }).waitFor()
	await navigateWithinSpa(page, "/web/fabric-store/delivery-challans/DC-LOAD-ERROR")
	await failedLoadRoot.getByText("Delivery Challan could not be loaded.", { exact: true }).waitFor()
	assert(await page.getByRole("dialog", { name: "Delivery Challan could not be completed" }).count() === 0, "Failed Delivery Challan load duplicates the same error in a popup")
	assert(await failedLoadRoot.getByText("DC-FAB-001", { exact: true }).count() === 0, "Failed in-place Delivery Challan load retained the previous document identity")
	assert(await failedLoadRoot.locator(".delivery-challan-field-group, .delivery-challan-matrix").count() === 0, "Failed in-place Delivery Challan load retained the previous form or matrices")
	assert(await failedLoadRoot.getByRole("button", { name: /Complete Transfer|Return/, exact: true }).count() === 0, "Failed in-place Delivery Challan load retained the previous capabilities")
	assert(await failedLoadRoot.getByText("Draft", { exact: true }).count() === 0, "Failed Delivery Challan load fabricates a Draft state")
	await failedLoadRoot.getByRole("button", { name: "Retry", exact: true }).click()
	await failedLoadRoot.locator('.delivery-challan-field-group[data-group="document"]').waitFor()
	await failedLoadRoot.getByText("DC-LOAD-ERROR", { exact: true }).waitFor()
	assert(loadRetryCalls === 2, `Delivery Challan Retry did not replay the failed request: ${loadRetryCalls}`)

	await page.goto(`${SITE}/web/fabric-store/delivery-challans/DC-RESTRICTED`, { waitUntil: "domcontentloaded" })
	const restrictedRoot = page.locator(".delivery-challan-workspace")
	await restrictedRoot.waitFor()
	assert(await restrictedRoot.getByRole("button", { name: "Save", exact: true }).count() === 0, "Unauthorized Delivery Challan Save is rendered")
	assert(await restrictedRoot.getByRole("button", { name: "Submit", exact: true }).count() === 0, "Unauthorized Delivery Challan Submit is rendered")

	await page.goto(`${SITE}/web/fabric-store/delivery-challans/DC-FAB-001`, { waitUntil: "domcontentloaded" })
	const submittedRoot = page.locator(".delivery-challan-workspace")
	await submittedRoot.waitFor()
	await page.setViewportSize({ width: 390, height: 844 })
	const existingMobileRail = await submittedRoot.locator(".fabric-document-workspace__rail").evaluate((element) => ({ height: element.getBoundingClientRect().height, clientWidth: element.clientWidth, scrollWidth: element.scrollWidth, overflowX: getComputedStyle(element).overflowX, tabIndex: element.tabIndex, maskImage: getComputedStyle(element).maskImage }))
	assert(existingMobileRail.height <= 82 && existingMobileRail.scrollWidth > existingMobileRail.clientWidth && ["auto", "scroll"].includes(existingMobileRail.overflowX) && existingMobileRail.tabIndex === 0 && existingMobileRail.maskImage !== "none", `Existing Delivery Challan totals are not an accessible compact ribbon: ${JSON.stringify(existingMobileRail)}`)
	await page.setViewportSize({ width: 1600, height: 1000 })
	assert(await submittedRoot.getByText("Comments", { exact: true }).count() === 0, "Submitted Delivery Challan shows an empty read-only field")
	assert(await submittedRoot.locator(".delivery-challan-fields input").count() === 0, "Submitted Delivery Challan still renders document facts as disabled form controls")
	assert(await submittedRoot.getByRole("button", { name: "Complete Transfer", exact: true }).count() === 1, "Submitted internal-unit DC lacks Complete Transfer")
	assert(await submittedRoot.locator(".delivery-challan-matrix--items .p-inputnumber-input").first().isDisabled(), "Submitted Delivery Challan matrix remains editable")
	await submittedRoot.getByRole("button", { name: "Return", exact: true }).click()
	const returnDialog = page.getByRole("dialog", { name: "Return Delivery Challan" })
	await returnDialog.waitFor()
	assert(await submittedRoot.locator(".delivery-challan-return-panel").count() === 0, "Delivery Challan return is still appended to the page body")
	assert(await returnDialog.locator(".delivery-challan-return-panel").count() === 1, "Delivery Challan return does not open in a focused popup")
	assert(await returnDialog.getByText("Return whole bundles", { exact: true }).count() === 1, "Essdee whole-bundle return variant is missing")
	await returnDialog.locator(".delivery-challan-return-panel__toggle .p-toggleswitch").click()
	const returnMovement = returnDialog.locator(".delivery-challan-return-panel .common-field").filter({ hasText: "Return Cut Panel Movement" })
	await selectAutocompleteOption(page, returnMovement, "TEST-VALUE")
	const returnQuantity = returnDialog.locator(".delivery-challan-return-panel .p-inputnumber-input")
	await returnQuantity.fill("2")
	await returnQuantity.press("Tab")
	await returnDialog.getByRole("button", { name: "Create Return GRN", exact: true }).click()
	await returnDialog.waitFor({ state: "detached" })
	assert(command?.command === "return" && command.payload?.items?.[0]?.return_quantity === 2 && command.payload?.return_whole_bundles === 1 && command.payload?.cut_panel_movement === "TEST-VALUE", `Delivery Challan return payload is incomplete: ${JSON.stringify(command)}`)
	const createdReturnDialog = page.getByRole("dialog", { name: /Goods Received Note.*GRN-RETURN-001/ })
	await createdReturnDialog.waitFor()
	assert(await createdReturnDialog.locator(".goods-received-note-workspace").count() === 1, "Created return GRN is hidden after Delivery Challan return")
	await createdReturnDialog.getByRole("button", { name: "Close workspace", exact: true }).click()
	await submittedRoot.getByRole("button", { name: "Complete Transfer", exact: true }).click()
	await submittedRoot.getByText("100%", { exact: true }).waitFor()
	assert(command?.command === "complete_transfer", `Unexpected Delivery Challan command: ${JSON.stringify(command)}`)
	const dcCompletionDialog = page.getByRole("dialog", { name: /Edit Stock Entry.*STE-COMPLETE-001/ })
	await dcCompletionDialog.waitFor()
	assert(await dcCompletionDialog.getByRole("button", { name: "Submit Completion", exact: true }).count() === 1, "DC completion leaves its draft Stock Entry without a review-and-submit popup")
	await dcCompletionDialog.locator(".fabric-stock-footer").getByRole("button", { name: "Close", exact: true }).click()

	await page.goto(`${SITE}/web/fabric-store/delivery-challans/DC-SPECIAL`, { waitUntil: "domcontentloaded" })
	const specialContext = page.locator(".delivery-challan-special-context")
	await specialContext.waitFor()
	assert(await specialContext.getByText("Cut Panel Movement", { exact: true }).count() === 1, "Special Delivery Challan mode is not shown")
	assert(await specialContext.locator("input, button, [role=checkbox]").count() === 0, "Source-owned Delivery Challan mode is exposed as an editable control")
	assert(await page.locator(".delivery-challan-matrix .p-inputnumber-input").first().isDisabled(), "Source-owned Delivery Challan quantities remain editable")

	await page.goto(`${SITE}/web/fabric-store/work-orders/WO-FAB-001`, { waitUntil: "domcontentloaded" })
	const parentUrl = page.url()
	await page.getByRole("button", { name: "Make DC", exact: true }).click()
	const popup = page.locator(".related-document-workspace-dialog")
	await popup.waitFor()
	assert(await popup.locator(".delivery-challan-workspace").count() === 1, "WO popup does not reuse the routed Delivery Challan root")
	const loadsBeforeSave = parentLoads
	await popup.getByRole("button", { name: "Save", exact: true }).click()
	await page.getByText("Delivery Challan saved", { exact: true }).waitFor()
	await page.waitForFunction((count) => window.location.pathname.includes("work-orders/WO-FAB-001") && document.querySelector(".related-document-workspace-dialog .delivery-challan-workspace"), loadsBeforeSave)
	await page.waitForTimeout(50)
	assert(parentLoads > loadsBeforeSave, "Delivery Challan mutation did not refresh the parent Work Order")
	assert(page.url() === parentUrl, `Delivery Challan popup navigated away from its parent: ${page.url()}`)
	assert(await popup.locator(".delivery-challan-workspace").count() === 1, "Delivery Challan popup closed after Save")
	await assertNoPageOverflow(page, "Delivery Challan popup at 1600px")

	return { sourcePreviewCalls, saveCalls, parentLoads, command: command?.command }
}

async function goodsReceivedNoteSuite(page) {
	const componentPath = "frontend/src/departments/fabric-store/GoodsReceivedNoteWorkspace.vue"
	const calculatePath = "frontend/src/departments/fabric-store/GrnCalculatePanel.vue"
	const inspectionPath = "frontend/src/departments/fabric-store/InspectionEntryPanel.vue"
	const routePath = "frontend/src/departments/FabricGoodsReceivedNote.vue"
	const hostPath = "frontend/src/departments/fabric-store/RelatedDocumentWorkspaceDialog.vue"
	const workOrderPath = "frontend/src/departments/FabricWorkOrder.vue"
	const purchaseOrderPath = "frontend/src/departments/FabricPurchaseOrder.vue"
	for (const path of [componentPath, calculatePath, inspectionPath, routePath, hostPath, workOrderPath, purchaseOrderPath]) {
		assert(existsSync(path), `Complete Goods Received Note workspace file is missing: ${path}`)
	}
	const componentSource = readFileSync(componentPath, "utf8")
	const routeSource = readFileSync(routePath, "utf8")
	const hostSource = readFileSync(hostPath, "utf8")
	assert(componentSource.includes("goods-received-note-workspace"), "Goods Received Note domain component lacks its stable root")
	assert(!componentSource.includes("window.confirm"), "Goods Received Note still uses the browser confirmation prompt")
	assert(routeSource.includes("GoodsReceivedNoteWorkspace"), "Goods Received Note route does not use the complete domain component")
	assert(hostSource.includes("FabricGoodsReceivedNote"), "Embedded host does not reuse the routed Goods Received Note component")
	assert(!/(router\.(push|replace)|window\.location|<iframe)/.test(hostSource), "Goods Received Note popup host can navigate away from its parent")
	for (const parentPath of [workOrderPath, purchaseOrderPath]) {
		assert(readFileSync(parentPath, "utf8").includes('@changed="relatedChanged"'), `${parentPath} does not refresh after a related GRN mutation`)
	}

	const normalGroup = {
		attributes: ["Colour", "received_type"], primary_attribute: "Size", primary_attribute_values: ["S", "M"],
		items: [{
			name: "GARMENT-001", attributes: { Colour: "Navy" }, dimensions: { lot: "LOT-001", received_type: "Accepted" }, received_type: "Accepted",
			values: {
				S: { qty: 4, pending_qty: 6, max_receivable_quantity: 6, secondary_qty: 2, secondary_uom: "Bundle", rate: 10, amount: 40 },
				M: { qty: 3, pending_qty: 5, max_receivable_quantity: 5, secondary_qty: 0, secondary_uom: "Bundle", rate: 10, amount: 30 },
			},
			default_uom: "Pieces", row_index: 0, item_variant: "GARMENT-001-NAVY", total_qty: 7,
		}],
	}
	const correctionGroup = structuredClone(normalGroup)
	correctionGroup.items[0].name = "GARMENT-CORRECTION"
	correctionGroup.items[0].item_variant = "GARMENT-CORRECTION-NAVY"
	correctionGroup.items[0].values.S.qty = 1
	const fields = [
		{ fieldname: "against", label: "Against", fieldtype: "Select", options: "YRP Work Order\nPurchase Order", value: "YRP Work Order", read_only: true },
		{ fieldname: "against_id", label: "Against ID", fieldtype: "Dynamic Link", options: "against", value: "WO-FAB-001", read_only: true },
		{ fieldname: "delivery_challan", label: "Delivery Challan", fieldtype: "Link", options: "YRP Delivery Challan", value: "DC-FAB-001", read_only: true },
		{ fieldname: "naming_series", label: "Series", fieldtype: "Select", options: "YRP-GRN-.YYYY.-", value: "YRP-GRN-.YYYY.-", reqd: true },
		{ fieldname: "posting_date", label: "Posting Date", fieldtype: "Date", value: "2026-10-06", reqd: true },
		{ fieldname: "posting_time", label: "Posting Time", fieldtype: "Time", value: "10:30:00.654321", reqd: true },
		{ fieldname: "edit_posting_date_and_time", label: "Edit Posting Date and Time", fieldtype: "Check", value: 0 },
		{ fieldname: "production_detail", label: "Production Detail", fieldtype: "Link", options: "YRP Item Production Detail", value: "IPD-001", read_only: true },
		{ fieldname: "delivery_location", label: "Delivery Location", fieldtype: "Link", options: "Supplier", value: "FABRIC-STORE" },
		{ fieldname: "supplier_document_no", label: "Supplier Document No", fieldtype: "Data", value: "SUP-DC-001" },
		{ fieldname: "supplier_document_date", label: "Supplier Document Date", fieldtype: "Date", value: "2026-10-05" },
		{ fieldname: "vehicle_no", label: "Vehicle No", fieldtype: "Data", value: "TN-01-AA-1001" },
		{ fieldname: "from_warehouse", label: "From Warehouse", fieldtype: "Link", options: "Warehouse", value: "Supplier - E" },
		{ fieldname: "to_warehouse", label: "To Warehouse", fieldtype: "Link", options: "Warehouse", value: "Stores - E" },
		{ fieldname: "billing_address", label: "Billing Address", fieldtype: "Link", options: "Address", value: "FABRIC-STORE-Billing" },
		{ fieldname: "supplier_address", label: "Supplier Address", fieldtype: "Link", options: "Address", value: "SUPPLIER-Billing" },
		{ fieldname: "supplier_address_display", label: "Supplier Address Details", fieldtype: "Small Text", value: "D No 15<br>Tiruppur &amp; Tamil Nadu", read_only: true },
		{ fieldname: "contact_person", label: "Supplier Contact", fieldtype: "Link", options: "Contact", value: "SUPPLIER-CONTACT" },
		{ fieldname: "delivery_address", label: "Delivery Address", fieldtype: "Link", options: "Address", value: "FABRIC-STORE-Billing" },
		{ fieldname: "dc_no", label: "DC No", fieldtype: "Data", value: "DC-22" },
		{ fieldname: "comments", label: "Comments", fieldtype: "Small Text", value: "" },
		{ fieldname: "freight_charges", label: "Freight Charges", fieldtype: "Currency", value: 25 },
		{ fieldname: "is_internal_unit", label: "Is Internal Unit", fieldtype: "Check", value: 0 },
		{ fieldname: "transfer_complete", label: "Transfer Complete", fieldtype: "Check", value: 0 },
		{ fieldname: "ste_transferred", label: "STE Transferred", fieldtype: "Float", value: 0, read_only: true },
		{ fieldname: "ste_transferred_percent", label: "STE Transferred (%)", fieldtype: "Percent", value: 0, read_only: true },
	]
	const workspacePayload = ({ name = null, against = "YRP Work Order", docstatus = 0, capabilities = null, special = null, transferComplete = false, inspectionCanSubmit = true } = {}) => ({
		record: {
			doctype: "YRP Goods Received Note", name, docstatus, status: docstatus === 1 ? "Submitted" : "Draft", modified: name ? "2026-10-06 11:00:00" : null,
			against, against_id: against === "Purchase Order" ? "PO-FAB-001" : "WO-FAB-001", delivery_challan: against === "YRP Work Order" ? "DC-FAB-001" : null,
			process_name: against === "YRP Work Order" ? "Stitching" : "Purchase", item: "GARMENT-001", production_detail: "IPD-001", supplier: "FABRIC-STORE", is_internal_unit: docstatus === 1 ? 1 : 0,
			transfer_complete: transferComplete ? 1 : 0, ste_transferred_percent: transferComplete ? 100 : (docstatus === 1 ? 40 : 0),
		},
		fields: fields.map((field) => ({ ...field, value: field.fieldname === "against" ? against : field.fieldname === "against_id" ? (against === "Purchase Order" ? "PO-FAB-001" : "WO-FAB-001") : field.value })),
		values: Object.fromEntries(fields.map((field) => [field.fieldname, field.fieldname === "against" ? against : field.fieldname === "against_id" ? (against === "Purchase Order" ? "PO-FAB-001" : "WO-FAB-001") : field.value])),
		totals: [
			{ fieldname: "total_received_quantity", label: "Total Received Quantity", value: 8 },
			{ fieldname: "total", label: "Total Value", value: 420.5 },
			{ fieldname: "freight_charges", label: "Freight Charges", value: 25 },
			{ fieldname: "grand_total", label: "Grand Total", value: 445.5 },
		],
		matrices: {
			items: [structuredClone(normalGroup)],
			correction_items: [{ work_order_correction: "WOC-001", title: "Correction WOC-001", item_details: [structuredClone(correctionGroup)] }],
		},
		dimensions: [{ fieldname: "received_type", label: "Received Type", fieldtype: "Link", options: "YRP Received Type", value: "Accepted", locked: true }],
		permissions: { can_read: true, can_create: !name, can_write: Boolean(name && docstatus === 0), can_submit: docstatus === 0, can_cancel: docstatus === 1, can_amend: false, can_print: docstatus === 1 },
		capabilities: capabilities || {
			...(docstatus === 1
				? { cancel: { label: "Cancel" }, create_inspection: { label: "Create Inspection Entry" }, view_inspections: { label: "View Inspection Entries" }, ...(transferComplete ? {} : { complete_transfer: { label: "Complete Transfer" } }) }
				: { save: { label: "Save" }, submit: { label: "Submit" }, ...(name && against === "YRP Work Order" ? { calculate: { label: "Calculate" } } : {}) }),
			...(name ? { prepare_sms: { label: "Send SMS" }, prepare_whatsapp: { label: "Send WhatsApp" } } : {}),
		},
		special_source: special || { active: false, modes: [], read_only: false },
		inspection: docstatus === 1 ? {
			can_create: true, can_submit: inspectionCanSubmit,
			initial_payload: [{
				item_variant: "GARMENT-001-NAVY-S", warehouse: "Transit - E", grn_qty: 5,
				ref_doctype: "YRP Goods Received Note Item", ref_docname: "GRNI-001", source_received_type: "Accepted", received_type: "Accepted", lot: "LOT-001",
				splits: [{ target_received_type: "Accepted", qty: 5, received_date: "2026-10-06", comments: "" }],
			}],
			entries: [{ name: "INS-FAB-001", docstatus: 0, posting_date: "2026-10-06", status: "Draft" }], reason: "",
		} : { can_create: false, initial_payload: [], entries: [], reason: "" },
		related: { inspection_entries: docstatus === 1 ? [{ name: "INS-FAB-001", docstatus: 0, status: "Draft" }] : [], completion_entries: [] }, print_formats: [],
	})
	const calculatedPayload = () => {
		const payload = workspacePayload({ name: "GRN-FAB-001" })
		payload.record.modified = "2026-10-06 11:05:00"
		payload.matrices.items[0].items[0].received_type = "Rejected"
		payload.matrices.items[0].items[0].dimensions.received_type = "Rejected"
		payload.matrices.items[0].items[0].values.S.qty = 2
		payload.totals[0].value = 6
		return payload
	}
	const restrictedPayload = workspacePayload({ name: "GRN-RESTRICTED", capabilities: {} })
	restrictedPayload.permissions = { can_read: true, can_write: false, can_submit: false, can_cancel: false, can_amend: false, can_print: false }
	const specialPayload = workspacePayload({ name: "GRN-SPECIAL", capabilities: { save: { label: "Save Draft" }, submit: { label: "Submit" } }, special: { active: true, modes: ["additional_grn", "cut_panel_movement"], read_only: true } })

	const calculationContext = {
		primary_attribute: "Size", primary_values: ["S", "M"], display_attributes: ["Colour"], default_received_type: "Accepted", modified: "2026-10-06 11:00:00",
		matrix_rows: [
			{ attributes: { Colour: "Navy" }, values: { S: { source_row: "WOCI-001", item_variant: "GARMENT-NAVY-S", available_qty: 6, qty: 6 }, M: { source_row: "WOCI-002", item_variant: "GARMENT-NAVY-M", available_qty: 5, qty: 5 } } },
			{ attributes: { Colour: "Wine" }, values: { S: { source_row: "WOCI-003", item_variant: "GARMENT-WINE-S", available_qty: 4, qty: 4 } } },
		],
	}

	let calculated = false
	let calculateCalls = 0
	let calculateRequest = null
	let saveRequest = null
	let inspectionRequest = null
	let commandRequest = null
	let parentLoads = 0
	let submitAttempts = 0
	let loadRetryCalls = 0
	const mismatchMessage = "Cannot submit this GRN because GARMENT-001-NAVY (Colour Navy, Size S, quantity 2) is not an expected Stitching input for Work Order WO-FAB-001 and Production Detail IPD-001. Open the Work Order, add or correct this item, colour, and size under the Stitching inputs, then click Calculate and submit again."
	await page.route("**/api/method/essdee_yrp.api.link_search.link_search*", (route) => {
		const body = requestBody(route)
		const name = body.doctype === "YRP Received Type" ? (body.txt || "Rejected") : body.doctype === "YRP Work Order" ? "WO-FAB-002" : "TEST-VALUE"
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: [{ name, label: name }] }) })
	})
	await page.route("**/api/method/essdee_yrp.fabric_store.web_workspace.get_goods_received_note_workspace*", (route) => {
		const body = requestBody(route)
		const name = body.name || ""
		if (name === "GRN-LOAD-ERROR") {
			loadRetryCalls += 1
			if (loadRetryCalls === 1) return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ exc: "ValidationError", message: "Goods Received Note could not be loaded." }) })
		}
		let payload
		if (name === "GRN-FAB-001") payload = calculated ? calculatedPayload() : workspacePayload({ name })
		else if (name === "GRN-PO-001") payload = workspacePayload({ name, against: "Purchase Order" })
		else if (name === "GRN-SUBMITTED") payload = workspacePayload({ name, docstatus: 1 })
		else if (name === "GRN-INSPECT-RESTRICTED") payload = workspacePayload({ name, docstatus: 1, inspectionCanSubmit: false })
		else if (name === "GRN-LOAD-ERROR") payload = workspacePayload({ name })
		else if (name === "GRN-RESTRICTED") payload = restrictedPayload
		else if (name === "GRN-SPECIAL") payload = specialPayload
		else payload = workspacePayload()
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: payload }) })
	})
	await page.route("**/api/method/essdee_yrp.fabric_store.web_workspace.get_goods_received_note_calculation*", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: { ...calculationContext, modified: calculated ? "2026-10-06 11:05:00" : "2026-10-06 11:01:00" } }) }))
	await page.route("**/api/method/essdee_yrp.fabric_store.web_workspace.calculate_goods_received_note*", (route) => {
		calculateCalls += 1
		calculateRequest = requestBody(route)
		if (calculateCalls === 1) return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ exc: "ValidationError", message: "Calculated quantities became stale." }) })
		calculated = true
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: { workspace: calculatedPayload(), calculation: { total_quantity: 6, received_type: "Rejected" } } }) })
	})
	await page.route("**/api/method/essdee_yrp.fabric_store.web_workspace.save_goods_received_note*", (route) => {
		saveRequest = requestBody(route)
		if (saveRequest.submit && ++submitAttempts === 1) return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ exc: "ValidationError", message: mismatchMessage }) })
		if (saveRequest.submit) return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: workspacePayload({ name: saveRequest.name || "GRN-FAB-001", docstatus: 1 }) }) })
		const payload = calculated ? calculatedPayload() : workspacePayload({ name: "GRN-NEW" })
		payload.values.comments = saveRequest.values?.comments || ""
		payload.fields.find((field) => field.fieldname === "comments").value = payload.values.comments
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: payload }) })
	})
	await page.route("**/api/method/essdee_yrp.fabric_store.web_workspace.save_goods_received_note_inspection*", (route) => {
		inspectionRequest = requestBody(route)
		const payload = workspacePayload({ name: "GRN-SUBMITTED", docstatus: 1 })
		payload.related.inspection_entries.push({ name: "INS-NEW", docstatus: 1, status: "Submitted" })
		payload.inspection.entries = payload.related.inspection_entries
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: { workspace: payload, inspection: { record: { name: "INS-NEW", docstatus: 1 } } } }) })
	})
	await page.route("**/api/method/essdee_yrp.fabric_store.web_workspace.execute_goods_received_note_command*", (route) => {
		commandRequest = requestBody(route)
		if (commandRequest.command === "prepare_sms") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: {
			channel: "sms", context: {
				supplier: "FABRIC-STORE", mobile: "+919876543210", numbers: ["+919876543210"],
				templates: [{ name: "Receipt", body: "Receipt {name}", variables: [{ name: "name", value: "GRN-FAB-001" }] }],
				doc_fields: [{ value: "name", label: "Name (name)" }],
			},
		} }) })
		if (commandRequest.command === "prepare_whatsapp") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: {
			channel: "whatsapp", context: {
				supplier: "FABRIC-STORE", mobile: "+919876543210", numbers: ["+919876543210"],
				templates: [{ name: "WA-RECEIPT", template_name: "grn_receipt", language_code: "en", body_text: "Receipt {{1}} is ready", footer_text: "Essdee", needs_media: false, variables: [{ name: "1", type: "body", value: "GRN-FAB-001" }] }],
				doc_fields: [{ value: "name", label: "Name (name)" }],
			},
		} }) })
		if (["send_sms", "send_whatsapp"].includes(commandRequest.command)) return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: { channel: commandRequest.command.replace("send_", ""), result: { ok: true, request_id: "NOTIFY-1" } } }) })
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: { workspace: workspacePayload({ name: "GRN-SUBMITTED", docstatus: 1, transferComplete: true }), created: { doctype: "YRP Stock Entry", name: "STE-GRN-001" } } }) })
	})
	await page.route("**/api/method/essdee_yrp.fabric_store.web_workspace.get_stock_operation_editor*", (route) => {
		const body = requestBody(route)
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: {
			operation: "stock_entry", doctype: "YRP Stock Entry", name: body.name, modified: "2026-10-06 12:00:00",
			defaults: { purpose: "GRN Completion", from_warehouse: "TRANSIT-WH", to_warehouse: "FABRIC-WH" },
			purpose_options: ["GRN Completion", "Send to Warehouse"], dimensions: [], default_dimensions: {}, locked_dimensions: [], item_filters: {},
			item_groups: [structuredClone(normalGroup)], purpose_locked: true, protected_completion: true, permissions: { can_write: true, can_submit: true },
		} }) })
	})
	await page.route("**/api/method/essdee_yrp.fabric_store.web_workspace.get_work_order_workspace*", (route) => {
		parentLoads += 1
		return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: {
			record: { doctype: "YRP Work Order", name: "WO-FAB-001", docstatus: 1, status: "Open", process_name: "Stitching", item: "GARMENT-001", lot: "LOT-001", modified: "2026-10-06 09:00:00" },
			fields: [], details: [], totals: [], matrices: { deliverables: [], receivables: [] }, summary: {}, related: { delivery_challans: [], goods_received_notes: [] },
			permissions: { can_read: true, can_write: false, can_print: false }, related_permissions: { delivery_challan: { can_read: true, can_create: false }, goods_received_note: { can_read: true, can_create: true } },
			capabilities: { create_goods_received_note: { label: "Make GRN", source_context: { work_order: "WO-FAB-001" } } }, print_formats: [],
		} }) })
	})

	await page.setViewportSize({ width: 1600, height: 1000 })
	await page.goto(`${SITE}/web/fabric-store/goods-received-notes/new?work_order=WO-FAB-001`, { waitUntil: "domcontentloaded" })
	const newRoot = page.locator(".goods-received-note-workspace")
	await newRoot.waitFor({ timeout: 20_000 })
	await newRoot.locator('.goods-received-note-field-group[data-group="posting"]').waitFor({ timeout: 20_000 })
	for (const group of ["posting", "movement", "supplier-document", "addresses"]) {
		assert(await newRoot.locator(`.goods-received-note-field-group[data-group="${group}"]`).count() === 1, `GRN fields are missing the ${group} group`)
	}
	assert(await newRoot.locator('.goods-received-note-field-group[data-group="source"]').count() === 0, "GRN still renders its redundant Receipt source section")
	for (const label of ["Source Type", "Source Document", "Delivery Challan", "Production Detail"]) {
		assert(await newRoot.locator(".form-field").filter({ hasText: label }).count() === 0, `GRN still renders redundant field: ${label}`)
	}
	const grnPostingLabels = (await newRoot.locator('.goods-received-note-field-group[data-group="posting"] .form-field__label').allTextContents()).map((label) => label.replace("*", "").trim())
	assert(JSON.stringify(grnPostingLabels.slice(0, 4)) === JSON.stringify(["Series", "Posting Date", "Posting Time", "Edit Posting Date and Time"]), `GRN posting fields do not follow the entry sequence: ${JSON.stringify(grnPostingLabels)}`)
	assert(await newRoot.getByLabel("Posting Time", { exact: true }).inputValue() === "10:30:00", "GRN does not display Frappe's fractional posting time")
	assert(await newRoot.locator(".goods-received-note-matrix--items").count() === 1, "WO GRN receivable matrix is missing")
	assert(await newRoot.locator(".goods-received-note-matrix--corrections").count() === 1, "WO GRN correction matrix is missing")
	const receiptQuantityInput = newRoot.locator(".goods-received-note-matrix--items .p-inputnumber-input").first()
	assert((await receiptQuantityInput.getAttribute("aria-label"))?.startsWith("Receive "), "Goods Received Note quantity input has no contextual accessible name")
	const receiptMatrixScroller = newRoot.locator(".goods-received-note-matrix__scroll").first()
	assert(await receiptMatrixScroller.getAttribute("role") === "region" && await receiptMatrixScroller.getAttribute("tabindex") === "0", "Goods Received Note matrix is not a keyboard-scrollable region")
	assert(Boolean(await receiptMatrixScroller.getAttribute("aria-label")), "Goods Received Note matrix region has no accessible name")
	assert(await newRoot.getByRole("button", { name: "Calculate", exact: true }).count() === 0, "Unsaved GRN exposes Calculate")
	assert(await newRoot.locator(".goods-received-note-total--primary").filter({ hasText: "Total Received Quantity" }).count() === 1, "Received quantity is not highlighted")
	assert(await newRoot.locator(".goods-received-note-total--primary").filter({ hasText: "Grand Total" }).count() === 1, "GRN value is not highlighted")
	assert(await newRoot.locator(".goods-received-note-matrix__group > header span").count() === 0, "GRN repeats Lot below every item title")
	const grnTail = newRoot.locator(".goods-received-note-after-matrix")
	assert(await grnTail.count() === 1, "GRN final fields are not placed below Received quantities")
	for (const label of ["Freight Charges", "Comments", "Is Internal Unit", "Transfer Complete", "STE Transferred", "STE Transferred (%)"]) {
		assert(await grnTail.getByText(label, { exact: true }).count() === 1, `GRN final field is missing: ${label}`)
	}
	const grnMatrixBox = await newRoot.locator(".fabric-document-workspace__matrix").boundingBox()
	const grnTailBox = await grnTail.boundingBox()
	assert(grnMatrixBox && grnTailBox && grnTailBox.y >= grnMatrixBox.y + grnMatrixBox.height, `GRN final fields are not below the table: ${JSON.stringify({ grnMatrixBox, grnTailBox })}`)
	assert(await newRoot.locator(".form-field").filter({ hasText: "Supplier Address Details" }).locator("textarea").inputValue() === "D No 15\nTiruppur & Tamil Nadu", "GRN address details expose raw <br> tags")


	await page.setViewportSize({ width: 900, height: 760 })
	const tabletRail = await newRoot.locator(".fabric-document-workspace__rail").boundingBox()
	const tabletMain = await newRoot.locator(".fabric-document-workspace__main").boundingBox()
	const tabletHeader = await newRoot.locator(".fabric-document-workspace__header").boundingBox()
	assert(tabletRail && tabletMain && tabletMain.y < tabletRail.y, `New GRN front-loads totals before its tablet form: ${JSON.stringify({ tabletRail, tabletMain })}`)
	assert(tabletHeader?.height <= 76, `GRN header wraps unnecessarily at tablet width: ${JSON.stringify(tabletHeader)}`)
	await page.setViewportSize({ width: 390, height: 844 })
	const mobileRail = await newRoot.locator(".fabric-document-workspace__rail").evaluate((element) => ({ tabIndex: element.tabIndex, maskImage: getComputedStyle(element).maskImage }))
	const mobileNewRailBox = await newRoot.locator(".fabric-document-workspace__rail").boundingBox()
	const mobileNewMainBox = await newRoot.locator(".fabric-document-workspace__main").boundingBox()
	assert(mobileNewMainBox && mobileNewRailBox && mobileNewMainBox.y < mobileNewRailBox.y && mobileRail.tabIndex === -1 && mobileRail.maskImage === "none", `New GRN totals should follow the form instead of using the existing-document ribbon: ${JSON.stringify({ mobileNewMainBox, mobileNewRailBox, mobileRail })}`)
	const mobileFacts = await newRoot.locator(".goods-received-note-header__facts").boundingBox()
	assert(mobileFacts?.width >= 280, `GRN mobile header facts are clipped: ${JSON.stringify(mobileFacts)}`)
	const mobileDocumentHeader = await newRoot.locator(".fabric-document-workspace__header").boundingBox()
	assert(mobileDocumentHeader?.height <= 128 && mobileFacts?.height <= 48, `GRN mobile identity wastes vertical space: ${JSON.stringify({ mobileDocumentHeader, mobileFacts })}`)
	const mobileCommandbar = await newRoot.locator(".fabric-document-workspace__commandbar").boundingBox()
	assert(mobileCommandbar?.height <= 64, `GRN mobile command bar wraps unnecessarily: ${JSON.stringify(mobileCommandbar)}`)
	assert(await newRoot.locator(".document-action-strip__primary").getByText("Save", { exact: true }).count() === 1, "GRN hides Save inside More on mobile")
	await assertNoPageOverflow(page, "Goods Received Note at 390px")
	await page.setViewportSize({ width: 1600, height: 1000 })

	await page.goto(`${SITE}/web/fabric-store/goods-received-notes/GRN-FAB-001`, { waitUntil: "domcontentloaded" })
	const failedLoadRoot = page.locator(".goods-received-note-workspace")
	await failedLoadRoot.getByText("GRN-FAB-001", { exact: true }).waitFor()
	await navigateWithinSpa(page, "/web/fabric-store/goods-received-notes/GRN-LOAD-ERROR")
	await failedLoadRoot.getByText("Goods Received Note could not be loaded.", { exact: true }).waitFor()
	assert(await page.getByRole("dialog", { name: "Goods Received Note could not be completed" }).count() === 0, "Failed GRN load duplicates the same error in a popup")
	assert(await failedLoadRoot.getByText("GRN-FAB-001", { exact: true }).count() === 0, "Failed in-place GRN load retained the previous document identity")
	assert(await failedLoadRoot.locator(".goods-received-note-field-group, .goods-received-note-matrix").count() === 0, "Failed in-place GRN load retained the previous form or matrices")
	assert(await failedLoadRoot.getByRole("button", { name: /Calculate|Submit/, exact: true }).count() === 0, "Failed in-place GRN load retained the previous capabilities")
	assert(await failedLoadRoot.getByText("Draft", { exact: true }).count() === 0, "Failed GRN load fabricates a Draft state")
	await failedLoadRoot.getByRole("button", { name: "Retry", exact: true }).click()
	await failedLoadRoot.locator('.goods-received-note-field-group[data-group="posting"]').waitFor()
	await failedLoadRoot.getByText("GRN-LOAD-ERROR", { exact: true }).waitFor()
	assert(loadRetryCalls === 2, `GRN Retry did not replay the failed request: ${loadRetryCalls}`)

	await page.goto(`${SITE}/web/fabric-store/goods-received-notes/GRN-FAB-001`, { waitUntil: "domcontentloaded" })
	const draftRoot = page.locator(".goods-received-note-workspace")
	await draftRoot.waitFor()
	await page.setViewportSize({ width: 390, height: 844 })
	const existingMobileRail = await draftRoot.locator(".fabric-document-workspace__rail").evaluate((element) => ({ height: element.getBoundingClientRect().height, clientWidth: element.clientWidth, scrollWidth: element.scrollWidth, overflowX: getComputedStyle(element).overflowX, tabIndex: element.tabIndex, maskImage: getComputedStyle(element).maskImage }))
	assert(existingMobileRail.height <= 82 && existingMobileRail.scrollWidth > existingMobileRail.clientWidth && ["auto", "scroll"].includes(existingMobileRail.overflowX) && existingMobileRail.tabIndex === 0 && existingMobileRail.maskImage !== "none", `Existing GRN totals are not an accessible compact ribbon: ${JSON.stringify(existingMobileRail)}`)
	await page.setViewportSize({ width: 1600, height: 1000 })
	await draftRoot.locator("#field-comments-value").fill("Unsaved local edit")
	const dirtyCalculate = draftRoot.locator(".document-action-strip__primary").filter({ hasText: "Calculate" })
	await page.waitForFunction(() => Array.from(document.querySelectorAll(".goods-received-note-workspace .document-action-strip__primary")).some((button) => button.textContent?.includes("Calculate") && button.getAttribute("aria-disabled") === "true"))
	const dirtyCalculateState = await dirtyCalculate.evaluateAll((buttons) => buttons.map((button) => ({ ariaDisabled: button.getAttribute("aria-disabled"), disabled: button.disabled, label: button.getAttribute("aria-label"), text: button.textContent })))
	assert(dirtyCalculateState.length === 1 && dirtyCalculateState[0].ariaDisabled === "true" && !dirtyCalculateState[0].disabled, `Dirty GRN Calculate is not focusable while exposing its unavailable state: ${JSON.stringify(dirtyCalculateState)}`)
	await dirtyCalculate.focus()
	await draftRoot.getByText("Save the Goods Received Note before calculating.", { exact: true }).waitFor()
	await page.goto(`${SITE}/web/fabric-store/goods-received-notes/GRN-FAB-001`, { waitUntil: "domcontentloaded" })
	await draftRoot.waitFor()
	const clickGrnAction = async (label) => {
		const direct = draftRoot.getByRole("button", { name: label, exact: true })
		if (await direct.count() && await direct.isVisible()) return direct.click()
		await draftRoot.getByRole("button", { name: "More", exact: true }).click()
		return page.locator(".document-action-menu:visible").getByText(label, { exact: true }).click()
	}
	await clickGrnAction("Send SMS")
	let notificationDialog = page.getByRole("dialog", { name: "Send supplier notification" })
	await notificationDialog.waitFor()
	let notificationPanel = notificationDialog.locator(".supplier-notification-panel")
	await notificationPanel.waitFor()
	await notificationPanel.getByRole("button", { name: "Send SMS", exact: true }).click()
	await notificationPanel.waitFor({ state: "detached" })
	assert(commandRequest?.command === "send_sms" && commandRequest?.payload?.template_name === "Receipt" && commandRequest?.payload?.mobile_no === "+919876543210" && commandRequest?.payload?.params?.name === "GRN-FAB-001", `SMS action mapping is incomplete: ${JSON.stringify(commandRequest)}`)
	await clickGrnAction("Send WhatsApp")
	notificationDialog = page.getByRole("dialog", { name: "Send supplier notification" })
	await notificationDialog.waitFor()
	notificationPanel = notificationDialog.locator(".supplier-notification-panel")
	await notificationPanel.waitFor()
	assert(await notificationPanel.getByText("Receipt GRN-FAB-001 is ready", { exact: true }).count() === 1, "WhatsApp template preview did not resolve its body variable")
	await notificationPanel.getByRole("button", { name: "Send WhatsApp", exact: true }).click()
	await notificationPanel.waitFor({ state: "detached" })
	assert(commandRequest?.command === "send_whatsapp" && commandRequest?.payload?.template_name === "grn_receipt" && commandRequest?.payload?.language_code === "en" && commandRequest?.payload?.params?.["body:1"] === "GRN-FAB-001", `WhatsApp action mapping is incomplete: ${JSON.stringify(commandRequest)}`)
	await draftRoot.getByRole("button", { name: "Calculate", exact: true }).click()
	const calculateDialog = page.getByRole("dialog", { name: "Calculate Goods Received Note" })
	await calculateDialog.waitFor()
	const calculatePanel = calculateDialog.locator(".grn-calculate-panel")
	await calculatePanel.waitFor()
	assert(await calculatePanel.getByText(/Available/).count() >= 1, "Calculate matrix does not show source availability")
	assert(await calculatePanel.getByText("Row total", { exact: true }).count() === 1, "Calculate matrix lacks row totals")
	assert(await calculatePanel.getByText("Column totals", { exact: true }).count() === 1, "Calculate matrix lacks column totals")
	assert(await calculatePanel.locator(".grn-calculate-panel__grand-total").getByText("15", { exact: true }).count() === 1, "Calculate grand total is wrong")
	await calculatePanel.getByRole("button", { name: "Unselect all", exact: true }).click()
	assert(await calculatePanel.locator(".grn-calculate-panel__grand-total").getByText("0", { exact: true }).count() === 1, "Unselect all does not clear the Calculate total")
	await calculatePanel.getByRole("button", { name: "Select all", exact: true }).click()
	await selectAutocompleteOption(page, calculatePanel.locator(".grn-calculate-panel__received-type"), "Rejected")
	const calculatedQty = calculatePanel.locator(".grn-calculate-panel__quantity .p-inputnumber-input").first()
	await calculatedQty.fill("2")
	await calculatePanel.getByRole("button", { name: "Apply Calculation", exact: true }).click()
	const grnCalculateError = page.getByRole("dialog", { name: "Goods Received Note could not be completed" })
	await grnCalculateError.getByText("Calculated quantities became stale.", { exact: true }).waitFor()
	assert(await calculatePanel.locator(".p-message-error").count() === 0, "GRN Calculate duplicates its server error inline")
	assert(await calculatedQty.inputValue() === "2", "Failed Calculate discarded an entered quantity")
	assert(await calculatePanel.locator(".grn-calculate-panel__received-type .p-autocomplete-input").inputValue() === "Rejected", "Failed Calculate discarded Received Type")
	await grnCalculateError.getByRole("button", { name: "OK", exact: true }).click()
	await calculatePanel.getByRole("button", { name: "Apply Calculation", exact: true }).click()
	await calculatePanel.waitFor({ state: "detached" })
	assert(calculateRequest?.received_type === "Rejected" && calculateRequest?.expected_modified === "2026-10-06 11:01:00" && calculateRequest?.rows?.some((row) => row.source_row === "WOCI-001" && row.qty === 2), `Calculate request is incomplete: ${JSON.stringify(calculateRequest)}`)
	assert(await draftRoot.getByText("Rejected", { exact: true }).count() >= 1, "Calculated Received Type was not reloaded into the matrix")
	await draftRoot.getByRole("button", { name: "Refresh", exact: true }).click()
	await page.waitForFunction(() => !document.querySelector('.goods-received-note-workspace button[aria-label="Refresh"]')?.disabled)
	await draftRoot.getByText("Rejected", { exact: true }).first().waitFor()
	await draftRoot.locator("#field-comments-value").fill("Keep calculated split")
	await page.waitForFunction(() => !document.querySelector('.goods-received-note-workspace button[aria-label="Save"]')?.disabled)
	await draftRoot.getByRole("button", { name: "Save", exact: true }).click()
	assert(saveRequest?.values?.item_details?.[0]?.items?.[0]?.dimensions?.received_type === "Rejected", `Ordinary save omitted the calculated split: ${JSON.stringify(saveRequest)}`)
	assert(saveRequest?.values?.against === "YRP Work Order" && saveRequest?.values?.against_id === "WO-FAB-001" && saveRequest?.values?.production_detail === "IPD-001", `Hidden GRN source values were dropped from save: ${JSON.stringify(saveRequest)}`)
	assert(await draftRoot.getByText("Rejected", { exact: true }).count() >= 1, "Save discarded the calculated Received Type split")
	await draftRoot.getByRole("button", { name: "Calculate", exact: true }).click()
	const reopenedCalculation = page.getByRole("dialog", { name: "Calculate Goods Received Note" })
	await reopenedCalculation.waitFor()
	await reopenedCalculation.locator(".grn-calculate-panel").getByRole("button", { name: "Close", exact: true }).click()
	await reopenedCalculation.waitFor({ state: "detached" })
	await draftRoot.getByRole("button", { name: "Submit", exact: true }).click()
	const grnSubmitError = page.getByRole("dialog", { name: "Goods Received Note could not be completed" })
	await grnSubmitError.getByText(mismatchMessage, { exact: true }).waitFor()
	assert(await draftRoot.locator(".p-message-error").count() === 0, "GRN duplicates the submit error inline")
	assert(await draftRoot.locator("#field-comments-value").inputValue() === "Keep calculated split", "Failed GRN submit discarded edited fields")
	await grnSubmitError.getByRole("button", { name: "OK", exact: true }).click()
	await draftRoot.getByRole("button", { name: "Submit", exact: true }).click()
	assert(await draftRoot.getByRole("button", { name: "Apply Calculation", exact: true }).count() === 0, "Submitted GRN retains an actionable Calculate panel")

	await page.goto(`${SITE}/web/fabric-store/goods-received-notes/GRN-PO-001`, { waitUntil: "domcontentloaded" })
	const poRoot = page.locator(".goods-received-note-workspace")
	await poRoot.waitFor()
	await poRoot.getByText("PO-FAB-001", { exact: true }).first().waitFor({ timeout: 20_000 })
	assert(await poRoot.getByText("PO-FAB-001", { exact: true }).count() >= 1, "PO GRN does not show its authoritative source")
	assert(await poRoot.getByRole("button", { name: "Calculate", exact: true }).count() === 0, "PO GRN exposes WO-only Calculate")

	await page.goto(`${SITE}/web/fabric-store/goods-received-notes/GRN-RESTRICTED`, { waitUntil: "domcontentloaded" })
	const restrictedRoot = page.locator(".goods-received-note-workspace")
	await restrictedRoot.waitFor()
	assert(await restrictedRoot.getByRole("button", { name: "Save", exact: true }).count() === 0, "Unauthorized GRN Save is rendered")
	assert(await restrictedRoot.getByRole("button", { name: "Submit", exact: true }).count() === 0, "Unauthorized GRN Submit is rendered")
	assert(await restrictedRoot.getByRole("button", { name: "Send SMS", exact: true }).count() === 0, "Unauthorized GRN SMS action is rendered")
	assert(await restrictedRoot.getByRole("button", { name: "Send WhatsApp", exact: true }).count() === 0, "Unauthorized GRN WhatsApp action is rendered")

	await page.goto(`${SITE}/web/fabric-store/goods-received-notes/GRN-SPECIAL`, { waitUntil: "domcontentloaded" })
	const specialRoot = page.locator(".goods-received-note-workspace")
	await specialRoot.waitFor()
	const specialContext = specialRoot.locator(".goods-received-note-special-context")
	await specialContext.waitFor()
	assert(await specialContext.getByText("Additional Grn", { exact: true }).count() === 1, "Special GRN mode is not shown")
	assert(await specialRoot.locator(".goods-received-note-matrix .p-inputnumber-input").first().isDisabled(), "Source-owned GRN rows remain editable")

	await page.goto(`${SITE}/web/fabric-store/goods-received-notes/GRN-INSPECT-RESTRICTED`, { waitUntil: "domcontentloaded" })
	const inspectionRestrictedRoot = page.locator(".goods-received-note-workspace")
	await inspectionRestrictedRoot.waitFor()
	await inspectionRestrictedRoot.getByRole("button", { name: "Create Inspection Entry", exact: true }).click()
	let inspectionDialog = page.getByRole("dialog", { name: "Create Inspection Entry" })
	await inspectionDialog.waitFor()
	assert(await inspectionDialog.getByRole("button", { name: "Save Inspection Draft", exact: true }).count() === 1, "Inspection create permission does not expose draft save")
	assert(await inspectionDialog.getByRole("button", { name: "Save & Submit Inspection", exact: true }).count() === 0, "Inspection Submit is rendered without submit permission")
	await inspectionDialog.locator(".inspection-entry-panel").getByRole("button", { name: "Close", exact: true }).click()

	await page.goto(`${SITE}/web/fabric-store/goods-received-notes/GRN-SUBMITTED`, { waitUntil: "domcontentloaded" })
	const submittedRoot = page.locator(".goods-received-note-workspace")
	await submittedRoot.waitFor()
	assert(await submittedRoot.getByText("Comments", { exact: true }).count() === 0, "Submitted GRN shows an empty read-only field")
	assert(await submittedRoot.locator(".goods-received-note-fields input").count() === 0, "Submitted GRN still renders document facts as disabled form controls")
	await submittedRoot.getByRole("button", { name: "Create Inspection Entry", exact: true }).click()
	inspectionDialog = page.getByRole("dialog", { name: "Create Inspection Entry" })
	await inspectionDialog.waitFor()
	const inspectionPanel = inspectionDialog.locator(".inspection-entry-panel")
	await inspectionPanel.waitFor()
	assert(await inspectionPanel.getByText("Transit - E", { exact: true }).count() === 1, "Inspection panel ignores the authoritative transit source bin")
	await inspectionPanel.getByRole("button", { name: "Add split", exact: true }).click()
	await inspectionPanel.locator(".inspection-entry-panel__split .p-inputnumber-input").nth(1).fill("1")
	await inspectionPanel.locator(".inspection-entry-panel__split .p-inputnumber-input").nth(1).press("Tab")
	assert(await inspectionPanel.getByRole("button", { name: "Save & Submit Inspection", exact: true }).isDisabled(), "Inspection can submit split totals above the authoritative source quantity")
	await inspectionPanel.getByRole("button", { name: "Remove inspection split", exact: true }).last().click()
	await selectAutocompleteOption(page, inspectionPanel.locator(".inspection-entry-panel__target-type").first(), "Rejected")
	await inspectionPanel.getByRole("button", { name: "Save & Submit Inspection", exact: true }).click()
	await inspectionPanel.waitFor({ state: "detached" })
	assert(inspectionRequest?.submit === true && inspectionRequest?.values?.item_details?.[0]?.warehouse === "Transit - E" && inspectionRequest?.values?.item_details?.[0]?.splits?.[0]?.target_received_type === "Rejected", `Inspection request is incomplete: ${JSON.stringify(inspectionRequest)}`)
	assert(await submittedRoot.getByText("INS-NEW", { exact: true }).count() >= 1, "Saved Inspection Entry was not reloaded in place")
	await submittedRoot.getByRole("button", { name: "Complete Transfer", exact: true }).click()
	await submittedRoot.getByText("100%", { exact: true }).waitFor()
	assert(commandRequest?.command === "complete_transfer", `Unexpected GRN command: ${JSON.stringify(commandRequest)}`)
	const grnCompletionDialog = page.getByRole("dialog", { name: /Edit Stock Entry.*STE-GRN-001/ })
	await grnCompletionDialog.waitFor()
	assert(await grnCompletionDialog.getByRole("button", { name: "Submit Completion", exact: true }).count() === 1, "GRN completion leaves its draft Stock Entry without a review-and-submit popup")
	await grnCompletionDialog.locator(".fabric-stock-footer").getByRole("button", { name: "Close", exact: true }).click()

	await page.goto(`${SITE}/web/fabric-store/work-orders/WO-FAB-001`, { waitUntil: "domcontentloaded" })
	const parentUrl = page.url()
	await page.getByRole("button", { name: "Make GRN", exact: true }).click()
	const parentGrnSource = page.getByRole("dialog", { name: "Create Goods Received Note" })
	await parentGrnSource.waitFor()
	await parentGrnSource.getByRole("button", { name: "Continue to GRN", exact: true }).click()
	const popup = page.locator(".related-document-workspace-dialog")
	await popup.waitFor()
	assert(await popup.locator(".goods-received-note-workspace").count() === 1, "WO popup does not reuse the routed GRN root")
	const loadsBeforeSave = parentLoads
	await popup.getByRole("button", { name: "Save", exact: true }).click()
	await page.getByText("Goods Received Note saved", { exact: true }).waitFor()
	await page.waitForFunction((count) => window.location.pathname.includes("work-orders/WO-FAB-001") && document.querySelector(".related-document-workspace-dialog .goods-received-note-workspace"), loadsBeforeSave)
	await page.waitForTimeout(50)
	assert(parentLoads > loadsBeforeSave, "GRN mutation did not refresh the parent Work Order")
	assert(page.url() === parentUrl, `GRN popup navigated away from its parent: ${page.url()}`)
	assert(await popup.locator(".goods-received-note-workspace").count() === 1, "GRN popup closed after Save")
	await assertNoPageOverflow(page, "Goods Received Note popup at 1600px")

	return { calculateCalls, calculated, parentLoads, inspection: inspectionRequest?.submit, command: commandRequest?.command }
}

async function paritySuite() {
	const inventoryPath = "docs/fabric-store-document-parity.md"
	const notificationPanelPath = "frontend/src/departments/fabric-store/SupplierNotificationPanel.vue"
	const obsoletePaths = [
		"frontend/src/departments/fabric-store/WorkOrderTransactionEditor.vue",
		"frontend/src/departments/fabric-store/PurchaseOrderGrnEditor.vue",
	]
	assert(existsSync(inventoryPath), "The concise Fabric Store parity inventory is missing")
	assert(existsSync(notificationPanelPath), "The reusable supplier notification panel is missing")
	for (const path of obsoletePaths) assert(!existsSync(path), `Obsolete reduced editor still exists: ${path}`)

	const runtimePaths = [
		"frontend/src/departments/FabricPurchaseOrder.vue",
		"frontend/src/departments/FabricWorkOrder.vue",
		"frontend/src/departments/fabric-store/DeliveryChallanWorkspace.vue",
		"frontend/src/departments/fabric-store/GoodsReceivedNoteWorkspace.vue",
		"frontend/src/departments/fabric-store/RelatedDocumentWorkspaceDialog.vue",
	]
	const runtimeSource = runtimePaths.map((path) => readFileSync(path, "utf8")).join("\n")
	for (const name of ["WorkOrderTransactionEditor", "PurchaseOrderGrnEditor"]) {
		assert(!runtimeSource.includes(name), `Runtime still imports the reduced ${name}`)
	}
	for (const path of [
		"frontend/src/departments/FabricPurchaseOrder.vue",
		"frontend/src/departments/fabric-store/DeliveryChallanWorkspace.vue",
		"frontend/src/departments/fabric-store/GoodsReceivedNoteWorkspace.vue",
	]) {
		assert(readFileSync(path, "utf8").includes("SupplierNotificationPanel"), `${path} does not use the shared SMS/WhatsApp panel`)
	}

	const inventory = readFileSync(inventoryPath, "utf8")
	for (const heading of ["Purchase Order", "Work Order", "Delivery Challan", "Goods Received Note", "Compatibility", "Acceptance gate"]) {
		assert(inventory.includes(heading), `Parity inventory is missing ${heading}`)
	}
	for (const action of ["Send SMS", "Send WhatsApp", "Calculate", "Create Inspection Entry", "Complete Transfer", "Manage Linked Lots", "Create Rework"]) {
		assert(inventory.includes(action), `Parity inventory does not map ${action}`)
	}
	assert(inventory.includes("yrp.notification.send_flow_sms_notification"), "SMS send endpoint is not audited")
	assert(inventory.includes("yrp.whatsapp_notification.send_whatsapp_notification"), "WhatsApp send endpoint is not audited")

	return { obsoleteEditorsRemoved: true, auditedDocuments: 4, sharedNotificationPanel: true }
}

async function statesSuite(page) {
	const context = page.context()
	const results = {}

	const loadingPage = await context.newPage()
	try {
		await mockWorkspace(loadingPage, [])
		await loadingPage.route("**/api/method/essdee_yrp.fabric_store.web_workspace.get_capabilities*", async (route) => {
			await new Promise((resolve) => setTimeout(resolve, 300))
			await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ message: capabilities }) })
		})
		await loadingPage.goto(`${SITE}/web/fabric-store`, { waitUntil: "domcontentloaded" })
		await loadingPage.locator(".workspace-launcher__grid[aria-label='Loading workspaces']").waitFor()
		await loadingPage.locator(".workspace-launcher__card").first().waitFor()
		results.loading = true
	} finally {
		await loadingPage.close()
	}

	const errorPage = await context.newPage()
	try {
		await mockWorkspace(errorPage, [])
		let capabilityFailed = true
		await errorPage.route("**/api/method/essdee_yrp.fabric_store.web_workspace.get_capabilities*", (route) => route.fulfill(capabilityFailed ? {
			status: 500, contentType: "application/json", body: JSON.stringify({ message: "Fabric workspace unavailable" }),
		} : {
			status: 200, contentType: "application/json", body: JSON.stringify({ message: capabilities }),
		}))
		await errorPage.goto(`${SITE}/web/fabric-store`, { waitUntil: "domcontentloaded" })
		await errorPage.getByText("Fabric workspace unavailable", { exact: true }).waitFor()
		capabilityFailed = false
		await errorPage.getByRole("button", { name: "Retry", exact: true }).click()
		await errorPage.locator(".workspace-launcher__card").first().waitFor()
		results.error = true
	} finally {
		await errorPage.close()
	}

	const emptyPage = await context.newPage()
	try {
		await mockWorkspace(emptyPage, [])
		await emptyPage.route("**/api/resource/**", (route) => route.fulfill({
			status: 200,
			contentType: "application/json",
			body: JSON.stringify({ data: [] }),
		}))
		await emptyPage.goto(`${SITE}/web/fabric-store/work-orders`, { waitUntil: "domcontentloaded" })
		await emptyPage.locator(".premium-list-table").getByText("No records found", { exact: true }).waitFor()
		results.empty = true
	} finally {
		await emptyPage.close()
	}

	const permissionPage = await context.newPage()
	try {
		const restrictedCapabilities = JSON.parse(JSON.stringify(capabilities))
		restrictedCapabilities.sections.stock_transfers.operations.stock_update.can_create = false
		restrictedCapabilities.sections.purchase_orders.can_create = false
		await mockWorkspace(permissionPage, [])
		await permissionPage.route("**/api/method/essdee_yrp.fabric_store.web_workspace.get_capabilities*", (route) => route.fulfill({
			status: 200,
			contentType: "application/json",
			body: JSON.stringify({ message: restrictedCapabilities }),
		}))
		await permissionPage.goto(`${SITE}/web/fabric-store/stock-transfers`, { waitUntil: "domcontentloaded" })
		const transfers = permissionPage.locator(".fabric-stock-transfers")
		await transfers.getByRole("button", { name: /Stock Update/ }).click()
		await transfers.locator(".premium-list-table").getByText("STU-FAB-001", { exact: true }).waitFor()
		assert(await transfers.getByRole("button", { name: "Create New", exact: true }).count() === 0, "Create New ignores the operation's create permission")
		await permissionPage.goto(`${SITE}/web/fabric-store/purchase-orders`, { waitUntil: "domcontentloaded" })
		await permissionPage.locator(".fabric-purchase-orders .common-list-view").waitFor()
		assert(await permissionPage.getByRole("button", { name: "Create Purchase Order", exact: true }).count() === 0, "Purchase Order create action ignores DocType permission")
		results.permission = true
	} finally {
		await permissionPage.close()
	}

	return results
}

async function liveDuplicateSuite(page) {
	const missing = await missingLiveFixtures(page, [
		["YRP Work Order", "YRP-WO-2026-00016"],
		["Purchase Order", "YRP-PO-2026-00002"],
		["YRP Goods Received Note", "YRP-GRN-2026-00037"],
		["YRP Delivery Challan", "DC-2026-00036"],
	])
	if (missing.length) {
		return { skipped: true, reason: `Live fixtures are unavailable: ${missing.join(", ")}` }
	}

	const duplicateFromMenu = async (root) => {
		await root.getByRole("button", { name: "More", exact: true }).click()
		await page.locator(".document-action-menu:visible").getByText("Duplicate", { exact: true }).click()
	}
	const assertCleanEditor = async (root, heading) => {
		await root.waitFor({ timeout: 20_000 })
		assert(await root.getByRole("heading", { name: heading, exact: true }).count() === 1, `${heading} did not open after Duplicate`)
		assert(await root.getByText(/Request failed with status|Unable to duplicate/).count() === 0, `${heading} opened with a duplicate error`)
	}

	await page.goto(`${SITE}/web/fabric-store/work-orders/YRP-WO-2026-00016`, { waitUntil: "domcontentloaded" })
	await duplicateFromMenu(page.locator(".fabric-work-order-frame"))
	await page.waitForURL((url) => url.pathname.endsWith("/web/fabric-store/work-orders/new") && url.searchParams.get("duplicate_from") === "YRP-WO-2026-00016")
	await assertCleanEditor(page.locator(".work-order-editor"), "New Work Order")
	await page.locator(".work-order-editor").getByText("Duplicate of YRP-WO-2026-00016", { exact: true }).waitFor()

	await page.goto(`${SITE}/web/fabric-store/purchase-orders/YRP-PO-2026-00002`, { waitUntil: "domcontentloaded" })
	await duplicateFromMenu(page.locator(".fabric-purchase-order-frame"))
	await page.waitForURL((url) => url.pathname.endsWith("/web/fabric-store/purchase-orders/new") && url.searchParams.get("duplicate_from") === "YRP-PO-2026-00002")
	await assertCleanEditor(page.locator(".purchase-order-editor"), "New Purchase Order")
	await page.locator(".purchase-order-editor").getByText("Duplicate of YRP-PO-2026-00002", { exact: true }).waitFor()

	await page.goto(`${SITE}/web/fabric-store/goods-received-notes/YRP-GRN-2026-00037`, { waitUntil: "domcontentloaded" })
	const grn = page.locator(".goods-received-note-workspace")
	await grn.waitFor({ timeout: 20_000 })
	await duplicateFromMenu(grn)
	await page.waitForURL((url) => url.pathname.endsWith("/web/fabric-store/goods-received-notes/new") && url.searchParams.get("duplicate_from") === "YRP-GRN-2026-00037")
	await grn.getByText("Duplicate of YRP-GRN-2026-00037", { exact: true }).waitFor()
	assert(await grn.getByText(/Request failed with status|Unable to duplicate/).count() === 0, "GRN Duplicate opened with an error")

	await page.goto(`${SITE}/web/fabric-store/delivery-challans/DC-2026-00036`, { waitUntil: "domcontentloaded" })
	const dc = page.locator(".delivery-challan-workspace")
	await dc.waitFor({ timeout: 20_000 })
	await duplicateFromMenu(dc)
	await page.waitForURL((url) => url.pathname.endsWith("/web/fabric-store/delivery-challans/new") && url.searchParams.get("duplicate_from") === "DC-2026-00036")
	await dc.getByText("Duplicate of DC-2026-00036", { exact: true }).waitFor()
	assert(await dc.getByText(/Request failed with status|Unable to duplicate/).count() === 0, "Delivery Challan Duplicate opened with an error")

	return { workOrder: true, purchaseOrder: true, goodsReceivedNote: true, deliveryChallan: true }
}

async function liveCompletedPurchaseOrderSuite(page) {
	const missing = await missingLiveFixtures(page, [["Purchase Order", "PO-2627-0968"]])
	if (missing.length) {
		return { skipped: true, reason: `Live fixture is unavailable: ${missing[0]}` }
	}

	await page.goto(`${SITE}/web/fabric-store/purchase-orders/PO-2627-0968`, { waitUntil: "domcontentloaded" })
	const root = page.locator(".fabric-purchase-order-frame")
	await root.waitFor({ timeout: 20_000 })
	await root.getByText("GRN-2627-06302", { exact: true }).waitFor({ timeout: 20_000 })
	for (const name of ["GRN-2627-06302", "GRN-2627-06963"]) {
		assert(await root.locator(".purchase-order-related").getByText(name, { exact: true }).count() === 1, `Completed Purchase Order hides linked GRN ${name}`)
	}
	assert(await root.locator(".item-matrix__received").count() === 0, "Completed Purchase Order still shows Received in item rows")
	assert(await root.locator(".item-matrix__price").filter({ hasText: /^Amount / }).count() === 0, "Completed Purchase Order still shows Amount in item rows")
	assert(await root.locator(".item-matrix__pending").count() > 0, "Completed Purchase Order hides Pending quantity")
	return { purchaseOrder: "PO-2627-0968", goodsReceivedNotes: 2 }
}

const suites = { parity: paritySuite, shell: shellSuite, "mobile-record-details": mobileRecordDetailsSuite, documents: documentsSuite, "work-order": workOrderSuite, "purchase-order": purchaseOrderSuite, "delivery-challan": deliveryChallanSuite, "goods-received-note": goodsReceivedNoteSuite, "stock-transfers": stockTransfersSuite, "document-dialog": documentDialogSuite, states: statesSuite, "live-duplicate": liveDuplicateSuite, "live-completed-purchase-order": liveCompletedPurchaseOrderSuite }
const browser = await chromium.launch({ headless: true })
const context = await browser.newContext()

try {
	const loginPage = await context.newPage()
	await login(loginPage)
	await loginPage.close()
	const selected = suite === "all" ? Object.keys(suites) : [suite]
	const results = {}
	for (const name of selected) {
		assert(suites[name], `Unknown suite: ${name}`)
		const page = await context.newPage()
		const errors = []
		page.on("pageerror", (error) => errors.push(error.message))
		page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()) })
		page.on("response", (response) => { if (response.status() >= 400) errors.push(`${response.status()} ${response.url()}`) })
		try {
			results[name] = await suites[name](page)
			assert(errors.length === 0, `${name} browser errors detected:\n${errors.join("\n")}`)
		} finally {
			await page.close()
		}
	}
	console.log(JSON.stringify({ passed: true, suites: results }, null, 2))
} finally {
	await browser.close()
}
