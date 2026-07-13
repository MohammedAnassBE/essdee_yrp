<!--
  PackingSection — /web port of the Desk IPD "Packing" tab (garment IPDs).

  Desk parity (item_production_detail.js):
    - Header: packing_combo (Int), packing_attribute_no (Int), auto_calculate,
      based_on_other_attribute_mapping, packing_mode.
    - "Fetch values" = Desk get_packing_attribute_values →
      essdee_yrp.ipd_ui.get_mapping_attribute_values(mapping, attribute_no),
      where mapping is the item_attributes row of doc.packing_attribute.
    - packing_attribute_details / packing_size_details are plain child tables
      saved WITH the document; packing_assortment_json is a JSON doc field whose
      boxes/qty the user edits in place (Desk render_packing_assortment).
    - "Build boxes" = Desk get_packing_combination →
      essdee_yrp.ipd_ui.get_packing_assortment_combination(doc_name).

  DOCUMENT-level edit mode: `editing` is a prop owned by IPDConfigView (ONE
  Edit/Save/Cancel for the whole IPD — the user rejected per-tab buttons).
  This section exposes validate() + apply(ipd) for the view's single save;
  styling comes from the shared ipd-sections.css.
-->
<template>
	<section class="panel pk-panel">
		<div class="panel-head">
			<h3>Packing</h3>
			<span class="panel-meta">{{ rows.length }} value(s)</span>
		</div>

		<!-- Compact facts strip (always visible) -->
		<div class="pk-facts">
			<div class="pf"><span class="pl">Attribute</span><span class="pv">{{ doc.packing_attribute || "—" }}</span></div>
			<div class="pf">
				<span class="pl">Combo <span class="req">*</span></span>
				<input v-if="editing" v-model.number="form.packing_combo" type="number" min="0" class="pk-num" data-testid="pk-combo" />
				<span v-else class="pv">{{ doc.packing_combo ?? "—" }}</span>
			</div>
			<div class="pf">
				<span class="pl">Values <span class="req">*</span></span>
				<input v-if="editing" v-model.number="form.packing_attribute_no" type="number" min="0" class="pk-num" data-testid="pk-attrno" />
				<span v-else class="pv">{{ doc.packing_attribute_no ?? "—" }}</span>
			</div>
			<div class="pf">
				<span class="pl">Auto qty</span>
				<input v-if="editing" v-model="form.auto_calculate" type="checkbox" />
				<span v-else class="pv">{{ doc.auto_calculate ? "Yes" : "No" }}</span>
			</div>
			<div class="pf">
				<span class="pl">Other mapping</span>
				<input v-if="editing" v-model="form.based_on_other_attribute_mapping" type="checkbox" data-testid="pk-basedon" />
				<span v-else class="pv">{{ doc.based_on_other_attribute_mapping ? "Yes" : "No" }}</span>
			</div>
			<div v-if="form.based_on_other_attribute_mapping" class="pf">
				<span class="pl">Mode</span>
				<Select
					v-if="editing"
					v-model="form.packing_mode"
					:options="['', 'Size Ratio Packing', 'Size Wise Packing']"
					class="pk-mode"
					size="small"
					data-testid="pk-mode"
				/>
				<span v-else class="pv">{{ doc.packing_mode || "Assortment" }}</span>
			</div>
		</div>

		<!-- Attribute values table -->
		<div class="pk-block">
			<div class="pk-block-head">
				<span class="pk-bt">{{ doc.packing_attribute || "Attribute" }} values</span>
				<Button
					v-if="editing && doc.packing_attribute && form.packing_attribute_no"
					size="small"
					text
					label="Fetch values"
					data-testid="pk-fetch"
					:loading="fetching"
					@click="fetchValues"
				/>
			</div>
			<table class="pk-table" data-testid="pk-values">
				<thead>
					<tr><th>Value</th><th class="num">Qty</th><th v-if="editing" class="act" /></tr>
				</thead>
				<tbody>
					<tr v-for="(r, i) in rows" :key="i">
						<td>
							<!-- Commit on SELECT; clearing is allowed (empty commits ""). -->
							<LinkField
								v-if="editing"
								:model-value="r.attribute_value"
								target-doctype="Item Attribute Value"
								:search-handler="attrValueSearch"
								class="pk-link"
								@item-select="(e) => (r.attribute_value = e.value)"
								@update:model-value="(v) => { if (!v) r.attribute_value = '' }"
							/>
							<span v-else>{{ r.attribute_value }}</span>
						</td>
						<td class="num">
							<input v-if="editing" v-model.number="r.quantity" type="number" min="0" class="pk-num" />
							<span v-else>{{ r.quantity }}</span>
						</td>
						<td v-if="editing" class="act">
							<button class="pk-rm" type="button" title="Remove" @click="rows.splice(i, 1)">×</button>
						</td>
					</tr>
					<tr v-if="!rows.length">
						<td :colspan="editing ? 3 : 2" class="pk-empty">No values</td>
					</tr>
				</tbody>
			</table>
			<Button v-if="editing" size="small" text label="+ Row" @click="rows.push({ attribute_value: '', quantity: 0 })" />
		</div>

		<!-- Size table. Shown for BOTH packing modes: the server requires
		     packing_size_details rows for Size Wise too (ipd_validations
		     validate_packing_size_details runs for either mode) — the Desk form
		     hides+clears it on Size Wise, which leaves those docs unsaveable;
		     /web deliberately keeps the rows visible and intact instead. -->
		<div v-if="form.based_on_other_attribute_mapping && form.packing_mode" class="pk-block">
			<div class="pk-block-head"><span class="pk-bt">{{ form.packing_mode === "Size Ratio Packing" ? "Size ratio" : "Sizes" }}</span></div>
			<table class="pk-table" data-testid="pk-sizes">
				<thead>
					<tr><th>Size</th><th class="num">Qty</th><th v-if="editing" class="act" /></tr>
				</thead>
				<tbody>
					<tr v-for="(r, i) in sizeRows" :key="i">
						<td>
							<LinkField
								v-if="editing"
								:model-value="r.attribute_value"
								target-doctype="Item Attribute Value"
								:search-handler="sizeSearch"
								class="pk-link"
								@item-select="(e) => (r.attribute_value = e.value)"
								@update:model-value="(v) => { if (!v) r.attribute_value = '' }"
							/>
							<span v-else>{{ r.attribute_value }}</span>
						</td>
						<td class="num">
							<input v-if="editing" v-model.number="r.quantity" type="number" min="0" class="pk-num" />
							<span v-else>{{ r.quantity }}</span>
						</td>
						<td v-if="editing" class="act">
							<button class="pk-rm" type="button" title="Remove" @click="sizeRows.splice(i, 1)">×</button>
						</td>
					</tr>
					<tr v-if="!sizeRows.length">
						<td :colspan="editing ? 3 : 2" class="pk-empty">No sizes</td>
					</tr>
				</tbody>
			</table>
			<Button v-if="editing" size="small" text label="+ Row" @click="sizeRows.push({ attribute_value: '', quantity: 0 })" />
		</div>

		<!-- Assortment boxes (based-on-other-mapping, no mode) -->
		<div v-if="form.based_on_other_attribute_mapping && !form.packing_mode" class="pk-block">
			<div class="pk-block-head">
				<span class="pk-bt">Assortment</span>
				<Button
					v-if="editing"
					size="small"
					text
					label="Build boxes"
					data-testid="pk-boxes"
					:loading="building"
					@click="buildBoxes"
				/>
			</div>
			<div v-if="assortment && assortment.boxes && assortment.boxes.length" class="pk-boxes">
				<div v-for="(box, bi) in assortment.boxes" :key="bi" class="pk-box">
					<div class="pk-box-name">Box {{ box.box }}</div>
					<table class="pk-table">
						<thead>
							<tr>
								<th>{{ (assortment.assortment_attributes || []).join(" / ") }}</th>
								<th class="num">Qty / Box</th>
							</tr>
						</thead>
						<tbody>
							<tr v-for="(row, ri) in box.rows || []" :key="ri">
								<td>{{ (assortment.assortment_attributes || []).map((a) => row[a]).join(" / ") }}</td>
								<td class="num">
									<input v-if="editing" v-model.number="row.qty" type="number" min="0" class="pk-num" />
									<span v-else>{{ row.qty || 0 }}</span>
								</td>
							</tr>
						</tbody>
					</table>
				</div>
			</div>
			<div v-else class="pk-empty">No boxes yet</div>
		</div>
	</section>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import Button from "primevue/button";
