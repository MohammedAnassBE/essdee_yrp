import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import test from "node:test"

import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import * as manualBundles from "../src/departments/cutting/laysheet/manualBundles.js"

const read = (path) => readFileSync(resolve(`frontend/src/departments/cutting/${path}`), "utf8")
const tick = async () => { await new Promise((done) => setImmediate(done)); await Vue.nextTick() }
const Button = (props) => Vue.h("button", props, props.label)
const Field = () => Vue.h("input", { type: "text" })
const controls = { "primevue/button": Button, "primevue/inputtext": Field, "primevue/inputnumber": Field, "primevue/message": () => null, "primevue/select": Field }
const checkboxes = (root) => findNodes(root, (node) => node.type === "input" && node.props.type === "checkbox")
const rowBoxes = (root) => checkboxes(root).filter((node) => "data-row-select" in node.props && !String(node.props["aria-label"]).startsWith("Select all"))
const headerBox = (root) => checkboxes(root).find((node) => String(node.props["aria-label"]).startsWith("Select all"))
const deleteButton = (root) => findNodes(root, (node) => node.type === "button" && node.props.label === "Delete")[0]
const text = (node) => [node.text, ...node.children.map(text)].join("")
const check = (box, checked = true) => box.props.onChange({ target: { checked } })

function plannerMatrix(editable = true) {
	const component = loadComponent(resolve("frontend/src/departments/cutting/planner/PlannerOrderMatrix.vue"), controls)
	const state = Vue.reactive({ rows: ["S", "M", "L"].map((size, index) => ({ _row_key: size, size, qty: index })), editable })
	const root = mountComponent({ render: () => Vue.h(component, { rows: state.rows, editable: state.editable, "onUpdate:rows": (rows) => { state.rows = rows } }) })
	return { root, state }
}

test("planner order sizes are deleted with row checkboxes instead of per-row buttons", async () => {
	const { root, state } = plannerMatrix()
	const boxes = rowBoxes(root)
	assert.equal(boxes.length, 3)
	assert.ok(boxes.every((box) => box.props.tabindex === "-1" || box.props.tabindex === -1))
	assert.equal(deleteButton(root), undefined)
	check(boxes[1])
	await tick()
	assert.match(text(findNodes(root, (node) => node.type === "footer")[0]), /1 selected/)
	await deleteButton(root).props.onClick()
	await tick()
	assert.deepEqual(state.rows.map((row) => row.size), ["S", "L"])
	check(headerBox(root))
	await tick()
	await deleteButton(root).props.onClick()
	await tick()
	assert.deepEqual(state.rows, [])
})

test("read-only planner order sizes show no checkboxes", () => {
	assert.equal(checkboxes(plannerMatrix(false).root).length, 0)
})

test("manual bundle rows are deleted together, last row first", async () => {
	const component = loadComponent(resolve("frontend/src/departments/cutting/laysheet/LaySheetManualBundles.vue"), { ...controls, "./manualBundles.js": manualBundles })
	const sheet = { name: "LS-1", sizes: ["S"], manual_items: ["Navy", "Red", "Blue"].map((colour) => ({ colour, quantity: 1, multipliers: { S: 1 } })) }
	const root = mountComponent(component, { sheet, editable: true, loadSetFields: async () => [] })
	const boxes = rowBoxes(root)
	assert.equal(boxes.length, 3)
	check(boxes[0]); check(boxes[2])
	await tick()
	await deleteButton(root).props.onClick()
	await tick()
	assert.equal(rowBoxes(root).length, 1)
	assert.equal(findNodes(root, (node) => node.type === "button" && node.props.icon === "pi pi-trash" && node.props.label !== "Delete").length, 0)
	assert.equal(checkboxes(mountComponent(component, { sheet, editable: false, loadSetFields: async () => [] })).length, 0)
})

