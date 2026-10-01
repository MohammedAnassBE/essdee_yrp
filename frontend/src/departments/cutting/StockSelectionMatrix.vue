<template>
	<section class="selection-matrix">
		<header class="selection-matrix__header">
			<div><span>Available stock</span><h3>Select by item attributes</h3><p>Choose the exact attribute quantities to include in this transaction.</p></div>
			<div class="selection-matrix__summary"><strong>{{ modelValue.length }}</strong><span>selected</span></div>
		</header>

		<div v-if="groups.length" class="selection-matrix__groups">
			<article v-for="(group, groupIndex) in groups" :key="groupKey(group, groupIndex)" class="selection-matrix__group">
				<header><div><i class="pi pi-th-large"></i><strong>{{ group.primary_attribute ? `${group.primary_attribute} matrix` : "Quantity" }}</strong></div><span>{{ group.items?.length || 0 }} rows</span></header>
				<div class="selection-matrix__scroll">
					<table>
						<thead><tr><th>#</th><th>Item</th><th>Lot</th><th>Received Type</th><th v-for="attribute in group.attributes || []" :key="attribute">{{ attribute }}</th><th v-for="value in primaryValues(group)" :key="value" class="selection-matrix__number">{{ valueLabel(group, value) }}</th><th v-if="group.primary_attribute" class="selection-matrix__number">Available</th><th>UOM</th></tr></thead>
						<tbody>
							<tr v-for="(row, rowIndex) in group.items || []" :key="`${row.name}-${rowIndex}`">
								<td class="selection-matrix__index">{{ rowIndex + 1 }}</td>
								<td class="selection-matrix__item"><strong>{{ row.name }}</strong><small v-if="row.primary_attribute">{{ row.primary_attribute }}</small></td>
								<td>{{ row.lot || "—" }}</td><td>{{ row.received_type || "—" }}</td>
								<td v-for="attribute in group.attributes || []" :key="attribute"><span class="selection-matrix__attribute">{{ row.attributes?.[attribute] || "—" }}</span></td>
								<td v-for="value in primaryValues(group)" :key="value" class="selection-matrix__number">
									<label v-if="cell(row, value).selection_key" class="selection-matrix__cell" :class="{ 'selection-matrix__cell--selected': isSelected(cell(row, value).selection_key) }">
										<input type="checkbox" :checked="isSelected(cell(row, value).selection_key)" @change="toggle(cell(row, value).selection_key)" />
										<strong>{{ formatQty(cell(row, value).qty) }}</strong>
									</label>
									<span v-else class="selection-matrix__missing">—</span>
								</td>
								<td v-if="group.primary_attribute" class="selection-matrix__number selection-matrix__total">{{ formatQty(rowTotal(row)) }}</td><td>{{ row.default_uom || "—" }}</td>
							</tr>
						</tbody>
					</table>
				</div>
			</article>
		</div>
		<div v-else class="selection-matrix__empty"><i class="pi pi-inbox"></i><span>No positive stock balance is available for this Cutting Plan.</span></div>
	</section>
</template>

<script setup>
const props = defineProps({ groups: { type: Array, default: () => [] }, modelValue: { type: Array, default: () => [] } })
const emit = defineEmits(["update:modelValue"])

function primaryValues(group) { return group.primary_attribute ? (group.primary_attribute_values || []) : ["default"] }
function valueLabel(group, value) { return group.primary_attribute ? value : "Quantity" }
function cell(row, value) { return row.values?.[value] || {} }
function isSelected(key) { return props.modelValue.includes(key) }
function toggle(key) { emit("update:modelValue", isSelected(key) ? props.modelValue.filter((value) => value !== key) : [...props.modelValue, key]) }
function rowTotal(row) { return Object.values(row.values || {}).reduce((total, value) => total + Number(value?.qty || 0), 0) }
function formatQty(value) { return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 3 }) }
function groupKey(group, index) { return `${group.primary_attribute || "quantity"}-${(group.attributes || []).join("-")}-${index}` }
</script>