import Select from "primevue/select";
import LinkField from "@/components/LinkField.vue";
import { callMethod } from "@/api/client";
import { stableStringify } from "./combinationCells";
import { useAppToast } from "@/composables/useToast";

const props = defineProps({
	doc: { type: Object, required: true },
	editing: { type: Boolean, default: false },
});

const toast = useAppToast();

const fetching = ref(false);
const building = ref(false);
const form = ref({});
const rows = ref([]);
const sizeRows = ref([]);
const assortment = ref(null);
let assortCorrupt = false;
// Version-noise guard: a save that never touched this section must not rewrite
// its JSON field (content-equal reserialization still shows as a Version diff).
let assortBaseline = "null";

// The packing attribute's Item Item Attribute Mapping (Desk: frm.set_packing_attr_map_value)
const packingMapping = computed(() => {
	const row = (props.doc.item_attributes || []).find((a) => a.attribute === props.doc.packing_attribute);
	return row?.mapping || null;
});

function hydrate() {
	const d = props.doc;
	form.value = {
		packing_combo: d.packing_combo ?? 0,
		packing_attribute_no: d.packing_attribute_no ?? 0,
		auto_calculate: !!d.auto_calculate,
		based_on_other_attribute_mapping: !!d.based_on_other_attribute_mapping,
		packing_mode: d.packing_mode || "",
	};
	rows.value = (d.packing_attribute_details || []).map((r) => ({
		name: r.name, // IMP-2: untouched rows round-trip in place
		attribute_value: r.attribute_value,
		quantity: r.quantity ?? 0,
	}));
	sizeRows.value = (d.packing_size_details || []).map((r) => ({
		name: r.name,
		attribute_value: r.attribute_value,
		quantity: r.quantity ?? 0,
	}));
	let aj = d.packing_assortment_json;
	assortCorrupt = false;
	if (typeof aj === "string") {
		try {
			aj = JSON.parse(aj);
		} catch {
			// m5: unreadable stored JSON must block the save, not be overwritten.
			aj = null;
			assortCorrupt = true;
		}
	}
	assortment.value = aj || null;
	assortBaseline = stableStringify(assortment.value);
}
// Don't clobber in-progress edits when the doc reloads behind us — rehydrate
// only while viewing; re-snapshot on every edit-mode toggle (enter AND leave).
watch(
	() => props.doc,
	() => {
		if (!props.editing) hydrate();
	},
	{ immediate: true },
);
watch(
	() => props.editing,
	() => hydrate(),
);

