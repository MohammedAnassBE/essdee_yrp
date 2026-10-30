import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import { getScrollLeftToReveal } from "../src/components/common/childGrid/syncedHorizontalScroll.js"

const read = (path) => readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8")
const enterprise = read("styles/enterprise.css")
const scroller = read("components/common/childGrid/syncedHorizontalScroll.js")
const workspaces = [
	["GoodsReceivedNoteWorkspace.vue", "goods-received-note"],
	["DeliveryChallanWorkspace.vue", "delivery-challan"],
]

test("GRN and DC quantity tables sit in clipped pinned-table boxes with a synced horizontal scrollbar", () => {
	for (const [page, prefix] of workspaces) {
		const workspace = read(`departments/fabric-store/${page}`)
		assert.match(workspace, new RegExp(`<div v-synced-horizontal-scroll class="erp-table-wrap erp-pinned-table ${prefix}-matrix__scroll" role="region"[^>]*>\\s*<table v-entry-table class="erp-data-table">\\s*<thead><tr>`), page)
		assert.match(workspace, /<\/table>\s*<div class="erp-pinned-table__scrollbar" data-horizontal-scrollbar aria-hidden="true" hidden><div \/><\/div>\s*<\/div>/, page)
		assert.match(workspace, /import \{ vSyncedHorizontalScroll \} from "\.\.\/\.\.\/components\/common\/childGrid\/syncedHorizontalScroll\.js"/, page)
		assert.match(workspace, new RegExp(`\\.${prefix}-matrix \\{ overflow: clip;`), page)
		assert.match(workspace, new RegExp(`\\.${prefix}-matrix__group \\{ overflow: clip;`), page)
		assert.doesNotMatch(workspace, new RegExp(`\\.${prefix}-matrix[^{]*\\{[^}]*(max-height|overflow: (hidden|auto))`), page)
	}
})

test("pinned-table CSS keeps headers sticky to the single outer scroller", () => {
	assert.match(enterprise, /\.erp-pinned-table \{\s*--erp-pinned-head-height: 56px;\s*overflow: clip;/)
	assert.match(enterprise, /\.erp-pinned-table thead th \{\s*z-index: calc\(var\(--erp-layer-content\) \+ 1\);\s*height: var\(--erp-pinned-head-height\);/)
	assert.match(enterprise, /\.erp-pinned-table tbody :is\(input, button, \[tabindex\]\) \{\s*scroll-margin-top: calc\(var\(--erp-pinned-head-height\) \+ 8px\);/)
	assert.match(enterprise, /\.erp-pinned-table__scrollbar \{\s*position: sticky;\s*z-index: calc\(var\(--erp-layer-content\) \+ 1\);\s*bottom: 0;\s*overflow-x: auto;/)
	assert.match(enterprise, /\.fabric-document-workspace--page \.erp-pinned-table thead th \{\s*top: var\(--erp-shell-header-height\);/)
	assert.match(enterprise, /\.erp-data-table th,[^{]*\{[^}]*position: sticky;[^}]*top: 0;[^}]*background: var\(--erp-surface-muted\);/)
})

test("horizontal sync only slides the table and never moves the header on vertical scroll", () => {
	assert.match(scroller, /bar\.addEventListener\("scroll", onBarScroll, \{ passive: true \}\)/)
	assert.match(scroller, /table\.style\.translate = bar\.scrollLeft \? `\$\{-bar\.scrollLeft\}px 0` : ""/)
	assert.doesNotMatch(scroller, /translateY|document\.addEventListener\("scroll"/)
})

test("focused cells are revealed horizontally", () => {
	assert.equal(getScrollLeftToReveal({ cellLeft: 100, cellRight: 200, viewWidth: 500, scrollLeft: 0 }), 0)
	assert.equal(getScrollLeftToReveal({ cellLeft: 700, cellRight: 800, viewWidth: 500, scrollLeft: 0 }), 300)
	assert.equal(getScrollLeftToReveal({ cellLeft: 50, cellRight: 150, viewWidth: 500, scrollLeft: 300 }), 50)
})

test("submitted and cancelled GRN/DC read-only matrices opt into the pinned header", () => {
	const matrix = read("components/stock/StockItemMatrix.vue")
	assert.match(matrix, /pinnedHeader: \{ type: Boolean, default: false \}/)
	assert.match(matrix, /<div v-synced-horizontal-scroll class="item-matrix__scroll" :class="\{ 'erp-pinned-table': pinnedHeader \}"/)
	assert.match(matrix, /<div v-if="pinnedHeader" class="erp-pinned-table__scrollbar" data-horizontal-scrollbar aria-hidden="true" hidden><div \/><\/div>/)
	assert.match(matrix, /\.item-matrix--pinned-header,\s*\.item-matrix--pinned-header \.item-matrix__group,\s*\.item-matrix--pinned-header \.item-matrix__scroll \{\s*min-width: 0;\s*overflow: clip;/)
	assert.match(matrix, /\.item-matrix--pinned-header \.item-matrix__footer :is\(th, td\) \{\s*position: static;/)
	for (const [page] of workspaces) {
		assert.match(read(`departments/fabric-store/${page}`), /<StockItemMatrix [^>]*group-by-item pinned-header/, page)
	}
	assert.match(scroller, /const \{ table, bar \} = parts\(wrap\)\n\t\tif \(!bar\) return/)
	assert.match(scroller, /if \(!state\.has\(wrap\)\) return/)
})
