<template>
	<DepartmentPage :title="storeName" accent="#0a7f5a" :show-title="false" flat>
		<WorkspaceLoadError v-if="error" :message="error" :loading="loading" @retry="load" />
		<WorkspaceLauncher
			v-else
			:title="storeName"
			:items="visibleWorkspaces"
			:loading="loading"
			:empty-text="`No permitted ${storeName} workspaces`"
		/>
	</DepartmentPage>
</template>

<script setup>
import { computed, onMounted, ref } from "vue"

import { getFabricStoreCapabilities } from "../api/fabricStore.js"
import DepartmentPage from "../components/DepartmentPage.vue"
import WorkspaceLauncher from "../components/common/WorkspaceLauncher.vue"
import WorkspaceLoadError from "../components/common/WorkspaceLoadError.vue"

const props = defineProps({
	storeName: { type: String, default: "Fabric Store" },
	basePath: { type: String, default: "/fabric-store" },
})
const loading = ref(true)
const error = ref("")
const sections = ref({})
const workspaces = computed(() => [
	{ key: "work_orders", label: "Work Orders", description: "Review production requirements, deliveries and receipts.", icon: "pi pi-briefcase", to: `${props.basePath}/work-orders` },
	{ key: "purchase_orders", label: "Purchase Orders", description: "Review purchase quantities and create Goods Received Notes.", icon: "pi pi-shopping-cart", to: `${props.basePath}/purchase-orders` },
	{ key: "stock_transfers", label: "Stock Transfers", description: "Create and review store stock movements and reconciliations.", icon: "pi pi-arrow-right-arrow-left", to: `${props.basePath}/stock-transfers` },
	{ key: "reports", label: "Reports", description: "Generate the current stock balance for store locations.", icon: "pi pi-chart-bar", to: `${props.basePath}/reports` },
])
const visibleWorkspaces = computed(() => workspaces.value.filter((workspace) => sections.value[workspace.key]))

async function load() {
	loading.value = true
	error.value = ""
	try {
		const payload = await getFabricStoreCapabilities() || {}
		sections.value = payload.sections || {}
	} catch (reason) {
		error.value = reason?.message || `Unable to load the ${props.storeName} workspace.`
	} finally {
		loading.value = false
	}
}

onMounted(load)
</script>
