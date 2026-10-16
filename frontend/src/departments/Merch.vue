<template>
	<DepartmentPage title="Merch" :show-title="false" flat inline-navigation>
		<WorkspaceLoadError v-if="loadError" :message="loadError" :loading="loading" @retry="load" />
		<WorkspaceLauncher
			v-else
			title="Merch"
			:items="visibleWorkspaces"
			:loading="loading"
			empty-text="No permitted Merch workspaces"
			:skeleton-count="merchLauncherItems().length"
		/>
	</DepartmentPage>
</template>

<script setup>
import { computed, onMounted, ref } from "vue"

import { getMerchCapabilities } from "../api/merch.js"
import DepartmentPage from "../components/DepartmentPage.vue"
import WorkspaceLauncher from "../components/common/WorkspaceLauncher.vue"
import WorkspaceLoadError from "../components/common/WorkspaceLoadError.vue"
import { merchLauncherItems, visibleMerchLauncherItems } from "./merch/merchViews.js"

const loading = ref(true)
const loadError = ref("")
const sections = ref({})
const visibleWorkspaces = computed(() => visibleMerchLauncherItems(sections.value))

async function load() {
	loading.value = true
	loadError.value = ""
	try {
		sections.value = (await getMerchCapabilities())?.sections || {}
	} catch (reason) {
		sections.value = {}
		loadError.value = reason?.message || "Unable to load the Merch workspace."
	} finally {
		loading.value = false
	}
}

onMounted(load)
</script>
