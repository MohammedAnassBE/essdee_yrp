<template>
	<DepartmentPage title="HR" :show-title="false" flat inline-navigation>
		<WorkspaceLoadError v-if="loadError" :message="loadError" :loading="loading" @retry="load" />
		<WorkspaceLauncher
			v-else
			title="HR"
			:items="visibleWorkspaces"
			:loading="loading"
			empty-text="No permitted HR workspaces"
			:skeleton-count="2"
		/>
	</DepartmentPage>
</template>

<script setup>
import { computed, onMounted, ref } from "vue"

import { getHrCapabilities } from "../api/hr.js"
import DepartmentPage from "../components/DepartmentPage.vue"
import WorkspaceLauncher from "../components/common/WorkspaceLauncher.vue"
import WorkspaceLoadError from "../components/common/WorkspaceLoadError.vue"

const loading = ref(true)
const loadError = ref("")
const sections = ref({})
const workspaces = [
	{
		key: "bill_tracking",
		label: "Bill Tracking",
		description: "Track vendor bills from receipt to invoice.",
		icon: "pi pi-inbox",
		to: "/hr/bill-tracking",
	},
	{
		key: "reports",
		label: "Reports",
		description: "Attendance strength.",
		icon: "pi pi-chart-bar",
		to: "/hr/reports",
	},
]
const visibleWorkspaces = computed(() => workspaces.filter((workspace) => sections.value[workspace.key]?.can_read))

async function load() {
	loading.value = true
	loadError.value = ""
	try {
		sections.value = (await getHrCapabilities())?.sections || {}
	} catch (reason) {
		sections.value = {}
		loadError.value = reason?.message || "Unable to load the HR workspace."
	} finally {
		loading.value = false
	}
}

onMounted(load)
</script>
