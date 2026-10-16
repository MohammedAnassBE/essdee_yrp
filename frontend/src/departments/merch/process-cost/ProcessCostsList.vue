<template>
	<DepartmentPage title="Process Costs" back-to="/merch" back-label="Merch" :show-title="false" flat full-width inline-navigation>
		<WorkspaceLoadError v-if="error" :message="error" :loading="loading" @retry="load" />
		<ListPageSkeleton v-else-if="loading" />
		<Message v-else-if="!capabilities.can_read" severity="warn" :closable="false">You do not have permission to view Process Costs.</Message>
		<ListView v-else doctype="YRP Process Cost" title="Process Costs" eyebrow="Merch" name-column-label="Process Cost" search-placeholder="Search Process Costs…" status-field="workflow_state" :status-options="PROCESS_COST_STATES" :default-columns="PROCESS_COST_COLUMNS" :column-labels="{ process_name: 'Process', from_date: 'From Date', to_date: 'To Date' }" :allow-bulk-actions="false" clickable viewport-bounded @row-click="openRecord">
			<template #toolbar-actions><Button v-if="capabilities.can_create" label="New" icon="pi pi-plus" @click="router.push({ name: MERCH_ROUTES.processCostNew })" /></template>
			<template #cell-workflow_state="{ value }"><DocumentStatusBadge :label="value" /></template>
		</ListView>
	</DepartmentPage>
</template>

<script setup>
import Button from "primevue/button"
import Message from "primevue/message"
import { onMounted, ref } from "vue"
import { useRouter } from "vue-router"
import { getProcessCostListCapabilities } from "../../../api/merch.js"
import DepartmentPage from "../../../components/DepartmentPage.vue"
import ListView from "../../../components/common/ListView.vue"
import ListPageSkeleton from "../../../components/common/ListPageSkeleton.vue"
import WorkspaceLoadError from "../../../components/common/WorkspaceLoadError.vue"
import DocumentStatusBadge from "../../../components/documents/DocumentStatusBadge.vue"
import { openListDocument } from "../../../router/listDocumentNavigation.js"
import { MERCH_ROUTES } from "../merchViews.js"
import { PROCESS_COST_COLUMNS, PROCESS_COST_STATES } from "./processCostViews.js"

const router = useRouter()
const capabilities = ref({})
const error = ref("")
const loading = ref(true)
async function load() {
	loading.value = true
	error.value = ""
	try { capabilities.value = await getProcessCostListCapabilities() }
	catch (reason) { error.value = reason.message }
	finally { loading.value = false }
}
function openRecord(row, snapshot) {
	return openListDocument(router, row, snapshot, { routeName: MERCH_ROUTES.processCost, paramName: "processCostId" })
}
onMounted(load)
</script>
