import assert from "node:assert/strict"
import fs from "node:fs"
import path from "node:path"
import test from "node:test"
import vm from "node:vm"

const root = path.resolve(import.meta.dirname, "../../essdee_yrp/essdee_yrp/report")
function load(name) {
	const slug = name.toLowerCase().replaceAll(" ", "_")
	const lookups = []
	const frappe = {
		query_reports: {},
		datetime: {
			get_today: () => "2026-10-20",
			nowdate: () => "2026-10-20",
			month_start: () => "2026-10-01",
			month_end: () => "2026-09-30",
			add_months: (date) => `2026-09-${date.slice(8)}`,
			add_days: () => "2026-09-30",
		},
		db: { get_link_options: (doctype, txt, filters) => { lookups.push(JSON.parse(JSON.stringify({ doctype, txt, filters }))); return [] } },
	}
	vm.runInNewContext(fs.readFileSync(path.join(root, slug, `${slug}.js`), "utf8"), { frappe, __: (s) => s })
	return { config: frappe.query_reports[name], lookups }
}

for (const name of ["SD YRP Finishing Plan DPR", "SD YRP Finishing Plan Ironing Report"]) {
	test(`${name}: daily and Summary filters match /web`, () => {
		const { config, lookups } = load(name)
		const filters = Object.fromEntries(config.filters.map((df) => [df.fieldname, { df, refresh() {} }]))
		let summary = 0
		const report = { get_filter_value: () => summary, get_filter: (key) => filters[key], refresh() {} }
		assert.equal(filters.date.df.default, "2026-10-20")
		assert.equal(filters.date.df.reqd, 1)
		assert.equal(filters.summary.df.default, 0)
		assert.ok(!filters.from_date.df.default)
		assert.ok(!filters.to_date.df.default)
		summary = 1
		filters.summary.df.on_change(report)
		assert.equal(filters.date.df.reqd, 0)
		assert.equal(filters.from_date.df.reqd, 1)
		assert.equal(filters.to_date.df.reqd, 1)
		assert.equal(filters.items.df.fieldtype, "MultiSelectList")
		filters.items.df.get_data("TEE")
		assert.deepEqual(lookups[0], { doctype: "Item", txt: "TEE", filters: { has_variants: 1 } })
		summary = 0
		filters.summary.df.on_change(report)
		assert.equal(filters.date.df.reqd, 1)
		assert.equal(filters.from_date.df.reqd, 0)
		assert.equal(filters.to_date.df.reqd, 0)
	})
}

test("Dispatch uses current month dates, mandatory range and optional multi-selects", () => {
	const { config, lookups } = load("SD YRP Finishing Plan Dispatch Details")
	const filters = Object.fromEntries(config.filters.map((df) => [df.fieldname, df]))
	assert.equal(filters.from_date.default, "2026-10-01")
	assert.equal(filters.to_date.default, "2026-10-20")
	assert.equal(filters.from_date.reqd, 1)
	assert.equal(filters.to_date.reqd, 1)
	assert.equal(filters.lots.fieldtype, "MultiSelectList")
	filters.items.get_data("TEE")
	assert.deepEqual(lookups[0], { doctype: "Item", txt: "TEE", filters: { has_variants: 1 } })
})

test("Rejection uses last calendar month, unrestricted item link and text colour", () => {
	const { config } = load("SD YRP Rejection Details")
	const filters = Object.fromEntries(config.filters.map((df) => [df.fieldname, df]))
	assert.equal(filters.start_date.default, "2026-09-01")
	assert.equal(filters.end_date.default, "2026-09-30")
	assert.equal(filters.start_date.reqd, 1)
	assert.equal(filters.end_date.reqd, 1)
	assert.equal(filters.item.options, "Item")
	assert.equal(filters.item.get_query, undefined)
	assert.equal(filters.colour.fieldtype, "Data")
})

test("Completion requires blank lot and process; grouped rework filters stay optional", () => {
	const completion = load("SD YRP Rework Completion Report").config.filters
	assert.deepEqual(Array.from(completion, (df) => [df.fieldname, df.options, df.reqd]), [["lot", "SD YRP Lot", 1], ["process", "YRP Process", 1]])
	assert.ok(completion.every((df) => !df.default))
	const groups = load("SD YRP Rework Group Details").config.filters
	assert.deepEqual(Array.from(groups, (df) => df.fieldname), ["lot", "item", "colour", "show_reworked"])
	assert.ok(groups.every((df) => !df.reqd))
	assert.equal(groups.find((df) => df.fieldname === "show_reworked").default, 0)
})
