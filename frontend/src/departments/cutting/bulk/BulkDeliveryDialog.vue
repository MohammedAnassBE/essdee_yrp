<template>
	<Dialog :visible="visible" modal dismissable-mask :header="bulkMode ? 'Create Bulk Delivery Challans' : `Create Delivery Challan · ${row?.lot || ''}`" class="bulk-delivery-dialog" @update:visible="emit('update:visible', $event)">
		<div class="delivery-form">
			<Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
			<Message v-if="bulkMode" severity="info" :closable="false">One submitted Delivery Challan will be created for every pending split lot.</Message>
			<label><span>Naming Series *</span><Select v-model="namingSeries" :options="options" :loading="loading" fluid /></label>
			<label><span>Vehicle No *</span><InputText v-model="vehicleNo" fluid /></label>
		</div>
		<template #footer><Button label="Close" severity="secondary" text :disabled="saving" @click="emit('update:visible', false)" /><Button :label="bulkMode ? 'Create & Submit All' : 'Create & Submit'" icon="pi pi-check" :loading="saving" :disabled="!namingSeries || !vehicleNo.trim()" @click="save" /></template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import InputText from "primevue/inputtext"
import Message from "primevue/message"
import Select from "primevue/select"
import { ref, watch } from "vue"

import { createAllBulkDeliveries, createBulkRowDelivery, getBulkDeliverySetup } from "../../../api/cuttingBulkLaySheets.js"

const props = defineProps({ visible: Boolean, bulkName: { type: String, required: true }, row: { type: Object, default: null }, bulkMode: Boolean })
const emit = defineEmits(["update:visible", "saved"])
const loading = ref(false)
const saving = ref(false)
const error = ref("")
const options = ref([])
const namingSeries = ref("")
const vehicleNo = ref("")

watch(() => props.visible, async (visible) => {
	if (!visible) return
	loading.value = true; error.value = ""; vehicleNo.value = ""
	try { const payload = await getBulkDeliverySetup(props.bulkName); options.value = payload?.options || []; namingSeries.value = payload?.default || options.value[0] || "" }
	catch (reason) { error.value = reason?.message || "Unable to load Delivery Challan setup." }
	finally { loading.value = false }
})
async function save() {
	saving.value = true; error.value = ""
	try {
		const payload = props.bulkMode
			? await createAllBulkDeliveries(props.bulkName, namingSeries.value, vehicleNo.value.trim())
			: await createBulkRowDelivery(props.bulkName, props.row.name, namingSeries.value, vehicleNo.value.trim())
		emit("saved", payload); emit("update:visible", false)
	} catch (reason) { error.value = reason?.message || "Unable to create Delivery Challan." }
	finally { saving.value = false }
}
</script>

<style scoped>
.delivery-form { display: grid; width: min(500px, calc(100vw - 64px)); gap: 13px; }.delivery-form label { display: grid; gap: 6px; }.delivery-form label span { color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 650; }
</style>
