<template>
	<div class="finishing-stack" :class="{ 'finishing-entry--readonly': readonly }">
		<div class="finishing-scroll" role="region" tabindex="0" aria-label="Packed and balance boxes">
			<table class="finishing-table">
				<thead><tr><th>Size</th><th v-for="size in sizes" :key="size" class="erp-number">{{ size }}</th><th class="erp-number">Total</th></tr></thead>
				<tbody>
					<tr v-if="showPacked"><td>Packed</td><td v-for="size in sizes" :key="size" class="erp-number">{{ formatQuantity(packedOf(size)) }}</td><td class="erp-number">{{ formatQuantity(packed.total_packed) }}</td></tr>
					<tr><td>Balance</td><td v-for="size in sizes" :key="size" class="erp-number">{{ formatQuantity(balance(size)) }}</td><td class="erp-number">{{ formatQuantity(Number(packed.total_packed || 0) - Number(packed.total_dispatched || 0)) }}</td></tr>
				</tbody>
			</table>
		</div>
		<div class="finishing-scroll" role="region" tabindex="0" aria-label="Dispatch entry">
			<table v-if="dynamic" class="finishing-table">
				<thead><tr><th>GRN</th><th>Colour</th><th>Ratio</th><th class="erp-number">Received</th><th class="erp-number">Already Dispatched</th><th class="erp-number">Available</th><th class="erp-number">Dispatch Boxes</th><th class="erp-number">Dispatch Pieces</th></tr></thead>
				<tbody>
					<tr v-for="batch in batches" :key="batch.batch_row">
						<td>{{ batch.grn }}</td><td>{{ batch.colour }}</td><td>{{ ratioText(batch.ratio) }}</td>
						<td class="erp-number">{{ formatQuantity(batch.box_quantity) }}</td><td class="erp-number">{{ formatQuantity(batch.dispatched_boxes) }}</td><td class="erp-number">{{ formatQuantity(batch.available_boxes) }}</td>
						<td><input v-model="state.batchBoxes[batch.batch_row]" type="number" min="0" step="1" :max="batch.available_boxes" class="finishing-entry-input" :aria-label="`${label} ${batch.batch_row} Dispatch boxes ${batch.grn} ${batch.colour}`" :disabled="disabled" /></td>
						<td class="erp-number">{{ formatQuantity(Number(state.batchBoxes[batch.batch_row] || 0) * Number(batch.pieces_per_box || 0)) }}</td>
					</tr>
					<tr class="finishing-table__total-row"><td colspan="6">Total</td><td class="erp-number">{{ formatQuantity(totalBoxes) }}</td><td class="erp-number">{{ formatQuantity(grandTotal) }}</td></tr>
				</tbody>
			</table>
			<table v-else-if="mode === 'Size Ratio Packing'" class="finishing-table">
				<thead><tr><th>Colour</th><th class="erp-number">Boxes</th><th v-for="size in sizes" :key="size" class="erp-number">{{ size }}</th></tr></thead>
				<tbody>
					<tr v-for="colour in colours" :key="colour">
						<td>{{ colour }}</td>
						<td><input v-model="state.colourBoxes[colour]" type="number" min="0" class="finishing-entry-input" :aria-label="`${label} ${colour} boxes`" :disabled="disabled" /></td>
						<td v-for="size in sizes" :key="size" class="erp-number">{{ formatQuantity(Number(state.colourBoxes[colour] || 0) * Number(ratio[size] || 0) / combo) }}</td>
					</tr>
					<tr class="finishing-table__total-row"><td>Dispatch</td><td class="erp-number">{{ formatQuantity(totalBoxes) }}</td><td v-for="size in sizes" :key="size" class="erp-number" :class="{ 'dispatch-entry--over': over(size) }">{{ formatQuantity(bySize[size]) }}</td></tr>
				</tbody>
			</table>
			<table v-else-if="mode === 'Size Wise Packing'" class="finishing-table">
				<thead><tr><th>Colour \ Size</th><th v-for="size in sizes" :key="size" class="erp-number">{{ size }}</th><th class="erp-number">Total</th></tr></thead>
				<tbody>
					<tr v-for="colour in colours" :key="colour">
						<td>{{ colour }}</td>
						<td v-for="size in sizes" :key="size"><input v-model="state.colourSize[colour][size]" type="number" min="0" class="finishing-entry-input" :aria-label="`${label} ${colour} ${size} boxes`" :disabled="disabled" /></td>
						<td class="erp-number">{{ formatQuantity(sizes.reduce((sum, size) => sum + Number(state.colourSize[colour][size] || 0), 0)) }}</td>
					</tr>
					<tr class="finishing-table__total-row"><td>Dispatch</td><td v-for="size in sizes" :key="size" class="erp-number" :class="{ 'dispatch-entry--over': over(size) }">{{ formatQuantity(bySize[size]) }}</td><td class="erp-number">{{ formatQuantity(grandTotal) }}</td></tr>
				</tbody>
			</table>
			<table v-else class="finishing-table">
				<thead><tr><th>Size</th><th v-for="size in sizes" :key="size" class="erp-number">{{ size }}</th><th class="erp-number">Total</th></tr></thead>
				<tbody>
					<tr>
						<td>Dispatch Qty</td>
						<td v-for="size in sizes" :key="size"><input v-model="state.legacy[size]" type="number" min="0" class="finishing-entry-input" :aria-label="`${label} ${size} dispatch boxes`" :disabled="disabled" /></td>
						<td class="erp-number">{{ formatQuantity(grandTotal) }}</td>
					</tr>
				</tbody>
			</table>
		</div>
	</div>
