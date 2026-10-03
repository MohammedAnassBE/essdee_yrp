<template>
	<section class="lot-order" ref="root">
		<div v-if="definition" class="lot-order__card">
			<div class="lot-order__header">
				<div>
					<div class="lot-order__title">{{ __("Order quantities") }}</div>
					<div class="lot-order__hint">
						{{ __("Enter the garment quantity, ratio and MRP for each attribute combination.") }}
					</div>
				</div>
				<button
					v-if="canEdit && !showParameters"
					type="button"
					class="btn btn-default btn-sm"
					@click="openEditor()"
				>
					{{ rows.length ? __("Add combination") : __("Enter quantities") }}
				</button>
			</div>

			<div v-if="rows.length" class="lot-order__table-wrap">
				<table class="lot-order__table">
					<thead>
						<tr>
							<th class="lot-order__number">#</th>
							<th v-for="attribute in finalAttributes" :key="attribute">{{ attribute }}</th>
							<th v-if="primaryAttribute" v-for="value in primaryValues" :key="value">
								{{ value }}
							</th>
							<template v-else>
								<th>{{ __("Quantity") }}</th>
								<th>{{ __("Ratio") }}</th>
								<th>{{ __("MRP") }}</th>
							</template>
							<th v-if="canEdit" class="lot-order__actions"></th>
						</tr>
					</thead>
					<tbody>
						<tr v-for="(row, index) in rows" :key="index">
							<td class="lot-order__number">{{ index + 1 }}</td>
							<td v-for="attribute in finalAttributes" :key="attribute">
								<span class="lot-order__attribute">{{ row.attributes?.[attribute] || "—" }}</span>
							</td>
							<td v-if="primaryAttribute" v-for="value in primaryValues" :key="value">
								<div class="lot-order__qty">{{ formatNumber(row.values?.[value]?.qty) }}</div>
								<div class="lot-order__meta">
									{{ __("Ratio") }} {{ formatNumber(row.values?.[value]?.ratio) }}
									<span>·</span>
									{{ __("MRP") }} {{ formatNumber(row.values?.[value]?.mrp) }}
								</div>
							</td>
							<template v-else>
								<td class="lot-order__qty">{{ formatNumber(row.values?.qty) }}</td>
								<td>{{ formatNumber(row.values?.ratio) }}</td>
								<td>{{ formatNumber(row.values?.mrp) }}</td>
							</template>
							<td v-if="canEdit" class="lot-order__actions">
								<button type="button" class="btn btn-default btn-xs" @click="editRow(index)">
									{{ __("Edit") }}
								</button>
								<button type="button" class="btn btn-link btn-xs text-danger" @click="deleteRow(index)">
									{{ __("Remove") }}
								</button>
							</td>
						</tr>
					</tbody>
				</table>
			</div>

			<div v-else-if="!showParameters" class="lot-order__empty">
				<div class="lot-order__empty-title">{{ __("No order quantities entered") }}</div>
				<div>{{ __("Add the first attribute combination to build this Lot's order matrix.") }}</div>
			</div>

			<div v-show="showParameters" class="lot-order__editor">
				<div class="lot-order__editor-title">
					{{ editIndex === null ? __("Add order combination") : __("Edit order combination") }}
				</div>
				<div class="lot-order__controls dependent-controls"></div>
				<div class="lot-order__measure-grid">
					<div class="quantity-controls"></div>
					<div class="ratio-controls"></div>
					<div class="mrp-controls"></div>
				</div>
				<div class="lot-order__editor-actions">
					<button type="button" class="btn btn-default btn-sm" @click="closeEditor()">{{ __("Cancel") }}</button>
					<button type="button" class="btn btn-primary btn-sm" @click="saveRow()">
						{{ editIndex === null ? __("Add") : __("Update") }}
					</button>
				</div>
			</div>
		</div>

		<div v-else class="lot-order__empty">
			<div class="lot-order__empty-title">{{ __("Select an Item Production Detail") }}</div>
			<div>{{ __("The order quantity matrix will appear after the Lot item and production detail are selected.") }}</div>
		</div>
	</section>
</template>

<script setup>
import { computed, nextTick, ref } from "vue";

const root = ref(null);
const list_item = ref([]);
const showParameters = ref(false);
const editIndex = ref(null);
const sampleDoc = ref({});

let primaryControls = {};
let dependentControls = {};

