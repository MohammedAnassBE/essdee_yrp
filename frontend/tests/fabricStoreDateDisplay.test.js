import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import test from "node:test"

import { findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import * as linkTarget from "../src/utils/linkTarget.js"
import * as documentValues from "../src/utils/documentValues.js"
import * as workOrderTotals from "../src/departments/fabric-store/workOrderTotals.js"

const root = resolve(import.meta.dirname, "../src")
const source = (path) => readFileSync(resolve(root, path), "utf8")
const text = (node) => node.type === "comment" ? "" : node.text + node.children.map(text).join("")
const modules = {
	"../../utils/linkTarget.js": linkTarget,
	"../../utils/documentValues.js": documentValues,
	"./workOrderTotals.js": workOrderTotals,
	"../../components/common/DocumentLink.vue": { props: ["label"], setup: (props) => () => props.label },
}
const dateFields = [
	{ fieldname: "planned_start_date", label: "Planned start", fieldtype: "Date", value: "2026-10-23" },
	{ fieldname: "expected_delivery_date", label: "Expected delivery", fieldtype: "Date", value: "" },
	{ fieldname: "approved_on", label: "Approved on", fieldtype: "Datetime", value: "2026-10-23 14:05:09.123456" },
]
const titles = (mounted, tag) => findNodes(mounted, (node) => node.type === tag).map((node) => node.props.title)

test("Work Order overview and details show Date and Datetime fields as DD-MM-YYYY", () => {
	for (const [file, tag] of [["WorkOrderOverview", "dd"], ["WorkOrderDetails", "strong"]]) {
		const component = loadComponent(resolve(root, `departments/fabric-store/${file}.vue`), modules)
		const mounted = mountComponent(component, { details: dateFields })
		const shown = titles(mounted, tag)
		assert.ok(shown.includes("23-10-2026"), `${file}: ${shown}`)
		assert.ok(shown.includes("23-10-2026 14:05:09"), `${file}: ${shown}`)
		assert.ok(shown.includes("—"), `${file}: ${shown}`)
		assert.ok(!text(mounted).includes("2026-10-23"), file)
	}
})

test("fabric store screens use the shared date helper instead of local ISO slicing", () => {
	const files = [
		"departments/FabricPurchaseOrder.vue",
		"departments/FabricWorkOrder.vue",
		"departments/fabric-store/WorkOrderActivityRail.vue",
		"departments/fabric-store/PurchaseOrderDialog.vue",
		"departments/fabric-store/WorkOrderDetails.vue",
		"departments/fabric-store/WorkOrderOverview.vue",
		"departments/fabric-store/DeliveryChallanWorkspace.vue",
		"departments/fabric-store/GoodsReceivedNoteWorkspace.vue",
	]
	for (const file of files) {
		const content = source(file)
		assert.match(content, /from "(\.\.\/)+utils\/dateFormat\.js"/, file)
		assert.doesNotMatch(content, /function formatDate\(/, file)
		assert.doesNotMatch(content, /\$\{match\[3\]\}-\$\{match\[2\]\}-\$\{match\[1\]\}|\$\{day\}-\$\{month\}-\$\{year\}/, file)
		assert.doesNotMatch(content, / · \$\{(match|String\(field\.value\))/, file)
	}
	assert.match(source("departments/FabricPurchaseOrder.vue"), /formatDisplayDate\(record\.transaction_date\)/)
	assert.match(source("departments/FabricWorkOrder.vue"), /formatDisplayDate\(fieldValues\.value\.get\("wo_date"\)\)/)
	assert.match(source("departments/fabric-store/WorkOrderActivityRail.vue"), /formatDisplayDate\(row\.posting_date\)/)
	assert.match(source("departments/fabric-store/PurchaseOrderDialog.vue"), /Updated \{\{ formatDisplayDatetime\(payload\.record\.modified\) \}\}/)
})
