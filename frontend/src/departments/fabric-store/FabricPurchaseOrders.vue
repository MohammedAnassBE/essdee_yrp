<template>
	<div class="fabric-purchase-orders">
		<ListView
			doctype="Purchase Order"
			title="Purchase Orders"
			search-placeholder="Search Purchase Orders…"
			name-column-label="Purchase Order"
			row-mark="PO"
			min-table-width="980px"
			status-field="status"
			:status-options="statusOptions"
			:default-columns="defaultColumns"
			viewport-bounded
			clickable
			@row-click="openPurchaseOrder"
		>
			<template #toolbar-actions>
				<Button
					v-if="capability.can_create"
					label="Create Purchase Order"
					icon="pi pi-plus"
					@click="createPurchaseOrder"
				/>
			</template>
			<template #cell-status="{ value }">
				<DocumentStatusBadge :label="value || 'Draft'" />
			</template>
		</ListView>
	</div>
</template>

<script setup>
import Button from "primevue/button"
import { useRouter } from "vue-router"

import ListView from "../../components/common/ListView.vue"
import DocumentStatusBadge from "../../components/documents/DocumentStatusBadge.vue"

defineProps({ capability: { type: Object, required: true } })

const router = useRouter()
const defaultColumns = ["supplier", "transaction_date", "status", "grand_total"]
const statusOptions = ["Draft", "To Receive and Bill", "To Receive", "To Bill", "Completed", "Cancelled", "Closed"]

function openPurchaseOrder(row) {
	if (!row?.name) return
	router.push({ name: "fabric-purchase-order", params: { purchaseOrderId: row.name } })
}

function createPurchaseOrder() { router.push({ name: "fabric-purchase-order-new" }) }

</script>
