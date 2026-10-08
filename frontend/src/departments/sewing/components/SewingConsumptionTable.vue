<template>
	<div class="sewing-consumption-table">
		<div class="sewing-consumption-table__scroll" role="region" :aria-label="`${label} consumption mapping`" tabindex="0">
			<table>
				<caption>{{ label }}<span v-if="uom"> · UOM {{ uom }}</span></caption>
				<thead><tr><th v-for="column in columns" :key="column" scope="col">{{ column }}</th><th v-if="showBom" scope="col">BOM quantity</th><th scope="col">{{ editableField === 'quantity' ? 'Consumption quantity' : editableField }}</th></tr></thead>
				<tbody><tr v-for="(row, index) in rows" :key="index">
					<td v-for="column in columns" :key="column">{{ display(valuesInRow ? row.values?.[column] : row[column]) }}</td>
					<td v-if="showBom" class="sewing-consumption-table__number">{{ display(row.item_bom_qty) }}</td>
					<td><input v-if="Object.hasOwn(row, editableField)" type="number" step="any" min="0" inputmode="decimal" :aria-label="`${label} row ${valuesInRow ? row.index : index + 1} ${editableField}`" :value="row[editableField]" :disabled="disabled" :aria-invalid="invalid(row[editableField]) || undefined" @input="emit('edit', { index, value: $event.target.value === '' ? '' : Number($event.target.value) })" /><span v-else>N/A</span><small v-if="Object.hasOwn(row, editableField) && invalid(row[editableField])">Use zero or a positive number.</small></td>
				</tr></tbody>
			</table>
		</div>
	</div>
</template>

<script setup>
defineProps({ label: { type: String, required: true }, uom: { type: String, default: "" }, columns: { type: Array, default: () => [] }, rows: { type: Array, default: () => [] }, editableField: { type: String, default: "quantity" }, showBom: Boolean, valuesInRow: Boolean, disabled: Boolean })
const emit = defineEmits(["edit"])
function display(value) { return value === null || value === undefined || value === "" ? "N/A" : typeof value === "object" ? JSON.stringify(value) : value }
function invalid(value) { return value === "" || !Number.isFinite(Number(value)) || Number(value) < 0 }
</script>

<style scoped>
.sewing-consumption-table { min-width: 0; max-width: 100%; margin-bottom: 14px; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); background: var(--erp-surface); }
.sewing-consumption-table__scroll { max-width: 100%; overflow: auto; overscroll-behavior-x: contain; }
table { min-width: 100%; width: max-content; border-collapse: collapse; font-size: var(--erp-font-size-caption); }
caption { text-align: left; padding: 10px; font-weight: 650; color: var(--erp-text-secondary); }
th, td { min-width: 112px; max-width: 220px; padding: 9px 10px; border-top: 1px solid var(--erp-border); text-align: left; overflow-wrap: anywhere; }
th { background: var(--erp-surface-soft); color: var(--erp-text-secondary); }
td { color: var(--erp-text); border-right: 1px solid var(--erp-border-subtle); }
.sewing-consumption-table__number { text-align: right; font-variant-numeric: tabular-nums; }
input { width: 110px; min-height: 38px; padding: 7px 8px; border: 1px solid var(--erp-border-strong); border-radius: var(--erp-control-radius); background: var(--erp-surface); color: var(--erp-text); text-align: right; font: inherit; font-variant-numeric: tabular-nums; }
input:focus-visible, .sewing-consumption-table__scroll:focus-visible { outline: 3px solid var(--erp-accent-soft); outline-offset: 1px; border-color: var(--erp-accent); }
input[aria-invalid="true"] { border-color: var(--erp-danger); }
input:disabled { opacity: .65; }
small { display: block; max-width: 112px; margin-top: 4px; color: var(--erp-danger); font-size: 11px; }
</style>
