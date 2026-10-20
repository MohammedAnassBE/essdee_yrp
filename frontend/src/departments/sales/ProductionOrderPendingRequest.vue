<template>
	<section v-if="request" class="ppo-pending erp-card" aria-label="Pending request">
		<h2>Pending request</h2>
		<p>{{ requestLabel }}</p>
		<dl>
			<template v-if="request.requested_status"><dt>Requested status</dt><dd>{{ request.previous_status || '—' }} → {{ request.requested_status }}</dd></template>
			<template v-if="request.source_production_order"><dt>Source Production Order</dt><dd><DocumentLink doctype="YRP Production Order" :name="request.source_production_order" /></dd><dt>Source status</dt><dd>{{ request.source_status || '—' }}</dd></template>
			<template v-if="request.target_previous_status"><dt>Destination status before request</dt><dd>{{ request.target_previous_status }}</dd></template>
			<template v-if="request.requested_by"><dt>{{ request.request_type === 'quantity_ratio' ? 'Requested by team' : 'Requested by' }}</dt><dd>{{ request.requested_by }}</dd></template>
			<template v-if="request.requested_user"><dt>Requested by user</dt><dd>{{ request.requested_user }}</dd></template>
			<template v-if="request.requested_on"><dt>Requested on</dt><dd>{{ productionOrderFieldDisplay({ fieldtype: 'Datetime', value: request.requested_on }) }}</dd></template>
			<template v-if="request.reason"><dt>Reason</dt><dd class="ppo-pending__reason">{{ request.reason }}</dd></template>
		</dl>
		<div v-if="rows.length" class="ppo-pending__table"><table><thead><tr><th>Size</th><th>Quantity (current → requested)</th><th v-if="isTransfer">Transfer quantity</th><th v-else>Ratio (current → requested)</th></tr></thead><tbody><tr v-for="row in rows" :key="row.size"><th>{{ row.size }}</th><td>{{ row.quantity }}</td><td>{{ isTransfer ? row.transferred : row.ratio }}</td></tr></tbody></table></div>
	</section>
</template>

<script setup>
import { computed } from "vue"
import DocumentLink from "../../components/common/DocumentLink.vue"
import { productionOrderFieldDisplay } from "./productionOrderDisplay.js"
import { productionOrderRequestRows } from "./productionOrderPendingRequest.js"

const props = defineProps({ request: { type: Object, default: null } })
const rows = computed(() => productionOrderRequestRows(props.request))
const isTransfer = computed(() => props.request?.request_type === "transfer")
const requestLabel = computed(() => ({ status: "Status change", quantity_ratio: "Quantity and ratio changes", transfer: "Incoming quantity transfer", ppo_approval: "PPO approval" }[props.request?.request_type] || ""))
</script>

<style scoped>
.ppo-pending { min-width: 0; padding: 13px; color: var(--erp-text); background: var(--erp-surface); }
.ppo-pending h2 { margin: 0; font-size: var(--erp-font-size-md); }
.ppo-pending p { margin: 6px 0 12px; color: var(--erp-text-secondary); }
.ppo-pending dl { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 2fr); gap: 8px 14px; margin: 0; font-size: var(--erp-font-size-caption); }
.ppo-pending dt { color: var(--erp-text-muted); }
.ppo-pending dd { margin: 0; overflow-wrap: anywhere; }
.ppo-pending__reason { white-space: pre-wrap; }
.ppo-pending__table { margin-top: 12px; overflow-x: auto; }
.ppo-pending table { width: 100%; border-collapse: collapse; font-size: var(--erp-font-size-caption); }
.ppo-pending th, .ppo-pending td { padding: 8px; text-align: left; border: 1px solid var(--erp-border); }
.ppo-pending th { color: var(--erp-text); background: var(--erp-surface-soft); }
</style>
