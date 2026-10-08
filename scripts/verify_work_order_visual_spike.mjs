#!/usr/bin/env node

import { spawn } from "node:child_process"
import { createRequire } from "node:module"
import { fileURLToPath } from "node:url"
import { dirname, resolve } from "node:path"
import { createServer } from "node:net"

const require = createRequire("/home/anas/.claude/playwright/package.json")
const { chromium } = require("playwright")

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..")
const PORT = await findFreePort()
const BASE_URL = `http://127.0.0.1:${PORT}`
const SCREENSHOT = "/tmp/essdee-yrp-work-order-visual-spike.png"

async function findFreePort() {
	const server = createServer()
	await new Promise((resolveReady, reject) => {
		server.once("error", reject)
		server.listen(0, "127.0.0.1", resolveReady)
	})
	const { port } = server.address()
	await new Promise((resolveClosed, reject) => server.close((error) => error ? reject(error) : resolveClosed()))
	return port
}

function assert(condition, message) {
	if (!condition) throw new Error(message)
}

function group(item, lot, quantity) {
	return {
		attributes: ["Colour"],
		primary_attribute: "Dia",
		primary_attribute_values: ["19 Dia", "14 Dia", "14.5 Dia"],
		items: [{
			name: item,
			dimensions: { lot },
			attributes: { Colour: "White" },
			values: {
				"19 Dia": { qty: quantity[0], delivered: 0, received: 0, pending_qty: quantity[0] },
				"14 Dia": { qty: quantity[1], delivered: 0, received: 0, pending_qty: quantity[1] },
				"14.5 Dia": { qty: quantity[2], delivered: 0, received: 0, pending_qty: quantity[2] },
			},
			total_qty: quantity.reduce((total, value) => total + value, 0),
			default_uom: "Kg",
		}],
	}
}

