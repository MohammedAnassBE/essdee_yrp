import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

import { LOTWISE_TABLE_TOTALS, formatLotwiseValue, lotwiseTableTotals } from "../src/departments/pd/lotwiseTotals.js"
import { LOTWISE_TABLE_COLUMNS } from "../src/departments/pd/pdViews.js"
import { isFormSubmitEnter } from "../src/utils/documentShortcuts.js"

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8")
const sections = read("../src/departments/pd/components/LotwiseCostSections.vue")

test("every Lotwise table has a totals config whose columns exist in that table", () => {
	assert.deepEqual(Object.keys(LOTWISE_TABLE_TOTALS).sort(), Object.keys(LOTWISE_TABLE_COLUMNS).sort())
	for (const [table, config] of Object.entries(LOTWISE_TABLE_TOTALS)) {
		for (const column of [config.label, ...Object.keys(config.columns)]) {
			assert.ok(LOTWISE_TABLE_COLUMNS[table].includes(column), `${table}.${column}`)
		}
	}
})

test("qty and rate totals sum qty and amount and show the weighted rate", () => {
	const rows = [{ size: "M", qty: 10, rate: 100, weight: 200, net_rate: 1000 }, { size: "L", qty: 30, rate: 120, weight: 220, net_rate: 3600 }]
	assert.deepEqual(lotwiseTableTotals("qty_rate_chart", rows), { size: "Total", qty: "40", rate: "₹115", net_rate: "₹4,600" })
})

test("cloth value totals sum qty and net rate, weight the total cost per kg and leave component rates blank", () => {
	const rows = [{ yarn: "A", qty: 2.5, rate: 200, total_cost: 300, net_rate: 750 }, { yarn: "B", qty: 1.5, rate: 100, total_cost: 150, net_rate: 225 }]
	assert.deepEqual(lotwiseTableTotals("cloth_value", rows), { yarn: "Total", qty: "4", total_cost: "₹243.75", net_rate: "₹975" })
})

test("cost tables sum their amount columns; per-piece weights and mixed rates stay blank", () => {
	assert.deepEqual(lotwiseTableTotals("cmt", [{ cost: 12.5 }, { cost: "7.5" }, {}]), { costing_name: "Total", cost: "₹20" })
	assert.deepEqual(lotwiseTableTotals("trade_discounts", [{ rate: 5, total: 100 }, { rate: 2, total: 50.555 }]), { costing_name: "Total", total: "₹150.56" })
	assert.deepEqual(lotwiseTableTotals("piece_cloth_weight", [{ size: "M", weight: 120 }]), { size: "Total" })
})

test("empty tables still show a Total row with zero sums and no weighted rate", () => {
	assert.deepEqual(lotwiseTableTotals("qty_rate_chart", undefined), { size: "Total", qty: "0", rate: "", net_rate: "₹0" })
	assert.throws(() => lotwiseTableTotals("unknown", []), /Totals for unknown/)
})

test("totals use the same formatter as the costing totals rail", () => {
	assert.equal(formatLotwiseValue(123456.789, "currency"), "₹1,23,456.79")
	assert.equal(formatLotwiseValue(12.5, "percent"), "12.5%")
	assert.match(read("../src/departments/pd/components/LotwiseTotalsRail.vue"), /formatLotwiseValue\(values\[metric\.fieldname\], metric\.type\)/)
})

