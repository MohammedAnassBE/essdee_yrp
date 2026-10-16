import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { createRequire } from "node:module"
import { cellText, cellTone, columnGroups, parsePastedNames, reportCsv, validateWipFilters } from "../frontend/src/departments/merch/reports/workInProgress.js"
import { selectionSummary } from "../frontend/src/departments/merch/reports/wipSelectionSummary.js"

const lots = Array.from({ length: 156 }, (_, index) => `Lot ${index + 1}`)
assert.deepEqual(selectionSummary([], [], 300), { visible: [], hiddenCount: 0 })
assert.deepEqual(selectionSummary(lots.slice(0, 3), [90, 90, 90], 300), { visible: lots.slice(0, 3), hiddenCount: 0 })
assert.deepEqual(selectionSummary(lots.slice(0, 6), Array(6).fill(90), 300), { visible: lots.slice(0, 6), hiddenCount: 0 })
assert.deepEqual(selectionSummary(lots, Array(6).fill(90), 300), { visible: lots.slice(0, 6), hiddenCount: 150 })
assert.deepEqual(selectionSummary(lots, Array(6).fill(90), 175), { visible: lots.slice(0, 2), hiddenCount: 154 })
assert.deepEqual(selectionSummary(lots, Array(6).fill(90), 185), { visible: lots.slice(0, 4), hiddenCount: 152 }, "chip gaps count when fitting two rows")
assert.deepEqual(selectionSummary(lots, Array(6).fill(900), 300), { visible: lots.slice(0, 2), hiddenCount: 154 }, "long names use one truncated chip per row")
assert.deepEqual(selectionSummary(lots, Array(6).fill(90), 600), { visible: lots.slice(0, 6), hiddenCount: 150 }, "at most six inline values even on wide screens")
assert.deepEqual(selectionSummary(lots, [], 0), { visible: [], hiddenCount: 156 }, "unmeasured selections retain an accurate count")
assert.deepEqual(selectionSummary(["Printing", "Fusing", "Ironing"], [100, 90, 80], 300), { visible: ["Printing", "Fusing", "Ironing"], hiddenCount: 0 }, "process order is preserved")

assert.deepEqual(parsePastedNames(" C0826-54\tC0826-57\n\r\nC0426-35/2\nC0826-54 "), ["C0826-54", "C0826-57", "C0426-35/2"])
assert.deepEqual(parsePastedNames("Style with spaces\tOther style\nStyle with spaces"), ["Style with spaces", "Other style"])
const columns = [
	{ fieldname: "style", label: "Style", group: "", fieldtype: "Data" },
	{ fieldname: "cut_qty", label: "Cut Qty", group: "Cut", fieldtype: "Float" },
	{ fieldname: "difference", label: "Diff", group: "Cut", fieldtype: "Float", is_difference: true },
	{ fieldname: "cut_0_sent", label: "Chest Fusing Sent", group: "Chest Fusing", stage: "cut", process: "Chest Fusing", fieldtype: "Float" },
	{ fieldname: "date", label: "Last Cut Date", group: "Dates", fieldtype: "Date" },
]
assert.deepEqual(columnGroups(columns), [{ label: "", span: 1 }, { label: "Cut", span: 2 }, { label: "Chest Fusing", span: 1 }, { label: "Dates", span: 1 }])
const row = { style: "A", cut_qty: 1200, difference: -10, not_in_ipd: ["Chest Fusing"], date: "2026-10-15" }
assert.equal(cellText(row, columns[1]), "1,200")
assert.equal(cellText(row, columns[3]), "not in IPD")
assert.equal(cellText(row, columns[4]), "15-10-2026")
assert.equal(cellText({}, columns[3]), "", "no-WO chain and cut-only cells remain blank")
assert.equal(cellText({ cut_0_sent: 0, process_stages: { "Chest Fusing": "cut" } }, columns[3]), "0", "in-IPD zero stays numeric")
assert.equal(cellTone(row, columns[2]), "wip-negative")
assert.equal(cellTone({ difference: 2 }, columns[2]), "wip-positive")
assert.equal(cellTone({ difference: 0 }, columns[2]), "")
assert.equal(cellTone({ difference: null }, columns[2]), "")
assert.equal(cellTone(row, columns[1]), "")
const csv = reportCsv([row, { style: '=HYPERLINK("evil")', difference: -2 }], columns)
assert.ok(csv.includes('"1200","-10","not in IPD"'))
assert.ok(csv.includes("'=HYPERLINK"), "CSV text does not execute spreadsheet formulas")
assert.ok(csv.includes('"-2"'), "negative numeric quantities stay numeric")

