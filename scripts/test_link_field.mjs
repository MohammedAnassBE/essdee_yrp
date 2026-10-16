import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import AutoComplete from "../frontend/node_modules/primevue/autocomplete/index.mjs"
import { Vue, findNodes, loadComponent, mountComponent } from "./helpers/vue_renderer.mjs"
import { handleAutocompleteKey, withAutocompleteCompositionGuard } from "../frontend/src/components/common/autocompleteKeys.js"
import * as gridHelpers from "../frontend/src/components/common/entryGrid.js"

const { h, reactive, nextTick } = Vue
const event = (key, target = controls.at(-1)?.$el.querySelector("input"), extra = {}) => ({ key, code: key, defaultPrevented: false, stopped: false, target, ...extra, preventDefault() { this.defaultPrevented = true }, stopPropagation() { this.stopped = true } })
let focusedInputs = 0
const controls = []
const AutoCompleteHost = {
	extends: AutoComplete,
	props: { unstyled: { default: true } },
	mounted() {
		this.$el.querySelector = () => findNodes(this.$el, node => node.type === "input")[0]
		this.$el.querySelector("input").focus = () => { focusedInputs += 1 }
		controls.push(this)
	},
	methods: {
		onKeyDown: AutoComplete.methods.onKeyDown,
		alignOverlay() {}, scrollInView() {},
		hide() { this.overlayVisible = false; this.focusedOptionIndex = -1 },
	},
	render() {
		const children = [h("input", { ref: "focusInput", onKeydown: event => this.onKeyDown(event) })]
		if (this.dropdown) children.push(h("button", { "aria-label": "Show options" }))
		if (!this.suggestions?.length && this.$slots.empty) children.push(...this.$slots.empty())
		return h("autocomplete", {
			value: this.modelValue, suggestions: this.suggestions, focused: this.focusedOptionIndex,
			onType: text => { this.onInput({ target: { value: text } }); clearTimeout(this.searchTimeout) },
			onSearch: text => this.search({}, text, "input"),
			onChange: () => this.onChange({}),
			onPick: index => this.onOptionSelect({}, this.suggestions[index]),
			onBlur: () => this.onBlur({}),
			onClear: () => this.onClearClick({}),
		}, children)
	},
}
const searches = []
const modules = {
	"primevue/autocomplete": AutoCompleteHost,
	"primevue/button": { render: () => h("button") },
	"./autocompleteKeys.js": { handleAutocompleteKey, withAutocompleteCompositionGuard },
	"../../api/frappe.js": { searchLink: async (...args) => { searches.push(args); return ["Knitting", "Knitting second"] } },
	"../../router/webDocumentRoutes.js": { webDocumentPath: (doctype, name) => `${doctype}/${name}` },
}
const LinkField = loadComponent("frontend/src/components/common/LinkField.vue", modules)
const flush = async () => { await nextTick(); await nextTick(); await nextTick() }
function mount(extra = {}) {
	const changes = [], picks = [], clears = []
	const props = reactive({ doctype: "YRP Process", modelValue: "", delay: 0, showOpenButton: false, ...extra,
		"onUpdate:modelValue": value => { changes.push(value); props.modelValue = value },
		onSelect: value => picks.push(value), onClear: () => clears.push(true),
	})
	const root = mountComponent(LinkField, props)
	const control = controls.at(-1)
	const node = () => findNodes(root, value => value.type === "autocomplete")[0]
	const key = async (name, extra = {}) => { const inputEvent = event(name, control.$el.querySelector("input"), extra); root.children[0].props.onKeydownCapture(inputEvent); if (!inputEvent.stopped) inputEvent.target.props.onKeydown(inputEvent); await flush(); return inputEvent }
	const search = async text => { node().props.onType(text); node().props.onSearch(text); await flush() }
	return { root, props, changes, picks, clears, control, node, key, search }
}

