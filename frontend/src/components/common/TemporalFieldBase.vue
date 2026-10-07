<template>
	<div
		class="erp-date-time-field"
		:class="{
			'erp-date-time-field--invalid': invalid,
			'erp-date-time-field--disabled': disabled,
		}"
	>
		<label v-if="label" :id="labelId" class="erp-date-time-field__label" :for="resolvedInputId">
			{{ label }}
			<b v-if="required" aria-hidden="true">*</b>
		</label>
		<DatePicker
			:input-id="resolvedInputId"
			:model-value="pickerValue"
			:selection-mode="selectionMode"
			:date-format="dateFormat"
			:show-time="mode === 'datetime'"
			:time-only="mode === 'time'"
			:show-seconds="showSeconds && mode !== 'date'"
			hour-format="24"
			show-icon
			:icon="mode === 'time' ? 'pi pi-clock' : 'pi pi-calendar'"
			:show-button-bar="showButtonBar && mode !== 'time'"
			:show-clear="showClear"
			:manual-input="allowsManualInput"
			:placeholder="resolvedPlaceholder"
			:disabled="disabled"
			:readonly="readonly"
			:invalid="invalid"
			:required="required"
			:min-date="minDate"
			:max-date="maxDate"
			:aria-labelledby="label ? labelId : undefined"
			:aria-label="label ? undefined : ariaLabel"
			:fluid="fluid"
			class="erp-date-time-picker"
			panel-class="erp-date-time-panel"
			:pt="pickerPt"
			@update:model-value="updateValue"
			@blur="emit('blur', $event)"
		/>
		<small v-if="helpText" :id="helpId" class="erp-date-time-field__help">{{ helpText }}</small>
		<small v-if="error" :id="errorId" class="erp-date-time-field__error" role="alert">{{ error }}</small>
	</div>
</template>

<script setup>
import DatePicker from "primevue/datepicker"
import { computed, useId } from "vue"

import { normaliseFrappeTime } from "../../utils/documentValues.js"

const props = defineProps({
	modelValue: { type: [String, Date, Array], default: "" },
	mode: {
		type: String,
		default: "date",
		validator: (value) => ["date", "datetime", "time"].includes(value),
	},
	valueType: {
		type: String,
		default: "string",
		validator: (value) => ["string", "date"].includes(value),
	},
	selectionMode: {
		type: String,
		default: "single",
		validator: (value) => ["single", "multiple", "range"].includes(value),
	},
	label: { type: String, default: "" },
	ariaLabel: { type: String, default: "" },
	ariaDescribedby: { type: String, default: "" },
	inputId: { type: String, default: "" },
	placeholder: { type: String, default: "" },
	helpText: { type: String, default: "" },
	error: { type: String, default: "" },
	disabled: { type: Boolean, default: false },
	readonly: { type: Boolean, default: false },
	invalid: { type: Boolean, default: false },
	required: { type: Boolean, default: false },
	showClear: { type: Boolean, default: false },
	showButtonBar: { type: Boolean, default: true },
	showSeconds: { type: Boolean, default: true },
	manualInput: { type: Boolean, default: true },
	fluid: { type: Boolean, default: true },
	minDate: { type: Date, default: undefined },
	maxDate: { type: Date, default: undefined },
})

const emit = defineEmits(["update:modelValue", "change", "blur"])
const componentId = useId()
const resolvedInputId = computed(() => props.inputId || `erp-temporal-${componentId}`)
const labelId = computed(() => `${resolvedInputId.value}-label`)
const helpId = computed(() => `${resolvedInputId.value}-help`)
const errorId = computed(() => `${resolvedInputId.value}-error`)
const describedBy = computed(() => [
	props.ariaDescribedby,
	props.helpText ? helpId.value : "",
	props.error ? errorId.value : "",
].filter(Boolean).join(" ") || undefined)
const dateFormat = computed(() => "dd-mm-yy")
const allowsManualInput = computed(() => props.manualInput && props.mode === "date")
const pickerActionLabel = computed(() => {
	if (props.mode === "time") return "Choose time"
	if (props.mode === "datetime") return "Choose date and time"
	return "Choose date"
})
const pickerPt = computed(() => ({
	panel: { "aria-label": pickerActionLabel.value },
	dropdown: {
		"aria-label": pickerActionLabel.value,
		title: pickerActionLabel.value,
	},
	pcInputText: {
		root: {
			required: props.required || undefined,
			"aria-required": props.required ? "true" : undefined,
			"aria-describedby": describedBy.value,
			"aria-invalid": props.invalid ? "true" : undefined,
		},
	},
}))
const resolvedPlaceholder = computed(() => {
	if (props.placeholder) return props.placeholder
	if (props.mode === "time") return "HH:MM:SS"
	if (props.selectionMode === "range") return "DD-MM-YYYY - DD-MM-YYYY"
	return props.mode === "datetime" ? "DD-MM-YYYY HH:MM:SS" : "DD-MM-YYYY"
})
const pickerValue = computed(() => mapValue(props.modelValue, parseValue))

