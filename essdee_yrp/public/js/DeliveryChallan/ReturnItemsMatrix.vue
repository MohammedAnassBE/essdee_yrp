<template>
	<div ref="root" class="essdee-dc-return">
		<div v-if="hasReceivedType" class="received-type-control mb-3"></div>
		<div class="table-responsive">
			<table class="table table-sm table-bordered">
				<thead>
					<tr>
						<th>
							<input type="checkbox" @change="selectAll($event.target.checked)" />
						</th>
						<th>{{ __("Item Variant") }}</th>
						<th>{{ __("DC Qty") }}</th>
						<th>{{ __("Consumed") }}</th>
						<th>{{ __("Returned") }}</th>
						<th>{{ __("Returnable") }}</th>
						<th style="min-width: 130px">{{ __("Return Qty") }}</th>
					</tr>
				</thead>
				<tbody>
					<tr v-for="(row, index) in items" :key="row.delivery_challan_item">
						<td>
							<input
								type="checkbox"
								:checked="Number(row.return_quantity) > 0"
								@change="selectRow(row, $event.target.checked)"
							/>
						</td>
						<td>
							<strong>{{ row.item_variant }}</strong>
							<div class="text-muted small">{{ row.uom || "" }}</div>
						</td>
						<td>{{ format(row.delivered_quantity) }}</td>
						<td>{{ format(row.consumed_quantity) }}</td>
						<td>{{ format(row.already_returned) }}</td>
						<td>{{ format(row.returnable_quantity) }}</td>
						<td>
							<input
								v-model.number="row.return_quantity"
								class="form-control input-sm"
								type="number"
								min="0"
								:max="row.returnable_quantity"
								step="0.001"
							/>
						</td>
					</tr>
				</tbody>
			</table>
		</div>
	</div>
</template>

<script setup>
import { nextTick, ref } from "vue";

const root = ref(null);
const items = ref([]);
const hasReceivedType = ref(false);
const defaultReceivedType = ref("");
let receivedTypeControl = null;

function __(message, replace) {
	return frappe._ ? frappe._(message, replace) : message;
}

async function load_data(data) {
	items.value = JSON.parse(JSON.stringify(data?.items || []));
	hasReceivedType.value = Boolean(data?.has_received_type);
	defaultReceivedType.value = data?.default_received_type || "";
	await nextTick();
	if (!hasReceivedType.value || !root.value) return;
	const parent = $(root.value).find(".received-type-control");
	parent.empty();
	receivedTypeControl = frappe.ui.form.make_control({
		parent,
		df: {
			fieldname: "received_type",
			fieldtype: "Link",
			options: "Received Type",
			label: __("Return Received Type"),
			reqd: 1,
		},
		render_input: true,
	});
	await receivedTypeControl.set_value(defaultReceivedType.value);
}

function selectRow(row, checked) {
	row.return_quantity = checked ? Number(row.returnable_quantity || 0) : 0;
}

function selectAll(checked) {
	for (const row of items.value) selectRow(row, checked);
}

function format(value) {
	return Number(value || 0).toLocaleString(undefined, {maximumFractionDigits: 3});
}

function get_data() {
	const selected = items.value.filter((row) => Number(row.return_quantity || 0) > 0);
	if (!selected.length) frappe.throw(__("Enter at least one Return Qty."));
	for (const row of selected) {
		if (Number(row.return_quantity) > Number(row.returnable_quantity) + 0.0001) {
			frappe.throw(__("Return Qty for {0} exceeds the returnable quantity.", [row.item_variant]));
		}
	}
	const receivedType = receivedTypeControl?.get_value() || defaultReceivedType.value;
	if (hasReceivedType.value && !receivedType) {
		frappe.throw(__("Select Return Received Type."));
	}
	return {items: selected, received_type: receivedType};
}

defineExpose({ load_data, get_data });
</script>
