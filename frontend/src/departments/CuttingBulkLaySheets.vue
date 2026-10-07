<template>
	<DepartmentPage title="Bulk LaySheets" accent="#059669" back-to="/cutting" back-label="Cutting" :show-title="false" flat full-width>
		<div class="cutting-list erp-workspace">
			<ListView
				v-if="capability"
				doctype="SD YRP Cutting Bulk Lay Sheets"
				title="Bulk LaySheets"
				search-placeholder="Search Bulk LaySheets…"
				name-column-label="Bulk LaySheets"
				row-mark="BL"
				min-table-width="980px"
				status-field="status"
				:status-options="statusOptions"
				:default-columns="defaultColumns"
				clickable
				@row-click="openBulkLaySheets"
			>
				<template #toolbar-actions>
					<Button v-if="capability.can_create" class="list-primary-action" label="Create Bulk LaySheets" icon="pi pi-plus" @click="createBulkLaySheets" />
				</template>
				<template #cell-status="{ value }">
					<Tag :value="value || 'Setup'" :severity="statusSeverity(value)" rounded />
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
const defaultColumns = ["main_lot", "from_location", "posting_date", "status"]
const statusOptions = ["Setup", "Lay Sheets Created", "In Progress", "Ready to Print", "Completed"]

function openBulkLaySheets(row) {
	if (row?.name) router.push(`/cutting/bulk-lay-sheets/${encodeURIComponent(row.name)}`)
}

function createBulkLaySheets() {
	router.push("/cutting/bulk-lay-sheets/new")
}

function statusSeverity(status) {
	if (status === "Completed") return "success"
	if (status === "Ready to Print") return "info"
	if (["Lay Sheets Created", "In Progress"].includes(status)) return "warn"
	return "secondary"
}

onMounted(async () => {
	const capabilities = await getCuttingCapabilities()
	capability.value = capabilities?.["bulk-lay-sheets"] || { can_read: false, can_create: false }
})
</script>

<style scoped>
.cutting-list { padding-top: 0; }
</style>