test("cutting tables replace per-row trash buttons with checkbox selection and a Delete footer", () => {
	const files = ["bulk/BulkSetupEditor.vue", "CuttingPlanActions.vue", "CuttingMarkerDialog.vue", "laysheet/LaySheetManualBundles.vue", "planner/PlannerOrderMatrix.vue", "order/CuttingOrderDetailDialog.vue"]
	for (const file of files) {
		const source = read(file)
		assert.doesNotMatch(source, /icon[=:]\s*"pi pi-trash"[^>]*(rounded|aria-label="Remove)/, file)
		assert.match(source, /useRowSelection/, file)
		assert.match(source, /data-row-select/, file)
		assert.match(source, /label[=:]\s*"Delete"/, file)
	}
})

test("bulk split lots add on Enter and lock rows that already have a LaySheet", () => {
	const source = read("bulk/BulkSetupEditor.vue")
	assert.match(source, /<table v-entry-table="\{ add: canEditRows && !busy \? addRow : null \}"/)
	assert.match(source, /:disabled="busy \|\| Boolean\(row\.cutting_laysheet\)"[^>]*@change="selection\.toggle/)
	assert.match(source, /row\.cutting_laysheet \? \[\] : \[index\]/)
})

test("recut form adds its item when Enter is pressed on the last field", () => {
	const source = read("CuttingPlanActions.vue")
	assert.match(source, /<div class="recut-form" @keydown\.enter="addRecutRowOnEnter">/)
	assert.match(source, /event\.currentTarget\.querySelector\("label:last-of-type"\)\) return\n\tevent\.preventDefault\(\)\n\taddRecutRow\(\)/)
})

test("selection footers never sit between an empty-state v-else and its table", () => {
	for (const file of ["bulk/BulkSetupEditor.vue", "laysheet/LaySheetManualBundles.vue", "planner/PlannerOrderMatrix.vue"]) {
		assert.doesNotMatch(read(file), /<footer v-if="selection[^\n]*\n\s*<div v-else/, file)
	}
})

test("planner order empty state stays hidden while rows exist", () => {
	const { root } = plannerMatrix()
	assert.equal(findNodes(root, (node) => node.props?.class === "planner-order-empty").length, 0)
})

test("marker panel groups add on Enter and hide checkboxes when not editable", () => {
	const source = read("CuttingMarkerDialog.vue")
	assert.match(source, /<table v-entry-table="\{ add: canEdit \? addGroup : null \}" class="marker-table group-table" @keydown\.enter\.capture="addGroupOnEnter"><thead><tr><th v-if="canEdit" class="select-column">/)
	assert.match(source, /<td v-if="canEdit" class="select-column"><input type="checkbox" class="row-checkbox" data-row-select tabindex="-1"/)
})

test("marker panel groups add a group on Enter from the last filled MultiSelect, which v-entry-table cannot see", () => {
	const source = read("CuttingMarkerDialog.vue")
	assert.match(source, /class="marker-table group-table" @keydown\.enter\.capture="addGroupOnEnter">/)
	const handler = source.match(/async function addGroupOnEnter\(event\) \{[\s\S]*?\n\}/)[0]
	assert.match(handler, /Panels for group \$\{count\}/)
	assert.match(handler, /aria-expanded"\) === "true"/)
	assert.match(handler, /selected\?\.length\) return/)
	assert.match(handler, /event\.stopPropagation\(\)[\s\S]*addGroup\(\)[\s\S]*Panels for group \$\{count \+ 1\}[\s\S]*focus\(\)/)
})

test("every select checkbox, header included, is skipped by Enter navigation", () => {
	for (const file of ["bulk/BulkSetupEditor.vue", "CuttingPlanActions.vue", "CuttingMarkerDialog.vue", "laysheet/LaySheetManualBundles.vue", "planner/PlannerOrderMatrix.vue", "order/CuttingOrderDetailDialog.vue", "shared/MaterialRequirementGroups.vue"]) {
		const source = read(file)
		assert.doesNotMatch(source, /type="checkbox"(?![^>]*data-row-select)[^>]*>/, file)
	}
})

test("material requirement rows emit one batch delete, last row first", async () => {
	const component = loadComponent(resolve("frontend/src/departments/cutting/shared/MaterialRequirementGroups.vue"), { ...controls, "../../../components/common/DocumentLink.vue": () => null })
	const deleted = []
	const rows = [{ name: "a", item: "Cloth" }, { name: "b", item: "Cloth" }, { name: "c", item: "Other" }]
	const root = mountComponent(component, { rows, columns: [{ field: "item", label: "Item" }], editable: true, onDelete: (indexes) => deleted.push(indexes) })
	const boxes = rowBoxes(root)
	assert.equal(boxes.length, 3)
	check(boxes[0]); check(boxes[2])
	await tick()
	deleteButton(root).props.onClick()
	await tick()
	assert.deepEqual(deleted, [[2, 0]])
	assert.equal(findNodes(root, (node) => node.type === "button" && node.props.icon === "pi pi-trash" && node.props.label !== "Delete").length, 0)
	assert.equal(checkboxes(mountComponent(component, { rows, columns: [{ field: "item", label: "Item" }], editable: false })).length, 0)
})
