import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

const source = path => readFileSync(new URL(path, import.meta.url), "utf8")
const printButton = text => (text.match(/<Button\b(?:"[^"]*"|[^">])*\/>/g) || []).find(button => button.includes('label="Print"')) || ""

test("web sewing consumption wires the Print button and availability to the current IPD", () => {
	const page = source("../src/departments/sewing/plan/SewingConsumption.vue")
	assert.match(page, /import \{ buildSewingConsumptionPrintUrl \} from "[^"\n]*utils\/sewingPrint\.js"/)
	assert.doesNotMatch(page, /openPrintUrl/)
	const button = printButton(page)
	assert.match(button, /icon="pi pi-print"/)
	assert.match(button, /severity="secondary"/)
	assert.match(button, /\boutlined\b/)
	assert.match(button, /:disabled="!state\.data\?\.ipd \|\| loading \|\| state\.busy"/)
	assert.match(button, /@click="handlePrint"/)
	assert.match(page, /buildSewingConsumptionPrintUrl\(\{ ipd: props\.state\.data\.ipd, lot: props\.state\.lot \}\)/)
	assert.match(page, /window\.open\(url, "_blank", "noopener"\)/)
})

test("web monthly summary offers Print in the report actions menu only for loaded results", () => {
	const page = source("../src/departments/sewing/reports/SewingMonthlySummary.vue")
	assert.match(page, /import \{ buildMonthlySummaryPrintUrl \} from "[^"\n]*utils\/sewingPrint\.js"/)
	assert.doesNotMatch(page, /openPrintUrl/)
	assert.ok(page.includes(":actions=\"[{ label: 'Print', icon: 'pi pi-print', visible: generated && data.rows?.length > 0 && !loading, command: handlePrint }]\""))
	assert.match(page, /buildMonthlySummaryPrintUrl\(\{ supplier: supplier\.value, filters: props\.filters \}\)/)
	assert.match(page, /window\.open\(url, "_blank", "noopener"\)/)
})

test("Desk sewing consumption prints the Frappe 16 doctype and format", () => {
	const page = source("../../essdee_yrp/public/js/SewingPlan/components/Consumption.vue")
	assert.ok(page.includes("YRP%20Item%20Production%20Detail"))
	assert.ok(page.includes("Essdee%20Sewing%20Consumption"))
	assert.ok(!page.includes("doctype=Item%20Production%20Detail"))
})

test("Desk monthly summary prints the Frappe 16 format", () => {
	const page = source("../../essdee_yrp/public/js/SewingPlan/components/MonthlySummaryTab.vue")
	assert.ok(page.includes("'Essdee Sewing Plan Monthly Summary'"))
	assert.ok(!page.includes("format: 'Sewing Plan Monthly Summary'"))
})

test("Desk rework restores the first Print column with both formats and consistent colspans", () => {
	const page = source("../../essdee_yrp/public/js/WorkOrder/components/ReworkPage.vue")
	assert.match(page, /<thead>\s*<tr>\s*<th>\{\{ __\("Print"\) \}\}<\/th>/)
	assert.match(page, /<tr class="summary-row"[^>]*>\s*<td[^>]*@click\.stop="redirectToPrint\(value\.grn_number\)"[^>]*>/)
	assert.match(page, /frappe\.utils\.icon\('printer', 'sm'\)/)
	assert.match(page, /const printerIcon = frappe\.utils\.icon\('printer', 'sm'\)/)
	assert.match(page, /v-html="printerIcon"/)
	assert.match(page, /:colspan="9 \+ items\.types\.length"/)
	assert.match(page, /colspan="8">\{\{ __\("Total"\) \}\}/)
	assert.match(page, /showReworkedValue\.value \? "Essdee Reworked Print" : "Essdee Rework Print"/)
	assert.ok(page.includes('encodeURIComponent("YRP Goods Received Note")'))
	assert.match(page, /window\.open\(frappe\.urllib\.get_full_url\(/)
	assert.match(page, /encodeURIComponent\(grn\)/)
	assert.match(page, /if \(!w\) frappe\.msgprint\(__\("Please enable pop-ups"\)\)/)
})
