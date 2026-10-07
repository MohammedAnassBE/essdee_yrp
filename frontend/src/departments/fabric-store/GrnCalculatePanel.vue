<template>
	<section class="grn-calculate-panel" aria-label="Goods Received Note calculation">
		<header class="grn-calculate-panel__header">
			<div><span>Saved Work Order calculation</span><h2>Calculate receivables</h2></div>
			<Button icon="pi pi-times" severity="secondary" text rounded aria-label="Close calculation" :disabled="Boolean(acting)" @click="emit('close')" />
		</header>

		<div class="grn-calculate-panel__toolbar">
			<div class="grn-calculate-panel__received-type">
				<LinkField v-model="receivedType" label="Received Type *" doctype="YRP Received Type" :show-open-button="false" :disabled="Boolean(acting)" />
			</div>
			<div class="grn-calculate-panel__selection-actions">
				<Button label="Select all" severity="secondary" outlined size="small" :disabled="Boolean(acting)" @click="setAll(true)" />
				<Button label="Unselect all" severity="secondary" text size="small" :disabled="Boolean(acting)" @click="setAll(false)" />
			</div>
		</div>

		<div class="erp-table-wrap grn-calculate-panel__matrix" role="region" tabindex="0" aria-label="Goods Received Note receivable quantities">
			<table class="erp-data-table">
				<thead>
					<tr>
						<th class="grn-calculate-panel__select">Use</th>
						<th v-for="attribute in context.display_attributes || []" :key="attribute">{{ attribute }}</th>
						<th v-for="value in primaryValues" :key="value" class="erp-number">{{ quantityHeading(value) }}</th>
						<th class="erp-number">Row total</th>
					</tr>
				</thead>
				<tbody>
					<tr v-for="(row, rowIndex) in rows" :key="rowIndex" :class="{ 'grn-calculate-panel__row--inactive': !row.selected }">
						<td class="grn-calculate-panel__select"><Checkbox v-model="row.selected" binary :input-id="`grn-calculate-row-${rowIndex}`" :aria-label="`Use receipt calculation row ${rowIndex + 1}`" :disabled="Boolean(acting)" /></td>
						<td v-for="attribute in context.display_attributes || []" :key="attribute">{{ row.attributes?.[attribute] || "—" }}</td>
						<td v-for="value in primaryValues" :key="value" class="erp-number grn-calculate-panel__quantity">
								<InputNumber
									v-if="row.values?.[value]"
									v-model="row.values[value].qty"
									:aria-label="quantityInputLabel(row, rowIndex, value)"
									:min="0"
									:max="Number(row.values[value].available_qty || 0)"
									:max-fraction-digits="3"
									:disabled="Boolean(acting) || !row.selected"
									fluid
								/>
								<small v-if="row.values?.[value]">Available {{ formatQty(row.values[value].available_qty) }}</small>
								<span v-else>—</span>
						</td>
						<td class="erp-number grn-calculate-panel__row-total">{{ formatQty(rowTotal(row)) }}</td>
					</tr>
				</tbody>
				<tfoot>
					<tr>
						<th :colspan="1 + (context.display_attributes || []).length">Column totals</th>
						<th v-for="value in primaryValues" :key="value" class="erp-number">{{ formatQty(columnTotal(value)) }}</th>
						<th class="erp-number grn-calculate-panel__grand-total"><span>Grand total</span><strong>{{ formatQty(grandTotal) }}</strong></th>
					</tr>
				</tfoot>
			</table>
		</div>

		<footer>
			<Button label="Close" severity="secondary" text :disabled="Boolean(acting)" @click="emit('close')" />
			<Button label="Apply Calculation" icon="pi pi-calculator" :loading="acting === 'calculate'" :disabled="!canApply" @click="apply" />
		</footer>
	</section>
	<DocumentErrorDialog :message="error" title="Goods Received Note could not be calculated" />
</template>

<script setup>
import Button from "primevue/button"
import Checkbox from "primevue/checkbox"
import InputNumber from "primevue/inputnumber"
import { computed, ref, watch } from "vue"

import LinkField from "../../components/common/LinkField.vue"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"

const props = defineProps({
	context: { type: Object, default: () => ({}) },
	acting: { type: String, default: "" },
	error: { type: String, default: "" },
})
const emit = defineEmits(["apply", "close"])

const receivedType = ref("")
const rows = ref([])
const primaryValues = computed(() => props.context.primary_values?.length ? props.context.primary_values : ["default"])
const grandTotal = computed(() => primaryValues.value.reduce((total, value) => total + columnTotal(value), 0))
const canApply = computed(() => Boolean(receivedType.value && grandTotal.value > 0 && !props.acting))

