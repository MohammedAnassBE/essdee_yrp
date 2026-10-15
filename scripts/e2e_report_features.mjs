#!/usr/bin/env node

import { execFileSync } from "node:child_process"
import { randomBytes } from "node:crypto"
import { mkdirSync, writeFileSync } from "node:fs"

process.env.E2E_SITE ||= "http://erp-migration-test.site:8001"

const { ADMIN, SITE, launch, loginAs } = await import("./e2e-lib.mjs")

const BENCH = "/home/anas/pilot/benches/frappe-16"
const PYTHON = `${BENCH}/env/bin/python`
const SITE_NAME = process.env.E2E_SITE_NAME || new URL(SITE).hostname
const PASSWORD = process.env.E2E_PASSWORD || randomBytes(18).toString("base64url")
const SCREENSHOT_DIRECTORY = "/tmp/claude-1000/-home-anas-pilot-benches-frappe-16/348c72ab-5d72-4bcf-a023-b3fbf230e45a/scratchpad/screens/reports"
const CUT_BUNDLE_REPORT = {
	key: "cut-bundle-balance",
	title: "Cut Bundle Balance",
	path: "/web/cut-panel-store/reports",
	tab: "Cut Bundle Balance",
	source: "Item",
	target: "item_group",
	targetLabel: "Item Group",
	left: "Lay No",
	center: "Quantity",
}
const results = []
const screenshots = []

mkdirSync(SCREENSHOT_DIRECTORY, { recursive: true })

function fixture(functionName) {
	return execFileSync(PYTHON, [
		"-m", "frappe.utils.bench_helper", "frappe", "--site", SITE_NAME,
		"execute", `essdee_yrp.report_features_fixtures.${functionName}`,
		...(functionName === "setup" ? ["--kwargs", `{'password': ${JSON.stringify(PASSWORD)}, 'restrict_item': False}`] : []),
	], {
		cwd: `${BENCH}/sites`,
		encoding: "utf8",
		env: process.env,
	})
}

let browser
let contextA
let contextB
let fixturesReady = false
let users
try {
	users = parseFixtureOutput(fixture("setup"))
	fixturesReady = true
	assert(users.cutting_from_date && users.cutting_to_date, "No Label Printed cutting date range is available")
	browser = await launch()
	const sessionA = await loginAs(browser, { usr: users.user_a, pwd: PASSWORD })
	const sessionB = await loginAs(browser, { usr: users.user_b, pwd: PASSWORD })
	await assertAuthenticated(sessionA.page, users.user_a)
	await assertAuthenticated(sessionB.page, users.user_b)
	contextA = sessionA.ctx
	contextB = sessionB.ctx
	await scenario("column picker layouts", () => verifyColumnPickers(sessionA.page, sessionB.page, users))
	await scenario("Cut Bundle column picker (System Manager)", () => verifyCutBundlePicker(browser, users))
	await scenario("DPR background lifecycle and realtime", () => verifyBackgroundLifecycle(sessionA.page, users))
	await scenario("DPR synchronous boundaries", () => verifySynchronousDpr(sessionA.page, users))
	await scenario("DPR polling fallback", () => verifyPollingFallback(browser, users))
	await scenario("DPR resume after reload", () => verifyResume(sessionA.page, users))
	await scenario("background job error state", () => verifyErrorState(browser, users))
	await scenario("worker unavailable message", () => verifyWorkerUnavailable(browser, users))
	await scenario("expired result after permission change", () => verifyExpiredState(browser, users))
} finally {
	await contextA?.close().catch(() => {})
	await contextB?.close().catch(() => {})
	await browser?.close().catch(() => {})
	if (fixturesReady) {
		const teardownError = teardownFixtures()
		if (teardownError) results.push({ scenario: "fixture teardown", passed: false, detail: teardownError })
	}
	writeFileSync(
		`${SCREENSHOT_DIRECTORY}/INDEX.txt`,
		screenshots.map(({ file, caption }) => `${file}\t${caption}`).join("\n") + "\n",
	)
}

