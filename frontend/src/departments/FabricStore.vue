<template>
	<DepartmentPage title="Fabric Store" accent="#0a7f5a" :show-title="false" flat>
		<Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
		<WorkspaceLauncher
			v-else
			title="Fabric Store"
			:items="visibleWorkspaces"
			:loading="loading"
			empty-text="No permitted Fabric Store workspaces"
		/>
	</DepartmentPage>
</template>

<script setup>
import Message from "primevue/message"
import { computed, onMounted, ref } from "vue"

import { getFabricStoreCapabilities } from "../api/fabricStore.js"
import DepartmentPage from "../components/DepartmentPage.vue"
import WorkspaceLauncher from "../components/common/WorkspaceLauncher.vue"

const loading = ref(true)
const error = ref("")
const sections = ref({})
const workspaces = [
	{ key: "work_orders", label: "Work Orders", description: "Review production requirements, deliveries and receipts.", icon: "pi pi-briefcase", to: "/fabric-store/work-orders" },
	{ key: "purchase_orders", label: "Purchase Orders", description: "Review purchase quantities and create Goods Received Notes.", icon: "pi pi-shopping-cart", to: "/fabric-store/purchase-orders" },
	{ key: "stock_transfers", label: "Stock Transfers", description: "Create and review store stock movements and reconciliations.", icon: "pi pi-arrow-right-arrow-left", to: "/fabric-store/stock-transfers" },
	{ key: "reports", label: "Reports", description: "Generate the current stock balance for store locations.", icon: "pi pi-chart-bar", to: "/fabric-store/reports" },
]
const visibleWorkspaces = computed(() => workspaces.filter((workspace) => sections.value[workspace.key]))

onMounted(async () => {
	try {
		const payload = await getFabricStoreCapabilities() || {}
		sections.value = payload.sections || {}
	} catch (reason) {
		error.value = reason?.message || "Unable to load the Fabric Store workspace."
	} finally {
		loading.value = false
	}
})
</script>
