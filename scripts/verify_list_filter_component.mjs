#!/usr/bin/env node

import { createRequire } from "node:module"
import { existsSync, readFileSync } from "node:fs"
import { join } from "node:path"

const require = createRequire("/home/anas/.claude/playwright/package.json")
const { chromium } = require("playwright")
const SITE = "http://erp-migration-test.site:8001"
const [usr, pwd] = readFileSync("/home/anas/.frappe-debug-creds-mrp3", "utf8").trim().split("\n")
const commonComponents = join(process.cwd(), "frontend/src/components/common")
const temporalComponentModes = {
	"DateField.vue": "date",
	"TimeField.vue": "time",
	"DateTimeField.vue": "datetime",
}
const temporalComponentContract = Object.entries(temporalComponentModes).every(([file, mode]) => {
	const componentPath = join(commonComponents, file)
	return existsSync(componentPath)
		&& readFileSync(componentPath, "utf8").includes(`<TemporalFieldBase v-bind="$attrs" mode="${mode}" />`)
})
const listViewSource = readFileSync(join(commonComponents, "ListView.vue"), "utf8")
const selectableListContract = listViewSource.includes('selectable: { type: Boolean, default: false }')
	&& listViewSource.includes('"selection-change"')
	&& listViewSource.includes('emit("selection-change", [...selection])')

const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({ viewport: { width: 1500, height: 950 } })
const page = await context.newPage()
const errors = []
const linkSearchRequests = []
page.on("pageerror", (error) => errors.push(`page: ${error.message}`))
page.on("console", (message) => {
	if (message.type() === "error") errors.push(`console: ${message.text()}`)
})
page.on("request", (request) => {
	if (request.url().includes("essdee_yrp.api.link_search.link_search")) {
		try {
			linkSearchRequests.push(JSON.parse(request.postData() || "{}"))
		} catch {
			linkSearchRequests.push({})
		}
	}
})

await page.goto(`${SITE}/login`, { waitUntil: "domcontentloaded" })
await page.fill("#login_email", usr.trim())
await page.fill("#login_password", pwd.trim())
await Promise.all([
	page.waitForNavigation({ waitUntil: "domcontentloaded", timeout: 20000 }).catch(() => {}),
	page.click(".btn-login, button[type=submit]"),
])

await page.goto(`${SITE}/web/cutting/plans`, { waitUntil: "domcontentloaded" })
await page.getByRole("button", { name: "Filters", exact: true }).waitFor({ timeout: 20000 })
await page.getByRole("button", { name: /^Filters/ }).click()
const dialog = page.getByRole("dialog", { name: "Filters" })
await dialog.waitFor()
const row = dialog.locator(".filter-row").first()

async function chooseField(label) {
	await row.locator(".p-select").first().click()
	const overlay = page.locator(".p-select-overlay:visible")
	await overlay.locator("input").fill(label)
	await page.getByRole("option", { name: label, exact: true }).click()
}

async function chooseCondition(label) {
	await row.locator(".p-select").nth(1).click()
	await page.getByRole("option", { name: label, exact: true }).click()
}

const defaultControl = {
	field: await row.locator(".p-select-label").first().textContent(),
	condition: await row.locator(".p-select-label").nth(1).textContent(),
	isLink: await row.locator(".p-autocomplete").count() === 1,
}

await chooseField("Lot")
const lotControlIsLink = await row.locator(".p-autocomplete").count() === 1
const lotInput = row.locator(".p-autocomplete input")
const unmatchedLotSearch = "__missing-lot__"
await lotInput.fill(unmatchedLotSearch)
await page.waitForTimeout(700)
const lotOptions = await page.locator(".p-autocomplete-option:visible").allTextContents()
const lotEmptyState = await page.locator(".link-field__empty:visible").allTextContents()
const lotSearchOnlyMatchesVisibleText = lotOptions.length
	? lotOptions.every((text) => text.toLocaleLowerCase().includes(unmatchedLotSearch.toLocaleLowerCase()))
	: lotEmptyState.some((text) => text.includes("No SD YRP Lot found"))

