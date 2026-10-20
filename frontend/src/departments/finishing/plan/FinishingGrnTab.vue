<template>
	<section class="finishing-section" aria-label="Packed and dispatched boxes">
		<h3 class="finishing-section__title">Packed Boxes</h3>
		<div class="finishing-scroll" role="region" tabindex="0" aria-label="Packed and dispatched boxes by size">
			<table class="finishing-table">
				<thead>
					<tr>
						<th>Size</th>
						<th v-for="size in data.primary_values || []" :key="size" class="erp-number">{{ size }}</th>
						<th class="erp-number">Total</th>
					</tr>
				</thead>
				<tbody>
					<tr v-for="row in rows" :key="row.label" :class="{ 'finishing-table__total-row': row.label === 'Balance' }">
						<td class="finishing-table__type">{{ row.label }}</td>
						<td v-for="(value, index) in row.cells" :key="index" class="erp-number">{{ formatQuantity(value) }}</td>
						<td class="erp-number finishing-table__row-total">{{ formatQuantity(row.total) }}</td>
					</tr>
				</tbody>
			</table>
		</div>
	</section>
	<section v-if="batches.length" class="finishing-section" aria-label="Packing batches">
		<h3 class="finishing-section__title">Packing Batches</h3>
		<div class="finishing-scroll" role="region" tabindex="0" aria-label="Packing batches">
			<table class="finishing-table">
				<thead><tr><th>GRN</th><th>Colour</th><th>Ratio</th><th class="erp-number">Received Boxes</th><th class="erp-number">Dispatched</th><th class="erp-number">Balance</th></tr></thead>
				<tbody>
					<tr v-for="batch in batches" :key="batch.batch_row">
						<td><DocumentLink doctype="YRP Goods Received Note" :name="batch.grn" :label="batch.grn" /></td>
						<td>{{ batch.colour }}</td>
						<td>{{ ratioText(batch.ratio) }}</td>
						<td class="erp-number">{{ formatQuantity(batch.box_quantity) }}</td>
						<td class="erp-number">{{ formatQuantity(batch.dispatched_boxes) }}</td>
						<td class="erp-number">{{ formatQuantity(batch.available_boxes) }}</td>
					</tr>
				</tbody>
			</table>
		</div>
	</section>
</template>

<script setup>
import DocumentLink from "../../../components/common/DocumentLink.vue"
import { computed } from "vue"

import { formatQuantity, packedRows } from "../finishingViews.js"

const props = defineProps({ data: { type: Object, required: true } })
const rows = computed(() => packedRows(props.data))
const batches = computed(() => (props.data.packed?.dynamic_ratio_packing ? props.data.packed?.packing_batches || [] : []))

function ratioText(ratio) {
	return Object.entries(ratio || {}).filter(([, quantity]) => Number(quantity)).map(([size, quantity]) => `${size}:${quantity}`).join(", ")
}
</script>
