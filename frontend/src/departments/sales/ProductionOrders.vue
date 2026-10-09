<template>
	<div class="production-orders">
		<ListView
			doctype="YRP Production Order"
			title="Production Orders"
			eyebrow="Sales"
			subtitle="Quantities, delivery commitments and approvals"
			search-placeholder="Search Production Orders…"
			name-column-label="Production Order"
			row-mark="PPO"
			min-table-width="980px"
			status-field="status"
			:status-options="statusOptions"
			:default-columns="defaultColumns"
			viewport-bounded
			clickable
			@row-click="openProductionOrder"
		>
			<template #toolbar-actions>
				<Button v-if="capability.can_create" label="Create Production Order" icon="pi pi-plus" @click="createProductionOrder" />
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

defineProps({ capability: { type: Object, required: true } })

const router = useRouter()
const defaultColumns = ["item", "production_term", "delivery_date", "status"]
const statusOptions = ["Draft", "PPO Request", "Open", "Pending Request", "Item Changed", "Not Processed", "Closed", "Cancelled"]

function openProductionOrder(row, snapshot) {
	return openListDocument(router, row, snapshot, { routeName: "sales-production-order", paramName: "productionOrderId" })
}

function createProductionOrder() {
	router.push({ name: "sales-production-order-new" })
}
</script>
