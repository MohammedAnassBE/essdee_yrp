<template>
	<section class="quick-filters">
		<div class="quick-filters__grid">
			<div v-for="field in fields" :key="field.fieldname" class="quick-filter-field">
				<label :for="`quick-filter-${field.fieldname}`">{{ field.label }}</label>

				<LinkField
					v-if="field.fieldtype === 'Link'"
					:model-value="modelValue[field.fieldname] || ''"
					:doctype="field.options"
					:filters="linkFilters(field)"
					:placeholder="`All ${field.label}`"
					match-visible-only
					show-clear
					:show-open-button="false"
					@update:model-value="update(field, $event)"
				/>
				<Select
					v-else-if="field.fieldtype === 'Select'"
					:input-id="`quick-filter-${field.fieldname}`"
					:model-value="modelValue[field.fieldname] || ''"
					:options="selectOptions(field)"
					:placeholder="`All ${field.label}`"
					show-clear
					fluid
					@update:model-value="update(field, $event)"
				/>
				<Select
					v-else-if="field.fieldtype === 'Check'"
					:input-id="`quick-filter-${field.fieldname}`"
					:model-value="modelValue[field.fieldname]"
					:options="checkOptions"
					option-label="label"
					option-value="value"
					:placeholder="`All ${field.label}`"
					show-clear
					fluid
					@update:model-value="update(field, $event)"
				/>
				<DateField
					v-else-if="field.fieldtype === 'Date'"
					:input-id="`quick-filter-${field.fieldname}`"
					:model-value="modelValue[field.fieldname] || ''"
					:aria-label="field.label"
					:placeholder="`All ${field.label}`"
					show-clear
					@update:model-value="update(field, $event)"
				/>
				<DateTimeField
					v-else-if="field.fieldtype === 'Datetime'"
					:input-id="`quick-filter-${field.fieldname}`"
					:model-value="modelValue[field.fieldname] || ''"
					:aria-label="field.label"
					:placeholder="`All ${field.label}`"
					show-clear
					@update:model-value="update(field, $event)"
				/>
				<TimeField
					v-else-if="field.fieldtype === 'Time'"
					:input-id="`quick-filter-${field.fieldname}`"
					:model-value="modelValue[field.fieldname] || ''"
					:aria-label="field.label"
					:placeholder="`All ${field.label}`"
					show-clear
					@update:model-value="update(field, $event)"
				/>
				<InputNumber
					v-else-if="numberTypes.has(field.fieldtype)"
					:input-id="`quick-filter-${field.fieldname}`"
					:model-value="numberValue(modelValue[field.fieldname])"
					:placeholder="`All ${field.label}`"
					:use-grouping="false"
					fluid
					@update:model-value="update(field, $event)"
				/>
				<InputText
					v-else
					:id="`quick-filter-${field.fieldname}`"
					:model-value="modelValue[field.fieldname] || ''"
					:placeholder="`All ${field.label}`"
					fluid
					@update:model-value="update(field, $event)"
				/>
			</div>
		</div>
	</section>
</template>

<script setup>
import InputNumber from "primevue/inputnumber"
import InputText from "primevue/inputtext"
import Select from "primevue/select"
import DateField from "./DateField.vue"
import DateTimeField from "./DateTimeField.vue"
import LinkField from "./LinkField.vue"
import TimeField from "./TimeField.vue"

const props = defineProps({
	modelValue: { type: Object, default: () => ({}) },
	fields: { type: Array, default: () => [] },
})

const emit = defineEmits(["update:modelValue", "change"])
const numberTypes = new Set(["Int", "Float", "Currency", "Percent"])
const checkOptions = [
	{ label: "Yes", value: 1 },
	{ label: "No", value: 0 },
]
function update(field, value) {
	const values = { ...props.modelValue }
	if (hasValue(value)) values[field.fieldname] = value
	else delete values[field.fieldname]
	emit("update:modelValue", values)
	emit("change", { values, field })
}

function hasValue(value) {
	return value !== null && value !== undefined && value !== ""
}

function selectOptions(field) {
	return String(field.options || "")
		.split("\n")
		.map((option) => option.trim())
		.filter(Boolean)
}

function numberValue(value) {
	if (!hasValue(value)) return null
	const number = Number(value)
	return Number.isFinite(number) ? number : null
}

function linkFilters(field) {
	if (!field.link_filters) return {}
	if (typeof field.link_filters === "object") return field.link_filters
	try {
		return JSON.parse(field.link_filters)
	} catch {
		return {}
	}
}
</script>

<style scoped>
.quick-filters {
	display: grid;
	gap: 8px;
	padding: 12px;
	background: var(--erp-surface-soft);
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-control-radius);
}

.quick-filters__grid {
	display: grid;
	grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
	gap: 10px;
}

.quick-filter-field {
	display: grid;
	gap: 6px;
	min-width: 0;
}

.quick-filter-field > label {
	color: #506159;
	font-size: var(--erp-font-size-caption);
	font-weight: 650;
}

.quick-filter-field :deep(.p-inputtext),
.quick-filter-field :deep(.p-select),
.quick-filter-field :deep(.p-autocomplete-input),
.quick-filter-field :deep(.p-inputnumber-input) {
	height: var(--erp-control-height);
	background: var(--erp-surface);
	border-color: var(--erp-border-strong);
	border-radius: var(--erp-control-radius);
	box-shadow: none;
	transition:
		border-color 160ms ease,
		box-shadow 160ms ease;
}

.quick-filter-field :deep(.p-inputtext:focus),
.quick-filter-field :deep(.p-select.p-focus),
.quick-filter-field :deep(.p-autocomplete:focus-within .p-inputtext),
.quick-filter-field :deep(.p-inputnumber:focus-within .p-inputnumber-input) {
	border-color: color-mix(in srgb, var(--list-accent) 48%, white);
	box-shadow: 0 0 0 3px color-mix(in srgb, var(--list-accent) 11%, transparent);
}

@media (max-width: 600px) {
	.quick-filters__grid {
		grid-template-columns: 1fr;
	}

}
</style>
