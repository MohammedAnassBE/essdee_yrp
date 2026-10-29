import assert from "node:assert/strict"
import test from "node:test"
import { resolve } from "node:path"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import * as ipdEditor from "../src/departments/merch/ipd/ipdEditor.js"
import { canCreateDoctype } from "../src/utils/linkTarget.js"

const LinkField = Vue.defineComponent({
	inheritAttrs: false,
	setup(_, { attrs, expose }) { expose({ focus() {} }); return () => Vue.h("link-field", attrs) },
})
const tick = async () => { await new Promise((done) => setImmediate(done)); await Vue.nextTick() }

async function chips() {
	const key = Symbol("ipd"), calls = []
	const props = Vue.reactive({ attribute: "Size", values: ["S", "M"], editable: true })
	const component = loadComponent(resolve("frontend/src/departments/merch/ipd/sections/IpdAttributeChips.vue"), {
		"primevue/button": (buttonProps) => Vue.h("button", buttonProps),
		"../../../../api/purchase.js": { searchItemAttributeValues: async () => [] },
		"../../../../components/common/LinkField.vue": LinkField,
		"../../../../components/documents/DocumentConfirmationDialog.vue": () => null,
		"../../../../components/common/useChipReorder.js": { useChipReorder: () => ({ chipProps: () => ({}) }) },
		"../ipdEditor.js": ipdEditor, "../useIpdEditor.js": { IPD_EDITOR_KEY: key },
	})
	const root = mountComponent({ setup() {
		Vue.provide(key, { saveAttributeValues: async (...args) => { calls.push(args) }, valueUsage: async () => ({}) })
		return () => Vue.h(component, props)
	} })
	return { link: findNodes(root, (node) => node.type === "link-field")[0], calls }
}

test("IPD value picker creates missing values as YRP Item Attribute Value for the chip's attribute", async () => {
	const { link, calls } = await chips()
	assert.equal(link.props["create-doctype"], "YRP Item Attribute Value")
	assert.deepEqual(link.props["create-values"], { attribute_name: "Size" })
	assert.equal(link.props["create-value-field"], "attribute_value")
	await link.props.onSelect({ name: "XXL", label: "XXL" })
	await tick()
	assert.deepEqual(calls, [["Size", ["S", "M", "XXL"]]])
})

test("the Create option follows create permission on YRP Item Attribute Value", () => {
	assert.equal(canCreateDoctype("YRP Item Attribute Value", { user: { can_create: ["YRP Item Attribute Value"] } }), true)
	assert.equal(canCreateDoctype("YRP Item Attribute Value", { user: { can_create: ["Item"] } }), false)
})