await chooseField("Item")
await row.locator(".p-autocomplete input").fill("Flame")
await page.waitForTimeout(700)
const itemRequest = [...linkSearchRequests].reverse().find((request) =>
	(request?.args?.doctype || request?.doctype) === "Item",
)
const itemFilters = itemRequest?.args?.filters || itemRequest?.filters || null

await chooseField("CP Status")
const statusControlIsSelect = await row.locator(".filter-row__value > .p-select").count() === 1
await chooseCondition("In")
const statusInControlIsMultiSelect = await row.locator(".p-multiselect").count() === 1

await chooseField("Is Manual Entry")
const checkConditionLabels = await (async () => {
	await row.locator(".p-select").nth(1).click()
	const values = await page.locator(".p-select-overlay:visible .p-select-option").allTextContents()
	await page.keyboard.press("Escape")
	return values
})()
const checkValueLabels = await (async () => {
	await row.locator(".filter-row__value .p-select").click()
	const values = await page.locator(".p-select-overlay:visible .p-select-option").allTextContents()
	await page.keyboard.press("Escape")
	return values
})()

await chooseField("Cutting Start Date")
const dateCondition = await row.locator(".p-select-label").nth(1).textContent()
const dateRangeControl = await row.locator(".p-datepicker").count() === 1
await chooseCondition("Timespan")
const timespanControlIsSelect = await row.locator(".filter-row__value > .p-select").count() === 1
await chooseCondition("In")
const dateInControlIsText = await row.locator('.filter-row__value input[placeholder="Values separated by commas"]').count() === 1

await chooseField("Last Updated On")
const datetimeInput = row.locator(".filter-row__value .p-datepicker-input")
const datetimeManualInputLocked = await datetimeInput.getAttribute("readonly") !== null
const datetimeTrigger = row.locator(".filter-row__value .p-datepicker-dropdown")
const datetimeTriggerLabel = await datetimeTrigger.getAttribute("aria-label")
await datetimeTrigger.click()
const datetimePanel = page.locator(".erp-date-time-panel:visible")
await datetimePanel.waitFor()
const datetimePanelLabel = await datetimePanel.getAttribute("aria-label")
await datetimeTrigger.click()

await chooseField("Maximum Allow Percent")
const numericControl = await row.locator(".p-inputnumber").count() === 1

await chooseField("Lot")
await chooseCondition("Is")
const isOptions = await (async () => {
	await row.locator(".filter-row__value .p-select").click()
	const values = await page.locator(".p-select-overlay:visible .p-select-option").allTextContents()
	await page.keyboard.press("Escape")
	return values
})()

await chooseCondition("In")
const multiValueHelp = await row.locator(".filter-value-help").textContent()

const fieldBeforeEmptySearch = await row.locator(".p-select-label").first().textContent()

await row.locator(".p-select").first().click()
const fieldOverlay = page.locator(".p-select-overlay:visible")
await fieldOverlay.locator("input").fill("(")
const childFieldOptions = await fieldOverlay.locator(".p-select-option").count()
await page.keyboard.press("Escape")
await page.waitForTimeout(50)
const fieldAfterEmptySearch = await row.locator(".p-select-label").first().textContent()

// Re-selecting the already-active field is a no-op in PrimeVue, so the user's
// current condition is intentionally preserved. Restore Equals explicitly
// before exercising the single-value LinkField path.
await chooseCondition("Equals")
const fieldAfterConditionRestore = await row.locator(".p-select-label").first().textContent()

