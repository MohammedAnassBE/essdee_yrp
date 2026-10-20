import assert from "node:assert/strict"
import test from "node:test"
import { expandTemplateItemFilters, hasChildTableFilter, parentGroupBy } from "../src/components/common/listItemFilters.js"

const itemFields = [{ fieldname: "item" }, { doctype: "Entry", fieldname: "item" }, { doctype: "Detail", fieldname: "item_variant" }]
const variants = { Template: ["Template", "Variant", "Disabled Variant"], Plain: ["Plain"] }

for (const [operator, expanded] of [["=", "in"], ["!=", "not in"], ["in", "in"], ["not in", "not in"]]) {
	test(`template Item ${operator} expands parent and child filters`, () => {
		const value = ["in", "not in"].includes(operator) ? ["Template", "Plain", "Variant"] : "Template"
		const names = ["in", "not in"].includes(operator) ? [...variants.Template, "Plain"] : variants.Template
		const filters = [["Entry", "item", operator, value], ["Detail", "item_variant", operator, value]]
		const original = structuredClone(filters)
		assert.deepEqual(expandTemplateItemFilters(filters, itemFields, variants), [["Entry", "item", expanded, names], ["Detail", "item_variant", expanded, names]])
		assert.deepEqual(filters, original)
	})
}

test("plain, comma-separated membership and three-part parent Item filters work", () => {
	assert.deepEqual(expandTemplateItemFilters([["item", "=", "Plain"], ["item", "in", "Template, Plain"]], itemFields, variants), [["item", "in", ["Plain"]], ["item", "in", [...variants.Template, "Plain"]]])
})

test("unrelated fields, child doctypes and operators stay unchanged", () => {
	const filters = [["Other", "item", "=", "Template"], ["supplier", "=", "Template"], ["item", "like", "%Template%"], ["item", "is", "set"]]
	assert.deepEqual(expandTemplateItemFilters(filters, itemFields, variants), filters)
	assert.deepEqual(expandTemplateItemFilters([["item", "=", "Unknown"]], itemFields, variants), [["item", "in", ["Unknown"]]])
})

test("child table filters are detected so list rows are de-duplicated per parent", () => {
	assert.equal(hasChildTableFilter([["Entry", "docstatus", "=", 1], ["name", "like", "%A%"]], "Entry"), false)
	assert.equal(hasChildTableFilter([["Detail", "item", "in", ["A"]]], "Entry"), true)
})

test("child table filters group list rows by the parent name", () => {
	assert.equal(parentGroupBy([["Entry", "docstatus", "=", 1]], "Entry"), undefined)
	assert.equal(parentGroupBy([["Detail", "item", "in", ["A"]]], "Entry"), "`tabEntry`.`name`")
})
