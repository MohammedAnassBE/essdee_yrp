#!/usr/bin/env node

import { createRequire } from "node:module"
import { readFileSync } from "node:fs"

const require = createRequire("/home/anas/.claude/playwright/package.json")
const { chromium } = require("playwright")

const SITE = "http://erp-migration-test.site:8001"
const CREDENTIALS = "/home/anas/.frappe-debug-creds-mrp3"
const LEGACY_GRN = "GRN-2425-04556"
const LOT = "Lot-44"

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
page.on("pageerror", (error) => pageErrors.push(error.message))

try {
	await login(page)

	await page.goto(`${SITE}/app/yrp-goods-received-note/${LEGACY_GRN}`, {
		waitUntil: "domcontentloaded",
	})
	await waitForForm(page, "YRP Goods Received Note", LEGACY_GRN)
	await page.waitForTimeout(2_000)
	const legacyState = await page.evaluate(() => ({
		hasActualDiaButton: [...document.querySelectorAll("button")]
			.some((button) => button.textContent.trim() === "Add Actual Dia"),
		hasRuntime: Boolean(
			window.essdee_yrp?.open_actual_dia_dialog
			&& window.frappe?.yrp?.work_order?.ItemEditor,
		),
	}))
	assert(legacyState.hasRuntime, "Cloth Desk runtime did not load on the GRN form")
	assert(!legacyState.hasActualDiaButton, "Legacy GRN incorrectly exposes Add Actual Dia")

	const guardState = await page.evaluate(() => {
		const originalCall = frappe.call
		const originalMount = essdee_yrp.mount_physical_grn_editor
		let calls = 0
		let mounted = 0
		const run = (doc, context) => {
			const buttons = []
			frappe.call = (options) => {
				calls += 1
				options.callback({ message: context })
			}
			essdee_yrp.mount_physical_grn_editor = () => { mounted += 1 }
			const frm = {
				doc,
				add_custom_button(label, action, group) { buttons.push({ label, action, group }) },
			}
			essdee_yrp.configure_actual_dia_button(frm)
			return buttons.map((button) => [button.label, button.group])
		}
		const normal = run(
			{ against: "YRP Work Order", against_id: "WO-E2E", docstatus: 0 },
			{ enabled: true, dia_options: ["30 Dia", "32 Dia"] },
		)
		const disabled = run(
			{ against: "YRP Work Order", against_id: "WO-LEGACY", docstatus: 0 },
			{ enabled: false, dia_options: [] },
		)
		const beforeAdditional = calls
		const additional = run(
			{
				against: "YRP Work Order",
				against_id: "WO-E2E",
				docstatus: 0,
				additional_grn: 1,
			},
			{ enabled: true, dia_options: ["30 Dia", "32 Dia"] },
		)
		frappe.call = originalCall
		essdee_yrp.mount_physical_grn_editor = originalMount
		return {
			normal,
			disabled,
			additional,
			additionalSkippedServer: calls === beforeAdditional,
			mounted,
		}
	})
	assert(
		guardState.normal.some(([label, group]) => label === "Add Actual Dia" && group === "Actual Dia"),
		"Versioned standard Knitting context did not expose Add Actual Dia",
	)
	assert(guardState.disabled.length === 0, "Disabled/legacy context exposed Add Actual Dia")
	assert(guardState.additional.length === 0, "Additional GRN exposed Add Actual Dia")
	assert(guardState.additionalSkippedServer, "Additional GRN queried Actual Dia context")
	assert(guardState.mounted === 1, `Physical editor mounted an unexpected number of times: ${guardState.mounted}`)

	await page.evaluate(() => {
		const host = document.createElement("div")
		host.id = "cloth-e2e-received-types"
		host.style.cssText = "position:fixed;inset:70px 30px 30px;z-index:1100;background:white;overflow:auto;padding:16px"
		document.body.appendChild(host)
		window.__clothE2EGroups = [{
			primary_attribute_values: [],
			items: [
				{
					name: "CLOTH-E2E",
					attributes: { Colour: "Navy", Dia: "30 Dia" },
					dimensions: { received_type: "Accepted" },
					values: { default: { qty: 0, pending_quantity: 10, max_receivable_quantity: 10, ref_docname: "WOR-E2E-1" } },
				},
				{
					name: "CLOTH-E2E",
					attributes: { Colour: "Navy", Dia: "30 Dia" },
					dimensions: { received_type: "Accepted" },
					values: { default: { qty: 0, pending_quantity: 8, max_receivable_quantity: 8, ref_docname: "WOR-E2E-2" } },
				},
			],
		}]
		window.__clothE2EEditor = new frappe.yrp.work_order.ItemEditor(host, {
			title: "Cloth E2E Received Types",
			editorType: "goods_received_note",
			sourceType: "YRP Work Order",
			showDimensions: true,
			allowCreate: false,
			allowEdit: false,
			allowRemove: false,
			allowExcess: true,
			aggregatePhysicalRows: true,
		})
		window.__clothE2EEditor.load_data(window.__clothE2EGroups)
	})
	const editor = page.locator("#cloth-e2e-received-types")
	await editor.locator(".grn-receive-block").first().waitFor({ timeout: 20_000 })
	assert(
		await editor.locator(".grn-receive-block").count() === 2,
		"Different receivable references collapsed into one Desk row",
	)
	const firstBlock = editor.locator(".grn-receive-block").first()
	const rejectedButton = firstBlock.locator(".grn-rt-add").filter({ hasText: "+ Rejected" })
	await rejectedButton.waitFor({ timeout: 20_000 })
	await rejectedButton.click()
	await page.waitForFunction(() => window.__clothE2EEditor.get_items()[0].items.length === 3)
	const receivedTypeState = await page.evaluate(() => {
		const items = window.__clothE2EEditor.get_items()[0].items
		const rejected = items.find((entry) => entry.dimensions?.received_type === "Rejected")
		return {
			count: items.length,
			reference: rejected?.values?.default?.ref_docname,
			qty: rejected?.values?.default?.qty,
		}
	})
	assert(receivedTypeState.count === 3, "Received Type row was not added")
	assert(receivedTypeState.reference === "WOR-E2E-1", "Received Type row lost exact receivable lineage")
	assert(Number(receivedTypeState.qty) === 0, "New Received Type row did not start at zero")
	await page.evaluate(() => {
		window.__clothE2EEditor.app.unmount()
		document.querySelector("#cloth-e2e-received-types")?.remove()
	})

	await page.evaluate(() => {
		window.__actualDiaGroups = [{
			primary_attribute_values: [],
			items: [{
				name: "CLOTH-E2E",
				attributes: { Colour: "Navy", Dia: "30 Dia" },
				dimensions: { received_type: "Accepted" },
				values: { default: { qty: 4, pending_quantity: 10, max_receivable_quantity: 10, ref_docname: "WOR-E2E-1" } },
			}],
		}]
		window.__actualDiaFrm = {
			doc: {},
			_essdee_actual_dia: { enabled: true, dia_options: ["30 Dia", "32 Dia"] },
			itemEditor: {
				get_items: () => window.__actualDiaGroups,
				load_data: (data) => { window.__actualDiaGroups = data },
			},
			dirty: () => { window.__actualDiaDirty = true },
		}
		essdee_yrp.open_actual_dia_dialog(window.__actualDiaFrm)
	})
	const dialog = page.locator(".modal-dialog:visible").filter({ hasText: "Add Actual Dia Receipt" })
	await dialog.waitFor({ timeout: 20_000 })
	await dialog.getByRole("button", { name: "Add Dia Row", exact: true }).click()
	await page.waitForFunction(() => window.__actualDiaGroups[0].items.length === 2)
	const actualDiaState = await page.evaluate(() => {
		const row = window.__actualDiaGroups[0].items[1]
		return {
			dia: row.attributes.Dia,
			reference: row.values.default.ref_docname,
			quantity: row.values.default.qty,
			dirty: Boolean(window.__actualDiaDirty),
			serialized: JSON.parse(window.__actualDiaFrm.doc.item_details).length,
		}
	})
	assert(actualDiaState.dia === "32 Dia", `Unexpected Actual Dia: ${actualDiaState.dia}`)
	assert(actualDiaState.reference === "WOR-E2E-1", "Actual Dia row lost exact receivable lineage")
	assert(actualDiaState.quantity === 6, `Unexpected Actual Dia default quantity: ${actualDiaState.quantity}`)
	assert(actualDiaState.dirty, "Actual Dia addition did not mark the GRN dirty")
	assert(actualDiaState.serialized === 1, "Actual Dia addition did not serialize grouped items")

	await page.goto(`${SITE}/app/sd-yrp-lot/${encodeURIComponent(LOT)}`, {
		waitUntil: "domcontentloaded",
	})
	await waitForForm(page, "SD YRP Lot", LOT)
	await page.locator(".form-tabs .nav-link")
		.filter({ hasText: "Actual Dia Conversions" })
		.click()
	const conversionHeading = page.getByRole("heading", { name: "Actual Dia Conversions", exact: true })
	await conversionHeading.waitFor({ timeout: 10_000 }).catch(() => {})
	const lotDiagnostics = await page.evaluate(() => {
		const field = cur_frm.fields_dict.actual_dia_conversion_html
		const wrapper = field?.wrapper
		return {
			hasField: Boolean(field),
			hasInstance: Boolean(cur_frm.actual_dia_conversions),
			wrapperVisible: Boolean(wrapper && wrapper.offsetParent !== null),
			wrapperText: wrapper?.textContent?.trim().slice(0, 160) || "",
			activeTab: document.querySelector(".form-tabs .nav-link.active")?.textContent?.trim() || "",
			tabs: [...document.querySelectorAll(".form-tabs .nav-link")].map((tab) => tab.textContent.trim()),
		}
	})
	assert(
		await conversionHeading.isVisible(),
		`Lot Actual Dia conversion Desk island is not visible: ${JSON.stringify(lotDiagnostics)}`,
	)

	assert(pageErrors.length === 0, `Desk page errors: ${JSON.stringify(pageErrors)}`)
	console.log(JSON.stringify({
		passed: true,
		legacyGrn: LEGACY_GRN,
		lot: LOT,
		guards: guardState,
		receivedType: receivedTypeState,
		actualDia: actualDiaState,
		lotConversionIsland: true,
	}, null, 2))
} finally {
	await context.close()
	await browser.close()
}
