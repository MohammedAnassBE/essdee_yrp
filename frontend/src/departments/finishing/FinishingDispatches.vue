<template>
	<DepartmentPage title="Finishing Plan Dispatches" :back-to="basePath" :back-label="backLabel" :show-title="false" flat full-width inline-navigation>
		<div class="finishing-list erp-workspace">
			<WorkspaceLoadError v-if="loadError" :message="loadError" :loading="loading" @retry="load" />
			<WorkspaceLoadError v-else-if="capability && !capability.can_read" title="Finishing Plan Dispatch unavailable" message="You do not have permission to view Finishing Plan Dispatches." :retryable="false" />
			<ListView
				v-else-if="capability?.can_read"
				doctype="SD YRP Finishing Plan Dispatch"
				title="Finishing Plan Dispatch"
				search-placeholder="Search Finishing Plan Dispatches…"
				name-column-label="Finishing Plan Dispatch"
				:column-labels="columnLabels"
				row-mark="FPD"
				min-table-width="760px"
				:default-columns="defaultColumns"
				viewport-bounded
				clickable
				@row-click="openDispatch"
			>
				<template #toolbar-actions>
					<Button v-if="capability.can_create" class="list-primary-action" label="Create Dispatch" icon="pi pi-plus" @click="router.push(`${basePath}/dispatches/new`)" />
				</template>
			</ListView>
		</div>
	</DepartmentPage>
</template>

<script setup>
import Button from "primevue/button"
import { onMounted, ref } from "vue"
import { useRouter } from "vue-router"

import { getFinishingCapabilities } from "../../api/finishing.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import ListView from "../../components/common/ListView.vue"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import { openListDocument } from "../../router/listDocumentNavigation.js"

/** `basePath` is the department that owns the dispatch pages. */
const props = defineProps({
	basePath: { type: String, default: "/finishing" },
	backLabel: { type: String, default: "Finishing" },
	viewRouteName: { type: String, default: "finishing-dispatch" },
})
const router = useRouter()
const capability = ref(null)
const loadError = ref("")
const loading = ref(true)
const defaultColumns = ["stock_entry", "fp_total_dispatched", "creation"]
const columnLabels = { stock_entry: "Stock Entry", fp_total_dispatched: "Total Dispatched", creation: "Created On" }

function openDispatch(row, snapshot) {
	return openListDocument(router, row, snapshot, { routeName: props.viewRouteName, paramName: "dispatchId" })
}

async function load() {
	loading.value = true
	loadError.value = ""
	try {
		capability.value = (await getFinishingCapabilities())?.sections?.dispatches || { can_read: false }
	} catch (reason) {
		capability.value = null
		loadError.value = reason?.message || "Unable to load Finishing Plan Dispatches."
	} finally {
		loading.value = false
	}
}

onMounted(load)
</script>

<style scoped>
.finishing-list { padding-top: 0; }
</style>