console.table(results.map(({ scenario: name, passed, detail }) => ({
	result: passed ? "PASS" : "FAIL",
	scenario: name,
	detail: detail.slice(0, process.env.E2E_DETAIL ? 4000 : 240),
})))
const passed = results.filter((result) => result.passed).length
console.log(`E2E_SUMMARY passed=${passed} failed=${results.length - passed} total=${results.length}`)
if (results.some((result) => !result.passed)) process.exitCode = 1


async function verifyCutBundlePicker(activeBrowser, fixtureData) {
	const session = await loginAs(activeBrowser, ADMIN)
	try {
		await verifyPickerFlow(session.page, CUT_BUNDLE_REPORT, fixtureData)
	} finally {
		await session.ctx.close()
	}
}

async function verifyColumnPickers(pageA, pageB, fixtureData) {
	const reports = [
		{
			key: "stock-balance",
			title: "Stock Balance",
			path: "/web/purchase/reports",
			tab: "Stock Balance",
			source: "Item",
			target: "item_group",
			targetLabel: "Item Group",
			left: "Balance Qty",
			center: "In Qty",
		},
		{
			key: "purchase-order-itemwise",
			title: "Purchase Order Itemwise",
			path: "/web/purchase/reports",
			tab: "Purchase Order Itemwise",
			source: "Item",
			target: "item_group",
			targetLabel: "Item Group",
			left: "Qty",
			center: "Delivered Qty",
		},
		{
			key: "finishing-plan",
			title: "Finishing Plan Report",
			path: "/web/finishing/reports?report=finishing-plan-report",
			source: "Item (Style)",
			target: "item_group",
			targetLabel: "Item Group",
			left: "Cut Qty",
			center: "Sewing Received",
		},
	]

	for (const [index, report] of reports.entries()) {
		await verifyPickerFlow(pageA, report, fixtureData, { withSearchShot: index === 0 })
		if (index === 0) {
			const userBShell = await openReport(pageB, report)
			await prepareTabularReport(pageB, userBShell, report.key, fixtureData)
			await generateTabularReport(pageB, userBShell, report.key)
			await assertTableLayout(userBShell, report.left, "right", null)
			await capture(pageB, "stock-balance-user-b-default", "Stock Balance: user B (other user) still sees the default layout while user A has a saved one.")
			await resetPickerLayout(pageA, report, fixtureData)
		}
	}
}

async function verifyPickerFlow(page, report, fixtureData, { withSearchShot = false } = {}) {
	const shell = await openReport(page, report)
	await prepareTabularReport(page, shell, report.key, fixtureData)
	await generateTabularReport(page, shell, report.key)
	const dialog = await openPicker(shell)
	await capture(page, `${report.key}-picker-open`, `${report.title}: Pick Columns dialog open.`)
	const sourceGroup = await expandLinkedSource(dialog, report.source)
	await capture(page, `${report.key}-picker-linked-expanded`, `${report.title}: linked fields expanded.`)
	const search = sourceGroup.getByPlaceholder("Find a linked field…")
	await search.fill(report.target)
	if (withSearchShot) await capture(page, `${report.key}-picker-search`, `${report.title}: linked field search.`)
	const option = sourceGroup.locator("label.report-column-option").filter({ hasText: report.target }).first()
	await option.waitFor({ state: "visible" })
	await option.click()
	await reorderLinkedColumn(dialog)
	await configurePickerColumn(dialog, report.left, "Left", 210)
	await configurePickerColumn(dialog, report.center, "Center", 170)
	await capture(page, `${report.key}-picker-configured`, `${report.title}: linked field added, reordered to second, align and width set.`)
	await dialog.getByRole("button", { name: "Save", exact: true }).click()
	await dialog.waitFor({ state: "hidden" })
	await assertSavedLayout(shell, report)
	await capture(page, `${report.key}-aligned-width-table`, `${report.title}: linked column in position 2 with values, explicit alignments and widths rendered.`)

	const persistedShell = await openReport(page, report)
	await prepareTabularReport(page, persistedShell, report.key, fixtureData)
	await generateTabularReport(page, persistedShell, report.key)
	await assertSavedLayout(persistedShell, report)
	await capture(page, `${report.key}-persisted-layout`, `${report.title}: saved layout after reload.`)
	if (report.key !== "stock-balance") await resetPickerLayout(page, report, fixtureData, persistedShell)
}

