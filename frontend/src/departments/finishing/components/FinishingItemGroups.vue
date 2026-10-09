<template>
	<p v-if="!hasItems" class="finishing-empty">Nothing to show</p>
	<div v-else class="finishing-stack">
		<section v-for="section in sections" :key="section.key" class="finishing-section" :aria-label="section.title">
			<h3 class="finishing-section__title">{{ section.title }}</h3>
			<div v-for="(group, groupIndex) in section.groups" :key="groupIndex" class="finishing-scroll" role="region" tabindex="0" :aria-label="`${section.title} group ${groupIndex + 1}`">
				<table class="finishing-table">
					<thead>
						<tr>
							<th>Item</th>
							<th v-for="attribute in group.attributes" :key="attribute">{{ attribute }}</th>
							<th>Received Type</th>
							<th v-if="showUom">UOM</th>
							<template v-if="group.primary_attribute">
								<th v-for="value in group.primary_attribute_values" :key="value" class="erp-number">{{ value }}</th>
							</template>
							<th v-else class="erp-number">{{ quantityLabel }}</th>
							<th class="erp-number">Total</th>
						</tr>
					</thead>
					<tbody>
						<tr v-for="(item, itemIndex) in group.items" :key="itemIndex">
							<td>{{ item.item }}</td>
							<td v-for="attribute in group.attributes" :key="attribute">{{ item.attributes?.[attribute] || "--" }}</td>
							<td>{{ item.received_type || "--" }}</td>
							<td v-if="showUom">{{ item.stock_uom || "--" }}</td>
							<td v-for="key in valueKeys(group)" :key="key" class="erp-number" :title="sourcesTitle(item, key)">{{ cellQuantity(item, key) ? formatQuantity(cellQuantity(item, key)) : "--" }}</td>
							<td class="erp-number finishing-table__row-total">{{ formatQuantity(item.total_quantity) }}</td>
						</tr>
						<tr class="finishing-table__total-row">
							<td :colspan="(showUom ? 3 : 2) + group.attributes.length"><strong>Total</strong></td>
							<td v-for="key in valueKeys(group)" :key="key" class="erp-number">{{ group.total_details?.[key] ? formatQuantity(group.total_details[key]) : "--" }}</td>
							<td class="erp-number">{{ formatQuantity(group.overall_total) }}</td>
						</tr>
					</tbody>
				</table>
			</div>
		</section>
	</div>
</template>

<script setup>
import { computed } from "vue"

import { formatQuantity } from "../finishingViews.js"

const props = defineProps({
	sections: { type: Array, default: () => [] },
	showUom: { type: Boolean, default: false },
	quantityLabel: { type: String, default: "Quantity" },
})
const hasItems = computed(() => props.sections.some((section) => section.groups?.some((group) => group.items?.length)))

function valueKeys(group) {
	return group.primary_attribute ? group.primary_attribute_values : ["default"]
}

function cellQuantity(item, key) {
	return Number(item.values?.[key]?.quantity || 0)
}

function sourcesTitle(item, key) {
	return (item.values?.[key]?.sources || []).map((source) => source.source_name).filter(Boolean).join(", ")
}
</script>
