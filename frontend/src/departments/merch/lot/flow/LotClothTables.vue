<template>
	<div class="pf-detail-tables">
		<div class="pf-stats">
			<div class="pf-stat"><span>Delivered</span><b>{{ formatNumber(totals.delivered) }} <small>{{ uom }}</small></b></div>
			<div class="pf-stat"><span>Received</span><b>{{ formatNumber(totals.received) }} <small>{{ uom }}</small></b></div>
			<div class="pf-stat" :class="tone(diffTone(totals.received - totals.base, totals.base))"><span>Difference</span><b>{{ formatNumber(totals.received - totals.base) }} <small>{{ uom }}</small></b></div>
			<div class="pf-stat"><span>Received of {{ hasDelivered ? "delivered" : "planned" }}</span><b>{{ percent(totals.received, totals.base) }}%</b></div>
			<div class="pf-stat"><span>First DC</span><b>{{ formatDisplayDate(workOrder.first_dc) }}</b></div>
			<div class="pf-stat"><span>Last GRN</span><b>{{ formatDisplayDate(workOrder.last_grn) }}</b></div>
		</div>
		<LotToneLegend />
		<div v-if="cloth.deliverables.length" class="pf-block">
			<h4>Delivered · yarn</h4>
			<div class="pf-table-wrap">
				<table class="erp-data-table lot-table pf-table">
					<thead><tr><th>Item</th><th>Colour</th><th class="erp-number">Planned</th><th class="erp-number">Delivered</th><th class="erp-number">Difference</th><th>UOM</th></tr></thead>
					<tbody>
						<tr v-for="row in cloth.deliverables" :key="row.item_variant">
							<td>{{ row.item_variant }}</td><td>{{ row.colour || "—" }}</td>
							<td class="erp-number">{{ formatNumber(row.planned) }}</td>
							<td class="erp-number" :class="tone(statusTone(row.delivered, row.planned))">{{ formatNumber(row.delivered) }}</td>
							<td class="erp-number" :class="tone(diffTone(row.delivered - row.planned, row.planned))">{{ formatNumber(row.delivered - row.planned) }}</td>
							<td>{{ row.uom }}</td>
						</tr>
					</tbody>
				</table>
			</div>
		</div>
		<div class="pf-block">
			<h4>{{ hasDelivered ? "Delivered and received" : "Received" }} · by colour and dia</h4>
			<div class="pf-table-wrap">
				<table class="erp-data-table lot-table pf-table">
					<thead>
						<tr><th>Colour</th><th>Dia</th><th class="erp-number">Planned</th><th v-if="hasDelivered" class="erp-number">Delivered</th><th class="erp-number">Received</th><th class="erp-number">Difference</th></tr>
					</thead>
					<tbody>
						<tr v-for="row in [...cloth.rows, totalRow]" :key="`${row.colour}-${row.dia}`" :class="{ 'pf-total': row === totalRow }">
							<td><span v-if="row !== totalRow" class="pf-swatch"><i :style="{ background: swatch(row.colour) }" />{{ row.colour || "—" }}</span><template v-else>Total</template></td>
							<td>{{ row.dia }}</td>
							<td class="erp-number">{{ formatNumber(row.planned) }}</td>
							<td v-if="hasDelivered" class="erp-number" :class="tone(statusTone(row.delivered, row.planned))">{{ formatNumber(row.delivered) }}</td>
							<td class="erp-number" :class="tone(statusTone(row.received, base(row)))">{{ formatNumber(row.received) }}</td>
							<td class="erp-number" :class="tone(diffTone(row.received - base(row), base(row)))">{{ formatNumber(row.received - base(row)) }}</td>
						</tr>
					</tbody>
				</table>
			</div>
		</div>
	</div>
</template>
<script setup>
import { computed } from "vue"
import { formatDisplayDate } from "../../../../utils/dateFormat.js"
import LotToneLegend from "./LotToneLegend.vue"
import { colourSwatch, diffTone, formatNumber, percent, statusTone } from "./processFlow.js"
/** Cloth Work Order: totals, yarn deliverables and colour × dia planned / delivered / received. */
const props = defineProps({
	cloth: { type: Object, required: true },
	workOrder: { type: Object, required: true },
})
const tone = (value) => (value ? `pf-tone-${value}` : "")
const swatch = colourSwatch
const hasDelivered = computed(() => props.cloth.rows.some((row) => row.delivered !== null))
const base = (row) => (hasDelivered.value ? row.delivered : row.planned)
const sum = (key) => props.cloth.rows.reduce((total, row) => total + Number(row[key] || 0), 0)
const totalRow = computed(() => ({ colour: "", dia: "", planned: sum("planned"), delivered: sum("delivered"), received: sum("received") }))
const uom = computed(() => props.cloth.deliverables[0]?.uom || "Kg")
const totals = computed(() => {
	const delivered = hasDelivered.value ? sum("delivered") : props.cloth.deliverables.reduce((total, row) => total + row.delivered, 0)
	return { delivered, received: sum("received"), base: hasDelivered.value ? delivered : sum("planned") }
})
</script>
