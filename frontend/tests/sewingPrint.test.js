import assert from "node:assert/strict"
import test from "node:test"

const builders = () => import("../src/utils/sewingPrint.js")
const entries = url => [...new URL(url, "https://test.local").searchParams]

test("sewing consumption print preserves exact parameter order and encodes names", async () => {
	const { buildSewingConsumptionPrintUrl } = await builders()
	const url = buildSewingConsumptionPrintUrl({ ipd: "IPD/26 & #1", lot: "LOT/26 & #2" })
	assert.equal(url, "/printview?doctype=YRP+Item+Production+Detail&name=IPD%2F26+%26+%231&format=Essdee+Sewing+Consumption&no_letterhead=1&lot=LOT%2F26+%26+%232&trigger_print=1")
	assert.deepEqual(entries(url), [
		["doctype", "YRP Item Production Detail"], ["name", "IPD/26 & #1"],
		["format", "Essdee Sewing Consumption"], ["no_letterhead", "1"],
		["lot", "LOT/26 & #2"], ["trigger_print", "1"],
	])
})

test("sewing consumption print uses empty strings for missing values", async () => {
	const { buildSewingConsumptionPrintUrl } = await builders()
	assert.equal(buildSewingConsumptionPrintUrl({}), "/printview?doctype=YRP+Item+Production+Detail&name=&format=Essdee+Sewing+Consumption&no_letterhead=1&lot=&trigger_print=1")
	assert.equal(buildSewingConsumptionPrintUrl({ ipd: null, lot: null }), buildSewingConsumptionPrintUrl({}))
})

test("monthly summary input print preserves exact parameter order and encodes names", async () => {
	const { buildMonthlySummaryPrintUrl } = await builders()
	const url = buildMonthlySummaryPrintUrl({ supplier: "Unit/1 & #2", filters: { fromDate: "2026-10-01", toDate: "2026-10-31", inputType: "Input/1 & #2", showGrn: false } })
	assert.equal(url, "/printview?doctype=Supplier&name=Unit%2F1+%26+%232&format=Essdee+Sewing+Plan+Monthly+Summary&no_letterhead=1&supplier=Unit%2F1+%26+%232&start_date=2026-10-01&end_date=2026-10-31&trigger_print=1&input_type=Input%2F1+%26+%232")
	assert.deepEqual(entries(url), [
		["doctype", "Supplier"], ["name", "Unit/1 & #2"], ["format", "Essdee Sewing Plan Monthly Summary"],
		["no_letterhead", "1"], ["supplier", "Unit/1 & #2"], ["start_date", "2026-10-01"],
		["end_date", "2026-10-31"], ["trigger_print", "1"], ["input_type", "Input/1 & #2"],
	])
})

test("monthly summary GRN print appends show_grn and omits input_type", async () => {
	const { buildMonthlySummaryPrintUrl } = await builders()
	const url = buildMonthlySummaryPrintUrl({ supplier: "Unit/1 & #2", filters: { fromDate: "2026-10-01", toDate: "2026-10-31", inputType: "Ignored", showGrn: true } })
	assert.equal(url, "/printview?doctype=Supplier&name=Unit%2F1+%26+%232&format=Essdee+Sewing+Plan+Monthly+Summary&no_letterhead=1&supplier=Unit%2F1+%26+%232&start_date=2026-10-01&end_date=2026-10-31&trigger_print=1&show_grn=1")
	assert.equal(new URL(url, "https://test.local").searchParams.has("input_type"), false)
})

test("monthly summary print uses empty strings for missing values", async () => {
	const { buildMonthlySummaryPrintUrl } = await builders()
	const expected = "/printview?doctype=Supplier&name=&format=Essdee+Sewing+Plan+Monthly+Summary&no_letterhead=1&supplier=&start_date=&end_date=&trigger_print=1&input_type="
	assert.equal(buildMonthlySummaryPrintUrl({ filters: {} }), expected)
	assert.equal(buildMonthlySummaryPrintUrl({ supplier: null, filters: { fromDate: null, toDate: null, inputType: null } }), expected)
	assert.equal(buildMonthlySummaryPrintUrl({}), expected)
})
