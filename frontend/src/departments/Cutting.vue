<template>
	<DepartmentPage title="Cutting" :show-title="false" flat inline-navigation>
		<WorkspaceLoadError v-if="loadError" :message="loadError" :loading="loadingPermissions" @retry="load" />
		<WorkspaceLauncher v-else title="Cutting" :items="visibleWorkspaces" :reports="reports" :loading="loadingPermissions" empty-text="No permitted Cutting workspaces" :skeleton-count="5" />
	</DepartmentPage>
</template>

<script setup>
import { computed, onMounted, ref } from "vue"

import { getCuttingReportPermissions } from "../api/cuttingReports.js"
import { getCuttingCapabilities } from "../api/cuttingWorkspaces.js"
import DepartmentPage from "../components/DepartmentPage.vue"
import WorkspaceLauncher from "../components/common/WorkspaceLauncher.vue"
import WorkspaceLoadError from "../components/common/WorkspaceLoadError.vue"
import { cuttingReportTabs } from "./departmentReports.js"

const loadingPermissions = ref(true)
const capabilities = ref({})
const loadError = ref("")
const reports = ref([])
const workspaces = [
	{ key: "cutting-plans", label: "Cutting Plans", description: "Plans, markers, lay sheets and production movements.", icon: "pi pi-th-large", to: "/cutting/plans" },
	{ key: "cutting-orders", label: "Cutting Orders", description: "Plan and complete cutting orders with their production details.", icon: "pi pi-file-edit", to: "/cutting/orders" },
	{ key: "bulk-lay-sheets", label: "Bulk LaySheets", description: "Manage multi-lot lay sheets, bundles and dispatch workflows.", icon: "pi pi-clone", to: "/cutting/bulk-lay-sheets" },
	{ key: "lay-sheet-planner", label: "LaySheet Planner", description: "Optimize size quantities into efficient marker and lay plans.", icon: "pi pi-sitemap", to: "/cutting/lay-sheet-planner" },
	{ key: "stock-transfers", label: "Stock Transfers", description: "Stock Update, Stock Reconciliation, Stock Entry and Lot Transfer.", icon: "pi pi-arrow-right-arrow-left", to: "/cutting/stock-transfers" },
	{ key: "reports", label: "Reports", description: "Production, cut sheet, cutting detail and stock reports.", icon: "pi pi-chart-bar", to: "/cutting/reports" },
]
const visibleWorkspaces = computed(() => workspaces.filter((workspace) => capabilities.value[workspace.key]?.can_read))

async function load() {
	loadingPermissions.value = true
	loadError.value = ""
	try {
		capabilities.value = await getCuttingCapabilities() || {}
		reports.value = capabilities.value.reports?.can_read ? cuttingReportTabs(await getCuttingReportPermissions() || {}) : []
	} catch (reason) {
		capabilities.value = {}
		reports.value = []
		loadError.value = reason?.message || "Unable to load the Cutting workspace."
	} finally {
		loadingPermissions.value = false
	}

}

onMounted(load)

</script>
