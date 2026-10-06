<template>
	<Dialog
		:visible="visible"
		modal
		dismissable-mask
		header="Filters"
		class="list-filter-dialog"
		:style="{ width: '64rem', maxWidth: 'calc(100vw - 24px)' }"
		@update:visible="$emit('update:visible', $event)"
	>
		<div class="filter-column-headings" aria-hidden="true">
			<span>Field</span>
			<span>Condition</span>
			<span>Value</span>
			<span></span>
		</div>

		<div class="filter-rows">
			<div v-for="(row, index) in rows" :key="row.id" class="filter-row">
				<label class="filter-control">
					<span class="filter-control__mobile-label">Field</span>
					<Select
						v-model="row.fieldKey"
						:options="fieldOptions"
						option-label="displayLabel"
						option-value="key"
						placeholder="Select field"
						filter
						fluid
						@change="fieldChanged(row)"
					/>
				</label>

				<label class="filter-control">
					<span class="filter-control__mobile-label">Condition</span>
					<Select
						v-model="row.operator"
						:options="operatorsFor(row)"
						option-label="label"
						option-value="value"
						placeholder="Condition"
						fluid
						@change="operatorChanged(row)"
					/>
				</label>

				<label class="filter-control filter-row__value">
					<span class="filter-control__mobile-label">Value</span>
					<Select
						v-if="row.operator === 'is'"
						v-model="row.value"
						:options="setOptions"
						option-label="label"
						option-value="value"
						placeholder="Set or not set"
						fluid
					/>
					<Select
						v-else-if="usesTimespanEditor(row)"
						v-model="row.value"
						:options="timespanOptions"
						option-label="label"
						option-value="value"
						placeholder="Select timespan"
						filter
						fluid
					/>
					<Select
						v-else-if="isCheckField(row)"
						v-model="row.value"
						:options="checkOptions"
						option-label="label"
						option-value="value"
						placeholder="Yes or No"
						fluid
					/>
					<LinkField
						v-else-if="usesLinkEditor(row)"
						v-model="row.value"
						:doctype="linkDoctype(row)"
						:filters="linkFilters(fieldFor(row))"
						:placeholder="`Search ${fieldFor(row)?.label || 'record'}…`"
						match-visible-only
						show-clear
						:show-open-button="false"
					/>
					<MultiSelectField
						v-else-if="usesSelectMultiEditor(row)"
						v-model="row.value"
						:options="selectOptions(fieldFor(row))"
						placeholder="Select values"
					/>
					<Select
						v-else-if="usesSelectEditor(row)"
						v-model="row.value"
						:options="selectOptions(fieldFor(row))"
						option-label="label"
						option-value="value"
						placeholder="Select value"
						filter
						show-clear
						fluid
					/>
					<DateTimeField
						v-else-if="usesDateRangeEditor(row) && fieldFor(row)?.fieldtype === 'Datetime'"
						v-model="row.value"
						:aria-label="`${fieldFor(row)?.label || 'Date'} range`"
						value-type="date"
						selection-mode="range"
						placeholder="DD-MM-YYYY - DD-MM-YYYY"
						show-clear
					/>
					<DateField
						v-else-if="usesDateRangeEditor(row)"
						v-model="row.value"
						:aria-label="`${fieldFor(row)?.label || 'Date'} range`"
						value-type="date"
						selection-mode="range"
						placeholder="DD-MM-YYYY - DD-MM-YYYY"
						show-clear
					/>
					<DateTimeField
						v-else-if="usesDateEditor(row) && fieldFor(row)?.fieldtype === 'Datetime'"
						v-model="row.value"
						:aria-label="fieldFor(row)?.label || 'Date'"
						value-type="date"
						placeholder="DD-MM-YYYY HH:MM:SS"
						show-clear
					/>
					<DateField
						v-else-if="usesDateEditor(row)"
						v-model="row.value"
						:aria-label="fieldFor(row)?.label || 'Date'"
						value-type="date"
						placeholder="DD-MM-YYYY"
						show-clear
					/>
					<TimeField
						v-else-if="fieldFor(row)?.fieldtype === 'Time' && !usesDataEditor(row)"
						v-model="row.value"
						:aria-label="fieldFor(row)?.label || 'Time'"
						value-type="date"
						placeholder="HH:MM:SS"
						show-clear
					/>
					<InputNumber
						v-else-if="usesNumberEditor(row)"
						v-model="row.value"
						:min-fraction-digits="minimumFractionDigits(row)"
						:max-fraction-digits="maximumFractionDigits(row)"
						:use-grouping="false"
						placeholder="Value"
						fluid
					/>
					<InputText
						v-else
						v-model="row.value"
						:placeholder="textValuePlaceholder(row)"
						fluid
					/>
					<small v-if="valueHelp(row)" class="filter-value-help">{{ valueHelp(row) }}</small>
				</label>

				<Button
					icon="pi pi-times"
					severity="secondary"
					text
					rounded
					aria-label="Remove filter"
					title="Remove filter"
					@click="rows.splice(index, 1)"
				/>
			</div>
			<div v-if="!rows.length" class="filter-empty">
				<i class="pi pi-filter-slash" />
				<span>No filters added.</span>
			</div>
		</div>

		<Button class="add-filter-button" label="Add a Filter" icon="pi pi-plus" text @click="add" />

		<template #footer>
			<Button label="Clear Filters" severity="secondary" outlined @click="clear" />
			<Button label="Apply Filters" icon="pi pi-check" @click="apply" />
		</template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import InputNumber from "primevue/inputnumber"