const field = mount({ modelValue: null })
await field.search("Knitt")
assert.equal(field.control.forceSelection, false)
assert.equal(field.control.autoOptionFocus, true)
assert.equal(field.control.selectOnFocus, false)
assert.equal(field.control.focusedOptionIndex, 0)
let prevented = false
field.control.pt.option.onMousedown({ preventDefault() { prevented = true } })
assert.ok(prevented, "option mousedown must retain input focus until click")
field.node().props.onChange()
await flush()
assert.deepEqual(field.changes, [], "native change on partial text must never emit a transient clear")
field.node().props.onPick(0)
await flush()
assert.equal(field.props.modelValue, "Knitting")
assert.equal(field.node().props.value.label, "Knitting")
assert.equal(field.picks.length, 1)

await field.search("Knitt")
assert.equal(field.control.focusedOptionIndex, 0)
assert.ok((await field.key("Enter")).stopped)
assert.equal(field.props.modelValue, "Knitting")
await field.search("Knitt")
field.control.onArrowDownKey(event("ArrowDown"))
assert.equal(field.control.focusedOptionIndex, 1)
await field.key("Enter")
assert.equal(field.props.modelValue, "Knitting second")
await field.search("Knitt")
assert.equal(field.control.focusedOptionIndex, 0)
field.control.onOptionMouseMove({}, 1)
assert.equal(field.control.focusedOptionIndex, 1)
field.control.onArrowUpKey(event("ArrowUp"))
assert.equal(field.control.focusedOptionIndex, 0)
await field.key("Tab")
assert.equal(field.props.modelValue, "Knitting")

field.props.searchHandler = async query => query.startsWith("Dye") ? ["Dyeing", "Dyeing second"] : []
await field.search("Dye")
field.node().props.onBlur()
await flush()
assert.equal(field.node().props.value.label, "Knitting")
assert.equal(field.props.modelValue, "Knitting")
await field.search("Dye")
assert.ok((await field.key("Escape")).stopped)
assert.equal(field.control.overlayVisible, false)
assert.equal(field.node().props.value.label, "Knitting")
assert.equal((await field.key("Escape")).stopped, false)
await field.search("zzzznotfound")
const emptyEnter = await field.key("Enter")
assert.ok(emptyEnter.stopped && emptyEnter.defaultPrevented)
assert.equal(field.props.modelValue, "Knitting")
await field.search("Dye")
await field.key("Enter")
assert.equal(field.props.modelValue, "Dyeing")
field.node().props.onType("")
await flush()
assert.equal(field.props.modelValue, "")
assert.equal(field.clears.length, 1)
field.props.modelValue = "Parent value"
await flush()
assert.equal(field.node().props.value.label, "Parent value")
field.node().props.onClear()
await flush()
assert.equal(field.props.modelValue, "")
assert.equal(field.clears.length, 2)

// A rejected source change restores through resetVersion without destroying the control.
field.props.modelValue = "Knitting"
field.props["onUpdate:modelValue"] = value => field.changes.push(value)
await flush()
await field.search("Dye")
field.node().props.onPick(0)
await flush()
assert.equal(field.node().props.value.label, "Dyeing")
field.node().props.onBlur()
await flush()
assert.deepEqual(field.node().props.value, { name: "Knitting", label: "Knitting" })
field.props.resetVersion = 1
await flush()
assert.equal(field.node().props.value.label, "Knitting")
assert.equal(controls.at(-1), field.control)

for (const doctype of ["Supplier", "SD YRP Lot", "Item"]) {
	const rejected = mount({ doctype, modelValue: "A", searchHandler: async () => [{ name: "B", label: "Label B" }] })
	rejected.props["onUpdate:modelValue"] = value => rejected.changes.push(value)
	for (const restore of ["blur", "Escape", "reset"]) {
		await rejected.search("B")
		await rejected.key("Enter")
		assert.equal(rejected.props.modelValue, "A")
		if (restore === "blur") rejected.node().props.onBlur()
		if (restore === "Escape") { await rejected.search("B"); await rejected.key("Escape") }
		if (restore === "reset") rejected.props.resetVersion = 1
		await flush()
		assert.deepEqual(rejected.node().props.value, { name: "A", label: "A" }, `${doctype}: rejected pick restored on ${restore}`)
	}
	// Reset must repair the display even if the input already has the parent's name.
	rejected.control.$emit("update:modelValue", { name: "A", label: "Label B" })
	await flush()
	rejected.props.resetVersion = 2
	await flush()
	assert.deepEqual(rejected.node().props.value, { name: "A", label: "A" })
}

