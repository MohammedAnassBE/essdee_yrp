<template>
	<DepartmentPage title="Cutting Orders" accent="#0b8f65" back-to="/cutting" back-label="Cutting" :show-title="false" flat>
		<div class="cutting-list erp-workspace">
			<ListView
				v-if="capability"
				doctype="SD YRP Cutting Order"
				title="Cutting Orders"
				search-placeholder="Search Cutting Orders…"
				name-column-label="Cutting Order"
				row-mark="CO"
				min-table-width="1040px"
				status-field="co_status"
				:status-options="statusOptions"
				:default-columns="defaultColumns"
				clickable
				@row-click="openCuttingOrder"
			>
				<template #toolbar-actions>
					<Button v-if="capability.can_create" class="list-primary-action" label="Create Cutting Order" icon="pi pi-plus" @click="createCuttingOrder" />
				</template>
				<template #cell-co_status="{ value }">
					<Tag :value="value || 'Draft'" :severity="statusSeverity(value)" rounded />
				</template>
			</ListView>
		</div>
	</DepartmentPage>
</template>

<script setup>
import Button from "primevue/button"
import Tag from "primevue/tag"
import { onMounted, ref } from "vue"
import { useRouter } from "vue-router"

import { getCuttingCapabilities } from "../api/cuttingWorkspaces.js"
import DepartmentPage from "../components/DepartmentPage.vue"
import ListView from "../components/common/ListView.vue"

const router = useRouter()
const capability = ref(null)
const defaultColumns = ["cutting_order_detail", "item", "co_status", "lay_no", "cutting_location"]
const statusOptions = ["Draft", "Submitted", "Cutting In Progress", "Partially Completed", "Completed"]

function openCuttingOrder(row) {
	if (row?.name) router.push(`/cutting/orders/${encodeURIComponent(row.name)}`)
}

function createCuttingOrder() {
	router.push("/cutting/orders/new")
}

function statusSeverity(status) {
	if (status === "Completed") return "success"
	if (status === "Partially Completed") return "warn"
	if (status === "Cutting In Progress") return "info"
	return "secondary"
}

onMounted(async () => {
	const capabilities = await getCuttingCapabilities()
	capability.value = capabilities?.["cutting-orders"] || { can_read: false, can_create: false }
})
</script>

<style scoped>
.cutting-list { padding-top: 0; }
</style>