const partialResults = {
	temporalComponentContract,
	selectableListContract,
	defaultControl,
	lotControlIsLink,
	lotSearchOnlyMatchesVisibleText,
	lotEmptyState,
	itemLinkFilters: itemFilters,
	statusControlIsSelect,
	statusInControlIsMultiSelect,
	checkConditionLabels,
	checkValueLabels,
	dateCondition,
	dateRangeControl,
	datetimeManualInputLocked,
	datetimeTriggerLabel,
	datetimePanelLabel,
	timespanControlIsSelect,
	dateInControlIsText,
	numericControl,
	isOptions,
	multiValueHelp,
	childFieldOptions,
	fieldBeforeEmptySearch,
	fieldAfterEmptySearch,
	fieldAfterConditionRestore,
}
const partialPassed = defaultControl.field === "ID"
	&& temporalComponentContract
	&& selectableListContract
	&& defaultControl.condition === "Equals"
	&& defaultControl.isLink
	&& lotControlIsLink
	&& lotSearchOnlyMatchesVisibleText
	&& Number(itemFilters?.has_variants) === 1
	&& statusControlIsSelect
	&& statusInControlIsMultiSelect
	&& checkConditionLabels.filter((value) => ["Equals", "Not Equals", "Like", "Not Like", "In", "Not In", "Is", "Greater Than", "Less Than", "Greater Than or Equal To", "Less Than or Equal To", "Between", "Timespan"].includes(value)).length === 1
	&& checkValueLabels.some((value) => value.includes("Yes"))
	&& checkValueLabels.some((value) => value.includes("No"))
	&& dateCondition === "Between"
	&& dateRangeControl
	&& datetimeManualInputLocked
	&& datetimeTriggerLabel === "Choose date and time"
	&& datetimePanelLabel === "Choose date and time"
	&& timespanControlIsSelect
	&& dateInControlIsText
	&& numericControl
	&& isOptions.some((value) => value.includes("Set"))
	&& isOptions.some((value) => value.includes("Not Set"))
	&& multiValueHelp?.includes("commas")
	&& childFieldOptions > 0
	&& fieldBeforeEmptySearch === "Lot"
	&& fieldAfterEmptySearch === "Lot"
	&& fieldAfterConditionRestore === "Lot"
	&& errors.length === 0

const lotFixtureResponse = await context.request.get(`${SITE}/api/resource/SD%20YRP%20Lot`, {
	params: { fields: JSON.stringify(["name"]), order_by: "modified desc", limit_page_length: 1 },
})
if (!lotFixtureResponse.ok()) {
	throw new Error(`Unable to inspect SD YRP Lot fixtures (${lotFixtureResponse.status()}).`)
}
const availableLotLabel = (await lotFixtureResponse.json()).data?.[0]?.name || ""
if (!availableLotLabel) {
	console.log(JSON.stringify({
		passed: partialPassed,
		skipped: true,
		reason: "Core filter controls passed; fixture-dependent apply/sidebar checks skipped because no SD YRP Lot exists.",
		...partialResults,
		errors,
	}, null, 2))
	await browser.close()
	process.exit(partialPassed ? 0 : 1)
}
const lotSearchText = availableLotLabel.slice(0, Math.min(6, availableLotLabel.length))
const finalLotInput = row.locator(".p-autocomplete input")
await finalLotInput.click()
await finalLotInput.fill("")
const finalLotSearch = page.waitForResponse((response) =>
	response.request().method() === "POST"
	&& response.url().includes("essdee_yrp.api.link_search.link_search")
	&& (() => {
		try {
			const body = JSON.parse(response.request().postData() || "{}")
			const args = typeof body.args === "string" ? JSON.parse(body.args) : (body.args || body)
			return args.txt === lotSearchText
		} catch {
			return false
		}
	})(),
)
await finalLotInput.pressSequentially(lotSearchText, { delay: 40 })
const finalLotResponse = await finalLotSearch
const finalLotPayload = await finalLotResponse.json().catch(() => ({}))
const selectedLotOption = page.locator(".p-autocomplete-overlay:visible .p-autocomplete-option").first()
let selectedLotLabel = ""
try {
	selectedLotLabel = await selectedLotOption.textContent({ timeout: 5000 })
} catch (error) {
	throw new Error(`Lot autocomplete did not render its result: ${JSON.stringify({
		fieldBeforeEmptySearch,
		fieldAfterEmptySearch,
		fieldAfterConditionRestore,
		field: await row.locator(".p-select-label").first().textContent(),
		condition: await row.locator(".p-select-label").nth(1).textContent(),
		input: await finalLotInput.inputValue(),
		response: finalLotPayload,
		emptyState: await page.locator(".p-autocomplete-empty-message:visible, .link-field__empty:visible").allTextContents(),
	})}`, { cause: error })
}
await selectedLotOption.click()
const listReload = page.waitForResponse((response) =>
	response.request().method() === "GET"
	&& response.url().includes("/api/resource/SD%20YRP%20Cutting%20Plan"),
)
await dialog.getByRole("button", { name: "Apply Filters", exact: true }).click()
const listResponse = await listReload
const appliedFilters = JSON.parse(new URL(listResponse.url()).searchParams.get("filters") || "[]")
const appliedLotFilter = appliedFilters.find((filter) => filter[0] === "lot")

