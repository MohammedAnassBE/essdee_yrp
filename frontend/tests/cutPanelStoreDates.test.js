import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import test from "node:test"

import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"

const read = (path) => readFileSync(new URL(`../src/departments/cut-panel-store/${path}`, import.meta.url), "utf8")
const text = (node) => node.type === "comment" ? "" : node.text + node.children.map(text).join("")

test("Cut Panel Movement rail shows posting date as DD-MM-YYYY HH:mm", () => {
	const control = (props, { slots }) => Vue.h("control", props, slots.default?.())
	const Rail = loadComponent(resolve("frontend/src/departments/cut-panel-store/CutPanelMovementRail.vue"), {
		"primevue/button": control,
		"primevue/skeleton": control,
		"../../components/documents/DocumentStatusBadge.vue": control,
		"../../utils/documentValues.js": { normaliseFrappeTime: (value) => String(value || "") },
	})
	const linked = { sections: { stock_entries: [{ name: "SE-0001", posting_date: "2026-10-23", posting_time: "14:05:09", docstatus: 1 }] }, actions: {} }
	const root = mountComponent(Rail, { linked })
	const small = findNodes(root, (node) => node.type === "small").map(text)
	assert.deepEqual(small, ["23-10-2026 14:05"])
})

test("Cut Panel Store dialogs and reports format dates through the shared helper", () => {
	const dialog = read("CutBundleEditDialog.vue")
	assert.match(dialog, /formatDisplayDatetime\(record\.value\?\.printed_time, \{ fallback: "Not printed" \}\)/)
	assert.doesNotMatch(dialog, /function formatDateTime/)
	const report = read("CutBundleBalanceReport.vue")
	assert.match(report, /formatDisplayByFieldtype\(cellValue\(row, column\), column\.fieldtype/)
	assert.match(report, /\{\{ cellText\(row, column\) \|\| "—" \}\}/)
})
