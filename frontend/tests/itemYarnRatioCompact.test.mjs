import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

const source = readFileSync(new URL("../src/departments/purchase/item/ItemYarnRatio.vue", import.meta.url), "utf8")

test("yarn ratio card is half width and left-aligned on desktop, full width on narrow screens", () => {
	assert.match(source, /<ItemTableCard class="item-yarn-ratio"/)
	assert.match(source, /\.item-yarn-ratio \{ width: 50%; justify-self: start; \}/)
	assert.match(source, /@media \(max-width: 900px\) \{ \.item-yarn-ratio \{ width: 100%; \} \}/)
})

test("yarn ratio keeps the ratio column narrow", () => {
	assert.match(source, /key: "yarn_item",[^}]*width: 300 \}/)
	assert.match(source, /key: "ratio",[^}]*width: 100 \}/)
})
