import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

const read = (path) => readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8")
const matrix = read("departments/fabric-store/WorkOrderItemMatrix.vue")

test("Work Order quantity tables sit in clipped pinned-table boxes with a synced horizontal scrollbar", () => {
	assert.match(matrix, /<div v-synced-horizontal-scroll class="erp-table-wrap erp-pinned-table work-order-item-matrix__scroll" role="region"[^>]*>\s*<table class="erp-data-table work-order-item-matrix__table">\s*<thead>/)
	assert.match(matrix, /<\/table>\s*<div class="erp-pinned-table__scrollbar" data-horizontal-scrollbar aria-hidden="true" hidden><div \/><\/div>\s*<\/div>/)
	assert.match(matrix, /import \{ vSyncedHorizontalScroll \} from "\.\.\/\.\.\/components\/common\/childGrid\/syncedHorizontalScroll\.js"/)
	assert.doesNotMatch(matrix, /work-order-item-matrix__scroll[^>]*tabindex/)
	assert.doesNotMatch(matrix, /\.work-order-item-matrix__scroll \{/)
})

test("Work Order boxes between the tables and the page or dialog scroller never become scroll containers", () => {
	const boxes = [
		["departments/fabric-store/WorkOrderItemMatrix.vue", "work-order-item-matrix"],
		["departments/fabric-store/WorkOrderDetails.vue", "work-order-section"],
		["departments/fabric-store/WorkOrderSummary.vue", "work-order-summary__section"],
		["departments/FabricWorkOrder.vue", "work-order-tabs"],
		["departments/purchase/lot/lot.css", "lot-section"],
	]
	for (const [path, selector] of boxes) {
		const source = read(path)
		assert.match(source, new RegExp(`\\.${selector} \\{[^}]*overflow: clip;`), path)
		assert.doesNotMatch(source, new RegExp(`\\.${selector} \\{[^}]*(max-height|overflow: (hidden|auto))`), path)
	}
})

test("Work Order tab list scrolls away so table headers own the top of the scroller", () => {
	assert.doesNotMatch(read("departments/FabricWorkOrder.vue"), /\.work-order-tablist \{[^}]*position: sticky/)
})

test("Lot document pop-up has no top padding on its scroller so pinned Work Order headers sit flush", () => {
	for (const path of ["departments/purchase/lot/lot.css"]) {
		assert.match(read(path), /\.lot-document-dialog\.p-dialog \.p-dialog-content \{\s*padding-top: 0;\s*\}/, path)
	}
})