const processColumns = [
	{ fieldname: "cut_0_diff", label: "Yolk Fusing Diff", group: "Yolk Fusing (cut stage)", stage: "cut", process: "Yolk Fusing", fieldtype: "Float", is_difference: true },
	{ fieldname: "piece_0_diff", label: "Yolk Fusing Diff", group: "Yolk Fusing (piece stage)", stage: "piece", process: "Yolk Fusing", fieldtype: "Float", is_difference: true },
	{ fieldname: "piece_3_to_sew_diff", label: "Ironing to Sew Diff", group: "Ironing", stage: "piece", process: "Ironing", fieldtype: "Float", is_difference: true },
	{ fieldname: "piece_3_to_yolk_fusing_diff", label: "Ironing to Yolk Fusing Diff", group: "Ironing", stage: "piece", process: "Ironing", fieldtype: "Float", is_difference: true },
]
assert.deepEqual(columnGroups(processColumns), [
	{ label: "Yolk Fusing (cut stage)", span: 1 }, { label: "Yolk Fusing (piece stage)", span: 1 }, { label: "Ironing", span: 2 },
])
const cutRow = { process_stages: { "Yolk Fusing": "cut", Ironing: "piece" }, cut_0_diff: -2, piece_3_to_sew_diff: -2 }
const pieceRow = { process_stages: { "Yolk Fusing": "piece", Ironing: "piece" }, piece_0_diff: -3, piece_3_to_yolk_fusing_diff: 2458 }
assert.deepEqual(processColumns.map((col) => cellText(cutRow, col)), ["-2", "", "-2", ""])
assert.deepEqual(processColumns.map((col) => cellText(pieceRow, col)), ["", "-3", "", "2,458"])
assert.equal(cellTone(pieceRow, processColumns[3]), "wip-positive")
assert.equal(cellText({ not_in_ipd: ["Yolk Fusing"] }, processColumns[0]), "not in IPD")
assert.equal(cellText({ not_in_ipd: ["Yolk Fusing"] }, processColumns[1]), "not in IPD")
assert.equal(cellText({ is_total_row: true, cut_0_diff: -2 }, processColumns[0]), "-2")
assert.equal(cellTone({ is_total_row: true, cut_0_diff: -2 }, processColumns[0]), "wip-negative")
const cutOnlyRow = { process_stages: {}, not_in_ipd: [], process_chains: {} }
assert.deepEqual(processColumns.map((col) => cellText(cutOnlyRow, col)), ["", "", "", ""])
assert.deepEqual(processColumns.map((col) => cellTone(cutOnlyRow, col)), ["", "", "", ""])
assert.equal(cellText(cutOnlyRow, columns[3]), "", "cut-only rows show blank process cells")
assert.ok(reportCsv([cutRow, pieceRow], processColumns).includes('"","-3","","2458"'))

const defaults = { category: "", product_season: "", lot_status: "Open", lot: [], item: [], from_date: "", to_date: "" }
assert.deepEqual(validateWipFilters(defaults), { category: "Set at least one filter other than Lot Status." })
assert.deepEqual(validateWipFilters({ ...defaults, product_season: "Winter" }), {})
assert.deepEqual(validateWipFilters({ ...defaults, lot: ["A"], from_date: "2026-10-15" }), { to_date: "To Date is required" })
assert.deepEqual(validateWipFilters({ ...defaults, item: ["A"], to_date: "2026-10-15" }), { from_date: "From Date is required" })
assert.deepEqual(validateWipFilters({ ...defaults, category: "Vest", from_date: "2026-10-15", to_date: "2026-10-15" }), {})

const require = createRequire(new URL("../frontend/package.json", import.meta.url))
const { parse, compileScript, compileStyle, compileTemplate } = require("@vue/compiler-sfc")
for (const name of ["MerchReports.vue", "reports/WorkInProgressReport.vue", "reports/PasteListDialog.vue", "reports/WipLinkMultiSelect.vue"]) {
	const path = new URL(`../frontend/src/departments/merch/${name}`, import.meta.url)
	const source = readFileSync(path, "utf8")
	const { descriptor, errors } = parse(source)
	assert.deepEqual(errors, [], name)
	const script = compileScript(descriptor, { id: name })
	const template = compileTemplate({ source: descriptor.template.content, filename: path.pathname, id: name, compilerOptions: { bindingMetadata: script.bindings } })
	assert.deepEqual(template.errors, [], name)
	for (const style of descriptor.styles) {
		const compiled = compileStyle({ source: style.content, filename: path.pathname, id: `data-v-${name}`, scoped: style.scoped })
		assert.deepEqual(compiled.errors, [], `${name} styles`)
	}
}
const view = readFileSync(new URL("../frontend/src/departments/merch/reports/WorkInProgressReport.vue", import.meta.url), "utf8")
assert.match(view, /reportKey: "merch-work-in-progress"/)
assert.ok(view.indexOf("validateWipFilters(filters)") < view.indexOf("report.generate({"))
assert.match(view, /role="alert"/)
assert.match(view, /payload.value\?\.not_in_ipd_processes/)
assert.match(view, /No columns for:/)
assert.match(view, /not in the IPD of any lot with sewing work orders/)
assert.doesNotMatch(view, /chain_labels|:title=/)
assert.match(view, /overflow: auto/)
assert.match(view, /grid-template-columns: minmax\(0, 1fr\)/)
assert.match(view, /align-items: start/)
const multiSelect = readFileSync(new URL("../frontend/src/departments/merch/reports/WipLinkMultiSelect.vue", import.meta.url), "utf8")
assert.match(multiSelect, /in summary\.visible/)
assert.match(multiSelect, /\+\{\{ summary\.hiddenCount \}\} more/)
assert.match(multiSelect, /<Dialog v-model:visible="allVisible" modal/)
assert.match(multiSelect, /in modelValue"/)
assert.match(multiSelect, /overflow-y: auto/)
assert.match(multiSelect, /maxWidth: 'calc\(100vw - 24px\)'/)
assert.match(multiSelect, /new ResizeObserver\(measure\)/)
assert.match(multiSelect, /@select="add"/)
assert.match(multiSelect, /@click="move\(index\)"/)
assert.match(multiSelect, /@click="clear"/)
assert.doesNotMatch(view, /router-link|window\.open|<a\s/)
const page = readFileSync(new URL("../frontend/src/departments/merch/MerchReports.vue", import.meta.url), "utf8")
assert.match(page, /back-to="\/merch"/)
assert.match(page, /route\.query\.report/)
assert.match(page, /reports\.value\[report.key\]\?\.can_read/)
console.log("Merch WIP view tests passed (selection summaries for 0/3/6/156 values, responsive chip counts, formatting, groups, paste, validation, CSV, Vue compilation)")
