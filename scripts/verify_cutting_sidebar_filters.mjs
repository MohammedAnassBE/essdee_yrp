#!/usr/bin/env node

import { createRequire } from 'node:module'
import { mkdirSync, readFileSync } from 'node:fs'

const require = createRequire('/home/anas/.claude/playwright/package.json')
const { chromium } = require('playwright')
const SITE = 'http://erp-migration-test.site:8001'
const OUT = '/home/anas/pilot/benches/frappe-16/apps/essdee_yrp/design-references/cutting-sidebar-filters'
const [usr, pwd] = readFileSync('/home/anas/.frappe-debug-creds-mrp3', 'utf8').trim().split('\n')
mkdirSync(OUT, { recursive: true })

const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({ viewport: { width: 1600, height: 1000 } })
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

const planList = await context.request.get(`${SITE}/api/resource/SD%20YRP%20Cutting%20Plan`, {
	params: {
		fields: JSON.stringify(['name']),
		order_by: 'modified desc',
		limit_page_length: 100,
	},
})
const planNames = (await planList.json()).data || []
let selectedPlan = ''
for (const { name } of planNames) {
	const response = await context.request.get(`${SITE}/api/method/essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan.sd_yrp_cutting_plan.get_web_view_data`, {
		params: { cutting_plan: name },
	})
	if (response.status() === 404) continue
	if (!response.ok()) throw new Error(`Unable to inspect Cutting Plan ${name} (${response.status()}).`)
	const data = (await response.json()).message || {}
	if (data.markers?.length && data.laysheets?.length) {
		selectedPlan = name
		break
	}
}
if (!selectedPlan) {
	console.log(JSON.stringify({
		passed: true,
		skipped: true,
		reason: 'No Cutting Plan with both markers and Lay Sheets is available on the current site.',
	}, null, 2))
	await browser.close()
	process.exit(0)
}

await page.goto(`${SITE}/web/cutting/plans/${encodeURIComponent(selectedPlan)}`, { waitUntil: 'domcontentloaded' })
await page.waitForSelector('.laysheet-card', { timeout: 20000 })
await page.waitForTimeout(600)

const mainScreenshot = `${OUT}/01-panels-and-filter-buttons.png`
await page.screenshot({ path: mainScreenshot, fullPage: true })
const laySheetCardsBeforeFilter = await page.locator('.laysheet-card').count()
const laySheetPanelChipCountBeforeFilter = await page.locator('.laysheet-card .panel-chips span').count()

const filterButtons = page.locator('.rail-filter-button')
await filterButtons.nth(1).click()
await page.waitForSelector('.p-dialog')
await page.getByRole('button', { name: 'Add a Filter', exact: true }).click()
const dialog = page.locator('.p-dialog')
await dialog.locator('.p-select').nth(0).click()
await page.getByRole('option', { name: 'Status', exact: true }).click()
await dialog.locator('.p-select').nth(1).click()
await page.getByRole('option', { name: 'Equals', exact: true }).click()
await dialog.locator('.p-select').nth(2).click()
await page.getByRole('option', { name: 'Started', exact: true }).click()
const filterScreenshot = `${OUT}/02-laysheet-filter-dialog.png`
await page.screenshot({ path: filterScreenshot, fullPage: true })
await dialog.getByRole('button', { name: 'Apply Filters', exact: true }).click()
await page.waitForTimeout(250)
const filteredCards = await page.locator('.laysheet-card').count()
const filterCountText = await page.locator('.laysheet-section .rail-heading h3 span').textContent()
const appliedScreenshot = `${OUT}/03-laysheet-filter-applied.png`
await page.screenshot({ path: appliedScreenshot, fullPage: true })

await filterButtons.nth(1).click()
await page.locator('.p-dialog').getByRole('button', { name: 'Clear Filters', exact: true }).click()
await page.waitForTimeout(250)

const results = {
	selectedPlan,
	filterButtonCount: await filterButtons.count(),
	laySheetCardsBeforeFilter,
	laySheetPanelChipCountBeforeFilter,
	filteredCards,
	filterCountText,
	clearRestoredAllCards: await page.locator('.laysheet-card').count() === laySheetCardsBeforeFilter,
	screenshots: [mainScreenshot, filterScreenshot, appliedScreenshot],
	errors,
}
console.log(JSON.stringify(results, null, 2))
await browser.close()
