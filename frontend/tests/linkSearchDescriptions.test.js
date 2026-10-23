import assert from "node:assert/strict"
import { resolve } from "node:path"
import test from "node:test"

import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import * as autocompleteKeys from "../src/components/common/autocompleteKeys.js"
import * as linkTarget from "../src/utils/linkTarget.js"
import * as quickEntry from "../src/utils/quickEntry.js"

const tick = async () => { await new Promise((done) => setImmediate(done)); await Vue.nextTick() }
const lot = { name: "F0325-65", label: "F0325-65", description: "Maze Capri Set R.N.S" }

function mountLinkField(props, searches) {
	const LinkField = loadComponent(resolve("frontend/src/components/common/LinkField.vue"), {
		"primevue/autocomplete": { inheritAttrs: false, setup: (_, { attrs, expose }) => { expose({ hide() {} }); return () => Vue.h("autocomplete", attrs) } },
		"primevue/button": (attrs) => Vue.h("button", attrs),
		"./autocompleteKeys.js": autocompleteKeys,
		"../../utils/linkTarget.js": linkTarget,
		"../../utils/quickEntry.js": quickEntry,
		"./asyncQuickEntryDialog.js": (attrs) => Vue.h("quick-entry", attrs),
		"./DocumentLink.vue": (attrs) => Vue.h("document-link", attrs),
		"../../api/frappe.js": { invalidatePendingReads() {}, searchLink: async (...args) => { searches.push(args); return [lot] } },
	})
	return mountComponent(LinkField, props)
}

test("searchLink asks the server for variants only when the field allows them", async () => {
	const oldWindow = globalThis.window, oldFetch = globalThis.fetch
	const bodies = []
	globalThis.window = { location: { host: "site" }, frappe: { session: { user: "one" } } }
	globalThis.fetch = async (_, options) => { bodies.push(JSON.parse(options.body)); return { ok: true, status: 200, json: async () => ({ message: [] }) } }
	try {
		const { searchLink } = await import("../src/api/frappe.js")
		await searchLink("Item", "polo")
		await searchLink("Item", "polo", {}, 20, false, { allowVariants: true })
		assert.equal("allow_variants" in bodies[0], false)
		assert.equal(bodies[1].allow_variants, 1)
	} finally { globalThis.window = oldWindow; globalThis.fetch = oldFetch }
})

test("LinkField keeps Item variants only for item-variant fields", async () => {
	const previous = globalThis.window
	globalThis.window = { frappe: { boot: { user: { can_read: [], can_create: [] } } } }
	try {
		for (const [props, allowVariants] of [
			[{ doctype: "Item", fieldname: "item", label: "Item" }, false],
			[{ doctype: "Item", fieldname: "item_variant", label: "" }, true],
			[{ doctype: "Item", label: "Cloth Item Variant" }, true],
			[{ doctype: "Item", fieldname: "item", allowVariants: true }, true],
		]) {
			const searches = []
			const root = mountLinkField(props, searches)
			const [autocomplete] = findNodes(root, (node) => node.type === "autocomplete")
			await autocomplete.props.onComplete({ query: "polo" })
			assert.deepEqual(searches[0].at(-1), { allowVariants }, JSON.stringify(props))
		}
	} finally { globalThis.window = previous }
})

test("Lot suggestions render the lot number with its Item on a second line", async () => {
	const previous = globalThis.window
	globalThis.window = { frappe: { boot: { user: { can_read: [], can_create: [] } } } }
	try {
		const searches = []
		const root = mountLinkField({ doctype: "SD YRP Lot", label: "Lot" }, searches)
		const [autocomplete] = findNodes(root, (node) => node.type === "autocomplete")
		await autocomplete.props.onComplete({ query: "maze capri" })
		await tick()
		assert.deepEqual(autocomplete.props.suggestions, [lot])
	} finally { globalThis.window = previous }
})

function mountMultiSelectField(props) {
	const MultiSelectField = loadComponent(resolve("frontend/src/components/common/MultiSelectField.vue"), {
		"primevue/multiselect": {
			inheritAttrs: false,
			setup: (_, { attrs, slots }) => () => Vue.h("multiselect", attrs, attrs.options.map((option) => slots.option({ option }))),
		},
	})
	return mountComponent(MultiSelectField, props)
}

test("MultiSelectField shows and filters by each option's description", () => {
	const root = mountMultiSelectField({ options: [{ label: lot.label, value: lot.name, description: lot.description }] })
	const [select] = findNodes(root, (node) => node.type === "multiselect")
	assert.deepEqual(select.props["filter-fields"], ["label", "description"])
	const [small] = findNodes(root, (node) => node.type === "small")
	assert.equal(small.text || small.children[0]?.text, "Maze Capri Set R.N.S")
	const [strong] = findNodes(root, (node) => node.type === "strong")
	assert.equal(strong.text || strong.children[0]?.text, "F0325-65")
})

test("LinkMultiSelectField searches the server and keeps chosen labels", async () => {
	const searches = []
	const registered = {}
	const MultiSelectFieldStub = { inheritAttrs: false, setup: (_, { attrs }) => () => Vue.h("multi-select-field", attrs) }
	const LinkMultiSelectField = loadComponent(resolve("frontend/src/components/common/LinkMultiSelectField.vue"), {
		"@primevue/core/api": { FilterService: { register: (name, matcher) => { registered[name] = matcher } } },
		"../../api/frappe.js": { searchLink: async (...args) => { searches.push(args); return [lot] } },
		"./MultiSelectField.vue": MultiSelectFieldStub,
	})
	const values = Vue.ref([])
	const root = { node: null }
	root.node = mountComponent({
		render: () => Vue.h(LinkMultiSelectField, {
			doctype: "SD YRP Lot", label: "Lot", delay: 0, modelValue: values.value,
			"onUpdate:modelValue": (next) => { values.value = next },
		}),
	}, {})
	const field = () => findNodes(root.node, (node) => node.type === "multi-select-field")[0]
	assert.equal(field().props["filter-match-mode"], "link-search-server")
	assert.equal(registered["link-search-server"](), true)
	field().props.onFilter({ value: "maze capri" })
	await tick(); await tick()
	assert.deepEqual(searches[0], ["SD YRP Lot", "maze capri", {}, 20, true, { allowVariants: false }])
	assert.deepEqual(field().props.options, [{ value: "F0325-65", label: "F0325-65", description: "Maze Capri Set R.N.S" }])
	field().props["onUpdate:modelValue"](["F0325-65"])
	await tick()
	field().props.onBeforeShow()
	searches.length = 0
	await tick()
	assert.deepEqual(field().props.options.map((option) => option.description), ["Maze Capri Set R.N.S"])
})

test("List view 'in' filters on Link fields use the two-line server-searched multi-select", async () => {
	const { readFile } = await import("node:fs/promises")
	const source = await readFile(resolve("frontend/src/components/common/ListviewFilters.vue"), "utf8")
	assert.match(source, /<LinkMultiSelectField\s+v-else-if="usesMultiValueEditor\(row\) && fieldFor\(row\)\?\.fieldtype === 'Link'"/)
	assert.match(source, /\["Select", "Link"\]\.includes\(fieldFor\(row\)\?\.fieldtype\) && MULTI_CONDITIONS\.has\(row\.operator\)/)
})
