#!/usr/bin/env node

import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { createRequire } from "node:module"

const require = createRequire("/home/anas/.claude/playwright/package.json")
const { chromium } = require("playwright")
const enterpriseCss = await readFile(new URL("../frontend/src/styles/enterprise.css", import.meta.url), "utf8")
const finishingCss = await readFile(new URL("../frontend/src/departments/finishing/finishing.css", import.meta.url), "utf8")

const browser = await chromium.launch({ headless: true })
try {
	const page = await browser.newPage()
	await page.setContent(`
		<table class="erp-data-table">
			<thead><tr><th id="erp-center" class="report-align-center">ERP</th></tr></thead>
			<tbody><tr><td id="erp-right" class="report-align-right">1</td></tr></tbody>
		</table>
		<table class="finishing-table">
			<thead><tr><th id="finishing-number" class="erp-number">Number</th><th id="finishing-center" class="erp-number report-align-center">Finishing</th></tr></thead>
			<tbody><tr><td id="finishing-right" class="report-align-right">2</td><td id="finishing-cell-number" class="erp-number">3</td></tr></tbody>
		</table>
	`)
	await page.addStyleTag({ content: enterpriseCss })
	await page.addStyleTag({ content: finishingCss })
	const alignments = await page.evaluate(() => Object.fromEntries([
		"erp-center",
		"erp-right",
		"finishing-number",
		"finishing-center",
		"finishing-right",
		"finishing-cell-number",
	].map((id) => [id, getComputedStyle(document.getElementById(id)).textAlign])))
	assert.deepEqual(alignments, {
		"erp-center": "center",
		"erp-right": "right",
		"finishing-number": "right",
		"finishing-center": "center",
		"finishing-right": "right",
		"finishing-cell-number": "right",
	})
} finally {
	await browser.close()
}

console.log("report alignment cascade OK")
