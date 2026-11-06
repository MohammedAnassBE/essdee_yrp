import assert from "node:assert/strict"
import test from "node:test"
import { fileURLToPath } from "node:url"

import Column from "primevue/column"
import ColumnGroup from "primevue/columngroup"
import PrimeVue from "primevue/config"
import DataTable from "primevue/datatable"
import Row from "primevue/row"

import { createTestRenderer, findNodes, loadComponent, Vue } from "../../scripts/helpers/vue_renderer.mjs"
import * as childTableFields from "../src/components/common/childTableFields.js"
import * as linkTarget from "../src/utils/linkTarget.js"

const Cell = { props: ["modelValue"], render() { return Vue.h("span", String(this.modelValue ?? "")) } }
const FIELD_PATH = fileURLToPath(new URL("../src/components/common/ChildTableField.vue", import.meta.url))
const childMeta = { fields: [{ fieldname: "size", label: "Size", fieldtype: "Data", in_list_view: 1 }, { fieldname: "qty", label: "Qty", fieldtype: "Int", in_list_view: 1 }] }
const field = { fieldname: "qty_rate_chart", label: "Qty Rate Chart", options: "Child" }
const texts = (node) => findNodes(node, (item) => item.text).map((item) => item.text)

function mountTable(withTotals) {
	let columnBuilds = 0
	const columns = DataTable.computed.columns
	const table = { ...DataTable, computed: { ...DataTable.computed, columns() { columnBuilds += 1; return columns.call(this) } } }
	const rows = Vue.ref([{ size: "M", qty: 1 }])
	const totals = Vue.computed(() => withTotals ? { size: "Total", qty: String(rows.value.reduce((sum, row) => sum + row.qty, 0)) } : null)
	const Field = loadComponent(FIELD_PATH, {
		"primevue/button": () => null, "primevue/column": Column, "primevue/columngroup": ColumnGroup, "primevue/datatable": table, "primevue/row": Row,
		"./FormField.vue": Cell, "./DocumentLink.vue": Cell, "../../utils/linkTarget.js": linkTarget, "./childTableFields.js": childTableFields,
	})
	const root = { type: "root", props: {}, children: [], parent: null, listeners: {}, addEventListener() {}, removeEventListener() {} }
	const app = createTestRenderer().createApp({ render: () => Vue.h(Field, { field, childMeta, modelValue: rows.value, totals: totals.value }) })
	app.use(PrimeVue, { unstyled: true })
	app.mount(root)
	return { rows, tfoot: () => findNodes(root, (item) => item.type === "tfoot")[0], builds: () => columnBuilds }
}

test("child tables render a Total footer row only when totals are given, and it follows edits", async () => {
	assert.equal(mountTable(false).tfoot(), undefined)
	const table = mountTable(true)
	assert.deepEqual(texts(table.tfoot()), ["Total", "1"])
	table.rows.value = [{ size: "M", qty: 4 }, { size: "L", qty: 2 }]
	await Vue.nextTick()
	await Vue.nextTick()
	assert.deepEqual(texts(table.tfoot()), ["Total", "6"])
})

test("changing totals does not rebuild the body columns more than an edit without totals does", async () => {
	const plain = mountTable(false)
	const totalled = mountTable(true)
	for (const table of [plain, totalled]) {
		table.rows.value = [{ size: "M", qty: 9 }]
		await Vue.nextTick()
		await Vue.nextTick()
	}
	assert.equal(totalled.builds(), plain.builds())
})
