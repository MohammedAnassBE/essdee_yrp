<template>
	<p v-if="!logs.length" class="erp-empty-state"><span class="erp-empty-state__text">No dispatches recorded yet.</span></p>
	<div v-else class="finishing-scroll" role="region" tabindex="0" aria-label="Dispatch history">
		<table class="finishing-table">
			<thead>
				<tr>
					<th class="finishing-table__index">#</th>
					<th>Stock Entry</th>
					<th>Source</th>
					<th>Posting</th>
					<th class="erp-number">Boxes</th>
					<th class="erp-number">Pieces</th>
					<th class="erp-number">Dispatched After</th>
					<th class="erp-number">Cutting Qty</th>
					<th class="erp-number">Dispatch % Before</th>
					<th class="erp-number">Dispatch % After</th>
					<th>Status</th>
				</tr>
			</thead>
			<tbody>
				<tr v-for="(log, index) in logs" :key="`${log.stock_entry}-${index}`" :class="{ 'dispatch-history__cancelled': log.cancelled }">
					<td class="finishing-table__index">{{ index + 1 }}</td>
					<td>
						<button v-if="log.stock_entry" type="button" class="dispatch-history__open" @click="emit('open', 'YRP Stock Entry', log.stock_entry)">{{ log.stock_entry }}</button>
						<span v-else>—</span>
					</td>
					<td><DocumentLink :doctype="log.source_doctype" :name="log.source_name" :label="log.source_name ? `${log.source_doctype || ''} ${log.source_name}`.trim() : '—'" /></td>
					<td class="dispatch-history__date">{{ formatDate(log.posting_date) }} {{ (log.posting_time || "").slice(0, 8) }}</td>
					<td class="erp-number">{{ formatQuantity(log.dispatch_boxes) }}</td>
					<td class="erp-number">{{ formatQuantity(log.dispatch_pieces) }}</td>
					<td class="erp-number">{{ formatQuantity(log.total_dispatched_pieces_after) }}</td>
					<td class="erp-number">{{ formatQuantity(log.cutting_qty) }}</td>
					<td class="erp-number">{{ percent(log.dispatch_percentage_before) }}</td>
					<td class="erp-number">{{ percent(log.dispatch_percentage_after) }}</td>
					<td><DocumentStatusBadge :label="log.cancelled ? 'Cancelled' : 'Submitted'" /></td>
				</tr>
			</tbody>
		</table>
	</div>
</template>

<script setup>
import DocumentLink from "../../../components/common/DocumentLink.vue"
import DocumentStatusBadge from "../../../components/documents/DocumentStatusBadge.vue"
import { formatDate } from "../../../components/reports/reportUtils.js"
import { formatQuantity } from "../finishingViews.js"

defineProps({ logs: { type: Array, default: () => [] } })
const emit = defineEmits(["open"])

function percent(value) {
	return `${Number(value || 0).toFixed(2)}%`
}
</script>

<style scoped>
.dispatch-history__open { padding: 0; color: var(--erp-accent-dark); background: none; border: 0; font: inherit; font-weight: 650; cursor: pointer; }
.dispatch-history__open:hover, .dispatch-history__open:focus-visible { text-decoration: underline; }
.dispatch-history__date { font-variant-numeric: tabular-nums; }
.dispatch-history__cancelled td { color: var(--erp-text-muted); text-decoration: line-through; }
.dispatch-history__cancelled td:last-child { text-decoration: none; }
</style>
