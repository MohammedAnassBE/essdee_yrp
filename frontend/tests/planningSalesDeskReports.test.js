import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import vm from "node:vm"

function load(slug, name) {
	const frappe = { query_reports: {}, db: { get_link_options: (...args) => args } }
	const path = new URL(`../../essdee_yrp/essdee_yrp/report/${slug}/${slug}.js`, import.meta.url)
	vm.runInNewContext(readFileSync(path, "utf8"), { frappe, __: value => value })
	return frappe.query_reports[name].filters
}

test("Inward Quantity requires the same Lot and Process links as web", () => {
	const fields = load("sd_yrp_inward_quantity_report", "SD YRP Inward Quantity Report")
	assert.deepEqual(JSON.parse(JSON.stringify(fields)), [
		{ fieldname: "lot", label: "Lot", fieldtype: "Link", options: "SD YRP Lot", reqd: 1 },
		{ fieldname: "process", label: "Process", fieldtype: "Link", options: "YRP Process", reqd: 1 },
	])
})

test("Size Wise Stock keeps web defaults, item search and ordered processes", () => {
	const fields = load("sd_yrp_size_wise_stock_report", "SD YRP Size Wise Stock Report")
	assert.deepEqual(Array.from(fields, field => field.fieldname), ["lot", "item", "product_category", "lot_status", "process_list"])
	assert.equal(fields.find(field => field.fieldname === "lot_status").default, "Open")
	assert.equal(fields.find(field => field.fieldname === "lot_status").options, "Open\nClosed")
	for (const [name, doctype, filters] of [["lot", "SD YRP Lot"], ["item", "Item", { has_variants: 1 }], ["process_list", "YRP Process"]]) {
		const field = fields.find(field => field.fieldname === name)
		assert.equal(field.fieldtype, "MultiSelectList")
		assert.deepEqual(JSON.parse(JSON.stringify(field.get_data("query"))), filters ? [doctype, "query", filters] : [doctype, "query"])
	}
})

test("PPO retains web statuses, optional dates, item search and display options", () => {
	const fields = load("sd_yrp_ppo_report", "SD YRP PPO Report")
	assert.deepEqual(Array.from(fields, field => field.fieldname), ["status", "product_category", "item", "from_date", "to_date", "show_fabric", "show_dia", "show_gsm", "summarized"])
	assert.equal(fields[0].options, "\nDraft\nPPO Request\nOpen\nPending Request\nItem Changed\nNot Processed\nClose Request\nClosed")
	assert.deepEqual(JSON.parse(JSON.stringify(fields[2].get_data("Shirt"))), ["Item", "Shirt", { has_variants: 1 }])
	for (const field of fields.slice(3, 5)) {
		assert.equal(field.fieldtype, "Date")
		assert.ok(!field.default && !field.reqd)
	}
	for (const field of fields.slice(5)) assert.equal(field.default, 0)
})
