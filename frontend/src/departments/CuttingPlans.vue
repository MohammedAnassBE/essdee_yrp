<template>
	<DepartmentPage title="Cutting Plans" accent="#0b8f65" back-to="/cutting" back-label="Cutting" :show-title="false" flat>
		<div class="cutting-list erp-workspace">
			<ListView
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
				clickable
				@row-click="openCuttingPlan"
			>
				<template #cell-cp_status="{ value }">
					<Tag :value="value || 'Draft'" :severity="statusSeverity(value)" rounded />
				</template>
			</ListView>
		</div>
	</DepartmentPage>
</template>

<script setup>
import Tag from "primevue/tag"
import { useRouter } from "vue-router"

import DepartmentPage from "../components/DepartmentPage.vue"
import ListView from "../components/common/ListView.vue"

const router = useRouter()
const defaultColumns = ["lot", "item", "cp_status", "no_of_colours", "no_of_colours_completed"]
const columnLabels = { cp_status: "Status", no_of_colours: "Colours", no_of_colours_completed: "Completed Colours" }
const linkFilters = { item: { has_variants: 1 } }
const statusOptions = ["Draft", "Planned", "Fabric Partially Received", "Ready to Cut", "Cutting In Progress", "Partially Completed", "Completed", "Cut Panel Dispatch Pending"]

function openCuttingPlan(row) {
	if (row?.name) router.push({ name: "cutting-plan", params: { cuttingPlanId: row.name } })
}

function statusSeverity(status) {
	if (status === "Completed") return "success"
	if (["Fabric Partially Received", "Partially Completed"].includes(status)) return "warn"
	if (status === "Cut Panel Dispatch Pending") return "danger"
	if (["Ready to Cut", "Cutting In Progress"].includes(status)) return "info"
	return "secondary"
}
</script>

<style scoped>
.cutting-list { padding-top: 0; }
</style>
