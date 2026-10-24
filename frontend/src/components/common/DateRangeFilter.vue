<template>
	<div class="date-range-filter">
		<DateField
			:input-id="inputId"
			:model-value="draft"
			selection-mode="range"
			:aria-label="`${label} range`"
			:placeholder="placeholder"
			show-clear
			@update:model-value="pick"
		/>
		<button
			type="button"
			class="date-range-filter__presets"
			:aria-label="`${label} presets`"
			:title="`${label} presets`"
			aria-haspopup="menu"
			@click="menu.toggle($event)"
		>
			<i class="pi pi-bolt" aria-hidden="true" />
		</button>
		<Menu ref="menu" :model="presetItems" popup />
	</div>
</template>

<script setup>
import Menu from "primevue/menu"
import { computed, ref, watch } from "vue"
import DateField from "./DateField.vue"
import { dateRangePresets, dateRangeValue, hasDateRangeValue } from "./listDateRangeFilters.js"

const props = defineProps({
	modelValue: { type: [Array, String], default: "" },
	inputId: { type: String, default: "" },
	label: { type: String, default: "Date" },
	placeholder: { type: String, default: "" },
})
const emit = defineEmits(["update:modelValue"])
const menu = ref(null)
const draft = ref(currentRange())
const presetItems = computed(() => dateRangePresets().map((preset) => ({ label: preset.label, command: () => apply(preset.value) })))

watch(() => props.modelValue, () => { draft.value = currentRange() })

function currentRange() {
	return hasDateRangeValue(props.modelValue) ? dateRangeValue(props.modelValue) : ""
}

/** The picker reports `[from, null]` after the first click; the filter changes only once the range is complete or cleared. */
function pick(value) {
	draft.value = value
	const [from, to] = Array.isArray(value) ? value : []
	if (!from && !to) apply("")
	else if (from && to) apply([from, to])
}

function apply(value) {
	draft.value = value
	emit("update:modelValue", value)
}
</script>

<style scoped>
.date-range-filter {
	display: flex;
	min-width: 0;
}

.date-range-filter > :first-child {
	flex: 1;
	min-width: 0;
}

.date-range-filter__presets {
	display: inline-grid;
	place-items: center;
	flex: none;
	width: var(--erp-control-height);
	height: var(--erp-control-height);
	margin-left: 4px;
	color: var(--erp-text-muted);
	background: var(--erp-surface);
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-control-radius);
	cursor: pointer;
}

.date-range-filter__presets:hover,
.date-range-filter__presets:focus-visible {
	color: var(--erp-accent);
	border-color: var(--erp-accent);
}
</style>
