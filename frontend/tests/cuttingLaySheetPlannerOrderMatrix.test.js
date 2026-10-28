import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

const source = readFileSync(new URL("../src/departments/cutting/planner/PlannerOrderMatrix.vue", import.meta.url), "utf8")

test("planner order details table adds a row on Enter through its own addRow", () => {
	assert.match(source, /import \{ vEntryTable \} from "\.\.\/\.\.\/\.\.\/components\/common\/childGrid\/entryTable\.js"/)
	assert.match(source, /<table v-entry-table="\{ add: editable \? addRow : null, fixed: false \}">/)
	assert.match(source, /function addRow\(\) \{ emit\("update:rows", \[\.\.\.cloneRows\(\), \{ _row_key: `new-size-\$\{\+\+rowSequence\}`, name: "", size: "", qty: 0 \}\]\) \}/)
})
