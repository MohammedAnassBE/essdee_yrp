<template>
	<Dialog :visible="visible" modal class="erp-dialog--sm" :header="mode === 'link' ? 'Link to PO' : 'Unlink from PO'" :closable="!saving" :dismissable-mask="false" @update:visible="emit('update:visible', $event)">
		<form class="lot-purchase-order-form" @submit.prevent="submit">
			<MultiSelectField v-model="selected" label="Purchase Orders" :options="options" :disabled="loading || saving" :loading="loading" :invalid="attempted && !selected.length" aria-required="true" @filter="search" />
			<small v-if="mode === 'link'" class="erp-help-text">Search submitted, open Purchase Orders.</small>
			<label class="lot-purchase-order-reason"><span class="erp-field-label">Reason<span class="erp-required-mark" aria-hidden="true">*</span></span><Textarea v-model="reason" rows="3" fluid required :disabled="saving" :invalid="attempted && !reason.trim()" /></label>
			<Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
		</form>
		<template #footer>
			<Button label="Cancel" severity="secondary" text :disabled="saving" @click="emit('update:visible', false)" />
			<Button :label="mode === 'link' ? 'Link' : 'Unlink'" :loading="saving" :disabled="loading" @click="submit" />
		</template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import Message from "primevue/message"
import Textarea from "primevue/textarea"
import { useToast } from "primevue/usetoast"
import { computed, ref, watch } from "vue"
import { callMethod, searchLink } from "../../../api/frappe.js"
import MultiSelectField from "../../../components/common/MultiSelectField.vue"
import { purchaseOrderLinkArgs, purchaseOrderLinkFilters, purchaseOrderOption } from "./lotPurchaseActions.js"

const props = defineProps({ visible: Boolean, lot: { type: String, required: true }, mode: { type: String, default: "link" } })
const emit = defineEmits(["update:visible", "changed"])
const toast = useToast()
const selected = ref([])
const choices = ref([])
const reason = ref("")
const error = ref("")
const loading = ref(false)
const saving = ref(false)
const attempted = ref(false)
const options = computed(() => {
	const byName = new Map(choices.value.map(option => [option.value, option]))
	const names = [...new Set([...selected.value, ...byName.keys()])]
	return names.map(name => byName.get(name) || purchaseOrderOption(name))
})
let sequence = 0

async function loadChoices(text = "") {
	const request = ++sequence
	loading.value = true
	error.value = ""
	try {
		const rows = props.mode === "unlink"
			? await callMethod("essdee_yrp.purchase_order_lots.get_purchase_orders_for_lot", { lot: props.lot })
			: await searchLink("Purchase Order", text, purchaseOrderLinkFilters(), 20)
		if (request !== sequence) return
		choices.value = (rows || []).map(purchaseOrderOption)
		if (props.mode === "unlink" && !choices.value.length) {
			toast.add({ severity: "info", summary: "This lot is not linked to any submitted PO", life: 5000 })
			emit("update:visible", false)
		}
	} catch (failure) {
		if (request === sequence) error.value = failure?.message || "Unable to load Purchase Orders."
	} finally {
		if (request === sequence) loading.value = false
	}
}
function search(event) {
	if (props.mode === "link") loadChoices(event.value || "")
}
async function submit() {
	if (saving.value || loading.value) return
	attempted.value = true
	error.value = ""
	try {
		const args = purchaseOrderLinkArgs(props.lot, props.mode, selected.value, reason.value)
		saving.value = true
		await callMethod("essdee_yrp.purchase_order_lots.update_lot_po_links", args)
		toast.add({ severity: "success", summary: props.mode === "link" ? "Purchase Orders linked" : "Purchase Orders unlinked", detail: props.lot, life: 3500 })
		emit("update:visible", false)
		emit("changed")
	} catch (failure) {
		error.value = failure?.message || "Unable to update Purchase Order links."
	} finally {
		saving.value = false
	}
}
watch(() => [props.visible, props.lot, props.mode], () => {
	sequence++
	if (!props.visible) return
	selected.value = []
	choices.value = []
	reason.value = ""
	attempted.value = false
	loadChoices()
}, { immediate: true })
</script>

<style scoped>
.lot-purchase-order-form, .lot-purchase-order-reason { display: grid; gap: 12px; }
.lot-purchase-order-reason { gap: 6px; }
</style>
