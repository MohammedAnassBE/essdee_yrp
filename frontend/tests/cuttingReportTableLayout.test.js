import assert from "node:assert/strict"
import fs from "node:fs"
import test from "node:test"
import { findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"

const reportUtils = {
	attributeValue: (row, attribute) => row.attributes?.[attribute] || "",
	number: (value) => String(value ?? ""),
	quantity: (value) => String(value ?? ""),
	rowColour: (row) => row.attributes?.Colour,
}
const mount = (file, props) => mountComponent(loadComponent(new URL(`../src/departments/cutting/reports/${file}`, import.meta.url).pathname, { "../../../components/reports/reportUtils.js": reportUtils }), props)
const classOf = (node) => String(node.props.class || "")
const rowsOf = (root) => findNodes(root, (node) => node.type === "tr")
const cellsOf = (row) => findNodes(row, (node) => node.type === "td")
const source = (file) => fs.readFileSync(new URL(`../src/${file}`, import.meta.url), "utf8")

test("Completion matrix uses the shared report table with a wrapping panel column and a total row", () => {
	const group = { is_set_item: 1, set_item_attr: "Part", stiching_attr: "Panels", Panels: { Top: ["Top Front", "Top Back"] }, attributes: ["Colour", "Part"], primary_attribute_values: ["S"], items: [{ attributes: { Colour: "Navy", Part: "Top" }, values: { S: 4 }, total_qty: 4 }], total_qty: { S: 4 } }
	const root = mount("CompletionMatrix.vue", { groups: [group], totalQty: 4, showAverages: true })
	assert.match(classOf(findNodes(root, (node) => node.type === "table")[0]), /\breport-table\b/)
	const [header, row, total] = rowsOf(root)
	assert.equal(findNodes(header, (node) => node.type === "th").length, 8)
	const cells = cellsOf(row)
	assert.match(classOf(cells[1]), /report-cell--text/)
	assert.match(classOf(cells[3]), /report-cell--num/)
	assert.match(classOf(cells.at(-1)), /report-cell--last-column/)
	assert.equal(findNodes(cells.at(-1), (node) => classOf(node) === "panel-chips").length, 1)
	assert.equal(cells.filter((cell) => /report-cell--last-column/.test(classOf(cell))).length, 1)
	assert.match(classOf(total), /report-total-row/)
	root.__vue_app__.unmount()
})

test("Completion matrix marks the total column as last when no averages or panels follow", () => {
	const root = mount("CompletionMatrix.vue", { groups: [{ attributes: ["Colour"], primary_attribute_values: ["S"], items: [{ attributes: { Colour: "Navy" }, values: { S: 1 }, total_qty: 1 }], total_qty: { S: 1 } }], totalQty: 1 })
	const cells = cellsOf(rowsOf(root)[1])
	assert.match(classOf(cells.at(-1)), /report-cell--last-column/)
	root.__vue_app__.unmount()
})

test("Cloth table shades its total row through the shared class", () => {
	const root = mount("ClothTable.vue", { rows: [{ cloth_item_variant: "Rib", required_weight: 1 }], totals: { required: 1 } })
	const [, row, total] = rowsOf(root)
	assert.match(classOf(cellsOf(row)[5]), /report-cell--num/)
	assert.match(classOf(total), /report-total-row/)
	assert.match(classOf(cellsOf(total).at(-1)), /report-cell--last-column/)
	root.__vue_app__.unmount()
})

test("Multi CCR and Daily Cut Sheet tables use the shared report table classes", () => {
	const multiCcr = source("departments/cutting/reports/MultiCCRReport.vue")
	assert.equal((multiCcr.match(/class="erp-data-table report-table/g) || []).length, 2)
	assert.doesNotMatch(multiCcr, /class="report-total"/)
	assert.equal((multiCcr.match(/class="report-total-row"/g) || []).length, 2)
	const cutSheet = source("departments/cutting/reports/DailyCutSheetReport.vue")
	assert.match(cutSheet, /class="erp-data-table report-table cut-sheet-table"/)
	assert.match(cutSheet.split("<style scoped>")[1], /\.cutter-chip \{[^}]*white-space: nowrap/)
})

test("Lot OCR left-aligns its process, documents and type cells and tops the serial", () => {
	const style = source("departments/sales/LotOcrTable.vue").split("<style scoped>")[1]
	assert.match(style, /\.ppo-lot-ocr__table-wrap tbody th, \.ppo-lot-ocr__table-wrap \.ppo-lot-ocr__documents \{ text-align: left; \}/)
	assert.match(style, /\.ppo-lot-ocr__serial \{[^}]*vertical-align: top/)
})
