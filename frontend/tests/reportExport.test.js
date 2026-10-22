import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"

const helpers = await import(new URL("../src/components/reports/reportExport.js", import.meta.url))
const source = path => readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8")
const cell = (text, extra = {}) => ({ textContent: text, colSpan: 1, rowSpan: 1, ...extra })

test("Desk export args send active filters, picked columns, and Desk dialog options", () => {
	const settings = { ...helpers.defaultExportSettings(), fileFormat: "CSV", csvDelimiter: ";", csvQuoting: 1, includeFilters: true }
	const args = helpers.deskExportArgs({
		reportKey: "purchase-order-itemwise",
		filters: { supplier: "SUP-1" },
		appliedFilters: { Supplier: "SUP-1" },
		columns: [
			{ kind: "base", fieldname: "item", label: "Item", visible: true },
			{ kind: "linked", source_column: "supplier", target_field: "supplier_name", label: "Supplier Name", fieldtype: "Data", width: 150 },
		],
	}, settings)
	assert.deepEqual(args, {
		report_key: "purchase-order-itemwise",
		filters: { supplier: "SUP-1" },
		columns: [
			{ kind: "base", fieldname: "item", label: "Item" },
			{ kind: "linked", source_column: "supplier", target_field: "supplier_name", label: "Supplier Name", fieldtype: "Data", width: 150 },
		],
		file_format_type: "CSV", include_filters: 1, applied_filters: { Supplier: "SUP-1" },
		csv_delimiter: ";", csv_quoting: 1, csv_decimal_sep: ".",
	})
})

test("Rendered export args gate on the report key, or the doctype when there is no key", () => {
	const settings = helpers.defaultExportSettings()
	const keyed = helpers.rowsExportArgs({ title: "WIP", reportKey: "merch-work-in-progress", doctype: "Ignored" }, [["Lot"]], settings)
	assert.equal(keyed.report_key, "merch-work-in-progress")
	assert.equal(keyed.doctype, undefined)
	assert.equal(keyed.file_format_type, "Excel")
	assert.equal(keyed.include_filters, 0)
	const unkeyed = helpers.rowsExportArgs({ title: "DPR", doctype: "SD YRP Sewing Plan" }, [["Lot"]], { ...settings, includeFilters: true })
	assert.equal(unkeyed.doctype, "SD YRP Sewing Plan")
	assert.equal(unkeyed.include_filters, 0, "Include filters needs applied filters")
})

test("Applied filter labels follow Desk: skip empty and hidden filters, label checks", () => {
	const fields = [
		{ fieldname: "lot", label: "Lot" }, { fieldname: "item", label: "Item" },
		{ fieldname: "from_date", label: "From Date", depends_on: "date_based_on" },
		{ fieldname: "warehouse_wise", label: "Warehouse Wise", fieldtype: "Check" },
	]
	assert.deepEqual(helpers.appliedFilterLabels(fields, { lot: "L1", item: "", from_date: "2026-01-01", warehouse_wise: 1 }), { Lot: "L1", "Warehouse Wise": "Yes" })
	assert.deepEqual(helpers.appliedFilterLabels(undefined, { product_category: "Tops" }), { "Product Category": "Tops" })
})

test("Table grid expands colspan and rowspan and keeps numbers numeric", () => {
	const table = { rows: [
		{ cells: [cell("Lot", { rowSpan: 2 }), cell("Qty", { colSpan: 2 })] },
		{ cells: [cell("S"), cell("M")] },
		{ cells: [cell("L-001"), cell("1,200.50"), cell("007")] },
	] }
	assert.deepEqual(helpers.tableGrid(table), [["Lot", "Qty", ""], ["", "S", "M"], ["L-001", 1200.5, "007"]])
	assert.equal(helpers.cellExportValue("  a \n  b "), "a\nb")
	assert.equal(helpers.cellExportValue("-12"), -12)
})

test("CSV preview applies quoting, delimiter, and decimal separator", () => {
	const rows = [["Item", "Qty"], ["A;B", 1.5]]
	assert.equal(helpers.csvPreview(rows, { csvDelimiter: ",", csvQuoting: 2 }), '"Item","Qty"\n"A;B",1.5')
	assert.equal(helpers.csvPreview(rows, { csvDelimiter: ";", csvQuoting: 0, csvDecimalSep: "," }), 'Item;Qty\n"A;B";1,5')
})

