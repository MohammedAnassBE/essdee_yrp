<template>
	<div class="lot-order-editor">
		<!-- ── Saved rows (mirror of Desk LotOrder.vue's nested table) ── -->
		<div v-if="struct && (struct.items || []).length" class="lot-table-wrap">
			<table class="esd-table lot-table">
				<thead>
					<tr>
						<th>#</th>
						<th>Item</th>
						<th v-for="attr in depAttrs" :key="'h-' + attr">{{ attr }}</th>
						<template v-if="hasPrimary">
							<th v-for="pv in struct.primary_attribute_values" :key="'p-' + pv">{{ pv }}</th>
						</template>
						<template v-else>
							<th>Qty</th>
							<th>Ratio</th>
							<th>MRP</th>
						</template>
						<th v-if="!readonly" class="col-actions"></th>
					</tr>
				</thead>
				<tbody>
					<tr v-for="(row, ri) in struct.items" :key="ri">
						<td>{{ ri + 1 }}</td>
						<td>{{ struct.item }}</td>
						<td v-for="attr in depAttrs" :key="'v-' + attr">{{ row.attributes?.[attr] }}</td>
						<template v-if="hasPrimary">
							<td v-for="pv in struct.primary_attribute_values" :key="'c-' + pv" class="lot-cell">
								<div class="lot-cell__qty">{{ cellVal(row, pv, "qty") }}</div>
								<div class="lot-cell__sub">R {{ cellVal(row, pv, "ratio") }} · ₹{{ cellVal(row, pv, "mrp") }}</div>
							</td>
						</template>
						<template v-else>
							<td>{{ row.values?.qty ?? 0 }}</td>
							<td>{{ row.values?.ratio ?? 0 }}</td>
							<td>{{ row.values?.mrp ?? 0 }}</td>
						</template>
						<td v-if="!readonly" class="col-actions">
							<Button icon="pi pi-pencil" size="small" text @click="editRow(ri)" />
							<Button icon="pi pi-trash" size="small" text severity="danger" @click="deleteRow(ri)" />
						</td>
					</tr>
				</tbody>
			</table>
		</div>
		<div v-else-if="!showForm" class="esd-empty">
			<i class="pi pi-inbox" />
			<p class="esd-empty__text">
				{{ struct ? "No order items yet." : "Pick an Item Production Detail to load the order-items editor." }}
			</p>
		</div>

		<!-- ── Add / edit form (mirror of Desk "Fetch Item" flow) ── -->
		<template v-if="!readonly && struct">
			<Button
				v-if="!showForm"
				label="Fetch Item"
				icon="pi pi-plus"
				size="small"
				severity="success"
				class="lot-fetch-btn"
				@click="openForm()"
			/>
			<div v-else class="lot-add-form">
				<div class="lot-form-row">
					<div v-for="attr in depAttrs" :key="'f-' + attr" class="lot-field">
						<label class="field-label">{{ attr }} *</label>
						<AutoComplete
							v-model="entry.attributes[attr]"
							:suggestions="attrSuggestions[attr] || []"
							dropdown
							fluid
							@complete="(e) => searchAttrValues(attr, e.query)"
						/>
					</div>
				</div>
				<div v-if="hasPrimary" class="lot-form-grid">
					<div v-for="pv in struct.primary_attribute_values" :key="'fp-' + pv" class="lot-field">
						<label class="field-label">{{ pv }} ({{ struct.default_uom }})</label>
						<InputNumber v-model="entry.values[pv].qty" :min="0" :maxFractionDigits="3" fluid placeholder="Qty" />
						<InputNumber v-model="entry.values[pv].ratio" :min="0" :maxFractionDigits="3" fluid placeholder="Ratio" />
						<InputNumber v-model="entry.values[pv].mrp" :min="0" :maxFractionDigits="2" fluid placeholder="MRP" />
					</div>
				</div>
				<div v-else class="lot-form-row">
					<div class="lot-field">
						<label class="field-label">Qty ({{ struct.default_uom }}) *</label>
						<InputNumber v-model="entry.flat.qty" :min="0" :maxFractionDigits="3" fluid />
					</div>
					<div class="lot-field">
						<label class="field-label">Ratio *</label>
						<InputNumber v-model="entry.flat.ratio" :min="0" :maxFractionDigits="3" fluid />
					</div>
					<div class="lot-field">
						<label class="field-label">MRP *</label>
						<InputNumber v-model="entry.flat.mrp" :min="0" :maxFractionDigits="2" fluid />
					</div>
				</div>
				<div class="lot-form-actions">
					<Button :label="editIndex === null ? 'Add Item' : 'Update Item'" icon="pi pi-check" size="small" severity="success" @click="commitEntry" />
					<Button label="Cancel" size="small" severity="secondary" text @click="closeForm" />
				</div>
			</div>
		</template>
	</div>
</template>

<script setup>
/**
 * Lot "Order Items" editor — /web mirror of the Desk Vue island
 * apps/yrp/yrp/public/js/Lot/components/LotOrder.vue (+ its LotOrderWrapper).
 *
 * Data contract (byte-faithful to the Desk):
 *  - loadData(x): x is either [] (clear) or the BARE item-structure dict
 *    returned by Lot.get_item_details / __onload.item_details:
 *      { item, primary_attribute, primary_attribute_values, final_state_attr,
 *        default_uom, items: [{ attributes:{attr:val}, primary_attribute,
 *        values: {<size>: {qty, ratio, mrp}} | {qty, ratio, mrp} }] }
 *  - getItems(): returns the ARRAY-WRAPPED [structure] (or []) — the server's
 *    save_item_details does item_details[0], and the Desk wrapper's get_data()
 *    returns list_item = [structure].
 *  - Dependent-attribute pickers query the SAME server query the Desk uses
 *    (yrp...item.get_item_attribute_values via frappe.desk.search.search_link)
 *    scoped to {item, attribute, production_detail}.
 *  - Add merges into an existing row when the dependent-attribute set matches
 *    (qty adds; ratio/mrp replace) — mirrors LotOrder.add_item exactly.
 */
import { computed, reactive, ref, watch } from "vue"
import AutoComplete from "primevue/autocomplete"
import InputNumber from "primevue/inputnumber"
import Button from "primevue/button"
import { callMethod } from "@/api/client"
import { useAppToast } from "@/composables/useToast"

const props = defineProps({
	initialData: { type: [Object, Array], default: null },
	readonly: { type: Boolean, default: false },
	// The Lot form's production_detail — scopes the attribute-value search.
	productionDetail: { type: String, default: "" },
})
const emit = defineEmits(["change"])
const toast = useAppToast()

const struct = ref(null)
const showForm = ref(false)
const editIndex = ref(null)
const attrSuggestions = reactive({})
const entry = reactive({ attributes: {}, values: {}, flat: { qty: null, ratio: null, mrp: null } })

const hasPrimary = computed(() => !!struct.value?.primary_attribute)
const depAttrs = computed(() => struct.value?.final_state_attr || [])

function loadData(x) {
	if (Array.isArray(x)) struct.value = x.length ? x[0] : null
	else struct.value = x || null
	if (struct.value && !Array.isArray(struct.value.items)) struct.value.items = []
	showForm.value = false
	editIndex.value = null
}
function getItems() {
	return struct.value ? [JSON.parse(JSON.stringify(struct.value))] : []
}
function hasItems() {
	return !!struct.value?.items?.length
}
watch(() => props.initialData, (v) => { if (v != null) loadData(v) }, { immediate: true })

function cellVal(row, pv, key) {
	const c = row.values?.[pv]
	return c ? (c[key] ?? 0) : 0
}

function blankEntry() {
	entry.attributes = {}
	entry.flat = { qty: null, ratio: null, mrp: null }
	entry.values = {}
	for (const pv of struct.value?.primary_attribute_values || []) {
		entry.values[pv] = { qty: null, ratio: null, mrp: null }
	}
}
function openForm(fromRow = null) {
	blankEntry()
	if (fromRow) {
		entry.attributes = { ...(fromRow.attributes || {}) }
		if (hasPrimary.value) {
			for (const pv of struct.value.primary_attribute_values || []) {
				const c = fromRow.values?.[pv] || {}
				entry.values[pv] = { qty: c.qty ?? null, ratio: c.ratio ?? null, mrp: c.mrp ?? null }
			}
		} else {
			entry.flat = {
				qty: fromRow.values?.qty ?? null,
				ratio: fromRow.values?.ratio ?? null,
				mrp: fromRow.values?.mrp ?? null,
			}
		}
	}
	showForm.value = true
}
function closeForm() {
	showForm.value = false
	editIndex.value = null
}
function editRow(i) {
	editIndex.value = i
	openForm(struct.value.items[i])
}
function deleteRow(i) {
	struct.value.items.splice(i, 1)
	emit("change")
}

// Desk parity: the dependent-value picker runs the SAME custom link query the
// Desk control uses, so only values valid for this item + IPD are offered.
async function searchAttrValues(attr, q) {
	try {
		const res = await callMethod("frappe.desk.search.search_link", {
			doctype: "Item Attribute Value",
			txt: q || "",
			query: "yrp.yrp.doctype.item.item.get_item_attribute_values",
			filters: {
				item: struct.value?.item || "",
				attribute: attr,
				production_detail: props.productionDetail || "",
			},
		})
		const rows = Array.isArray(res) ? res : res?.results || []
		attrSuggestions[attr] = rows.map((r) => r.value ?? r)
	} catch (_) {
		attrSuggestions[attr] = []
	}
}

function sameAttrs(a, b) {
	for (const attr of depAttrs.value) {
		if ((a?.[attr] ?? "") !== (b?.[attr] ?? "")) return false
	}
	return true
}

// Mirror LotOrder.add_item: validate deps + at-least-one qty; merge on equal
// dependent-attribute sets (qty adds, ratio/mrp replace); else push a new row.
function commitEntry() {
	for (const attr of depAttrs.value) {
		if (!entry.attributes[attr]) {
			toast.warn("Missing value", `Enter a value for ${attr}.`)
			return
		}
	}
	let values
	let anyQty = false
	if (hasPrimary.value) {
		values = {}
		for (const pv of struct.value.primary_attribute_values || []) {
			const c = entry.values[pv] || {}
			values[pv] = { qty: c.qty || 0, ratio: c.ratio || 0, mrp: c.mrp || 0 }
			if (values[pv].qty > 0) anyQty = true
		}
	} else {
		values = { qty: entry.flat.qty || 0, ratio: entry.flat.ratio || 0, mrp: entry.flat.mrp || 0 }
		anyQty = values.qty > 0
	}
	if (!anyQty) {
		toast.warn("Fill the quantity", "Enter a quantity greater than zero.")
		return
	}

	const item = {
		attributes: { ...entry.attributes },
		primary_attribute: struct.value.primary_attribute,
		values,
	}

	if (editIndex.value !== null) {
		struct.value.items[editIndex.value] = item
	} else {
		const existing = struct.value.items.find((r) => sameAttrs(r.attributes, item.attributes))
		if (existing) {
			if (hasPrimary.value) {
				for (const pv of Object.keys(existing.values || {})) {
					existing.values[pv].qty = (existing.values[pv].qty || 0) + (item.values[pv]?.qty || 0)
					existing.values[pv].ratio = item.values[pv]?.ratio ?? existing.values[pv].ratio
					existing.values[pv].mrp = item.values[pv]?.mrp ?? existing.values[pv].mrp
				}
			} else {
				existing.values.qty = (existing.values.qty || 0) + (item.values.qty || 0)
				existing.values.ratio = item.values.ratio
				existing.values.mrp = item.values.mrp
			}
		} else {
			struct.value.items.push(item)
		}
	}
	closeForm()
	emit("change")
}

defineExpose({ loadData, getItems, hasItems })
</script>

<style scoped>
.lot-order-editor {
	display: flex;
	flex-direction: column;
	gap: 10px;
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
.lot-cell__qty {
	font-weight: 600;
}
.lot-cell__sub {
	font-size: 11px;
	color: var(--esd-muted);
}
.col-actions {
	width: 1%;
}
.lot-fetch-btn {
	align-self: flex-start;
}
.lot-add-form {
	border: 1px dashed var(--esd-line);
	border-radius: 10px;
	padding: 12px;
	display: flex;
	flex-direction: column;
	gap: 10px;
	background: var(--esd-card);
}
.lot-form-row {
	display: flex;
	flex-wrap: wrap;
	gap: 10px;
}
.lot-form-grid {
	display: grid;
	grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
	gap: 10px;
}
.lot-field {
	display: flex;
	flex-direction: column;
	gap: 4px;
	min-width: 140px;
}
.lot-form-actions {
	display: flex;
	gap: 8px;
}
</style>
