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
			viewport-bounded
			clickable
			@row-click="openWorkOrder"
		>
			<template #toolbar-actions>
				<Button v-if="capability.can_create" label="Create Work Order" icon="pi pi-plus" @click="createWorkOrder" />
			</template>
			<template #cell-status="{ value }">
				<Tag :value="value || 'Draft'" :severity="statusSeverity(value)" rounded />
			</template>
		</ListView>
	</div>
</template>

<script setup>
import Button from "primevue/button"
import Tag from "primevue/tag"
import { useRouter } from "vue-router"

import ListView from "../../components/common/ListView.vue"

const props = defineProps({
	capability: { type: Object, required: true },
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

function openWorkOrder(row) {
	if (!row?.name) return
	router.push({ name: props.viewRouteName, params: { workOrderId: row.name } })
}

function createWorkOrder() { router.push({ name: props.newRouteName }) }

function statusSeverity(status) {
	if (["Fully Delivered", "Fully Received", "Fully Billed", "Closed"].includes(status)) return "success"
	if (status === "Cancelled") return "danger"
	if (["Partially Delivered", "Partially Received", "Partially Billed", "Close Request", "Draft"].includes(status)) return "warn"
	if (status === "Submitted") return "info"
	return "secondary"
}
</script>