async function resetPickerLayout(page, report, fixtureData, existingShell = null) {
	let shell = existingShell
	if (!shell) {
		shell = await openReport(page, report)
		await prepareTabularReport(page, shell, report.key, fixtureData)
		await generateTabularReport(page, shell, report.key)
	}
	const resetDialog = await openPicker(shell)
	await resetDialog.getByRole("button", { name: "Reset", exact: true }).click()
	await resetDialog.waitFor({ state: "hidden" })
	await assertTableLayout(shell, report.left, "right", null)
	assert(await linkedHeaderIndex(shell, report.targetLabel) === -1, "linked column survived Reset")
	await capture(page, `${report.key}-reset-layout`, `${report.title}: Reset restored the default layout.`)
}

async function assertSavedLayout(shell, report) {
	await assertTableLayout(shell, report.left, "left", 210)
	await assertTableLayout(shell, report.center, "center", 170)
	const index = await linkedHeaderIndex(shell, report.targetLabel)
	const headers = await shell.locator("table").first().locator("thead th").allTextContents()
	assert(index === 1, `linked ${report.targetLabel} column is at index ${index}, expected 1; headers=${JSON.stringify(headers)}`)
	const values = await shell.locator("table").first().locator("tbody tr").evaluateAll(
		(rows, column) => rows.map((row) => row.children[column]?.textContent.trim() || ""),
		index,
	)
	assert(values.length === 0 || values.some(Boolean), `linked ${report.targetLabel} column has no values`)
}

async function linkedHeaderIndex(shell, targetLabel) {
	return shell.locator("table").first().locator("thead th").evaluateAll(
		(elements, label) => elements.findIndex((element) => {
			const text = element.textContent.trim()
			return text.includes(" · ") && text.endsWith(label)
		}),
		targetLabel,
	)
}

async function verifyBackgroundLifecycle(page, fixtureData) {
	const shell = await openDailyProduction(page)
	await selectSummaryRange(shell, fixtureData.cutting_from_date, fixtureData.cutting_to_date)
	const realtime = observeRealtime(page)
	const responsePromise = reportRunResponse(page, "cutting-dpr")
	await shell.getByRole("button", { name: "Generate", exact: true }).click()
	const envelope = await responsePromise
	assert(envelope.mode === "background", envelope)
	const status = shell.locator(".report-run-status--running")
	await status.waitFor({ state: "visible", timeout: 10_000 })
	assert((await status.textContent()).includes("Queued"), "Queued state was not rendered")
	await capture(page, "cutting-dpr-queued", "Cutting DPR: prominent queued background panel.")
	await shell.locator(".report-run-status__eyebrow", { hasText: "Running" }).waitFor({ timeout: 30_000 })
	const firstElapsed = await shell.locator(".report-run-status__eyebrow").textContent()
	await page.waitForTimeout(1_200)
	const secondElapsed = await shell.locator(".report-run-status__eyebrow").textContent()
	assert(firstElapsed !== secondElapsed, `elapsed timer did not advance: ${firstElapsed}`)
	await capture(page, "cutting-dpr-running-progress", "Cutting DPR: running panel with elapsed timer and progress.")
	await waitForDprResult(shell)
	assert(realtime.doneEvents > 0, "yrp_report_done was not observed on the websocket")
	await capture(page, "cutting-dpr-auto-result", "Cutting DPR: result shown automatically after realtime completion.")

	const reusedResponse = reportRunResponse(page, "cutting-dpr")
	await shell.getByRole("button", { name: "Generate", exact: true }).click()
	const reused = await reusedResponse
	assert(reused.reused === true, reused)
	await shell.getByText(/^Generated /).waitFor({ state: "visible" })
	await shell.getByRole("button", { name: "Rebuild", exact: true }).waitFor({ state: "visible" })
	await capture(page, "cutting-dpr-generated-reused", "Cutting DPR: reused result with Generated age and Rebuild.")

	const rebuildResponse = reportRunResponse(page, "cutting-dpr")
	await shell.getByRole("button", { name: "Rebuild", exact: true }).click()
	assert((await rebuildResponse).mode === "background", "Rebuild did not stay in background mode")
	await shell.locator(".report-run-status--running").waitFor({ state: "visible" })
	await capture(page, "cutting-dpr-rebuild-in-progress", "Cutting DPR: rebuild in progress.")
	await waitForDprResult(shell)
}

