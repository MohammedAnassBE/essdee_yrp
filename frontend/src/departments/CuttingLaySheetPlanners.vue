<template>
	<DepartmentPage title="LaySheet Planner" :back-to="backTo" :back-label="backLabel" :show-title="false" flat full-width>
		<div class="cutting-list erp-workspace">
			<WorkspaceLoadError v-if="loadError" :message="loadError" :loading="loadingCapability" @retry="load" />
			<WorkspaceLoadError v-else-if="capability && !capability.can_read" title="LaySheet Planner unavailable" message="You do not have permission to view LaySheet Planner documents." :retryable="false" />
			<ListView
				v-else
				:can-read="Boolean(capability?.can_read)"
				doctype="SD YRP Cutting Laysheet Planner"
				title="LaySheet Planner"
				search-placeholder="Search LaySheet Plans…"
				name-column-label="LaySheet Plan"
				row-mark="LP"
				min-table-width="1080px"
				status-field="optimization_status"
				:status-options="statusOptions"
				:default-columns="defaultColumns"
				viewport-bounded
				clickable
				@row-click="openPlan"
			>
				<template #toolbar-actions>
					<Button v-if="capability?.can_create" class="list-primary-action" label="Create LaySheet Plan" icon="pi pi-plus" @click="createPlan" />
				</template>
				<template #cell-optimization_status="{ value }">
					<DocumentStatusBadge :label="value || 'Not Started'" />
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

const props = defineProps({
	backTo: { type: String, default: "/cutting" },
	backLabel: { type: String, default: "Cutting" },
	viewRouteName: { type: String, default: "cutting-lay-sheet-planner" },
	newRouteName: { type: String, default: "cutting-lay-sheet-planner-new" },
})

const router = useRouter()
const capability = ref(null)
const loadError = ref("")
const loadingCapability = ref(true)
const defaultColumns = ["description", "lot", "item", "optimization_status", "selected_strategy", "modified"]
const statusOptions = ["Not Started", "Queued", "Running", "Completed", "Failed"]

function openPlan(row) {
	if (row?.name) router.push({ name: props.viewRouteName, params: { plannerId: row.name } })
}

function createPlan() {
	router.push({ name: props.newRouteName })
}

async function load() {
	loadingCapability.value = true
	loadError.value = ""
	try {
		const capabilities = await getCuttingCapabilities()
		capability.value = capabilities?.["lay-sheet-planner"] || { can_read: false, can_create: false }
	} catch (reason) {
		capability.value = null
		loadError.value = reason?.message || "Unable to load LaySheet Planner."
	} finally {
		loadingCapability.value = false
	}
}

onMounted(load)
</script>

<style scoped>
.cutting-list { padding-top: 0; }
</style>
