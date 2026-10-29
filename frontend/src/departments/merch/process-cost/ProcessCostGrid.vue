<template>
	<div class="process-cost-grid">
		<EntryGrid :rows="grid.rows" :columns="columns" :model-value="grid.model" :readonly="readonly" title="Process Cost Values" row-header-label="Attribute Value" :errors="errors" :toolbar="readonly ? [] : ['fillDown', 'paste', 'clear']" :removable-rows="!readonly && tiers.length > 1" :add-row="readonly || (attribute && !tierValue) ? null : addTier" @update:model-value="updateModel" @remove-row="removeRow" />
		<p v-if="message" class="process-cost-grid__error" role="alert">{{ message }}</p>
		<ul v-if="cellMessages.length" class="process-cost-grid__error" aria-live="polite"><li v-for="text in cellMessages" :key="text">{{ text }}</li></ul>
		<div v-if="!readonly" class="process-cost-grid__tiers">
			<template v-if="attribute">
				<label for="process-cost-tier-value">Attribute Value</label>
				<Select v-model="tierValue" input-id="process-cost-tier-value" :options="values" option-label="label" option-value="name" placeholder="Select Attribute Value" />
			</template>
			<Button label="Add tier" icon="pi pi-plus" severity="secondary" :disabled="attribute && !tierValue" @click="addTier" />
		</div>
	</div>
</template>

<script setup>
import Button from "primevue/button"
import Select from "primevue/select"
import { computed, ref, watch } from "vue"
import EntryGrid from "../../../components/common/EntryGrid.vue"
import { buildProcessCostGrid, processCostGridValues } from "./processCostViews.js"

const props = defineProps({
	tiers: { type: Array, default: () => [] }, values: { type: Array, default: () => [] },
	attribute: { type: String, default: "" }, readonly: Boolean,
	fields: { type: Array, default: () => [] },
	errors: { type: Object, default: () => ({}) }, message: { type: String, default: "" },
})
const emit = defineEmits(["update:tiers"])
const tierValue = ref(null)
const grid = computed(() => buildProcessCostGrid(props.tiers))
const cellMessages = computed(() => Object.entries(props.errors).flatMap(([key, errors]) => {
	const index = grid.value.rows.findIndex((row) => row.key === key)
	return Object.values(errors).map((message) => `Row ${index + 1}: ${message}`)
}))
const columns = computed(() => [["min_order_qty", "Min Order Qty"], ["price", "Price"]].map(([key, label]) => {
	const field = props.fields.find((field) => field.fieldname === key)
	return { key, label: field?.label || label, type: "number", min: 0, precision: field?.precision }
}))
watch(() => props.values, () => { tierValue.value = props.values[0]?.name || null }, { immediate: true })
function updateModel(model) { emit("update:tiers", processCostGridValues(props.tiers, model)) }
function removeRow(key) { emit("update:tiers", props.tiers.filter((_, index) => `tier-${index}` !== key)) }
function addTier() {
	const value = props.values.find((value) => value.name === tierValue.value)
	emit("update:tiers", [...props.tiers, { attribute_value: props.attribute ? value.name : null, attribute_value_label: value?.label || "", min_order_qty: 0, price: 0 }])
}
</script>

<style scoped>
.process-cost-grid { min-width: 0; overflow: hidden; }
.process-cost-grid__tiers { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; padding: 12px 0; }
.process-cost-grid__error { color: var(--erp-danger); font-size: var(--erp-font-size-caption); }
</style>
