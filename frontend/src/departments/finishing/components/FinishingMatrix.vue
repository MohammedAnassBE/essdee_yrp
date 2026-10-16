<template>
	<section class="finishing-matrix" :aria-label="title || 'Finishing quantities'">
		<h3 v-if="title" class="finishing-matrix__title">{{ title }}</h3>
		<div v-if="model.groups.length" class="finishing-matrix__scroll" role="region" tabindex="0" :aria-label="`${title || 'Finishing'} matrix`">
			<table class="finishing-table">
				<thead>
					<tr>
						<th class="finishing-table__index">S.No</th>
						<th class="finishing-table__colour">Colour</th>
						<th v-if="model.setAttr">{{ model.setAttr }}</th>
						<th v-if="showType" class="finishing-table__type">Type</th>
						<th v-for="size in model.sizes" :key="size" class="erp-number">{{ size }}</th>
						<th class="erp-number">Total</th>
					</tr>
				</thead>
				<tbody v-for="group in model.groups" :key="group.key" :class="{ 'finishing-table__total-group': group.total }">
					<tr v-for="(row, rowIndex) in group.rows" :key="rowIndex">
						<template v-if="rowIndex === 0">
							<td :rowspan="group.rows.length" class="finishing-table__index">{{ group.index }}</td>
							<td :rowspan="group.rows.length" class="finishing-table__colour"><strong v-if="group.total">{{ group.colour }}</strong><template v-else>{{ group.colour }}</template></td>
							<td v-if="model.setAttr" :rowspan="group.rows.length">{{ group.part || "—" }}</td>
						</template>
						<td v-if="showType" class="finishing-table__type">{{ row.label }}</td>
						<td v-for="(cell, cellIndex) in row.cells" :key="cellIndex" class="erp-number" :class="toneClass(cell.tone)">{{ quantity(cell.value) }}</td>
						<td class="erp-number finishing-table__row-total" :class="toneClass(row.total.tone)">{{ quantity(row.total.value) }}</td>
					</tr>
				</tbody>
			</table>
		</div>
		<p v-else class="erp-empty-state"><span class="erp-empty-state__text">{{ emptyText }}</span></p>
	</section>
</template>

<script setup>
import { computed } from "vue"

import { formatQuantity } from "../finishingViews.js"

const props = defineProps({
	model: { type: Object, required: true },
	title: { type: String, default: "" },
	emptyText: { type: String, default: "No quantities yet." },
})
const showType = computed(() => props.model.groups.some((group) => group.rows.length > 1 || group.rows[0]?.label))

function toneClass(tone) {
	return tone ? `finishing-tone finishing-tone--${tone}` : ""
}

function quantity(value) {
	return formatQuantity(value)
}
</script>

<style scoped>
.finishing-matrix { display: grid; min-width: 0; gap: var(--erp-space-2); }
.finishing-matrix__title { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-section); font-weight: 700; }
</style>