async function verifySynchronousDpr(page, fixtureData) {
	let shell = await openDailyProduction(page)
	const toDate = fixtureData.cutting_to_date
	const fromDate = addDays(toDate, -10)
	await selectSummaryRange(shell, fromDate, toDate)
	const summaryResponse = reportRunResponse(page, "cutting-dpr")
	await shell.getByRole("button", { name: "Generate", exact: true }).click()
	assert((await summaryResponse).mode === "sync", "10-day summary did not run synchronously")
	assert(await shell.locator(".report-run-status--running").count() === 0, "sync summary showed background panel")
	await capture(page, "cutting-dpr-sync-summary", "Cutting DPR: ten-day summary rendered synchronously.")

	shell = await openDailyProduction(page)
	await shell.getByLabel(/^Date/).fill(displayDate(toDate))
	await shell.getByLabel(/^Date/).press("Tab")
	const dailyResponse = reportRunResponse(page, "cutting-dpr")
	await shell.getByRole("button", { name: "Generate", exact: true }).click()
	assert((await dailyResponse).mode === "sync", "daily mode did not run synchronously")
	assert(await shell.locator(".report-run-status--running").count() === 0, "daily mode showed background panel")
	await capture(page, "cutting-dpr-sync-daily", "Cutting DPR: daily mode rendered synchronously.")
}

async function verifyPollingFallback(activeBrowser, fixtureData) {
	const session = await loginAs(activeBrowser, { usr: fixtureData.user_a, pwd: PASSWORD })
	try {
		await session.page.route("**/socket.io/**", (route) => route.abort())
		const shell = await openDailyProduction(session.page)
		await selectSummaryRange(shell, fixtureData.cutting_from_date, fixtureData.cutting_to_date)
		const firstResponse = reportRunResponse(session.page, "cutting-dpr")
		await shell.getByRole("button", { name: "Generate", exact: true }).click()
		const firstEnvelope = await firstResponse
		if (firstEnvelope.reused) {
			const rebuildResponse = reportRunResponse(session.page, "cutting-dpr")
			await shell.getByRole("button", { name: "Rebuild", exact: true }).click()
			assert((await rebuildResponse).mode === "background", "polling rebuild did not start")
		}
		await waitForDprResult(shell, 180_000)
		await capture(session.page, "cutting-dpr-polling-fallback", "Cutting DPR: result delivered by polling with socket.io blocked.")
	} finally {
		await session.ctx.close()
	}
}

async function verifyResume(page, fixtureData) {
	const shell = await openDailyProduction(page)
	await selectSummaryRange(shell, fixtureData.cutting_from_date, fixtureData.cutting_to_date)
	const initialResponse = reportRunResponse(page, "cutting-dpr")
	await shell.getByRole("button", { name: "Generate", exact: true }).click()
	const initial = await initialResponse
	if (initial.reused) {
		const rebuildResponse = reportRunResponse(page, "cutting-dpr")
		await shell.getByRole("button", { name: "Rebuild", exact: true }).click()
		await rebuildResponse
	}
	await shell.locator(".report-run-status--running").waitFor({ state: "visible", timeout: 10_000 })
	const stored = await page.evaluate(() => sessionStorage.getItem("yrp:web-report:cutting-dpr"))
	assert(stored, "pending job was not persisted before reload")
	await page.reload({ waitUntil: "domcontentloaded" })
	const resumedShell = page.locator(".report-shell").filter({ hasText: "Daily Production Report" }).first()
	await waitForDprResult(resumedShell, 180_000)
	await capture(page, "cutting-dpr-resumed-job", "Cutting DPR: pending job resumed after page reload.")
}

async function verifyErrorState(activeBrowser, fixtureData) {
	await withSession(activeBrowser, fixtureData, async (page) => {
		await page.route(/yrp\.api\.web_reports\.(run_web_report|get_report_job)/, (route) => {
			const body = route.request().postDataJSON() || {}
			body.report_key = "web-report--test-failing"
			if (route.request().url().includes("run_web_report")) body.filters = {}
			return route.continue({ postData: JSON.stringify(body) })
		})
		const shell = await openDailyProduction(page)
		await selectSummaryRange(shell, fixtureData.cutting_from_date, fixtureData.cutting_to_date)
		await shell.getByRole("button", { name: "Generate", exact: true }).click()
		const panel = shell.locator(".report-run-status--error")
		await panel.waitFor({ state: "visible", timeout: 120_000 })
		assert((await panel.textContent()).includes("Retry"), "error panel has no Retry action")
		await capture(page, "background-error-state", "Background job failed in the real worker (allow_tests failing key): error panel with Retry.")
	})
}

