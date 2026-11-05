<template>
	<h3 class="pf-modal__h">Work Orders <em>{{ workOrders.length }}</em></h3>
	<div class="pf-table-wrap">
		<table class="erp-data-table lot-table pf-table pf-breakdown">
			<thead>
				<tr><th>Work Order</th><th>Supplier</th><th>Status</th><th>Colours</th><th class="erp-number">Planned</th><th class="erp-number">Delivered</th><th class="erp-number">Received</th><th>First DC · Last GRN</th></tr>
			</thead>
			<tbody>
				<tr v-for="row in workOrders" :key="row.name">
					<td><button type="button" class="pf-wo__name" @click="emit('open', row)">{{ row.name }}</button></td>
					<td>{{ row.supplier_name }}</td>
					<td><DocumentStatusBadge :docstatus="row.docstatus" :label="row.status" /></td>
					<td class="pf-breakdown__colours" :title="row.colours.join(', ')">{{ row.colours.join(", ") || "—" }}</td>
					<td class="erp-number">{{ formatNumber(row.planned) }}</td>
					<td v-if="clothByOrder[row.name] !== undefined" class="erp-number">{{ formatNumber(clothByOrder[row.name]) }} {{ cloth[0]?.uom }}</td>
					<td v-else class="erp-number" :class="tone(statusTone(row.delivered, row.planned))">{{ formatNumber(row.delivered) }}</td>
					<td class="erp-number" :class="tone(statusTone(row.received, row.planned))">{{ formatNumber(row.received) }}</td>
					<td>{{ formatDisplayDate(row.first_dc) }}<br>{{ formatDisplayDate(row.last_grn) }}</td>
				</tr>
			</tbody>
		</table>
	</div>
</template>
<script setup>
import { computed } from "vue"
import DocumentStatusBadge from "../../../../components/documents/DocumentStatusBadge.vue"
import { formatDisplayDate } from "../../../../utils/dateFormat.js"
import { formatNumber, statusTone } from "./processFlow.js"
/** One row per Work Order of a step; cutting shows delivered cloth in its own UOM. */
const props = defineProps({
	workOrders: { type: Array, required: true },
	cloth: { type: Array, default: () => [] },
})
const emit = defineEmits(["open"])
const tone = (value) => (value ? `pf-tone-${value}` : "")
const clothByOrder = computed(() => props.cloth.reduce((result, row) => ({ ...result, [row.work_order]: (result[row.work_order] || 0) + row.delivered }), {}))
</script>
