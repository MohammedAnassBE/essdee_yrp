<template>
	<DepartmentPage :title="definition.label" accent="#0a7f5a" :back-to="basePath" :back-label="storeName" :show-title="false" flat full-width inline-navigation>
		<section class="fabric-store-section erp-workspace" :aria-label="definition.label">
			<div v-if="loading" class="fabric-store-section__loading">
				<Skeleton height="76px" />
				<Skeleton height="420px" />
			</div>
			<WorkspaceLoadError v-else-if="error" :message="error" :loading="loading" @retry="load" />
			<Message v-else-if="!capability" severity="warn" :closable="false">You do not have permission to view {{ definition.label }}.</Message>
			<component v-else :is="definition.component" v-bind="sectionProps" />
		</section>
	</DepartmentPage>
</template>

<script setup>
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import { computed, onMounted, ref, watch } from "vue"

import { getFabricStoreCapabilities } from "../api/fabricStore.js"
import DepartmentPage from "../components/DepartmentPage.vue"
import WorkspaceLoadError from "../components/common/WorkspaceLoadError.vue"
import FabricPurchaseOrders from "./fabric-store/FabricPurchaseOrders.vue"
import FabricReports from "./fabric-store/FabricReports.vue"
import FabricStockTransfers from "./fabric-store/FabricStockTransfers.vue"
import FabricWorkOrders from "./fabric-store/FabricWorkOrders.vue"

const props = defineProps({
	section: { type: String, required: true },
	storeName: { type: String, default: "Fabric Store" },
	basePath: { type: String, default: "/fabric-store" },
	workOrderViewRouteName: { type: String, default: "fabric-work-order" },
	workOrderNewRouteName: { type: String, default: "fabric-work-order-new" },
	purchaseOrderViewRouteName: { type: String, default: "fabric-purchase-order" },
	purchaseOrderNewRouteName: { type: String, default: "fabric-purchase-order-new" },
})
const definitions = {
	work_orders: { label: "Work Orders", component: FabricWorkOrders },
	purchase_orders: { label: "Purchase Orders", component: FabricPurchaseOrders },
	stock_transfers: { label: "Stock Transfers", component: FabricStockTransfers },
	reports: { label: "Reports", component: FabricReports },
}
const definition = computed(() => definitions[props.section] || definitions.work_orders)
const capability = ref(null)
const sectionProps = computed(() => ({
	capability: capability.value,
	...(props.section === "work_orders" ? {
		viewRouteName: props.workOrderViewRouteName,
		newRouteName: props.workOrderNewRouteName,
	} : {}),
	...(props.section === "purchase_orders" ? {
		viewRouteName: props.purchaseOrderViewRouteName,
		newRouteName: props.purchaseOrderNewRouteName,
	} : {}),
}))
const loading = ref(true)
const error = ref("")

async function load() {
	loading.value = true
	error.value = ""
	try {
		const payload = await getFabricStoreCapabilities() || {}
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
.fabric-store-section {
	width: 100%;
	max-width: 1800px;
	min-width: 0;
	margin: 0 auto;
	padding: 2px 0 var(--erp-space-5);
}

.fabric-store-section__loading {
	display: grid;
	gap: var(--erp-space-3);
	padding-top: 2px;
}

.fabric-store-section__loading :deep(.p-skeleton) {
	border-radius: var(--erp-panel-radius);
	background: color-mix(in srgb, var(--erp-surface-muted) 74%, white);
}
</style>
