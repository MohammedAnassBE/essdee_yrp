<template>
	<DepartmentPage title="Quality" :show-title="false" flat inline-navigation>
		<WorkspaceLoadError v-if="error" :message="error" :loading="loading" @retry="load" />
		<WorkspaceLauncher v-else title="Quality" :items="visibleWorkspaces" :loading="loading"
			empty-text="No permitted Quality workspaces" :skeleton-count="3" />
	</DepartmentPage>
</template>

<script setup>
import { computed, onMounted, ref } from "vue"
import { getQualityCapabilities } from "../api/quality.js"
import DepartmentPage from "../components/DepartmentPage.vue"
import WorkspaceLauncher from "../components/common/WorkspaceLauncher.vue"
import WorkspaceLoadError from "../components/common/WorkspaceLoadError.vue"

const loading = ref(true)
const error = ref("")
const sections = ref({})
const workspaces = [
	{ key: "inspections", label: "Essdee Quality Inspection", icon: "pi pi-verified", to: "/quality/inspections", description: "Inspect delivered colours and sizes." },
	{ key: "work_orders", label: "Work Orders", icon: "pi pi-briefcase", to: "/quality/work-orders", description: "Work Orders for quality checks." },
	{ key: "reports", label: "Reports", icon: "pi pi-chart-bar", to: "/quality/reports", description: "Quality inspection results." },
]
const visibleWorkspaces = computed(() => workspaces.filter(({ key }) => sections.value[key]?.can_read))

async function load() {
	loading.value = true
	error.value = ""
	try {
		sections.value = (await getQualityCapabilities())?.sections || {}
	} catch (reason) {
		error.value = reason?.message || "Unable to load Quality."
	} finally {
		loading.value = false
	}
}

onMounted(load)
</script>
