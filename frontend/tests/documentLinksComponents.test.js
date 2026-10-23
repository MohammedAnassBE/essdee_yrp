import assert from "node:assert/strict"
import test from "node:test"
import { resolve } from "node:path"
import { readFileSync } from "node:fs"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import * as overview from "../src/utils/documentOverview.js"
import * as values from "../src/utils/documentValues.js"
import * as autocompleteKeys from "../src/components/common/autocompleteKeys.js"
import { MERCH_DETAIL_GROUPS } from "../src/departments/merch/lot/merchLotViews.js"

import * as target from "../src/utils/linkTarget.js"
import * as quickEntry from "../src/utils/quickEntry.js"
const nodes = (root, type) => findNodes(root, node => node.type === type)
const text = node => node.text + node.children.map(text).join("")
const tick = async () => { await new Promise(resolve => setImmediate(resolve)); await Vue.nextTick() }
const control = (props, { slots }) => Vue.h("control", props, slots.default?.())
function component(path, push, modules = {}) {
	return loadComponent(resolve(`frontend/src/${path}.vue`), {
		"vue-router": { useRouter: () => push ? { push } : undefined },
		"../../utils/linkTarget.js": target,
		"../../utils/documentOverview.js": overview,
		"../../utils/documentValues.js": values,
		"primevue/button": (props) => Vue.h("button", props),
		...modules,
	})
}
function readable(doctypes, fn) {
	const previous = globalThis.window
	globalThis.window = { frappe: { boot: { user: { can_read: doctypes } } } }
	return Promise.resolve().then(fn).finally(() => { globalThis.window = previous })
}
function click(overrides = {}) {
	return { button: 0, prevented: false, preventDefault() { this.prevented = true }, ...overrides }
}

test("DocumentLink renders encoded anchors, labels, slots and inherited attributes", () => readable(["Item"], () => {
	const link = component("components/common/DocumentLink")
	const root = mountComponent(link, { doctype: "Item", name: "A/B #1?x&y%", label: "Display Item", class: "custom", "aria-label": "Open item", title: "Item title" })
	const anchor = nodes(root, "a")[0]
	assert.equal(anchor.props.href, "/web/purchase/items/A%2FB%20%231%3Fx%26y%25")
	assert.equal(text(anchor), "Display Item")
	assert.ok(anchor.props.class.includes("custom"))
	assert.equal(anchor.props["aria-label"], "Open item")
	assert.equal(anchor.props.title, "Item title")
	const slot = mountComponent({ setup: () => () => Vue.h(link, { doctype: "Item", name: "X" }, { default: () => Vue.h("i", { class: "pi pi-arrow-up-right" }) }) })
	assert.equal(nodes(slot, "a").length, 1)
	assert.equal(nodes(slot, "i").length, 1)
}))

test("DocumentLink keeps unreadable and empty values as spans", () => readable([], () => {
	for (const props of [{ doctype: "Item", name: "X" }, { doctype: "Item", name: "" }, { doctype: "", name: "X" }]) {
		const root = mountComponent(component("components/common/DocumentLink"), props)
		assert.equal(nodes(root, "a").length, 0)
		assert.equal(text(nodes(root, "span")[0]), props.name)
	}
}))

test("DocumentLink pushes only plain left web clicks and preserves native navigation otherwise", () => readable(["SD YRP Lot", "User"], () => {
	const pushed = []
	const root = mountComponent(component("components/common/DocumentLink", route => pushed.push(route)), { doctype: "SD YRP Lot", name: "A/B", currentPath: "/web/merch/lots/L" })
	const anchor = nodes(root, "a")[0], plain = click()
	anchor.props.onClick(plain)
	assert.equal(plain.prevented, true)
	assert.deepEqual(pushed, ["/merch/lots/A%2FB"])
	for (const modifier of [{ ctrlKey: true }, { metaKey: true }, { shiftKey: true }, { altKey: true }, { button: 1 }]) {
		const event = click(modifier); anchor.props.onClick(event); assert.equal(event.prevented, false)
	}
	assert.equal(pushed.length, 1)
	for (const [doctype, push] of [["User", route => pushed.push(route)], ["SD YRP Lot", undefined]]) {
		const native = mountComponent(component("components/common/DocumentLink", push), { doctype, name: "X" })
		const event = click(); nodes(native, "a")[0].props.onClick(event)
		assert.equal(event.prevented, false)
		if (doctype === "User") assert.equal(nodes(native, "a")[0].props.href, "/desk/user/X")
	}
}))

test("DocumentOverview links raw targets while preserving labels and plain fields", () => readable(["User", "Item"], () => {
	const root = mountComponent(component("components/documents/DocumentOverview"), { includeUnclaimed: true, includeEmpty: true, fields: [
		{ fieldname: "person", fieldtype: "Link", options: "User", value: "Person", link_name: "user@example.test" },
		{ fieldname: "data", fieldtype: "Data", value: "Plain" },
		{ fieldname: "private", fieldtype: "Link", options: "Season", value: "Summer" },
		{ fieldname: "empty", fieldtype: "Link", options: "Item", value: "", link_name: "X" },
	] })
	assert.equal(nodes(root, "a").length, 1)
	assert.equal(text(nodes(root, "a")[0]), "Person")
	assert.equal(nodes(root, "a")[0].props.href, "/desk/user/user%40example.test")
	assert.ok(nodes(root, "dd").some(node => text(node) === "Plain"))
}))

