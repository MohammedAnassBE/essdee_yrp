<template>
	<div class="pd-detail__section">
		<h4>Work Orders</h4>
		<table class="erp-data-table pf-table">
			<thead>
				<tr>
					<th>Work Order</th><th>Supplier</th><th>Status</th><th>First DC</th><th>Last GRN</th>
					<th class="erp-number">Planned {{ isCloth ? "Kg" : "pcs" }}</th>
					<th class="erp-number">Delivered {{ isCloth || step.kind === "cutting" ? "Kg" : "pcs" }}</th>
					<th class="erp-number">Received {{ isCloth ? "Kg" : "pcs" }}</th>
				</tr>
			</thead>
			<tbody>
				<tr v-for="order in workOrders" :key="order.name">
					<td><router-link class="pd-link" :to="`/planning/work-orders/${encodeURIComponent(order.name)}`">{{ order.name }}</router-link></td>
					<td>{{ order.supplier_name || order.supplier }}</td>
					<td><span class="pd-state" :class="`pd-state--${orderTone(order)}`">{{ order.status }}</span></td>
					<td>{{ formatDisplayDate(order.first_dc) }}</td>
					<td>{{ formatDisplayDate(order.last_grn) }}</td>
					<td class="erp-number">{{ formatQuantity(order.planned, isCloth) }}</td>
					<td class="erp-number">{{ formatQuantity(order.delivered, isCloth || step.kind === "cutting") }}</td>
					<td class="erp-number">{{ formatQuantity(order.received, isCloth) }}</td>
				</tr>
			</tbody>
		</table>
	</div>
</template>

<script setup>
import { computed } from "vue"

import { formatDisplayDate } from "../../../utils/dateFormat.js"
import { formatQuantity } from "./dashboardFormat.js"

/** Work Orders of one lot process with their dates and quantities. */
const props = defineProps({
	step: { type: Object, required: true },
	workOrders: { type: Array, default: () => [] },
})
const DONE = ["Fully Received", "Partially Billed", "Fully Billed", "Close Request", "Closed"]
const PARTIAL = ["Partially Delivered", "Fully Delivered", "Partially Received"]
const isCloth = computed(() => props.step.kind === "cloth")
const orderTone = (order) => (DONE.includes(order.status) ? "done" : PARTIAL.includes(order.status) ? "partial" : "idle")
</script>
