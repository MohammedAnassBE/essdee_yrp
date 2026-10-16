import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import AutoComplete from "../frontend/node_modules/primevue/autocomplete/index.mjs"
import { Vue, createTestRenderer, findNodes, loadComponent, mountComponent } from "./helpers/vue_renderer.mjs"
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
let gridSearchHandler = null
const modules = {
	"primevue/autocomplete": AutoCompleteHost,
	"primevue/button": { render: () => h("button") },
	"./autocompleteKeys.js": { handleAutocompleteKey, withAutocompleteCompositionGuard },
	"../../api/frappe.js": { searchLink: async (...args) => { searches.push(args); return gridSearchHandler ? gridSearchHandler(...args) : args[1] === "ZZ no such item qq" ? [] : ["Knitting", "Knitting second"] } },
	"../../router/webDocumentRoutes.js": { webDocumentPath: (doctype, name) => `${doctype}/${name}` },
}
const LinkField = loadComponent("frontend/src/components/common/LinkField.vue", modules)
const flush = async () => { await nextTick(); await nextTick(); await nextTick() }
{
	const reference = Vue.ref(null)
	const queries = []
	const root = mountComponent(LinkField, { ref: reference, doctype: "Colour", modelValue: "Black", searchHandler: async query => {
		queries.push(query)
		return [{ name: "Blue", label: "Blue" }, { name: "Black", label: "Black" }]
	} })
	const control = controls.at(-1)
	await reference.value.open("bl")
	await flush()
	assert.deepEqual(queries, ["bl"])
	assert.equal(findNodes(root, node => node.type === "autocomplete")[0].props.value, "bl")
	assert.equal(control.overlayVisible, true)
	assert.equal(control.focusedOptionIndex, 0)
	assert.equal(control.suggestions[0].name, "Blue")
	let selected = false
	control.$el.querySelector("input").select = () => { selected = true }
	await reference.value.open()
	assert.equal(queries.at(-1), "")
	assert.equal(selected, true, "empty-query open selects the current input text")
}
for (const validate of [false, true]) {
	const reference = Vue.ref(null)
	const root = mountComponent(LinkField, { ref: reference, doctype: "Sequence", cellEditor: true,
		searchHandler: async () => [10, 20].map((name) => ({ name, label: name })),
	})
	const control = findNodes(root, node => node.type === "autocomplete")[0]
	control.props.onType("20")
	control.props.onSearch("20")
	await flush()
	assert.equal(reference.value.finishEdit({ validate }), 20, "typed numeric choices retain their numeric name")
}
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

// Invalidate at the keystroke, before the next debounced search even starts.
function deferred() {
	let resolve, reject
	const promise = new Promise((yes, no) => { resolve = yes; reject = no })
	return { promise, resolve, reject }
}
for (const oldResult of ["success", "failure"]) {
	const oldSearch = deferred(), currentSearch = deferred()
	const race = mount({ modelValue: "Original", searchHandler: query => query === "Knitt" ? oldSearch.promise : currentSearch.promise })
	await race.search("Knitt")
	race.node().props.onType("Dye"); await flush()
	assert.deepEqual(race.control.suggestions, [], "typing clears old suggestions during the debounce gap")
	assert.equal(race.control.focusedOptionIndex, -1)
	if (oldResult === "success") oldSearch.resolve(["Knitting"])
	else oldSearch.reject(new Error("obsolete search failed"))
	await flush()
	assert.deepEqual(race.control.suggestions, [], "a superseded response cannot repopulate the list")
	assert.equal(race.node().props.value, "Dye")
	await race.key("Enter")
	assert.equal(race.props.modelValue, "Original", "Enter must not pick the old query's first result")
	assert.doesNotMatch(findNodes(race.root, node => node.props.role === "alert").map(node => node.text).join(""), /obsolete search failed/)
	race.node().props.onSearch("Dye"); await flush()
	await race.key("Enter")
	assert.equal(race.props.modelValue, "Original", "Enter must wait for current results")
	currentSearch.resolve(["Dyeing"]); await flush()
	assert.equal(race.control.focusedOptionIndex, 0, "current results still highlight the first option")
	await race.key("Enter")
	assert.equal(race.props.modelValue, "Dyeing")
}
const stalePick = mount({ modelValue: "Original" })
await stalePick.search("Knitt")
const obsoleteOption = stalePick.control.suggestions[0]
stalePick.node().props.onType("Dye")
// A click/Tab selection already queued by PrimeVue must also fail the token check.
stalePick.control.onOptionSelect({}, obsoleteOption); await flush()
assert.equal(stalePick.props.modelValue, "Original")
assert.deepEqual(stalePick.control.suggestions, [])
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

