import assert from "node:assert/strict"
import { readFileSync } from "node:fs"

import { Vue, findNodes, loadComponent, mountComponent } from "./helpers/vue_renderer.mjs"
import AutoComplete from "../frontend/node_modules/primevue/autocomplete/index.mjs"
import Column from "../frontend/node_modules/primevue/column/index.mjs"
import PrimeDataTable from "../frontend/node_modules/primevue/datatable/index.mjs"
import { handleAutocompleteKey, withAutocompleteCompositionGuard } from "../frontend/src/components/common/autocompleteKeys.js"
import { plainTextFromHtml } from "../frontend/src/utils/documentValues.js"
import { mergeComputedValues } from "../frontend/src/departments/pd/pdViews.js"
import { childTableColumnField } from "../frontend/src/components/common/childTableFields.js"

const { h, reactive, nextTick, Fragment } = Vue
const BodyCell = PrimeDataTable.components.DTTableBody.components.DTBodyRow.components.DTBodyCell
// Render real PrimeVue cells on a node host, without a browser or table layout.
assert.match(readFileSync("frontend/node_modules/primevue/datatable/BodyCell.vue", "utf8"), /:is="column.children.body"/)
const DataTable = {
	props: ["value"],
	setup(props, { slots }) {
		return () => {
			const flatten = nodes => nodes.flatMap(node => node.type === Fragment ? flatten(node.children) : [node])
			const columns = flatten(slots.default()).filter(node => node.type === Column)
			return h("table", props.value.map((data, index) => h("tr", { key: index }, columns.map((column, columnIndex) =>
				h(BodyCell, {
					key: column.props?.columnKey || column.props?.field || columnIndex,
					rowData: data, rowIndex: index, index: columnIndex, column, unstyled: true,
				}),
			))))
		}
	},
}
const control = type => ({
	props: ["modelValue"],
	emits: ["update:modelValue"],
	setup(props, { attrs, emit }) {
		return () => h(type, { ...attrs, value: props.modelValue, onInput: value => emit("update:modelValue", value) })
	},
})
const AutoCompleteControl = {
	props: ["modelValue", "suggestions"],
	emits: ["update:modelValue", "item-select", "option-select", "clear", "blur", "complete"],
	setup(props, { attrs, emit, expose }) {
		expose({ hide() {} })
		let focusedOptionIndex = -1
		const context = () => ({
			forceSelection: Boolean(attrs.forceSelection), multiple: false, visibleOptions: props.suggestions,
			typeahead: true, overlayVisible: true, focusedOptionIndex,
			findFirstFocusedOptionIndex: () => 0,
			findNextOptionIndex: index => Math.min(index + 1, props.suggestions.length - 1),
			changeFocusedOptionIndex: (_, index) => { focusedOptionIndex = index },
			onOptionSelect: (event, option) => AutoComplete.methods.onOptionSelect.call(context(), event, option),
			$refs: { focusInput: { $el: { value: props.modelValue?.label || "" } } },
			$emit: emit, getOptionValue: option => option,
			isOptionMatched: (option, value) => option.label === value,
			isSelected: option => option.name === props.modelValue?.name,
			updateModel: (_, value) => emit("update:modelValue", value), hide() {},
		})
		return () => h("autocomplete", {
			...attrs, value: props.modelValue, suggestions: props.suggestions,
			onSearch: query => emit("complete", { query }),
			onPick: option => AutoComplete.methods.onOptionSelect.call(context(), {}, option),
			onArrowDown: () => AutoComplete.methods.onArrowDownKey.call(context(), { preventDefault() {} }),
			onEnter: () => AutoComplete.methods.onEnterKey.call(context(), { preventDefault() {} }),
			onChange: () => AutoComplete.methods.onChange.call(context(), {}),
			onBlur: () => emit("blur"),
			onClear: () => emit("clear"),
		})
	},
}
const searches = []
const modules = {
	"./autocompleteKeys.js": { handleAutocompleteKey, withAutocompleteCompositionGuard },
	"primevue/autocomplete": AutoCompleteControl,
	"primevue/button": control("button"),
	"primevue/inputtext": control("input"),
	"primevue/inputnumber": control("number"),
	"primevue/select": control("select"),
	"primevue/textarea": control("textarea"),
	"primevue/toggleswitch": control("check"),
	"./DateField.vue": {}, "./DateTimeField.vue": {}, "./TimeField.vue": {},
	"../../api/frappe.js": { searchLink: async (...args) => {
		searches.push(args)
		return [{ name: "black", label: "black" }, { name: "beige", label: "beige" }].filter(row => row.name.includes(args[1]))
	} },
	"../../router/webDocumentRoutes.js": { webDocumentPath: (doctype, name) => `${doctype}/${name}` },
	"../../utils/documentValues.js": { plainTextFromHtml },
}
const LinkField = loadComponent("frontend/src/components/common/LinkField.vue", modules)
const FormField = loadComponent("frontend/src/components/common/FormField.vue", { ...modules, "./LinkField.vue": LinkField })
const ChildTableField = loadComponent("frontend/src/components/common/ChildTableField.vue", {
	...modules,
	"primevue/column": Column,
	"primevue/datatable": DataTable,
	"./FormField.vue": FormField,
	"./childTableFields.js": { childTableColumnField },
})

