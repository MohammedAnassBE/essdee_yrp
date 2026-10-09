<template>
	<div class="finishing-scroll" role="region" tabindex="0" aria-label="Packed box entry">
		<table v-if="mode === 'Size Ratio Packing'" class="finishing-table finishing-packing-entry">
			<thead>
				<tr>
					<th>Colour</th>
					<th class="erp-number">Boxes</th>
					<th v-for="size in sizes" :key="size" class="erp-number">{{ size }}</th>
					<th class="erp-number">Pcs/Box (Required: {{ combo }})</th>
					<th class="erp-number">Total Pcs</th>
					<th><span class="sr-only">Actions</span></th>
				</tr>
			</thead>
			<tbody>
				<tr v-for="(batch, index) in state.batches" :key="batch.key">
					<td><Select v-model="batch.colour" :options="colours" placeholder="Select" :aria-label="`Ratio ${index + 1} colour`" :disabled="disabled" /></td>
					<td><input v-model="batch.box_quantity" type="number" min="0" step="1" class="finishing-entry-input" :aria-label="`Ratio ${index + 1} boxes`" :disabled="disabled" /></td>
					<td v-for="size in sizes" :key="size"><input v-model="batch.ratio[size]" type="number" min="0" step="1" class="finishing-entry-input" :aria-label="`Ratio ${index + 1} ${size}`" :disabled="disabled" /></td>
					<td class="erp-number"><strong :class="batchPiecesPerBox(batch, sizes) === combo ? 'packing-entry--ok' : 'packing-entry--bad'">{{ batchPiecesPerBox(batch, sizes) }} / {{ combo }}</strong></td>
					<td class="erp-number"><strong>{{ formatQuantity(Number(batch.box_quantity || 0) * batchPiecesPerBox(batch, sizes)) }}</strong></td>
					<td class="packing-entry__actions">
						<Button label="Copy" severity="secondary" text size="small" :disabled="disabled" @click="addBatch(batch)" />
						<Button icon="pi pi-times" severity="danger" text size="small" :aria-label="`Remove ratio ${index + 1}`" :disabled="disabled || state.batches.length === 1" @click="state.batches.splice(index, 1)" />
					</td>
				</tr>
				<tr class="finishing-table__total-row">
					<td>Total</td>
					<td class="erp-number">{{ formatQuantity(totalBoxes) }}</td>
					<td v-for="size in sizes" :key="size" class="erp-number">{{ formatQuantity(boxQuantities[size]) }}</td>
					<td></td>
					<td class="erp-number">{{ formatQuantity(total) }}</td>
					<td><Button label="Add Ratio" icon="pi pi-plus" size="small" :disabled="disabled" @click="addBatch()" /></td>
				</tr>
			</tbody>
		</table>
		<table v-else-if="mode === 'Size Wise Packing'" class="finishing-table finishing-packing-entry">
			<thead><tr><th>Colour \ Size</th><th v-for="size in sizes" :key="size" class="erp-number">{{ size }}</th><th class="erp-number">Total</th></tr></thead>
			<tbody>
				<tr v-for="colour in colours" :key="colour">
					<td>{{ colour }}</td>
					<td v-for="size in sizes" :key="size"><input v-model="state.colourSize[colour][size]" type="number" min="0" class="finishing-entry-input" :aria-label="`${colour} ${size} pieces`" :disabled="disabled" /></td>
					<td class="erp-number">{{ formatQuantity(sizes.reduce((sum, size) => sum + Number(state.colourSize[colour][size] || 0), 0)) }}</td>
				</tr>
				<tr class="finishing-table__total-row"><td>Total</td><td v-for="size in sizes" :key="size" class="erp-number">{{ formatQuantity(boxQuantities[size]) }}</td><td class="erp-number">{{ formatQuantity(total) }}</td></tr>
			</tbody>
		</table>
		<table v-else class="finishing-table finishing-packing-entry">
			<thead><tr><th>Size</th><th v-for="size in sizes" :key="size" class="erp-number">{{ size }}</th><th class="erp-number">Total</th></tr></thead>
			<tbody>
				<tr>
					<td>Quantity</td>
					<td v-for="size in sizes" :key="size"><input v-model="state.flat[size]" type="number" min="0" class="finishing-entry-input" :aria-label="`${size} boxes`" :disabled="disabled" /></td>
					<td class="erp-number">{{ formatQuantity(total) }}</td>
				</tr>
			</tbody>
		</table>
	</div>
</template>

<script setup>
import Button from "primevue/button"
import Select from "primevue/select"
import { computed, reactive } from "vue"

import { batchPiecesPerBox, coloursValid, grnBoxQuantities, packingMode, packingRatio, ratiosValid } from "../finishingEntries.js"
import { formatQuantity } from "../finishingViews.js"

const props = defineProps({
	sizes: { type: Array, required: true },
	config: { type: Object, default: () => ({}) },
	disabled: { type: Boolean, default: false },
})
const mode = computed(() => packingMode(props.config))
const colours = computed(() => props.config.colours || [])
const combo = computed(() => Number(props.config.packing_combo) || 1)
let sequence = 0
const state = reactive({
	flat: Object.fromEntries(props.sizes.map((size) => [size, 0])),
	colourSize: Object.fromEntries(colours.value.map((colour) => [colour, Object.fromEntries(props.sizes.map((size) => [size, 0]))])),
	batches: [],
})
const boxQuantities = computed(() => grnBoxQuantities(mode.value, props.sizes, state))
const total = computed(() => props.sizes.reduce((sum, size) => sum + boxQuantities.value[size], 0))
const totalBoxes = computed(() => state.batches.reduce((sum, batch) => sum + (Number(batch.box_quantity) || 0), 0))

function addBatch(source = null) {
	const ratio = packingRatio(props.config)
	state.batches.push({
		key: ++sequence,
		colour: source ? source.colour : (colours.value.length === 1 ? colours.value[0] : ""),
		box_quantity: source ? source.box_quantity : 0,
		ratio: Object.fromEntries(props.sizes.map((size) => [size, Number(source ? source.ratio[size] : ratio[size]) || 0])),
	})
}

function validationError() {
	if (!props.config.dynamic_ratio_packing) return ""
	if (!coloursValid(state.batches, colours.value)) return "Select a valid colour in every packing ratio."
	if (!ratiosValid(state.batches, props.sizes, combo.value)) return `Every packing ratio must total ${combo.value} pieces per box.`
	return ""
}

function values() {
	return {
		quantities: boxQuantities.value,
		packing_batches: mode.value === "Size Ratio Packing"
			? state.batches.map((batch) => ({ colour: batch.colour, box_quantity: Number(batch.box_quantity) || 0, ratio: Object.fromEntries(props.sizes.map((size) => [size, Number(batch.ratio[size]) || 0])) }))
			: [],
	}
}

addBatch()
defineExpose({ values, validationError })
</script>

<style scoped>
.packing-entry--ok { color: var(--erp-success); }
.packing-entry--bad { color: var(--erp-danger); }
.packing-entry__actions { white-space: nowrap; }
.finishing-packing-entry :deep(.p-select) { min-width: 150px; }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
</style>