const deliverable = group("Cotton Poly 58/42 Jersey Fabric", "F0926-49", [25, 29, 20])
const receivable = group("Cotton Poly 58/42 Jersey Fabric - Washed", "F0926-49", [24, 28, 19])
const payload = {
	record: {
		doctype: "YRP Work Order",
		name: "YRP-WO-2026-00003",
		docstatus: 1,
		status: "Fully Received",
		supplier: "ESSDEE-IRONING-UNIT",
		supplier_name: "Essdee Ironing Unit - Tirupur",
		process_name: "Washing",
		item: "Cotton Poly 58/42 Jersey Fabric",
		lot: "F0926-49",
		production_detail: "Cotton Poly 58/42 Jersey Fabric-1",
		open_status: "Open",
		permissions: { can_read: true, can_write: true },
	},
	fields: [
		{ fieldname: "status", label: "Status", fieldtype: "Select", value: "Fully Received" },
		{ fieldname: "naming_series", label: "WO Series", fieldtype: "Select", value: "YRP-WO-.YYYY.-" },
		{ fieldname: "wo_date", label: "WO Date", fieldtype: "Date", value: "2026-10-08" },
		{ fieldname: "supplier", label: "Supplier", fieldtype: "Link", value: "ESSDEE-IRONING-UNIT" },
		{ fieldname: "supplier_name", label: "Supplier Name", fieldtype: "Data", value: "Essdee Ironing Unit - Tirupur" },
		{ fieldname: "includes_packing", label: "Includes Packing", fieldtype: "Check", value: 0 },
		{ fieldname: "no_receivables", label: "No Receivables", fieldtype: "Check", value: 0 },
		{ fieldname: "process_name", label: "Process", fieldtype: "Link", value: "Washing" },
		{ fieldname: "lot", label: "Lot", fieldtype: "Link", value: "F0926-49" },
		{ fieldname: "item", label: "Item", fieldtype: "Link", value: "Cotton Poly 58/42 Jersey Fabric" },
		{ fieldname: "production_detail", label: "Production Detail", fieldtype: "Link", value: "Cotton Poly 58/42 Jersey Fabric-1" },
		{ fieldname: "delivery_location", label: "Delivery Location", fieldtype: "Link", value: "S-0005" },
		{ fieldname: "delivery_location_name", label: "Delivery Location Name", fieldtype: "Data", value: "Essdee Fabric Store - Tirupur" },
		{ fieldname: "planned_start_date", label: "Planned Start Date", fieldtype: "Date", value: "2026-10-08" },
		{ fieldname: "planned_end_date", label: "Planned End Date", fieldtype: "Date", value: "2026-10-15" },
		{ fieldname: "expected_delivery_date", label: "Expected Delivery Date", fieldtype: "Date", value: "2026-10-15" },
		{ fieldname: "start_date", label: "Start Date", fieldtype: "Date", value: "2026-10-08" },
		{ fieldname: "end_date", label: "End Date", fieldtype: "Date", value: "2026-10-08" },
		{ fieldname: "supplier_address", label: "Supplier Address", fieldtype: "Link", value: "Essdee Knitting Mills Private Limited-Billing-4" },
		{ fieldname: "delivery_address", label: "Delivery Address", fieldtype: "Link", value: "Essdee Knitting Mills Private Limited-Billing" },
		{ fieldname: "open_status", label: "Open Status", fieldtype: "Select", value: "Open" },
		{ fieldname: "is_rework", label: "Is Rework", fieldtype: "Check", value: 0 },
		{ fieldname: "supplier_type", label: "Supplier Type", fieldtype: "Select", value: "Same Supplier" },
		{ fieldname: "comments", label: "Comments", fieldtype: "Small Text", value: "QA cloth flow test - safe to delete" },
	],
	dimensions: [{ fieldname: "received_type", label: "Received Type", fieldtype: "Link", value: "Accepted" }],
	totals: [
		{ fieldname: "planned_quantity", label: "Planned Quantity", value: 74 },
		{ fieldname: "total_quantity", label: "Total Quantity", value: 74 },
		{ fieldname: "total_no_of_pieces_delivered", label: "Pieces Delivered", value: 0 },
		{ fieldname: "total_no_of_pieces_received", label: "Pieces Received", value: 0 },
	],
	matrices: { deliverables: [deliverable], receivables: [receivable] },
	summary: { item_detail: [deliverable], deliverables: [], work_order_docstatus: 1 },
	related: {
		delivery_challans: [{ name: "DC-2026-00003", docstatus: 1, status: "Submitted", item: "Cotton Poly 58/42 Jersey Fabric", lot: "F0926-49", posting_date: "2026-10-08", posting_time: "10:49:00" }],
		goods_received_notes: [{ name: "YRP-GRN-2026-00005", docstatus: 1, status: "Submitted", item: "Cotton Poly 58/42 Jersey Fabric", lot: "F0926-49", posting_date: "2026-10-08", posting_time: "10:49:00" }],
	},
	permissions: { can_read: true, can_write: true, can_print: false },
	capabilities: {
		create_delivery_challan: { label: "Make DC", source_context: { work_order: "YRP-WO-2026-00003" } },
		create_goods_received_note: { label: "Make GRN", source_context: { work_order: "YRP-WO-2026-00003" } },
	},
	related_permissions: {
		delivery_challan: { can_read: true, can_create: true },
		goods_received_note: { can_read: true, can_create: true },
	},
}

async function waitForServer() {
	for (let attempt = 0; attempt < 80; attempt += 1) {
		try {
			const response = await fetch(`${BASE_URL}/web/`)
			if (response.ok) return
		} catch {}
		await new Promise((resolve) => setTimeout(resolve, 125))
	}
	throw new Error("Vite did not start in time.")
}

const vite = spawn(resolve(ROOT, "frontend/node_modules/.bin/vite"), ["--host", "127.0.0.1", "--port", String(PORT), "--strictPort"], {
	cwd: resolve(ROOT, "frontend"),
	stdio: ["ignore", "pipe", "pipe"],
})

async function stopVite() {
	if (vite.exitCode !== null) return
	const exited = new Promise((resolveExit) => vite.once("exit", resolveExit))
	vite.kill("SIGTERM")
	const forceKill = setTimeout(() => {
		if (vite.exitCode === null) vite.kill("SIGKILL")
	}, 1_500)
	await exited
	clearTimeout(forceKill)
}

