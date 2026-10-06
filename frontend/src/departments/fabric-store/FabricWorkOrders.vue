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

defineProps({ capability: { type: Object, required: true } })

const router = useRouter()
const defaultColumns = ["supplier", "item", "lot", "status"]
const columnLabels = { supplier: "Supplier / Location" }
const statusOptions = ["Open", "In Progress", "Completed", "Stopped", "Cancelled"]

function openWorkOrder(row) {
	if (!row?.name) return
	router.push({ name: "fabric-work-order", params: { workOrderId: row.name } })
}

function createWorkOrder() { router.push({ name: "fabric-work-order-new" }) }

function statusSeverity(status) {
	if (status === "Completed") return "success"
	if (["Stopped", "Cancelled"].includes(status)) return "danger"
	if (status === "In Progress") return "info"
	return "secondary"
}
</script>
