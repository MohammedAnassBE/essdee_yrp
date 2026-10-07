<template>
	<DepartmentPage title="LaySheet Planner" accent="#059669" back-to="/cutting" back-label="Cutting" :show-title="false" flat full-width>
		<div class="cutting-list erp-workspace">
			<ListView
				v-if="capability"
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
					<Button v-if="capability.can_create" class="list-primary-action" label="Create LaySheet Plan" icon="pi pi-plus" @click="createPlan" />
				</template>
				<template #cell-optimization_status="{ value }">
					<Tag :value="value || 'Not Started'" :severity="statusSeverity(value)" rounded />
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
const defaultColumns = ["description", "lot", "item", "optimization_status", "selected_strategy", "modified"]
const statusOptions = ["Not Started", "Queued", "Running", "Completed", "Failed"]

function openPlan(row) {
	if (row?.name) router.push(`/cutting/lay-sheet-planner/${encodeURIComponent(row.name)}`)
}

function createPlan() {
	router.push("/cutting/lay-sheet-planner/new")
}

function statusSeverity(status) {
	if (status === "Completed") return "success"
	if (status === "Failed") return "danger"
	if (["Queued", "Running"].includes(status)) return "info"
	return "secondary"
}

onMounted(async () => {
	const capabilities = await getCuttingCapabilities()
	capability.value = capabilities?.["lay-sheet-planner"] || { can_read: false, can_create: false }
})
</script>

<style scoped>
.cutting-list { padding-top: 0; }
</style>
