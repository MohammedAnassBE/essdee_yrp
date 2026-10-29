<template>
	<section class="inspection-entry-panel" aria-label="Inspection Entry preparation">
		<header class="inspection-entry-panel__header">
			<div><span>Goods receipt inspection</span><h2>Create Inspection Entry</h2></div>
			<Button icon="pi pi-times" severity="secondary" text rounded aria-label="Close inspection" :disabled="Boolean(acting)" @click="emit('close')" />
		</header>

		<Message v-if="context.reason" severity="warn" :closable="false">{{ context.reason }}</Message>

		<div class="inspection-entry-panel__fields">
			<DateField v-model="form.posting_date" label="Posting Date" required :disabled="Boolean(acting)" />
			<TimeField v-model="form.posting_time" label="Posting Time" required :disabled="Boolean(acting)" />
			<label class="inspection-entry-panel__remarks"><span>Remarks</span><Textarea v-model="form.remarks" rows="2" auto-resize fluid :disabled="Boolean(acting)" /></label>
		</div>

		<div class="inspection-entry-panel__sources">
			<article v-for="(source, sourceIndex) in sources" :key="sourceKey(source, sourceIndex)" class="inspection-entry-panel__source">
				<header>
					<div><strong>{{ source.item_variant || "Item" }}</strong><span>{{ source.lot || "No lot" }}</span></div>
					<div><span>Source bin</span><strong>{{ source.warehouse || "—" }}</strong></div>
					<div><span>Available</span><strong>{{ formatQty(source.grn_qty || source.quantity) }}</strong></div>
				</header>
				<div class="inspection-entry-panel__split-list" role="region" :aria-label="`Inspection splits for ${source.item_variant || 'item'}`">
					<table v-entry-table="{ add: () => addSplit(source), canAdd: !acting, isRowBlank: (index) => isSplitBlank(source.splits[index]), fixed: false }" class="erp-data-table inspection-entry-panel__splits">
						<thead><tr><th class="inspection-entry-panel__select"><input type="checkbox" class="inspection-entry-panel__checkbox" data-row-select :checked="isSourceAllSelected(source)" :indeterminate="isSourcePartlySelected(source)" :disabled="!sourceSelectableSplits(source).length" aria-label="Select all inspection splits" @change="toggleSource(source, $event.target.checked)" /></th><th>Target Received Type *</th><th class="erp-number">Quantity *</th><th>Received Date</th><th>Comments</th></tr></thead>
						<tbody>
							<tr v-for="(split, splitIndex) in source.splits" :key="splitIndex">
								<td class="inspection-entry-panel__select"><input type="checkbox" class="inspection-entry-panel__checkbox" data-row-select tabindex="-1" :checked="splitSelection.isSelected(split)" :disabled="!removableSplits.includes(split)" :aria-label="`Select inspection split ${splitIndex + 1}`" @change="splitSelection.toggle(split, $event.target.checked)" /></td>
								<td class="inspection-entry-panel__target-type"><LinkField v-model="split.target_received_type" :aria-label="`Target Received Type for split ${splitIndex + 1}`" doctype="YRP Received Type" :show-open-button="false" :disabled="Boolean(acting)" /></td>
								<td class="inspection-entry-panel__quantity"><InputNumber v-model="split.qty" :aria-label="`Quantity for split ${splitIndex + 1}`" :min="0" :max="Number(source.grn_qty || source.quantity || 0)" :max-fraction-digits="3" fluid :disabled="Boolean(acting)" /></td>
								<td class="inspection-entry-panel__date"><DateField v-model="split.received_date" :aria-label="`Received Date for split ${splitIndex + 1}`" :disabled="Boolean(acting)" /></td>
								<td><InputText v-model="split.comments" :aria-label="`Comments for split ${splitIndex + 1}`" fluid :disabled="Boolean(acting)" /></td>
							</tr>
						</tbody>
					</table>
				</div>
				<div v-if="sourceSelectedSplits(source).length" class="inspection-entry-panel__selection">
					<span>{{ sourceSelectedSplits(source).length }} selected</span>
					<Button label="Delete" icon="pi pi-trash" severity="danger" size="small" :disabled="Boolean(acting)" @click="deleteSelectedSplits(source)" />
				</div>
				<footer><span>Assigned {{ formatQty(splitTotal(source)) }} / {{ formatQty(source.grn_qty || source.quantity) }}</span><Button label="Add split" icon="pi pi-plus" severity="secondary" text size="small" :disabled="Boolean(acting)" @click="addSplit(source)" /></footer>
			</article>
		</div>

		<section v-if="context.entries?.length" class="inspection-entry-panel__existing">
			<header><span>Existing Inspection Entries</span><strong>{{ context.entries.length }}</strong></header>
			<div><span v-for="entry in context.entries" :key="entry.name"><strong>{{ entry.name }}</strong><small>{{ entry.status || statusLabel(entry.docstatus) }}</small></span></div>
		</section>

		<footer class="inspection-entry-panel__actions">
			<Button label="Close" severity="secondary" text :disabled="Boolean(acting)" @click="emit('close')" />
			<div>
				<Button v-if="context.can_create" label="Save Inspection Draft" icon="pi pi-save" severity="secondary" outlined :loading="acting === 'inspection_save'" :disabled="!canSave" @click="save(false)" />
				<Button v-if="context.can_submit" label="Save & Submit Inspection" icon="pi pi-check" :loading="acting === 'inspection_submit'" :disabled="!canSave" @click="save(true)" />
			</div>
		</footer>
	</section>
	<DocumentErrorDialog :message="error" title="Inspection Entry could not be saved" />