watch(() => props.context, (context) => {
	receivedType.value = context.default_received_type || ""
	rows.value = clone(context.matrix_rows || []).map((row) => ({ ...row, selected: true }))
}, { immediate: true })

function setAll(selected) { for (const row of rows.value) row.selected = selected }
function rowTotal(row) {
	if (!row.selected) return 0
	return primaryValues.value.reduce((total, value) => total + Number(row.values?.[value]?.qty || 0), 0)
}
function columnTotal(value) { return rows.value.reduce((total, row) => total + (row.selected ? Number(row.values?.[value]?.qty || 0) : 0), 0) }
function quantityHeading(value) { return value === "default" || !props.context.primary_attribute ? "Receive" : value }
function quantityInputLabel(row, rowIndex, value) {
	const attributes = (props.context.display_attributes || []).map((attribute) => row.attributes?.[attribute]).filter(Boolean).join(", ")
	const quantity = value === "default" ? "receive quantity" : `${value} receive quantity`
	return `${quantity} for ${attributes || `row ${rowIndex + 1}`}`
}
function formatQty(value) { return Number(value || 0).toLocaleString("en-IN", { maximumFractionDigits: 3 }) }
function apply() {
	const selectedRows = []
	for (const row of rows.value) {
		if (!row.selected) continue
		for (const value of primaryValues.value) {
			const cell = row.values?.[value]
			if (cell?.source_row) selectedRows.push({ source_row: cell.source_row, qty: Number(cell.qty || 0) })
		}
	}
	emit("apply", { rows: selectedRows, received_type: receivedType.value })
}
function clone(value) { return JSON.parse(JSON.stringify(value || [])) }
</script>

<style scoped>
.grn-calculate-panel { display: grid; overflow: hidden; gap: var(--erp-space-3); border: 1px solid color-mix(in srgb, var(--erp-accent) 20%, var(--erp-border)); border-radius: var(--erp-panel-radius); background: var(--erp-surface); box-shadow: 0 7px 20px rgb(28 61 45 / 4%); }
.grn-calculate-panel__header { display: flex; min-height: 48px; align-items: center; justify-content: space-between; gap: 12px; padding: 8px 12px; border-bottom: 1px solid var(--erp-border); border-left: 3px solid var(--erp-accent); background: color-mix(in srgb, var(--erp-accent-soft) 72%, white); }
.grn-calculate-panel__header > div { display: grid; gap: 2px; }
.grn-calculate-panel__header span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 750; letter-spacing: .035em; text-transform: uppercase; }
.grn-calculate-panel__header h2 { margin: 0; font-size: var(--erp-font-size-section); }
.grn-calculate-panel > :not(.grn-calculate-panel__header, footer) { margin-right: var(--erp-space-3); margin-left: var(--erp-space-3); }
.grn-calculate-panel__toolbar, .grn-calculate-panel__selection-actions, .grn-calculate-panel footer { display: flex; align-items: end; justify-content: space-between; gap: 8px; }
.grn-calculate-panel__received-type { width: min(320px, 100%); }
.grn-calculate-panel__matrix { border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); }
.grn-calculate-panel__matrix table { min-width: 780px; }
.grn-calculate-panel__select { width: 54px; text-align: center; }
.grn-calculate-panel__quantity { min-width: 112px; }
.grn-calculate-panel__quantity :deep(.p-inputnumber-input) { height: 32px; padding: 5px 8px; text-align: right; }
.grn-calculate-panel__quantity small { display: block; margin-top: 3px; color: #765b20; font-size: var(--erp-font-size-min); }
.grn-calculate-panel__row--inactive { opacity: .58; }
.grn-calculate-panel__row-total { color: var(--erp-accent); font-weight: 800; }
.grn-calculate-panel__grand-total span { display: block; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.grn-calculate-panel__grand-total strong { color: var(--erp-accent); font-size: 17px; }
.grn-calculate-panel footer { padding: 0 var(--erp-space-3) var(--erp-space-3); justify-content: flex-end; }
@media (max-width: 620px) { .grn-calculate-panel__toolbar { align-items: stretch; flex-direction: column; } .grn-calculate-panel__selection-actions { justify-content: flex-start; } }
@media (max-width: 1024px), (pointer: coarse) { .grn-calculate-panel :deep(.p-button) { min-width: 44px; min-height: 44px; } .grn-calculate-panel__quantity :deep(.p-inputnumber-input) { height: 44px; min-height: 44px; } }
</style>
