<template>
	<DepartmentPage title="Bulk LaySheets" back-to="/cutting" back-label="Cutting" :show-title="false" flat full-width inline-navigation>
		<div class="cutting-list erp-workspace">
			<WorkspaceLoadError v-if="loadError" :message="loadError" :loading="loadingCapability" @retry="load" />
			<WorkspaceLoadError v-else-if="capability && !capability.can_read" title="Bulk LaySheets unavailable" message="You do not have permission to view Bulk LaySheets." :retryable="false" />
			<ListView
				v-else
				:can-read="Boolean(capability?.can_read)"
				doctype="SD YRP Cutting Bulk Lay Sheets"
				title="Bulk LaySheets"
				search-placeholder="Search Bulk LaySheets…"
				name-column-label="Bulk LaySheets"
				row-mark="BL"
				min-table-width="980px"
				status-field="status"
				:status-options="statusOptions"
				:default-columns="defaultColumns"
				viewport-bounded
				clickable
				@row-click="openBulkLaySheets"
			>
				<template #toolbar-actions>
					<Button v-if="capability?.can_create" class="list-primary-action" label="Create Bulk LaySheets" icon="pi pi-plus" @click="createBulkLaySheets" />
				</template>
				<template #cell-status="{ value }">
					<DocumentStatusBadge :label="value || 'Setup'" />
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
import { openListDocument } from "../router/listDocumentNavigation.js"

const router = useRouter()
const capability = ref(null)
const loadError = ref("")
const loadingCapability = ref(true)
const defaultColumns = ["main_lot", "from_location", "posting_date", "status"]
const statusOptions = ["Setup", "Lay Sheets Created", "In Progress", "Ready to Print", "Completed"]

function openBulkLaySheets(row, snapshot) {
	return openListDocument(router, row, snapshot, { routeName: "cutting-bulk-lay-sheet", paramName: "bulkLaySheetsId" })
}

function createBulkLaySheets() {
	router.push("/cutting/bulk-lay-sheets/new")
}

async function load() {
	loadingCapability.value = true
	loadError.value = ""
	try {
		const capabilities = await getCuttingCapabilities()
		capability.value = capabilities?.["bulk-lay-sheets"] || { can_read: false, can_create: false }
	} catch (reason) {
		capability.value = null
		loadError.value = reason?.message || "Unable to load Bulk LaySheets."
	} finally {
		loadingCapability.value = false
	}
}

onMounted(load)
</script>

<style scoped>
.cutting-list { padding-top: 0; }
</style>