const EntryGrid = loadComponent("frontend/src/components/common/EntryGrid.vue", { ...modules, vue: { ...Vue, withDirectives: node => node }, "./LinkField.vue": LinkField, "./entryGrid.js": gridHelpers })
function mountChoiceGrid(extra = {}) {
	const batches = [], updates = [], focused = []
	const props = reactive({ rows: [{ key: "front", label: "Front" }, { key: "locked", label: "Locked", readonly: true }],
		columns: [{ key: "colour", label: "Colour", type: "select", options: ["Black", "Blue"], fill: true }, { key: "weight", label: "Weight", type: "number", min: 0, fill: true }],
		modelValue: { front: { colour: "Blue", weight: 1 }, locked: { colour: "Black", weight: 2 } },
		...extra, "onUpdate:modelValue": value => { updates.push(value); props.modelValue = value }, onChange: changes => batches.push(changes),
	})
	const root = mountComponent(EntryGrid, props)
	const cells = () => findNodes(root, node => node.props.role === "gridcell")
	const cell = (index = 0) => cells()[index]
	const table = findNodes(root, node => node.props.role === "grid")[0]
	for (const element of cells()) element.focus = () => focused.push(element.props["data-col"])
	table.querySelector = selector => cells().find(node => selector.includes(`data-row="${node.props["data-row"]}"`) && selector.includes(`data-col="${node.props["data-col"]}"`))
	const input = () => findNodes(root, node => node.type === "autocomplete")[0]
	const key = async (name, extra = {}) => {
		const pressed = event(name, undefined, extra)
		if (input()) {
			findNodes(root, node => String(node.props.class).includes("common-field"))[0].props.onKeydownCapture(pressed)
			if (!pressed.stopped) pressed.target.props.onKeydown(pressed)
		}
		if (!pressed.stopped) table.props.onKeydown(pressed)
		await flush()
		return pressed
	}
	return { props, root, cell, table, input, key, batches, updates, focused }
}
{
	const previousWindow = globalThis.window
	globalThis.window = { addEventListener() {}, removeEventListener() {} }
	const grid = mountChoiceGrid()
	grid.cell().props.onMousedown(event("", null, { button: 0 }))
	await flush()
	assert.equal(grid.input(), undefined, "mousedown retains selection without opening")
	grid.cell().props.onClick(event("", null, { button: 0 }))
	await flush()
	assert.deepEqual(controls.at(-1).suggestions.map(({ name }) => name), ["Black", "Blue"])
	assert.equal(controls.at(-1).overlayVisible, true)
	assert.equal(controls.at(-1).focusedOptionIndex, 0)
	assert.equal(findNodes(grid.root, node => ["select", "datalist"].includes(node.type)).length, 0)
	await grid.key("Enter")
	assert.equal(grid.props.modelValue.front.colour, "Black")
	assert.equal(grid.cell().props.tabindex, 0, "Enter commits without moving")
	assert.equal(grid.focused.at(-1), 0)
	await grid.key("ArrowRight")
	assert.equal(grid.cell(1).props.tabindex, 0)
	await grid.key("ArrowLeft")
	await grid.key("b")
	assert.equal(grid.input().props.value, "b", "printable input becomes the search query")
	assert.equal(grid.props.modelValue.front.colour, "Black", "the query never becomes the committed model")
	controls.at(-1).onArrowDownKey(event("ArrowDown"))
	assert.equal(controls.at(-1).focusedOptionIndex, 1)
	controls.at(-1).onArrowUpKey(event("ArrowUp"))
	await grid.key("Enter")
	assert.equal(grid.props.modelValue.front.colour, "Blue")
	await grid.key("F2")
	assert.equal(controls.at(-1).suggestions.length, 2)
	await grid.key("Escape")
	assert.equal(grid.input(), undefined, "Escape cancels editing in one keypress")
	await grid.key("F2")
	grid.input().props.onType("Bl"); grid.input().props.onSearch("Bl"); await flush()
	await grid.key("Tab")
	assert.equal(grid.props.modelValue.front.colour, "Blue", "Tab rejects a partial match")
	assert.equal(grid.cell(1).props.tabindex, 0)
	await grid.key("ArrowLeft")
	await grid.key("F2")
	grid.input().props.onType("Black"); grid.input().props.onSearch("Black"); await flush()
	await grid.key("Tab")
	assert.equal(grid.props.modelValue.front.colour, "Black", "Tab commits an exact match")
	assert.equal(grid.cell(1).props.tabindex, 0)
	for (const modifier of ["shiftKey", "ctrlKey", "metaKey"]) {
		grid.cell().props.onClick(event("", null, { button: 0, [modifier]: true }))
		await flush()
		assert.equal(grid.input(), undefined)
	}
	grid.cell().props.onMousedown(event("", null, { button: 0 }))
	grid.cell(1).props.onMouseenter()
	grid.cell().props.onClick(event("", null, { button: 0 }))
	await flush()
	assert.equal(grid.input(), undefined, "dragging across cells never opens a choice editor")
	for (const extra of [{ readonly: true }, { rows: [{ key: "front", readonly: true }] }, { columns: [{ key: "colour", type: "value", readonly: true }] }]) {
		const locked = mountChoiceGrid(extra)
		locked.cell().props.onClick(event("", null, { button: 0 }))
		await locked.key("F2")
		assert.equal(locked.input(), undefined)
	}
	globalThis.window = previousWindow
}
{
	for (const type of ["value", "link"]) {
		const grid = mountChoiceGrid({ columns: [{ key: "colour", label: "Colour", type, options: [{ value: "BL", label: "Blue" }, { value: "BK", label: "Black" }] }] })
		grid.cell().props.onClick(event("", null, { button: 0 })); await flush()
		assert.deepEqual(controls.at(-1).suggestions.map(({ name }) => name), ["BL", "BK"])
		grid.input().props.onPick(0); await flush()
		assert.equal(grid.props.modelValue.front.colour, "BL")
	}
}
{
	const columns = [{ key: "colour", label: "Colour", type: "select", options: Array.from({ length: 60 }, (_, index) => `Colour ${index}`) }]
	const grid = mountChoiceGrid({ columns })
	const heading = findNodes(grid.root, node => node.props.role === "columnheader")[1]
	assert.equal(heading.text, "Colour", "ordinary headers retain their plain labels")
	grid.cell().props.onClick(event("", null, { button: 0 })); await flush()
	assert.equal(controls.at(-1).suggestions.length, 60, "large option sets expose every local option")
	assert.equal(findNodes(grid.root, node => ["select", "datalist"].includes(node.type)).length, 0)
	const queries = []
	const custom = mountChoiceGrid({ columns: [{ ...columns[0], type: "link", searchHandler: query => { queries.push(query); return ["Colour 59"] } }] })
	custom.cell().props.onClick(event("", null, { button: 0 })); await flush()
	assert.deepEqual(queries, [""])
	assert.deepEqual(controls.at(-1).suggestions.map(({ name }) => name), ["Colour 59"], "custom link search takes precedence over options")
	const server = mountChoiceGrid({ columns: [{ key: "colour", label: "Colour", type: "link", doctype: "Item", filters: { disabled: 0 } }] })
	server.cell().props.onClick(event("", null, { button: 0 })); await flush()
	assert.deepEqual(searches.at(-1).slice(0, 3), ["Item", "", { disabled: 0 }], "server links retain their filters")
}
{
	const grid = mountChoiceGrid()
	const button = label => findNodes(grid.root, node => node.type === "button" && node.props.label === label)[0]
	const fill = async label => { findNodes(grid.root, node => node.props["aria-label"] === `Fill ${label}` && node.type === "button")[0].props.onClick(); await flush() }
	await fill("Colour")
	assert.equal(controls.at(-1).overlayVisible, true)
	grid.input().props.onPick(0); await flush()
	assert.equal(grid.props.modelValue.front.colour, "Black")
	assert.equal(grid.props.modelValue.locked.colour, "Black")
	assert.equal(grid.batches.length, 1)
	assert.equal(grid.updates.length, 1)
	assert.deepEqual(grid.batches[0], [{ rowKey: "front", colKey: "colour", value: "Black" }])
	assert.ok(findNodes(grid.root, node => node.text === "Filled 1 rows").length)
	await fill("Weight")
	let input = findNodes(grid.root, node => node.type === "input" && node.props["aria-label"] === "Fill Weight")[0]
	assert.equal(input.props.inputmode, "decimal")
	input.props["onUpdate:modelValue"]("oops")
	button("Apply").props.onClick(); await flush()
	assert.ok(findNodes(grid.root, node => node.props.role === "alert" && /not a number/.test(node.text)).length)
	assert.equal(grid.batches.length, 1)
	input.props["onUpdate:modelValue"]("1.25")
	input.props.onKeydown(event("Enter")); await flush()
	assert.equal(grid.props.modelValue.front.weight, 1.25)
	assert.equal(grid.props.modelValue.locked.weight, 2)
	assert.equal(grid.batches.length, 2)
	await fill("Weight")
	button("Apply").props.onClick(); await flush()
	assert.equal(grid.props.modelValue.front.weight, null, "empty Fill clears the column")
	await fill("Colour")
	grid.input().props.onType("invalid"); grid.input().props.onSearch("invalid"); await flush()
	button("Apply").props.onClick(); await flush()
	assert.equal(grid.batches.length, 3, "unselected choice text must never fill blanks")
	assert.ok(findNodes(grid.root, node => node.props.role === "alert").length)
	button("Cancel").props.onClick(); await flush()
	assert.equal(grid.input(), undefined)
	await fill("Weight")
	const header = findNodes(grid.root, node => node.props.class === "entry-grid__fill")[0]
	header.props.onKeydownCapture(event("Escape")); await flush()
	assert.equal(findNodes(grid.root, node => node.props.class === "entry-grid__fill").length, 0)
	assert.equal(grid.batches.length, 3, "Escape cancels Fill")
}
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


