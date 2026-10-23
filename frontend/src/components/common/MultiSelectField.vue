<template>
	<label class="common-field">
		<span v-if="label" class="common-field__label erp-field-label">{{ label }}</span>
		<MultiSelect
			v-bind="$attrs"
			:model-value="modelValue"
			:options="options"
			:option-label="optionLabel"
			:option-value="optionValue"
			:placeholder="placeholder"
			:disabled="disabled"
			:invalid="invalid"
			:filter="filter"
			:filter-fields="filterFields || [optionLabel, 'description']"
			:display="display"
			:max-selected-labels="maxSelectedLabels"
			fluid
			@update:model-value="$emit('update:modelValue', $event)"
			@change="$emit('change', $event)"
			@filter="$emit('filter', $event)"
		>
			<template #option="{ option }">
				<span class="multi-select-field__option">
					<strong>{{ optionText(option) }}</strong>
					<small v-if="option?.description">{{ option.description }}</small>
				</span>
			</template>
		</MultiSelect>
		<small v-if="helpText" class="common-field__help">{{ helpText }}</small>
	</label>
</template>

<script setup>
import MultiSelect from "primevue/multiselect"

defineOptions({ inheritAttrs: false })

const props = defineProps({
	modelValue: { type: Array, default: () => [] },
	options: { type: Array, default: () => [] },
	optionLabel: { type: String, default: "label" },
	optionValue: { type: String, default: "value" },
	label: { type: String, default: "" },
	helpText: { type: String, default: "" },
	placeholder: { type: String, default: "Select" },
	disabled: { type: Boolean, default: false },
	invalid: { type: Boolean, default: false },
	filter: { type: Boolean, default: true },
	display: { type: String, default: "chip" },
	maxSelectedLabels: { type: Number, default: 4 },
	filterFields: { type: Array, default: null },
})

defineEmits(["update:modelValue", "change", "filter"])

function optionText(option) {
	return option && typeof option === "object" ? option[props.optionLabel] : option
}
</script>

<style scoped>
.common-field {
	display: grid;
	gap: 6px;
	width: 100%;
}

.multi-select-field__option {
	display: grid;
	gap: 2px;
	min-width: 0;
}

.multi-select-field__option strong {
	color: var(--erp-text);
	font-size: var(--erp-font-size-table);
	font-weight: var(--erp-font-weight-semibold);
}

.multi-select-field__option small {
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
}

.common-field__help {
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-caption);
}
</style>
