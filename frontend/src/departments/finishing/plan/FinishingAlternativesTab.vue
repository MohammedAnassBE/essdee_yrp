<template>
	<p v-if="!lots.length" class="finishing-empty">No alternative details available</p>
	<div v-else class="finishing-stack">
		<section v-for="lot in lots" :key="lot.name" class="finishing-section" :aria-label="`Alternative ${lot.name}`">
			<h3 class="finishing-section__title"><DocumentLink doctype="SD YRP Lot" :name="lot.name" /> - <DocumentLink doctype="Item" :name="lot.item" /></h3>
			<div v-for="(detail, detailIndex) in lot.details" :key="detailIndex" class="finishing-scroll" role="region" tabindex="0" :aria-label="`${lot.name} quantities ${detailIndex + 1}`">
				<table class="finishing-table">
					<thead>
						<tr>
							<th class="finishing-table__index">S.No.</th>
							<th v-for="attribute in detail.attributes || []" :key="attribute">{{ attribute }}</th>
							<th v-for="value in detail.primary_attribute_values || []" :key="value" class="erp-number">{{ value }}</th>
							<th class="erp-number">Total</th>
						</tr>
					</thead>
					<tbody>
						<tr v-for="(row, rowIndex) in detail.items || []" :key="rowIndex">
							<td class="finishing-table__index">{{ rowIndex + 1 }}</td>
							<td v-for="attribute in detail.attributes || []" :key="attribute">{{ row.attributes?.[attribute] }}</td>
							<td v-for="value in detail.primary_attribute_values || []" :key="value" class="erp-number">{{ row.values?.[value]?.qty ? formatQuantity(row.values[value].qty) : "---" }}</td>
							<td class="erp-number finishing-table__row-total">{{ formatQuantity(row.total_qty) }}</td>
						</tr>
						<tr class="finishing-table__total-row">
							<td>Total</td>
							<td v-for="attribute in detail.attributes || []" :key="attribute"></td>
							<td v-for="(value, index) in totals(detail)" :key="index" class="erp-number">{{ formatQuantity(value) }}</td>
							<td class="erp-number">{{ formatQuantity(detail.total_sum) }}</td>
						</tr>
					</tbody>
				</table>
			</div>
		</section>
	</div>
</template>

<script setup>
import DocumentLink from "../../../components/common/DocumentLink.vue"
import { computed } from "vue"

import { formatQuantity } from "../finishingViews.js"

const props = defineProps({ data: { type: Object, default: () => ({}) } })
const lots = computed(() => Object.entries(props.data || {}).map(([name, lot]) => ({ name, item: lot.item, details: (lot.details || []).filter((detail) => detail.items?.length) })))

function totals(detail) {
	return (detail.primary_attribute_values || []).map((value) => detail.size_wise_total?.[value] ?? 0)
}
</script>
