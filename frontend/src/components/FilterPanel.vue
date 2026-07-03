<!--
  FilterPanel — a Frappe-style list filter (modal popover). Stackable rows of
  [field → operator → value], ANDed, mirroring the Desk filter:
    • the field picker includes CHILD-TABLE fields, labelled "Field (Child DocType)";
    • operators are filtered per fieldtype (filter.js parity);
    • the value input adapts to fieldtype + operator (Link → search, Select →
      dropdown, Date → range/timespan, Check → Yes/No, "is" → Set/Not Set …).

  Filters are emitted as Frappe 4-tuples [doctype, fieldname, operator, value],
  where doctype is the parent OR a child doctype — frappe.client.get_list applies
  the child-table JOIN automatically, so no server change is needed.
-->
<template>
	<Dialog
		:visible="visible"
		modal
		header="Filter"
		:style="{ width: '660px', maxWidth: '95vw' }"
		@update:visible="$emit('update:visible', $event)"
	>
		<div v-if="loading" class="fp-loading">Loading fields…</div>
		<template v-else>
			<div v-if="!rows.length" class="fp-empty">No filters yet — add one below.</div>

			<div v-for="(row, i) in rows" :key="row.uid" class="fp-row">
				<!-- Field (parent + child-table fields, grouped + searchable) -->
				<Select
					v-model="row.field"
					:options="fieldGroups"
					optionGroupLabel="group"
					optionGroupChildren="items"
					optionLabel="label"
					dataKey="key"
					filter
					placeholder="Field"
					class="fp-field"
					@change="onFieldChange(row)"
				/>

				<!-- Operator (valid set for the field's fieldtype) -->
				<Select
					v-model="row.operator"
					:options="operatorsFor(row.field)"
					optionLabel="label"
					optionValue="value"
					placeholder="Condition"
					class="fp-op"
					:disabled="!row.field"
					@change="onOperatorChange(row)"
				/>

				<!-- Value (adapts to fieldtype + operator) -->
				<div class="fp-val">
					<Select
						v-if="row.operator === 'is'"
						v-model="row.value"
						:options="SET_OPTIONS"
						optionLabel="label"
						optionValue="value"
						placeholder="Value"
						fluid
					/>
					<Select
						v-else-if="row.field && row.field.fieldtype === 'Check'"
						v-model="row.value"
						:options="YESNO_OPTIONS"
						optionLabel="label"
						optionValue="value"
						placeholder="Value"
						fluid
					/>
					<DatePicker
						v-else-if="isDateField(row.field) && row.operator === 'between'"
						v-model="row.value"
						selectionMode="range"
						dateFormat="yy-mm-dd"
						placeholder="From – To"
						showButtonBar
						fluid
					/>
					<Select
						v-else-if="isDateField(row.field) && row.operator === 'timespan'"
						v-model="row.value"
						:options="TIMESPANS"
						optionLabel="label"
						optionValue="value"
						placeholder="Timespan"
						filter
						fluid
					/>
					<DatePicker
						v-else-if="isDateField(row.field)"
						v-model="row.value"
						dateFormat="yy-mm-dd"
						placeholder="Pick a date"
						showButtonBar
						fluid
					/>
					<LinkField
						v-else-if="row.field && row.field.fieldtype === 'Link' && ['=', '!='].includes(row.operator)"
						:model-value="row.value"
						@update:model-value="row.value = $event"
						:target-doctype="row.field.options"
					/>
					<Select
						v-else-if="row.field && row.field.fieldtype === 'Select' && ['=', '!='].includes(row.operator)"
						v-model="row.value"
						:options="selectOptions(row.field)"
						placeholder="Value"
						filter
						fluid
					/>
					<InputNumber
						v-else-if="isNumberField(row.field) && !['in', 'not in'].includes(row.operator)"
						v-model="row.value"
						:useGrouping="false"
						placeholder="Value"
						fluid
					/>
					<InputText
						v-else
						v-model="row.value"
						:placeholder="['in', 'not in'].includes(row.operator) ? 'value1, value2, …' : 'Value'"
						fluid
					/>
				</div>

				<Button
					icon="pi pi-times"
					text
					rounded
					severity="secondary"
					size="small"
					class="fp-del"
					v-tooltip.top="'Remove'"
					@click="removeRow(i)"
				/>
			</div>

			<Button
				label="Add Filter"
				icon="pi pi-plus"
				text
				size="small"
				class="fp-add"
				@click="addRow()"
			/>
		</template>

		<template #footer>
			<Button
				label="Clear all"
				severity="secondary"
				outlined
				size="small"
				:disabled="!rows.length"
				@click="clearAll"
			/>
			<Button label="Apply Filters" icon="pi pi-check" size="small" @click="apply" />
		</template>
	</Dialog>
</template>

<script setup>
import { ref, watch } from "vue"
import Dialog from "primevue/dialog"
import Select from "primevue/select"
import InputText from "primevue/inputtext"
import InputNumber from "primevue/inputnumber"
import DatePicker from "primevue/datepicker"
import Button from "primevue/button"
import Tooltip from "primevue/tooltip"
import LinkField from "@/components/LinkField.vue"
import { getMeta } from "@/api/client"

const vTooltip = Tooltip

const props = defineProps({
	visible: { type: Boolean, default: false },
	doctype: { type: String, required: true },
	// Current advanced filters: array of [doctype, fieldname, operator, value].
	modelValue: { type: Array, default: () => [] },
})
const emit = defineEmits(["update:visible", "apply"])

// ── constants ──────────────────────────────────────────────────────────────
const SET_OPTIONS = [
	{ label: "Set", value: "set" },
	{ label: "Not Set", value: "not set" },
]
const YESNO_OPTIONS = [
	{ label: "Yes", value: 1 },
	{ label: "No", value: 0 },
]
const TIMESPANS = [
	"today", "yesterday", "tomorrow",
	"this week", "this month", "this quarter", "this year",
	"last week", "last month", "last quarter", "last year",
	"last 7 days", "last 14 days", "last 30 days", "last 90 days",
	"next week", "next month", "next quarter", "next year",
].map((v) => ({ label: v.replace(/\b\w/g, (c) => c.toUpperCase()), value: v }))

const ALL_OPERATORS = [
	{ value: "=", label: "Equals" },
	{ value: "!=", label: "Not Equals" },
	{ value: "like", label: "Like" },
	{ value: "not like", label: "Not Like" },
	{ value: "in", label: "In" },
	{ value: "not in", label: "Not In" },
	{ value: "is", label: "Set / Not Set" },
	{ value: ">", label: ">" },
	{ value: "<", label: "<" },
	{ value: ">=", label: ">=" },
	{ value: "<=", label: "<=" },
	{ value: "between", label: "Between" },
	{ value: "timespan", label: "Timespan" },
]

// fieldtypes that can't be filtered (layout / no-value / table / attachment)
const NON_FILTER_FT = new Set([
	"Section Break", "Column Break", "Tab Break", "HTML", "Button", "Image",
	"Fold", "Heading", "Table", "Table MultiSelect", "Geolocation", "Signature",
	"Barcode", "Attach", "Attach Image",
])

// ── state ────────────────────────────────────────────────────────────────
const loading = ref(false)
const fieldGroups = ref([]) // [{ group, items: [fieldOption] }]
const fieldByKey = ref({}) // key -> fieldOption (for rebuilding rows from tuples)
const rows = ref([])
let uidSeq = 0

function isDateField(f) {
	return !!f && (f.fieldtype === "Date" || f.fieldtype === "Datetime")
}
function isNumberField(f) {
	return !!f && ["Int", "Float", "Currency", "Percent"].includes(f.fieldtype)
}
function selectOptions(f) {
	return (f.options || "").split("\n").map((s) => s.trim()).filter(Boolean)
}

// operators valid for the selected field's fieldtype (mirrors Frappe filter.js)
function operatorsFor(f) {
	if (!f) return ALL_OPERATORS
	const ft = f.fieldtype
	let ops = [...ALL_OPERATORS]
	const drop = (vals) => (ops = ops.filter((o) => !vals.includes(o.value)))
	if (ft === "Date" || ft === "Datetime") {
		drop(["like", "not like"])
	} else if (ft === "Check") {
		ops = [{ value: "=", label: "Equals" }]
	} else if (ft === "Link" || ft === "Dynamic Link") {
		drop(["between", "timespan", ">", "<", ">=", "<="])
	} else if (["Int", "Float", "Currency", "Percent"].includes(ft)) {
		drop(["like", "not like", "between", "in", "not in", "timespan"])
	} else if (ft === "Select") {
		drop(["like", "not like", "between", "timespan"])
	}
	return ops
}

// ── build the field picker (parent + child-table fields) ──────────────────
async function loadFields() {
	loading.value = true
	try {
		// getMeta bundles the parent doctype AND its child-table metas in `docs`.
		const docs = await getMeta(props.doctype)
		const byName = {}
		for (const d of docs) byName[d.name] = d
		const parent = byName[props.doctype] || docs[0]
		const groups = []
		const keyMap = {}

		const addGroup = (dt, metaDoc, isChild) => {
			const items = []
			if (!isChild) {
				// parent gets an explicit ID (name) option, like the Desk
				const k = `${dt}::name`
				const opt = { key: k, doctype: dt, fieldname: "name", fieldtype: "Data", options: "", label: "ID" }
				keyMap[k] = opt
				items.push(opt)
			}
			for (const df of metaDoc?.fields || []) {
				if (NON_FILTER_FT.has(df.fieldtype)) continue
				if (!df.fieldname || !df.label) continue
				const k = `${dt}::${df.fieldname}`
				const opt = {
					key: k,
					doctype: dt,
					fieldname: df.fieldname,
					fieldtype: df.fieldtype,
					options: df.options || "",
					label: isChild ? `${df.label} (${dt})` : df.label,
				}
				keyMap[k] = opt
				items.push(opt)
			}
			if (items.length) groups.push({ group: isChild ? dt : metaDoc?.name || dt, items })
		}

		addGroup(props.doctype, parent, false)
		for (const df of parent?.fields || []) {
			if ((df.fieldtype === "Table" || df.fieldtype === "Table MultiSelect") && df.options) {
				const childMeta = byName[df.options]
				if (childMeta) addGroup(df.options, childMeta, true)
			}
		}

		fieldGroups.value = groups
		fieldByKey.value = keyMap
		seedRows()
	} finally {
		loading.value = false
	}
}

// rebuild editable rows from the current modelValue tuples
function seedRows() {
	const seeded = []
	for (const t of props.modelValue || []) {
		if (!Array.isArray(t) || t.length < 3) continue
		// support both [field, op, val] (parent) and [doctype, field, op, val]
		let dt, fn, op, val
		if (t.length >= 4) [dt, fn, op, val] = t
		else {
			dt = props.doctype
			;[fn, op, val] = t
		}
		const field = fieldByKey.value[`${dt}::${fn}`] || null
		seeded.push({ uid: ++uidSeq, field, operator: op, value: hydrateValue(field, op, val) })
	}
	rows.value = seeded
}

// stored value → input-friendly value (Dates → Date objects, like → unwrapped %, in → csv)
function hydrateValue(field, op, val) {
	if (op === "between" && Array.isArray(val)) return val.map((v) => (v ? new Date(v) : null))
	if (isDateField(field) && typeof val === "string" && val) return new Date(val)
	if ((op === "like" || op === "not like") && typeof val === "string") return val.replace(/^%|%$/g, "")
	if ((op === "in" || op === "not in") && Array.isArray(val)) return val.join(", ")
	return val
}

function defaultValueFor(op) {
	return op === "is" ? "set" : null
}
function addRow() {
	rows.value.push({ uid: ++uidSeq, field: null, operator: "=", value: null })
}
function removeRow(i) {
	rows.value.splice(i, 1)
}
function clearAll() {
	rows.value = []
}
function onFieldChange(row) {
	const ops = operatorsFor(row.field)
	if (!ops.some((o) => o.value === row.operator)) row.operator = ops[0]?.value || "="
	row.value = defaultValueFor(row.operator)
}
function onOperatorChange(row) {
	// value shape changes with the operator (range / list / set / scalar) — reset it
	row.value = defaultValueFor(row.operator)
}

// ── apply ──────────────────────────────────────────────────────────────────
function toISO(d) {
	if (!d) return d
	if (typeof d === "string") return d
	const pad = (n) => String(n).padStart(2, "0")
	return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}
function opLabel(v) {
	return ALL_OPERATORS.find((o) => o.value === v)?.label || v
}
function valueText(field, op, val) {
	if (op === "is") return val === "not set" ? "Not Set" : "Set"
	if (field && field.fieldtype === "Check") return val ? "Yes" : "No"
	if (Array.isArray(val)) return val.map((v) => toISO(v)).join(" – ")
	return String(val)
}

function apply() {
	const tuples = []
	const labels = []
	for (const r of rows.value) {
		if (!r.field) continue
		const { doctype, fieldname, fieldtype } = r.field
		const op = r.operator
		let val = r.value

		if (op === "is") {
			val = val || "set"
		} else if (fieldtype === "Check") {
			if (val === null || val === undefined) continue
			val = val ? 1 : 0
		} else if (op === "between") {
			if (!Array.isArray(val) || !val[0] || !val[1]) continue
			val = [toISO(val[0]), toISO(val[1])]
		} else if (isDateField(r.field) && op !== "timespan") {
			if (!val) continue
			val = toISO(val)
		} else if (op === "in" || op === "not in") {
			if (typeof val === "string") val = val.split(",").map((s) => s.trim()).filter(Boolean)
			if (!Array.isArray(val) || !val.length) continue
		} else if (op === "like" || op === "not like") {
			if (val === null || val === undefined || val === "") continue
			val = String(val).includes("%") ? val : `%${val}%`
		} else {
			if (val === null || val === undefined || val === "") continue
		}

		tuples.push([doctype, fieldname, op, val])
		labels.push(`${r.field.label} ${opLabel(op)} ${valueText(r.field, op, val)}`)
	}
	emit("apply", tuples, labels)
	emit("update:visible", false)
}

// reload fields + reseed rows each time the dialog opens
watch(
	() => props.visible,
	(open) => {
		if (open) loadFields()
	},
)
</script>

<style scoped>
.fp-row {
	display: grid;
	grid-template-columns: 1.4fr 1fr 1.6fr auto;
	gap: 8px;
	align-items: center;
	margin-bottom: 8px;
}
.fp-field,
.fp-op,
.fp-val {
	min-width: 0;
}
.fp-add {
	margin-top: 4px;
}
.fp-empty,
.fp-loading {
	padding: 12px 4px;
	color: var(--esd-muted);
	font-size: 13px;
}
.fp-del {
	flex-shrink: 0;
}
</style>