function updateValue(value) {
	const nextValue = props.valueType === "date" ? value : mapValue(value, serialiseValue)
	emit("update:modelValue", nextValue ?? "")
	emit("change", nextValue ?? "")
}

function mapValue(value, transform) {
	if (Array.isArray(value)) return value.map((item) => item == null ? null : transform(item))
	if (value === null || value === undefined || value === "") return null
	return transform(value)
}

function parseValue(value) {
	if (value instanceof Date) return new Date(value.getTime())
	const text = String(value || "").trim()
	if (!text) return null

	if (props.mode === "time") {
		const normalized = normaliseFrappeTime(text)
		const match = normalized.match(/^(\d{2}):(\d{2}):(\d{2})$/)
		if (!match) return null
		const result = new Date()
		result.setHours(Number(match[1]), Number(match[2]), Number(match[3] || 0), 0)
		return result
	}

	const iso = text.match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?$/)
	if (iso) return localDate(iso[1], iso[2], iso[3], iso[4], iso[5], iso[6])
	const display = text.match(/^(\d{2})-(\d{2})-(\d{4})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?$/)
	if (display) return localDate(display[3], display[2], display[1], display[4], display[5], display[6])
	return null
}

function localDate(year, month, day, hour = 0, minute = 0, second = 0) {
	const value = new Date(Number(year), Number(month) - 1, Number(day), Number(hour || 0), Number(minute || 0), Number(second || 0))
	if (
		value.getFullYear() !== Number(year)
		|| value.getMonth() !== Number(month) - 1
		|| value.getDate() !== Number(day)
	) return null
	return value
}

function serialiseValue(value) {
	if (!(value instanceof Date) || Number.isNaN(value.getTime())) return ""
	if (props.mode === "time") return formatTime(value)
	const date = `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}`
	return props.mode === "datetime" ? `${date} ${formatTime(value)}` : date
}

function formatTime(value) {
	return `${pad(value.getHours())}:${pad(value.getMinutes())}:${pad(value.getSeconds())}`
}

function pad(value) {
	return String(value).padStart(2, "0")
}
</script>

<style scoped>
.erp-date-time-field {
	display: grid;
	align-content: start;
	gap: 6px;
	min-width: 0;
	width: 100%;
}

.erp-date-time-field__label {
	color: var(--erp-text);
	font-size: var(--erp-font-size-caption);
	font-weight: 680;
	line-height: 1.25;
}

.erp-date-time-field:focus-within .erp-date-time-field__label {
	color: var(--erp-accent-hover);
}

.erp-date-time-field__label b,
.erp-date-time-field__error {
	color: var(--erp-danger);
}

.erp-date-time-field__help,
.erp-date-time-field__error {
	font-size: var(--erp-font-size-min);
	line-height: 1.35;
}

.erp-date-time-field__help {
	color: var(--erp-text-muted);
}

.erp-date-time-picker {
	width: 100%;
	min-width: 0;
}

.erp-date-time-field :deep(.erp-date-time-picker .p-datepicker-input) {
	min-width: 0;
	background: var(--erp-surface);
	border-color: var(--erp-border-strong);
	box-shadow: var(--erp-shadow-xs);
	font-variant-numeric: tabular-nums;
}

.erp-date-time-field :deep(.erp-date-time-picker:focus-within .p-datepicker-input) {
	border-color: var(--erp-accent);
	box-shadow: 0 0 0 3px color-mix(in srgb, var(--erp-accent) 11%, transparent);
	outline: 2px solid var(--erp-accent-dark);
	outline-offset: -2px;
}

.erp-date-time-field :deep(.erp-date-time-picker .p-datepicker-dropdown) {
	width: var(--erp-control-height);
	min-width: var(--erp-control-height);
	color: var(--erp-accent);
	background: var(--erp-accent-soft);
	border-color: var(--erp-border-strong);
	border-left: 0;
}

.erp-date-time-field :deep(.erp-date-time-picker .p-datepicker-dropdown:hover) {
	color: var(--erp-accent-hover);
	background: color-mix(in srgb, var(--erp-accent-soft) 72%, var(--erp-accent-border));
}

.erp-date-time-field :deep(.erp-date-time-picker .p-datepicker-dropdown:active) {
	transform: translateY(1px);
}

.erp-date-time-field--invalid :deep(.p-datepicker-input),
.erp-date-time-field--invalid :deep(.p-datepicker-dropdown) {
	border-color: var(--erp-danger);
}

</style>