async function verifyWorkerUnavailable(activeBrowser, fixtureData) {
	await withSession(activeBrowser, fixtureData, async (page) => {
		await page.route(/yrp\.api\.web_reports\.run_web_report/, (route) => route.fulfill({
			status: 417,
			contentType: "application/json",
			body: JSON.stringify({
				exc_type: "ValidationError",
				_server_messages: JSON.stringify([JSON.stringify({ message: "background worker unavailable: no long worker is running." })]),
			}),
		}))
		const shell = await openDailyProduction(page)
		await selectSummaryRange(shell, fixtureData.cutting_from_date, fixtureData.cutting_to_date)
		await shell.getByRole("button", { name: "Generate", exact: true }).click()
		await shell.getByText(/Background processing is temporarily unavailable/).first().waitFor({ state: "visible", timeout: 15_000 })
		await capture(page, "worker-unavailable", "Worker unavailable: friendly message (server's exact 417 response simulated; live workers left running).")
	})
}

async function verifyExpiredState(activeBrowser, fixtureData) {
	await withSession(activeBrowser, fixtureData, async (page) => {
		let restricted = false
		await page.route(/yrp\.api\.web_reports\.get_report_job/, async (route) => {
			if (restricted) return route.continue()
			const peek = await route.fetch()
			const status = (await peek.json().catch(() => ({})))?.message?.job?.status
			if (status !== "Completed") return route.fulfill({ response: peek })
			fixture("restrict_user_a")
			restricted = true
			return route.continue()
		})
		try {
			const shell = await openDailyProduction(page)
			await selectSummaryRange(shell, fixtureData.cutting_from_date, fixtureData.cutting_to_date)
			const firstResponse = reportRunResponse(page, "cutting-dpr")
			await shell.getByRole("button", { name: "Generate", exact: true }).click()
			if ((await firstResponse).reused) await shell.getByRole("button", { name: "Rebuild", exact: true }).click()
			const panel = shell.locator(".report-run-status--expired")
			await panel.waitFor({ state: "visible", timeout: 180_000 })
			assert(restricted, "expired panel appeared before the permission change")
			await capture(page, "expired-permissions-changed", "Expired: a User Permission was added after the job completed, so the server refused the stale result; Rebuild offered.")
		} finally {
			if (restricted) fixture("clear_user_a_restrictions")
		}
	})
}

async function withSession(activeBrowser, fixtureData, task) {
	const session = await loginAs(activeBrowser, { usr: fixtureData.user_a, pwd: PASSWORD })
	try {
		await task(session.page)
	} finally {
		await session.ctx.close()
	}
}

async function openReport(page, report) {
	await page.goto(`${SITE}${report.path}`, { waitUntil: "domcontentloaded" })
	if (new URL(page.url()).pathname.startsWith("/login")) throw new Error(`${report.title} redirected to login`)
	if (report.tab) {
		const tab = page.getByRole("tab").filter({ hasText: report.tab })
		await waitForVisible(tab, page, `${report.title} tab`)
		await tab.click()
	}
	const shell = page.locator(".report-shell").filter({ hasText: report.title }).first()
	await shell.waitFor({ state: "visible", timeout: 30_000 })
	return shell
}

async function generateTabularReport(page, shell, reportKey) {
	const responsePromise = reportRunResponse(page, reportKey)
	await shell.getByRole("button", { name: "Generate", exact: true }).click()
	const envelope = await responsePromise
	assert(envelope.mode === "sync", `${reportKey} unexpectedly used ${envelope.mode}`)
	const picker = shell.getByRole("button", { name: "Pick Columns", exact: true })
	await picker.waitFor({ state: "visible" })
	await page.waitForFunction((button) => !button.disabled, await picker.elementHandle(), { timeout: 30_000 })
}

