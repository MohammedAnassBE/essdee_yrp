<template>
	<DepartmentPage title="PD" :show-title="false" flat inline-navigation>
		<WorkspaceLoadError v-if="loadError" :message="loadError" :loading="loading" @retry="load" />
		<WorkspaceLauncher
			v-else
			title="PD"
			:items="visibleWorkspaces"
			:loading="loading"
			empty-text="No permitted PD workspaces"
			:skeleton-count="3"
		/>
	</DepartmentPage>
</template>

<script setup>
import { computed, onMounted, ref } from "vue"

import { getPdCapabilities } from "../api/pd.js"
import DepartmentPage from "../components/DepartmentPage.vue"
import WorkspaceLauncher from "../components/common/WorkspaceLauncher.vue"
import WorkspaceLoadError from "../components/common/WorkspaceLoadError.vue"
import { pdLauncherItems } from "./pd/pdViews.js"

const loading = ref(true)
const loadError = ref("")
const sections = ref({})
const workspaces = pdLauncherItems()
const visibleWorkspaces = computed(() => workspaces.filter((workspace) => sections.value[workspace.key]?.can_read))

async function load() {
	loading.value = true
	loadError.value = ""
	try {
		sections.value = (await getPdCapabilities())?.sections || {}
	} catch (reason) {
		sections.value = {}
		loadError.value = reason?.message || "Unable to load the PD workspace."
	} finally {
		loading.value = false
	}
}

onMounted(load)
</script>