// Invalid Link text must be explained after Enter and after blur in every wrapper.
for (const [doctype, expected] of [
	["Item", 'No Item matches "zzz". Pick one from the list.'],
	["", 'No option matches "zzz". Pick one from the list.'],
]) {
	const noMatch = mount({ doctype, searchHandler: async () => [] })
	await noMatch.search("zzz")
	await noMatch.key("Enter")
	assert.ok(findNodes(noMatch.root, node => node.props.role === "alert" && node.text === expected).length)
}

const invalidLink = mount({ modelValue: "Knitting", searchHandler: async () => [] })
await invalidLink.search("zzqq nothing")
await invalidLink.key("Enter")
const processError = 'No YRP Process matches "zzqq nothing". Pick one from the list.'
assert.ok(findNodes(invalidLink.root, node => node.props.role === "alert" && node.text === processError).length)
assert.equal(invalidLink.control.invalid, true)
assert.match(invalidLink.control.pt.pcInputText.root["aria-describedby"], /link-error/)
invalidLink.node().props.onBlur(); await flush()
assert.equal(invalidLink.props.modelValue, "Knitting")
assert.ok(findNodes(invalidLink.root, node => node.text === processError).length, "blur must retain the explanation after restoring the prior value")
await invalidLink.search("try again")
assert.equal(findNodes(invalidLink.root, node => node.props.role === "alert").length, 0, "typing clears the previous error")
await invalidLink.key("Escape")
assert.equal(findNodes(invalidLink.root, node => node.props.role === "alert").length, 0)
invalidLink.props.searchHandler = async () => ["Dyeing"]
await flush()
await invalidLink.search("Dye"); await invalidLink.key("Enter")
assert.equal(invalidLink.props.modelValue, "Dyeing")
assert.equal(invalidLink.control.invalid, false)