const labelled = mount({ modelValue: "A", searchHandler: async () => [{ name: "B", label: "Label B" }] })
await labelled.search("B")
await labelled.key("Enter")
labelled.node().props.onBlur()
labelled.props.resetVersion = 1
await flush()
assert.deepEqual(labelled.node().props.value, { name: "B", label: "Label B" }, "accepted picks keep their matching label")

field.props.modelValue = "Knitting second"
field.props.searchHandler = null
await flush()
field.control.search({}, "", "dropdown"); await flush()
assert.equal(field.control.focusedOptionIndex, 0, "reopening must highlight the first item even when the committed item is second")
const lot = mount({ doctype: "SD YRP Lot", searchHandler: async () => ["F0926-49", "F0926-490"] })
await lot.search("F0926-4"); lot.node().props.onPick(0); await flush()
assert.equal(lot.props.modelValue, "F0926-49")
await lot.search("F0926-4"); await lot.key("Enter")
assert.equal(lot.props.modelValue, "F0926-49")
const exposed = Vue.ref(null)
const requiredRoot = mountComponent({ render: () => h(LinkField, { ref: exposed, doctype: "Supplier", modelValue: "S-0005", required: true, invalid: true, label: "Supplier", showClear: true, filters: { parent: "" } }) }, {})
const requiredControl = controls.at(-1)
assert.equal(requiredControl.pt.pcInputText.root.required, true)
assert.equal(requiredControl.invalid, true)
assert.equal(requiredControl.showClear, true)
assert.equal(requiredControl.dropdown, true)
assert.equal(requiredControl.modelValue.name, "S-0005")
assert.ok(findNodes(requiredRoot, node => node.text.includes("Select the related field first")).length)
const focusBefore = focusedInputs
exposed.value.focus()
assert.equal(focusedInputs, focusBefore + 1)
assert.ok(findNodes(requiredRoot, node => node.type === "span" && node.props.class === "erp-required-mark").length)
let opened
const openField = mount({ modelValue: "S-0005", showOpenButton: true, openHandler: (...args) => { opened = args } })
await openField.search("Knitt")
const buttons = findNodes(openField.root, node => node.type === "button")
const openButton = buttons.find(node => node.props.onClick)
const dropdownButton = buttons.find(node => node.props["aria-label"] === "Show options")
assert.ok(openButton && dropdownButton)
for (const button of [openButton, dropdownButton]) {
	const enter = event("Enter", button)
	openField.root.children[0].props.onKeydownCapture(enter)
	assert.equal(enter.defaultPrevented, false, "button Enter must retain native activation")
	assert.equal(enter.stopped, false)
	assert.equal(openField.props.modelValue, "S-0005", "button Enter must not pick an option")
}
openButton.props.onClick(event("click", openButton))
assert.deepEqual(opened, ["YRP Process", "S-0005"])
await openField.key("Enter")
assert.equal(openField.props.modelValue, "Knitting", "input Enter must still select the highlighted option")

const composing = mount({ modelValue: "Existing" })
await composing.search("Knitt")
for (const extra of [{ isComposing: true }, { keyCode: 229 }]) {
	for (const key of ["Enter", "Escape"]) {
		const composingEvent = await composing.key(key, extra)
		assert.equal(composingEvent.defaultPrevented, false)
		assert.equal(composingEvent.stopped, false)
		assert.equal(composing.props.modelValue, "Existing")
		assert.equal(composing.control.overlayVisible, true)
		assert.equal(composing.control.focusedOptionIndex, 0)
		assert.equal(composing.node().props.value, "Knitt", "composition must not restore the committed text")
	}
}
await composing.key("Enter")
assert.equal(composing.props.modelValue, "Knitting")

