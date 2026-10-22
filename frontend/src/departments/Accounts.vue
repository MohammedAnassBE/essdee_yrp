<template>
	<DepartmentPage title="Accounts" :show-title="false" flat inline-navigation>
		<WorkspaceLoadError v-if="loadError" :message="loadError" :loading="loading" @retry="load" />
		<WorkspaceLauncher
			v-else
			title="Accounts"
			:items="visibleWorkspaces"
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

const loading = ref(true)
const loadError = ref("")
const sections = ref({})
const workspaces = [
	{ key: "debits", label: "Debits", description: "Work Order debits and approval status.", icon: "pi pi-wallet", to: "/accounts/debits" },
	{
		key: "purchase_invoices",
		label: "Purchase Invoice",
		description: "Supplier bills against GRNs, with approval and ERP sync.",
		icon: "pi pi-file-edit",
		to: "/accounts/purchase-invoices",
	},
	{
		key: "bill_tracking",
		label: "Vendor Bill Tracking",
		description: "Track vendor bills, assignments and receipt status.",
		icon: "pi pi-receipt",
		to: "/accounts/bill-tracking",
	},
	{
		key: "reports",
		label: "Reports",
		description: "Stock, cutting, sewing, dispatch and ironing reports.",
		icon: "pi pi-chart-bar",
		to: "/accounts/reports",
	},
]
const visibleWorkspaces = computed(() => workspaces.filter((workspace) => sections.value[workspace.key]?.can_read))

async function load() {
	loading.value = true
	loadError.value = ""
	try {
		sections.value = (await getAccountsCapabilities())?.sections || {}
	} catch (reason) {
		sections.value = {}
		loadError.value = reason?.message || "Unable to load the Accounts workspace."
	} finally {
		loading.value = false
	}
}

onMounted(load)
</script>