import InputText from "primevue/inputtext"
import Select from "primevue/select"
import { computed, ref, watch } from "vue"

import DateField from "./DateField.vue"
import DateTimeField from "./DateTimeField.vue"
import LinkField from "./LinkField.vue"
import MultiSelectField from "./MultiSelectField.vue"
import TimeField from "./TimeField.vue"

const props = defineProps({
	visible: { type: Boolean, default: false },
	doctype: { type: String, default: "" },
	fields: { type: Array, default: () => [] },
	modelValue: { type: Array, default: () => [] },
})

const emit = defineEmits(["update:visible", "apply", "update:modelValue"])
const rows = ref([])
let nextId = 0

const BASE_CONDITIONS = [
	{ label: "Equals", value: "=" },
	{ label: "Not Equals", value: "!=" },
	{ label: "Like", value: "like" },
	{ label: "Not Like", value: "not like" },
	{ label: "In", value: "in" },
	{ label: "Not In", value: "not in" },
	{ label: "Is", value: "is" },
	{ label: "Greater Than", value: ">" },
	{ label: "Less Than", value: "<" },
	{ label: "Greater Than or Equal To", value: ">=" },
	{ label: "Less Than or Equal To", value: "<=" },
	{ label: "Between", value: "Between" },
	{ label: "Timespan", value: "Timespan" },
]
const NESTED_SET_CONDITIONS = [
	{ label: "Descendants Of", value: "descendants of" },
	{ label: "Descendants Of (inclusive)", value: "descendants of (inclusive)" },
	{ label: "Not Descendants Of", value: "not descendants of" },
	{ label: "Ancestors Of", value: "ancestors of" },
	{ label: "Not Ancestors Of", value: "not ancestors of" },
]
const INVALID_CONDITIONS = {
	Date: ["like", "not like"],
	Datetime: ["like", "not like", "in", "not in", "=", "!="],
	Data: ["Between", "Timespan"],
	Time: ["Between", "Timespan"],
	Select: ["like", "not like", "Between", "Timespan"],
	Link: ["Between", "Timespan", ">", "<", ">=", "<="],
	Currency: ["Between", "Timespan"],
	Color: ["Between", "Timespan"],
	Check: BASE_CONDITIONS.map((condition) => condition.value).filter((condition) => condition !== "="),
	Code: ["Between", "Timespan", ">", "<", ">=", "<=", "in", "not in"],
	"HTML Editor": ["Between", "Timespan", ">", "<", ">=", "<=", "in", "not in"],
	"Markdown Editor": ["Between", "Timespan", ">", "<", ">=", "<=", "in", "not in"],
	Password: ["Between", "Timespan", ">", "<", ">=", "<=", "in", "not in"],
	Rating: ["like", "not like", "Between", "in", "not in", "Timespan"],
	Int: ["like", "not like", "Between", "in", "not in", "Timespan"],
	Float: ["like", "not like", "Between", "in", "not in", "Timespan"],
	Percent: ["like", "not like", "Between", "in", "not in", "Timespan"],
}
const DATA_CONTROL_TYPES = new Set([
	"Text", "Small Text", "Long Text", "Text Editor", "Attach", "Attach Image",
	"Markdown Editor", "HTML Editor", "Tag", "Phone", "JSON", "Comments", "Barcode",
	"Dynamic Link", "Read Only", "Assign", "Color",
])
const NUMBER_TYPES = new Set(["Currency", "Float", "Int", "Percent", "Duration", "Rating"])
const LINK_CONDITIONS = new Set([
	"=", "!=", "descendants of", "descendants of (inclusive)", "not descendants of",
	"ancestors of", "not ancestors of",
])
const MULTI_CONDITIONS = new Set(["in", "not in"])

