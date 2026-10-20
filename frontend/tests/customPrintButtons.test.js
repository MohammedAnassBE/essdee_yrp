import assert from "node:assert/strict"
import test from "node:test"
import { getCustomPrintButtons } from "../src/utils/customPrintButtons.js"

const cases = [
	["YRP Production Order", { docstatus: 1 }, "production-order", "Print", "Essdee Production Order", null],
	["SD YRP Product", {}, "tech-pack", "Print Tech Pack", "Essdee Product Tech Pack", 1],
	["SD YRP Product Release", {}, "tech-pack", "Print Tech Pack", "Essdee Tech Pack", 1],
	["SD YRP Finishing Plan Dispatch", { docstatus: 1 }, "dispatch", "Print Dispatch", "Essdee Finishing Plan Dispatch", 1],
	["SD YRP Lot", { has_cloth_program: true }, "cloth-program", "Cloth Program", "Essdee Lot Cloth Program", 1],
]
for (const [doctype, fields, key, label, format, noLetterhead] of cases) {
	test(`${doctype}: saved record, permission, visibility and exact URL`, () => {
		const record = { name: "DOC/1 & 2", ...fields }
		const query = new URLSearchParams({ doctype, name: record.name, trigger_print: "1", format })
		if (noLetterhead !== null) query.set("no_letterhead", "1")
		assert.deepEqual(getCustomPrintButtons(doctype, record, { can_print: true }), [{ key, label, url: `/printview?${query}` }])
		assert.deepEqual(getCustomPrintButtons(doctype, record, { can_print: false }), [])
		assert.deepEqual(getCustomPrintButtons(doctype, { ...record, name: "" }, { can_print: true }), [])
		if ("docstatus" in fields) for (const docstatus of [0, 2]) assert.deepEqual(getCustomPrintButtons(doctype, { ...record, docstatus }, { can_print: true }), [])
		if (doctype === "SD YRP Lot") assert.deepEqual(getCustomPrintButtons(doctype, { name: record.name }, { can_print: true }), [])
	})
}
test("LaySheet uses separate permissions and selects movement chart at the nine-part boundary", () => {
	const doctype = "SD YRP Cutting LaySheet"
	for (const count of [0, 9, 10]) {
		const record = { name: "SHEET/1", calculated_parts: Array.from({ length: count }, (_, i) => i).join(",") }
		for (const can_print_movement_chart of [false, true]) for (const can_print_laysheet of [false, true]) {
			const expected = []
			const make = (key, label, format) => ({ key, label, url: `/printview?${new URLSearchParams({ doctype, name: record.name, trigger_print: "1", format, no_letterhead: "1" })}` })
			if (can_print_movement_chart) expected.push(make("movement-chart", "Print Movement Chart", count > 9 ? "Essdee Cutting Movement Chart 2" : "Essdee Cutting Movement Chart"))
			if (can_print_laysheet) expected.push(make("laysheet", "Print Laysheet", "Essdee Cutting LaySheet"))
			assert.deepEqual(getCustomPrintButtons(doctype, record, { can_print_movement_chart, can_print_laysheet }), expected)
		}
	}
	assert.deepEqual(getCustomPrintButtons(doctype, {}, { can_print_laysheet: true }), [])
})
