import assert from "node:assert/strict"
import test from "node:test"

import { useDocumentPermissions } from "../frontend/src/composables/useDocumentPermissions.js"
import { Vue, findNodes, loadComponent, mountComponent } from "./helpers/vue_renderer.mjs"

test("print button gates formats and opens the print options dialog", async () => {
	const component = loadComponent("frontend/src/components/documents/DocumentPrintButton.vue", {
		"../../composables/useDocumentPermissions.js": { useDocumentPermissions },
		"primevue/button": (props) => Vue.h("button", { disabled: props.disabled, onClick: props.onClick }),
		"./DocumentPrintDialog.vue": (props) => Vue.h("print-dialog", props),
	})
	const props = Vue.reactive({ doctype: "YRP Production Order", name: "PPO-00001", formats: [] })
	const root = mountComponent(component, props)
	const button = () => findNodes(root, node => node.type === "button")[0]
	const dialog = () => findNodes(root, node => node.type === "print-dialog")[0]
	assert.equal(button().props.disabled, true)
	button().props.onClick()
	await Vue.nextTick()
	assert.equal(dialog().props.visible, false)
	props.formats = [{ label: "Production Order", format: "Essdee Production Order" }]
	await Vue.nextTick()
	assert.equal(button().props.disabled, false)
	button().props.onClick()
	await Vue.nextTick()
	assert.equal(dialog().props.visible, true)
	dialog().props["onUpdate:visible"](false)
	props.formats = []
	await Vue.nextTick()
	assert.equal(button().props.disabled, true)
	button().props.onClick()
	await Vue.nextTick()
	assert.equal(dialog().props.visible, false)
})