</template>

<script setup>
import Button from "primevue/button"
import InputNumber from "primevue/inputnumber"
import InputText from "primevue/inputtext"
import Message from "primevue/message"
import Textarea from "primevue/textarea"
import { computed, reactive, ref, watch } from "vue"

import DateField from "../../components/common/DateField.vue"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import LinkField from "../../components/common/LinkField.vue"
import TimeField from "../../components/common/TimeField.vue"
import { vEntryTable } from "../../components/common/childGrid/entryTable.js"
import { removalOrder, useRowSelection } from "../../components/common/childGrid/rowSelection.js"

const props = defineProps({
	context: { type: Object, default: () => ({}) },
	acting: { type: String, default: "" },
	error: { type: String, default: "" },
})
const emit = defineEmits(["save", "close"])

const form = reactive({ posting_date: "", posting_time: "", remarks: "" })
const sources = ref([])
const canSave = computed(() => Boolean(
	!props.acting
	&& sources.value.length
	&& sources.value.every((source) => {
		const available = Number(source.grn_qty || source.quantity || 0)
		const splits = source.splits || []
		return splits.some((split) => split.target_received_type && Number(split.qty || 0) > 0)
			&& splits.every((split) => split.target_received_type && Number(split.qty || 0) >= 0)
			&& splitTotal(source) <= available + 0.0001
	}),
))

const removableSplits = computed(() => props.acting ? [] : sources.value.flatMap((source) => source.splits.length > 1 ? source.splits : []))
const splitSelection = useRowSelection(removableSplits)

watch(() => props.context, (context) => {
	form.posting_date = context.posting_date || new Date().toISOString().slice(0, 10)
	form.posting_time = context.posting_time || new Date().toTimeString().slice(0, 8)
	form.remarks = ""
	sources.value = clone(context.initial_payload || []).map((source) => ({
		...source,
		splits: source.splits?.length ? source.splits : [emptySplit(source)],
	}))
}, { immediate: true })

function emptySplit(source) {
	return {
		target_received_type: source.received_type || source.source_received_type || "",
		qty: Number(source.grn_qty || source.quantity || 0),
		received_date: new Date().toISOString().slice(0, 10),
		comments: "",
	}
}
function addSplit(source) { source.splits.push({ ...emptySplit(source), qty: 0 }) }
function isSplitBlank(split) { return !Number(split?.qty || 0) && !split?.comments }
function removeSplit(source, index) { source.splits.splice(index, 1) }
function sourceSelectableSplits(source) { return source.splits.filter((split) => removableSplits.value.includes(split)) }
function sourceSelectedSplits(source) { return source.splits.filter((split) => splitSelection.isSelected(split)) }
function isSourceAllSelected(source) { return sourceSelectableSplits(source).length > 0 && sourceSelectableSplits(source).every((split) => splitSelection.isSelected(split)) }
function isSourcePartlySelected(source) { return sourceSelectedSplits(source).length > 0 && !isSourceAllSelected(source) }
function toggleSource(source, on) { for (const split of sourceSelectableSplits(source)) splitSelection.toggle(split, on) }
function deleteSelectedSplits(source) {
	const chosen = sourceSelectedSplits(source)
	for (const split of chosen) splitSelection.toggle(split, false)
	for (const split of removalOrder(source.splits, chosen)) if (source.splits.length > 1) removeSplit(source, source.splits.indexOf(split))
}
function splitTotal(source) { return (source.splits || []).reduce((total, split) => total + Number(split.qty || 0), 0) }
function save(submit) { emit("save", { values: { ...form, item_details: clone(sources.value) }, submit }) }
function sourceKey(source, index) { return `${source.ref_doctype || "source"}-${source.ref_docname || source.item_variant || index}` }
function statusLabel(docstatus) { return Number(docstatus) === 1 ? "Submitted" : Number(docstatus) === 2 ? "Cancelled" : "Draft" }
function formatQty(value) { return Number(value || 0).toLocaleString("en-IN", { maximumFractionDigits: 3 }) }
function clone(value) { return JSON.parse(JSON.stringify(value || [])) }
</script>