await page.getByRole("button", { name: /^Filters/ }).click()
await dialog.getByRole("button", { name: "Add a Filter", exact: true }).click()
const childRow = dialog.locator(".filter-row").nth(1)
await childRow.locator(".p-select").first().click()
let overlay = page.locator(".p-select-overlay:visible")
await overlay.locator("input").fill("From Grammage Allowance")
await page.getByRole("option", { name: "From Grammage Allowance (kg) (Grammage Change Logs)", exact: true }).click()
await childRow.locator(".p-select").nth(1).click()
await page.getByRole("option", { name: "Greater Than", exact: true }).click()
await childRow.locator(".p-inputnumber-input").fill("0")
const childReload = page.waitForResponse((response) =>
	response.request().method() === "GET"
	&& response.url().includes("/api/resource/SD%20YRP%20Cutting%20Plan"),
)
await dialog.getByRole("button", { name: "Apply Filters", exact: true }).click()
const childResponse = await childReload
const filtersWithChild = JSON.parse(new URL(childResponse.url()).searchParams.get("filters") || "[]")
const appliedChildFilter = filtersWithChild.find((filter) => filter[0] === "SD YRP Cutting Plan Grammage Change Log")

const planList = await context.request.get(`${SITE}/api/resource/SD%20YRP%20Cutting%20Plan`, {
	params: { fields: JSON.stringify(["name"]), order_by: "modified desc", limit_page_length: 100 },
})
if (!planList.ok()) {
	throw new Error(`Cutting Plan fixture list failed with HTTP ${planList.status()}.`)
}
let sidebarFixture = null
for (const { name } of (await planList.json()).data || []) {
	const response = await context.request.get(
		`${SITE}/api/method/essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan.sd_yrp_cutting_plan.get_web_view_data`,
		{ params: { cutting_plan: name } },
	)
	if (response.status() === 404) continue
	if (!response.ok()) {
		throw new Error(`Cutting Plan ${name} fixture lookup failed with HTTP ${response.status()}.`)
	}
	const data = (await response.json()).message || {}
	if (data.markers?.length && data.laysheets?.length) {
		sidebarFixture = { name, data }
		break
	}
}
if (!sidebarFixture) throw new Error("No Cutting Plan with both marker and Lay Sheet data was found.")

await page.goto(`${SITE}/web/cutting/plans/${encodeURIComponent(sidebarFixture.name)}`, { waitUntil: "domcontentloaded" })
await page.locator(".laysheet-card").first().waitFor({ timeout: 20000 })
await page.locator(".marker-section .rail-filter-button").click()
await dialog.waitFor()
const markerDefaultControl = {
	field: await row.locator(".p-select-label").first().textContent(),
	isLink: await row.locator(".p-autocomplete").count() === 1,
}
await row.locator(".p-autocomplete input").fill(sidebarFixture.data.markers[0].name)
await page.waitForTimeout(700)
const markerRequest = [...linkSearchRequests].reverse().find((request) =>
	(request?.args?.doctype || request?.doctype) === "SD YRP Cutting Marker",
)
const markerLinkFilters = markerRequest?.args?.filters || markerRequest?.filters || null
await dialog.getByRole("button", { name: "Close" }).click()

