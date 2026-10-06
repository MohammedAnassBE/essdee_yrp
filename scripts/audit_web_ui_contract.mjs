#!/usr/bin/env node

import { createRequire } from "node:module"
import { mkdirSync, readFileSync } from "node:fs"

const require = createRequire("/home/anas/.claude/playwright/package.json")
const { chromium } = require("playwright")
const SITE = "http://erp-migration-test.site:8001"
const [username, password] = readFileSync("/home/anas/.frappe-debug-creds-mrp3", "utf8").trim().split("\n")
const viewports = process.argv.includes("--all-widths")
	? [{ width: 1600, height: 1000 }, { width: 1280, height: 900 }, { width: 900, height: 900 }, { width: 390, height: 844 }]
	: [{ width: 1600, height: 1000 }]
const screenshotDirectory = process.argv.includes("--screenshots") ? "/tmp/essdee-web-ui-review" : ""
if (screenshotDirectory) mkdirSync(screenshotDirectory, { recursive: true })
const routes = [
	"/", "/cutting", "/cutting/plans", "/cutting/plans/new",
	"/cutting/orders", "/cutting/orders/new",
	"/cutting/bulk-lay-sheets", "/cutting/bulk-lay-sheets/new",
	"/cutting/lay-sheet-planner", "/cutting/lay-sheet-planner/new",
	"/cutting/reports", "/fabric-store", "/fabric-store/work-orders",
	"/fabric-store/purchase-orders", "/fabric-store/purchase-orders/new", "/fabric-store/stock-transfers", "/fabric-store/reports",
	"/cut-panel-store", "/accessory-store", "/sewing", "/finishing", "/merch", "/purchase", "/sales", "/planning",
]

function assert(condition, message) {
	if (!condition) throw new Error(message)
}

const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({ viewport: viewports[0] })
const page = await context.newPage()
const browserErrors = []
page.on("pageerror", (error) => browserErrors.push(error.message))

await page.goto(`${SITE}/login`, { waitUntil: "domcontentloaded" })
await page.fill("#login_email", username.trim())
await page.fill("#login_password", password.trim())
await Promise.all([
	page.waitForNavigation({ waitUntil: "domcontentloaded", timeout: 20_000 }).catch(() => {}),
	page.click(".btn-login, button[type=submit]"),
])

for (const [doctype, routePrefix] of [
	["SD YRP Cutting Plan", "/cutting/plans"],
	["SD YRP Cutting Order", "/cutting/orders"],
	["SD YRP Cutting Bulk Lay Sheets", "/cutting/bulk-lay-sheets"],
	["SD YRP Cutting Laysheet Planner", "/cutting/lay-sheet-planner"],
	["YRP Work Order", "/fabric-store/work-orders"],
	["Purchase Order", "/fabric-store/purchase-orders"],
]) {
	const response = await context.request.get(`${SITE}/api/resource/${encodeURIComponent(doctype)}`, {
		params: { fields: JSON.stringify(["name"]), order_by: "modified desc", limit_page_length: 1 },
	})
	if (!response.ok()) continue
	const name = (await response.json()).data?.[0]?.name
	if (name) routes.push(`${routePrefix}/${encodeURIComponent(name)}`)
}

