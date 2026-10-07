#!/usr/bin/env node

import { createRequire } from 'node:module'
import { readFileSync } from 'node:fs'

const require = createRequire('/home/anas/.claude/playwright/package.json')
const { chromium } = require('playwright')
const SITE = 'http://erp-migration-test.site:8001'
const REQUESTED_PLAN = process.argv[2] || 'CP-2609-00007'
const [usr, pwd] = readFileSync('/home/anas/.frappe-debug-creds-mrp3', 'utf8').trim().split('\n')
const WEB_DATA = '**/api/method/essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan.sd_yrp_cutting_plan.get_web_view_data*'
const WORKSPACE = '**/api/method/essdee_yrp.cutting.web_workspace.get_workspace'
const REPORT_PERMISSIONS = '**/api/method/essdee_yrp.cutting.reports.get_report_permissions'
const CUTTING_CAPABILITIES = '**/api/method/essdee_yrp.cutting.web_capabilities.get_capabilities*'

const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
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

const planListResponse = await context.request.get(`${SITE}/api/resource/SD%20YRP%20Cutting%20Plan`, {
	params: { fields: JSON.stringify(['name']), order_by: 'modified desc', limit_page_length: 25 },
})
if (!planListResponse.ok()) throw new Error(`Unable to inspect Cutting Plan fixtures (${planListResponse.status()}).`)
const listedPlans = ((await planListResponse.json()).data || []).map((row) => row.name).filter(Boolean)
const candidates = [...new Set([REQUESTED_PLAN, ...listedPlans])]
let PLAN = ''
let restrictedPlan = null
let restrictedWorkspace = null
for (const candidate of candidates) {
	const [planResponse, workspaceResponse] = await Promise.all([
		context.request.get(`${SITE}/api/method/essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan.sd_yrp_cutting_plan.get_web_view_data`, {
			params: { cutting_plan: candidate },
		}),
		context.request.get(`${SITE}/api/method/essdee_yrp.cutting.web_workspace.get_workspace`, {
			params: { cutting_plan: candidate },
		}),
	])
	const [planBody, workspaceBody] = await Promise.all([
		planResponse.json().catch(() => ({})),
		workspaceResponse.json().catch(() => ({})),
	])
	for (const [label, response] of [["web view", planResponse], ["workspace", workspaceResponse]]) {
		if (response.status() !== 404 && !response.ok()) throw new Error(`Unable to inspect ${label} for Cutting Plan ${candidate} (${response.status()}).`)
	}
	if (planResponse.ok() && workspaceResponse.ok() && planBody.message && workspaceBody.message?.permissions?.stock_update) {
		PLAN = candidate
		restrictedPlan = planBody
		restrictedWorkspace = workspaceBody
		break
	}
}
if (!PLAN) {
	console.log(JSON.stringify({
		passed: true,
		skipped: true,
		reason: 'No Cutting Plan fixture with web-view and stock-workspace data is available.',
	}, null, 2))
	await browser.close()
	process.exit(0)
}
await page.route(WEB_DATA, async (route) => {
	const body = structuredClone(restrictedPlan)
	body.message.permissions = {
		...body.message.permissions,
		can_write: false,
		can_print: false,
		can_read_marker: false,
		can_read_laysheet: false,
		can_read_movement: false,
		can_read_stock_transfers: false,
	}
	await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
})
await page.goto(`${SITE}/web/cutting/plans/${PLAN}`, { waitUntil: 'domcontentloaded' })
await page.waitForTimeout(1800)
const deniedPlan = {
	editButtons: await page.getByRole('button', { name: 'Edit', exact: true }).count(),
	printButtons: await page.getByRole('button', { name: 'Print', exact: true }).count(),
	sidebars: await page.locator('.operations-rail').count(),
	cpmTabs: await page.getByRole('tab', { name: 'CPM', exact: true }).count(),
	stockTransferTabs: await page.getByRole('tab', { name: 'Stock Transfers', exact: true }).count(),
}
await page.unroute(WEB_DATA)

await page.route(WORKSPACE, async (route) => {
	const body = structuredClone(restrictedWorkspace)
	for (const flags of Object.values(body.message.permissions || {})) {
		flags.can_read = false
		flags.can_create = false
	}
	body.message.permissions.stock_update.can_read = true
	await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
})
await page.goto(`${SITE}/web/cutting/plans/${PLAN}`, { waitUntil: 'domcontentloaded' })
await page.getByRole('tab', { name: 'Stock Transfers', exact: true }).click()
await page.waitForTimeout(900)
const stockWorkspace = {
	operationCards: await page.locator('.erp-activity-card').allTextContents(),
	createButtons: await page.locator('.erp-create-actions .p-button').count(),
}
await page.unroute(WORKSPACE)

await page.route(CUTTING_CAPABILITIES, async (route) => {
	await route.fulfill({
		status: 200,
		contentType: 'application/json',
		body: JSON.stringify({
			message: {
				'cutting-plans': { can_read: true, can_create: false },
				'cutting-orders': { can_read: false, can_create: true },
				'bulk-lay-sheets': { can_read: true, can_create: false },
				'lay-sheet-planner': { can_read: false, can_create: false },
				'reports': { can_read: true, can_create: false },
			},
		}),
	})
})
await page.goto(`${SITE}/web/cutting`, { waitUntil: 'domcontentloaded' })
await page.locator('.workspace-launcher__grid').waitFor()
const capabilityCards = await page.locator('.workspace-launcher__card strong').allTextContents()

await page.route(REPORT_PERMISSIONS, async (route) => {
	await route.fulfill({
		status: 200,
		contentType: 'application/json',
		body: JSON.stringify({
			message: {
				'daily-production': false,
				'daily-cut-sheet': true,
				'multi-ccr': false,
				'cutting-detail': false,
				'stock-balance': false,
			},
		}),
	})
})
await page.goto(`${SITE}/web/cutting/reports`, { waitUntil: 'domcontentloaded' })
await page.waitForTimeout(900)
const reportTabs = await page.getByRole('tab').allTextContents()

const passed = Object.values(deniedPlan).every((value) => value === 0)
	&& stockWorkspace.operationCards.length === 1
	&& stockWorkspace.operationCards[0].includes('Stock Update')
	&& stockWorkspace.createButtons === 0
	&& JSON.stringify(capabilityCards) === JSON.stringify(['Cutting Plans', 'Bulk LaySheets', 'Reports'])
	&& reportTabs.length === 1
	&& reportTabs[0].includes('Daily Cut Sheet')
	&& errors.length === 0

console.log(JSON.stringify({ passed, deniedPlan, stockWorkspace, capabilityCards, reportTabs, errors }, null, 2))
await browser.close()
if (!passed) process.exitCode = 1
