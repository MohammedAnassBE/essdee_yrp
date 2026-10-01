<template>
	<div class="form-field" :class="{ 'form-field--wide': isWide }">
		<label v-if="showLabel" class="form-field__label" :for="inputId">
			{{ field.label || field.fieldname }}
			<span v-if="required" class="form-field__required" aria-hidden="true">*</span>
		</label>

		<LinkField
			v-if="isLink"
			:model-value="modelValue"
			:doctype="linkDoctype"
			:filters="linkFilters"
			:disabled="isDisabled"
			:invalid="invalid"
			:show-open-button="showOpenButton"
			@update:model-value="updateValue"
		/>
		<ToggleSwitch
			v-else-if="field.fieldtype === 'Check'"
			:input-id="inputId"
			:model-value="Boolean(Number(modelValue))"
			:disabled="isDisabled"
			@update:model-value="updateValue($event ? 1 : 0)"
		/>
		<Select
			v-else-if="field.fieldtype === 'Select'"
			:input-id="inputId"
			:model-value="modelValue"
			:options="selectOptions"
			:disabled="isDisabled"
			:invalid="invalid"
			show-clear
			fluid
			@update:model-value="updateValue"
		/>
		<InputNumber
			v-else-if="isNumber"
			:input-id="inputId"
			:model-value="numberValue"
			:disabled="isDisabled"
			:invalid="invalid"
			:min-fraction-digits="minimumFractionDigits"
			:max-fraction-digits="maximumFractionDigits"
			:suffix="field.fieldtype === 'Percent' ? '%' : undefined"
			:use-grouping="false"
			fluid
			@update:model-value="updateValue"
		/>
		<DatePicker
			v-else-if="field.fieldtype === 'Date'"
			:input-id="inputId"
			:model-value="dateValue"
			:disabled="isDisabled"
			:invalid="invalid"
			date-format="yy-mm-dd"
			show-icon
			fluid
			@update:model-value="updateDate"
		/>
		<DatePicker
			v-else-if="field.fieldtype === 'Datetime'"
			:input-id="inputId"
			:model-value="dateValue"
			:disabled="isDisabled"
			:invalid="invalid"
			date-format="yy-mm-dd"
			show-time
			show-seconds
			show-icon
			fluid
			@update:model-value="updateDatetime"
		/>
		<Textarea
			v-else-if="isTextArea"
			:id="inputId"
			:model-value="modelValue ?? ''"
			:disabled="isDisabled"
			:invalid="invalid"
			:rows="field.fieldtype === 'Small Text' ? 3 : 5"
			auto-resize
			fluid
			@update:model-value="updateValue"
		/>
		<InputText
			v-else
			:id="inputId"
			:model-value="modelValue ?? ''"
			:type="field.fieldtype === 'Password' ? 'password' : 'text'"
			:disabled="isDisabled"
			:invalid="invalid"
			fluid
			@update:model-value="updateValue"
		/>

		<small v-if="field.description" class="form-field__description">
			{{ field.description }}
		</small>
		<small v-if="error" class="form-field__error">{{ error }}</small>
	</div>
</template>

<script setup>
import DatePicker from "primevue/datepicker"
import InputNumber from "primevue/inputnumber"
import InputText from "primevue/inputtext"
import Select from "primevue/select"
import Textarea from "primevue/textarea"
import ToggleSwitch from "primevue/toggleswitch"
import { computed } from "vue"

import LinkField from "./LinkField.vue"

const props = defineProps({
	field: { type: Object, required: true },
	modelValue: { default: null },
	form: { type: Object, default: () => ({}) },
	disabled: { type: Boolean, default: false },
	invalid: { type: Boolean, default: false },
	required: { type: Boolean, default: false },
	error: { type: String, default: "" },
	showLabel: { type: Boolean, default: true },
	showOpenButton: { type: Boolean, default: true },
})

const emit = defineEmits(["update:modelValue", "change"])

const inputId = computed(() => `field-${props.field.fieldname}-${props.field.idx || "value"}`)
const isDisabled = computed(() => props.disabled || Boolean(props.field.read_only))
const isLink = computed(() => ["Link", "Dynamic Link"].includes(props.field.fieldtype))
const linkDoctype = computed(() => {
	if (props.field.fieldtype === "Dynamic Link") return props.form?.[props.field.options] || "DocType"
	return props.field.options || "DocType"
})
const isNumber = computed(() =>
	["Int", "Float", "Currency", "Percent"].includes(props.field.fieldtype),
)
const isTextArea = computed(() =>
	["Small Text", "Text", "Long Text", "Text Editor", "Code"].includes(props.field.fieldtype),
)
const isWide = computed(() => isTextArea.value)
const numberValue = computed(() => {
	if (props.modelValue === "" || props.modelValue === null || props.modelValue === undefined) return null
	const value = Number(props.modelValue)
	return Number.isFinite(value) ? value : null
})
const maximumFractionDigits = computed(() => {
	if (props.field.fieldtype === "Int") return 0
	const precision = Number(props.field.precision)
	return Number.isInteger(precision) && precision >= 0 ? precision : 6
})
const minimumFractionDigits = computed(() => {
	if (props.field.fieldtype === "Int") return 0
	const precision = Number(props.field.precision)
	return Number.isInteger(precision) && precision >= 0 ? precision : 0
})
const selectOptions = computed(() =>
	String(props.field.options || "")
		.split("\n")
		.map((option) => option.trim())
		.filter(Boolean),
)
const dateValue = computed(() => parseDate(props.modelValue))
const linkFilters = computed(() => parseLinkFilters(props.field.link_filters))

function updateValue(value) {
	emit("update:modelValue", value)
	emit("change", value)
}

function updateDate(value) {
	updateValue(value ? formatDate(value) : "")
}

function updateDatetime(value) {
	updateValue(value ? `${formatDate(value)} ${formatTime(value)}` : "")
}

function parseDate(value) {
	if (value instanceof Date) return value
	if (!value) return null
	const match = String(value).match(
		/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?/,
	)
	if (!match) return null
	return new Date(
		Number(match[1]),
		Number(match[2]) - 1,
		Number(match[3]),
		Number(match[4] || 0),
		Number(match[5] || 0),
		Number(match[6] || 0),
	)
}

function pad(value) {
	return String(value).padStart(2, "0")
}

function formatDate(value) {
	return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}`
}

function formatTime(value) {
	return `${pad(value.getHours())}:${pad(value.getMinutes())}:${pad(value.getSeconds())}`
}

function parseLinkFilters(value) {
	if (!value) return {}
	if (typeof value === "object") return value
	try {
		return JSON.parse(value)
	} catch {
		return {}
	}
}
</script>

<style scoped>
.form-field {
	display: grid;
	align-content: start;
	gap: 6px;
	min-width: 0;
}

.form-field__label {
	font-size: 0.8rem;
	font-weight: 650;
	color: #34413a;
}

.form-field__required,
.form-field__error {
	color: #c24145;
}

.form-field__description,
.form-field__error {
	font-size: 0.74rem;
	line-height: 1.35;
}

.form-field__description {
	color: #77827c;
}
</style>
