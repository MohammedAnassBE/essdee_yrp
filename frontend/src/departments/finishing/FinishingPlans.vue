<template>
	<DepartmentPage title="Finishing Plans" accent="#087c91" back-to="/finishing" back-label="Finishing" :show-title="false" flat full-width inline-navigation>
		<div class="finishing-list erp-workspace">
			<WorkspaceLoadError v-if="loadError" :message="loadError" :loading="loading" @retry="load" />
			<WorkspaceLoadError v-else-if="capability && !capability.can_read" title="Finishing Plans unavailable" message="You do not have permission to view Finishing Plans." :retryable="false" />
			<ListView
				v-else-if="capability?.can_read"
				doctype="SD YRP Finishing Plan"
				title="Finishing Plans"
				search-placeholder="Search Finishing Plans…"
				name-column-label="Finishing Plan"
				:column-labels="columnLabels"
				row-mark="FP"
				min-table-width="980px"
				status-field="fp_status"
				:status-options="statusOptions"
				:default-columns="defaultColumns"
				viewport-bounded
				clickable
				@row-click="openFinishingPlan"
			>
				<template #cell-fp_status="{ value }">
					<DocumentStatusBadge :label="value || 'Planned'" />
				</template>
			</ListView>
		</div>
	</DepartmentPage>
</template>

<script setup>
import { onMounted, ref } from "vue"
import { useRouter } from "vue-router"

import { getFinishingCapabilities } from "../../api/finishing.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import ListView from "../../components/common/ListView.vue"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import DocumentStatusBadge from "../../components/documents/DocumentStatusBadge.vue"
import { openListDocument } from "../../router/listDocumentNavigation.js"

const router = useRouter()
const capability = ref(null)
const loadError = ref("")
const loading = ref(true)
const defaultColumns = ["lot", "item", "work_order", "fp_status", "finishing_start_date", "finishing_end_date"]
const columnLabels = { fp_status: "Status", finishing_start_date: "Start Date", finishing_end_date: "End Date" }
const statusOptions = ["Planned", "Partially Received", "Ready to Pack", "Partially Dispatched", "Dispatched", "Fully Dispatched", "Ready for Audit", "Audit Completed", "Auto Closed", "OCR Completed", "P&L Submitted"]

function openFinishingPlan(row, snapshot) {
	return openListDocument(router, row, snapshot, { routeName: "finishing-plan", paramName: "finishingPlanId" })
}

async function load() {
	loading.value = true
	loadError.value = ""
	try {
		const sections = (await getFinishingCapabilities())?.sections || {}
		capability.value = sections.plans || { can_read: false }
	} catch (reason) {
		capability.value = null
		loadError.value = reason?.message || "Unable to load Finishing Plans."
	} finally {
		loading.value = false
	}
}

onMounted(load)
</script>

<style scoped>
.finishing-list { padding-top: 0; }
</style>