const setOptions = [
	{ label: "Set", value: "set" },
	{ label: "Not Set", value: "not set" },
]
const checkOptions = [
	{ label: "Yes", value: 1 },
	{ label: "No", value: 0 },
]
const timespanOptions = [
	["Last 7 Days", "last 7 days"], ["Last 14 Days", "last 14 days"],
	["Last 30 Days", "last 30 days"], ["Last 90 Days", "last 90 days"],
	["Last Week", "last week"], ["Last Month", "last month"],
	["Last Quarter", "last quarter"], ["Last 6 Months", "last 6 months"],
	["Last Year", "last year"], ["Yesterday", "yesterday"], ["Today", "today"],
	["Tomorrow", "tomorrow"], ["This Week", "this week"], ["This Month", "this month"],
	["This Quarter", "this quarter"], ["This Year", "this year"],
	["Next 7 Days", "next 7 days"], ["Next 14 Days", "next 14 days"],
	["Next 30 Days", "next 30 days"], ["Next Week", "next week"],
	["Next Month", "next month"], ["Next Quarter", "next quarter"],
	["Next 6 Months", "next 6 months"], ["Next Year", "next year"],
].map(([label, value]) => ({ label, value }))

const fieldOptions = computed(() =>
	props.fields.map((field) => ({
		...field,
		key: field.key || fieldKey(field.doctype, field.fieldname),
		displayLabel: field.displayLabel || field.label || field.fieldname,
	})),
)

watch(
	() => props.visible,
	(visible) => {
		if (!visible) return
		rows.value = props.modelValue.map(rowFromFilter)
		if (!rows.value.length) add(defaultField())
	},
)

function fieldKey(doctype, fieldname) {
	return `${doctype || props.doctype || ""}::${fieldname || ""}`
}

function defaultField() {
	return fieldOptions.value.find((field) => field.fieldname === "name") || fieldOptions.value[0] || null
}

function rowFromFilter(filter) {
	const hasDoctype = filter.length >= 4
	const [doctype, fieldname, operator, rawValue] = hasDoctype
		? filter
		: [props.doctype, filter[0], filter[1], filter[2]]
	const field = fieldOptions.value.find(
		(option) => option.fieldname === fieldname && (!doctype || option.doctype === doctype),
	) || fieldOptions.value.find((option) => option.fieldname === fieldname)
	const row = {
		id: ++nextId,
		fieldKey: field?.key || fieldKey(doctype, fieldname),
		operator: operator || defaultOperator(field),
		value: null,
	}
	row.value = inflateValue(row, rawValue)
	return row
}

function fieldFor(row) {
	return fieldOptions.value.find((field) => field.key === row.fieldKey)
}

function effectiveConditionType(field) {
	if (!field) return "Data"
	if (INVALID_CONDITIONS[field.fieldtype]) return field.fieldtype
	if (DATA_CONTROL_TYPES.has(field.fieldtype)) return "Data"
	return field.fieldtype || "Data"
}

function defaultOperator(field) {
	if (!field) return "="
	if (["_assign", "_liked_by"].includes(field.fieldname)) return "like"
	if (field.fieldtype === "Data") return "like"
	if (["Date", "Datetime"].includes(field.fieldtype)) return "Between"
	return "="
}

