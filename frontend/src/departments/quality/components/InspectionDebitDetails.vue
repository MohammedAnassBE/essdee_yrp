<template>
	<section v-if="debits.length" class="quality-page__section" aria-label="Debit Details">
		<h2>Debit Details · {{ debits.length }} · Total {{ money(total) }}</h2>
		<div class="inspection-debits" role="region" aria-label="Inspection debits" tabindex="0">
			<table>
				<thead><tr><th>Debit</th><th>Type</th><th>Value</th><th>Reason</th><th>Document</th><th>Status</th><th>Approved by</th><th>Created</th></tr></thead>
				<tbody>
					<tr v-for="debit in debits" :key="debit.name">
						<td><DocumentLink doctype="YRP Debit" :name="debit.name" /></td>
						<td>{{ debit.debit_type || '—' }}</td><td>{{ money(debit.debit_value) }}</td><td>{{ debit.reason || '—' }}</td>
						<td><a v-if="debit.debit_document" :href="debit.debit_document" target="_blank" rel="noopener">Open document</a><template v-else>—</template></td>
						<td><DocumentStatusBadge v-if="debit.status" :label="debit.status" /></td>
						<td><DocumentLink doctype="User" :name="debit.approved_by" /></td><td>{{ formatDocumentOverviewValue({ fieldtype: 'Datetime', value: debit.creation }) }}</td>
					</tr>
				</tbody>
			</table>
		</div>
	</section>
</template>

<script setup>
import { computed } from "vue"
import DocumentLink from "../../../components/common/DocumentLink.vue"
import DocumentStatusBadge from "../../../components/documents/DocumentStatusBadge.vue"
import { formatDocumentOverviewValue } from "../../../utils/documentOverview.js"
const props = defineProps({ debits: { type: Array, default: () => [] } })
const money = (value) => formatDocumentOverviewValue({ fieldtype: "Currency", precision: 2, value: Number(value || 0) })
const total = computed(() => props.debits.reduce((sum, debit) => sum + Number(debit.debit_value || 0), 0))
</script>

<style scoped>
.inspection-debits { width: 100%; max-width: 100%; overflow-x: auto; }
.inspection-debits table { width: 100%; border-collapse: collapse; text-align: left; }
.inspection-debits th, .inspection-debits td { padding: var(--erp-space-3); border-bottom: 1px solid var(--erp-border); vertical-align: top; }
.inspection-debits th { color: var(--erp-text-muted); white-space: nowrap; }
.inspection-debits td { min-width: 110px; overflow-wrap: anywhere; }
.inspection-debits a { color: var(--erp-accent-ink); }
.inspection-debits:focus-visible { outline: 2px solid var(--erp-accent); }
</style>