const props = reactive({
	field: { fieldname: "fabric_composition", options: "Fabric" },
	modelValue: [{ fabric_name: "" }],
	childMeta: { fields: [{ fieldname: "fabric_name", fieldtype: "Data", in_list_view: 1 }] },
	"onUpdate:modelValue": rows => { props.modelValue = JSON.parse(JSON.stringify(rows)) },
})
const root = mountComponent(ChildTableField, props)
const inputs = () => findNodes(root, node => node.type === "input")
const originalInput = inputs()[0]
for (const character of "Polyester") {
	inputs()[0].props.onInput(props.modelValue[0].fabric_name + character)
	await nextTick()
	assert.ok(inputs()[0] === originalInput, "typing must retain the input node")
}
assert.equal(props.modelValue[0].fabric_name, "Polyester")

// Recreated metadata, filters and row objects must update props without remounting.
props.childMeta = { fields: [{ fieldname: "fabric_name", label: "Fabric Name", fieldtype: "Data", in_list_view: 1 }] }
props.columnFilters = () => ({ docstatus: 1 })
await nextTick()
assert.ok(inputs()[0] === originalInput)
assert.equal(inputs()[0].props["aria-label"], "Fabric Name, row 1")
props.errors = { "0.fabric_name": "Fabric is required" }
await nextTick()
assert.equal(inputs()[0].props.invalid, true)
assert.equal(findNodes(root, node => node.props.role === "alert")[0].text, "Fabric is required")

// Lotwise preview replaces calculated columns while retaining the active text cell.
props.field = { fieldname: "cmt", options: "CMT" }
props.childMeta = { fields: [{ fieldname: "costing_name", fieldtype: "Data" }] }
props.modelValue = [{ costing_name: "", rate: 5 }]
await nextTick()
const costingInput = inputs()[0]
for (const character of "ZZ TEST sewing") {
	inputs()[0].props.onInput((props.modelValue[0].costing_name || "") + character)
	await nextTick()
	props.modelValue = mergeComputedValues({ cmt: props.modelValue }, { cmt: [{ costing_name: "stale", amount: 10 }] }).cmt
	await nextTick()
	assert.ok(inputs()[0] === costingInput)
}
assert.equal(props.modelValue[0].costing_name, "ZZ TEST sewing")
assert.equal(props.modelValue[0].rate, 5)

props.field = { fieldname: "cloth_value" }
props.modelValue = [{ costing_name: "Cloth", total_cost: 0 }]
await nextTick()
const clothInput = inputs()[0]
props.modelValue = mergeComputedValues({ cloth_value: props.modelValue }, { cloth_value: [{ costing_name: "stale", total_cost: 10 }] }).cloth_value
await nextTick()
assert.ok(inputs()[0] === clothInput)
assert.equal(props.modelValue[0].costing_name, "Cloth")
assert.equal(props.modelValue[0].total_cost, 10)

