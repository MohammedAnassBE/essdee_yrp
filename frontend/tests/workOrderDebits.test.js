import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import test from "node:test"

import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"

const read = (path) => readFileSync(resolve(`frontend/src/departments/${path}`), "utf8")
const text = (node) => node.type === "comment" ? "" : node.text + node.children.map(text).join("")
const stub = (tag) => (props) => Vue.h(tag, props)
const DebitTable = loadComponent(resolve("frontend/src/departments/fabric-store/WorkOrderDebitTable.vue"), {
	"primevue/button": stub("approve-button"),
	"../../components/common/DocumentLink.vue": (props) => Vue.h("doc-link", props, props.label),
	"../../components/documents/DocumentStatusBadge.vue": (props) => Vue.h("status", props, props.label),
})
const debits = [
	{ name: "DEBIT-1", work_order: "WO-1", debit_type: "Permanent", debit_no: "11", debit_value: 100, reason: "Short", inspection: 0, on_close: 1, status: "Approved" },
	{ name: "DEBIT-2", work_order: "WO-1", debit_type: "Permanent", debit_no: "", debit_value: 50.5, reason: "QC", inspection: 1, on_close: 0, status: "Debit Requested" },
]

function rows(root, tag) {
	return findNodes(root, (node) => node.type === "tr").map((row) => row.children.filter((cell) => cell.type === tag).map(text))
}

test("debit table lists production columns, flags and the total", () => {
	const root = mountComponent(DebitTable, { debits, showWorkOrder: true })
	assert.deepEqual(rows(root, "th")[0], ["S.No.", "Work Order", "Debit", "Debit Type", "Debit No", "Debit Value", "Reason", "Inspection", "On Close", "Status"])
	const body = rows(root, "td").filter((cells) => cells.length)
	assert.deepEqual(body[0], ["1", "WO-1", "DEBIT-1", "Permanent", "11", "100.00", "Short", "No", "Yes", "Approved"])
	assert.deepEqual(body[1].slice(4, 9), ["—", "50.50", "QC", "Yes", "No"])
	assert.ok(text(root).includes("150.50"))
	assert.equal(findNodes(root, (node) => node.type === "approve-button").length, 0)
})

test("approvers see Approve only on requested debits", () => {
	const root = mountComponent(DebitTable, { debits, canApprove: true })
	const buttons = findNodes(root, (node) => node.type === "approve-button")
	assert.equal(buttons.length, 1)
	assert.equal(rows(root, "th")[0].at(-1), "Action")
	assert.equal(rows(root, "th")[0].includes("Work Order"), false)

	const approved = mountComponent(DebitTable, { debits: [debits[0]], canApprove: true })
	assert.equal(rows(approved, "th")[0].includes("Action"), false)
})

test("close panel shows debits first, offers attachable debit entry and keeps the panel open on approve", () => {
	const panel = read("fabric-store/WorkOrderActionPanel.vue")
	const closeBlock = panel.slice(panel.indexOf('v-else-if="isCloseMode"'), panel.indexOf("v-else-if=\"mode === 'create_debit'\""))
	assert.ok(closeBlock.indexOf("<WorkOrderDebitTable") < closeBlock.indexOf("Close reason *"))
	assert.match(closeBlock, /:can-approve="Boolean\(closeContext\.can_approve_debit\)"/)
	assert.match(closeBlock, /<DebitEntryFields v-if="draft\.with_debit"[^>]*v-model:reason="draft\.debit_reason"[^>]*v-model:debit-document="draft\.debit_document"/)
	const approve = panel.slice(panel.indexOf("async function approveDebit"), panel.indexOf("async function confirmClose"))
	assert.match(approve, /approved\.status = "Approved"/)
	assert.doesNotMatch(approve, /close\(\)/)
})

test("Purchase Invoice verification reuses the debit table with the Work Order column", () => {
	const verification = read("accounts/components/PurchaseInvoiceVerification.vue")
	assert.match(verification, /<WorkOrderDebitTable[^>]*:debits="debitSummary"[^>]*show-work-order/)
})

test("debit view offers Approve only to approvers of a requested debit", () => {
	const view = read("accounts/Debits.vue")
	assert.match(view, /doc\.docstatus === 1 && doc\.status === "Debit Requested" && Boolean\(await callMethod\(`\$\{DEBIT_METHOD\}\.has_debit_approval_permission`\)\)/)
	assert.match(view, /<Button v-if="canApprove" label="Approve"/)
})
