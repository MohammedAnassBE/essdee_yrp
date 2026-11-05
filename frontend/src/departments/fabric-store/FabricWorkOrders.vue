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
			:custom-bulk-actions="bulkActions"
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
import { computed, onMounted, ref } from "vue"
import { useRouter } from "vue-router"

import { approveCloseRequests, getWorkOrderClosePermission } from "../../api/planning.js"
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

/** Approves pending Close Requests; the server reports orders that are not pending as failures. */
const APPROVE_CLOSE = {
	action: "approve_close",
	label: "Approve Close",
	icon: "pi pi-check-circle",
	severity: "primary",
	done: "closed",
	async run(rows) {
		const { approved = [], failed = [] } = await approveCloseRequests(rows.map((row) => row.name))
		return { done: approved, failed: failed.map(({ work_order, error }) => ({ name: work_order, error })) }
	},
}
const canApproveClose = ref(false)
const bulkActions = computed(() => (canApproveClose.value ? [APPROVE_CLOSE] : []))

onMounted(async () => {
	try {
		canApproveClose.value = Boolean((await getWorkOrderClosePermission())?.is_close_manager)
	} catch {
		canApproveClose.value = false
	}
})

function openWorkOrder(row, snapshot) {
	return openListDocument(router, row, snapshot, { routeName: props.viewRouteName, paramName: "workOrderId" })
}

function createWorkOrder() { router.push({ name: props.newRouteName }) }

</script>