async function prepareTabularReport(page, shell, reportKey, fixtureData) {
	if (reportKey !== "stock-balance") return
	await shell.getByLabel(/^From date/).fill(displayDate(fixtureData.stock_date))
	await shell.getByLabel(/^To date/).fill(displayDate(fixtureData.stock_date))
	const item = shell.getByRole("combobox", { name: "Item variant", exact: true })
	await item.fill(fixtureData.allowed_item)
	const option = page.locator(".p-autocomplete-overlay:visible .p-autocomplete-option")
		.filter({ hasText: fixtureData.allowed_item }).first()
	await option.waitFor({ state: "visible", timeout: 20_000 })
	await option.click()
}

async function openPicker(shell) {
	await shell.getByRole("button", { name: "Pick Columns", exact: true }).click()
	const dialog = shell.page().getByRole("dialog", { name: "Pick report columns" })
	await dialog.waitFor({ state: "visible" })
	return dialog
}

async function expandLinkedSource(dialog, label) {
	const group = dialog.locator("details.report-column-group").filter({ hasText: label }).first()
	await group.locator("summary").click()
	await group.getByPlaceholder("Find a linked field…").waitFor({ state: "visible" })
	await group.locator(".report-column-loading").waitFor({ state: "hidden", timeout: 30_000 }).catch(() => {})
	return group
}

async function reorderLinkedColumn(dialog) {
	const rows = dialog.locator(".report-column-order__row")
	const linkedRow = () => rows.filter({ hasText: "Linked field" }).last()
	await linkedRow().waitFor({ state: "visible" })
	const draggedRow = rows.nth(3)
	const movedLabel = await draggedRow.locator(".report-column-order__identity > strong").textContent()
	await draggedRow.locator(".report-column-handle").dragTo(rows.first(), { targetPosition: { x: 40, y: 4 } })
	assert((await rows.first().textContent()).includes(movedLabel), `drag did not move ${movedLabel} to the top`)
	await dialog.getByRole("button", { name: `Reorder ${movedLabel}`, exact: true }).press("Alt+ArrowDown")
	assert((await rows.nth(1).textContent()).includes(movedLabel), `keyboard did not move ${movedLabel} down`)
	for (let attempt = 0; attempt < 60; attempt += 1) {
		const position = Number(await linkedRow().locator(".report-column-position").textContent())
		if (position === 2) return
		const handle = linkedRow().locator(".report-column-handle")
		await handle.focus()
		await handle.press(position > 2 ? "Alt+ArrowUp" : "Alt+ArrowDown")
	}
	throw new Error("keyboard reorder did not move the linked column to position 2")
}

async function configurePickerColumn(dialog, label, alignment, width) {
	const row = pickerRow(dialog, label)
	await row.waitFor({ state: "visible" })
	await row.getByRole("button", { name: alignment, exact: true }).click()
	const widthInput = row.getByLabel(`Width for ${label}`)
	await widthInput.fill(String(width))
	await widthInput.press("Tab")
}

function pickerRow(dialog, label) {
	return dialog.locator(".report-column-order__identity > strong")
		.getByText(label, { exact: true }).first().locator("xpath=../..")
}

async function assertTableLayout(shell, label, expectedAlignment, expectedWidth) {
	const table = shell.locator("table").first()
	await table.waitFor({ state: "visible", timeout: 30_000 })
	const headers = table.locator("thead th")
	const header = headers.filter({ hasText: exactText(label) }).first()
	await header.waitFor({ state: "visible" })
	assert(await header.evaluate((element) => getComputedStyle(element).textAlign) === expectedAlignment, `${label} is not ${expectedAlignment}-aligned`)
	const index = await headers.evaluateAll((elements, target) => elements.findIndex((element) => element.textContent.trim() === target), label)
	assert(index >= 0, `${label} header index was not found`)
	const cell = table.locator("tbody tr").first().locator("td").nth(index)
	if (await cell.count()) {
		assert(await cell.evaluate((element) => getComputedStyle(element).textAlign) === expectedAlignment, `${label} body cell is not ${expectedAlignment}-aligned`)
	}
	if (expectedWidth === null) return
	const style = await table.locator("colgroup col").nth(index).getAttribute("style")
	assert(style?.includes(`${expectedWidth}px`), `${label} width is ${style}, expected ${expectedWidth}px`)
}

