import { createRequire } from "node:module"
import { readFileSync } from "node:fs"
import { dirname, resolve } from "node:path"

const require = createRequire(new URL("../../frontend/package.json", import.meta.url))
export const Vue = require("vue")
const { parse, compileScript } = require("@vue/compiler-sfc")
// Pure display helpers every component may import; resolved to the real module by default.
const sharedModules = {
	"dateFormat.js": await import("../../frontend/src/utils/dateFormat.js"),
	"listClickFilters.js": await import("../../frontend/src/components/common/listClickFilters.js"),
	"listDateRangeFilters.js": await import("../../frontend/src/components/common/listDateRangeFilters.js"),
	"newDocumentDefaults.js": await import("../../frontend/src/utils/newDocumentDefaults.js"),
	// Tab titles need the app router; components under test only report them.
	"usePageTitle.js": { usePageTitle() {} },
	// The activity footer loads its own data; tests that cover it pass the real component explicitly.
	"DocumentActivity.vue": () => null,
	// Template-only placeholder (no <script>); rendered as a marker node.
	"ListPageSkeleton.vue": () => Vue.h("list-page-skeleton"),
	"documentShortcuts.js": await import("../../frontend/src/utils/documentShortcuts.js"),
	// Keyboard shortcuts bind to window; tests that cover them pass the real composable explicitly.
	"useDocumentShortcuts.js": { useDocumentShortcuts() {} },
}
const sharedModule = (specifier) => sharedModules[specifier.split("/").pop()]

// Compile the real SFCs, substituting only platform controls and API calls.
export function loadComponent(filename, modules) {
	const path = resolve(filename)
	const { descriptor } = parse(readFileSync(path, "utf8"), { filename: path })
	const compiled = compileScript(descriptor, { id: path, inlineTemplate: true, templateOptions: { compilerOptions: { hoistStatic: false } } })
	const dependencies = { vue: Vue, ...modules }
	const source = compiled.content.replace(/^import\s+["'][^"']+\.css["'];?$/gm, "").replace(/import\s+([\s\S]*?)\s+from\s+["']([^"']+)["'];?/g, (_, names, specifier) => {
		if (!(specifier in dependencies) && sharedModule(specifier)) dependencies[specifier] = sharedModule(specifier)
		if (!(specifier in dependencies)) {
			if (!specifier.endsWith(".vue")) throw new Error(`Missing test module: ${specifier}`)
			dependencies[specifier] = loadComponent(resolve(dirname(path), specifier), modules)
		}
		const binding = names.startsWith("{") ? names.replace(/\bas\b/g, ":") : names.replace(/^\*\s+as\s+/, "")
		return `const ${binding} = modules[${JSON.stringify(specifier)}];`
	}).replace("export default", "return")
	return new Function("modules", source)(dependencies)
}

function node(type, text = "") {
	const listeners = {}
	return {
		type, text, props: {}, children: [], parent: null, listeners,
		getRootNode() { return this.parent ? this.parent.getRootNode() : this },
		addEventListener: (event, handler) => { (listeners[event] ||= []).push(handler) },
		removeEventListener: (event, handler) => { listeners[event] = (listeners[event] || []).filter(item => item !== handler) },
	}
}

export function typeInto(element, value) {
	element.value = String(value)
	for (const handler of element.listeners.input || []) handler({ target: element })
	element.props.onInput?.({ target: element })
}

export function createTestRenderer() {
	return Vue.createRenderer({
		createElement: node,
		createText: text => node("text", text),
		createComment: text => node("comment", text),
		setText: (element, text) => { element.text = text },
		setElementText: (element, text) => { element.text = text },
		parentNode: element => element.parent,
		nextSibling: element => element.parent?.children[element.parent.children.indexOf(element) + 1],
		patchProp: (element, key, previous, value) => { element.props[key] = value },
		insert(element, parent, anchor = null) {
			if (element.parent) element.parent.children.splice(element.parent.children.indexOf(element), 1)
			element.parent = parent
			const index = anchor ? parent.children.indexOf(anchor) : -1
			parent.children.splice(index < 0 ? parent.children.length : index, 0, element)
		},
		remove(element) {
			element.parent.children.splice(element.parent.children.indexOf(element), 1)
			element.parent = null
		},
	})
}

export function findNodes(root, predicate) {
	return [root, ...root.children.flatMap(child => findNodes(child, predicate))].filter(predicate)
}

export function mountComponent(component, props) {
	const root = node("root")
	const renderer = createTestRenderer()
	renderer.createApp({ render: () => Vue.h(component, props) }).mount(root)
	return root
}