</template>

<script setup>
import { computed, reactive } from "vue"

import { colourDetails, dispatchBySize, packingMode, packingRatio } from "../finishingEntries.js"
import { formatQuantity } from "../finishingViews.js"

const props = defineProps({
	label: { type: String, default: "Finishing Plan" },
	sizes: { type: Array, required: true },
	packed: { type: Object, default: () => ({}) },
	config: { type: Object, default: () => ({}) },
	disabled: { type: Boolean, default: false },
	showPacked: { type: Boolean, default: true },
	readonly: { type: Boolean, default: false },
	initial: { type: Object, default: () => ({}) },
})
const dynamic = computed(() => Boolean(props.packed.dynamic_ratio_packing))
const mode = computed(() => packingMode(props.config))
const colours = computed(() => props.config.colours || [])
const ratio = computed(() => packingRatio(props.config))
const combo = computed(() => Number(props.config.packing_combo) || 1)
const batches = computed(() => (props.packed.packing_batches || []).filter((batch) => Number(batch.available_boxes) > 0))
const zeroSizes = () => Object.fromEntries(props.sizes.map((size) => [size, 0]))
const state = reactive({
	legacy: { ...zeroSizes(), ...props.initial.legacy },
	colourBoxes: { ...Object.fromEntries(colours.value.map((colour) => [colour, 0])), ...props.initial.colourBoxes },
	colourSize: { ...Object.fromEntries(colours.value.map((colour) => [colour, zeroSizes()])), ...props.initial.colourSize },
	batchBoxes: { ...props.initial.batchBoxes },
})
const context = computed(() => ({ dynamic: dynamic.value, mode: mode.value, sizes: props.sizes, config: props.config, batches: batches.value, ...state }))
const bySize = computed(() => dispatchBySize(context.value))
const grandTotal = computed(() => props.sizes.reduce((sum, size) => sum + bySize.value[size], 0))
const totalBoxes = computed(() => dynamic.value
	? batches.value.reduce((sum, batch) => sum + (Number(state.batchBoxes[batch.batch_row]) || 0), 0)
	: Object.values(state.colourBoxes).reduce((sum, boxes) => sum + (Number(boxes) || 0), 0))

function packedOf(size) {
	return Number(props.packed.sizes?.[size]?.packed) || 0
}

function balance(size) {
	return packedOf(size) - (Number(props.packed.sizes?.[size]?.dispatched) || 0)
}

function over(size) {
	return bySize.value[size] > balance(size) + 1e-6
}

function ratioText(value) {
	return Object.entries(value || {}).filter(([, quantity]) => Number(quantity)).map(([size, quantity]) => `${size}:${quantity}`).join(", ")
}

function values() {
	return {
		quantities: bySize.value,
		colour_details: colourDetails(context.value),
		packing_batch_dispatches: dynamic.value
			? batches.value.map((batch) => ({ batch_row: batch.batch_row, grn: batch.grn, box_quantity: Number(state.batchBoxes[batch.batch_row]) || 0 })).filter((row) => row.box_quantity > 0)
			: [],
	}
}

defineExpose({ values, validationError: () => "" })
</script>

<style scoped>
.dispatch-entry--over { color: var(--erp-danger) !important; font-weight: 750; }
</style>
