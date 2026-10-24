<template>
	<div
		class="erp-time-field"
		:class="{ 'erp-time-field--invalid': isInvalid, 'erp-time-field--disabled': disabled }"
	>
		<label v-if="label" :id="labelId" class="erp-time-field__label erp-field-label" :for="resolvedInputId">
			{{ labelParts.text }}
			<span v-if="required || labelParts.required" class="erp-required-mark" aria-hidden="true">*</span>
		</label>
		<div ref="controlRef" class="erp-time-field__control">
			<InputText
				:id="resolvedInputId"
				v-model="draft"
				class="erp-time-field__input"
				autocomplete="off"
				inputmode="text"
				:placeholder="resolvedPlaceholder"
				:disabled="disabled"
				:readonly="readonly"
				:invalid="isInvalid"
				:required="required"
				:aria-required="required ? 'true' : undefined"
				:aria-invalid="isInvalid ? 'true' : undefined"
				:aria-describedby="describedBy"
				:aria-labelledby="label ? labelId : undefined"
				:aria-label="label ? undefined : ariaLabel || undefined"
				@blur="handleBlur"
				@keydown="handleKeydown"
			/>
			<template v-if="isEditable">
				<button
					type="button"
					class="erp-time-field__now"
					title="Set current time"
					:aria-label="`Set ${ariaLabel || labelParts.text || 'time'} to now`"
					@click="setNow"
				>Now</button>
				<button
					type="button"
					class="erp-time-field__toggle"
					title="Choose time"
					aria-label="Choose time"
					aria-haspopup="dialog"
					@click="togglePanel"
				><i class="pi pi-clock" aria-hidden="true" /></button>
			</template>
		</div>
		<Popover ref="panelRef" class="erp-time-panel" :pt="{ content: { 'aria-label': 'Choose time' } }">
			<div class="erp-time-panel__body">
				<div class="erp-time-panel__section">
					<div class="erp-time-panel__heading">Hour</div>
					<div class="erp-time-panel__grid erp-time-panel__grid--hours">
						<button
							v-for="hour in hourOptions"
							:key="hour.value"
							type="button"
							class="erp-time-panel__cell"
							:class="{ 'is-selected': hour.value === selectedHour }"
							@click="pick('hour', hour.value)"
						>{{ hour.label }}</button>
					</div>
					<div v-if="twelveHour" class="erp-time-panel__meridiem">
						<button
							v-for="meridiem in ['AM', 'PM']"
							:key="meridiem"
							type="button"
							class="erp-time-panel__cell"
							:class="{ 'is-selected': selectedMeridiem === meridiem }"
							@click="pickMeridiem(meridiem)"
						>{{ meridiem }}</button>
					</div>
				</div>
				<div class="erp-time-panel__section">
					<div class="erp-time-panel__heading">Minute</div>
					<div class="erp-time-panel__grid erp-time-panel__grid--minutes">
						<button
							v-for="minute in minuteOptions"
							:key="minute"
							type="button"
							class="erp-time-panel__cell"
							:class="{ 'is-selected': minute === selectedMinute }"
							@click="pick('minute', minute)"
						>{{ String(minute).padStart(2, "0") }}</button>
					</div>
				</div>
			</div>
			<div class="erp-time-panel__footer">
				<button type="button" class="erp-time-panel__action" @click="setNow">Now</button>
				<button v-if="canClear" type="button" class="erp-time-panel__action" @click="clear">Clear</button>
			</div>
		</Popover>
		<small v-if="helpText" :id="helpId" class="erp-time-field__help">{{ helpText }}</small>
		<small v-if="visibleError" :id="errorId" class="erp-time-field__error" role="alert">{{ visibleError }}</small>
	</div>
</template>

<script setup>
import InputText from "primevue/inputtext"
import Popover from "primevue/popover"
import { computed, ref, useId, watch } from "vue"

import { normaliseFrappeTime } from "../../utils/documentValues.js"
import {
	currentFrappeTime,
	formatTimeDisplay,
	parseTimeInput,
	setTimePart,
	usesTwelveHourClock,
} from "../../utils/timeInput.js"

