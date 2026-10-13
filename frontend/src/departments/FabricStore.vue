<template>
	<DepartmentPage :title="storeName" :show-title="false" flat inline-navigation>
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

import { getCutPanelStoreCapabilities } from "../api/cutPanelStore.js"
import { getFabricStoreCapabilities } from "../api/fabricStore.js"
import DepartmentPage from "../components/DepartmentPage.vue"
import WorkspaceLauncher from "../components/common/WorkspaceLauncher.vue"
import WorkspaceLoadError from "../components/common/WorkspaceLoadError.vue"

const props = defineProps({
	storeName: { type: String, default: "Fabric Store" },
	basePath: { type: String, default: "/fabric-store" },
	workspaceKeys: {
		type: Array,
		default: () => ["work_orders", "purchase_orders", "stock_transfers", "reports"],
	},
	reportKeys: { type: Array, default: () => ["stock_balance"] },
})
const loading = ref(true)
const error = ref("")
const sections = ref({})
const workspaces = computed(() => [
	{ key: "work_orders", label: "Work Orders", description: "Review production requirements, deliveries and receipts.", icon: "pi pi-briefcase", to: `${props.basePath}/work-orders` },
	{ key: "purchase_orders", label: "Purchase Orders", description: "Review purchase quantities and create Goods Received Notes.", icon: "pi pi-shopping-cart", to: `${props.basePath}/purchase-orders` },
	{ key: "stock_transfers", label: "Stock Transfers", description: "Create and review store stock movements and reconciliations.", icon: "pi pi-arrow-right-arrow-left", to: `${props.basePath}/stock-transfers` },
	{ key: "box_stickers", label: "Box Sticker Print", description: "Prepare, preview and print size-based box labels.", icon: "pi pi-tags", to: `${props.basePath}/box-sticker-prints` },
	{
		key: "reports",
		label: "Reports",
		description: props.reportKeys.includes("purchase_order_itemwise")
			? "Review stock, Purchase Order items and Lot cut quantities."
			: "Generate the current stock balance for store locations.",
		icon: "pi pi-chart-bar",
		to: `${props.basePath}/reports`,
	},
])
const visibleWorkspaces = computed(() => workspaces.value.filter((workspace) => (
	props.workspaceKeys.includes(workspace.key)
		&& sections.value[workspace.key]
		&& (workspace.key !== "reports" || props.reportKeys.some((key) => sections.value.reports?.reports?.[key]?.can_read))
)))

async function load() {
	loading.value = true
	error.value = ""
	try {
		const includesBoxStickers = props.workspaceKeys.includes("box_stickers")
		const [payload, cutPanelPayload] = await Promise.all([
			getFabricStoreCapabilities(),
			includesBoxStickers ? getCutPanelStoreCapabilities() : null,
		])
		sections.value = { ...payload?.sections }
		if (cutPanelPayload?.sections?.box_stickers) sections.value.box_stickers = cutPanelPayload.sections.box_stickers
	} catch (reason) {
		error.value = reason?.message || `Unable to load the ${props.storeName} workspace.`
	} finally {
		loading.value = false
	}
}

onMounted(load)
</script>
