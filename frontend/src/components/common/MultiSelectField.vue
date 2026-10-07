<template>
	<label class="common-field">
		<span v-if="label" class="common-field__label">{{ label }}</span>
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
			:display="display"
			:max-selected-labels="maxSelectedLabels"
			fluid
			@update:model-value="$emit('update:modelValue', $event)"
			@change="$emit('change', $event)"
		/>
		<small v-if="helpText" class="common-field__help">{{ helpText }}</small>
	</label>
</template>

<script setup>
import MultiSelect from "primevue/multiselect"

defineOptions({ inheritAttrs: false })

defineProps({
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
})

defineEmits(["update:modelValue", "change"])
</script>

<style scoped>
.common-field {
	display: grid;
	gap: 6px;
	width: 100%;
}

.common-field__label {
	color: var(--erp-text);
	font-size: var(--erp-font-size-caption);
	font-weight: 680;
	transition: color var(--erp-transition-fast);
}

.common-field:focus-within .common-field__label {
	color: var(--erp-accent-hover);
}

.common-field :deep(.p-multiselect) {
	background: var(--erp-surface);
	border-color: var(--erp-border-strong);
	box-shadow: var(--erp-shadow-xs);
}

.common-field :deep(.p-multiselect:not(.p-disabled):hover) {
	border-color: color-mix(in srgb, var(--erp-accent) 32%, var(--erp-border-strong));
}

.common-field :deep(.p-multiselect.p-focus) {
	border-color: var(--erp-accent);
	box-shadow: 0 0 0 3px color-mix(in srgb, var(--erp-accent) 11%, transparent);
}

.common-field__help {
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
}
</style>
