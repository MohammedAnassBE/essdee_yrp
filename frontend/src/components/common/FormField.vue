<template>
	<div class="form-field" :class="{ 'form-field--wide': isWide }">
		<label v-if="showLabel" class="form-field__label" :for="inputId">
			{{ field.label || field.fieldname }}
			<span v-if="required" class="form-field__required" aria-hidden="true">*</span>
		</label>

		<LinkField
			v-if="isLink"
			:input-id="inputId"
			:model-value="modelValue"
			:doctype="linkDoctype"
			:filters="linkFilters"
			:search-handler="searchHandler"
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
		<DateField
			v-else-if="field.fieldtype === 'Date'"
			:input-id="inputId"
			:model-value="modelValue"
			:aria-label="field.label || field.fieldname"
			:disabled="isDisabled"
			:invalid="invalid"
			:required="required"
			@update:model-value="updateValue"
		/>
		<DateTimeField
			v-else-if="field.fieldtype === 'Datetime'"
			:input-id="inputId"
			:model-value="modelValue"
			:aria-label="field.label || field.fieldname"
			:disabled="isDisabled"
			:invalid="invalid"
			:required="required"
			@update:model-value="updateValue"
		/>
		<TimeField
			v-else-if="field.fieldtype === 'Time'"
			:input-id="inputId"
			:model-value="modelValue"
			:aria-label="field.label || field.fieldname"
			:disabled="isDisabled"
			:invalid="invalid"
			:required="required"
			@update:model-value="updateValue"
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
		<small v-if="error" class="form-field__error" role="alert">{{ error }}</small>
	</div>
</template>

<script setup>
import InputNumber from "primevue/inputnumber"
import InputText from "primevue/inputtext"
import Select from "primevue/select"
import Textarea from "primevue/textarea"
import ToggleSwitch from "primevue/toggleswitch"
import { computed } from "vue"

import DateField from "./DateField.vue"
import DateTimeField from "./DateTimeField.vue"
import LinkField from "./LinkField.vue"
import TimeField from "./TimeField.vue"

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
	searchHandler: { type: Function, default: null },
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
const linkFilters = computed(() => parseLinkFilters(props.field.link_filters))

function updateValue(value) {
	emit("update:modelValue", value)
	emit("change", value)
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
	color: var(--erp-text);
	font-size: var(--erp-font-size-caption);
	font-weight: 680;
	line-height: 1.25;
	transition: color var(--erp-transition-fast);
}

.form-field:focus-within .form-field__label {
	color: var(--erp-accent-hover);
}

.form-field__required,
.form-field__error {
	color: #c24145;
}

.form-field__description,
.form-field__error {
	font-size: var(--erp-font-size-min);
	line-height: 1.35;
}

.form-field__description {
	color: var(--erp-text-muted);
}

.form-field__error {
	padding-left: 8px;
	border-left: 2px solid var(--erp-danger);
}

.form-field :deep(.p-inputtext),
.form-field :deep(.p-select),
.form-field :deep(.p-inputnumber-input),
.form-field :deep(.p-textarea) {
	background: #fff;
	border-color: var(--erp-border-strong);
	box-shadow: 0 1px 2px rgb(24 53 39 / 3%);
}

.form-field :deep(.p-inputtext:enabled:hover),
.form-field :deep(.p-select:not(.p-disabled):hover),
.form-field :deep(.p-inputnumber:not(.p-disabled):hover .p-inputnumber-input),
.form-field :deep(.p-textarea:enabled:hover) {
	border-color: color-mix(in srgb, var(--erp-accent) 32%, var(--erp-border-strong));
}

.form-field :deep(.p-inputtext:focus),
.form-field :deep(.p-select.p-focus),
.form-field :deep(.p-inputnumber:focus-within .p-inputnumber-input),
.form-field :deep(.p-textarea:focus) {
	border-color: var(--erp-accent);
	box-shadow: 0 0 0 3px color-mix(in srgb, var(--erp-accent) 11%, transparent);
}
</style>