// The primary attribute's mapping — sizes live there (Desk get_packing_size_values).
const primaryMapping = computed(() => {
	const row = (props.doc.item_attributes || []).find(
		(a) => a.attribute === props.doc.primary_item_attribute,
	);
	return row?.mapping || null;
});

// Desk packing_mode trigger parity: Size Wise forces combo = 1 (server does the
// same); Size Ratio prefills one row per valid size, preserving typed quantities.
watch(
	() => form.value.packing_mode,
	async (mode, prev) => {
		if (!props.editing || mode === prev) return;
		if (mode === "Size Wise Packing") {
			form.value.packing_combo = 1;
			return;
		}
		if (mode !== "Size Ratio Packing") return;
		try {
			const sizes = await callMethod("essdee_yrp.ipd_ui.get_packing_size_values", {
				doc_name: props.doc.name,
			});
			if (!sizes) return;
			const existing = {};
			sizeRows.value.forEach((r) => {
				existing[r.attribute_value] = r.quantity;
			});
			sizeRows.value = sizes.map((s) => ({ attribute_value: s, quantity: existing[s] || 0 }));
		} catch (e) {
			toast.error("Prefill failed", e.message);
		}
	},
);

async function mappingSearch(mapping, q) {
	if (!mapping) return [];
	const res = await callMethod("essdee_yrp.ipd_ui.get_attribute_detail_values", {
		doctype: "Item Attribute Value",
		txt: q || "",
		searchfield: "name",
		start: 0,
		page_len: 20,
		filters: { mapping },
	});
	return (res || []).map((t) => ({ name: Array.isArray(t) ? t[0] : t }));
}
// Size picker: only the primary attribute's (size) values.
const sizeSearch = (q) => mappingSearch(primaryMapping.value, q);

