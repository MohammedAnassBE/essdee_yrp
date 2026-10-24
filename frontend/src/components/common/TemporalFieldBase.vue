<template>
	<div
		class="erp-date-time-field"
		:class="{
			'erp-date-time-field--invalid': invalid,
			'erp-date-time-field--disabled': disabled,
		}"
	>
		<label v-if="label" :id="labelId" class="erp-date-time-field__label erp-field-label" :for="resolvedInputId">
			{{ labelParts.text }}
			<span v-if="required || labelParts.required" class="erp-required-mark" aria-hidden="true">*</span>
		</label>
		<DatePicker
			:input-id="resolvedInputId"
			:model-value="pickerValue"
			:selection-mode="selectionMode"
			:date-format="dateFormat"
			:show-time="mode === 'datetime'"
			:show-seconds="showSeconds && mode === 'datetime'"
			hour-format="24"
			show-icon
			icon="pi pi-calendar"
			:show-button-bar="showButtonBar"
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

const props = defineProps({
	modelValue: { type: [String, Date, Array], default: "" },
	mode: {
		type: String,
		default: "date",
		validator: (value) => ["date", "datetime"].includes(value),
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

const labelParts = computed(() => {
	const match = /^(.*?)\s*\*$/.exec(props.label || "")
	return match ? { text: match[1], required: true } : { text: props.label, required: false }
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

.erp-date-time-field__error {
	color: var(--erp-danger);
}

.erp-date-time-field__help,
.erp-date-time-field__error {
	font-size: var(--erp-font-size-caption);
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
	font-variant-numeric: tabular-nums;
}

.erp-date-time-field :deep(.erp-date-time-picker .p-datepicker-dropdown) {
	width: var(--erp-control-height);
	min-width: var(--erp-control-height);
	color: var(--erp-text-muted);
	background: var(--erp-surface);
	border-color: var(--erp-border-strong);
	border-left: 0;
}

.erp-date-time-field :deep(.erp-date-time-picker .p-datepicker-dropdown:hover) {
	color: var(--erp-accent);
	background: var(--erp-surface-hover);
}

@media (prefers-reduced-motion: no-preference) {
	.erp-date-time-field :deep(.erp-date-time-picker .p-datepicker-dropdown:active) {
		transform: translateY(1px);
	}
}

.erp-date-time-field--invalid :deep(.p-datepicker-input),
.erp-date-time-field--invalid :deep(.p-datepicker-dropdown) {
	border-color: var(--erp-danger);
}

</style>
