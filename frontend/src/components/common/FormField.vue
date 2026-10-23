<template>
	<div class="form-field" :class="{ 'form-field--wide': isWide }">
		<label v-if="showLabel" :id="labelId" class="form-field__label erp-field-label" :for="inputId">
			{{ field.label || field.fieldname }}
			<span v-if="required" class="form-field__required erp-required-mark" aria-hidden="true">*</span>
		</label>

		<LinkField
			v-if="isLink"
			:input-id="inputId"
			:model-value="modelValue"
			:reset-version="resetVersion"
			:doctype="linkDoctype"
			:fieldname="field.fieldname"
			:filters="linkFilters"
			:search-handler="searchHandler"
			:disabled="isDisabled"
			:invalid="invalid || Boolean(linkError)"
			:required="required"
			:aria-label="accessibleLabel"
			:aria-describedby="describedBy"
			:show-open-button="showOpenButton"
			:show-clear="showClear"
			:show-validation-message="false"
			@validation="linkError = $event.message"
			@update:model-value="updateValue"
		/>
		<ToggleSwitch
			v-else-if="field.fieldtype === 'Check'"
			:input-id="inputId"
			:model-value="Boolean(Number(modelValue))"
			:disabled="isDisabled"
			:invalid="invalid"
			:aria-labelledby="showLabel ? labelId : undefined"
			:aria-label="showLabel ? undefined : accessibleLabel"
			:pt="toggleSwitchPt"
			@update:model-value="updateValue($event ? 1 : 0)"
		/>
		<Select
			v-else-if="field.fieldtype === 'Select'"
			:input-id="inputId"
			:model-value="modelValue"
			:options="selectOptions"
			:disabled="isDisabled"
			:invalid="invalid"
			:aria-labelledby="showLabel ? labelId : undefined"
			:aria-label="showLabel ? undefined : accessibleLabel"
			:pt="selectPt"
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
			:required="required"
			:aria-labelledby="showLabel ? labelId : undefined"
			:aria-label="showLabel ? undefined : accessibleLabel"
			:pt="inputNumberPt"
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
			:aria-label="accessibleLabel"
			:disabled="isDisabled"
			:invalid="invalid"
			:required="required"
			:aria-describedby="describedBy"
			@update:model-value="updateValue"
		/>
		<DateTimeField
			v-else-if="field.fieldtype === 'Datetime'"
			:input-id="inputId"
			:model-value="modelValue"
			:aria-label="accessibleLabel"
			:disabled="isDisabled"
			:invalid="invalid"
			:required="required"
			:aria-describedby="describedBy"
			@update:model-value="updateValue"
		/>
		<TimeField
			v-else-if="field.fieldtype === 'Time'"
			:input-id="inputId"
			:model-value="modelValue"
			:aria-label="accessibleLabel"
			:disabled="isDisabled"
			:invalid="invalid"
			:required="required"
			:aria-describedby="describedBy"
			@update:model-value="updateValue"
		/>
		<Textarea
			v-else-if="isTextArea"
			:id="inputId"
			:model-value="textAreaValue"
			:disabled="isDisabled"
			:invalid="invalid"
			:required="required"
			:aria-required="required ? 'true' : undefined"
			:aria-labelledby="showLabel ? labelId : undefined"
			:aria-label="showLabel ? undefined : accessibleLabel"
			:aria-describedby="describedBy"
			:aria-invalid="invalid || undefined"
			:rows="textAreaRows"
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
			:required="required"
			:aria-required="required ? 'true' : undefined"
			:aria-labelledby="showLabel ? labelId : undefined"
			:aria-label="showLabel ? undefined : accessibleLabel"
			:aria-describedby="describedBy"
			:aria-invalid="invalid || undefined"
			fluid
			@update:model-value="updateValue"
		/>

		<small v-if="field.description" :id="descriptionId" class="form-field__description">
			{{ field.description }}
		</small>
		<small v-if="displayError" :id="errorId" class="form-field__error" role="alert">{{ displayError }}</small>
	</div>
</template>

<script setup>
import InputNumber from "primevue/inputnumber"
import InputText from "primevue/inputtext"
import Select from "primevue/select"
import Textarea from "primevue/textarea"
import ToggleSwitch from "primevue/toggleswitch"
import { computed, ref } from "vue"

import { plainTextFromHtml } from "../../utils/documentValues.js"

import DateField from "./DateField.vue"
import DateTimeField from "./DateTimeField.vue"
import LinkField from "./LinkField.vue"
import TimeField from "./TimeField.vue"

const props = defineProps({
	field: { type: Object, required: true },
	modelValue: { default: null },
	resetVersion: { type: Number, default: 0 },
	form: { type: Object, default: () => ({}) },
	disabled: { type: Boolean, default: false },
	invalid: { type: Boolean, default: false },
	required: { type: Boolean, default: false },
	error: { type: String, default: "" },
	showLabel: { type: Boolean, default: true },
	showOpenButton: { type: Boolean, default: true },
	showClear: { type: Boolean, default: false },
	inputId: { type: String, default: "" },
	ariaLabel: { type: String, default: "" },
	compact: { type: Boolean, default: false },
	searchHandler: { type: Function, default: null },
})

const emit = defineEmits(["update:modelValue", "change"])

const linkError = ref("")
const displayError = computed(() => linkError.value || props.error)
const inputId = computed(() => props.inputId || `field-${props.field.fieldname}-${props.field.idx || "value"}`)
const labelId = computed(() => `${inputId.value}-label`)
const accessibleLabel = computed(() => props.ariaLabel || props.field.label || props.field.fieldname)
const descriptionId = computed(() => `${inputId.value}-description`)
const errorId = computed(() => `${inputId.value}-error`)
const describedBy = computed(() => [props.field.description ? descriptionId.value : "", displayError.value ? errorId.value : ""].filter(Boolean).join(" ") || undefined)
const focusableControlAria = computed(() => ({
	"aria-required": props.required ? "true" : undefined,
	"aria-describedby": describedBy.value,
	"aria-invalid": props.invalid ? "true" : undefined,
}))
const toggleSwitchPt = computed(() => ({
	input: {
		...focusableControlAria.value,
		required: props.required || undefined,
	},
}))
const selectPt = computed(() => ({ label: focusableControlAria.value }))
const inputNumberPt = computed(() => ({
	pcInputText: {
		root: {
			...focusableControlAria.value,
			required: props.required || undefined,
		},
	},
}))
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
const textAreaRows = computed(() => props.compact
	? (props.field.fieldtype === "Small Text" ? 2 : 3)
	: (props.field.fieldtype === "Small Text" ? 3 : 5))
const textAreaValue = computed(() => isDisabled.value && typeof props.modelValue === "string"
	? plainTextFromHtml(props.modelValue)
	: (props.modelValue ?? ""))
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

.form-field__error {
	color: var(--erp-danger);
}

.form-field__description,
.form-field__error {
	font-size: var(--erp-font-size-caption);
	line-height: 1.35;
}

.form-field__description {
	color: var(--erp-text-muted);
}

.form-field__error {
	padding-left: 8px;
	border-left: 2px solid var(--erp-danger);
}

</style>