function fieldChanged(row) {
	const field = fieldFor(row)
	row.operator = defaultOperator(field)
	row.value = defaultValue(row)
}

function operatorChanged(row) {
	row.value = defaultValue(row)
}

function defaultValue(row) {
	if (row.operator === "is") return "set"
	if (usesTimespanEditor(row)) return "last 7 days"
	if (isCheckField(row)) return 1
	if (usesSelectMultiEditor(row)) return []
	return null
}

function isNestedSet(field) {
	const doctypes = window.frappe?.boot?.nested_set_doctypes || []
	return field?.fieldtype === "Link" && doctypes.includes(field.options)
}

function operatorsFor(row) {
	const field = fieldFor(row)
	const type = effectiveConditionType(field)
	const invalid = new Set(INVALID_CONDITIONS[type] || [])
	const conditions = BASE_CONDITIONS.filter((condition) => !invalid.has(condition.value))
	if (isNestedSet(field)) conditions.push(...NESTED_SET_CONDITIONS)
	return conditions.map((condition) => {
		if (!["Date", "Datetime"].includes(field?.fieldtype)) return condition
		const labels = { "<": "Before", ">": "After", "<=": "On or Before", ">=": "On or After" }
		return labels[condition.value] ? { ...condition, label: labels[condition.value] } : condition
	})
}

function isCheckField(row) {
	return fieldFor(row)?.fieldtype === "Check"
}

function linkDoctype(row) {
	return fieldFor(row)?.options || props.doctype || "DocType"
}

function usesLinkEditor(row) {
	const field = fieldFor(row)
	return field?.fieldtype === "Link" && LINK_CONDITIONS.has(row.operator)
}

function usesSelectMultiEditor(row) {
	return fieldFor(row)?.fieldtype === "Select" && MULTI_CONDITIONS.has(row.operator)
}

function usesSelectEditor(row) {
	const field = fieldFor(row)
	return field?.fieldtype === "Select" || field?.fieldname === "docstatus"
}

function usesDateRangeEditor(row) {
	return ["Date", "Datetime"].includes(fieldFor(row)?.fieldtype) && row.operator === "Between"
}

function usesTimespanEditor(row) {
	return row.operator === "Timespan"
		&& ["Date", "Datetime", "DateRange", "Select"].includes(fieldFor(row)?.fieldtype)
}

function usesDateEditor(row) {
	return ["Date", "Datetime"].includes(fieldFor(row)?.fieldtype) && !usesDataEditor(row)
}

function usesNumberEditor(row) {
	return NUMBER_TYPES.has(fieldFor(row)?.fieldtype) && !usesDataEditor(row)
}

function usesDataEditor(row) {
	return ["in", "not in", "like", "not like"].includes(row.operator)
		&& !usesSelectMultiEditor(row)
}

function selectOptions(field) {
	if (field?.fieldname === "docstatus") {
		return [
			{ label: "Draft", value: 0 },
			{ label: "Submitted", value: 1 },
			{ label: "Cancelled", value: 2 },
		]
	}
	if (Array.isArray(field?.options)) {
		return field.options.map((option) =>
			typeof option === "object" ? option : { label: String(option), value: option },
		)
	}
	return String(field?.options || "")
		.split("\n")
		.map((value) => value.trim())
		.filter(Boolean)
		.map((value) => ({ label: value, value }))
}

function linkFilters(field) {
	const value = field?.link_filters
	if (!value) return {}
	let parsed = value
	if (typeof parsed === "string") {
		try {
			parsed = JSON.parse(parsed)
		} catch {
			return {}
		}
	}
	if (!Array.isArray(parsed)) return parsed && typeof parsed === "object" ? parsed : {}
	return Object.fromEntries(
		parsed.flatMap((filter) => {
			if (!Array.isArray(filter)) return []
			const parts = filter.length >= 4 ? filter.slice(1) : filter
			return parts[1] === "=" ? [[parts[0], parts[2]]] : []
		}),
	)
}

function minimumFractionDigits() {
	return 0
}

function maximumFractionDigits(row) {
	const field = fieldFor(row)
	if (field?.fieldtype === "Int") return 0
	const precision = Number(field?.precision)
	return Number.isInteger(precision) && precision >= 0 ? precision : 6
}

