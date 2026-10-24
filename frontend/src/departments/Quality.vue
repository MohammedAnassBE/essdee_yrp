<template>
	<DepartmentPage title="Quality" :show-title="false" flat inline-navigation>
		<WorkspaceLoadError v-if="error" :message="error" :loading="loading" @retry="load" />
		<WorkspaceLauncher v-else title="Quality" :items="visibleWorkspaces" :loading="loading"
			empty-text="No permitted Quality workspaces" :skeleton-count="workspaces.length" />
	</DepartmentPage>
</template>

<script setup>
import { computed, onMounted, ref } from "vue"
import { getQualityCapabilities } from "../api/quality.js"
import DepartmentPage from "../components/DepartmentPage.vue"
import WorkspaceLauncher from "../components/common/WorkspaceLauncher.vue"
import WorkspaceLoadError from "../components/common/WorkspaceLoadError.vue"
import { qualityLauncherItems } from "./quality/qualityWorkspaces.js"

const loading = ref(true)
const error = ref("")
const sections = ref({})
const workspaces = qualityLauncherItems()
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