let resolveSearch
const waiting = mount({ modelValue: "Knitting", searchHandler: () => new Promise(resolve => { resolveSearch = resolve }) })
waiting.node().props.onType("Dye")
waiting.node().props.onSearch("Dye")
await flush()
await waiting.key("Escape")
resolveSearch(["Dyeing"])
await flush()
assert.equal(waiting.props.modelValue, "Knitting")
assert.equal(waiting.control.overlayVisible, false)
assert.equal(waiting.node().props.value.label, "Knitting")
// FormField is the DC wrapper; Item Production Detail > Yarn Ratio uses this EntryGrid link column.
const FormField = loadComponent("frontend/src/components/common/FormField.vue", {
	...modules, "./LinkField.vue": LinkField,
	"primevue/inputnumber": {}, "primevue/inputtext": {}, "primevue/select": {}, "primevue/textarea": {}, "primevue/toggleswitch": {},
	"../../utils/documentValues.js": {}, "./DateField.vue": {}, "./DateTimeField.vue": {}, "./TimeField.vue": {},
})
const formProps = reactive({ field: { fieldname: "from_location", fieldtype: "Link", options: "Supplier" }, form: {}, modelValue: "", searchHandler: async () => [{ name: "S-0005", label: "Fabric Store" }], "onUpdate:modelValue": value => { formProps.modelValue = value } })
const formRoot = mountComponent(FormField, formProps)
let input = findNodes(formRoot, node => node.type === "autocomplete")[0]
input.props.onType("Fab"); input.props.onSearch("Fab"); await flush()
findNodes(formRoot, node => node.props.onKeydownCapture)[0].props.onKeydownCapture(event("Enter")); await flush()
assert.equal(formProps.modelValue, "S-0005")
input.props.onType("Fab"); input.props.onSearch("Fab"); await flush(); input.props.onPick(0); await flush()
assert.equal(formProps.modelValue, "S-0005")

formProps.searchHandler = async () => [{ name: "S-0070", label: "Accessories Store" }]
formProps["onUpdate:modelValue"] = () => {}
await flush()
input.props.onType("Acc"); input.props.onSearch("Acc"); await flush(); input.props.onPick(0); await flush()
assert.equal(input.props.value.name, "S-0070")
formProps.resetVersion = 1
await flush()
assert.equal(input.props.value.name, "S-0005")

const EntryGrid = loadComponent("frontend/src/components/common/EntryGrid.vue", { ...modules, "./LinkField.vue": LinkField, "./entryGrid.js": gridHelpers })
const gridProps = reactive({ rows: [{ key: "0", label: "Yarn" }], columns: [{ key: "yarn_item", label: "Yarn item", type: "link", doctype: "Item" }], modelValue: { 0: { yarn_item: "Old yarn" } }, "onUpdate:modelValue": value => { gridProps.modelValue = value } })
const gridRoot = mountComponent(EntryGrid, gridProps)
findNodes(gridRoot, node => node.props.role === "grid")[0].querySelector = () => null
const cell = () => findNodes(gridRoot, node => node.props.role === "gridcell")[0]
cell().props.onDblclick(); await flush()
input = findNodes(gridRoot, node => node.type === "autocomplete")[0]
input.props.onType("Knitt"); input.props.onSearch("Knitt"); await flush()
findNodes(gridRoot, node => node.props.onKeydownCapture)[0].props.onKeydownCapture(event("Enter")); await flush()
assert.equal(gridProps.modelValue[0].yarn_item, "Knitting")
cell().props.onDblclick(); await flush()
input = findNodes(gridRoot, node => node.type === "autocomplete")[0]
input.props.onType("Knitt"); input.props.onSearch("Knitt"); await flush(); input.props.onPick(1); await flush()
assert.equal(gridProps.modelValue[0].yarn_item, "Knitting second")
cell().props.onDblclick(); await flush()
input = findNodes(gridRoot, node => node.type === "autocomplete")[0]
input.props.onType("Dye"); input.props.onSearch("Dye"); await flush()
const escape = event("Escape")
findNodes(gridRoot, node => node.props.onKeydownCapture)[0].props.onKeydownCapture(escape)
assert.ok(escape.stopped)
const closedEscape = event("Escape")
findNodes(gridRoot, node => node.props.onKeydownCapture)[0].props.onKeydownCapture(closedEscape)
findNodes(gridRoot, node => node.props.role === "grid")[0].props.onKeydown(closedEscape)
await flush()
assert.equal(gridProps.modelValue[0].yarn_item, "Knitting second")
assert.equal(findNodes(gridRoot, node => node.type === "autocomplete").length, 0)