<style scoped>
.inspection-entry-panel { display: grid; overflow: hidden; gap: var(--erp-space-3); border: 1px solid color-mix(in srgb, var(--erp-accent) 20%, var(--erp-border)); border-radius: var(--erp-panel-radius); background: var(--erp-surface); box-shadow: 0 7px 20px rgb(28 61 45 / 4%); }
.inspection-entry-panel__header { display: flex; min-height: 48px; align-items: center; justify-content: space-between; gap: 12px; padding: 8px 12px; border-bottom: 1px solid var(--erp-border); border-left: 3px solid var(--erp-accent); background: color-mix(in srgb, var(--erp-accent-soft) 72%, var(--erp-surface)); }
.inspection-entry-panel__header > div { display: grid; gap: 2px; }
.inspection-entry-panel__header span, .inspection-entry-panel__remarks > span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 750; letter-spacing: .035em; text-transform: uppercase; }
.inspection-entry-panel__header h2 { margin: 0; font-size: var(--erp-font-size-section); }
.inspection-entry-panel > :not(.inspection-entry-panel__header, .inspection-entry-panel__actions) { margin-right: var(--erp-space-3); margin-left: var(--erp-space-3); }
.inspection-entry-panel__fields { display: grid; grid-template-columns: minmax(160px, 1fr) minmax(150px, 1fr) minmax(260px, 2fr); gap: var(--erp-space-3); }
.inspection-entry-panel__remarks { display: grid; align-content: start; gap: 6px; }
.inspection-entry-panel__sources { display: grid; gap: var(--erp-space-3); }
.inspection-entry-panel__source { overflow: hidden; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); }
.inspection-entry-panel__source > header { display: grid; grid-template-columns: 2fr 1fr 1fr; gap: 12px; padding: 9px 11px; border-bottom: 1px solid var(--erp-border); background: var(--erp-surface-soft); }
.inspection-entry-panel__source > header > div { display: grid; gap: 2px; }
.inspection-entry-panel__source > header span, .inspection-entry-panel__source > footer span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.inspection-entry-panel__source > header strong { font-size: var(--erp-font-size-caption); }
.inspection-entry-panel__split-list { overflow-x: auto; }
.inspection-entry-panel__splits { min-width: 720px; }
.inspection-entry-panel__select { width: 36px; }
.inspection-entry-panel__target-type { min-width: 190px; }
.inspection-entry-panel__quantity { width: 130px; }
.inspection-entry-panel__quantity :deep(.p-inputnumber-input) { text-align: right; }
.inspection-entry-panel__date { width: 170px; }
.inspection-entry-panel__checkbox { width: 15px; height: 15px; margin: 0; accent-color: var(--erp-accent); cursor: pointer; }
.inspection-entry-panel__checkbox:disabled { cursor: not-allowed; opacity: .45; }
.inspection-entry-panel__selection { display: flex; align-items: center; justify-content: flex-end; gap: 10px; padding: 6px 10px; border-top: 1px solid var(--erp-border); color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
.inspection-entry-panel__source > footer, .inspection-entry-panel__actions, .inspection-entry-panel__actions > div { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.inspection-entry-panel__source > footer { padding: 6px 10px; border-top: 1px solid var(--erp-border); }
.inspection-entry-panel__existing { overflow: hidden; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); }
.inspection-entry-panel__existing > header { display: flex; justify-content: space-between; padding: 8px 10px; background: var(--erp-surface-soft); }
.inspection-entry-panel__existing > div { display: flex; gap: 8px; padding: 10px; flex-wrap: wrap; }
.inspection-entry-panel__existing > div > span { display: grid; gap: 2px; padding: 6px 9px; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); }
.inspection-entry-panel__existing small { color: var(--erp-text-muted); }
.inspection-entry-panel__actions { padding: 0 var(--erp-space-3) var(--erp-space-3); }
@media (max-width: 900px) { .inspection-entry-panel__fields { grid-template-columns: repeat(2, minmax(0, 1fr)); } .inspection-entry-panel__remarks { grid-column: 1 / -1; } }
@media (max-width: 620px) { .inspection-entry-panel__fields, .inspection-entry-panel__source > header { grid-template-columns: 1fr; } .inspection-entry-panel__remarks { grid-column: auto; } .inspection-entry-panel__actions { align-items: stretch; flex-direction: column; } .inspection-entry-panel__actions > div { display: grid; width: 100%; grid-template-columns: 1fr; } }
</style>
