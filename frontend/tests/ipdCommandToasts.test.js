import assert from "node:assert/strict"
import test from "node:test"
import { readFileSync } from "node:fs"
import { ipdCommandSuccess } from "../src/departments/merch/ipd/ipdCommandSuccess.js"

test("IPD commands have explicit success messages", () => {
	for (const [command, summary] of Object.entries({ approve: "IPD approved", revert_approval: "IPD approval reverted", regenerate_process_matrix: "Process matrix regenerated" })) {
		assert.deepEqual(ipdCommandSuccess(command, "IPD-2"), { severity: "success", summary, detail: "IPD-2", life: 3500 })
	}
})

test("record commands and editor approve/regenerate show their success toast only after the API succeeds", () => {
	const page = readFileSync(new URL("../src/departments/merch/ipd/IpdPage.vue", import.meta.url), "utf8")
	const editor = readFileSync(new URL("../src/departments/merch/ipd/useIpdEditor.js", import.meta.url), "utf8")
	assert.match(page, /await executeIpdCommand[\s\S]*toast.add\(ipdCommandSuccess\(command, record.value.name\)\)/)
	for (const command of ["approve", "regenerate_process_matrix"]) {
		assert.ok(editor.includes(`toast.add(ipdCommandSuccess("${command}", name.value))`))
	}
})
