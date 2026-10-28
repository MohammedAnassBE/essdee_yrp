import assert from "node:assert/strict"
import test from "node:test"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { Vue } from "../../scripts/helpers/vue_renderer.mjs"

const PAGE = "departments/CuttingLaySheetPlanner.vue"
const read = path => readFileSync(resolve(`frontend/src/${path}`), "utf8")
const script = path => read(path).split("<script setup>")[1].split("</script>")[0].replace(/^import[\s\S]*? from ["'][^"']+["'];?\n/gm, "")
const NAMES = "load, optimize, activeTab, optimizationActive, optimizationRunState, payload"

function setup(bindings) {
	const values = {
		...Vue, watch: () => {}, onBeforeUnmount: () => {}, setTimeout: () => 0, clearTimeout: () => {}, useRoute: () => ({ params: { plannerId: "CLP-1" } }),
		getLaySheetOptimizationStatus: async () => ({ status: "Running" }), getLaySheetPlannerEditor: async () => ({}),
		saveLaySheetPlanner: async () => ({}), selectLaySheetStrategy: async () => ({}), startLaySheetOptimization: async () => ({}),
		...bindings,
	}
	return new Function(...Object.keys(values), `${script(PAGE)}\nreturn { ${NAMES} }`)(...Object.values(values))
}
const editor = (status, successful = []) => ({ record: { name: "CLP-1", optimization_status: status }, results: { successful, failed: [] }, actions: { can_optimize: status !== "Queued" && status !== "Running" } })

test("Plan tab shows the running state from the Optimize click until the queued run starts", async () => {
	let release
	const page = setup({
		getLaySheetPlannerEditor: async () => editor("Not Started"),
		startLaySheetOptimization: () => new Promise((resolveStart) => { release = resolveStart }),
	})
	await page.load()
	assert.equal(page.activeTab.value, "inputs")
	assert.equal(page.optimizationActive.value, false)
	const running = page.optimize()
	assert.equal(page.activeTab.value, "plan")
	assert.equal(page.optimizationActive.value, true)
	assert.equal(page.optimizationRunState.value, "queued")
	release({ status: "Queued", actions: { can_optimize: false, should_poll: false } })
	await running
	assert.equal(page.optimizationActive.value, true)
	assert.equal(page.payload.value.actions.can_optimize, false)
})

test("reloading during a background run reopens the Plan tab running state", async () => {
	const page = setup({ getLaySheetPlannerEditor: async () => editor("Running") })
	await page.load()
	assert.equal(page.activeTab.value, "plan")
	assert.equal(page.optimizationActive.value, true)
	assert.equal(page.optimizationRunState.value, "running")
})

test("finished or failed runs clear the running state", async () => {
	for (const status of ["Completed", "Failed"]) {
		const page = setup({ getLaySheetPlannerEditor: async () => editor(status) })
		await page.load()
		assert.equal(page.optimizationActive.value, false)
	}
})
