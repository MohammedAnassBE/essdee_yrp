<template>
	<section class="lt-quantity-editor" aria-label="Lot Transfer quantities">
		<header>
			<strong>Transfer Quantity</strong>
			<small>Only the quantity can be changed. Delete a row to leave it in the current Lot.</small>
		</header>
		<div class="table-scroll" role="region" tabindex="0" aria-label="Lot Transfer quantity rows">
			<table class="lt-quantity-table">
				<thead><tr><th>Cloth</th><th>From Lot</th><th>To Lot</th><th class="numeric">Available</th><th class="numeric">Quantity</th><th></th></tr></thead>
				<tbody>
					<tr v-for="row in draft" :key="row.name">
						<td>{{ row.label }}</td>
						<td>{{ row.from_lot }}</td>
						<td>{{ row.to_lot }}</td>
						<td class="numeric">{{ row.available }} {{ row.uom || "" }}</td>
						<td class="numeric">
							<InputNumber v-model="row.qty" :min="0" :max-fraction-digits="3" :invalid="Boolean(errors[row.name])" :disabled="saving" :input-props="{ 'aria-label': `Quantity for ${row.label}` }" fluid />
							<small v-if="errors[row.name]" class="lt-quantity-error">{{ errors[row.name] }}</small>
						</td>
						<td><Button icon="pi pi-trash" severity="danger" text rounded :disabled="saving || draft.length === 1" :title="draft.length === 1 ? 'A Lot Transfer needs at least one row. Delete the Lot Transfer instead.' : 'Delete row'" :aria-label="`Delete ${row.label}`" @click="requestDelete(row)" /></td>
					</tr>
				</tbody>
			</table>
		</div>
		<footer>
			<Button label="Reset" severity="secondary" text :disabled="saving || !dirty" @click="reset" />
			<Button label="Save Quantity" icon="pi pi-save" :disabled="!dirty || hasErrors" :loading="saving" @click="save" />
		</footer>
		<DocumentErrorDialog :message="error" title="Lot Transfer quantity was not saved" @dismiss="error = ''" />
	</section>
</template>

<script setup>
import Button from "primevue/button"
import InputNumber from "primevue/inputnumber"
import { computed, ref, watch } from "vue"

import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import { useActionConfirmation } from "../../utils/useActionConfirmation.js"
import { updateLotTransferQuantities } from "./cpmApi.js"
import { hasQuantityChanges, quantityDraft, quantityErrors, quantityPayload } from "./lotTransferQuantities.js"

const props = defineProps({ cuttingPlan: { type: String, required: true }, record: { type: Object, required: true } })
const emit = defineEmits(["saved", "dirty"])
const confirmAction = useActionConfirmation()
const draft = ref([])
const saving = ref(false)
const error = ref("")
const errors = computed(() => quantityErrors(draft.value))
const hasErrors = computed(() => Object.keys(errors.value).length > 0)
const dirty = computed(() => hasQuantityChanges(props.record.quantity_rows, draft.value))

watch(() => props.record, reset, { immediate: true })
watch(dirty, (value) => emit("dirty", value), { immediate: true })

function reset() { draft.value = quantityDraft(props.record.quantity_rows) }

function requestDelete(row) {
	if (draft.value.length === 1) return
	confirmAction({
		header: "Delete row?",
		message: `Remove ${row.label} from Lot Transfer ${props.record.name}? It is removed when you save.`,
		acceptLabel: "Delete Row",
		acceptIcon: "pi pi-trash",
		rejectLabel: "Keep Row",
		accept: () => { draft.value = draft.value.filter((item) => item.name !== row.name) },
	})
}

async function save() {
	if (!dirty.value || hasErrors.value) return
	saving.value = true
	error.value = ""
	try {
		emit("saved", await updateLotTransferQuantities(props.cuttingPlan, props.record.name, quantityPayload(draft.value), props.record.modified))
	} catch (reason) {
		error.value = reason.message || "Unable to save the Lot Transfer quantity."
	} finally {
		saving.value = false
	}
}
</script>

<style scoped>
.lt-quantity-editor{display:grid;gap:10px;padding:12px;border:1px solid var(--erp-border);border-radius:var(--erp-panel-radius);background:var(--erp-surface)}.lt-quantity-editor header{display:grid;gap:2px}.lt-quantity-editor header strong{color:var(--erp-text);font-size:13px}.lt-quantity-editor header small{color:var(--erp-text-muted);font-size:var(--erp-font-size-min)}.table-scroll{overflow-x:auto}.lt-quantity-table{width:100%;border-collapse:collapse;font-size:13px}.lt-quantity-table th,.lt-quantity-table td{padding:6px 8px;border-bottom:1px solid var(--erp-border);text-align:left;vertical-align:top}.lt-quantity-table th{color:var(--erp-text-muted);font-size:var(--erp-font-size-min);text-transform:uppercase}.lt-quantity-table .numeric{text-align:right;font-variant-numeric:tabular-nums}.lt-quantity-table td.numeric{min-width:140px}.lt-quantity-error{display:block;margin-top:4px;color:var(--erp-danger);font-size:var(--erp-font-size-min);text-align:left}.lt-quantity-editor footer{display:flex;justify-content:flex-end;gap:8px}
</style>