const audits = []
for (const viewport of viewports) {
	await page.setViewportSize(viewport)
	for (const route of routes) {
		await page.goto(`${SITE}/web${route}`, { waitUntil: "domcontentloaded" })
		await page.locator(".app-shell").waitFor({ timeout: 20_000 })
		await page.locator(".p-skeleton:visible").first().waitFor({ state: "hidden", timeout: 5_000 }).catch(() => {})
		await page.waitForTimeout(500)
		if (screenshotDirectory) {
			const slug = route === "/" ? "home" : route.slice(1).replaceAll("/", "--")
			await page.screenshot({ path: `${screenshotDirectory}/${viewport.width}--${slug}.png`, fullPage: false })
		}
		const audit = await page.evaluate(() => {
			const visible = (element) => {
				const style = getComputedStyle(element)
				const rect = element.getBoundingClientRect()
				return style.display !== "none" && style.visibility !== "hidden" && Number(style.opacity) > 0 && rect.width > 0 && rect.height > 0
			}
			const undersizedText = [...document.querySelectorAll(".app-shell *")].flatMap((element) => {
				if (!(element instanceof HTMLElement) || element.children.length || !visible(element)) return []
				if (element.matches("script, style, svg, path, .pi, [aria-hidden='true']")) return []
				const text = (element.innerText || "").trim()
				const size = Number.parseFloat(getComputedStyle(element).fontSize)
				return text && size < 11 ? [{ text: text.slice(0, 70), size, className: element.className }] : []
			})
			const buttonColourMismatches = [...document.querySelectorAll(".p-button")].flatMap((button) => {
				if (!(button instanceof HTMLButtonElement) || button.disabled || !visible(button)) return []
				const style = getComputedStyle(button)
				const label = button.querySelector(".p-button-label")
				const icon = button.querySelector(".p-button-icon")
				const labelColour = label ? getComputedStyle(label).color : style.color
				const iconColour = icon ? getComputedStyle(icon).color : style.color
				return labelColour !== style.color || iconColour !== style.color
					? [{ text: (button.textContent || button.getAttribute("aria-label") || "").trim(), button: style.color, label: labelColour, icon: iconColour }]
					: []
			})
			const parseColour = (value) => {
				const parts = String(value || "").match(/[\d.]+/g)?.map(Number) || []
				return parts.length >= 3 ? { r: parts[0], g: parts[1], b: parts[2], a: parts[3] ?? 1 } : null
			}
			const effectiveBackground = (element) => {
				let current = element
				while (current) {
					const colour = parseColour(getComputedStyle(current).backgroundColor)
					if (colour && colour.a > 0.01) return colour
					current = current.parentElement
				}
				return { r: 255, g: 255, b: 255, a: 1 }
			}
			const luminance = ({ r, g, b }) => {
				const channels = [r, g, b].map((value) => { const channel = value / 255; return channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4 })
				return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]
			}
			const contrast = (foreground, background) => { const light = Math.max(luminance(foreground), luminance(background)); const dark = Math.min(luminance(foreground), luminance(background)); return (light + 0.05) / (dark + 0.05) }
			const buttonContrastFailures = [...document.querySelectorAll(".p-button")].flatMap((button) => {
				if (!(button instanceof HTMLButtonElement) || button.disabled || !visible(button)) return []
				const label = button.querySelector(".p-button-label")
				if (!label || !(label.textContent || "").trim()) return []
				const foreground = parseColour(getComputedStyle(label).color)
				const background = effectiveBackground(button)
				const ratio = foreground && background ? contrast(foreground, background) : 21
				return ratio < 3 ? [{ text: label.textContent.trim(), foreground, background, ratio }] : []
			})
			return {
				title: document.title,
				bodyOverflow: document.documentElement.scrollWidth - window.innerWidth,
				undersizedText: undersizedText.slice(0, 12),
				buttonColourMismatches: buttonColourMismatches.slice(0, 12),
				buttonContrastFailures: buttonContrastFailures.slice(0, 12),
			}
		})
		audits.push({ route, viewport: viewport.width, ...audit })
	}
}

await browser.close()
const failures = audits.filter((audit) => audit.bodyOverflow > 1 || audit.undersizedText.length || audit.buttonColourMismatches.length || audit.buttonContrastFailures.length)
console.log(JSON.stringify({ passed: failures.length === 0 && browserErrors.length === 0, audited: audits.length, failures, browserErrors }, null, 2))
assert(browserErrors.length === 0, `Browser errors: ${browserErrors.join("; ")}`)
assert(failures.length === 0, `${failures.length} route/viewport combinations violate the UI contract`)
