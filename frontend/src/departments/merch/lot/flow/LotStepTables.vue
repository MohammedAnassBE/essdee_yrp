<template>
	<div class="pf-detail-tables">
		<LotToneLegend />
		<div v-if="cloth.length" class="pf-block">
			<h4>Deliverables · cloth</h4>
			<div class="pf-table-wrap">
				<table class="erp-data-table lot-table pf-table">
					<thead><tr><th>Work Order</th><th>Item</th><th>Attributes</th><th class="erp-number">Planned</th><th class="erp-number">Delivered</th><th class="erp-number">Difference</th><th>UOM</th></tr></thead>
					<tbody>
						<tr v-for="(row, index) in cloth" :key="index">
							<td>{{ row.work_order }}</td><td>{{ row.item }}</td><td>{{ row.attributes }}</td>
							<td class="erp-number">{{ formatNumber(row.planned) }}</td>
							<td class="erp-number" :class="tone(statusTone(row.delivered, row.planned))">{{ formatNumber(row.delivered) }}</td>
							<td class="erp-number" :class="tone(diffTone(row.delivered - row.planned, row.planned))">{{ formatNumber(row.delivered - row.planned) }}</td>
							<td>{{ row.uom }}</td>
						</tr>
						<tr class="pf-total">
							<td colspan="3">Total</td>
							<td class="erp-number">{{ formatNumber(clothTotal.planned) }}</td>
							<td class="erp-number" :class="tone(statusTone(clothTotal.delivered, clothTotal.planned))">{{ formatNumber(clothTotal.delivered) }}</td>
							<td class="erp-number" :class="tone(diffTone(clothTotal.delivered - clothTotal.planned, clothTotal.planned))">{{ formatNumber(clothTotal.delivered - clothTotal.planned) }}</td>
							<td>{{ cloth[0].uom }}</td>
						</tr>
					</tbody>
				</table>
			</div>
		</div>
		<LotSizeTable v-if="table" :table="table.data" :sizes="sizes" :title="table.title" :hint="table.hint" :first-label="table.firstLabel" />
	</div>
</template>
<script setup>
import { computed } from "vue"
import LotSizeTable from "./LotSizeTable.vue"
import LotToneLegend from "./LotToneLegend.vue"
import { diffTone, formatNumber, sizeTable, statusTone } from "./processFlow.js"
/** Size-wise detail of an item step or Work Order: cutting cloth, in-house sizes or packing quantities. */
const props = defineProps({
	kind: { type: String, default: "inhouse" },
	sizes: { type: Array, default: () => [] },
	grid: { type: Array, default: () => [] },
	cloth: { type: Array, default: () => [] },
	packing: { type: Object, default: null },
	hasOrders: Boolean,
	workOrder: Boolean,
})
const tone = (value) => (value ? `pf-tone-${value}` : "")
const clothTotal = computed(() => ({
	planned: props.cloth.reduce((sum, row) => sum + row.planned, 0),
	delivered: props.cloth.reduce((sum, row) => sum + row.delivered, 0),
}))
const table = computed(() => {
	if (props.kind === "packing" && props.packing) {
		const row = { colour: "All colours", part: `Finishing Plan ${props.packing.finishing_plans.join(", ") || "—"}`, ...props.packing }
		return {
			title: "Finishing Plan quantities by size (pieces)",
			hint: `Delivered = sent on DCs · Received = packed and returned on GRNs (${props.packing.pieces_per_box} per box) · Dispatch = dispatched from the Finishing Plan`,
			firstLabel: "Lot · Plan",
			data: sizeTable([row], props.sizes, ["planned", "delivered", "received", "dispatch"], { delivered: "Delivered (DC)", received: "Received (GRN)" }),
		}
	}
	if (props.workOrder) return { title: "Work Order Summary", data: sizeTable(props.grid, props.sizes, ["planned", "delivered", "received", "pending"]) }
	if (props.kind === "cutting") return { title: "Receivables · cut pieces by size", data: sizeTable(props.grid, props.sizes, ["planned", "received", "difference"]) }
	if (!props.hasOrders) return { title: "Planned by size", hint: "no Work Order yet", data: sizeTable(props.grid, props.sizes, ["planned", "received", "difference"]) }
	return { title: "Planned / delivered / received by size", data: sizeTable(props.grid, props.sizes, ["planned", "delivered", "received", "difference"]) }
})
</script>
