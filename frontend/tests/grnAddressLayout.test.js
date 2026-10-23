import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import vm from "node:vm"

const read = (path) => readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8")
const workspace = read("departments/fabric-store/GoodsReceivedNoteWorkspace.vue")

function constant(name) {
	const match = workspace.match(new RegExp(`const ${name} = ([\\[{][\\s\\S]*?\\n[\\]}])\\n`))
	assert.ok(match, name)
	return JSON.parse(JSON.stringify(vm.runInNewContext(`(${match[1]})`)))
}

test("GRN keeps addresses and contact in one card next to the movement fields", () => {
	const groups = constant("grnGroupFields")
	assert.deepEqual(groups.movement, ["from_warehouse", "delivery_location", "to_warehouse", "delivery_location_name"])
	assert.deepEqual(groups.addresses, [
		"supplier_address", "supplier_address_display",
		"billing_address", "billing_address_display",
		"delivery_address", "delivery_address_display",
		"contact_person", "contact_display", "contact_mobile",
	])
	assert.match(workspace, /const primaryGroupKeys = \["posting", "movement", "addresses"\]/)
	const order = constant("grnFieldGroups").map((group) => group.key)
	assert.equal(order.indexOf("addresses"), order.indexOf("movement") + 1)
})

test("GRN address card lays each address over its details in three columns", () => {
	assert.match(workspace, /:data-fieldname="field\.fieldname"/)
	assert.match(workspace, /"supplier_address billing_address delivery_address" "supplier_address_display billing_address_display delivery_address_display" "contact_person contact_display contact_mobile"/)
	for (const fieldname of constant("grnGroupFields").addresses) {
		assert.match(workspace, new RegExp(`\\[data-fieldname="${fieldname}"\\]\\) \\{ grid-area: ${fieldname}; \\}`), fieldname)
	}
})

test("Read-only text boxes start at one row and grow to their content", () => {
	const formField = read("components/common/FormField.vue")
	assert.match(formField, /const textAreaRows = computed\(\(\) => isDisabled\.value \? 1 :/)
	assert.match(formField, /:rows="textAreaRows"\n\t\t\tauto-resize/)
})
