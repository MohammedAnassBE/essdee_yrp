<template>
	<DepartmentPage title="Accounts" :show-title="false" flat inline-navigation>
		<WorkspaceLoadError v-if="loadError" :message="loadError" :loading="loading" @retry="load" />
		<WorkspaceLauncher
			v-else
			title="Accounts"
			:items="visibleWorkspaces"
			:reports="reports"
			:loading="loading"
			empty-text="No permitted Accounts workspaces"
			:skeleton-count="2"
		/>
	</DepartmentPage>
</template>

<script setup>
import { computed, onMounted, ref } from "vue"

import { getAccountsCapabilities } from "../api/accounts.js"
import DepartmentPage from "../components/DepartmentPage.vue"
import WorkspaceLauncher from "../components/common/WorkspaceLauncher.vue"
import WorkspaceLoadError from "../components/common/WorkspaceLoadError.vue"
import { accountsLauncherItems, accountsReportTabs } from "./accounts/accountsViews.js"

const loading = ref(true)
const loadError = ref("")
const sections = ref({})
const reports = ref([])
const visibleWorkspaces = computed(() => accountsLauncherItems().filter((workspace) => sections.value[workspace.key]?.can_read))

async function load() {
	loading.value = true
	loadError.value = ""
	try {
		const capabilities = await getAccountsCapabilities()
		sections.value = capabilities?.sections || {}
		reports.value = accountsReportTabs(capabilities?.reports)
	} catch (reason) {
		sections.value = {}
		reports.value = []
		loadError.value = reason?.message || "Unable to load the Accounts workspace."
	} finally {
		loading.value = false
	}
}

onMounted(load)
</script>
