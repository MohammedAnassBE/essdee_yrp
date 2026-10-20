<template>
	<DepartmentPage title="Cut Panel Store" :show-title="false" flat inline-navigation>
		<WorkspaceLoadError v-if="error" :message="error" :loading="loading" @retry="load" />
		<WorkspaceLauncher
			v-else
			title="Cut Panel Store"
			:items="visibleWorkspaces"
			:loading="loading"
			empty-text="No permitted Cut Panel Store workspaces"
			:skeleton-count="6"
		/>
	</DepartmentPage>
</template>

<script setup>
import { computed, onMounted, ref } from "vue"

import { getCutPanelStoreCapabilities } from "../api/cutPanelStore.js"
import DepartmentPage from "../components/DepartmentPage.vue"
import WorkspaceLauncher from "../components/common/WorkspaceLauncher.vue"
import WorkspaceLoadError from "../components/common/WorkspaceLoadError.vue"

const loading = ref(true)
const error = ref("")
const sections = ref({})
const workspaces = [
	{ key: "delivery_challans", label: "Delivery Challans", description: "Review deliveries linked to Cut Panel Movements.", icon: "pi pi-truck", to: "/cut-panel-store/delivery-challans" },
	{ key: "goods_received_notes", label: "Goods Received Notes", description: "Review receipts linked to Cut Panel Movements.", icon: "pi pi-inbox", to: "/cut-panel-store/goods-received-notes" },
	{ key: "movements", label: "Cut Panel Movement", description: "Move bundles and create linked stock documents in one workspace.", icon: "pi pi-arrow-right-arrow-left", to: "/cut-panel-store/movements" },
	{ key: "work_orders", label: "Work Orders", description: "Review production requirements, deliveries and receipts.", icon: "pi pi-briefcase", to: "/cut-panel-store/work-orders" },
	{ key: "cut_bundle_edits", label: "Cut Bundle Edit", description: "Correct bundle composition using authoritative stock data.", icon: "pi pi-pencil", to: "/cut-panel-store/cut-bundle-edits" },
	{ key: "box_stickers", label: "Box Sticker Print", description: "Prepare, preview and print size-based box labels.", icon: "pi pi-tags", to: "/cut-panel-store/box-sticker-prints" },
	{ key: "excel_stickers", label: "Excel Sticker Print", description: "Upload sticker rows, preview labels and print through QZ.", icon: "pi pi-file-excel", to: "/cut-panel-store/excel-sticker-prints" },
	{ key: "reports", label: "Reports", description: "Review stock and cut bundle balances.", icon: "pi pi-chart-bar", to: "/cut-panel-store/reports" },
]
const visibleWorkspaces = computed(() => workspaces.filter((workspace) => sections.value[workspace.key]?.can_read))

async function load() {
	loading.value = true
	error.value = ""
	try {
		const payload = await getCutPanelStoreCapabilities() || {}
		sections.value = payload.sections || {}
	} catch (reason) {
		error.value = reason?.message || "Unable to load the Cut Panel Store workspace."
	} finally {
		loading.value = false
	}
}

onMounted(load)
</script>
