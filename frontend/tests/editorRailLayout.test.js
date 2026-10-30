import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

const source = (path) => readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8")

test("document workspace drops the right rail and gives the main column full width when showRail is false", () => {
	const workspace = source("departments/fabric-store/FabricDocumentWorkspace.vue")
	assert.match(workspace, /showRail: \{ type: Boolean, default: true \}/)
	assert.match(workspace, /<aside v-if="showRail" class="fabric-document-workspace__rail"/)
	assert.match(workspace, /:class="\{ 'fabric-document-workspace__columns--without-rail': !showRail \}"/)
	assert.match(workspace, /\.fabric-document-workspace__columns\.fabric-document-workspace__columns--without-rail \{ grid-template-areas: "main"; grid-template-columns: minmax\(0, 1fr\); \}\n<\/style>/)
})

test("GRN and Delivery Challan hide the totals rail while the draft is editable", () => {
	for (const page of ["GoodsReceivedNoteWorkspace.vue", "DeliveryChallanWorkspace.vue"]) {
		assert.match(source(`departments/fabric-store/${page}`), /:show-rail="!canEditDraft"/, page)
	}
})

test("GRN and Delivery Challan quantity grids stay compact without an inner vertical scroller", () => {
	for (const [page, prefix] of [["GoodsReceivedNoteWorkspace.vue", "goods-received-note"], ["DeliveryChallanWorkspace.vue", "delivery-challan"]]) {
		const workspace = source(`departments/fabric-store/${page}`)
		assert.doesNotMatch(workspace, new RegExp(`\\.${prefix}-matrix__scroll \\{[^}]*max-height`), page)
		assert.match(workspace, new RegExp(`\\.${prefix}-matrix :deep\\(\\.p-inputnumber\\) \\{ min-width: 64px; \\}`), page)
		assert.match(workspace, new RegExp(`\\.${prefix}-matrix__secondary-inline \\{ display: grid; grid-template-columns: minmax\\(0, 1fr\\);`), page)
		assert.match(workspace, new RegExp(`<td class="${prefix}-matrix__comments"><InputText`), page)
		assert.doesNotMatch(workspace, /min-width: 94px/, page)
	}
})

test("Purchase Invoice editor shows totals as a full-width strip instead of a side rail", () => {
	const body = source("departments/accounts/components/PurchaseInvoiceEditorBody.vue")
	assert.match(body, /\.purchase-invoice-editor__body \{ display: grid; width: 100%; min-width: 0; grid-template-columns: minmax\(0, 1fr\);/)
	assert.match(body, /\.purchase-invoice-editor__rail \{ display: grid; grid-template-columns: repeat\(4, minmax\(0, 1fr\)\);/)
	assert.doesNotMatch(body, /position: sticky/)
})

test("Cut Panel Movement shows the linked-documents rail only after submit or cancel", () => {
	const dialog = source("departments/cut-panel-store/CutPanelMovementDialog.vue")
	assert.match(dialog, /const showRail = computed\(\(\) => Boolean\(record\.value && Number\(record\.value\.docstatus \|\| 0\) !== 0\)\)/)
	assert.match(dialog, /<CutPanelMovementRail\n\t+v-if="showRail"/)
	assert.match(dialog, /'cut-panel-movement-layout--without-rail': !showRail/)
})
