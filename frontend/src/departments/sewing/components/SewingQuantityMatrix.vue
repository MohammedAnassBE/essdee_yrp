<template>
	<div class="sewing-quantity-matrix">
		<div class="sewing-quantity-matrix__scroll" role="region" :aria-label="`${label} quantity matrix`" tabindex="0">
			<table>
				<caption v-if="showCaption">{{ label }} · Quantities by colour and size</caption>
				<thead><tr><th scope="col">Colour / Part</th><th v-for="size in sizes" :key="size" scope="col">{{ size }}</th><th scope="col" class="sewing-quantity-matrix__total">Total</th></tr></thead>
				<tbody>
					<tr v-for="(colour, key) in colours" :key="key">
						<th scope="row">{{ colour.colour || key }}<small v-if="colour.part">{{ colour.part }}</small><slot name="colour-actions" :colour="colour" :colour-key="key" /></th>
						<td v-for="size in sizes" :key="colour.values?.[size]?.order_detail || size">
							<template v-if="colour.values?.[size]">
								<small v-for="column in contextColumns" :key="column.key">{{ column.label }} <b>{{ format(colour.values[size][column.key]) }}</b></small>
								<label :for="`${matrixId}-${colour.values[size].order_detail}`">{{ quantityLabel }}</label>
								<input :id="`${matrixId}-${colour.values[size].order_detail}`" type="number" step="any" inputmode="decimal" :aria-label="`${colour.colour || key} ${size} ${quantityLabel}`" :aria-invalid="invalid(colour.values[size].order_detail) || undefined" :value="modelValue[colour.values[size].order_detail] ?? 0" :disabled="disabled || !editable" @input="edit(colour.values[size].order_detail, $event.target.value)" />
								<small v-if="invalid(colour.values[size].order_detail)" class="sewing-quantity-matrix__error">Use zero or a positive number.</small>
							</template>
							<span v-else aria-label="No order row">N/A</span>
						</td>
						<td class="sewing-quantity-matrix__total"><small v-for="column in contextColumns" :key="column.key">{{ column.label }} <b>{{ format(totals.colours[key].context[column.key]) }}</b></small><strong>{{ format(totals.colours[key].quantity) }}</strong></td>
					</tr>
				</tbody>
				<tfoot>
					<tr>
						<th scope="row">Total</th>
						<td v-for="size in sizes" :key="size"><small v-for="column in contextColumns" :key="column.key">{{ column.label }} <b>{{ format(totals.sizes[size].context[column.key]) }}</b></small><strong>{{ format(totals.sizes[size].quantity) }}</strong></td>
						<td class="sewing-quantity-matrix__total"><small v-for="column in contextColumns" :key="column.key">{{ column.label }} <b>{{ format(totals.grand.context[column.key]) }}</b></small><strong>{{ format(totals.grand.quantity) }}</strong></td>
					</tr>
				</tfoot>
			</table>
		</div>
	</div>
</template>

<script setup>
import { computed, useId } from "vue"
import { sewingMatrixTotals } from "../sewingQuantityTotals.js"
const props = defineProps({
	colours: { type: Object, default: () => ({}) }, primaryValues: { type: Array, default: () => [] },
	modelValue: { type: Object, default: () => ({}) }, contextColumns: { type: Array, default: () => [] },
	label: { type: String, default: "Sewing Plan" }, quantityLabel: { type: String, default: "Entry quantity" },
	disabled: Boolean, editable: { type: Boolean, default: true }, showCaption: { type: Boolean, default: true },
})
const emit = defineEmits(["update:modelValue"])
const matrixId = useId()
const sizes = computed(() => [...new Set([...props.primaryValues, ...Object.values(props.colours).flatMap(colour => Object.keys(colour.values || {}))])])
const totals = computed(() => sewingMatrixTotals(props.colours, sizes.value, props.modelValue, props.contextColumns))
function edit(identity, value) { emit("update:modelValue", { ...props.modelValue, [identity]: value }) }
function invalid(identity) { const value = props.modelValue[identity]; return value !== undefined && (!Number.isFinite(Number(value)) || Number(value) < 0) }
function format(value) { return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 3 }) }
</script>

<style scoped>
.sewing-quantity-matrix { min-width: 0; max-width: 100%; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); background: var(--erp-surface); }
.sewing-quantity-matrix__scroll { max-width: 100%; overflow: auto; overscroll-behavior-x: contain; }
table { min-width: 100%; width: max-content; border-collapse: separate; border-spacing: 0; font-size: 13px; }
caption { padding: 10px; text-align: left; color: var(--erp-text-secondary); font-weight: 650; }
th, td { min-width: 112px; padding: 9px 10px; border-top: 1px solid var(--erp-border); vertical-align: top; }
th { text-align: left; background: color-mix(in srgb, var(--erp-accent) 5%, var(--erp-surface-soft)); color: var(--erp-text-secondary); font-weight: 700; }
thead th { position: sticky; top: 0; z-index: 1; }
tbody th { min-width: 130px; max-width: 180px; overflow-wrap: anywhere; }
td { border-left: 1px solid var(--erp-border-subtle); }
tbody tr:nth-child(even) { background: color-mix(in srgb, var(--erp-accent) 2.5%, var(--erp-surface)); }
small { display: block; font-size: 11px; color: var(--erp-text-muted); line-height: 1.7; }
b { float: right; margin-left: 8px; font-variant-numeric: tabular-nums; color: var(--erp-text-secondary); }
label { display: block; font-size: 11px; font-weight: 650; margin: 6px 0 4px; }
input { width: 94px; min-height: 38px; padding: 7px 8px; border: 1px solid var(--erp-border-strong); border-radius: var(--erp-control-radius); background: var(--erp-surface); color: var(--erp-text); text-align: right; font: inherit; font-variant-numeric: tabular-nums; }
input:focus-visible, .sewing-quantity-matrix__scroll:focus-visible { outline: 3px solid var(--erp-accent-soft); outline-offset: 1px; border-color: var(--erp-accent); }
input[aria-invalid="true"] { border-color: var(--erp-danger); }
.sewing-quantity-matrix__error { color: var(--erp-danger); max-width: 110px; }
input:disabled { opacity: .65; }
tfoot th, tfoot td { background: color-mix(in srgb, var(--erp-accent) 8%, var(--erp-surface-soft)); color: var(--erp-text); font-weight: 700; border-top: 2px solid var(--erp-border-strong); }
.sewing-quantity-matrix__total { text-align: right; font-weight: 700; }
td strong { display: block; text-align: right; font-variant-numeric: tabular-nums; color: var(--erp-text); }
</style>