test("every Lotwise child table passes its totals to the shared child table footer", () => {
	assert.equal((sections.match(/<ChildTableField\b/g) || []).length, (sections.match(/:totals="totalsFor\(/g) || []).length)
	assert.match(read("../src/components/common/ChildTableField.vue"), /:footer="totals"/)
	const grid = read("../src/components/common/childGrid/ChildGridTable.vue")
	assert.match(grid, /<ColumnGroup v-if="hasFooter" type="footer">\s*<Row>[\s\S]*<Column v-for="column in visibleColumns" :key="column.key" :footer="footerFor\(column\.key\)" \/>/)
	assert.match(grid, /const hasFooter = computed\(\(\) => Boolean\(props\.footer\)\)/)
})

const keyEvent = (extra = {}, target = { tagName: "INPUT", getAttribute: () => null }) => ({
	key: "Enter", target, preventDefault() { this.prevented = true }, ...extra,
})

test("isFormSubmitEnter accepts plain Enter in inputs only", () => {
	assert.equal(isFormSubmitEnter(keyEvent()), true)
	assert.equal(isFormSubmitEnter(keyEvent({ key: "Tab" })), false)
	assert.equal(isFormSubmitEnter(keyEvent({ shiftKey: true })), false)
	assert.equal(isFormSubmitEnter(keyEvent({ isComposing: true })), false)
	assert.equal(isFormSubmitEnter(keyEvent({ defaultPrevented: true })), false)
	assert.equal(isFormSubmitEnter(keyEvent({}, { tagName: "TEXTAREA", getAttribute: () => null })), false)
	assert.equal(isFormSubmitEnter(keyEvent({}, { tagName: "BUTTON", getAttribute: () => null })), false)
	assert.equal(isFormSubmitEnter(keyEvent({}, { tagName: "INPUT", getAttribute: (name) => name === "aria-expanded" ? "true" : null })), false)
})

function addRateHandler(props, emit) {
	const body = sections.match(/function addRateOnEnter\(event\) \{\n([\s\S]*?)\n\}/)[1]
	return new Function("props", "emit", "isFormSubmitEnter", `return function addRateOnEnter(event) {\n${body}\n}`)(props, emit, isFormSubmitEnter)
}

test("Enter in the Additional Rate row runs Add Rate once and never while busy", () => {
	assert.match(sections, /<div class="lotwise-section__inline-action" @keydown="addRateOnEnter">\s*<FormField\s*:field="fieldByName\('additional_rate'\)"/)
	const commands = []
	const props = { canEdit: true, pageBusy: false }
	const handler = addRateHandler(props, (...args) => commands.push(args))
	const event = keyEvent()
	handler(event)
	assert.deepEqual(commands, [["command", "add_rate"]])
	assert.equal(event.prevented, true)
	handler(keyEvent({ repeat: true }))
	handler(keyEvent({}, { tagName: "INPUT", getAttribute: () => "true" }))
	props.pageBusy = true
	handler(keyEvent())
	props.pageBusy = false
	props.canEdit = false
	handler(keyEvent())
	assert.equal(commands.length, 1)
})

test("the page ignores a second command while the first is still committing the focused field", () => {
	const page = read("../src/departments/pd/LotwiseItemProfitPage.vue")
	assert.match(page, /if \(!canEdit\.value \|\| pageBusy\.value \|\| userCommandPending\) return\n[^\n]*\n\tuserCommandPending = true/)
})

test("Desk: Enter in Additional Rate commits the value and triggers Add Rate once", async () => {
	const source = read("../../essdee_yrp/essdee_yrp/doctype/sd_yrp_lotwise_item_profit/sd_yrp_lotwise_item_profit.js")
	assert.match(source, /refresh: function\(frm\) \{\n\t\tbind_add_rate_on_enter\(frm\);/)
	const body = source.match(/function bind_add_rate_on_enter\(frm\) \{\n([\s\S]*?)\n\}\n/)[1]
	const bind = new Function("frm", body)
	let listener = null
	const input = { off() { return input }, on(_name, handler) { listener = handler; return input } }
	const calls = []
	let release
	const frm = {
		fields_dict: {
			additional_rate: {
				$input: input,
				get_input_value: () => "15",
				parse_validate_and_set_in_model: (value) => { calls.push(["set", value]); return new Promise((resolve) => { release = resolve }) },
			},
			add_rate: { df: {} },
		},
		script_manager: { trigger: (name) => { calls.push(["trigger", name]) } },
	}
	bind(frm)
	const enter = keyEvent({ originalEvent: {} })
	listener(enter)
	listener(keyEvent({ originalEvent: {} }))
	listener(keyEvent({ key: "a", originalEvent: {} }))
	assert.equal(enter.prevented, true)
	release()
	await new Promise((resolve) => setTimeout(resolve, 0))
	assert.deepEqual(calls, [["set", "15"], ["trigger", "add_rate"]])
	assert.equal(frm.adding_rate, false)
})