const definition = computed(() => list_item.value[0] || null);
const rows = computed(() => definition.value?.items || []);
const primaryAttribute = computed(() => definition.value?.primary_attribute || "");
const primaryValues = computed(() => definition.value?.primary_attribute_values || []);
const finalAttributes = computed(() => definition.value?.final_state_attr || []);
const canEdit = computed(() => Number(cur_frm.doc.docstatus || 0) === 0 && !cur_frm.doc.is_transferred);

function clone(value) {
	return JSON.parse(JSON.stringify(value));
}

function normalizeDefinition(value) {
	if (!value || Array.isArray(value)) return null;
	const result = clone(value);
	result.items = (result.items || []).map((row) => ({
		...row,
		name: row.name || result.item,
		item_keys: row.item_keys || {},
		primary_attribute: row.primary_attribute || result.primary_attribute || null,
		attributes: row.attributes || {},
		values: row.values || {},
	}));
	return result;
}

function formatNumber(value) {
	const number = Number(value || 0);
	return Number.isInteger(number) ? String(number) : number.toFixed(2).replace(/\.?0+$/, "");
}

function clearControls() {
	if (!root.value) return;
	[".dependent-controls", ".quantity-controls", ".ratio-controls", ".mrp-controls"].forEach((selector) => {
		$(root.value).find(selector).empty();
	});
	primaryControls = {};
	dependentControls = {};
}

function makeControl(parent, df) {
	return frappe.ui.form.make_control({
		parent: $(root.value).find(parent),
		df,
		doc: sampleDoc.value,
		render_input: true,
	});
}

function numericControl(parent, fieldname, label) {
	return makeControl(parent, {
		fieldtype: "Float",
		fieldname,
		label,
		reqd: true,
	});
}

async function renderControls(row = null) {
	await nextTick();
	clearControls();
	if (!definition.value) return;

	for (const [index, attribute] of finalAttributes.value.entries()) {
		const control = makeControl(".dependent-controls", {
			fieldtype: "Link",
			fieldname: `lot_attribute_${index}`,
			options: "Item Attribute Value",
			label: attribute,
			only_select: true,
			reqd: true,
			get_query() {
				return {
					query: "yrp.yrp.doctype.item.item.get_item_attribute_values",
					filters: {
						item: definition.value.item,
						attribute,
					},
				};
			},
		});
		control.set_value(row?.attributes?.[attribute] || "");
		dependentControls[attribute] = control;
	}

	if (primaryAttribute.value) {
		for (const [index, value] of primaryValues.value.entries()) {
			const current = row?.values?.[value] || {};
			primaryControls[value] = {
				qty: numericControl(".quantity-controls", `lot_qty_${index}`, `${value} ${definition.value.default_uom || ""}`.trim()),
				ratio: numericControl(".ratio-controls", `lot_ratio_${index}`, `${value} ${__("Ratio")}`),
				mrp: numericControl(".mrp-controls", `lot_mrp_${index}`, `${value} ${__("MRP")}`),
			};
			primaryControls[value].qty.set_value(current.qty || 0);
			primaryControls[value].ratio.set_value(current.ratio || 0);
			primaryControls[value].mrp.set_value(current.mrp || 0);
		}
	} else {
		primaryControls.qty = numericControl(".quantity-controls", "lot_qty", definition.value.default_uom || __("Quantity"));
		primaryControls.ratio = numericControl(".ratio-controls", "lot_ratio", __("Ratio"));
		primaryControls.mrp = numericControl(".mrp-controls", "lot_mrp", __("MRP"));
		primaryControls.qty.set_value(row?.values?.qty || 0);
		primaryControls.ratio.set_value(row?.values?.ratio || 0);
		primaryControls.mrp.set_value(row?.values?.mrp || 0);
	}
}

function openEditor(index = null) {
	if (!canEdit.value || !definition.value) return;
	editIndex.value = index;
	showParameters.value = true;
	renderControls(index === null ? null : rows.value[index]);
}

function closeEditor() {
	showParameters.value = false;
	editIndex.value = null;
	clearControls();
}

function numberFrom(control) {
	return Number(control?.get_value() || 0);
}

