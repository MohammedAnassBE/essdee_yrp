<template>
	<DepartmentPage :title="definition.label" :back-to="basePath" :back-label="storeName" :show-title="false" flat full-width inline-navigation>
		<section class="fabric-store-section erp-workspace" :aria-label="definition.label">
			<div v-if="loading" class="fabric-store-section__loading">
				<ListPageSkeleton />
			</div>
			<WorkspaceLoadError v-else-if="error" :message="error" :loading="loading" @retry="load" />
			<Message v-else-if="!capability" severity="warn" :closable="false">You do not have permission to view {{ definition.label }}.</Message>
			<component v-else :is="definition.component" v-bind="sectionProps" />
		</section>
	</DepartmentPage>
</template>

<script setup>
import Message from "primevue/message"
import { computed, onMounted, ref, watch } from "vue"

import { getFabricStoreCapabilities } from "../api/fabricStore.js"
import { getFinishingCapabilities } from "../api/finishing.js"
import { getSewingWorkOrderProcesses } from "../api/sewing.js"
import { getQualityCapabilities } from "../api/quality.js"
import DepartmentPage from "../components/DepartmentPage.vue"
import ListPageSkeleton from "../components/common/ListPageSkeleton.vue"
import WorkspaceLoadError from "../components/common/WorkspaceLoadError.vue"
import FabricPurchaseOrders from "./fabric-store/FabricPurchaseOrders.vue"
import FabricReports from "./fabric-store/FabricReports.vue"
import FabricStockTransfers from "./fabric-store/FabricStockTransfers.vue"
import FabricWorkOrders from "./fabric-store/FabricWorkOrders.vue"
import ItemConversions from "./fabric-store/item-conversion/ItemConversions.vue"
import CutPanelDocuments from "./cut-panel-store/CutPanelDocuments.vue"

const props = defineProps({
	section: { type: String, required: true },
	storeName: { type: String, default: "Fabric Store" },
	basePath: { type: String, default: "/fabric-store" },
	workOrderViewRouteName: { type: String, default: "fabric-work-order" },
	workOrderNewRouteName: { type: String, default: "fabric-work-order-new" },
	purchaseOrderViewRouteName: { type: String, default: "fabric-purchase-order" },
	purchaseOrderNewRouteName: { type: String, default: "fabric-purchase-order-new" },
	deliveryChallanViewRouteName: { type: String, default: "fabric-delivery-challan" },
	deliveryChallanNewRouteName: { type: String, default: "" },
	goodsReceivedNoteViewRouteName: { type: String, default: "fabric-goods-received-note" },
	goodsReceivedNoteNewRouteName: { type: String, default: "" },
	reportKeys: { type: Array, default: () => ["stock_balance"] },
})
const definitions = {
	work_orders: { label: "Work Orders", component: FabricWorkOrders },
	delivery_challans: { label: "Delivery Challans", component: CutPanelDocuments },
	goods_received_notes: { label: "Goods Received Notes", component: CutPanelDocuments },
	purchase_orders: { label: "Purchase Orders", component: FabricPurchaseOrders },
	stock_transfers: { label: "Stock Transfers", component: FabricStockTransfers },
	item_conversions: { label: "Item Conversions", component: ItemConversions },
	reports: { label: "Reports", component: FabricReports },
}
const definition = computed(() => definitions[props.section] || definitions.work_orders)
const capability = ref(null)
const workOrderFilters = ref([])
const DOCUMENT_VIEW_ROUTES = { delivery_challans: "deliveryChallanViewRouteName", goods_received_notes: "goodsReceivedNoteViewRouteName" }
const sectionProps = computed(() => ({
	capability: capability.value,
	...(props.section === "work_orders" ? {
		filters: workOrderFilters.value,
		viewRouteName: props.workOrderViewRouteName,
		newRouteName: props.workOrderNewRouteName,
	} : {}),
	...(DOCUMENT_VIEW_ROUTES[props.section] ? {
		filters: workOrderFilters.value,
		viewRouteName: props[DOCUMENT_VIEW_ROUTES[props.section]],
	} : {}),
	...(props.section === "delivery_challans" ? { newRouteName: props.deliveryChallanNewRouteName } : {}),
	...(props.section === "goods_received_notes" ? { newRouteName: props.goodsReceivedNoteNewRouteName } : {}),
	...(props.section === "purchase_orders" ? {
		viewRouteName: props.purchaseOrderViewRouteName,
		newRouteName: props.purchaseOrderNewRouteName,
	} : {}),
	...(props.section === "reports" ? { reportKeys: props.reportKeys, department: props.basePath.slice(1) } : {}),
}))
const loading = ref(true)
const error = ref("")
let loadSequence = 0
const CAPABILITY_LOADERS = { "/quality": getQualityCapabilities, "/finishing": getFinishingCapabilities }

/** Work Order, Delivery Challan and GRN list filters a department narrows to: Sewing and Quality see their stitching processes. */
async function getWorkOrderFilters(basePath) {
	if (basePath !== "/sewing" && basePath !== "/quality") return []
	const processFilter = ["process_name", "in", await getSewingWorkOrderProcesses() || []]
	return basePath === "/quality" ? [["docstatus", "=", 1], processFilter] : [processFilter]
}

async function load() {
	const sequence = ++loadSequence
	const section = props.section, basePath = props.basePath
	loading.value = true
	error.value = ""
	try {
		const quality = basePath === "/quality"
		const payload = await (CAPABILITY_LOADERS[basePath] || getFabricStoreCapabilities)() || {}
		const sectionCapability = payload.sections?.[section] || null
		const nextCapability = quality
			? (sectionCapability?.can_read ? { ...sectionCapability, can_create: false } : null)
			: sectionCapability
		const scoped = section === "work_orders" || Boolean(DOCUMENT_VIEW_ROUTES[section])
		const filters = scoped && nextCapability ? await getWorkOrderFilters(basePath) : []
		if (sequence !== loadSequence) return
		capability.value = nextCapability
		workOrderFilters.value = filters
	} catch (reason) {
		if (sequence !== loadSequence) return
		error.value = reason?.message || `Unable to load ${definition.value.label}.`
	} finally {
		if (sequence === loadSequence) loading.value = false
	}
}

onMounted(load)
watch(() => [props.section, props.basePath], load)
</script>

<style scoped>
.fabric-store-section {
	width: 100%;
	min-width: 0;
	padding: 2px 0 var(--erp-space-5);
}

.fabric-store-section__loading {
	display: grid;
	gap: var(--erp-space-3);
	padding-top: 2px;
}
</style>
