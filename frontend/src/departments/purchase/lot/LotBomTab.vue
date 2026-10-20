<template>
	<div class="lot-tab-stack">
		<section v-for="section in sections" :key="section.key" class="lot-section">
			<header>
				<div>
					<span>BOM</span>
					<h2>{{ section.label }}</h2>
				</div>
				<span class="lot-count">{{ countLabel(section.rows.length, "item") }}</span>
			</header>
			<div
				class="erp-table-wrap lot-table-wrap"
				role="region"
				tabindex="0"
				:aria-label="section.label"
			>
				<table class="erp-data-table lot-table">
					<thead>
						<tr>
							<th>S.No</th>
							<th>Item</th>
							<th class="erp-number">Required Qty</th>
							<th>UOM</th>
						</tr>
					</thead>
					<tbody v-for="group in bomProcessGroups(section.rows)" :key="group.process">
						<tr class="lot-group-row">
							<th :colspan="4"><DocumentLink doctype="YRP Process" :name="group.process === '—' ? '' : group.process" :label="group.process" /></th>
						</tr>
						<tr v-for="row in group.rows" :key="row.index">
							<td>{{ row.index }}</td>
							<td><DocumentLink doctype="Item" :name="row.item" /></td>
							<td class="erp-number">
								{{ formatQuantity(row.required_qty, bom.precision) }}
							</td>
							<td><DocumentLink doctype="UOM" :name="row.uom" /></td>
						</tr>
					</tbody>
					<tfoot
						v-if="section.key === 'summary' && bomUomTotals(section.rows).length > 1"
					>
						<tr v-for="total in bomUomTotals(section.rows)" :key="total.uom">
							<th colspan="2">Total</th>
							<td class="erp-number lot-total">
								{{ quantityTotal(total.total, bom.precision) }}
							</td>
							<td><DocumentLink doctype="UOM" :name="total.uom" /></td>
						</tr>
					</tfoot>
				</table>
			</div>
		</section>
		<LotEmptyState
			v-if="!sections.length"
			title="No BOM items"
			reason="No material requirements are recorded for this Lot."
		/>
	</div>
</template>

<script setup>
import { computed } from "vue"
import DocumentLink from "../../../components/common/DocumentLink.vue"
import LotEmptyState from "./LotEmptyState.vue"
import {
	countLabel,
	bomProcessGroups,
	bomSections,
	bomUomTotals,
	formatQuantity,
	quantityTotal,
} from "./lotViews.js"

const props = defineProps({ bom: { type: Object, required: true } })
const sections = computed(() => bomSections(props.bom))
</script>