let browser
try {
	await waitForServer()
	browser = await chromium.launch({ headless: true })
	const page = await browser.newPage({ viewport: { width: 1848, height: 1016 }, deviceScaleFactor: 1 })
	await page.addInitScript(() => {
		window.csrf_token = "visual-spike"
		window.frappe = {
			boot: { user: { name: "Administrator", can_read: ["YRP Work Order"] } },
			session: { user: "Administrator" },
		}
	})
	await page.route("**/api/method/essdee_yrp.fabric_store.web_workspace.get_work_order_workspace*", (route) => route.fulfill({
		status: 200,
		contentType: "application/json",
		body: JSON.stringify({ message: payload }),
	}))

	await page.goto(`${BASE_URL}/web/fabric-store/work-orders/YRP-WO-2026-00003`, { waitUntil: "domcontentloaded" })
	const frame = page.locator(".fabric-work-order-frame")
	await frame.waitFor({ timeout: 20_000 })

	const identity = frame.locator(".work-order-page__identity")
	assert(await identity.getByRole("heading", { name: "F0926-49 · Cotton Poly 58/42 Jersey Fabric", exact: true }).count() === 1, "The header does not lead with the Lot and Work Order item.")
	assert(await identity.getByText("WO date", { exact: true }).count() === 1, "The Work Order date label is missing from the header.")
	assert(await identity.getByText("08-10-2026", { exact: true }).count() === 1, "The Work Order date is missing from the header.")
	for (const removedHeaderFact of ["Process", "Job worker", "Planned qty"]) {
		assert(await identity.getByText(removedHeaderFact, { exact: true }).count() === 0, `${removedHeaderFact} still appears in the compact header.`)
	}
	assert(JSON.stringify(await frame.locator(".work-order-tabs").getByRole("tab").allTextContents()) === JSON.stringify(["Overview", "Deliverables 1", "Receivables 1", "Summary"]), "The Work Order does not expose the planned business tabs.")
	for (const heading of ["Order identity", "Schedule", "Supplier & delivery", "Status & notes", "Stock dimensions"]) {
		assert(await frame.getByRole("heading", { name: heading, exact: true }).count() === 1, `The Overview is missing ${heading}.`)
	}
	const cardPositions = {}
	for (const heading of ["Order identity", "Supplier & delivery", "Schedule", "Status & notes"]) {
		cardPositions[heading] = await frame.getByRole("heading", { name: heading, exact: true }).locator("xpath=ancestor::section[1]").boundingBox()
	}
	assert(
		Math.abs(cardPositions["Order identity"].y - cardPositions["Supplier & delivery"].y) < 2
			&& Math.abs(cardPositions.Schedule.y - cardPositions["Status & notes"].y) < 2
			&& cardPositions["Order identity"].y < cardPositions.Schedule.y,
		`The Overview cards are not ordered as Identity/Delivery then Schedule/Status: ${JSON.stringify(cardPositions)}`,
	)
	assert(await frame.getByText("Process", { exact: true }).count() === 1, "Process is missing from the Order identity section or repeated elsewhere.")
	assert(await frame.getByText("Job worker", { exact: true }).count() === 1, "Job worker is missing from Supplier & delivery or repeated elsewhere.")
	assert(await frame.getByText("WO date", { exact: true }).count() === 1, "WO date is repeated outside the header.")
	assert(await frame.getByText("Planned Quantity", { exact: true }).count() === 1, "Planned Quantity is missing from the right-side quantity summary or repeated elsewhere.")
	assert(await frame.getByRole("button", { name: "Make DC", exact: true }).count() === 1, "Make DC disappeared during the redesign.")
	assert(await frame.getByRole("button", { name: "Make GRN", exact: true }).count() === 1, "Make GRN disappeared during the redesign.")
	assert(await frame.getByRole("heading", { name: "Delivery Challans", exact: true }).count() === 1, "The Delivery Challan rail disappeared.")
	assert(await frame.getByRole("heading", { name: "Goods Received Notes", exact: true }).count() === 1, "The GRN rail disappeared.")

	await frame.getByRole("tab", { name: "Deliverables 1", exact: true }).click()
	assert(await frame.getByRole("heading", { name: "Deliverables", exact: true }).count() === 1, "The Deliverables matrix is not isolated in its tab.")
	await frame.getByRole("tab", { name: "Receivables 1", exact: true }).click()
	assert(await frame.getByRole("heading", { name: "Receivables", exact: true }).count() === 1, "The Receivables matrix is not isolated in its tab.")

	await frame.getByRole("tab", { name: "Overview", exact: true }).click()
	await page.screenshot({ path: SCREENSHOT, fullPage: true })
	console.log(`Work Order visual spike verified. Screenshot: ${SCREENSHOT}`)
} finally {
	await browser?.close()
	await stopVite()
}
