<template>
	<section class="planner-order-matrix">
		<header><div><span>Size quantities</span><h3>Order Details</h3></div><Button v-if="editable" label="Add Size" icon="pi pi-plus" size="small" severity="secondary" outlined @click="addRow" /></header>
		<div v-if="rows.length" class="planner-order-table-wrap"><table><thead><tr><th>#</th><th>Size</th><th class="numeric">Order Quantity</th><th v-if="editable">Actions</th></tr></thead><tbody><tr v-for="(row, index) in rows" :key="row._row_key" class="planner-order-row"><td><span class="row-number">{{ index + 1 }}</span></td><td><InputText :model-value="row.size" :aria-label="`Size row ${index + 1}`" :disabled="!editable" fluid @update:model-value="update(index, 'size', $event)" /></td><td><InputNumber :model-value="row.qty" :aria-label="`Quantity row ${index + 1}`" :min="0" :use-grouping="false" :disabled="!editable" fluid @update:model-value="update(index, 'qty', $event)" /></td><td v-if="editable" class="row-actions"><Button icon="pi pi-trash" aria-label="Remove size" severity="danger" text rounded @click="removeRow(index)" /></td></tr></tbody><tfoot><tr><td colspan="2">Total Order Quantity</td><td class="numeric"><strong>{{ total.toLocaleString() }}</strong></td><td v-if="editable"></td></tr></tfoot></table></div>
		<div v-else class="planner-order-empty"><i class="pi pi-table"></i><strong>No size quantities</strong><span>Add at least one size. Zero-demand sizes are allowed when another size has demand.</span></div>
	</section>
</template>

<script setup>
import Button from "primevue/button"
import InputNumber from "primevue/inputnumber"
import InputText from "primevue/inputtext"
import { computed } from "vue"

const props = defineProps({ rows: { type: Array, default: () => [] }, editable: Boolean })
const emit = defineEmits(["update:rows"])
let rowSequence = 0
const total = computed(() => props.rows.reduce((sum, row) => sum + Number(row.qty || 0), 0))
function cloneRows() { return props.rows.map((row) => ({ ...row })) }
function addRow() { emit("update:rows", [...cloneRows(), { _row_key: `new-size-${++rowSequence}`, name: "", size: "", qty: 0 }]) }
function removeRow(index) { const rows = cloneRows(); rows.splice(index, 1); emit("update:rows", rows) }
function update(index, field, value) { const rows = cloneRows(); rows[index][field] = value; emit("update:rows", rows) }
</script>

<style scoped>
.planner-order-matrix { width: min(100%, 600px); min-width: 0; justify-self: start; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); overflow: hidden; }.planner-order-matrix > header { display: flex; min-height: 54px; padding: 9px 11px; align-items: center; justify-content: space-between; gap: 10px; background: var(--erp-surface-muted); border-bottom: 1px solid var(--erp-border); }.planner-order-matrix > header span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 720; letter-spacing: .04em; text-transform: uppercase; }.planner-order-matrix h3 { margin: 2px 0 0; color: var(--erp-text); font-size: var(--erp-font-size-section); }
.planner-order-table-wrap { overflow-x: auto; }
.planner-order-matrix table { width: 600px; min-width: 600px; table-layout: fixed; border-right: 1px solid var(--erp-border); border-collapse: collapse; }
.planner-order-matrix th, .planner-order-matrix td { padding: 4px 8px; text-align: left; border-right: 1px solid var(--erp-border); border-bottom: 1px solid var(--erp-border); }
.planner-order-matrix th { padding-block: 7px; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); background: var(--erp-surface); }
.planner-order-matrix th:nth-child(1) { width: 56px; }
.planner-order-matrix th:nth-child(2) { width: 256px; }
.planner-order-matrix th:nth-child(3) { width: 228px; }
.planner-order-matrix th:nth-child(4) { width: 60px; }
.planner-order-matrix th:last-child, .planner-order-matrix td:last-child { border-right: 0; }
.planner-order-matrix :deep(.p-inputtext), .planner-order-matrix :deep(.p-inputnumber-input) { min-height: var(--erp-control-height-compact); height: var(--erp-control-height-compact); padding-block: 5px; }
.planner-order-matrix :deep(.p-inputnumber) { width: 100%; }
.planner-order-matrix tfoot td { color: var(--erp-text); background: var(--erp-accent-soft); border-bottom: 0; }
.numeric { text-align: right !important; font-variant-numeric: tabular-nums; }
.row-number { display: inline-grid; width: 22px; height: 22px; place-items: center; color: var(--erp-accent); font-size: var(--erp-font-size-min); font-weight: 760; background: var(--erp-accent-soft); border-radius: 50%; }
.row-actions { width: 60px; text-align: center !important; }
.row-actions :deep(.p-button) { width: var(--erp-control-height-compact); min-width: var(--erp-control-height-compact); height: var(--erp-control-height-compact); min-height: var(--erp-control-height-compact); padding: 0; }
.planner-order-empty { display: grid; min-height: 160px; place-content: center; justify-items: center; gap: 6px; color: var(--erp-text-muted); text-align: center; }.planner-order-empty i { color: var(--erp-accent); font-size: 1.5rem; }.planner-order-empty strong { color: var(--erp-text); }
</style>