formProps.searchHandler = async () => []
await flush()
input = findNodes(formRoot, node => node.type === "autocomplete")[0]
input.props.onType("zzqq nothing"); input.props.onSearch("zzqq nothing"); await flush()
input.props.onBlur(); await flush()
assert.equal(formProps.modelValue, "S-0005")
assert.ok(findNodes(formRoot, node => node.props.class === "form-field__error" && node.text === 'No Supplier matches "zzqq nothing". Pick one from the list.').length)
assert.equal(controls.find(control => control.$el === input).invalid, true)
assert.match(controls.find(control => control.$el === input).pt.pcInputText.root["aria-describedby"], /-error/)
formProps.resetVersion += 1; await flush()
assert.equal(findNodes(formRoot, node => node.props.class === "form-field__error").length, 0)

// Use the Item BOM Link-cell configuration, including the grid's invalid registry.
const invalidCounts = new Map()
const invalidGridRoot = { type: "root", text: "", props: {}, children: [] }
const invalidGridProps = reactive({ rows: [{ key: "bom-1", label: "1" }], columns: [{ key: "item", label: "Item", type: "link", doctype: "Item" }], modelValue: { "bom-1": { item: "Original" } }, "onUpdate:modelValue": value => { invalidGridProps.modelValue = value } })
const invalidGridApp = createTestRenderer().createApp({
	setup() {
		Vue.provide(gridHelpers.ENTRY_GRID_INVALID_KEY, { report: (key, count) => invalidCounts.set(key, count), remove: key => invalidCounts.delete(key) })
		return () => h(EntryGrid, invalidGridProps)
	},
})
invalidGridApp.mount(invalidGridRoot)
const invalidTable = findNodes(invalidGridRoot, node => node.props.role === "grid")[0]
invalidTable.querySelector = () => null
const invalidCell = () => findNodes(invalidGridRoot, node => node.props.role === "gridcell")[0]
invalidCell().props.onDblclick(); await flush()
input = findNodes(invalidGridRoot, node => node.type === "autocomplete")[0]
input.props.onType("ZZ no such item qq"); input.props.onSearch("ZZ no such item qq"); await flush()
findNodes(invalidGridRoot, node => node.props.onKeydownCapture)[0].props.onKeydownCapture(event("Enter")); await flush()
const itemError = 'No Item matches "ZZ no such item qq". Pick one from the list.'
assert.equal(invalidCell().props["aria-invalid"], true)
assert.equal(invalidCell().props.title, itemError)
assert.ok(findNodes(invalidGridRoot, node => node.props["aria-live"] === "polite" && node.text === itemError).length)
assert.equal([...invalidCounts.values()].reduce((sum, count) => sum + count, 0), 1)
assert.equal(invalidGridProps.modelValue["bom-1"].item, "Original")
input.props.onBlur(); await flush()
assert.ok(findNodes(invalidGridRoot, node => node.text === itemError).length)
input.props.onType("Knitt"); input.props.onSearch("Knitt"); await flush()
findNodes(invalidGridRoot, node => node.props.onKeydownCapture)[0].props.onKeydownCapture(event("Enter")); await flush()
assert.equal(invalidGridProps.modelValue["bom-1"].item, "Knitting")
assert.equal([...invalidCounts.values()].reduce((sum, count) => sum + count, 0), 0)