const AsyncMulti = loadComponent("frontend/src/departments/cutting/reports/AsyncLinkMultiSelect.vue", {
	...modules,
	"../../../components/common/autocompleteKeys.js": { handleAutocompleteKey, withAutocompleteCompositionGuard },
	"../../../api/frappe.js": { searchLink: async () => [{ name: "Knitting", label: "Knitting" }, { name: "Dyeing", label: "Dyeing" }] },
})
const multiProps = reactive({ modelValue: [], doctype: "YRP Process", label: "Process", "onUpdate:modelValue": value => { multiProps.modelValue = value } })
const multiRoot = mountComponent(AsyncMulti, multiProps)
const multi = controls.at(-1)
let multiInput = findNodes(multiRoot, node => node.type === "autocomplete")[0]
multiInput.props.onSearch("K"); await flush()
assert.equal(multi.focusedOptionIndex, 0)
for (const extra of [{ isComposing: true }, { keyCode: 229 }]) {
	const composingEvent = event("Enter", multi.$el.querySelector("input"), extra)
	findNodes(multiRoot, node => node.props.onKeydownCapture)[0].props.onKeydownCapture(composingEvent)
	if (!composingEvent.stopped) composingEvent.target.props.onKeydown(composingEvent)
	await flush()
	assert.equal(composingEvent.defaultPrevented, false)
	assert.equal(composingEvent.stopped, false)
	assert.deepEqual(multiProps.modelValue, [])
	assert.equal(multi.overlayVisible, true)
}
const chipEnter = event("Enter", { type: "button" })
findNodes(multiRoot, node => node.props.onKeydownCapture)[0].props.onKeydownCapture(chipEnter)
assert.equal(chipEnter.defaultPrevented, false)
assert.equal(chipEnter.stopped, false)
findNodes(multiRoot, node => node.props.onKeydownCapture)[0].props.onKeydownCapture(event("Enter")); await flush()
assert.deepEqual(multiProps.modelValue, ["Knitting"])
multiInput = findNodes(multiRoot, node => node.type === "autocomplete")[0]
multiInput.props.onSearch("D"); await flush()
assert.equal(multi.focusedOptionIndex, 0)
findNodes(multiRoot, node => node.props.onKeydownCapture)[0].props.onKeydownCapture(event("Enter")); await flush()
assert.deepEqual(multiProps.modelValue, ["Knitting", "Dyeing"])

// Existing re-key / busy source handlers are no longer allowed to unmount the selection.
for (const filename of ["WorkOrderEditor", "PurchaseOrderEditor"]) {
	const source = readFileSync(`frontend/src/departments/fabric-store/${filename}.vue`, "utf8")
	assert.doesNotMatch(source, /:key="`(?:process|lot|item|supplier)-\$\{sourceRevision\}/)
	assert.match(source, /:reset-version="sourceRevision"/)
}
console.log("LinkField: real PrimeVue keyboard, highlight, mouse race, wrappers, grid, clear and restore tests passed")
