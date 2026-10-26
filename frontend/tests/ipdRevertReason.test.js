import assert from "node:assert/strict"
import test from "node:test"
import { readFileSync } from "node:fs"
import { revertReasonPayload } from "../src/departments/merch/ipd/ipdRevertReason.js"

const page = () => readFileSync(new URL("../src/departments/merch/ipd/IpdPage.vue", import.meta.url), "utf8")

test("revert payload needs a non-blank reason and sends it trimmed", () => {
	for (const reason of [undefined, null, "", "   \n\t"]) assert.equal(revertReasonPayload(reason), null)
	assert.deepEqual(revertReasonPayload("  Wrong ratio \n"), { reason: "Wrong ratio" })
})

test("revert dialog keeps the lots message and adds a required multiline reason", () => {
	const source = page()
	const dialog = source.match(/<DocumentConfirmationDialog[\s\S]*?<\/DocumentConfirmationDialog>/)?.[0] || ""
	assert.match(dialog, /:message="revertMessage"/)
	assert.match(dialog, /<Textarea[^>]*v-model="revertReason"[^>]*required/)
	assert.match(dialog, /:confirm-disabled="!revertPayload"/)
	assert.match(dialog, /@confirm="runCommand\('revert_approval', revertPayload\)"/)
	assert.match(source, /const revertPayload = computed\(\(\) => revertReasonPayload\(revertReason.value\)\)/)
	assert.match(source, /revert_approval: \(\) => \{ revertReason.value = ""; revertVisible.value = true \}/)
})

test("record commands pass their payload to the API", () => {
	assert.match(page(), /executeIpdCommand\(record.value.name, command, \{ payload, expectedModified: record.value.modified \}\)/)
})

test("confirmation dialog can hold its confirm button until the form is valid", () => {
	const dialog = readFileSync(new URL("../src/components/documents/DocumentConfirmationDialog.vue", import.meta.url), "utf8")
	assert.match(dialog, /confirmDisabled: \{ type: Boolean, default: false \}/)
	assert.match(dialog, /:disabled="confirmDisabled"/)
})

test("desk revert asks for a required reason and sends it", () => {
	const desk = readFileSync(new URL("../../essdee_yrp/public/js/item_production_detail.js", import.meta.url), "utf8")
	const revert = desk.slice(desk.indexOf('__("Revert Approval"), () =>'), desk.indexOf("essdee_yrp.ipd_ui.revert_ipd_approval") + 200)
	assert.doesNotMatch(revert, /frappe\.confirm/)
	assert.match(revert, /frappe\.prompt\(\s*\[\{ fieldname: "reason", fieldtype: "Small Text", label: __\("Reason"\), reqd: 1 \}\]/)
	assert.match(revert, /args: \{ doc_name: frm\.doc\.name, reason: values\.reason \}/)
})