test("Every /web report shell declares an export source", () => {
	const files = [
		"components/reports/DeskBackedReport.vue", "components/reports/StockBalanceReport.vue", "components/reports/PurchaseOrderItemwiseReport.vue",
		"departments/finishing/reports/FinishingPlanReport.vue", "departments/merch/reports/WorkInProgressReport.vue",
		"departments/planning/reports/InhouseQuantityReport.vue", "departments/sewing/reports/SewingDpr.vue",
		"departments/cutting/reports/DailyCutSheetReport.vue", "components/reports/AttendanceStrengthReport.vue",
	]
	for (const file of files) assert.match(source(file), /<ReportShell\b[\s\S]{0,800}?:export-source=/, file)
	for (const file of ["departments/planning/reports/InhouseQuantityReport.vue", "departments/merch/reports/WorkInProgressReport.vue", "departments/finishing/reports/FinishingPlanReport.vue"]) {
		assert.doesNotMatch(source(file), /Download CSV/, `${file} keeps a one-off CSV button`)
	}
})

function loadButton(calls, allowed = true) {
	const passthrough = name => (props, { slots }) => Vue.h(name, props, [slots.default?.(), slots.footer?.()])
	return loadComponent(new URL("../src/components/reports/ReportExportButton.vue", import.meta.url).pathname, {
		"primevue/button": props => Vue.h("export-button", props),
		"primevue/checkbox": () => null, "primevue/inputtext": () => null, "primevue/message": () => null,
		"primevue/select": () => null, "primevue/textarea": () => null,
		"primevue/dialog": passthrough("export-dialog"),
		"../../api/reportExport.js": {
			getExportPermission: async source => { calls.push(["permission", source]); return allowed },
			exportWebReport: async (args, name) => calls.push(["desk", args, name]),
			exportReportRows: async (args, name) => calls.push(["rows", args, name]),
		},
		"./reportExport.js": helpers,
	})
}

const flush = () => new Promise(resolve => setTimeout(resolve, 0))

test("Export button is hidden without export permission", async () => {
	const calls = []
	const root = mountComponent(loadButton(calls, false), { title: "SCR", source: { doctype: "SD YRP Sewing Plan" }, getRows: () => [] })
	await flush()
	assert.deepEqual(calls, [["permission", { doctype: "SD YRP Sewing Plan" }]])
	assert.equal(findNodes(root, node => node.type === "export-button" && node.props.label === "Export").length, 0)
})

test("Desk-backed reports download through export_web_report with picked columns", async () => {
	const calls = []
	const source = helpers.deskExportSource("purchase-order-itemwise", { supplier: "SUP-1" }, [{ kind: "base", fieldname: "item", label: "Item" }])
	const root = mountComponent(loadButton(calls), { title: "Purchase Order Itemwise", source, getRows: () => [["Item"], ["A"]] })
	await flush()
	const exportButton = findNodes(root, node => node.type === "export-button" && node.props.label === "Export")[0]
	assert.ok(exportButton)
	exportButton.props.onClick()
	findNodes(root, node => node.type === "export-button" && node.props.label === "Download")[0].props.onClick()
	await flush()
	const [kind, args, name] = calls.at(-1)
	assert.equal(kind, "desk")
	assert.equal(name, "Purchase Order Itemwise.xlsx")
	assert.deepEqual(args.filters, { supplier: "SUP-1" })
	assert.deepEqual(args.columns, [{ kind: "base", fieldname: "item", label: "Item" }])
})

test("Custom reports download their rendered rows", async () => {
	const calls = []
	const root = mountComponent(loadButton(calls), { title: "Size-wise", source: { reportKey: "planning-size-wise-stock" }, getRows: () => [["Lot", "S"], ["L1", 4]] })
	await flush()
	findNodes(root, node => node.type === "export-button" && node.props.label === "Export")[0].props.onClick()
	findNodes(root, node => node.type === "export-button" && node.props.label === "Download")[0].props.onClick()
	await flush()
	const [kind, args] = calls.at(-1)
	assert.equal(kind, "rows")
	assert.deepEqual(args.rows, [["Lot", "S"], ["L1", 4]])
	assert.equal(args.report_key, "planning-size-wise-stock")
})
