<template>
	<Tabs :value="activeTab" class="purchase-invoice-tabs erp-tabs" @update:value="emit('update:active-tab', $event)">
		<TabList>
			<Tab value="details">Details</Tab>
			<Tab value="items">Items &amp; GRNs</Tab>
			<Tab v-if="workspace.record?.against === 'YRP Work Order'" value="verification">Verification</Tab>
		</TabList>
		<TabPanels>
			<TabPanel value="details">
				<PurchaseInvoiceOverview :fields="workspace.details || []" />
			</TabPanel>
			<TabPanel value="items" class="purchase-invoice-items-grns">
				<h2 class="purchase-invoice-section-title">Items <span>{{ workspace.items?.length || 0 }}</span></h2>
				<PurchaseInvoiceGroupedItems
					:rows="workspace.items || []"
					:erp-sync-enabled="Boolean(workspace.erp_sync_enabled)"
				/>
				<h2 class="purchase-invoice-section-title">GRNs <span>{{ workspace.grns?.length || 0 }}</span></h2>
				<section class="purchase-invoice-grns erp-card" aria-label="Purchase Invoice GRNs">
					<div v-if="workspace.grns?.length" class="purchase-invoice-grns__table" role="region" tabindex="0">
						<table>
							<thead><tr><th>GRN</th><th>Date</th><th>Against</th><th>Supplier Doc No</th><th class="purchase-invoice-number">Qty</th><th class="purchase-invoice-number">Total</th></tr></thead>
							<tbody>
								<tr v-for="grn in workspace.grns" :key="grn.grn">
									<td><button type="button" class="purchase-invoice-link" @click="emit('open-grn', grn.grn)">{{ grn.grn }}</button></td>
									<td>{{ formatDisplayDate(grn.posting_date) }}</td>
									<td><DocumentLink :doctype="grn.against" :name="grn.against_id" :label="grn.against_id || '—'" /></td>
									<td>{{ grn.supplier_document_no || "—" }}</td>
									<td class="purchase-invoice-number">{{ number(grn.total_received_quantity) }}</td>
									<td class="purchase-invoice-number">{{ money(grn.grand_total) }}</td>
								</tr>
							</tbody>
						</table>
					</div>
					<div v-else class="purchase-invoice-grns__empty"><i class="pi pi-inbox" /><span>No GRNs are linked.</span></div>
				</section>
			</TabPanel>
			<TabPanel v-if="workspace.record?.against === 'YRP Work Order'" value="verification">
				<PurchaseInvoiceVerification
					:verification="workspace.verification || []"
					:debit-summary="workspace.debit_summary || []"
					:approvals="workspace.approvals || []"
					:work-orders="workspace.work_orders || []"
					@changed="emit('changed')"
				/>
			</TabPanel>
		</TabPanels>
	</Tabs>
</template>

<script setup>
import DocumentLink from "../../../components/common/DocumentLink.vue"
import Tab from "primevue/tab"
import TabList from "primevue/tablist"
import TabPanel from "primevue/tabpanel"
import TabPanels from "primevue/tabpanels"
import Tabs from "primevue/tabs"

import { formatDisplayDate } from "../../../utils/dateFormat.js"
import PurchaseInvoiceGroupedItems from "./PurchaseInvoiceGroupedItems.vue"
import PurchaseInvoiceOverview from "./PurchaseInvoiceOverview.vue"
import PurchaseInvoiceVerification from "./PurchaseInvoiceVerification.vue"

defineProps({
	activeTab: { type: String, required: true },
	workspace: { type: Object, required: true },
})
const emit = defineEmits(["update:active-tab", "open-grn", "changed"])

function money(input) {
	if (input === null || input === undefined || input === "") return "—"
	const numericValue = Number(input)
	return Number.isFinite(numericValue)
		? numericValue.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
		: "—"
}

function number(input) {
	if (input === null || input === undefined || input === "") return "—"
	const numericValue = Number(input)
	return Number.isFinite(numericValue)
		? numericValue.toLocaleString("en-IN", { maximumFractionDigits: 3 })
		: "—"
}
</script>

<style scoped>
.purchase-invoice-tabs { display: flex; min-height: 0; flex: 1; flex-direction: column; }
.purchase-invoice-tabs :deep(.p-tablist-tab-list) { padding-inline: 2px; }
.purchase-invoice-tabs :deep(.p-tab > span) { margin-left: 5px; padding: 2px 6px; color: var(--erp-text-muted); background: var(--erp-surface-muted); border-radius: var(--erp-pill-radius); font-size: var(--erp-font-size-min); }
.purchase-invoice-tabs :deep(.p-tabpanels) { min-height: 0; padding: 12px 0 0; overflow-y: auto; background: transparent; }
.purchase-invoice-items-grns { display: grid; gap: var(--erp-space-2); }
.purchase-invoice-section-title { margin: 0; color: var(--erp-text-secondary); font-size: var(--erp-font-size-table); font-weight: var(--erp-font-weight-bold); }
.purchase-invoice-section-title:not(:first-child) { margin-top: var(--erp-space-3); }
.purchase-invoice-section-title > span { margin-left: 5px; padding: 2px 6px; color: var(--erp-text-muted); background: var(--erp-surface-muted); border-radius: var(--erp-pill-radius); font-size: var(--erp-font-size-min); font-weight: 600; }
.purchase-invoice-grns { min-width: 0; overflow: hidden; border-color: var(--erp-border); box-shadow: var(--erp-shadow-xs); }
.purchase-invoice-grns__table { max-width: 100%; overflow: auto; }
.purchase-invoice-grns__table table { width: 100%; min-width: 850px; border-collapse: collapse; font-size: var(--erp-font-size-caption); }
.purchase-invoice-grns th, .purchase-invoice-grns td { padding: 9px 10px; text-align: left; border-right: 1px solid var(--erp-border); border-bottom: 1px solid var(--erp-border); }
.purchase-invoice-grns th { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 750; background: var(--erp-surface-muted); }
.purchase-invoice-grns th:last-child, .purchase-invoice-grns td:last-child { border-right: 0; }
.purchase-invoice-grns tbody tr:last-child td { border-bottom: 0; }
.purchase-invoice-number { text-align: right !important; font-variant-numeric: tabular-nums; }
.purchase-invoice-link { padding: 0; color: var(--erp-accent-hover); font: inherit; font-weight: 720; border: 0; background: transparent; cursor: pointer; }
.purchase-invoice-link:hover { text-decoration: underline; }
.purchase-invoice-grns__empty { display: grid; min-height: 150px; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); place-content: center; justify-items: center; gap: 8px; }
.purchase-invoice-grns__empty i { color: var(--erp-accent); font-size: 1.15rem; }
@media (max-width: 1050px) { .purchase-invoice-tabs :deep(.p-tabpanels) { overflow-y: visible; } }
</style>
