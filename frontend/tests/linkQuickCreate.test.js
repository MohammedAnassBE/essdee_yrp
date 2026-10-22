import assert from "node:assert/strict"
import test from "node:test"
import { readFileSync } from "node:fs"
import { canCreateDoctype } from "../src/utils/linkTarget.js"
import { linkCreateValues, quickEntryPlan } from "../src/utils/quickEntry.js"

const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8")

const attributeValueMeta = {
	name: "YRP Item Attribute Value",
	title_field: "attribute_value",
	fields: [
		{ fieldname: "attribute_name", fieldtype: "Link", options: "Item Attribute", reqd: 1 },
		{ fieldname: "attribute_value", fieldtype: "Data", reqd: 1 },
		{ fieldname: "notes", fieldtype: "Small Text" },
		{ fieldname: "section", fieldtype: "Section Break", reqd: 1 },
	],
}

test("create is offered only for doctypes the user can create", () => {
	const boot = { user: { name: "store@example.test", can_create: ["YRP Item Attribute Value"] } }
	assert.equal(canCreateDoctype("YRP Item Attribute Value", boot), true)
	assert.equal(canCreateDoctype("Item", boot), false)
	assert.equal(canCreateDoctype("Item", { user: {} }), false)
	assert.equal(canCreateDoctype("", boot), false)
})

test("link filters with plain values preset the new record, operator filters do not", () => {
	assert.deepEqual(linkCreateValues({ attribute_name: "Colour", disabled: 0, item: ["in", ["A"]], blank: "" }), { attribute_name: "Colour", disabled: 0 })
	assert.deepEqual(linkCreateValues({ attribute_name: "Dia" }, { attribute_name: "Colour" }), { attribute_name: "Colour" })
})

test("quick entry shows mandatory fields, locks presets and puts the typed text in the title field", () => {
	const plan = quickEntryPlan(attributeValueMeta, { attribute_name: "Colour", unknown: "x" }, "Navy")
	assert.equal(plan.supported, true)
	assert.deepEqual(plan.fields.map((field) => field.fieldname), ["attribute_name", "attribute_value"])
	assert.deepEqual(plan.locked, ["attribute_name"])
	assert.deepEqual(plan.values, { attribute_name: "Colour", attribute_value: "Navy" })
})

test("quick entry asks for the name of prompt-named doctypes and falls back for mandatory tables", () => {
	const prompt = quickEntryPlan({ name: "Brand", autoname: "Prompt", fields: [] }, {}, "Acme")
	assert.deepEqual(prompt.fields.map((field) => field.fieldname), ["__newname"])
	assert.deepEqual(prompt.values, { __newname: "Acme" })
	const table = quickEntryPlan({ name: "BOM", fields: [{ fieldname: "items", fieldtype: "Table", reqd: 1 }] })
	assert.equal(table.supported, false)
})

test("LinkField offers Create a new <DocType> below the options and selects the created record", () => {
	const link = source("../src/components/common/LinkField.vue")
	assert.match(link, /<template v-if="showCreate" #footer>/)
	assert.match(link, /Create a new \{\{ createTarget \}\}/)
	assert.match(link, /canCreateDoctype\(createTarget\.value\)/)
	assert.match(link, /@mousedown\.prevent/)
	assert.match(link, /QuickEntryDialog/)
	assert.match(link, /auto-option-focus/)
})

test("stock attribute fields create YRP Item Attribute Values for their own attribute", () => {
	const composer = source("../src/components/stock/StockItemComposer.vue")
	assert.match(composer, /create-doctype="YRP Item Attribute Value"/)
	assert.match(composer, /:create-values="\{ attribute_name: attribute \}"/)
	assert.match(composer, /create-value-field="attribute_value"/)
})

test("LinkField footer opens quick entry with presets and commits the created record", async () => {
	const { resolve } = await import("node:path")
	const { Vue, findNodes, loadComponent, mountComponent } = await import("../../scripts/helpers/vue_renderer.mjs")
	const target = await import("../src/utils/linkTarget.js")
	const quickEntry = await import("../src/utils/quickEntry.js")
	const autocompleteKeys = await import("../src/components/common/autocompleteKeys.js")
	const previous = globalThis.window
	const render = (canCreate, props) => {
		globalThis.window = { frappe: { boot: { user: { can_read: [], can_create: canCreate } } } }
		const LinkField = loadComponent(resolve("frontend/src/components/common/LinkField.vue"), {
			"primevue/autocomplete": { setup: (_, { slots, expose }) => { expose({ hide() {} }); return () => Vue.h("autocomplete", {}, slots.footer?.()) } },
			"primevue/button": (attrs) => Vue.h("button", attrs),
			"vue-router": { useRouter: () => undefined },
			"./autocompleteKeys.js": autocompleteKeys,
			"../../utils/linkTarget.js": target,
			"../../utils/quickEntry.js": quickEntry,
			"./asyncQuickEntryDialog.js": (attrs) => Vue.h("quick-entry", attrs),
			"../../api/frappe.js": { invalidatePendingReads() {}, searchLink: async () => [] },
		})
		return mountComponent(LinkField, props)
	}
	const emitted = []
	const props = {
		doctype: "Item Attribute Value",
		createDoctype: "YRP Item Attribute Value",
		createValues: { attribute_name: "Colour" },
		createValueField: "attribute_value",
		"onUpdate:modelValue": (value) => emitted.push(value),
	}
	try {
		const createButtons = (root) => findNodes(root, (node) => node.props?.class === "link-field__create")
		assert.equal(createButtons(render([], props)).length, 0)
		const root = render(["YRP Item Attribute Value"], props)
		const [button] = createButtons(root)
		assert.match(findNodes(button, () => true).map((node) => node.text).join(""), /Create a new YRP Item Attribute Value/)
		button.props.onClick()
		await Vue.nextTick()
		const [dialog] = findNodes(root, (node) => node.type === "quick-entry")
		assert.equal(dialog.props.doctype, "YRP Item Attribute Value")
		assert.deepEqual(dialog.props.presets, { attribute_name: "Colour" })
		dialog.props.onCreated({ doc: { name: "IAV-1", attribute_value: "Navy" }, label: "Navy" })
		assert.deepEqual(emitted, ["Navy"])
		assert.equal(createButtons(render(["YRP Item Attribute Value"], { ...props, cellEditor: true })).length, 0)
	} finally {
		globalThis.window = previous
	}
})
