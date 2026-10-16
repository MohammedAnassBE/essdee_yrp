<template>
	<Dialog :visible="visible" modal :header="title" class="ppo-action-dialog erp-dialog--md" :dismissable-mask="false" @update:visible="emit('update:visible', $event)">
		<div class="ppo-action-dialog__body">
			<template v-if="mode === 'request_changes'">
				<label class="ppo-action-field"><span>Reason *</span><Textarea v-model="form.reason" rows="4" autofocus fluid /></label>
			</template>
			<template v-else-if="mode === 'change_dates'">
				<label class="ppo-action-field"><span>Date to change *</span><Select v-model="form.date_field" :options="dateFields" option-label="label" option-value="value" fluid /></label>
				<label class="ppo-action-field"><span>New date *</span><DateField v-model="form.new_date" fluid /></label>
				<label class="ppo-action-field ppo-action-field--wide"><span>Reason *</span><Textarea v-model="form.reason" rows="3" fluid /></label>
			</template>
			<template v-else-if="mode === 'change_status'">
				<label class="ppo-action-field"><span>New status *</span><Select v-model="form.new_status" :options="statuses" fluid /></label>
				<label class="ppo-action-field"><span>Reason *</span><Textarea v-model="form.reason" rows="3" fluid /></label>
			</template>
			<template v-else-if="mode === 'update_quantity_ratio'">
				<label class="ppo-action-field"><span>Requested by *</span><Select v-model="form.requested_by" :options="requestedByOptions" fluid /></label>
				<label class="ppo-action-field"><span>Reason *</span><Textarea v-model="form.reason" rows="2" fluid /></label>
				<div class="ppo-action-matrix ppo-action-field--wide"><table><thead><tr><th>Size</th><th>Quantity</th><th>Ratio</th></tr></thead><tbody><tr v-for="row in editableRows" :key="row.size"><th>{{ row.size }}</th><td><InputNumber v-model="row.quantity" :min="0" :max-fraction-digits="0" :use-grouping="false" /></td><td><InputNumber v-model="row.ratio" :min="0" :max-fraction-digits="3" :use-grouping="false" /></td></tr></tbody></table></div>
			</template>
			<template v-else-if="mode === 'transfer_quantity'">
				<LinkField v-model="form.target_production_order" label="Target Production Order *" doctype="YRP Production Order" :show-open-button="false" />
				<label class="ppo-action-field"><span>Reason *</span><Textarea v-model="form.reason" rows="3" fluid /></label>
			</template>
			<template v-else-if="mode === 'create_lot'">
				<label class="ppo-action-field"><span>New Lot name *</span><InputText v-model="form.lot_name" autofocus fluid /></label>
			</template>
			<template v-else-if="mode === 'link_lot'">
				<LinkField v-model="form.lot_name" label="Existing Lot *" doctype="SD YRP Lot" :show-open-button="false" />
			</template>
		</div>
		<template #footer><Button label="Cancel" severity="secondary" text :disabled="busy" @click="emit('update:visible', false)" /><Button :label="submitLabel" icon="pi pi-check" :loading="busy" :disabled="!valid" @click="submit" /></template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import InputNumber from "primevue/inputnumber"
import InputText from "primevue/inputtext"
import Select from "primevue/select"
import Textarea from "primevue/textarea"
import { computed, reactive, ref, watch } from "vue"

import DateField from "../../components/common/DateField.vue"
import LinkField from "../../components/common/LinkField.vue"

const props = defineProps({ visible: { type: Boolean, default: false }, mode: { type: String, default: "" }, matrix: { type: Array, default: () => [] }, busy: { type: Boolean, default: false } })
const emit = defineEmits(["update:visible", "submit"])
const form = reactive({ reason: "", date_field: "Delivery Date", new_date: "", new_status: "", requested_by: "", target_production_order: "", lot_name: "" })
const editableRows = ref([])
const dateFields = [{ label: "Delivery Date", value: "Delivery Date" }, { label: "Don't Deliver After", value: "Don't Deliver After" }]
const statuses = ["Open", "Item Changed", "Not Processed"]
const requestedByOptions = ["Sales Team", "Planning Team", "Merch Team"]
const titles = { request_changes: "Request PPO changes", change_dates: "Change delivery dates", change_status: "Change status", update_quantity_ratio: "Update quantity & ratio", transfer_quantity: "Transfer quantity", create_lot: "Create Lot", link_lot: "Link existing Lot" }
const title = computed(() => titles[props.mode] || "Production Order action")
const submitLabel = computed(() => ({ request_changes: "Request Changes", change_dates: "Change Dates", change_status: "Change Status", update_quantity_ratio: "Send Request", transfer_quantity: "Send Transfer Request", create_lot: "Create Lot", link_lot: "Link Lot" }[props.mode] || "Continue"))
const valid = computed(() => {
	if (props.mode === "request_changes") return Boolean(form.reason.trim())
	if (props.mode === "change_dates") return Boolean(form.date_field && form.new_date && form.reason.trim())
	if (props.mode === "change_status") return Boolean(form.new_status && form.reason.trim())
	if (props.mode === "update_quantity_ratio") return Boolean(form.requested_by && form.reason.trim() && editableRows.value.length)
	if (props.mode === "transfer_quantity") return Boolean(form.target_production_order && form.reason.trim())
	return Boolean(form.lot_name)
})

function number(value) { const parsed = Number(value); return Number.isFinite(parsed) ? parsed : 0 }
function reset() {
	Object.assign(form, { reason: "", date_field: "Delivery Date", new_date: "", new_status: "", requested_by: "", target_production_order: "", lot_name: "" })
	editableRows.value = props.matrix.map((row) => ({ ...JSON.parse(JSON.stringify(row)), quantity: number(row.quantity), ratio: number(row.ratio) }))
}
function submit() {
	let payload = { ...form }
	if (props.mode === "update_quantity_ratio") payload = { size_quantities: Object.fromEntries(editableRows.value.map((row) => [row.size, row.quantity])), size_ratios: Object.fromEntries(editableRows.value.map((row) => [row.size, row.ratio])), requested_by: form.requested_by, reason: form.reason }
	emit("submit", payload)
}
watch(() => props.visible, (visible) => { if (visible) reset() })
</script>

<style scoped>
.ppo-action-dialog__body { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; min-width: 0; }
.ppo-action-field { display: grid; align-content: start; gap: 6px; }
.ppo-action-field > span { color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 680; }
.ppo-action-field--wide { grid-column: 1 / -1; }
.ppo-action-matrix { max-height: min(48dvh, 420px); overflow: auto; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); }
.ppo-action-matrix table { width: 100%; border-collapse: collapse; }
.ppo-action-matrix th, .ppo-action-matrix td { padding: 8px 10px; text-align: left; border-bottom: 1px solid var(--erp-border); }
.ppo-action-matrix thead { position: sticky; z-index: 1; top: 0; background: var(--erp-surface-muted); }
.ppo-action-matrix th { color: var(--erp-text); font-size: var(--erp-font-size-caption); }
.ppo-action-matrix td { color: var(--erp-text-secondary); font-size: var(--erp-font-size-caption); }
@media (max-width: 620px) { .ppo-action-dialog__body { grid-template-columns: 1fr; } .ppo-action-field--wide { grid-column: auto; } }
</style>
