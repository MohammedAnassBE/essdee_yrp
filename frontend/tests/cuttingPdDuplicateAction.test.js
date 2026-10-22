import assert from "node:assert/strict"
import test from "node:test"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { Vue } from "../../scripts/helpers/vue_renderer.mjs"
import { useDuplicateAction } from "../src/composables/useDuplicateAction.js"
import { PLANNING_ROUTES } from "../src/departments/planning/planningViews.js"
import * as pdViews from "../src/departments/pd/pdViews.js"

const read = path => readFileSync(resolve(`frontend/src/${path}`), "utf8")
const script = path => read(path).split("<script setup>")[1].split("</script>")[0].replace(/^import[\s\S]*? from ["'][^"']+["'];?\n/gm, "")
function setup(path, bindings, names) {
	const values = {
		...Vue, ...Object.fromEntries(Object.entries(pdViews).filter(([key]) => key !== "default")), watch: () => {}, onMounted: () => {}, onBeforeUnmount: () => {}, onBeforeRouteLeave: () => {},
		defineProps: () => ({}), defineEmits: () => () => {}, useActionConfirmation: () => () => {}, useDuplicateAction, PLANNING_ROUTES, ...bindings,
	}
	return new Function(...Object.keys(values), `${script(path)}\nreturn { ${names} }`)(...Object.values(values))
}
function lotwiseMetadata() {
	const tables = Object.entries(pdViews.LOTWISE_TABLE_COLUMNS)
	const inputs = [...new Set(Object.values(pdViews.LOTWISE_SECTIONS).flat())]
	return [
		{ name: "SD YRP Lotwise Item Profit", fields: inputs.map(fieldname => ({ fieldname, options: `Child ${fieldname}` })) },
		...tables.map(([table, columns]) => ({ name: `Child ${table}`, fields: columns.map(fieldname => ({ fieldname })) })),
	]
}
const recordingRouter = () => { const pushes = []; return { pushes, push: location => pushes.push(location), replace() {} } }

test("Cutting Order offers Duplicate in its More menus only with create permission", () => {
	const router = recordingRouter()
	const state = setup("departments/CuttingOrder.vue", { useRoute: () => ({ params: { cuttingOrderId: "CO-1" } }), useRouter: () => router }, "workspace, editorProbe, duplicateActions")
	state.editorProbe.value = { record: { name: "CO-1", docstatus: 0 }, permissions: { can_create: false } }
	assert.deepEqual(state.duplicateActions.value, [])
	state.editorProbe.value = { record: { name: "CO-1", docstatus: 0 }, permissions: { can_create: true } }
	const [action] = state.duplicateActions.value
	assert.equal(action.label, "Duplicate")
	assert.equal(action.menuOnly, true)
	action.command()
	assert.deepEqual(router.pushes, [{ name: "cutting-order-new", query: { duplicate_from: "CO-1" } }])
	const source = read("departments/CuttingOrder.vue")
	assert.match(source, /<DocumentActionStrip :actions="duplicateActions" \/>/)
	assert.match(source, /<CuttingOrderActions [^>]*:extra-actions="duplicateActions"/)
	assert.match(read("departments/cutting/order/CuttingOrderActions.vue"), /\.\.\.props\.extraActions/)
})

test("Cutting Plan Duplicate opens the new editor of the current section", () => {
	const router = recordingRouter()
	const route = Vue.reactive({ name: "cutting-plan", params: { cuttingPlanId: "CP-1" } })
	const state = setup("departments/CuttingPlan.vue", { useRoute: () => route, useRouter: () => router }, "editorProbe, duplicateActions")
	assert.deepEqual(state.duplicateActions.value, [])
	state.editorProbe.value = { record: { name: "CP-1", docstatus: 1 }, permissions: { can_create: true } }
	state.duplicateActions.value[0].command()
	route.name = PLANNING_ROUTES.cuttingPlan
	state.duplicateActions.value[0].command()
	assert.deepEqual(router.pushes, [
		{ name: "cutting-plan-new", query: { duplicate_from: "CP-1" } },
		{ name: PLANNING_ROUTES.cuttingPlanNew, query: { duplicate_from: "CP-1" } },
	])
	const source = read("departments/CuttingPlan.vue")
	assert.match(source, /<DocumentActionStrip :actions="duplicateActions" \/>/)
	assert.match(source, /:extra-actions="duplicateActions"/)
	assert.match(read("departments/cutting/CuttingPlanActions.vue"), /props\.extraActions,/)
})

test("new Cutting Order and Cutting Plan editors load prefill from duplicate_from", async () => {
	const calls = []
	const order = setup("departments/cutting/order/CuttingOrderEditor.vue", {
		defineProps: () => ({ name: "", initialPayload: null, duplicateFrom: "CO-1" }),
		getCuttingOrderEditor: async (...args) => { calls.push(["order", ...args]); return { record: { cutting_order_detail: "COD-1", maximum_no_of_plys: 80 }, matrix: { groups: [] } } },
		getCuttingOrderDetail: async () => ({ permissions: {} }),
	}, "load, form")
	await order.load()
	assert.equal(order.form.cutting_order_detail, "COD-1")
	const plan = setup("departments/cutting/plan/CuttingPlanEditor.vue", {
		defineProps: () => ({ name: "", initialPayload: null, initialSource: {}, duplicateFrom: "CP-1" }),
		getCuttingPlanEditor: async (...args) => { calls.push(["plan", ...args]); return { record: { lot: "LOT-1" }, matrix: { groups: [] } } },
	}, "load, form")
	await plan.load()
	assert.equal(plan.form.lot, "LOT-1")
	assert.deepEqual(calls, [["order", "", "", "CO-1"], ["plan", "", "", "CP-1"]])
	assert.match(read("departments/CuttingOrderEditorPage.vue"), /:duplicate-from="duplicateFrom"/)
	assert.match(read("departments/CuttingPlanEditorPage.vue"), /:duplicate-from="duplicateFrom"/)
})
