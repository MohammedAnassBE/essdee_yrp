#!/usr/bin/env node

import { createRequire } from 'node:module'
import { mkdirSync, readFileSync } from 'node:fs'

const require = createRequire('/home/anas/.claude/playwright/package.json')
const { chromium } = require('playwright')
const SITE = 'http://erp-migration-test.site:8001'
const OUT = '/home/anas/pilot/benches/frappe-16/apps/essdee_yrp/design-references/cutting-reports-clean'
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
await page.goto(`${SITE}/web/cutting/reports`, { waitUntil: 'domcontentloaded' })
await page.waitForTimeout(2500)

const tabs = [
	['Daily Production', '01-daily-production'],
	['Daily Cut Sheet', '02-daily-cut-sheet'],
	['Multi CCR', '03-multi-ccr'],
	['Cutting Detail', '04-cutting-detail'],
	['Stock Balance', '05-stock-balance'],
]
const results = { screenshots: {}, errors }
for (const [label, name] of tabs) {
	await page.getByRole('tab', { name: label }).click()
	await page.waitForTimeout(350)
	const path = `${OUT}/${name}.png`
	await page.screenshot({ path, fullPage: true })
	results.screenshots[label] = path
}
results.outerHeaderCount = await page.locator('.reports-header').count()
results.innerHeaderCount = await page.locator('.report-shell__header').count()
results.manufacturingIntelligenceVisible = await page.getByText('Manufacturing intelligence', { exact: true }).count()
results.tabs = await page.getByRole('tab').allTextContents()

console.log(JSON.stringify(results, null, 2))
await browser.close()
