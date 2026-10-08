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
import { openListDocument } from "../../router/listDocumentNavigation.js"

const props = defineProps({
	capability: { type: Object, required: true },
	viewRouteName: { type: String, default: "fabric-purchase-order" },
	newRouteName: { type: String, default: "fabric-purchase-order-new" },
})

const router = useRouter()
const defaultColumns = ["supplier", "transaction_date", "status", "grand_total"]
const statusOptions = ["Draft", "To Receive and Bill", "To Receive", "To Bill", "Completed", "Cancelled", "Closed"]

function openPurchaseOrder(row, snapshot) {
	return openListDocument(router, row, snapshot, { routeName: props.viewRouteName, paramName: "purchaseOrderId" })
}

function createPurchaseOrder() { router.push({ name: props.newRouteName }) }

</script>