function saveRow() {
	const attributes = {};
	for (const attribute of finalAttributes.value) {
		const value = dependentControls[attribute]?.get_value();
		if (!value) frappe.throw(__("Enter value for {0}", [attribute]));
		attributes[attribute] = value;
	}

	const values = {};
	let hasQuantity = false;
	if (primaryAttribute.value) {
		for (const value of primaryValues.value) {
			values[value] = {
				qty: numberFrom(primaryControls[value]?.qty),
				ratio: numberFrom(primaryControls[value]?.ratio),
				mrp: numberFrom(primaryControls[value]?.mrp),
			};
			if (values[value].qty > 0) hasQuantity = true;
		}
	} else {
		values.qty = numberFrom(primaryControls.qty);
		values.ratio = numberFrom(primaryControls.ratio);
		values.mrp = numberFrom(primaryControls.mrp);
		hasQuantity = values.qty > 0;
	}
	if (!hasQuantity) frappe.throw(__("Enter at least one quantity greater than zero."));

	const row = {
		name: definition.value.item,
		item_keys: editIndex.value === null ? {} : (rows.value[editIndex.value].item_keys || {}),
		attributes,
		primary_attribute: primaryAttribute.value || null,
		values,
	};

	if (editIndex.value !== null) {
		rows.value.splice(editIndex.value, 1, row);
	} else {
		const match = rows.value.findIndex((candidate) =>
			JSON.stringify(candidate.attributes || {}) === JSON.stringify(attributes)
		);
		if (match >= 0) rows.value.splice(match, 1, row);
		else rows.value.push(row);
	}
	cur_frm.dirty();
	closeEditor();
}

function editRow(index) {
	openEditor(index);
}

function deleteRow(index) {
	rows.value.splice(index, 1);
	cur_frm.dirty();
	if (editIndex.value === index) closeEditor();
}

function load_data(items) {
	const normalized = normalizeDefinition(items);
	list_item.value = normalized ? [normalized] : [];
	if (!normalized) {
		closeEditor();
		return;
	}
	if (showParameters.value || cur_frm.is_new()) openEditor(editIndex.value);
}

function show_add_items() {
	if (showParameters.value) closeEditor();
	else openEditor();
}

defineExpose({ list_item, load_data, show_add_items });
</script>

<style scoped>
.lot-order { color: var(--text-color); }
.lot-order__card { border: 1px solid var(--border-color); border-radius: 8px; overflow: hidden; background: var(--card-bg, var(--fg-color)); }
.lot-order__header { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 14px 16px; background: var(--subtle-fg); border-bottom: 1px solid var(--border-color); }
.lot-order__title { font-weight: 600; }
.lot-order__hint, .lot-order__meta, .lot-order__empty { color: var(--text-muted); font-size: 12px; }
.lot-order__table-wrap { overflow-x: auto; }
.lot-order__table { width: 100%; min-width: 720px; border-collapse: collapse; font-size: 12px; }
.lot-order__table th, .lot-order__table td { padding: 9px 10px; border-right: 1px solid var(--border-color); border-bottom: 1px solid var(--border-color); vertical-align: middle; }
.lot-order__table th { background: var(--subtle-fg); color: var(--text-muted); font-size: 11px; font-weight: 600; text-align: left; white-space: nowrap; }
.lot-order__table tr:last-child td { border-bottom: 0; }
.lot-order__table th:last-child, .lot-order__table td:last-child { border-right: 0; }
.lot-order__number { width: 42px; color: var(--text-muted); text-align: center !important; }
.lot-order__qty { font-weight: 600; font-variant-numeric: tabular-nums; }
.lot-order__meta { margin-top: 2px; white-space: nowrap; }
.lot-order__meta span { margin: 0 3px; }
.lot-order__attribute { display: inline-flex; padding: 2px 7px; border-radius: 999px; background: var(--control-bg); white-space: nowrap; }
.lot-order__actions { width: 126px; white-space: nowrap; text-align: right !important; }
.lot-order__empty { padding: 32px 20px; text-align: center; background: var(--subtle-fg); border: 1px dashed var(--border-color); border-radius: 8px; }
.lot-order__empty-title { color: var(--text-color); font-size: 13px; font-weight: 600; margin-bottom: 4px; }
.lot-order__editor { padding: 16px; border-top: 1px solid var(--border-color); background: var(--fg-color); }
.lot-order__editor-title { margin-bottom: 12px; font-weight: 600; }
.lot-order__controls, .lot-order__measure-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px 14px; }
.lot-order__measure-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.lot-order__measure-grid > div { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px; align-content: start; }
.lot-order__editor-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 14px; }
@media (max-width: 900px) { .lot-order__measure-grid { grid-template-columns: 1fr; } }
</style>
