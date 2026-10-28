<template>
	<div class="sales-launcher">
		<WorkspaceLoadError v-if="error" :message="error" :loading="loading" @retry="load" />
		<WorkspaceLauncher
			v-else
			title="Sales"
			:items="visibleItems"
			:reports="salesReportTabs(capabilities)"
			:loading="loading"
			:skeleton-count="2"
			empty-text="No permitted Sales workspaces"
		/>
	</div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue"

import { getSalesCapabilities } from "../../api/sales.js"
import WorkspaceLauncher from "../../components/common/WorkspaceLauncher.vue"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import { salesReportTabs } from "../departmentReports.js"

const loading = ref(true)
const error = ref("")
const capabilities = ref({ sections: {} })
const items = [
	{
		key: "production_orders",
		label: "Production Orders",
		description: "Plan quantities, prices, delivery dates and approvals in one compact workflow.",
		icon: "pi pi-file-edit",
		to: "/sales/production-orders",
	},
	{
		key: "reports",
		label: "Reports",
		description: "Review Production Orders by delivery period, status, category and size.",
		icon: "pi pi-chart-bar",
		to: "/sales/reports",
	},
]

const visibleItems = computed(() => items.filter((item) => capabilities.value.sections?.[item.key]?.can_read))

async function load() {
	loading.value = true
	error.value = ""
	try {
		capabilities.value = await getSalesCapabilities() || { sections: {} }
	} catch (reason) {
		error.value = reason?.message || "Unable to load the Sales workspace."
	} finally {
		loading.value = false
	}
}

onMounted(load)
</script>
