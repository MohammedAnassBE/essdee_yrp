<template>
	<div class="production-orders">
		<ListView
			doctype="YRP Production Order"
			title="Production Orders"
			:eyebrow="eyebrow"
			subtitle="Quantities, delivery commitments and approvals"
			search-placeholder="Search Production Orders…"
			name-column-label="Production Order"
			row-mark="PPO"
			min-table-width="980px"
			status-field="status"
			:initial-status="initialStatus"
			:status-options="statusOptions"
			:default-columns="defaultColumns"
			viewport-bounded
			clickable
			selectable
			@row-click="openProductionOrder"
			@selection-change="selectedRows = $event"
		>
			<template #toolbar-actions>
				<Button v-if="selectedNames.length" :label="`Create Purchase Order (${selectedNames.length})`" icon="pi pi-shopping-cart" severity="secondary" outlined @click="purchaseOrderVisible = true" />
				<Button v-if="capability.can_create" label="Create Production Order" icon="pi pi-plus" @click="createProductionOrder" />
			</template>
			<template #cell-status="{ value, row }">
				<DocumentStatusBadge :docstatus="row.docstatus" :label="Number(row.docstatus) === 2 ? '' : value || ''" />
			</template>
		</ListView>
		<ProductionOrderPurchaseOrderDialog v-model:visible="purchaseOrderVisible" :production-orders="selectedNames" />
	</div>
</template>

<script setup>
import Button from "primevue/button"
import { computed, ref } from "vue"
import { useRouter } from "vue-router"

import ListView from "../../components/common/ListView.vue"
import DocumentStatusBadge from "../../components/documents/DocumentStatusBadge.vue"
import { openListDocument } from "../../router/listDocumentNavigation.js"
import ProductionOrderPurchaseOrderDialog from "./ProductionOrderPurchaseOrderDialog.vue"
import { productionOrderStatusOptions as statusOptions } from "./productionOrderOptions.js"

const props = defineProps({
	capability: { type: Object, required: true },
	viewRouteName: { type: String, default: "sales-production-order" },
	newRouteName: { type: String, default: "sales-production-order-new" },
	initialStatus: { type: String, default: "" },
	eyebrow: { type: String, default: "Sales" },
})

const router = useRouter()
const defaultColumns = ["item", "production_term", "delivery_date", "status"]
const selectedRows = ref([])
const selectedNames = computed(() => selectedRows.value.map((row) => row.name))
const purchaseOrderVisible = ref(false)

function openProductionOrder(row, snapshot) {
	return openListDocument(router, row, snapshot, { routeName: props.viewRouteName, paramName: "productionOrderId" })
}

function createProductionOrder() {
	router.push({ name: props.newRouteName })
}
</script>
