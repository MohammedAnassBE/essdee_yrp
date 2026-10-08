#!/usr/bin/env node

import { createRequire } from "node:module"
import { readFileSync } from "node:fs"

const require = createRequire("/home/anas/.claude/playwright/package.json")
const { chromium } = require("playwright")

const SITE = process.env.ESSDEE_TEST_SITE || "http://erp-migration-test.site:8001"
const PURCHASE_ORDER = process.env.ESSDEE_PO_REGRESSION || "PO-2627-1083"
const CREDENTIALS = "/home/anas/.frappe-debug-creds-mrp3"
const WORKSPACE_METHOD = "essdee_yrp.fabric_store.web_workspace"

function assert(condition, message) {
	if (!condition) throw new Error(message)
}

function displayDate(isoDate) {
	const [year, month, day] = String(isoDate || "").split("-")
	return `${day}-${month}-${year}`
}

function addDays(isoDate, days) {
	const date = new Date(`${isoDate}T00:00:00`)
	date.setDate(date.getDate() + days)
	return [date.getFullYear(), date.getMonth() + 1, date.getDate()]
		.map((value, index) => index ? String(value).padStart(2, "0") : String(value))
		.join("-")
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

async function selectAutocompleteOption(page, field, value) {
	const input = field.locator(".p-autocomplete-input")
	await input.fill(value)
	const option = page.locator(".p-autocomplete-option:visible").filter({ hasText: value }).first()
	await option.waitFor({ timeout: 20_000 })
	await option.click()
}

async function callMethod(page, method, args) {
	return page.evaluate(async ({ methodName, methodArgs }) => {
		const response = await fetch(`/api/method/${methodName}`, {
			method: "POST",
			credentials: "include",
			headers: {
				Accept: "application/json",
				"Content-Type": "application/json",
				"X-Frappe-CSRF-Token": window.csrf_token || window.frappe?.csrf_token || "",
			},
			body: JSON.stringify(methodArgs),
		})
		return { status: response.status, payload: await response.json() }
	}, { methodName: method, methodArgs: args })
}

const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({ viewport: { width: 1600, height: 1000 } })
const page = await context.newPage()

try {
	await login(page)

	const editorResponse = await callMethod(page, `${WORKSPACE_METHOD}.get_purchase_order_editor`, { purchase_order: PURCHASE_ORDER })
	assert(editorResponse.status === 200, `Could not load live Purchase Order ${PURCHASE_ORDER}: HTTP ${editorResponse.status}`)
	const editorPayload = editorResponse.payload
	const editor = editorPayload.message || {}
	const firstItem = editor.item_groups?.[0]?.items?.[0]
	assert(editor.name === PURCHASE_ORDER && firstItem, `Live Purchase Order fixture is incomplete: ${PURCHASE_ORDER}`)

	const safeRequiredBy = addDays(editor.values.transaction_date, 7)
	const values = {
		...editor.values,
		schedule_date: safeRequiredBy,
		set_warehouse: editor.values.set_warehouse || editor.values.default_delivery_location,
		item_details: editor.item_groups,
	}
	const saveResponse = await callMethod(
		page,
		`${WORKSPACE_METHOD}.save_purchase_order`,
		{
			purchase_order: PURCHASE_ORDER,
			values,
			submit: false,
			expected_modified: editor.modified,
		},
	)
	const savePayload = saveResponse.payload
	const saveText = JSON.stringify(savePayload)
	assert(!saveText.includes("'dict' object has no attribute"), `Live save still has the dictionary-row crash: ${saveText}`)
	assert(
		saveText.includes("has Required By") && saveText.includes("before Order Date"),
		`Live server did not return the item/date validation: HTTP ${saveResponse.status} ${saveText}`,
	)

	await page.goto(`${SITE}/web/fabric-store/purchase-orders/${encodeURIComponent(PURCHASE_ORDER)}/edit`, { waitUntil: "domcontentloaded" })
	const purchaseOrderEditor = page.locator(".purchase-order-editor")
	await purchaseOrderEditor.waitFor({ timeout: 20_000 })
	const requiredBy = purchaseOrderEditor.locator(".purchase-order-editor__date .p-datepicker-input").nth(1)
	await requiredBy.fill(displayDate(safeRequiredBy))
	await requiredBy.press("Tab")

	const warehouse = purchaseOrderEditor.locator(".common-field").filter({ hasText: "Delivery warehouse *" })
	if (!await warehouse.locator(".p-autocomplete-input").inputValue()) {
		await selectAutocompleteOption(page, warehouse, editor.values.default_delivery_location)
	}
	const saveButton = purchaseOrderEditor.getByRole("button", { name: "Save", exact: true })
	await saveButton.click()
	const dialog = page.getByRole("dialog", { name: "Purchase Order could not be saved" })
	await dialog.waitFor({ timeout: 20_000 })
	const dialogText = await dialog.innerText()
	assert(!dialogText.includes("'dict' object has no attribute"), `UI exposed the dictionary-row crash: ${dialogText}`)
	assert(dialogText.includes("has Required By") && dialogText.includes("before Order Date"), `UI did not explain the invalid item date: ${dialogText}`)

	console.log(JSON.stringify({
		passed: true,
		purchaseOrder: PURCHASE_ORDER,
		serverValidation: "item/date error returned without mutation",
		uiValidation: "clear Purchase Order popup shown",
	}, null, 2))
} finally {
	await browser.close()
}
