import assert from "node:assert/strict"
import { readdirSync, readFileSync, statSync } from "node:fs"
import { join, resolve } from "node:path"
import test from "node:test"

const departments = resolve("frontend/src/departments")

function cuttingSources() {
	const walk = (directory) => readdirSync(directory).flatMap((name) => {
		const path = join(directory, name)
		return statSync(path).isDirectory() ? walk(path) : /\.(vue|js)$/.test(name) ? [path] : []
	})
	const pages = readdirSync(departments).filter((name) => /^Cutting.*\.vue$/.test(name)).map((name) => join(departments, name))
	return [...pages, ...walk(join(departments, "cutting"))]
}

test("cutting screens use the shared date helper instead of local date formatters", () => {
	const offenders = cuttingSources().filter((path) => {
		const source = readFileSync(path, "utf8")
		return /function format(Date|DateTime|Timestamp|CompletionTimestamp)\(/.test(source) || /Intl\.DateTimeFormat|toLocaleDateString|toLocaleTimeString/.test(source)
	})
	assert.deepEqual(offenders, [])
})

test("cutting date displays route raw values through the shared helper", () => {
	const read = (path) => readFileSync(join(departments, path), "utf8")
	assert.match(read("cutting/CuttingPlanTabs.vue"), /formatDisplayDatetime\(row\.changed_on\)/)
	assert.match(read("cutting/CuttingPlanSidebar.vue"), /formatDisplayDate\(sheet\.bundle_generated_date, "Not generated"\)/)
	assert.match(read("cutting/CuttingPlanSidebar.vue"), /formatDisplayDatetime\(sheet\.printed_time\)/)
	assert.match(read("CuttingBulkLaySheet.vue"), /formatDisplayDate\(record\.value\.posting_date, ""\)/)
	for (const path of ["cutting/CpmTransactionDialog.vue", "cutting/CuttingMarkerDialog.vue", "cutting/CuttingPlanStockTransfers.vue"]) {
		assert.match(read(path), /formatDisplayDatetime\(record\.modified\)/, path)
	}
	for (const path of ["cutting/CuttingPlanActions.vue", "cutting/order/CuttingOrderActions.vue"]) {
		assert.match(read(path), /formatDisplayDatetime\(new Date\(\), \{ seconds: true \}\)/, path)
	}
})

test("Planner status shows optimization times as DD-MM-YYYY HH:mm", async () => {
	const { findNodes, loadComponent, mountComponent } = await import("../../scripts/helpers/vue_renderer.mjs")
	const PlannerStatus = loadComponent(join(departments, "cutting/planner/PlannerStatus.vue"), {})
	const root = mountComponent(PlannerStatus, { status: "Completed", started: "2026-10-23 09:05:41.123456", completed: "2026-10-23T14:30:00" })
	const text = (node) => node.type === "comment" ? "" : node.text + node.children.map(text).join("")
	assert.deepEqual(findNodes(root, (node) => node.type === "strong").map(text).slice(1), ["23-10-2026 09:05", "23-10-2026 14:30"])
})
