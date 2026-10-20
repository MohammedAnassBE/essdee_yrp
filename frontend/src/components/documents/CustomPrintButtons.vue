<template>
	<Button v-for="action in actions" :key="action.key" :label="action.label" icon="pi pi-print" severity="secondary" outlined :disabled="disabled || loading" @click="print(action)" />
	<Dialog v-model:visible="printDialogVisible" modal header="Print Production Order" class="erp-dialog--sm">
		<label for="production-order-pieces-per-box">Pieces per Box</label>
		<InputNumber v-model="piecesPerBox" input-id="production-order-pieces-per-box" :use-grouping="false" :max-fraction-digits="0" :required="true" :invalid="Boolean(validationError)" aria-describedby="production-order-print-description" fluid />
		<p id="production-order-print-description">{{ description }}</p>
		<p v-if="validationError" role="alert">{{ validationError }}</p>
		<template #footer>
			<Button label="Cancel" severity="secondary" text @click="printDialogVisible = false" />
			<Button label="Print" icon="pi pi-print" @click="printPieces" />
		</template>
	</Dialog>
	<DocumentErrorDialog :message="error" title="Print failed" @dismiss="error = ''" />
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import InputNumber from "primevue/inputnumber"
import { computed, onBeforeUnmount, ref } from "vue"
import { callMethod } from "../../api/frappe.js"
import { useDocumentPermissions } from "../../composables/useDocumentPermissions.js"
import { getCustomPrintButtons } from "../../utils/customPrintButtons.js"
import { openPrintUrl } from "../../utils/printUrl.js"
import { buildProductionOrderPrintUrl, needsProductionOrderPrintDialog, getProductionOrderPrintDescription, validateProductionOrderPiecesPerBox } from "../../utils/productionOrderPrint.js"
import DocumentErrorDialog from "./DocumentErrorDialog.vue"

const props = defineProps({
	doctype: { type: String, required: true },
	record: { type: Object, default: () => ({}) },
	permissions: { type: Object, default: () => ({}) },
	disabled: { type: Boolean, default: false },
})
const permissions = useDocumentPermissions(() => [props.doctype, props.record?.name, props.record?.docstatus], () => props.permissions.can_print === undefined && props.doctype !== "SD YRP Cutting LaySheet")
const actions = computed(() => getCustomPrintButtons(props.doctype, props.record, { ...props.permissions, can_print: props.permissions.can_print ?? permissions.value?.print }))
const error = ref("")
const loading = ref(false)
const printDialogVisible = ref(false)
const piecesPerBox = ref(null)
const description = ref("")
const validationError = ref("")
let active = true
onBeforeUnmount(() => { active = false })

function openPrint(url) {
	error.value = openPrintUrl(url) ? "" : "Please enable pop-ups to print."
}

function print(action) {
	if (props.disabled || loading.value) return
	if (action.key === "production-order") return prepareProductionOrderPrint()
	openPrint(action.url)
}

async function prepareProductionOrderPrint() {
	loading.value = true
	error.value = ""
	const name = props.record.name
	try {
		const settings = await callMethod("essdee_yrp.production_order_workflow.get_production_order_print_settings", { production_order: name }) || {}
		if (!active || props.record?.name !== name) return
		if (!needsProductionOrderPrintDialog(settings)) {
			openPrint(buildProductionOrderPrintUrl({ doctype: props.doctype, name, piecesPerBox: Number(settings.pieces_per_box) }))
			return
		}
		piecesPerBox.value = null
		validationError.value = ""
		description.value = getProductionOrderPrintDescription(settings.fg_item_exists)
		printDialogVisible.value = true
	} catch (reason) {
		error.value = reason?.message || "Unable to load print settings."
	} finally {
		loading.value = false
	}
}

function printPieces() {
	validationError.value = validateProductionOrderPiecesPerBox(piecesPerBox.value)
	if (validationError.value) return
	printDialogVisible.value = false
	openPrint(buildProductionOrderPrintUrl({ doctype: props.doctype, name: props.record.name, piecesPerBox: piecesPerBox.value }))
}
</script>