const props = defineProps({
	modelValue: { type: [String, Date], default: "" },
	valueType: {
		type: String,
		default: "string",
		validator: (value) => ["string", "date"].includes(value),
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
})

const emit = defineEmits(["update:modelValue", "change", "blur"])
const componentId = useId()
const resolvedInputId = computed(() => props.inputId || `erp-time-${componentId}`)
const labelId = computed(() => `${resolvedInputId.value}-label`)
const helpId = computed(() => `${resolvedInputId.value}-help`)
const errorId = computed(() => `${resolvedInputId.value}-error`)
const twelveHour = usesTwelveHourClock()
const controlRef = ref(null)
const panelRef = ref(null)
const draft = ref("")
const typingError = ref("")

const labelParts = computed(() => {
	const match = /^(.*?)\s*\*$/.exec(props.label || "")
	return match ? { text: match[1], required: true } : { text: props.label, required: false }
})
const storedTime = computed(() => {
	const value = props.modelValue
	if (value instanceof Date) return Number.isNaN(value.getTime()) ? "" : currentFrappeTime(value)
	return normaliseFrappeTime(value)
})
const displayValue = computed(() => formatTimeDisplay(storedTime.value, { twelveHour }))
const isEditable = computed(() => !props.disabled && !props.readonly)
const canClear = computed(() => props.showClear || !(props.required || labelParts.value.required))
const visibleError = computed(() => typingError.value || props.error)
const isInvalid = computed(() => props.invalid || Boolean(typingError.value))
const resolvedPlaceholder = computed(() => props.placeholder || (twelveHour ? "h:mm AM" : "HH:MM"))
const describedBy = computed(() => [
	props.ariaDescribedby,
	props.helpText ? helpId.value : "",
	visibleError.value ? errorId.value : "",
].filter(Boolean).join(" ") || undefined)

const hourOptions = computed(() => twelveHour
	? [12, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11].map((hour) => ({ label: String(hour), value: hour % 12 + (selectedMeridiem.value === "PM" ? 12 : 0) }))
	: Array.from({ length: 24 }, (_, hour) => ({ label: String(hour).padStart(2, "0"), value: hour })))
const minuteOptions = Array.from({ length: 12 }, (_, index) => index * 5)
const selectedHour = computed(() => storedTime.value ? Number(storedTime.value.slice(0, 2)) : null)
const selectedMinute = computed(() => storedTime.value ? Number(storedTime.value.slice(3, 5)) : null)
const selectedMeridiem = computed(() => (selectedHour.value ?? 0) >= 12 ? "PM" : "AM")

watch(displayValue, (value) => {
	draft.value = value
	typingError.value = ""
}, { immediate: true })

function commit(value) {
	typingError.value = ""
	draft.value = formatTimeDisplay(value, { twelveHour })
	if (value === storedTime.value) return
	const nextValue = props.valueType === "date" && value ? toDate(value) : value
	emit("update:modelValue", nextValue)
	emit("change", nextValue)
}

function toDate(value) {
	const [hours, minutes, seconds] = value.split(":").map(Number)
	const result = new Date()
	result.setHours(hours, minutes, seconds, 0)
	return result
}

function commitDraft() {
	if (draft.value.trim() === displayValue.value) {
		typingError.value = ""
		return true
	}
	const parsed = parseTimeInput(draft.value)
	if (parsed === null) {
		typingError.value = "Enter a time like 14:30, 1430 or 2:30 pm."
		return false
	}
	if (parsed === "" && !canClear.value) {
		draft.value = displayValue.value
		return true
	}
	commit(parsed)
	return true
}

function handleBlur(event) {
	commitDraft()
	emit("blur", event)
}

function handleKeydown(event) {
	if (event.key === "Enter") {
		if (!commitDraft()) event.preventDefault()
	} else if (event.key === "Escape" && draft.value !== displayValue.value) {
		event.stopPropagation()
		draft.value = displayValue.value
		typingError.value = ""
	} else if (event.key === "ArrowDown" && event.altKey && isEditable.value) {
		event.preventDefault()
		togglePanel(event)
	}
}

function togglePanel(event) {
	panelRef.value?.toggle(event, controlRef.value)
}

function setNow() {
	commit(currentFrappeTime())
	panelRef.value?.hide()
}

function clear() {
	commit("")
	panelRef.value?.hide()
}

function pick(part, amount) {
	commit(setTimePart(storedTime.value, part, amount))
	if (part === "minute") panelRef.value?.hide()
}

function pickMeridiem(meridiem) {
	const hour = selectedHour.value ?? 0
	commit(setTimePart(storedTime.value, "hour", hour % 12 + (meridiem === "PM" ? 12 : 0)))
}
</script>

<style scoped>
.erp-time-field {
	display: grid;
	align-content: start;
	gap: 6px;
	min-width: 0;
	width: 100%;
}

.erp-time-field__control {
	display: flex;
	min-width: 0;
	container-type: inline-size;
}

.erp-time-field__input {
	flex: 1 1 auto;
	min-width: 0;
	font-variant-numeric: tabular-nums;
}

.erp-time-field__control:has(button) .erp-time-field__input {
	border-top-right-radius: 0;
	border-bottom-right-radius: 0;
}

.erp-time-field__now,
.erp-time-field__toggle {
	flex: 0 0 auto;
	min-width: var(--erp-control-height);
	padding: 0 10px;
	color: var(--erp-text-muted);
	font: inherit;
	font-size: var(--erp-font-size-caption);
	font-weight: var(--erp-font-weight-semibold);
	background: var(--erp-surface);
	border: 1px solid var(--erp-border-strong);
	border-left: 0;
	cursor: pointer;
}

.erp-time-field__toggle {
	border-top-right-radius: var(--erp-control-radius);
	border-bottom-right-radius: var(--erp-control-radius);
}

.erp-time-field__now:hover,
.erp-time-field__toggle:hover {
	color: var(--erp-accent);
	background: var(--erp-surface-hover);
}

.erp-time-field__now:focus-visible,
.erp-time-field__toggle:focus-visible {
	outline: 2px solid var(--erp-accent);
	outline-offset: -2px;
}

@container (max-width: 10rem) {
	.erp-time-field__now {
		display: none;
	}
}

.erp-time-field__help,
.erp-time-field__error {
	font-size: var(--erp-font-size-caption);
	line-height: 1.35;
}

.erp-time-field__help {
	color: var(--erp-text-muted);
}

.erp-time-field__error {
	color: var(--erp-danger);
}

.erp-time-field--invalid .erp-time-field__now,
.erp-time-field--invalid .erp-time-field__toggle {
	border-color: var(--erp-danger);
}
</style>

<style>
.erp-time-panel.p-popover {
	color: var(--erp-text);
	font-family: var(--erp-font-family);
	font-size: var(--erp-font-size-table);
	background: var(--erp-surface);
	border: 1px solid var(--erp-border-strong);
	border-radius: var(--erp-panel-radius);
	box-shadow: var(--erp-shadow-dialog);
}

.erp-time-panel .p-popover-content {
	padding: 10px;
}

.erp-time-panel__body {
	display: flex;
	gap: 14px;
}

.erp-time-panel__heading {
	margin-bottom: 6px;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	font-weight: var(--erp-font-weight-semibold);
	text-transform: uppercase;
}

.erp-time-panel__grid {
	display: grid;
	gap: 3px;
}

.erp-time-panel__grid--hours {
	grid-template-columns: repeat(6, 34px);
}

.erp-time-panel__grid--minutes {
	grid-template-columns: repeat(3, 34px);
}

.erp-time-panel__meridiem {
	display: grid;
	grid-template-columns: repeat(2, 1fr);
	gap: 3px;
	margin-top: 6px;
}

.erp-time-panel__cell,
.erp-time-panel__action {
	height: 30px;
	color: var(--erp-text);
	font: inherit;
	font-variant-numeric: tabular-nums;
	background: transparent;
	border: 0;
	border-radius: 7px;
	cursor: pointer;
}

.erp-time-panel__cell:hover,
.erp-time-panel__action:hover {
	color: var(--erp-accent-hover);
	background: var(--erp-accent-soft);
}

.erp-time-panel__cell.is-selected {
	color: var(--erp-on-accent);
	font-weight: var(--erp-font-weight-semibold);
	background: var(--erp-accent);
}

.erp-time-panel__cell:focus-visible,
.erp-time-panel__action:focus-visible {
	outline: 2px solid var(--erp-accent);
	outline-offset: 1px;
}

.erp-time-panel__footer {
	display: flex;
	justify-content: space-between;
	margin-top: 8px;
	padding-top: 8px;
	border-top: 1px solid var(--erp-border);
}

.erp-time-panel__action {
	padding: 0 10px;
	color: var(--erp-accent);
	font-weight: var(--erp-font-weight-semibold);
}
</style>
