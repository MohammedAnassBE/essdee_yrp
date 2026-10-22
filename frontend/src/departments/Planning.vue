<template>
	<DepartmentPage title="Planning" :show-title="false" flat inline-navigation>
		<WorkspaceLoadError v-if="loadError" :message="loadError" :loading="loading" @retry="load" />
		<WorkspaceLauncher
			v-else
			title="Planning"
			:items="visibleWorkspaces"
			:loading="loading"
			empty-text="No permitted Planning workspaces"
			:skeleton-count="8"
		/>
	</DepartmentPage>
</template>

<script setup>
import { computed, onMounted, ref } from "vue"

import { getPlanningCapabilities } from "../api/planning.js"
import DepartmentPage from "../components/DepartmentPage.vue"
import WorkspaceLauncher from "../components/common/WorkspaceLauncher.vue"
import WorkspaceLoadError from "../components/common/WorkspaceLoadError.vue"
import { visiblePlanningWorkspaces } from "./planning/planningViews.js"

const loading = ref(true)
const loadError = ref("")
const sections = ref({})
const visibleWorkspaces = computed(() => visiblePlanningWorkspaces(sections.value))

async function load() {
	loading.value = true
	loadError.value = ""
	try {
		sections.value = (await getPlanningCapabilities())?.sections || {}
	} catch (reason) {
		sections.value = {}
		loadError.value = reason?.message || "Unable to load the Planning workspace."
	} finally {
		loading.value = false
	}
}

onMounted(load)
</script>