// Mount the actual tab-switch finish handler around the real grid and LinkField.
// The stub supplies only tab layout/routing; before-change runs production code.
const route = reactive({ hash: "#cutting_tab", query: {} })
const IpdSections = loadComponent("frontend/src/departments/merch/ipd/IpdSections.vue", {
	"primevue/usetoast": { useToast: () => ({ add() {} }) },
	"vue-router": { useRoute: () => route, useRouter: () => ({ replace() {} }) },
	"../../../router/listDocumentNavigation.js": { preserveListNavigationState: () => ({}) },
	"./ipdSectionRegistry.js": { preloadSectionComponents() {}, sectionComponent: () => ({ render: () => null }) },
	"./ipdTabs.js": { visibleTabs: tabs => tabs, resolveTab: (_tabs, key) => key, preloadSectionKeys: () => [] },
	"./ipdFocus.js": { focusElement: () => false, GRID_FOCUS_PART: {} },
	"./IpdTabs.vue": {
		props: ["modelValue"], emits: ["before-change", "update:modelValue"],
		setup(_props, { emit }) {
			return () => h("tabs", { onSwitch: () => emit("before-change") }, [h("panel", { role: "tabpanel" }, [h(EntryGrid, invalidGridProps)])])
		},
	},
})
const switchRoot = { type: "root", text: "", props: {}, children: [] }
const switchApp = createTestRenderer().createApp({
	setup() {
		Vue.provide(gridHelpers.ENTRY_GRID_INVALID_KEY, { report: (key, count) => invalidCounts.set(key, count) })
		return () => h(IpdSections, { tabs: [], doc: {} })
	},
})
switchApp.mount(switchRoot)
const switchPanel = findNodes(switchRoot, node => node.props.role === "tabpanel")[0]
const switchGrid = findNodes(switchRoot, node => node.props.role === "grid")[0]
const switchCell = () => findNodes(switchRoot, node => node.props.role === "gridcell")[0]
switchRoot.children[0].querySelector = () => switchPanel
switchPanel.querySelectorAll = () => [switchGrid]
switchPanel.contains = () => false // the tab already received focus on native mousedown
switchGrid.querySelector = () => null
switchGrid.dispatchEvent = event => switchGrid.props.onEntryGridFinishEdit(event)
const beforeSwitchDocument = globalThis.document
globalThis.document = { activeElement: null }
const switchTabs = findNodes(switchRoot, node => node.type === "tabs")[0]
const assertFinished = (expected) => {
	assert.equal(invalidGridProps.modelValue["bom-1"].item, expected)
	assert.equal(switchCell().props["aria-invalid"], undefined)
	assert.equal(switchCell().props.title, undefined)
	assert.equal(findNodes(switchRoot, node => node.type === "autocomplete").length, 0)
	assert.equal([...invalidCounts.values()].reduce((sum, count) => sum + count, 0), 0, "Save must not remain blocked")
	assert.equal(findNodes(switchCell(), node => node.text === expected).length, 1)
}
for (const blurFirst of [false, true]) {
	invalidGridProps.modelValue = { "bom-1": { item: "Thermal Fabric" } }; await flush()
	switchCell().props.onDblclick(); await flush()
	input = findNodes(switchRoot, node => node.type === "autocomplete")[0]
	input.props.onType("Thermal FabricZZpartial"); input.props.onSearch("Thermal FabricZZpartial"); await flush()
	if (blurFirst) {
		input.props.onBlur(); await flush()
		assert.equal(switchCell().props.title, 'Pick a value from the list for "Thermal FabricZZpartial".')
		assert.equal(switchCell().props["aria-invalid"], true)
	}
	switchTabs.props.onSwitch(); await flush()
	assertFinished("Thermal Fabric")
	// Finishing again, as jumpTo/watch do, must be harmless.
	switchTabs.props.onSwitch(); await flush()
	assertFinished("Thermal Fabric")
	for (const exactText of ["Knitting", "Knitting second"]) {
		switchCell().props.onDblclick(); await flush()
		input = findNodes(switchRoot, node => node.type === "autocomplete")[0]
		input.props.onType(exactText); input.props.onSearch(exactText); await flush()
		if (blurFirst) { input.props.onBlur(); await flush() }
		switchTabs.props.onSwitch(); await flush()
		assertFinished(exactText)
	}
}

