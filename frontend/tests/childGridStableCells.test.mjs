import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

import { keepIfUnchanged, resolveGridColumns } from "../src/components/common/childGrid/childGridColumns.js"

const read = (path) => readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8")
const schema = [{ key: "size", label: "Size", fieldtype: "Data" }, { key: "qty", label: "Qty", fieldtype: "Int", reqd: 1 }]

test("rebuilt but equal grid columns keep the previous array so DataTable keeps cell editors mounted", () => {
	const first = resolveGridColumns(schema, null)
	assert.equal(keepIfUnchanged(first, resolveGridColumns(schema.map((column) => ({ ...column })), null)), first)
	assert.equal(keepIfUnchanged(undefined, first), first)
	const relabelled = resolveGridColumns([{ ...schema[0], label: "Sizes" }, schema[1]], null)
	assert.equal(keepIfUnchanged(first, relabelled), relabelled)
})

test("grid visible columns are memoized against the previous value", () => {
	assert.match(read("components/common/childGrid/useGridColumns.js"), /computed\(\(previous\) => keepIfUnchanged\(previous, resolveGridColumns\(/)
})

test("child grid columns read widths from CSS variables, so a resize does not remount cells", () => {
	const source = read("components/common/childGrid/ChildGridTable.vue")
	const template = source.slice(0, source.indexOf("</template>\n\n<script"))
	assert.doesNotMatch(template, /columnWidths/)
	assert.match(template, /<Column v-for="\(column, index\) in visibleColumns"[^>]*widthStyle\(`var\(--child-grid-column-\$\{index\}\)`\)/)
	assert.match(source, /--child-grid-column-\$\{index\}`, `\$\{width\}px`/)
})

test("lotwise cost sections build child metadata once instead of on every render", () => {
	const source = read("departments/pd/components/LotwiseCostSections.vue")
	assert.match(source, /const childMetas = computed\(/)
	assert.match(source, /function childMetaFor\(fieldname\) \{\n\treturn childMetas\.value\[fieldname\]\n\}/)
})

test("row remove buttons stay out of the Tab order between cells", () => {
	assert.match(read("components/common/ChildTableField.vue"), /<Button icon="pi pi-trash"[^>]*tabindex="-1"[^>]*removeRow\(index\)/)
})