function textValuePlaceholder(row) {
	if (MULTI_CONDITIONS.has(row.operator)) return "Values separated by commas"
	if (["like", "not like"].includes(row.operator)) return "Text to match"
	return "Value"
}

function valueHelp(row) {
	if (MULTI_CONDITIONS.has(row.operator) && !usesSelectMultiEditor(row)) {
		return "Enter multiple values separated by commas."
	}
	if (["like", "not like"].includes(row.operator)) {
		return "Use % as a wildcard; it is added automatically when omitted."
	}
	return ""
}

function add(field = defaultField()) {
	const row = {
		id: ++nextId,
		fieldKey: field?.key || "",
		operator: defaultOperator(field),
		value: null,
	}
	row.value = defaultValue(row)
	rows.value.push(row)
}

function clear() {
	rows.value = []
	emit("update:modelValue", [])
	emit("apply", [])
	emit("update:visible", false)
}

function inflateValue(row, value) {
	if (value === null || value === undefined || value === "") return defaultValue(row)
	const field = fieldFor(row)
	if (usesSelectMultiEditor(row)) return Array.isArray(value) ? value : splitValues(value)
	if (MULTI_CONDITIONS.has(row.operator)) return Array.isArray(value) ? value.join(", ") : value
	if (["like", "not like"].includes(row.operator)) return value
	if (row.operator === "Timespan") return value
	if (["Date", "Datetime"].includes(field?.fieldtype)) {
		if (row.operator === "Between") {
			const values = Array.isArray(value) ? value : String(value).split(",")
			return values.map(parseDate).filter(Boolean)
		}
		return parseDate(value)
	}
	if (field?.fieldtype === "Time") return parseTime(value)
	if (isCheckField(row) || (NUMBER_TYPES.has(field?.fieldtype) && !MULTI_CONDITIONS.has(row.operator))) {
		const number = Number(value)
		return Number.isFinite(number) ? number : value
	}
	return Array.isArray(value) && !usesSelectMultiEditor(row) ? value.join(", ") : value
}

function parseDate(value) {
	if (value instanceof Date) return value
	const match = String(value || "").match(
		/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?/,
	)
	if (!match) return null
	return new Date(
		Number(match[1]), Number(match[2]) - 1, Number(match[3]),
		Number(match[4] || 0), Number(match[5] || 0), Number(match[6] || 0),
	)
}

function parseTime(value) {
	if (value instanceof Date) return value
	const match = String(value || "").match(/^(\d{1,2}):(\d{2})(?::(\d{2}))?/)
	if (!match) return null
	const result = new Date()
	result.setHours(Number(match[1]), Number(match[2]), Number(match[3] || 0), 0)
	return result
}

function pad(value) {
	return String(value).padStart(2, "0")
}

function formatDate(value, withTime = false) {
	if (!(value instanceof Date)) return value
	const date = `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}`
	return withTime
		? `${date} ${pad(value.getHours())}:${pad(value.getMinutes())}:${pad(value.getSeconds())}`
		: date
}

function formatTime(value) {
	if (!(value instanceof Date)) return value
	return `${pad(value.getHours())}:${pad(value.getMinutes())}:${pad(value.getSeconds())}`
}

function splitValues(value) {
	if (Array.isArray(value)) return value.filter(hasScalarValue)
	const text = String(value || "").trim()
	if (!text) return []
	try {
		const parsed = JSON.parse(text)
		if (Array.isArray(parsed)) return parsed.filter(hasScalarValue)
	} catch {
		// A normal comma-separated value is the expected input.
	}
	return text.split(",").map((part) => part.trim()).filter(Boolean)
}

function normaliseValue(row) {
	const field = fieldFor(row)
	let value = row.value
	if (row.operator === "Between" && ["Date", "Datetime"].includes(field?.fieldtype)) {
		value = (Array.isArray(value) ? value : []).map((item) =>
			formatDate(item, field?.fieldtype === "Datetime"),
		)
	} else if (MULTI_CONDITIONS.has(row.operator)) {
		value = splitValues(value)
	} else if (["like", "not like"].includes(row.operator)) {
		value = String(value ?? "").trim()
		if (value && !value.startsWith("%") && !value.endsWith("%")) value = `%${value}%`
	} else if (["Date", "Datetime"].includes(field?.fieldtype)) {
		value = formatDate(value, field.fieldtype === "Datetime")
	} else if (field?.fieldtype === "Time") {
		value = formatTime(value)
	}
	return value
}

