#!/usr/bin/env node

import { createRequire } from 'node:module'
import { readFileSync } from 'node:fs'

const require = createRequire('/home/anas/.claude/playwright/package.json')
const { chromium } = require('playwright')
const SITE = 'http://erp-migration-test.site:8001'
const [username, password] = readFileSync('/home/anas/.frappe-debug-creds-mrp3', 'utf8').trim().split('\n')

function assert(condition, message) {
	if (!condition) throw new Error(message)
}

const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
const page = await context.newPage()
const errors = []
page.on('pageerror', (error) => errors.push(`page: ${error.message}`))
page.on('console', (message) => { if (message.type() === 'error') errors.push(`console: ${message.text()}`) })

try {
	await page.goto(`${SITE}/login`, { waitUntil: 'domcontentloaded' })
	await page.fill('#login_email', username.trim())
	await page.fill('#login_password', password.trim())
	await Promise.all([
		page.waitForNavigation({ waitUntil: 'domcontentloaded', timeout: 20_000 }).catch(() => {}),
		page.click('.btn-login, button[type=submit]'),
	])

	await page.goto(`${SITE}/web/cutting/plans`, { waitUntil: 'domcontentloaded' })
	await page.locator('.app-shell').waitFor()
	await page.getByRole('button', { name: 'Filters', exact: true }).click()
	const dialog = page.locator('.p-dialog:visible')
	await dialog.waitFor()
	await page.waitForTimeout(250)
	const dialogContract = await dialog.evaluate((element) => {
		const button = element.querySelector('.add-filter-button')
		const select = element.querySelector('.p-select')
		const style = (node) => node ? getComputedStyle(node) : null
		return {
			button: button ? {
				height: button.getBoundingClientRect().height,
				radius: style(button).borderRadius,
				fontSize: style(button).fontSize,
				fontWeight: style(button).fontWeight,
			} : null,
			select: select ? {
				height: select.getBoundingClientRect().height,
				radius: style(select).borderRadius,
				fontSize: style(select).fontSize,
			} : null,
		}
	})
	assert(dialogContract.button?.height >= 37.5, `Dialog button is shorter than the shared control height: ${JSON.stringify(dialogContract)}`)
	assert(dialogContract.button?.radius === '9px', `Dialog button misses the shared radius: ${JSON.stringify(dialogContract)}`)
	assert(dialogContract.button?.fontSize === '13px' && Number(dialogContract.button?.fontWeight) >= 600, `Dialog button misses shared typography: ${JSON.stringify(dialogContract)}`)
	assert(dialogContract.select?.height >= 37.5 && dialogContract.select?.radius === '9px' && dialogContract.select?.fontSize === '13px', `Dialog select misses the shared control theme: ${JSON.stringify(dialogContract)}`)

	await page.keyboard.press('Escape')
	await dialog.waitFor({ state: 'hidden' })
	await page.goto(`${SITE}/web/cutting/reports`, { waitUntil: 'domcontentloaded' })
	await page.locator('.erp-date-time-picker .p-datepicker-input').first().waitFor()
	const dateInput = page.locator('.erp-date-time-picker .p-datepicker-input').first()
	await dateInput.focus()
	await page.waitForTimeout(250)
	const temporalFocus = await dateInput.evaluate((element) => {
		const style = getComputedStyle(element)
		return { outlineStyle: style.outlineStyle, outlineWidth: style.outlineWidth, outlineColor: style.outlineColor, boxShadow: style.boxShadow }
	})
	assert(temporalFocus.outlineStyle === 'solid' && temporalFocus.outlineWidth === '2px' && temporalFocus.outlineColor !== 'rgba(0, 0, 0, 0)', `Temporal field focus is not clearly visible: ${JSON.stringify(temporalFocus)}`)

	const tab = page.getByRole('tab').first()
	await page.keyboard.press('Tab')
	await tab.focus()
	await page.waitForTimeout(250)
	const tabFocus = await tab.evaluate((element) => {
		const style = getComputedStyle(element)
		return { focusVisible: element.matches(':focus-visible'), className: element.className, parentClasses: element.parentElement?.className, outlineStyle: style.outlineStyle, outlineWidth: style.outlineWidth, outlineColor: style.outlineColor }
	})
	assert(tabFocus.outlineStyle === 'solid' && tabFocus.outlineWidth === '2px' && tabFocus.outlineColor !== 'rgba(0, 0, 0, 0)', `Report tab focus is not clearly visible: ${JSON.stringify(tabFocus)}`)
	assert(errors.length === 0, `Browser errors detected:\n${errors.join('\n')}`)

	console.log(JSON.stringify({ passed: true, dialogContract, temporalFocus, tabFocus, errors }, null, 2))
} finally {
	await browser.close()
}