const layCardsBefore = await page.locator(".laysheet-card").count()
const layStatus = sidebarFixture.data.laysheets.find((sheet) => sheet.status)?.status
await page.locator(".laysheet-section .rail-filter-button").click()
await chooseField("Status")
const sidebarStatusIsSelect = await row.locator(".filter-row__value > .p-select").count() === 1
await row.locator(".filter-row__value > .p-select").click()
await page.getByRole("option", { name: layStatus, exact: true }).click()
await dialog.getByRole("button", { name: "Apply Filters", exact: true }).click()
const layCardsAfter = await page.locator(".laysheet-card").count()
const shownStatuses = await page.locator(".laysheet-card .lay-status").allTextContents()

const results = {
	temporalComponentContract,
	selectableListContract,
	defaultControl,
	lotControlIsLink,
	lotSearchOnlyMatchesVisibleText,
	lotOptions,
	itemLinkFilters: itemFilters,
	statusControlIsSelect,
	statusInControlIsMultiSelect,
	checkConditionLabels,
	checkValueLabels,
	dateCondition,
	dateRangeControl,
	datetimeManualInputLocked,
	datetimeTriggerLabel,
	datetimePanelLabel,
	timespanControlIsSelect,
	dateInControlIsText,
	numericControl,
	isOptions,
	multiValueHelp,
	childFieldOptions,
	selectedLotLabel,
	appliedLotFilter,
	listReloadStatus: listResponse.status(),
	appliedChildFilter,
	childReloadStatus: childResponse.status(),
	markerDefaultControl,
	markerLinkFilters,
	sidebarStatusIsSelect,
	layCardsBefore,
	layCardsAfter,
	layStatus,
	shownStatuses,
	errors,
}

const passed = defaultControl.field === "ID"
	&& temporalComponentContract
	&& selectableListContract
	&& defaultControl.condition === "Equals"
	&& defaultControl.isLink
	&& lotControlIsLink
	&& lotSearchOnlyMatchesVisibleText
	&& Number(itemFilters?.has_variants) === 1
	&& statusControlIsSelect
	&& statusInControlIsMultiSelect
	&& checkConditionLabels.filter((value) => ["Equals", "Not Equals", "Like", "Not Like", "In", "Not In", "Is", "Greater Than", "Less Than", "Greater Than or Equal To", "Less Than or Equal To", "Between", "Timespan"].includes(value)).length === 1
	&& checkValueLabels.some((value) => value.includes("Yes"))
	&& checkValueLabels.some((value) => value.includes("No"))
	&& dateCondition === "Between"
	&& dateRangeControl
	&& datetimeManualInputLocked
	&& datetimeTriggerLabel === "Choose date and time"
	&& datetimePanelLabel === "Choose date and time"
	&& timespanControlIsSelect
	&& dateInControlIsText
	&& numericControl
	&& isOptions.some((value) => value.includes("Set"))
	&& isOptions.some((value) => value.includes("Not Set"))
	&& multiValueHelp?.includes("commas")
	&& childFieldOptions > 0
	&& fieldBeforeEmptySearch === "Lot"
	&& fieldAfterEmptySearch === "Lot"
	&& fieldAfterConditionRestore === "Lot"
	&& appliedLotFilter?.[1] === "="
	&& appliedLotFilter?.[2]
	&& listResponse.ok()
	&& appliedChildFilter?.[1] === "from_grammage_allowance"
	&& appliedChildFilter?.[2] === ">"
	&& childResponse.ok()
	&& markerDefaultControl.field === "Marker ID"
	&& markerDefaultControl.isLink
	&& markerLinkFilters?.cutting_plan === sidebarFixture.name
	&& sidebarStatusIsSelect
	&& layCardsAfter > 0
	&& layCardsAfter <= layCardsBefore
	&& shownStatuses.every((status) => status.trim() === layStatus)
	&& errors.length === 0

console.log(JSON.stringify({ passed, ...results }, null, 2))
await browser.close()
if (!passed) process.exitCode = 1
