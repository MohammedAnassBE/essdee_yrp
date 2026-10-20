import assert from "node:assert/strict"
import test from "node:test"
import { canDeleteDocument, documentDeletedToast, getDeleteRedirectTarget } from "../src/utils/documentDelete.js"

test("only named drafts and cancelled documents with delete permission can be deleted", () => {
	for (const docstatus of [0, "0", 2, "2"]) assert.equal(canDeleteDocument({ name: "DOC-1", docstatus, permissions: { delete: 1 } }), true)
	for (const docstatus of [1, "1"]) assert.equal(canDeleteDocument({ name: "DOC-1", docstatus, permissions: { delete: 1 } }), false)
	assert.equal(canDeleteDocument({ name: "DOC-1", docstatus: 0 }), false)
	assert.equal(canDeleteDocument({ name: "DOC-1", permissions: { delete: 0 } }), false)
	assert.equal(canDeleteDocument({ permissions: { delete: 1 } }), false)
})
test("delete redirect prefers the explicit target, then navigation backTo, then home", () => {
	assert.equal(getDeleteRedirectTarget("/explicit", "/list"), "/explicit")
	assert.equal(getDeleteRedirectTarget("", "/list"), "/list")
	assert.equal(getDeleteRedirectTarget(), "/")
})

test("delete toast uses the document label and name", () => {
	assert.deepEqual(documentDeletedToast("SD YRP Lot", "LOT-1", "Lot"), { severity: "success", summary: "Lot LOT-1 deleted", life: 3500 })
	assert.equal(documentDeletedToast("Purchase Order", "PO-1").summary, "Purchase Order PO-1 deleted")
})
