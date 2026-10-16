import assert from "node:assert/strict"
import test from "node:test"

import { Vue, findNodes, loadComponent, mountComponent } from "./helpers/vue_renderer.mjs"

test("print button disables empty formats, opens an available format, and disables again on refresh", async () => {
	const component = loadComponent("frontend/src/components/documents/DocumentPrintButton.vue", {
		"primevue/button": (props) => Vue.h("button", { disabled: props.disabled, onClick: props.onClick }),
		"primevue/menu": () => null,
	})
	const props = Vue.reactive({ doctype: "YRP Production Order", name: "PPO-00001", formats: [] })
	const root = mountComponent(component, props)
	const button = () => findNodes(root, (node) => node.type === "button")[0]
	const opened = []
	const originalWindow = globalThis.window
	globalThis.window = { open: (...args) => opened.push(args) }
	try {
		assert.equal(button().props.disabled, true)
		button().props.onClick()
		assert.equal(opened.length, 0)

		props.formats = [{ label: "Production Order", format: "Essdee Production Order" }]
		await Vue.nextTick()
		assert.equal(button().props.disabled, false)
		button().props.onClick()
		assert.equal(opened.length, 1)
		const url = new URL(opened[0][0], "https://example.test")
		assert.equal(url.pathname, "/printview")
		assert.equal(url.searchParams.get("name"), props.name)
		assert.equal(url.searchParams.get("format"), "Essdee Production Order")

		props.formats = []
		await Vue.nextTick()
		assert.equal(button().props.disabled, true)
		button().props.onClick()
		assert.equal(opened.length, 1)
	} finally {
		if (originalWindow === undefined) delete globalThis.window
		else globalThis.window = originalWindow
	}
})