function exactText(value) {
	return new RegExp(`^${value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}$`)
}

async function openDailyProduction(page) {
	await page.goto(`${SITE}/web/cutting/reports`, { waitUntil: "domcontentloaded" })
	const tab = page.getByRole("tab").filter({ hasText: "Daily Production" })
	await waitForVisible(tab, page, "Daily Production tab")
	await tab.click()
	const shell = page.locator(".report-shell").filter({ hasText: "Daily Production Report" }).first()
	await shell.waitFor({ state: "visible" })
	return shell
}

async function selectSummaryRange(shell, fromDate, toDate) {
	await shell.getByRole("button").filter({ hasText: "Summary" }).click()
	await shell.getByLabel("From date", { exact: true }).fill(displayDate(fromDate))
	await shell.getByLabel("From date", { exact: true }).press("Tab")
	await shell.getByLabel("To date", { exact: true }).fill(displayDate(toDate))
	await shell.getByLabel("To date", { exact: true }).press("Tab")
}

async function waitForDprResult(shell, timeout = 180_000) {
	await shell.locator(".summary-day, .production-card").first().waitFor({ state: "visible", timeout })
}

function reportRunResponse(page, reportKey) {
	return page.waitForResponse(async (response) => {
		if (!response.url().includes("yrp.api.web_reports.run_web_report")) return false
		const body = response.request().postDataJSON?.() || {}
		return body.report_key === reportKey
	}, { timeout: 30_000 }).then(async (response) => {
		const body = await response.json()
		assert(response.status() === 200, body)
		return body.message
	})
}

function observeRealtime(page) {
	const state = { doneEvents: 0 }
	page.on("websocket", (socket) => {
		socket.on("framereceived", ({ payload }) => {
			if (String(payload).includes("yrp_report_done")) state.doneEvents += 1
		})
	})
	return state
}

async function assertAuthenticated(page, user) {
	if (!new URL(page.url()).pathname.startsWith("/login")) return
	throw new Error(`Login failed for ${user}: ${(await page.locator("body").innerText()).slice(0, 500)}`)
}

async function waitForVisible(locator, page, label) {
	try {
		await locator.waitFor({ state: "visible", timeout: 30_000 })
	} catch (reason) {
		const body = (await page.locator("body").innerText()).replaceAll(/\s+/g, " ").slice(0, 800)
		throw new Error(`${label} was not visible at ${page.url()}; body=${body}; console=${JSON.stringify(page._errs || [])}; cause=${describe(reason)}`)
	}
}

async function capture(page, name, caption) {
	const file = `${name}.png`
	await page.screenshot({ path: `${SCREENSHOT_DIRECTORY}/${file}`, fullPage: true })
	screenshots.push({ file, caption })
}

async function scenario(name, task) {
	if (process.env.E2E_ONLY && !new RegExp(process.env.E2E_ONLY, "i").test(name)) return
	try {
		await task()
		results.push({ scenario: name, passed: true, detail: "" })
	} catch (reason) {
		results.push({ scenario: name, passed: false, detail: describe(reason) })
	}
}

function parseFixtureOutput(output) {
	const line = output.trim().split("\n").reverse().find((value) => value.trim().startsWith("{"))
	if (!line) throw new Error(`Fixture setup did not return users: ${output}`)
	return JSON.parse(line)
}

function teardownFixtures() {
	let failure
	for (let attempt = 0; attempt < 2; attempt += 1) {
		try {
			fixture("teardown")
			return ""
		} catch (reason) {
			failure = describe(reason)
		}
	}
	return failure
}

function displayDate(value) {
	const [year, month, day] = value.split("-")
	return `${day}-${month}-${year}`
}

function addDays(value, amount) {
	const date = new Date(`${value}T00:00:00Z`)
	date.setUTCDate(date.getUTCDate() + amount)
	return date.toISOString().slice(0, 10)
}

function assert(condition, detail) {
	if (!condition) throw new Error(describe(detail))
}

function describe(value) {
	if (value instanceof Error) return value.stack || value.message
	return typeof value === "string" ? value : JSON.stringify(value)
}