// Adding an unnamed row applies defaults; removing renumbers idx.
props.childMeta = { fields: [
	{ fieldname: "costing_name", fieldtype: "Data", default: "Default" },
	{ fieldname: "enabled", fieldtype: "Check", default: "1" },
] }
await nextTick()
findNodes(root, node => node.type === "button" && node.props.label === "Add Row")[0].props.onClick()
await nextTick()
assert.equal(props.modelValue[1].costing_name, "Default")
assert.equal(props.modelValue[1].enabled, 1)
assert.equal(props.modelValue[1].idx, 2)
assert.equal(props.modelValue[1].name, undefined)
const newInput = inputs()[1]
newInput.props.onInput("ZZ TEST info")
await nextTick()
assert.ok(inputs()[1] === newInput)
assert.equal(props.modelValue[1].costing_name, "ZZ TEST info")
findNodes(root, node => node.type === "button" && node.props["aria-label"] === "Remove row 1")[0].props.onClick()
await nextTick()
assert.equal(props.modelValue.length, 1)
assert.equal(props.modelValue[0].idx, 1)

// Other field types still commit without replacing their controls.
for (const [fieldtype, type, value] of [["Float", "number", 12.5], ["Percent", "number", 20], ["Check", "check", true], ["Select", "select", "A"]]) {
	props.childMeta = { fields: [{ fieldname: "value", fieldtype, options: "A\nB" }] }
	props.modelValue = [{ value: null }]
	await nextTick()
	const original = findNodes(root, node => node.type === type)[0]
	original.props.onInput(value)
	await nextTick()
	assert.ok(findNodes(root, node => node.type === type)[0] === original)
	assert.equal(props.modelValue[0].value, fieldtype === "Check" ? 1 : value)
}

// Use real FormField/LinkField and PrimeVue's actual select/change methods.
props.columnFilters = null
props.field = { fieldname: "product_set_colours", options: "SD YRP Product Set Colour" }
props.childMeta = { fields: ["top_colour", "bottom_colour"].map(fieldname => ({
	fieldname, fieldtype: "Link", options: "SD YRP Product Colour Code", link_filters: { docstatus: 1 },
})) }
props.modelValue = [{}]
await nextTick()
const autocomplete = () => findNodes(root, node => node.type === "autocomplete")
for (const [index, name] of [[0, "black"], [1, "beige"]]) {
	const original = autocomplete()[index]
	await original.props.onSearch(index ? "be" : "")
	await nextTick()
	if (index) {
		original.props.onArrowDown()
		original.props.onEnter()
	} else original.props.onPick(original.props.suggestions.find(option => option.name === name))
	await nextTick()
	assert.ok(autocomplete()[index] === original, "selection must retain suggestions until native change validation")
	original.props.onChange()
	original.props.onBlur()
	await nextTick()
	assert.equal(props.modelValue[0][index ? "bottom_colour" : "top_colour"], name)
	assert.equal(original.props.value.name, name)
}
assert.deepEqual(searches.at(-1).slice(0, 3), ["SD YRP Product Colour Code", "be", { docstatus: 1 }])
assert.equal(findNodes(root, node => node.type === "button" && node.props.icon === "pi pi-arrow-up-right").length, 0)

// Main-form Link pick/clear/filter and open-record behavior use the same component.
const mainProps = reactive({ modelValue: "", doctype: "Product", filters: { enabled: 1 }, "onUpdate:modelValue": value => { mainProps.modelValue = value } })
const mainRoot = mountComponent(LinkField, mainProps)
const mainInput = findNodes(mainRoot, node => node.type === "autocomplete")[0]
await mainInput.props.onSearch("b")
await nextTick()
mainInput.props.onPick(mainInput.props.suggestions[0])
await nextTick()
mainInput.props.onChange()
mainInput.props.onBlur()
await nextTick()
assert.equal(mainProps.modelValue, "black")
assert.deepEqual(searches.at(-1).slice(0, 3), ["Product", "b", { enabled: 1 }])
const opened = []
globalThis.window = { open: (...args) => opened.push(args) }
findNodes(mainRoot, node => node.type === "button")[0].props.onClick({ preventDefault() {} })
assert.deepEqual(opened[0], ["Product/black", "_blank", "noopener"])
mainInput.props.onClear()
await nextTick()
assert.equal(mainProps.modelValue, "")

console.log("Child table identity, value commits, previews and Link selection tests passed")