// The grid uses this same LinkField search; cover its pending-response race too.
const oldGridSearch = deferred(), currentGridSearch = deferred()
gridSearchHandler = (_doctype, query) => query === "Knitt" ? oldGridSearch.promise : currentGridSearch.promise
switchCell().props.onDblclick(); await flush()
input = findNodes(switchRoot, node => node.type === "autocomplete")[0]
input.props.onType("Knitt"); input.props.onSearch("Knitt"); await flush()
input.props.onType("Dye"); await flush()
oldGridSearch.resolve(["Knitting"]); await flush()
findNodes(switchRoot, node => node.props.onKeydownCapture)[0].props.onKeydownCapture(event("Enter")); await flush()
assert.equal(invalidGridProps.modelValue["bom-1"].item, "Knitting second")
assert.deepEqual(input.props.suggestions, [])
input.props.onSearch("Dye"); await flush()
currentGridSearch.resolve(["Dyeing"]); await flush()
assert.equal(input.props.focused, 0)
findNodes(switchRoot, node => node.props.onKeydownCapture)[0].props.onKeydownCapture(event("Enter")); await flush()
assertFinished("Dyeing")
gridSearchHandler = null

// Form and grid wrappers must share the same grammatical Link error.
formProps.field.options = "Item"
formProps.searchHandler = async () => ["Other item"]
await flush()
input = findNodes(formRoot, node => node.type === "autocomplete")[0]
input.props.onType("partial"); input.props.onSearch("partial"); await flush()
input.props.onBlur(); await flush()
assert.ok(findNodes(formRoot, node => node.props.class === "form-field__error" && node.text === 'Pick a value from the list for "partial".').length)
globalThis.document = beforeSwitchDocument
const previousWindow = globalThis.window
globalThis.window = { removeEventListener() {} }
switchApp.unmount()
invalidGridApp.unmount()
globalThis.window = previousWindow


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