// Restrict the picker to the packing attribute's own values (Desk set_query).
async function attrValueSearch(q) {
	if (!packingMapping.value) return [];
	const res = await callMethod("essdee_yrp.ipd_ui.get_attribute_detail_values", {
		doctype: "Item Attribute Value",
		txt: q || "",
		searchfield: "name",
		start: 0,
		page_len: 20,
		filters: { mapping: packingMapping.value },
	});
	return (res || []).map((t) => ({ name: Array.isArray(t) ? t[0] : t }));
}

async function fetchValues() {
	if (!packingMapping.value) {
		toast.error("No mapping", "Set the packing attribute first (Advance Settings).");
		return;
	}
	fetching.value = true;
	try {
		const res = await callMethod("essdee_yrp.ipd_ui.get_mapping_attribute_values", {
			attribute_mapping_value: packingMapping.value,
			attribute_no: form.value.packing_attribute_no,
		});
		rows.value = (res || []).map((r) => ({
			attribute_value: r.attribute_value,
			quantity: r.quantity ?? 0,
		}));
	} catch (e) {
		toast.error("Fetch failed", e.message);
	} finally {
		fetching.value = false;
	}
}

async function buildBoxes() {
	building.value = true;
	try {
		const res = await callMethod("essdee_yrp.ipd_ui.get_packing_assortment_combination", {
			doc_name: props.doc.name,
		});
		if (res) assortment.value = res;
	} catch (e) {
		toast.error("Build failed", e.message);
	} finally {
		building.value = false;
	}
}

// ── document-level save contract (called by IPDConfigView) ──
function validate() {
	if (assortCorrupt) {
		return "Assortment: stored data is unreadable — fix it in Desk before saving here";
	}
	// mandatory_depends_on parity (garment IPD): combo + attribute count required.
	if (!form.value.packing_combo || !form.value.packing_attribute_no) {
		return "Packing combo and the attribute count are both required";
	}
	// m2: half-filled rows BLOCK with visible row numbers — never silently drop.
	const rowBlank = (r) => !r.attribute_value && !r.quantity;
	const badVal = rows.value.map((r, i) => (!rowBlank(r) && !r.attribute_value ? i + 1 : 0)).filter(Boolean);
	if (badVal.length) return `Value row(s) ${badVal.join(", ")}: value is required`;
	const keepSizes = form.value.based_on_other_attribute_mapping && form.value.packing_mode;
	if (keepSizes) {
		const badSize = sizeRows.value.map((r, i) => (!rowBlank(r) && !r.attribute_value ? i + 1 : 0)).filter(Boolean);
		if (badSize.length) return `Size row(s) ${badSize.join(", ")}: size is required`;
	}
	return null;
}
function apply(ipd) {
	ipd.packing_combo = form.value.packing_combo;
	ipd.packing_attribute_no = form.value.packing_attribute_no;
	ipd.auto_calculate = form.value.auto_calculate ? 1 : 0;
	ipd.based_on_other_attribute_mapping = form.value.based_on_other_attribute_mapping ? 1 : 0;
	ipd.packing_mode = form.value.based_on_other_attribute_mapping ? form.value.packing_mode || "" : "";
	ipd.packing_attribute_details = rows.value
		.filter((r) => r.attribute_value)
		.map((r) => ({
			doctype: "Item Production Detail Packing Attribute Detail",
			...(r.name ? { name: r.name } : {}),
			attribute_value: r.attribute_value,
			quantity: r.quantity || 0,
		}));
	// Rows are required for BOTH packing modes (server validates either);
	// only clear them when no mode / no other-mapping is in play.
	const keepSizes = form.value.based_on_other_attribute_mapping && form.value.packing_mode;
	ipd.packing_size_details = (keepSizes ? sizeRows.value : [])
		.filter((r) => r.attribute_value)
		.map((r) => ({
			doctype: "Item Production Detail Packing Size Detail",
			...(r.name ? { name: r.name } : {}),
			attribute_value: r.attribute_value,
			quantity: r.quantity || 0,
		}));
	// m6: the assortment JSON belongs to assortment mode only — when the mode
	// has moved to Size Ratio/Wise, preserve the stored value untouched.
	const assortmentMode = form.value.based_on_other_attribute_mapping && !form.value.packing_mode;
	if (assortmentMode && assortment.value && stableStringify(assortment.value) !== assortBaseline) {
		ipd.packing_assortment_json = assortment.value;
	}
}
defineExpose({ validate, apply });
</script>
