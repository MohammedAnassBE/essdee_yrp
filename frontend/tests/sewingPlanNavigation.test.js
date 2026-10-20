import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

const read = (path) => readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8")

test("Open Sewing Plan goes to the Sewing data entry for the Work Order's unit and Lot", () => {
	const workOrder = read("departments/FabricWorkOrder.vue")
	assert.match(workOrder, /path: "\/sewing\/plans", query: \{ \.\.\.\(capability\.source_context \|\| \{\}\), tab: "data-entry" \}/)
	assert.doesNotMatch(workOrder, /webDocumentPath\("SD YRP Sewing Plan"/)
})

test("Sewing data entry starts on the Lot named in the URL", () => {
	const workspace = read("departments/sewing/SewingPlanWorkspace.vue")
	assert.match(workspace, /entryFilters = reactive\(\{ lot: typeof route\.query\.lot === "string" \? route\.query\.lot : ""/)
})
