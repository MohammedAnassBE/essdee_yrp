#!/usr/bin/env node

import { createRequire } from 'node:module'
import { mkdirSync, readFileSync } from 'node:fs'

const require = createRequire('/home/anas/.claude/playwright/package.json')
const { chromium } = require('playwright')

const SITE = 'http://erp-migration-test.site:8001'
const PLAN = process.argv[2] || 'CP-2609-00007'
const OUT = '/home/anas/pilot/benches/frappe-16/apps/essdee_yrp/design-references/cutting-stock-workflows'
const [usr, pwd] = readFileSync('/home/anas/.frappe-debug-creds-mrp3', 'utf8').trim().split('\n')
mkdirSync(OUT, { recursive: true })

const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 1 })
const page = await context.newPage()
const errors = []
page.on('pageerror', (error) => errors.push(`page: ${error.message}`))
page.on('console', (message) => { if (message.type() === 'error') errors.push(`console: ${message.text()}`) })

await page.goto(`${SITE}/login`, { waitUntil: 'domcontentloaded' })
await page.fill('#login_email', usr.trim())
await page.fill('#login_password', pwd.trim())
await Promise.all([
	page.waitForNavigation({ waitUntil: 'domcontentloaded', timeout: 20000 }).catch(() => {}),
	page.click('.btn-login, button[type=submit]'),
])
await page.goto(`${SITE}/web/cutting/plans/${encodeURIComponent(PLAN)}`, { waitUntil: 'domcontentloaded' })
await page.waitForTimeout(3500)
await page.getByRole('tab', { name: 'Stock Transfers' }).click()
await page.waitForTimeout(1800)

async function screenshot(name) {
	// Capture the resting interface, not PrimeVue's dialog entrance frame.
	await page.waitForTimeout(350)
	const path = `${OUT}/${name}.png`
	await page.screenshot({ path, fullPage: true })
	return path
}

async function chooseOperation(name) {
	await page.locator('.erp-activity-card', { hasText: name }).click()
	await page.waitForTimeout(400)
}

async function closeDialog() {
	await page.locator('.p-dialog:visible .p-dialog-footer button').filter({ hasText: 'Close' }).click()
	await page.waitForTimeout(250)
}

const results = {}
results.workspace = await screenshot('01-stock-transfers')

await chooseOperation('Stock Entry')
await page.getByRole('button', { name: 'Plan Stock Entry' }).click()
await page.waitForSelector('.p-dialog:visible .stock-composer')
results.stockEntryPurposeSelect = await page.locator('.p-dialog:visible .erp-select-field .p-select').count()
results.stockEntry = await screenshot('02-stock-entry-purpose-select')
await closeDialog()

await chooseOperation('Stock Update')
await page.getByRole('button', { name: 'New Stock Update' }).click()
await page.waitForSelector('.p-dialog:visible .stock-composer')
results.stockUpdateSelect = await page.locator('.p-dialog:visible .erp-select-field .p-select').count()
results.stockUpdate = await screenshot('03-stock-update-manual-entry')
await closeDialog()

await chooseOperation('Lot Transfer')
await page.getByRole('button', { name: 'New Lot Transfer' }).click()
await page.waitForSelector('.p-dialog:visible .stock-composer')
results.lotTransferFields = await page.locator('.p-dialog:visible .stock-composer__fields .common-field').allTextContents()
results.lotTransfer = await screenshot('04-lot-transfer-manual-entry')
await closeDialog()

await chooseOperation('Delivery Challan')
results.deliveryButtons = await page.locator('.erp-create-actions button').allTextContents()
await page.getByRole('button', { name: 'From Work Order' }).click()
await page.waitForSelector('.p-dialog:visible .wo-delivery-matrix')
results.deliveryInputs = await page.locator('.p-dialog:visible .wo-delivery-matrix input[type=number]').count()
results.workOrderDelivery = await screenshot('05-delivery-challan-work-order')
results.dialogStyles = await page.evaluate(() => {
	const dialog = [...document.querySelectorAll('.p-dialog')].find((element) => element.offsetParent !== null)
	const content = dialog?.querySelector('.p-dialog-content')
	const mask = dialog?.closest('.p-dialog-mask')
	const pick = (element) => element ? {
		background: getComputedStyle(element).background,
		opacity: getComputedStyle(element).opacity,
		backdropFilter: getComputedStyle(element).backdropFilter,
	} : null
	return { dialog: pick(dialog), content: pick(content), mask: pick(mask) }
})

results.errors = errors
console.log(JSON.stringify(results, null, 2))
await browser.close()
