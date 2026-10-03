<!-- Essdee Lot order-detail editor; intentionally not part of base YRP. -->
<template>
	<section class="order-detail">
		<div class="order-detail__header">
			<div>
				<div class="order-detail__title">{{ __("Process quantities") }}</div>
				<div class="order-detail__hint">
					{{ editable ? __("Adjust the size-wise quantities used by the downstream production plan.") : __("Size-wise quantities used by the downstream production plan.") }}
				</div>
			</div>
			<span v-if="rowCount" class="order-detail__badge">{{ rowCount }} {{ __("combinations") }}</span>
		</div>

		<div v-if="!rowCount" class="order-detail__empty">
			<div class="order-detail__empty-title">{{ __("No process quantities calculated") }}</div>
			<div>{{ __("Use Calculate Order Items after entering the Lot's order quantities.") }}</div>
		</div>

		<div v-for="(group, groupIndex) in groups" :key="groupIndex" class="order-detail__group">
			<div class="order-detail__table-wrap">
				<table class="order-detail__table">
					<thead>
						<tr>
							<th class="order-detail__index">#</th>
							<th v-for="attribute in group.attributes || []" :key="attribute">{{ attribute }}</th>
							<th v-for="value in group.primary_attribute_values || []" :key="value" class="order-detail__number">{{ value }}</th>
							<th class="order-detail__number">{{ __("Total") }}</th>
						</tr>
					</thead>
					<tbody>
						<tr v-for="(row, rowIndex) in group.items || []" :key="rowIndex">
							<td class="order-detail__index">{{ rowIndex + 1 }}</td>
							<td v-for="attribute in group.attributes || []" :key="attribute">
								<span class="order-detail__attribute">{{ row.attributes?.[attribute] || "—" }}</span>
								<span v-if="majorColourNote(row, attribute)" class="order-detail__note">
									{{ majorColourNote(row, attribute) }}
								</span>
							</td>
							<td v-for="value in group.primary_attribute_values || []" :key="value" class="order-detail__number">
								<input
									v-if="editable"
									v-model.number="row.values[value].qty"
									type="number"
									min="0"
									step="1"
									class="order-detail__input"
									@change="markDirty"
								/>
								<span v-else>{{ displayQuantity(row.values?.[value]?.qty) }}</span>
							</td>
							<td class="order-detail__number order-detail__total">{{ rowTotal(row, group) }}</td>
						</tr>
					</tbody>
					<tfoot v-if="(group.items || []).length > 1">
						<tr>
							<th :colspan="1 + (group.attributes || []).length">{{ __("Total") }}</th>
							<th v-for="value in group.primary_attribute_values || []" :key="value" class="order-detail__number">
								{{ columnTotal(group, value) }}
							</th>
							<th class="order-detail__number">{{ groupTotal(group) }}</th>
						</tr>
					</tfoot>
				</table>
			</div>
		</div>
	</section>
</template>

<script setup>
import { computed, ref } from "vue";

const groups = ref([]);
const docstatus = ref(0);

const editable = computed(() => docstatus.value === 0 && !cur_frm.doc.is_transferred);
const rowCount = computed(() => groups.value.reduce((total, group) => total + (group.items || []).length, 0));

function load_data(item) {
	docstatus.value = Number(cur_frm.doc.docstatus || 0);
	groups.value = item || [];
	for (const group of groups.value) {
		for (const row of group.items || []) {
			row.values = row.values || {};
			for (const value of group.primary_attribute_values || []) {
				row.values[value] = row.values[value] || { qty: 0 };
			}
		}
	}
}

function displayQuantity(value) {
	const quantity = Number(value || 0);
	return quantity ? quantity : "—";
}

function rowTotal(row, group) {
	return (group.primary_attribute_values || []).reduce((sum, value) => sum + Number(row.values?.[value]?.qty || 0), 0);
}

function columnTotal(group, value) {
	return (group.items || []).reduce((sum, row) => sum + Number(row.values?.[value]?.qty || 0), 0);
}

function groupTotal(group) {
	return (group.items || []).reduce((sum, row) => sum + rowTotal(row, group), 0);
}

function majorColourNote(row, attribute) {
	if (attribute !== "Colour" || !row.is_set_item || row.attributes?.[row.set_attr] === row.major_attr_value) return "";
	return row.item_keys?.major_colour ? `(${row.item_keys.major_colour})` : "";
}

function markDirty() {
	cur_frm.dirty();
}

function get_items() {
	return groups.value;
}

function update_docstatus() {
	docstatus.value = 1;
}

defineExpose({ load_data, get_items, update_docstatus });
</script>

<style scoped>
.order-detail { border: 1px solid var(--border-color); border-radius: 8px; overflow: hidden; background: var(--card-bg, var(--fg-color)); }
.order-detail__header { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 14px 16px; background: var(--subtle-fg); border-bottom: 1px solid var(--border-color); }
.order-detail__title { font-weight: 600; }
.order-detail__hint, .order-detail__empty { color: var(--text-muted); font-size: 12px; }
.order-detail__badge { padding: 3px 8px; border-radius: 999px; background: var(--control-bg); color: var(--text-muted); font-size: 11px; }
.order-detail__empty { padding: 32px 20px; text-align: center; }
.order-detail__empty-title { color: var(--text-color); font-size: 13px; font-weight: 600; margin-bottom: 4px; }
.order-detail__group + .order-detail__group { border-top: 1px solid var(--border-color); }
.order-detail__table-wrap { overflow-x: auto; }
.order-detail__table { width: 100%; min-width: 720px; border-collapse: collapse; font-size: 12px; }
.order-detail__table th, .order-detail__table td { padding: 8px 10px; border-right: 1px solid var(--border-color); border-bottom: 1px solid var(--border-color); vertical-align: middle; }
.order-detail__table th { background: var(--subtle-fg); color: var(--text-muted); font-size: 11px; font-weight: 600; text-align: left; white-space: nowrap; }
.order-detail__table th:last-child, .order-detail__table td:last-child { border-right: 0; }
.order-detail__table tbody tr:last-child td { border-bottom: 0; }
.order-detail__table tfoot th { border-top: 1px solid var(--border-color); border-bottom: 0; color: var(--text-color); }
.order-detail__index { width: 42px; text-align: center !important; color: var(--text-muted); }
.order-detail__number { text-align: right !important; font-variant-numeric: tabular-nums; }
.order-detail__total { font-weight: 600; background: var(--subtle-fg); }
.order-detail__attribute { display: inline-flex; padding: 2px 7px; border-radius: 999px; background: var(--control-bg); white-space: nowrap; }
.order-detail__note { margin-left: 4px; color: var(--text-muted); font-size: 10px; }
.order-detail__input { width: 74px; padding: 5px 7px; border: 1px solid var(--border-color); border-radius: 5px; background: var(--control-bg, var(--fg-color)); text-align: right; outline: none; }
.order-detail__input:hover { border-color: var(--gray-400); }
.order-detail__input:focus { border-color: var(--primary); box-shadow: 0 0 0 2px var(--gray-100); }
</style>
