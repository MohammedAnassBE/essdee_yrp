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

const loading = ref(true)
const loadError = ref("")
const sections = ref({})
const workspaces = [
	{
		key: "products",
		label: "Products",
		description: "Style master, silhouettes, trims, colours, graphics and tech pack release.",
		icon: "pi pi-palette",
		to: "/pd/products",
	},
	{
		key: "product_releases",
		label: "Product Releases",
		description: "Released tech pack snapshots, read-only with print.",
		icon: "pi pi-send",
		to: "/pd/product-releases",
	},
	{
		key: "lotwise_item_profits",
		label: "Lotwise Item Profit",
		description: "Costing sheets: size rates, cloth, production cost, discounts and profit.",
		icon: "pi pi-calculator",
		to: "/pd/lotwise-item-profits",
	},
]
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
