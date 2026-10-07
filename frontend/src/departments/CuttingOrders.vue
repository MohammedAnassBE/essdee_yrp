<template>
	<DepartmentPage title="Cutting Orders" accent="#059669" back-to="/cutting" back-label="Cutting" :show-title="false" flat full-width>
		<div class="cutting-list erp-workspace">
			<WorkspaceLoadError v-if="loadError" :message="loadError" :loading="loadingCapability" @retry="load" />
			<WorkspaceLoadError v-else-if="capability && !capability.can_read" title="Cutting Orders unavailable" message="You do not have permission to view Cutting Orders." :retryable="false" />
			<ListView
				v-else-if="capability?.can_read"
				doctype="SD YRP Cutting Order"
				title="Cutting Orders"
				search-placeholder="Search Cutting Orders…"
				name-column-label="Cutting Order"
				row-mark="CO"
				min-table-width="1040px"
				status-field="co_status"
				:status-options="statusOptions"
				:default-columns="defaultColumns"
				viewport-bounded
				clickable
				@row-click="openCuttingOrder"
			>
				<template #toolbar-actions>
					<Button v-if="capability.can_create" class="list-primary-action" label="Create Cutting Order" icon="pi pi-plus" @click="createCuttingOrder" />
				</template>
				<template #cell-co_status="{ value }">
					<DocumentStatusBadge :label="value || 'Draft'" />
				</template>
			</ListView>
		</div>
	</DepartmentPage>
</template>

<script setup>
import Button from "primevue/button"
import { onMounted, ref } from "vue"
import { useRouter } from "vue-router"

import { getCuttingCapabilities } from "../api/cuttingWorkspaces.js"
import DepartmentPage from "../components/DepartmentPage.vue"
import ListView from "../components/common/ListView.vue"
import WorkspaceLoadError from "../components/common/WorkspaceLoadError.vue"
import DocumentStatusBadge from "../components/documents/DocumentStatusBadge.vue"

const router = useRouter()
const capability = ref(null)
const loadError = ref("")
const loadingCapability = ref(true)
const defaultColumns = ["cutting_order_detail", "item", "co_status", "lay_no", "cutting_location"]
const statusOptions = ["Draft", "Submitted", "Cutting In Progress", "Partially Completed", "Completed"]

function openCuttingOrder(row) {
	if (row?.name) router.push(`/cutting/orders/${encodeURIComponent(row.name)}`)
}

function createCuttingOrder() {
	router.push("/cutting/orders/new")
}

async function load() {
	loadingCapability.value = true
	loadError.value = ""
	try {
		const capabilities = await getCuttingCapabilities()
		capability.value = capabilities?.["cutting-orders"] || { can_read: false, can_create: false }
	} catch (reason) {
		capability.value = null
		loadError.value = reason?.message || "Unable to load Cutting Orders."
	} finally {
		loadingCapability.value = false
	}
}

onMounted(load)
</script>

<style scoped>
.cutting-list { padding-top: 0; }
</style>
