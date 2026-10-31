<template>
	<Dialog
		:visible="visible"
		modal
		maximizable
		:closable="false"
		:close-on-escape="false"
		:header="header"
		class="production-order-purchase-order-dialog erp-entity-dialog erp-dialog--xl"
		@update:visible="(value) => { if (!value) close() }"
	>
		<template v-if="visible && productionOrder">
			<PurchaseOrderEditor v-if="editing" :key="`edit-${currentName || 'new'}`" :name="currentName" :source="currentName ? {} : source" @saved="saved" @cancel="cancelEdit" />
			<FabricPurchaseOrder v-else :key="`view-${currentName}`" presentation="embedded" :name="currentName" @changed="emit('changed', $event)" @edit="editing = true" @open="currentName = $event" @closed="close" />
		</template>
	</Dialog>
</template>

<script setup>
import Dialog from "primevue/dialog"
import { computed, ref, watch } from "vue"

import FabricPurchaseOrder from "../FabricPurchaseOrder.vue"
import PurchaseOrderEditor from "../fabric-store/PurchaseOrderEditor.vue"
import { purchaseOrderSourceFor } from "./productionOrderPurchaseOrder.js"

const props = defineProps({
	visible: { type: Boolean, default: false },
	productionOrder: { type: String, default: "" },
	purchaseOrder: { type: String, default: "" },
})
const emit = defineEmits(["update:visible", "changed"])
const source = computed(() => purchaseOrderSourceFor(props.productionOrder))
const currentName = ref("")
const editing = ref(true)
const header = computed(() => `${currentName.value ? `Purchase Order · ${currentName.value}` : "New Purchase Order"} · ${props.productionOrder}`)

watch(() => [props.visible, props.purchaseOrder], ([visible]) => {
	if (!visible) return
	currentName.value = props.purchaseOrder
	editing.value = !props.purchaseOrder
}, { immediate: true })

function close() { emit("update:visible", false) }
function saved(record) {
	if (record?.name) currentName.value = record.name
	editing.value = false
	emit("changed", record)
}
function cancelEdit() {
	if (currentName.value) editing.value = false
	else close()
}
</script>

<style scoped>
:global(.production-order-purchase-order-dialog .purchase-order-editor) { min-height: 0; border: 0; }
</style>
