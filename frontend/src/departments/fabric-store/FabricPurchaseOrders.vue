<template>
	<div class="fabric-purchase-orders">
		<ListView
			doctype="Purchase Order"
			title="Purchase Orders"
			search-placeholder="Search Purchase Orders…"
			name-column-label="Purchase Order"
			row-mark="PO"
			min-table-width="980px"
			status-field="yrp_fulfillment_status"
			:status-options="purchaseOrderStatusOptions"
			:default-columns="defaultColumns"
			:extra-fields="['status', 'is_yrp_managed']"
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
			<template #cell-yrp_fulfillment_status="{ row }">
				<DocumentStatusBadge v-bind="purchaseOrderStatusBadgeProps(row)" />
			</template>
			<template #cell-status="{ row }">
				<DocumentStatusBadge v-bind="purchaseOrderStatusBadgeProps(row)" />
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
import { purchaseOrderStatusLabel, purchaseOrderStatusOptions, purchaseOrderStatusTone } from "../../utils/purchaseOrderStatus.js"

const props = defineProps({
	capability: { type: Object, required: true },
	viewRouteName: { type: String, default: "fabric-purchase-order" },
	newRouteName: { type: String, default: "fabric-purchase-order-new" },
})

const router = useRouter()
const defaultColumns = ["supplier", "transaction_date", "yrp_fulfillment_status", "grand_total"]

function purchaseOrderStatusBadgeProps(row) {
	const label = purchaseOrderStatusLabel(row)
	return { label, tone: purchaseOrderStatusTone(label) }
}

function openPurchaseOrder(row, snapshot) {
	return openListDocument(router, row, snapshot, { routeName: props.viewRouteName, paramName: "purchaseOrderId" })
}

function createPurchaseOrder() { router.push({ name: props.newRouteName }) }

</script>
