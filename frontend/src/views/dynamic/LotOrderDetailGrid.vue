<template>
	<div class="lot-od-grid">
		<div v-if="!blocks.length" class="esd-empty">
			<i class="pi pi-table" />
			<p class="esd-empty__text">No order details yet — they are generated from the order items on save.</p>
		</div>
		<div v-for="(blk, bi) in blocks" :key="bi" class="lot-table-wrap">
			<table v-if="(blk.items || []).length" class="esd-table lot-table">
				<thead>
					<tr>
						<th>#</th>
						<th v-for="attr in blk.attributes || []" :key="'h-' + attr">{{ attr }}</th>
						<th v-for="pv in blk.primary_attribute_values || []" :key="'p-' + pv">{{ pv }}</th>
					</tr>
				</thead>
				<tbody>
					<tr v-for="(row, ri) in blk.items" :key="ri">
						<td>{{ ri + 1 }}</td>
						<td v-for="attr in blk.attributes || []" :key="'v-' + attr">{{ row.attributes?.[attr] }}</td>
						<td v-for="pv in blk.primary_attribute_values || []" :key="'q-' + pv" class="lot-od-cell">
							<InputNumber
								v-if="!readonly && row.values?.[pv]"
								v-model="row.values[pv].qty"
								:min="0"
								:maxFractionDigits="3"
								class="lot-od-input"
								@update:modelValue="emit('change')"
							/>
							<span v-else-if="row.values?.[pv] && Number(row.values[pv].qty)">{{ row.values[pv].qty }}</span>
							<span v-else class="lot-od-none">—</span>
						</td>
					</tr>
				</tbody>
			</table>
		</div>
	</div>
</template>

<script setup>
/**
 * Lot "Order Details" grid — /web mirror of the Desk Vue island
 * apps/yrp/yrp/public/js/CuttingPlan/components/CutPlanItems.vue.
 *
 * Data contract (byte-faithful): loadData(blocks) receives the grouped
 * structure from Lot.fetch_order_item_details / __onload.order_item_details —
 * an array of { primary_attribute, primary_attribute_values, attributes
 * (names), items: [{ attributes:{name:value}, values:{<size>:{qty,…}} }] }.
 * getItems() returns the (possibly qty-edited) blocks — serialized by the
 * parent into payload.order_item_details, which save_order_item_details
 * merges against the loaded lot_order_details rows (preserving cut/stich/pack).
 * qty cells are editable in edit mode (Lot is never submittable; the Desk
 * gates on docstatus which is always 0 here — the parent gates on view/edit).
 */
import { ref, watch } from "vue"
import InputNumber from "primevue/inputnumber"

const props = defineProps({
	initialData: { type: Array, default: null },
	readonly: { type: Boolean, default: false },
})
const emit = defineEmits(["change"])

const blocks = ref([])

function loadData(x) {
	blocks.value = Array.isArray(x) ? x : []
}
function getItems() {
	return JSON.parse(JSON.stringify(blocks.value))
}
function hasItems() {
	return blocks.value.some((b) => (b.items || []).length)
}
watch(() => props.initialData, (v) => { if (v != null) loadData(v) }, { immediate: true })

defineExpose({ loadData, getItems, hasItems })
</script>

<style scoped>
.lot-od-grid {
	display: flex;
	flex-direction: column;
	gap: 12px;
}
.lot-table-wrap {
	overflow-x: auto;
}
.lot-table {
	width: 100%;
	border-collapse: collapse;
	font-size: 12.5px;
}
.lot-table th,
.lot-table td {
	border: 1px solid var(--esd-line);
	padding: 6px 10px;
	text-align: left;
	white-space: nowrap;
}
.lot-table th {
	background: var(--esd-accent-50);
	color: var(--esd-accent-700);
	font-size: 11px;
	text-transform: uppercase;
	letter-spacing: 0.04em;
}
.lot-od-input {
	max-width: 110px;
}
.lot-od-none {
	color: var(--esd-muted);
}
</style>
