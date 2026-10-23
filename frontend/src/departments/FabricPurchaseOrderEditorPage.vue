<template>
	<DepartmentPage title="Purchase Order" :back-to="backTo" :back-label="backLabel" :show-title="false" flat full-width>
		<div class="fabric-purchase-order-editor-page erp-workspace">
			<PurchaseOrderEditor :key="`${purchaseOrderId || 'new'}-${duplicateFrom}`" :name="purchaseOrderId" :source="duplicateSource" :new-defaults="newDefaults" @saved="saved" @cancel="cancel" />
		</div>
	</DepartmentPage>
</template>

<script setup>
import { computed } from "vue"
import { useRoute, useRouter } from "vue-router"

import DepartmentPage from "../components/DepartmentPage.vue"
import { preserveListNavigationState } from "../router/listDocumentNavigation.js"
import PurchaseOrderEditor from "./fabric-store/PurchaseOrderEditor.vue"
import { takeNewDocumentDefaults } from "../utils/newDocumentDefaults.js"

const props = defineProps({
	backTo: { type: String, default: "/fabric-store/purchase-orders" },
	backLabel: { type: String, default: "Purchase Orders" },
	listRouteName: { type: String, default: "fabric-purchase-orders" },
	viewRouteName: { type: String, default: "fabric-purchase-order" },
})

const route = useRoute()
const router = useRouter()
const purchaseOrderId = computed(() => String(route.params.purchaseOrderId || ""))
const duplicateFrom = computed(() => String(route.query.duplicate_from || ""))
const duplicateSource = computed(() => duplicateFrom.value ? { duplicate_from: duplicateFrom.value } : {})
const filterDefaults = takeNewDocumentDefaults("Purchase Order")
const newDefaults = purchaseOrderId.value || duplicateFrom.value ? {} : filterDefaults

function saved(record) {
	if (!record?.name) return
	router.replace({ name: props.viewRouteName, params: { purchaseOrderId: record.name }, state: preserveListNavigationState(record.name, record.modified) })
}
function cancel() {
	if (purchaseOrderId.value) router.push({ name: props.viewRouteName, params: { purchaseOrderId: purchaseOrderId.value }, state: preserveListNavigationState(purchaseOrderId.value) })
	else if (duplicateFrom.value) router.push({ name: props.viewRouteName, params: { purchaseOrderId: duplicateFrom.value } })
	else router.push({ name: props.listRouteName })
}
</script>

<style scoped>
.fabric-purchase-order-editor-page { width: 100%; min-width: 0; padding-bottom: var(--erp-space-3); }
</style>
