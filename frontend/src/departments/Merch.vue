<template>
	<DepartmentPage :title="title" :show-title="false" flat inline-navigation>
		<WorkspaceLoadError v-if="loadError" :message="loadError" :loading="loading" @retry="load" />
		<WorkspaceLauncher
			v-else
			:title="title"
			:items="visibleWorkspaces"
			:loading="loading"
			:empty-text="`No permitted ${title} workspaces`"
			:skeleton-count="items.length"
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

const props = defineProps({
	title: { type: String, default: "Merch" },
	items: { type: Array, default: merchLauncherItems },
	loadCapabilities: { type: Function, default: getMerchCapabilities },
})
const loading = ref(true)
const loadError = ref("")
const sections = ref({})
const visibleWorkspaces = computed(() => visibleMerchLauncherItems(sections.value, props.items))

async function load() {
	loading.value = true
	loadError.value = ""
	try {
		sections.value = (await props.loadCapabilities())?.sections || {}
	} catch (reason) {
		sections.value = {}
		loadError.value = reason?.message || `Unable to load the ${props.title} workspace.`
	} finally {
		loading.value = false
	}
}

onMounted(load)
</script>
