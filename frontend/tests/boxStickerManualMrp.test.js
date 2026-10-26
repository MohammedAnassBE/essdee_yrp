import assert from "node:assert/strict"
import test from "node:test"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { Vue } from "../../scripts/helpers/vue_renderer.mjs"

const PATH = "frontend/src/departments/cut-panel-store/BoxStickerPrintPage.vue"
const source = readFileSync(resolve(PATH), "utf8")
const script = source.split("<script setup>")[1].split("</script>")[0].replace(/^import[\s\S]*? from ["'][^"']+["'];?\n/gm, "")

function dialog() {
	const values = {
		...Vue, watch: () => {}, onMounted: () => {}, onBeforeUnmount: () => {}, onBeforeRouteLeave: () => {},
		defineProps: () => ({ boxStickerPrintId: "" }), useRoute: () => ({ query: {} }), onBeforeRouteUpdate: () => {},
		useRouter: () => ({ push() {}, replace() {} }), takeNewDocumentDefaults: () => ({}), withNewDocumentDefaults: (value) => value,
		usePageTitle: () => {}, useDuplicateAction: () => ({ value: null }), loadDuplicateValues: async () => null,
		window: { addEventListener() {}, removeEventListener() {} },
	}
	return new Function(...Object.keys(values), `${script}\nreturn { rows, documentValues, sourcePreviewValues }`)(...Object.values(values))
}

test("manual Box Sticker save sends the MRP and quantity the user typed", () => {
	const box = dialog()
	box.rows.value = [{ name: "ROW-S", size: "S", mrp: 199.5, quantity: 42, allow_excess_percentage: 5 }]
	assert.deepEqual(
		{ mrp: box.documentValues().rows[0].mrp, quantity: box.documentValues().rows[0].quantity },
		{ mrp: 199.5, quantity: 42 },
	)
})

test("Fetch Size Rows asks the server for suggested MRPs instead of resending typed ones", () => {
	const box = dialog()
	box.rows.value = [{ name: "ROW-S", size: "S", mrp: 199.5, quantity: 42, allow_excess_percentage: 5 }]
	assert.equal("mrp" in box.sourcePreviewValues().rows[0], false)
	assert.equal(box.sourcePreviewValues().rows[0].quantity, 42)
})

test("draft Box Sticker rows render an editable MRP input", () => {
	assert.match(source, /<InputNumber[^>]*v-model="row\.mrp"/s)
})
