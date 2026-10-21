<template>
	<div class="fabric-work-orders">
		<ListView
			doctype="YRP Work Order"
			title="Work Orders"
			search-placeholder="Search Work Orders…"
			name-column-label="Work Order"
			row-mark="WO"
			min-table-width="1040px"
			status-field="status"
			:status-options="statusOptions"
			:default-columns="defaultColumns"
			:column-labels="columnLabels"
			:filters="filters"
			viewport-bounded
			clickable
			@row-click="openWorkOrder"
		>
			<template #toolbar-actions>
				<Button v-if="capability.can_create" label="Create Work Order" icon="pi pi-plus" @click="createWorkOrder" />
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
	filters: { type: Array, default: () => [] },
	viewRouteName: { type: String, default: "fabric-work-order" },
	newRouteName: { type: String, default: "fabric-work-order-new" },
})

const router = useRouter()
const defaultColumns = ["supplier", "item", "lot", "status"]
const columnLabels = { supplier: "Supplier / Location" }
const statusOptions = [
	"Draft",
	"Submitted",
	"Partially Delivered",
	"Fully Delivered",
	"Partially Received",
	"Fully Received",
	"Partially Billed",
	"Fully Billed",
	"Close Request",
	"Closed",
	"Cancelled",
]

function openWorkOrder(row, snapshot) {
	return openListDocument(router, row, snapshot, { routeName: props.viewRouteName, paramName: "workOrderId" })
}

function createWorkOrder() { router.push({ name: props.newRouteName }) }

</script>
