<template>
	<DepartmentPage :title="definition.label" :back-to="backTo" :back-label="backLabel" :show-title="false" flat full-width inline-navigation>
		<section class="cut-panel-store-section erp-workspace" :aria-label="definition.label">
			<div v-if="loading" class="cut-panel-store-section__loading">
				<ListPageSkeleton />
			</div>
			<WorkspaceLoadError v-else-if="error" :message="error" :loading="loading" @retry="load" />
			<Message v-else-if="!capability" severity="warn" :closable="false">You do not have permission to view {{ definition.label }}.</Message>
			<component v-else-if="definition.component" :is="definition.component" :capability="capability" v-bind="componentProps" />
			<div v-else class="erp-empty-state cut-panel-store-section__empty">
				<i :class="definition.icon" aria-hidden="true" />
				<strong>{{ definition.label }}</strong>
				<span>No records are available yet.</span>
			</div>
		</section>
	</DepartmentPage>
</template>

<script setup>
import Message from "primevue/message"
import { computed, onMounted, ref, watch } from "vue"

import { getCutPanelStoreCapabilities } from "../api/cutPanelStore.js"
import DepartmentPage from "../components/DepartmentPage.vue"
import ListPageSkeleton from "../components/common/ListPageSkeleton.vue"
import WorkspaceLoadError from "../components/common/WorkspaceLoadError.vue"
import CutPanelDocuments from "./cut-panel-store/CutPanelDocuments.vue"
import CutPanelMovements from "./cut-panel-store/CutPanelMovements.vue"
import CutBundleEdits from "./cut-panel-store/CutBundleEdits.vue"
import BoxStickerPrints from "./cut-panel-store/BoxStickerPrints.vue"
import FabricWorkOrders from "./fabric-store/FabricWorkOrders.vue"
import ExcelStickerPrints from "./cut-panel-store/ExcelStickerPrints.vue"
import CutPanelStoreReports from "./cut-panel-store/CutPanelStoreReports.vue"

const props = defineProps({
	section: { type: String, required: true },
	backTo: { type: String, default: "/cut-panel-store" },
	backLabel: { type: String, default: "Cut Panel Store" },
	newRouteName: { type: String, default: "" },
	viewRouteName: { type: String, default: "" },
})
const definitions = {
	delivery_challans: { label: "Delivery Challans", icon: "pi pi-truck", component: CutPanelDocuments },
	goods_received_notes: { label: "Goods Received Notes", icon: "pi pi-inbox", component: CutPanelDocuments },
	movements: { label: "Cut Panel Movement", icon: "pi pi-arrow-right-arrow-left", component: CutPanelMovements },
	work_orders: {
		label: "Work Orders",
		icon: "pi pi-briefcase",
		component: FabricWorkOrders,
		componentProps: { viewRouteName: "cut-panel-work-order", newRouteName: "cut-panel-work-order-new" },
	},
	cut_bundle_edits: { label: "Cut Bundle Edit", icon: "pi pi-pencil", component: CutBundleEdits },
	box_stickers: { label: "Box Sticker Print", icon: "pi pi-tags", component: BoxStickerPrints },
	excel_stickers: { label: "Excel Sticker Print", icon: "pi pi-file-excel", component: ExcelStickerPrints },
	reports: { label: "Reports", icon: "pi pi-chart-bar", component: CutPanelStoreReports },
}
const definition = computed(() => definitions[props.section] || definitions.movements)
const componentProps = computed(() => ({
	...(definition.value.componentProps || {}),
	...(props.viewRouteName ? { newRouteName: props.newRouteName, viewRouteName: props.viewRouteName } : {}),
}))
const capability = ref(null)
const loading = ref(true)
const error = ref("")

async function load() {
	loading.value = true
	error.value = ""
	try {
		const payload = await getCutPanelStoreCapabilities() || {}
		capability.value = payload.sections?.[props.section] || null
	} catch (reason) {
		error.value = reason?.message || `Unable to load ${definition.value.label}.`
	} finally {
		loading.value = false
	}
}

onMounted(load)
watch(() => props.section, load)
</script>

<style scoped>
.cut-panel-store-section {
	width: 100%;
	min-width: 0;
	padding: 2px 0 var(--erp-space-5);
}

.cut-panel-store-section__loading {
	display: grid;
	gap: var(--erp-space-3);
	padding-top: 2px;
}

.cut-panel-store-section__empty {
	min-height: 360px;
}
</style>
