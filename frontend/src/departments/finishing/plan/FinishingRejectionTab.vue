<template>
	<div class="finishing-stack">
		<div class="rejection__toolbar">
			<h3 class="finishing-section__title">Rejection Details</h3>
			<label v-if="receivedTypes.length" class="rejection__filter">
				<span>Received Type</span>
				<Select v-model="selectedType" :options="filterOptions" option-label="label" option-value="value" placeholder="All" aria-label="Received Type" />
			</label>
		</div>
		<div v-if="summaryRows.length" class="finishing-scroll rejection__summary" role="region" tabindex="0" aria-label="Rejection summary">
			<table class="finishing-table">
				<thead><tr><th>Received Type</th><th class="erp-number">Rework Qty</th><th class="erp-number">Rejection Qty</th></tr></thead>
				<tbody>
					<tr v-for="row in summaryRows" :key="row.receivedType"><td><strong>{{ row.receivedType }}</strong></td><td class="erp-number">{{ formatQuantity(row.rework) }}</td><td class="erp-number">{{ formatQuantity(row.rejection) }}</td></tr>
					<tr class="finishing-table__total-row"><td>Grand Total</td><td class="erp-number">{{ formatQuantity(summaryTotal.rework) }}</td><td class="erp-number">{{ formatQuantity(summaryTotal.rejection) }}</td></tr>
				</tbody>
			</table>
		</div>
		<p v-if="!detailRows.length" class="finishing-empty">No rejection data</p>
		<div v-else class="finishing-scroll" role="region" tabindex="0" aria-label="Rejection details by colour and size">
			<table class="finishing-table">
				<thead>
					<tr>
						<th>Received Type</th>
						<th>Colour</th>
						<th v-if="data.is_set_item">{{ data.set_attr }}</th>
						<th>Type</th>
						<th v-for="size in sizes" :key="size" class="erp-number">{{ size }}</th>
						<th class="erp-number">Total</th>
					</tr>
				</thead>
				<tbody v-for="block in detailRows" :key="block.receivedType">
					<template v-for="(colour, colourIndex) in block.colours" :key="colour.key">
						<tr v-for="(kind, kindIndex) in kinds" :key="kind.key">
							<td v-if="colourIndex === 0 && kindIndex === 0" :rowspan="block.colours.length * 2"><strong>{{ block.receivedType }}</strong></td>
							<td v-if="kindIndex === 0" rowspan="2">{{ colour.label }}</td>
							<td v-if="data.is_set_item && kindIndex === 0" rowspan="2">{{ colour.part || "—" }}</td>
							<td class="finishing-table__type">{{ kind.label }}</td>
							<td v-for="size in sizes" :key="size" class="erp-number">{{ formatQuantity(colour.values[kind.key]?.values?.[size] ?? 0) }}</td>
							<td class="erp-number finishing-table__row-total">{{ formatQuantity(colour.values[kind.key]?.total ?? 0) }}</td>
						</tr>
					</template>
				</tbody>
				<tbody>
					<tr class="finishing-table__total-row">
						<td :colspan="3 + (data.is_set_item ? 1 : 0) + sizes.length" class="erp-number">Total Rejection</td>
						<td class="erp-number">{{ formatQuantity(rejectionTotal) }}</td>
					</tr>
				</tbody>
			</table>
		</div>
	</div>
</template>

<script setup>
import Select from "primevue/select"
import { computed, ref } from "vue"

import { colourLabel, formatQuantity } from "../finishingViews.js"

const props = defineProps({ data: { type: Object, required: true } })
const selectedType = ref(null)
const kinds = [{ key: "rework", label: "Rework Qty" }, { key: "rejection", label: "Rejection Qty" }]
const sizes = computed(() => props.data.primary_values || [])
const receivedTypes = computed(() => Object.keys(props.data.data || {}))
const filterOptions = computed(() => [{ label: "All", value: null }, ...receivedTypes.value.map((value) => ({ label: value, value }))])
const total = (colours, key) => Object.values(colours || {}).reduce((sum, colour) => sum + Number(colour[key]?.total || 0), 0)
const summaryRows = computed(() => Object.entries(props.data.data || {}).map(([receivedType, colours]) => ({ receivedType, rework: total(colours, "rework"), rejection: total(colours, "rejection") })))
const summaryTotal = computed(() => summaryRows.value.reduce((sum, row) => ({ rework: sum.rework + row.rework, rejection: sum.rejection + row.rejection }), { rework: 0, rejection: 0 }))
const detailRows = computed(() => Object.entries(props.data.data || {})
	.filter(([receivedType]) => !selectedType.value || receivedType === selectedType.value)
	.map(([receivedType, colours]) => ({
		receivedType,
		colours: Object.entries(colours).map(([key, values]) => ({ key, label: colourLabel(key), part: values.part, values })),
	})))
const rejectionTotal = computed(() => detailRows.value.reduce((sum, block) => sum + block.colours.reduce((inner, colour) => inner + Number(colour.values.rejection?.total || 0), 0), 0))
</script>

<style scoped>
.rejection__toolbar { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 10px; }
.rejection__filter { display: flex; align-items: center; gap: 8px; color: var(--erp-text-secondary); font-size: var(--erp-font-size-caption); font-weight: 650; }
.rejection__filter :deep(.p-select) { min-width: 200px; }
.rejection__summary { justify-self: start; min-width: min(100%, 420px); }
</style>