<style scoped>
.selection-matrix{overflow:hidden;border:1px solid #dce7e1;border-radius:11px;background:#fff}.selection-matrix__header{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:11px 13px;border-bottom:1px solid #e1eae5;background:#fbfdfc}.selection-matrix__header>div:first-child{display:grid;gap:2px}.selection-matrix__header>div:first-child>span{color:#078451;font-size:.61rem;font-weight:800;letter-spacing:.08em;text-transform:uppercase}.selection-matrix__header h3{margin:0;color:#233d30;font-size:.87rem}.selection-matrix__header p{margin:0;color:#748179;font-size:.67rem}.selection-matrix__summary{display:grid;justify-items:center;min-width:58px;padding:6px 10px;border-radius:9px;background:#e7f5ed;color:#08794a}.selection-matrix__summary strong{font-size:.9rem}.selection-matrix__summary span{font-size:.59rem;text-transform:uppercase}.selection-matrix__groups{display:grid;gap:10px;max-height:470px;padding:10px;overflow:auto;background:#f7faf8}.selection-matrix__group{overflow:hidden;border:1px solid #dce7e1;border-radius:9px;background:#fff}.selection-matrix__group>header{display:flex;align-items:center;justify-content:space-between;padding:8px 10px;border-bottom:1px solid #e3ebe7}.selection-matrix__group>header>div{display:flex;align-items:center;gap:7px}.selection-matrix__group>header i{color:#0a8752;font-size:.72rem}.selection-matrix__group>header strong{color:#2a4034;font-size:.73rem}.selection-matrix__group>header span{color:#77847d;font-size:.63rem}.selection-matrix__scroll{overflow:auto}.selection-matrix table{width:100%;min-width:840px;border-collapse:separate;border-spacing:0;font-size:.71rem}.selection-matrix th{position:sticky;z-index:1;top:0;padding:8px 9px;border-bottom:1px solid #dfe8e3;background:#eef5f1;color:#58675f;font-size:.6rem;text-align:left;text-transform:uppercase;white-space:nowrap}.selection-matrix td{padding:8px 9px;border-bottom:1px solid #e7edea;color:#374a40;vertical-align:middle;white-space:nowrap}.selection-matrix tbody tr:last-child td{border-bottom:0}.selection-matrix__index{color:#88948d!important;text-align:center}.selection-matrix__item{display:grid;gap:1px;min-width:170px;white-space:normal!important}.selection-matrix__item strong{color:#20382c;font-size:.72rem}.selection-matrix__item small{color:#77847d;font-size:.59rem}.selection-matrix__attribute{display:inline-flex;padding:3px 7px;border:1px solid #dce8e1;border-radius:6px;background:#f7faf8;font-size:.66rem}.selection-matrix__number{text-align:right!important;font-variant-numeric:tabular-nums}.selection-matrix__cell{display:inline-flex;min-width:66px;align-items:center;justify-content:flex-end;gap:6px;padding:5px 7px;border:1px solid #d8e4dd;border-radius:7px;background:#fff;cursor:pointer}.selection-matrix__cell:hover,.selection-matrix__cell--selected{border-color:#70bd98;background:#edf9f3;color:#087a4a;box-shadow:0 0 0 1px rgb(11 143 85 / 7%)}.selection-matrix__cell input{width:13px;height:13px;margin:0;accent-color:#0b8f55}.selection-matrix__cell strong{font-size:.7rem}.selection-matrix__missing{color:#a0aaa4}.selection-matrix__total{color:#087a4a!important;font-weight:800}.selection-matrix__empty{display:flex;align-items:center;justify-content:center;gap:8px;padding:34px;color:#748179;font-size:.75rem}@media(max-width:700px){.selection-matrix__header{align-items:flex-start;flex-direction:column}.selection-matrix__summary{grid-auto-flow:column;justify-content:start;gap:5px}}
</style>
