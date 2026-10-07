<template>
	<DepartmentPage title="Purchase Order" accent="#0a7f5a" back-to="/fabric-store/purchase-orders" back-label="Purchase Orders" :show-title="false" flat full-width>
		<div class="fabric-purchase-order-editor-page erp-workspace">
			<PurchaseOrderEditor :key="`${purchaseOrderId || 'new'}-${duplicateFrom}`" :name="purchaseOrderId" :source="duplicateSource" @saved="saved" @cancel="cancel" />
		</div>
	</DepartmentPage>
</template>

<script setup>
import { computed } from "vue"
import { useRoute, useRouter } from "vue-router"

import DepartmentPage from "../components/DepartmentPage.vue"
import PurchaseOrderEditor from "./fabric-store/PurchaseOrderEditor.vue"

const route = useRoute()
const router = useRouter()
const purchaseOrderId = computed(() => String(route.params.purchaseOrderId || ""))
const duplicateFrom = computed(() => String(route.query.duplicate_from || ""))
const duplicateSource = computed(() => duplicateFrom.value ? { duplicate_from: duplicateFrom.value } : {})

function saved(record) {
	if (!record?.name) return
	router.replace({ name: "fabric-purchase-order", params: { purchaseOrderId: record.name } })
}
function cancel() {
	if (purchaseOrderId.value) router.push({ name: "fabric-purchase-order", params: { purchaseOrderId: purchaseOrderId.value } })
	else if (duplicateFrom.value) router.push({ name: "fabric-purchase-order", params: { purchaseOrderId: duplicateFrom.value } })
	else router.push({ name: "fabric-purchase-orders" })
}
</script>

<style scoped>
.fabric-purchase-order-editor-page { width: 100%; max-width: 1840px; min-width: 0; margin: 0 auto; padding: 0 clamp(2px, .7vw, 10px) var(--erp-space-3); }
@media (max-width: 620px) { .fabric-purchase-order-editor-page { padding-right: 0; padding-left: 0; } }
</style>
