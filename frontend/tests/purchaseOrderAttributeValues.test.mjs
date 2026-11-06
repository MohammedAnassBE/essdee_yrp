import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import * as attributeHelpers from "../src/departments/fabric-store/purchaseOrderAttributeValues.js"
import {
	createAttributeDraft,
	getAttributeChanges,
	getEditableAttributeRows,
	getMissingAttributeMessage,
	searchAttributeOptions,
} from "../src/departments/fabric-store/purchaseOrderAttributeValues.js"

const rows = [
	{
		name: "ROW-1", idx: 1, item_code: "Yarn-Red-S", qty: 12,
		attributes: [
			{ attribute: "Colour", value: "Red", options: ["Red", "Blue", "Dark Red"], editable: true },
			{ attribute: "Size", value: "S", options: ["S", "M"], editable: true },
			{ attribute: "Stage", value: "Yarn", options: ["Yarn"], editable: false },
		],
	},
	{ name: "ROW-2", idx: 2, item_code: "Plain", qty: 3, attributes: [] },
	{ name: "ROW-3", idx: 3, item_code: "Staged", qty: 1, attributes: [{ attribute: "Stage", value: "Yarn", options: [], editable: false }] },
]

test("only rows with an editable attribute are offered", () => {
	assert.deepEqual(getEditableAttributeRows(rows).map((row) => row.name), ["ROW-1"])
})

test("the draft starts from the saved values and an unchanged draft sends nothing", () => {
	const editable = getEditableAttributeRows(rows)
	const draft = createAttributeDraft(editable)
	assert.deepEqual(draft, { "ROW-1": { Colour: "Red", Size: "S", Stage: "Yarn" } })
	assert.deepEqual(getAttributeChanges(editable, draft), [])
})

test("changes carry only edited attributes plus the saved item code and quantity", () => {
	const editable = getEditableAttributeRows(rows)
	const draft = createAttributeDraft(editable)
	draft["ROW-1"].Colour = "Blue"
	draft["ROW-1"].Stage = "Knitted"
	assert.deepEqual(getAttributeChanges(editable, draft), [
		{ name: "ROW-1", item_code: "Yarn-Red-S", qty: 12, attributes: { Colour: "Blue" } },
	])
})

test("a cleared attribute is reported before saving", () => {
	const editable = getEditableAttributeRows(rows)
	const draft = createAttributeDraft(editable)
	assert.equal(getMissingAttributeMessage(editable, draft), "")
	draft["ROW-1"].Size = ""
	assert.equal(getMissingAttributeMessage(editable, draft), "Row #1: Size is required.")
})

test("attribute search ranks exact and prefix matches first so Enter picks the best value", () => {
	assert.deepEqual(searchAttributeOptions(["Dark Red", "Redwood", "Red"], "red").map((row) => row.name), ["Red", "Redwood", "Dark Red"])
	assert.deepEqual(searchAttributeOptions(["Red", "Blue"], "").map((row) => row.name), ["Red", "Blue"])
	assert.deepEqual(searchAttributeOptions(["Red", "Blue"], "zz"), [])
})

test("the Purchase Order page wires the capability to the attribute dialog", () => {
	const page = readFileSync(new URL("../src/departments/FabricPurchaseOrder.vue", import.meta.url), "utf8")
	assert.match(page, /add\("update_attribute_values", "Update Attribute Values"/)
	assert.match(page, /<PurchaseOrderAttributeDialog v-model:visible="attributeEditorVisible"/)
	const dialog = readFileSync(new URL("../src/departments/fabric-store/PurchaseOrderAttributeDialog.vue", import.meta.url), "utf8")
	assert.match(dialog, /:search-handler="\(text\) => searchAttributeOptions\(entry\.options, text\)"/)
	assert.doesNotMatch(dialog, /InputNumber/, "quantity is shown, never edited")
})

test("the dialog loads rows, edits one attribute and saves only that change", async () => {
	const saved = []
	const Container = (props, { slots }) => Vue.h("container", props, [slots.default?.(), slots.footer?.()])
	const Dialog = loadComponent(new URL("../src/departments/fabric-store/PurchaseOrderAttributeDialog.vue", import.meta.url).pathname, {
		"primevue/button": (props) => Vue.h("button", props, props.label),
		"primevue/dialog": Container,
		"primevue/inputtext": (props) => Vue.h("input-text", props),
		"primevue/message": Container,
		"primevue/skeleton": () => Vue.h("skeleton"),
		"../../api/fabricStore.js": {
			getPurchaseOrderAttributeRows: async () => ({ rows }),
			updatePurchaseOrderAttributeValues: async (name, changes) => { saved.push([name, changes]); return { changes } },
		},
		"../../components/common/LinkField.vue": (props) => Vue.h("link-field", props),
		"../../components/documents/DocumentErrorDialog.vue": (props) => Vue.h("error-dialog", props),
		"./purchaseOrderAttributeValues.js": attributeHelpers,
	})
	const root = mountComponent(Dialog, { visible: true, purchaseOrder: "PO-1" })
	await new Promise((resolve) => setImmediate(resolve))
	await Vue.nextTick()
	const links = findNodes(root, (node) => node.type === "link-field")
	assert.deepEqual(links.map((node) => [node.props.label, node.props.modelValue, Boolean(node.props.disabled)]), [
		["Colour *", "Red", false], ["Size *", "S", false], ["Stage *", "Yarn", true],
	])
	links[0].props["onUpdate:modelValue"]("Blue")
	await Vue.nextTick()
	const save = findNodes(root, (node) => node.type === "button" && node.props.label === "Save Changes")[0]
	await save.props.onClick()
	assert.deepEqual(saved, [["PO-1", [{ name: "ROW-1", item_code: "Yarn-Red-S", qty: 12, attributes: { Colour: "Blue" } }]]])
})
