<template>
	<div class="inspection-picker">
		<section v-for="group in groups" :key="group.key" :aria-label="group.label">
			<header>
				<h3>{{ group.label }}</h3>
				<div v-if="!readonly">
					<Button label="Select all" severity="secondary" text :disabled="disabled || !rows(group).length" @click="setAll(group, true)" />
					<Button label="Unselect all" severity="secondary" text :disabled="disabled || !rows(group).length" @click="setAll(group, false)" />
				</div>
			</header>
			<div class="inspection-picker__chips">
				<button v-for="row in rows(group)" :key="row[group.field]" type="button"
					class="inspection-picker__chip" :class="{ 'inspection-picker__chip--selected': Number(row.selected) === 1 }"
					:aria-pressed="Number(row.selected) === 1" :disabled="disabled || readonly"
					@click="toggle(group, row)">
					<i :class="Number(row.selected) === 1 ? 'pi pi-check-circle' : 'pi pi-circle'" aria-hidden="true" />
					{{ row[group.field] }}
				</button>
			</div>
			<p v-if="!rows(group).length">{{ readonly ? 'None selected.' : 'Choose a Work Order to load options.' }}</p>
		</section>
	</div>
</template>

<script setup>
import Button from "primevue/button"
import { selectAll, toggleSelection } from "../qualityViews.js"

const props = defineProps({
	modelValue: { type: Object, default: () => ({ colours: [], sizes: [] }) },
	readonly: { type: Boolean, default: false },
	disabled: { type: Boolean, default: false },
})
const emit = defineEmits(["update:modelValue"])
const groups = [
	{ key: "colours", field: "colour", label: "Colours" },
	{ key: "sizes", field: "size", label: "Sizes" },
]

function rows(group) {
	const options = props.modelValue[group.key] || []
	return props.readonly ? options.filter((row) => Number(row.selected) === 1) : options
}

function toggle(group, row) {
	if (props.disabled || props.readonly) return
	emit("update:modelValue", toggleSelection(props.modelValue, group.key, row[group.field]))
}

function setAll(group, selected) {
	if (props.disabled || props.readonly) return
	emit("update:modelValue", selectAll(props.modelValue, group.key, selected))
}
</script>

<style scoped>
.inspection-picker { display: grid; min-width: 0; gap: var(--erp-space-4); }
.inspection-picker section { min-width: 0; }
.inspection-picker header { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--erp-space-2); }
.inspection-picker h3 { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-body); }
.inspection-picker header > div { display: flex; flex-wrap: wrap; }
.inspection-picker :deep(.p-button) { min-height: 44px; }
.inspection-picker__chips { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--erp-space-2); }
.inspection-picker__chip { display: flex; min-width: 0; min-height: 44px; align-items: center; gap: var(--erp-space-2); padding: var(--erp-space-2); border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); color: var(--erp-text); background: var(--erp-surface); font: inherit; overflow-wrap: anywhere; cursor: pointer; text-align: left; }
.inspection-picker__chip--selected { border-color: var(--erp-accent); color: var(--erp-accent-ink); background: var(--erp-accent-soft); }
.inspection-picker__chip:focus-visible { outline: 2px solid var(--erp-accent); outline-offset: 2px; }
.inspection-picker__chip:disabled { cursor: default; }
.inspection-picker p { color: var(--erp-text-muted); }
@media (min-width: 641px) { .inspection-picker { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
