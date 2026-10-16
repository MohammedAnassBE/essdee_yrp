#!/usr/bin/env node
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"

import { documentStatusTone, listStatusTone } from "../frontend/src/utils/statusTone.js"

for (const tone of [documentStatusTone, listStatusTone]) {
	assert.equal(tone("Not Approved"), "warning")
	assert.equal(tone("Unapproved"), "warning")
	assert.equal(tone("Approved"), "success")
}
assert.equal(documentStatusTone("Pending Approval"), "warning")
assert.equal(documentStatusTone("Open"), "success")
assert.equal(documentStatusTone("Closed"), "neutral")
assert.equal(documentStatusTone("Cancelled"), "danger")
assert.equal(documentStatusTone("", 1), "success")
assert.equal(listStatusTone("Pending"), "danger")
assert.equal(listStatusTone("Partially Received"), "warning")
assert.equal(listStatusTone("Completed"), "success")
assert.equal(listStatusTone("Open"), "neutral")

const badge = readFileSync(new URL("../frontend/src/components/documents/DocumentStatusBadge.vue", import.meta.url), "utf8")
const list = readFileSync(new URL("../frontend/src/components/common/ListView.vue", import.meta.url), "utf8")
assert.match(badge, /documentStatusTone\(displayLabel\.value, props\.docstatus\)/)
assert.match(list, /return listStatusTone\(status\)/)
console.log("status tone tests passed")
