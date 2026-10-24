<template>
	<DepartmentPage title="Cutting Plans" :back-to="backTo" :back-label="backLabel" :show-title="false" flat full-width inline-navigation>
		<div class="cutting-list erp-workspace">
			<WorkspaceLoadError v-if="loadError" :message="loadError" :loading="loadingCapability" @retry="load" />
			<WorkspaceLoadError v-else-if="capability && !capability.can_read" title="Cutting Plans unavailable" message="You do not have permission to view Cutting Plans." :retryable="false" />
			<ListView
				v-else
				:can-read="Boolean(capability?.can_read)"
				doctype="SD YRP Cutting Plan"
				title="Cutting Plans"
				search-placeholder="Search Cutting Plans…"
				name-column-label="Cutting Plan"
				:column-labels="columnLabels"
				:link-filters="linkFilters"
				row-mark="CP"
				min-table-width="980px"
				status-field="cp_status"
				:status-options="statusOptions"
				:default-columns="defaultColumns"
				viewport-bounded
				clickable
				@row-click="openCuttingPlan"
			>
				<template #toolbar-actions>
					<Button v-if="capability?.can_create" class="list-primary-action" label="Create Cutting Plan" icon="pi pi-plus" @click="createCuttingPlan" />
				</template>
				<template #cell-cp_status="{ value }">
					<DocumentStatusBadge :label="value || 'Draft'" />
				</template>
			</ListView>
		</div>
	</DepartmentPage>
</template>

<script setup>
import Button from "primevue/button"
import { useRouter } from "vue-router"
import { onMounted, ref } from "vue"

import { getCuttingCapabilities } from "../api/cuttingWorkspaces.js"
import DepartmentPage from "../components/DepartmentPage.vue"
import ListView from "../components/common/ListView.vue"
import WorkspaceLoadError from "../components/common/WorkspaceLoadError.vue"
import DocumentStatusBadge from "../components/documents/DocumentStatusBadge.vue"
import { openListDocument } from "../router/listDocumentNavigation.js"

const props = defineProps({
	backTo: { type: String, default: "/cutting" },
	backLabel: { type: String, default: "Cutting" },
	viewRouteName: { type: String, default: "cutting-plan" },
	newRouteName: { type: String, default: "cutting-plan-new" },
})

const router = useRouter()
const capability = ref(null)
const loadError = ref("")
const loadingCapability = ref(true)
const defaultColumns = ["lot", "item", "cp_status", "no_of_colours", "no_of_colours_completed"]
const columnLabels = { cp_status: "Status", no_of_colours: "Colours", no_of_colours_completed: "Completed Colours" }
const linkFilters = { item: { has_variants: 1 } }
const statusOptions = ["Draft", "Planned", "Fabric Partially Received", "Ready to Cut", "Cutting In Progress", "Partially Completed", "Completed", "Cut Panel Dispatch Pending", "Cancelled"]

function openCuttingPlan(row, snapshot) {
	return openListDocument(router, row, snapshot, { routeName: props.viewRouteName, paramName: "cuttingPlanId" })
}

function createCuttingPlan() {
	router.push({ name: props.newRouteName })
}

async function load() {
	loadingCapability.value = true
	loadError.value = ""
	try {
		const capabilities = await getCuttingCapabilities()
		capability.value = capabilities?.["cutting-plans"] || { can_read: false, can_create: false }
	} catch (reason) {
		capability.value = null
		loadError.value = reason?.message || "Unable to load Cutting Plans."
	} finally {
		loadingCapability.value = false
	}
}

onMounted(load)

</script>

<style scoped>
.cutting-list { padding-top: 0; }
</style>
