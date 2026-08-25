<template>
	<div class="essdee-ppo-entry">
		<div class="entry-card">
			<div class="entry-heading">{{ __("Total Order Quantity") }}</div>
			<div class="table-responsive">
				<table class="table table-bordered entry-table">
					<thead>
						<tr>
							<th>{{ primary_attribute || __("Size") }}</th>
							<th v-for="value in primary_values" :key="value">{{ value }}</th>
							<th>{{ __("Total") }}</th>
						</tr>
					</thead>
					<tbody>
						<tr>
							<th>{{ __("Qty") }}</th>
							<td v-for="value in primary_values" :key="`qty-${value}`">
								<input
									v-model.number="items[value].qty"
									class="form-control input-sm"
									type="number"
									min="0"
									step="any"
									:disabled="!editable"
									@input="mark_dirty"
								/>
							</td>
							<td class="total-cell">{{ total_quantity }}</td>
						</tr>
						<tr>
							<th>{{ __("Ratio") }}</th>
							<td v-for="value in primary_values" :key="`ratio-${value}`">
								<input
									v-model.number="items[value].ratio"
									class="form-control input-sm"
									type="number"
									min="0"
									step="any"
									:disabled="!editable"
									@input="mark_dirty"
								/>
							</td>
							<td></td>
						</tr>
						<tr>
							<th>{{ __("Wholesale Price (Piece)") }}</th>
							<td v-for="value in primary_values" :key="`wholesale-${value}`">
								<input
									:value="display_number(items[value].wholesale)"
									class="form-control input-sm"
									type="number"
									disabled
								/>
							</td>
							<td></td>
						</tr>
						<tr>
							<th>{{ __("Retail Price (Piece)") }}</th>
							<td v-for="value in primary_values" :key="`retail-${value}`">
								<input
									:value="display_number(items[value].retail)"
									class="form-control input-sm"
									type="number"
									disabled
								/>
							</td>
							<td></td>
						</tr>
						<tr>
							<th>{{ __("MRP (Piece)") }}</th>
							<td v-for="value in primary_values" :key="`mrp-${value}`">
								<input
									v-model.number="items[value].mrp"
									class="form-control input-sm"
									type="number"
									min="0"
									step="any"
									:disabled="!editable"
									@input="mark_dirty"
								/>
							</td>
							<td></td>
						</tr>
					</tbody>
				</table>
			</div>
		</div>
	</div>
</template>

<script setup>
import { computed, ref } from "vue";

const primary_attribute = ref("");
const primary_values = ref([]);
const items = ref({});
const editable = ref(false);
const item_name = ref("");

const total_quantity = computed(() =>
	primary_values.value.reduce(
		(total, value) => total + Number((items.value[value] || {}).qty || 0),
		0
	)
);

function __(message) {
	return window.__(message);
}

function mark_dirty() {
	if (editable.value && window.cur_frm && !cur_frm.is_dirty()) {
		cur_frm.dirty();
	}
}

function display_number(value) {
	return Number(value || 0);
}

function load_data(context, can_edit = false) {
	const payload = JSON.parse(JSON.stringify(context || {}));
	primary_attribute.value = payload.primary_attribute || "";
	primary_values.value = payload.primary_values || [];
	item_name.value = payload.item || (window.cur_frm && cur_frm.doc.item) || "";
	editable.value = Boolean(can_edit);
	items.value = {};

	primary_values.value.forEach((value) => {
		const row = (payload.items || {})[value] || {};
		items.value[value] = {
			qty: Number(row.qty || 0),
			ratio: Number(row.ratio || 0),
			mrp: Number(row.mrp || 0),
			wholesale: Number(row.wholesale || 0),
			retail: Number(row.retail || 0),
		};
	});
}

function set_edit(value) {
	editable.value = Boolean(value);
}

function get_final_output() {
	if (!item_name.value || !primary_attribute.value) return [];

	const entries = [];
	primary_values.value.forEach((value) => {
		const row = items.value[value] || {};
		const qty = Number(row.qty || 0);
		if (qty <= 0) return;
		entries.push({
			attributes: { [primary_attribute.value]: value },
			qty,
			ratio: Number(row.ratio || 0),
			mrp: Number(row.mrp || 0),
			wholesale: Number(row.wholesale || 0),
			retail: Number(row.retail || 0),
		});
	});

	return entries.length ? [{ item: item_name.value, entries }] : [];
}

defineExpose({ get_final_output, load_data, set_edit });
</script>

<style scoped>
.essdee-ppo-entry {
	padding: 8px 0;
}

.entry-card {
	background: var(--card-bg, #fff);
	border: 1px solid var(--border-color, #d1d8dd);
	border-radius: 8px;
	overflow: hidden;
}

.entry-heading {
	background: var(--subtle-fg, #f7fafc);
	border-bottom: 1px solid var(--border-color, #d1d8dd);
	font-size: 14px;
	font-weight: 700;
	padding: 12px 15px;
}

.entry-table {
	margin: 0;
	min-width: 720px;
	text-align: center;
}

.entry-table th,
.entry-table td {
	padding: 8px;
	vertical-align: middle;
}

.entry-table th:first-child {
	min-width: 155px;
	text-align: left;
}

.entry-table input {
	margin: auto;
	max-width: 90px;
	text-align: center;
}

.total-cell {
	font-weight: 700;
}

</style>
