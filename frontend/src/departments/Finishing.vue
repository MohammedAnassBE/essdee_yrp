<template>
	<DepartmentPage title="Finishing" :show-title="false" flat inline-navigation>
		<WorkspaceLoadError v-if="loadError" :message="loadError" :loading="loading" @retry="load" />
		<WorkspaceLauncher v-else title="Finishing" :items="visibleWorkspaces" :reports="reports" :loading="loading" empty-text="No permitted Finishing workspaces" :skeleton-count="6" />
	</DepartmentPage>
</template>

<script setup>
import { computed, onMounted, ref } from "vue"

import { getFinishingCapabilities } from "../api/finishing.js"
import { finishingReportTabs } from "./departmentReports.js"
import { documentWorkspaces } from "./fabric-store/storeWorkspaces.js"
import DepartmentPage from "../components/DepartmentPage.vue"
import WorkspaceLauncher from "../components/common/WorkspaceLauncher.vue"
import WorkspaceLoadError from "../components/common/WorkspaceLoadError.vue"

const loading = ref(true)
const loadError = ref("")
const sections = ref({})
const reports = computed(() => finishingReportTabs(sections.value.reports?.reports))
const workspaces = [
	{ key: "plans", label: "Finishing Plan", description: "Inward, packing, dispatch, OCR and audit for each lot.", icon: "pi pi-box", to: "/finishing/plans" },
	{ key: "reports", label: "Reports", description: "Packing, dispatch, ironing, rejection, rework and stock reports.", icon: "pi pi-chart-bar", to: "/finishing/reports" },
	{ key: "rework_details", label: "Rework Details", description: "Clear rework pieces into Accepted or Rejected stock per GRN.", icon: "pi pi-replay", to: "/finishing/rework-details" },
	{ key: "rework_groups", label: "Rework Grouped Details", description: "Rework rows grouped by item and lot with size-wise entry.", icon: "pi pi-objects-column", to: "/finishing/rework-groups" },
	{ key: "dispatches", label: "Finishing Plan Dispatch", description: "Dispatch packed boxes from several Finishing Plans together.", icon: "pi pi-truck", to: "/finishing/dispatches" },
	{ key: "work_orders", label: "Work Orders", description: "Work Orders: make DCs and receive GRNs.", icon: "pi pi-briefcase", to: "/finishing/work-orders" },
	...documentWorkspaces("/finishing"),
]
const visibleWorkspaces = computed(() => workspaces.filter((workspace) => sections.value[workspace.key]?.can_read))

async function load() {
	loading.value = true
	loadError.value = ""
	try {
		sections.value = (await getFinishingCapabilities())?.sections || {}
	} catch (reason) {
		sections.value = {}
		loadError.value = reason?.message || "Unable to load the Finishing workspace."
	} finally {
		loading.value = false
	}
}

onMounted(load)
</script>
