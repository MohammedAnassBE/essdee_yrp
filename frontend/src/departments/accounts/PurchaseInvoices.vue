<template>
	<DepartmentPage
		title="Purchase Invoices"
		back-to="/accounts"
		back-label="Accounts"
		:show-title="false"
		flat
		full-width
		inline-navigation
	>
		<section class="purchase-invoices-page erp-workspace" aria-label="Purchase Invoices">
			<div v-if="loading" class="purchase-invoices-page__loading">
				<Skeleton height="76px" />
				<Skeleton height="420px" />
			</div>
			<WorkspaceLoadError
				v-else-if="loadError"
				:message="loadError"
				:loading="loading"
				@retry="load"
			/>
			<Message v-else-if="!capability?.can_read" severity="warn" :closable="false">
				You do not have permission to view Purchase Invoices.
			</Message>
			<ListView
				v-else
				doctype="YRP Purchase Invoice"
				title="Purchase Invoices"
				eyebrow="Accounts"
				subtitle="Supplier bills, approvals and ERP invoice status"
				search-placeholder="Search Purchase Invoices…"
				name-column-label="Purchase Invoice"
				row-mark="MPI"
				min-table-width="1040px"
				status-field="status"
				:status-options="PURCHASE_INVOICE_STATUS_OPTIONS"
				:default-columns="PURCHASE_INVOICE_LIST_COLUMNS"
				default-order-by="posting_date desc"
				:allow-bulk-actions="false"
				viewport-bounded
				clickable
				@row-click="openPurchaseInvoice"
			>
				<template #toolbar-actions>
					<Button
						v-if="capability.can_create"
						label="New Purchase Invoice"
						icon="pi pi-plus"
						@click="createPurchaseInvoice"
					/>
				</template>
				<template #cell-status="{ value }">
					<DocumentStatusBadge :label="value || 'Draft'" :class="statusClass(value)" />
				</template>
			</ListView>
		</section>
	</DepartmentPage>
</template>

<script setup>
import Button from "primevue/button"
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import { onMounted, ref } from "vue"
import { useRouter } from "vue-router"

import { getAccountsCapabilities } from "../../api/accounts.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import ListView from "../../components/common/ListView.vue"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import DocumentStatusBadge from "../../components/documents/DocumentStatusBadge.vue"
import { openListDocument } from "../../router/listDocumentNavigation.js"
import {
	PURCHASE_INVOICE_LIST_COLUMNS,
	PURCHASE_INVOICE_STATUS_OPTIONS,
} from "./accountsViews.js"

const router = useRouter()
const loading = ref(true)
const loadError = ref("")
const capability = ref(null)

async function load() {
	loading.value = true
	loadError.value = ""
	try {
		capability.value = (await getAccountsCapabilities())?.sections?.purchase_invoices || null
	} catch (reason) {
		capability.value = null
		loadError.value = reason?.message || "Unable to load Purchase Invoices."
	} finally {
		loading.value = false
	}
}

function openPurchaseInvoice(row, snapshot) {
	return openListDocument(router, row, snapshot, {
		routeName: "accounts-purchase-invoice",
		paramName: "purchaseInvoiceId",
	})
}

function createPurchaseInvoice() {
	router.push({ name: "accounts-purchase-invoice-new" })
}

function statusClass(status) {
	return `purchase-invoice-status--${String(status || "draft").toLowerCase().replaceAll(" ", "-")}`
}

onMounted(load)
</script>

<style scoped>
.purchase-invoices-page { width: 100%; max-width: 1800px; min-width: 0; margin: 0 auto; padding: 2px 0 var(--erp-space-5); }
.purchase-invoices-page__loading { display: grid; gap: var(--erp-space-3); padding-top: 2px; }
.purchase-invoices-page__loading :deep(.p-skeleton) { border-radius: var(--erp-panel-radius); }
:deep(.purchase-invoice-status--draft) { color: var(--erp-warning); background: var(--erp-warning-soft); border-color: var(--erp-attention-border); }
:deep(.purchase-invoice-status--approval-initiated) { color: var(--erp-danger); background: var(--erp-danger-soft); border-color: color-mix(in srgb, var(--erp-danger) 22%, transparent); }
:deep(.purchase-invoice-status--approval-pending) { color: var(--erp-warning); background: var(--erp-warning-soft); border-color: var(--erp-attention-border); }
:deep(.purchase-invoice-status--approved) { color: var(--erp-success); background: var(--erp-success-soft); border-color: color-mix(in srgb, var(--erp-success) 18%, transparent); }
:deep(.purchase-invoice-status--submitted) { color: var(--erp-info); background: var(--erp-info-soft); border-color: color-mix(in srgb, var(--erp-info) 18%, transparent); }
:deep(.purchase-invoice-status--cancelled) { color: var(--erp-text); background: var(--erp-surface-muted); border-color: var(--erp-border-strong); }
</style>
