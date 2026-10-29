import assert from "node:assert/strict"
import { resolve } from "node:path"
import test from "node:test"
import { fileURLToPath } from "node:url"

import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import * as rowSelection from "../src/components/common/childGrid/rowSelection.js"
import * as lotTransferQuantities from "../src/departments/cutting/lotTransferQuantities.js"

const rootPath = fileURLToPath(new URL("../../", import.meta.url))
const tick = async () => { await new Promise((done) => setImmediate(done)); await Vue.nextTick() }
const Button = (props) => Vue.h("button", props, props.label)
const Stub = (name) => (props) => Vue.h(name, props)
const checkboxes = (root) => findNodes(root, (node) => node.type === "input" && "data-row-select" in node.props)
const rowBoxes = (root) => checkboxes(root).filter((node) => !String(node.props["aria-label"]).startsWith("Select all"))
const headerBox = (root) => checkboxes(root).find((node) => String(node.props["aria-label"]).startsWith("Select all"))
const deleteButton = (root) => findNodes(root, (node) => node.type === "button" && node.props.label === "Delete")[0]
const hasText = (root, value) => findNodes(root, (node) => node.text === value).length > 0
const check = (box, checked = true) => box.props.onChange({ target: { checked } })

function lotTransferEditor() {
	const confirmations = []
	const component = loadComponent(resolve(rootPath, "frontend/src/departments/cutting/LotTransferQuantityEditor.vue"), {
		"primevue/button": Button, "primevue/inputnumber": Stub("input-number"),
		"../../components/documents/DocumentErrorDialog.vue": Stub("error-dialog"), "../../components/documents/DocumentShortcuts.vue": Stub("shortcuts"),
		"../../utils/useActionConfirmation.js": { useActionConfirmation: () => (options) => confirmations.push(options) },
		"../../utils/documentShortcuts.js": { withShortcutHint: (label) => label }, "./cpmApi.js": { updateLotTransferQuantities: async () => ({}) },
		"./lotTransferQuantities.js": lotTransferQuantities, "../../components/common/childGrid/rowSelection.js": rowSelection,
	})
	const record = { name: "LT-1", modified: "2026-10-29", quantity_rows: ["RED", "BLUE", "GREEN"].map((colour) => ({ name: `ROW-${colour}`, label: colour, qty: 10, available: 10 })) }
	const root = mountComponent(component, { cuttingPlan: "CP-1", record })
	return { root, confirmations, names: () => rowBoxes(root).map((box) => box.props["aria-label"].replace("Select ", "")) }
}

test("lot transfer rows are deleted through checkboxes after one confirmation", async () => {
	const { root, confirmations, names } = lotTransferEditor()
	assert.equal(findNodes(root, (node) => node.type === "button" && node.props.icon === "pi pi-trash" && node.props.text).length, 0)
	assert.ok(rowBoxes(root).every((box) => String(box.props.tabindex) === "-1"))
	assert.equal(deleteButton(root), undefined)
	check(rowBoxes(root)[1])
	await tick()
	assert.ok(hasText(root, "1 selected"))
	deleteButton(root).props.onClick()
	assert.deepEqual(names(), ["RED", "BLUE", "GREEN"])
	await confirmations[0].accept()
	await tick()
	assert.deepEqual(names(), ["RED", "GREEN"])
})

test("lot transfer select all keeps the last row", async () => {
	const { root, confirmations, names } = lotTransferEditor()
	check(headerBox(root))
	await tick()
	assert.ok(hasText(root, "3 selected"))
	deleteButton(root).props.onClick()
	assert.equal(confirmations[0].acceptLabel, "Delete Rows")
	await confirmations[0].accept()
	await tick()
	assert.equal(names().length, 1)
	assert.equal(rowBoxes(root)[0].props.disabled, true)
	assert.equal(headerBox(root).props.disabled, true)
})

function inspectionPanel(acting = "") {
	const component = loadComponent(resolve(rootPath, "frontend/src/departments/fabric-store/InspectionEntryPanel.vue"), {
		"primevue/button": Button, "primevue/inputnumber": Stub("input-number"), "primevue/inputtext": Stub("input-text"), "primevue/message": Stub("message"), "primevue/textarea": Stub("textarea"),
		"../../components/common/DateField.vue": Stub("date-field"), "../../components/common/TimeField.vue": Stub("time-field"), "../../components/common/LinkField.vue": Stub("link-field"),
		"../../components/documents/DocumentErrorDialog.vue": Stub("error-dialog"), "../../components/common/childGrid/rowSelection.js": rowSelection,
	})
	const split = (comments) => ({ target_received_type: "Good", qty: 1, received_date: "2026-10-29", comments })
	const props = Vue.reactive({ acting, context: { initial_payload: [
		{ item_variant: "Fabric A", grn_qty: 10, splits: [split("one"), split("two"), split("three")] },
		{ item_variant: "Fabric B", grn_qty: 10, splits: [split("only")] },
	] } })
	const root = mountComponent(component, props)
	const comments = () => findNodes(root, (node) => node.type === "input-text").map((node) => node.props.modelValue)
	return { root, props, comments }
}

test("inspection splits are deleted through checkboxes, keeping one split per source", async () => {
	const { root, comments } = inspectionPanel()
	assert.equal(findNodes(root, (node) => node.props["aria-label"] === "Remove inspection split").length, 0)
	const boxes = rowBoxes(root)
	assert.equal(boxes.length, 4)
	assert.ok(boxes.every((box) => String(box.props.tabindex) === "-1"))
	assert.equal(boxes[3].props.disabled, true)
	check(boxes[1])
	await tick()
	assert.ok(hasText(root, "1 selected"))
	deleteButton(root).props.onClick()
	await tick()
	assert.deepEqual(comments(), ["one", "three", "only"])
	check(headerBox(root))
	await tick()
	deleteButton(root).props.onClick()
	await tick()
	assert.equal(comments().length, 2)
	assert.ok(rowBoxes(root).every((box) => box.props.disabled))
})

test("inspection split checkboxes are disabled while saving", () => {
	const { root } = inspectionPanel("inspection_save")
	assert.ok(rowBoxes(root).every((box) => box.props.disabled))
})