function hasScalarValue(value) {
	return value !== null && value !== undefined && String(value).trim() !== ""
}

function hasCompleteValue(row, value) {
	if (usesDateRangeEditor(row)) return Array.isArray(value) && value.length === 2 && value.every(hasScalarValue)
	if (Array.isArray(value)) return value.length > 0
	return hasScalarValue(value)
}

function apply() {
	const filters = rows.value.flatMap((row) => {
		const field = fieldFor(row)
		if (!field || !row.operator) return []
		const value = normaliseValue(row)
		if (!hasCompleteValue(row, value)) return []
		const useDoctype = props.doctype && field.doctype && field.doctype !== props.doctype
		return [useDoctype
			? [field.doctype, field.fieldname, row.operator, value]
			: [field.fieldname, row.operator, value]]
	})
	emit("update:modelValue", filters)
	emit("apply", filters)
	emit("update:visible", false)
}
</script>

<style scoped>
.filter-column-headings,
.filter-row {
	display: grid;
	grid-template-columns: minmax(190px, 1.08fr) minmax(180px, 0.92fr) minmax(260px, 1.45fr) 36px;
	gap: 10px;
}

.filter-column-headings { padding: 0 10px 7px; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 780; letter-spacing: 0.04em; text-transform: uppercase; }
.filter-rows { display: grid; gap: 8px; max-height: min(54vh, 470px); margin-bottom: 8px; overflow-y: auto; scrollbar-width: thin; }
.filter-row { align-items: start; padding: 10px; background: #fff; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); box-shadow: 0 1px 2px rgb(24 53 39 / 3%); }
.filter-row:hover { border-color: color-mix(in srgb, var(--erp-accent) 22%, var(--erp-border)); }
.filter-row:focus-within { background: #fff; border-color: color-mix(in srgb, var(--erp-accent) 55%, white); box-shadow: 0 0 0 3px color-mix(in srgb, var(--erp-accent) 9%, transparent); }
.filter-control { display: grid; gap: 4px; min-width: 0; }
.filter-control__mobile-label { display: none; }
.filter-row__value { min-width: 0; }
.filter-value-help { color: #6b7b73; font-size: var(--erp-font-size-min); line-height: 1.35; }

.filter-row :deep(.p-inputtext),
.filter-row :deep(.p-select),
.filter-row :deep(.p-autocomplete-input),
.filter-row :deep(.p-inputnumber-input),
.filter-row :deep(.p-multiselect) { min-height: var(--erp-control-height); border-color: var(--erp-border-strong); border-radius: var(--erp-control-radius); }

.filter-row :deep(.p-datepicker-input) { min-width: 0; }
.filter-row :deep(.common-field) { gap: 0; }
.filter-row > :deep(.p-button) { width: 34px; height: 34px; margin-top: 2px; }
.filter-empty { display: grid; place-items: center; gap: 6px; min-height: 128px; color: var(--erp-text-muted); background: #fff; border: 1px dashed var(--erp-border-strong); border-radius: var(--erp-control-radius); font-size: 0.8rem; }
.filter-empty i { color: var(--erp-accent); font-size: 1.12rem; }
.add-filter-button { margin-top: 2px; }

.add-filter-button:focus-visible { outline: 3px solid color-mix(in srgb, var(--erp-accent) 16%, transparent); outline-offset: 1px; }

@media (max-width: 760px) {
	.filter-column-headings { display: none; }
	.filter-rows { max-height: 58vh; }
	.filter-row { grid-template-columns: 1fr auto; }
	.filter-control { grid-column: 1 / -1; }
	.filter-row > :deep(.p-button) { grid-column: 2; grid-row: 1; }
	.filter-control__mobile-label { display: inline; color: #697970; font-size: var(--erp-font-size-min); font-weight: 750; letter-spacing: 0.04em; text-transform: uppercase; }
}
</style>
