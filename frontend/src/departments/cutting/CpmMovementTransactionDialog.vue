<template>
	<Dialog :visible="visible" modal dismissable-mask :header="title" class="erp-movement-transaction-dialog erp-entity-dialog" @update:visible="emit('update:visible', $event)">
		<div class="erp-movement-transaction">
			<Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
			<label v-if="movements.length" class="erp-movement-field"><span>Cut Panel Movement *</span><Select v-model="selectedMovementName" :options="movements" option-label="name" option-value="name" placeholder="Select a submitted movement" fluid /></label>
			<div v-if="chosenMovement" class="erp-transaction-source"><i class="pi pi-box"></i><div><span>Cut Panel Movement</span><strong>{{ chosenMovement.name }}</strong><small>{{ chosenMovement.totals?.exact_bundles || 0 }} bundles · {{ chosenMovement.totals?.selected_panels || 0 }} panels · {{ chosenMovement.totals?.collapsed_rows || 0 }} collapsed rows · {{ chosenMovement.totals?.accessory_rows || 0 }} accessories</small></div></div>
			<template v-if="operation === 'stock_entry'">
				<LinkField v-model="form.to_warehouse" label="To Warehouse *" doctype="Warehouse" help-text="The source Warehouse and selected bundle quantities come from the movement." :show-open-button="false" />
			</template>
			<template v-else>
				<div class="erp-same-location"><i class="pi pi-check-circle"></i><div><strong>Same-location Work Order delivery</strong><span>From and To use {{ context.source_supplier }} / {{ context.source_warehouse }}. The Delivery Challan keeps balanced audit legs.</span></div></div>
				<div class="erp-derived-fields"><span><small>Work Order</small><strong>{{ context.work_order || "Derived from plan" }}</strong></span><span><small>Vehicle / Supplier document</small><strong>Recorded as NA</strong></span></div>
			</template>
		</div>
		<template #footer>
			<Button label="Close" severity="secondary" text :disabled="saving" @click="emit('update:visible', false)" />
			<Button v-if="permissions.can_create" label="Save Draft" icon="pi pi-save" severity="secondary" outlined :disabled="!canSave" :loading="saving && saveMode === 'draft'" @click="save(false)" />
			<Button v-if="permissions.can_create && permissions.can_submit" label="Save & Submit" icon="pi pi-check" :disabled="!canSave" :loading="saving && saveMode === 'submit'" @click="save(true)" />
		</template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import Message from "primevue/message"
import Select from "primevue/select"
import { computed, reactive, ref, watch } from "vue"

import LinkField from "../../components/common/LinkField.vue"
import { createMovementTransaction } from "./cpmApi.js"

const props = defineProps({
	visible: Boolean,
	cuttingPlan: { type: String, required: true },
	movement: { type: Object, default: null },
	movements: { type: Array, default: () => [] },
	operation: { type: String, required: true },
	context: { type: Object, default: () => ({}) },
	permissions: { type: Object, default: () => ({}) },
})
const emit = defineEmits(["update:visible", "changed"])
const form = reactive(emptyForm())
const error = ref("")
const saving = ref(false)
const saveMode = ref("")
const selectedMovementName = ref("")
const title = computed(() => props.operation === "delivery_challan" ? "Create Delivery Challan" : "Create Stock Entry from Movement")
const chosenMovement = computed(() => props.movements.find((row) => row.name === selectedMovementName.value) || (props.movement?.name === selectedMovementName.value ? props.movement : null))
const canSave = computed(() => Boolean(props.permissions.can_create && chosenMovement.value?.name && (props.operation !== "stock_entry" || form.to_warehouse)))

watch(() => [props.visible, props.operation, props.movement?.name], ([visible]) => {
	if (!visible) return
	Object.assign(form, emptyForm())
	selectedMovementName.value = props.movement?.name || ""
	error.value = ""
})

async function save(submit) {
	if (!canSave.value) return
	saving.value = true
	saveMode.value = submit ? "submit" : "draft"
	error.value = ""
	try {
		const saved = await createMovementTransaction(props.cuttingPlan, chosenMovement.value.name, props.operation, form, submit)
		emit("changed", saved)
		emit("update:visible", false)
	} catch (reason) {
		error.value = reason.message || "Unable to create the movement transaction."
	} finally {
		saving.value = false
		saveMode.value = ""
	}
}

function emptyForm() { return { to_warehouse: "", vehicle_no: "NA", supplier_document_no: "NA" } }
</script>

<style scoped>
.erp-movement-transaction{display:grid;gap:14px;min-width:min(560px,80vw)}.erp-movement-field{display:grid;gap:6px}.erp-movement-field>span{color:var(--erp-text);font-size:var(--erp-font-size-caption);font-weight:650}.erp-transaction-source,.erp-same-location{display:flex;gap:11px;padding:13px;border:1px solid var(--erp-border);border-radius:var(--erp-control-radius);background:var(--erp-surface-soft)}.erp-transaction-source>i,.erp-same-location>i{display:grid;width:34px;height:34px;flex:0 0 34px;place-items:center;border-radius:var(--erp-control-radius);background:var(--erp-accent-soft);color:var(--erp-accent)}.erp-transaction-source div,.erp-same-location div{display:grid;gap:2px}.erp-transaction-source span{color:var(--erp-text-muted);font-size:var(--erp-font-size-min);text-transform:uppercase}.erp-transaction-source strong,.erp-same-location strong{color:var(--erp-text);font-size:.84rem}.erp-transaction-source small,.erp-same-location span{color:var(--erp-text-muted);font-size:var(--erp-font-size-min);line-height:1.45}.erp-derived-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));overflow:hidden;border:1px solid var(--erp-border);border-radius:var(--erp-control-radius)}.erp-derived-fields>span{display:grid;gap:3px;padding:10px 12px;background:var(--erp-surface-soft);border-right:1px solid var(--erp-border)}.erp-derived-fields>span:last-child{border-right:0}.erp-derived-fields small{color:var(--erp-text-muted);font-size:var(--erp-font-size-min);text-transform:uppercase}.erp-derived-fields strong{color:var(--erp-text);font-size:var(--erp-font-size-caption)}@media(max-width:650px){.erp-movement-transaction{min-width:0}.erp-derived-fields{grid-template-columns:1fr}}
</style>