test("Merch Lot overview links every requested Link fact using Lot metadata and keeps other types plain", () => {
	const meta = JSON.parse(readFileSync(new URL("../../essdee_yrp/essdee_yrp/doctype/sd_yrp_lot/sd_yrp_lot.json", import.meta.url), "utf8"))
	const values = {
		production_order: ["PPO/1", "/web/merch/production-orders/PPO%2F1"],
		production_detail: ["IPD/1", "/web/merch/item-production-details/IPD%2F1"],
		assigned_person: ["person@example.test", "/desk/user/person%40example.test", "Person"],
		season: ["Summer", "/desk/sd-yrp-product-season/Summer"],
		primary_item_attribute: ["Size", "/desk/item-attribute/Size"],
		uom: ["Nos", "/desk/uom/Nos"],
		pack_in_stage: ["IAV/Stitched", "/desk/yrp-item-attribute-value/IAV%2FStitched", "Stitched"],
		pack_out_stage: ["IAV/Packed", "/desk/yrp-item-attribute-value/IAV%2FPacked", "Packed"],
		packing_uom: ["Box", "/desk/uom/Box"],
		transferred_lot: ["Lot/2", "/web/merch/lots/Lot%2F2"],
		version: ["V3"], capacity_planning: [1], cloth_excess_percentage: [5],
	}
	const fields = Object.entries(values).map(([fieldname, [name, , label]]) => ({
		...meta.fields.find(field => field.fieldname === fieldname), value: label ?? name, ...(label ? { link_name: name } : {}),
	}))
	return readable(fields.filter(field => field.fieldtype === "Link").map(field => field.options), () => {
		const previous = globalThis.location
		globalThis.location = { pathname: "/web/merch/lots/Lot" }
		try {
			const root = mountComponent(component("components/documents/DocumentOverview"), { fields, definitions: MERCH_DETAIL_GROUPS })
			assert.deepEqual(nodes(root, "a").map(node => [text(node), node.props.href]).sort(), Object.values(values).filter(([, href]) => href).map(([name, href, label]) => [label ?? name, href]).sort())
			assert.equal(nodes(root, "dd").length, fields.length)
		} finally { globalThis.location = previous }
	})
})

function linkField(props, push) {
	return mountComponent(component("components/common/LinkField", push, {
		"primevue/autocomplete": { setup: () => () => Vue.h("input") },
		"./autocompleteKeys.js": autocompleteKeys,
		"../../utils/quickEntry.js": quickEntry,
		"./asyncQuickEntryDialog.js": () => null,
		"../../api/frappe.js": { invalidatePendingReads() {}, searchLink: async () => [] },
	}), props)
}

test("LinkField open icon gates read access, uses document navigation and keeps custom handlers", async () => {
	await readable(["Item", "User"], () => {
		const pushed = [], root = linkField({ doctype: "Item", modelValue: "A/B" }, route => pushed.push(route))
		const anchor = nodes(root, "a")[0]
		assert.ok(anchor)
		assert.equal(anchor.props["aria-label"], "Open A/B")
		assert.equal(anchor.props.title, "Open A/B")
		assert.equal(nodes(anchor, "i")[0].props.class, "pi pi-arrow-up-right")
		anchor.props.onClick(click()); anchor.props.onClick(click({ ctrlKey: true }))
		assert.deepEqual(pushed, ["/purchase/items/A%2FB"])
		assert.equal(nodes(linkField({ doctype: "User", modelValue: "U" }), "a")[0].props.href, "/desk/user/U")
		for (const props of [{ doctype: "Item", modelValue: "" }, { doctype: "Item", modelValue: "X", showOpenButton: false }]) assert.equal(nodes(linkField(props), "a").length, 0)
		const called = [], custom = linkField({ doctype: "Item", modelValue: "X", openHandler: (...args) => called.push(args) })
		nodes(custom, "button")[0].props.onClick(click())
		assert.deepEqual(called, [["Item", "X"]])
		assert.equal(nodes(custom, "a").length, 0)
	})
	await readable([], () => {
		const root = linkField({ doctype: "Item", modelValue: "X" })
		assert.equal(nodes(root, "a").length, 0)
		assert.equal(nodes(root, "button").length, 0)
	})
})

test("FormView read mode resolves Dynamic Link records and gates links", () => readable(["Item"], async () => {
	const root = mountComponent(component("components/common/FormView", undefined, {
		"primevue/column": control, "primevue/datatable": control, "primevue/message": control, "primevue/skeleton": control,
		"./ChildTableField.vue": control, "./FormField.vue": control, "../documents/DocumentErrorDialog.vue": control, "../navigation/InlinePageNavigation.vue": control,
		"../../api/frappe.js": {
			getMeta: async () => [{ name: "Test", fields: [
				{ fieldname: "item", fieldtype: "Link", options: "Item" },
				{ fieldname: "against_id", fieldtype: "Dynamic Link", options: "against" },
				{ fieldname: "user", fieldtype: "Link", options: "User" },
				{ fieldname: "empty", fieldtype: "Link", options: "Item" },
			] }],
			getDoc: async () => ({ name: "D", item: "A/B", against: "Item", against_id: "Dynamic", user: "Private", empty: "" }),
			createDoc() {}, updateDoc() {},
		},
	}), { doctype: "Test", name: "D", readonly: true })
	await tick()
	assert.deepEqual(nodes(root, "a").map(node => node.props.href), ["/web/purchase/items/A%2FB", "/web/purchase/items/Dynamic"])
}))

for (const department of ["purchase", "planning"]) {
	test(`${department} LotIdentity links the header Item with unchanged display text`, () => readable(["Item"], () => {
		const root = mountComponent(component(`departments/${department}/lot/LotIdentity`, undefined, {
			"../../../components/documents/DocumentStatusBadge.vue": control,
		}), { name: "LOT", item: "A/B", headingId: "lot-title" })
		assert.equal(nodes(root, "a")[0].props.href, "/web/purchase/items/A%2FB")
		assert.equal(text(nodes(root, "a")[0]), "A/B")
	}))
}
