import assert from "node:assert/strict"
import { resolve } from "node:path"
import test from "node:test"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import * as inlineFilters from "../src/composables/useInlineFilters.js"
import * as workInProgress from "../src/departments/merch/reports/workInProgress.js"

const nodes = (root, type) => findNodes(root, node => node.type === type)
const stub = () => ({ setup: (_, { slots }) => () => Vue.h("div", slots.default?.()) })

test("Merch Work In Progress renders a report-table with typed cells and a shaded total row", async () => {
	const columns = [
		{ fieldname: "style", label: "Style", fieldtype: "Data", group: "" },
		{ fieldname: "order_qty", label: "Order Qty", fieldtype: "Float", group: "Cut" },
	]
	const report = {
		sourceColumns: Vue.ref(columns),
		sourceRows: Vue.shallowRef([{ lot: "L-1", style: "Tee", order_qty: 10 }, { is_total_row: true, style: "Total", order_qty: 10 }]),
		reportSummary: Vue.ref([]), payload: Vue.ref({}), generated: Vue.ref(true), isBusy: Vue.ref(false), error: Vue.ref(""),
		filtersChanged() {}, generate() {}, clear() {},
	}
	const component = loadComponent(resolve("frontend/src/departments/merch/reports/WorkInProgressReport.vue"), {
		"primevue/select": stub(),
		"../../../components/common/DateField.vue": stub(),
		"../../../components/common/LinkField.vue": stub(),
		"../../../components/reports/ReportShell.vue": stub(),
		"../../../components/reports/PasteListDialog.vue": stub(),
		"../../../components/reports/ReportFilterRow.vue": () => null,
		"../../../components/reports/pasteValues.js": { mergeNames: (left) => left },
		"../../../composables/useWebReport.js": { useWebReport: () => report },
		"../../../composables/useInlineFilters.js": inlineFilters,
		"./WipLinkMultiSelect.vue": stub(),
		"./workInProgress.js": workInProgress,
	})
	const root = mountComponent(component)
	try {
		await Vue.nextTick()
		assert.match(nodes(root, "table")[0].props.class, /\breport-table\b/)
		const [, header] = nodes(root, "tr")
		const [styleHeader, qtyHeader] = nodes(header, "th")
		assert.match(styleHeader.props.class, /report-cell--text/)
		assert.match(qtyHeader.props.class, /report-cell--num.*wip-number/)
		const bodyRows = nodes(root, "tr").filter(row => nodes(row, "td").length)
		const [styleCell, qtyCell] = nodes(bodyRows[0], "td")
		assert.match(styleCell.props.class, /report-cell--text/)
		assert.match(qtyCell.props.class, /report-cell--num/)
		assert.match(bodyRows[1].props.class, /\breport-total-row\b/)
	} finally { root.__vue_app__.unmount() }
})
