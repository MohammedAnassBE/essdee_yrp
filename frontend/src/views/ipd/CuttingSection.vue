<!--
  CuttingSection — /web port of the Desk IPD "Cutting" tab (garment IPDs).

  Desk parity (item_production_detail.js + CuttingItemDetail widget):
    - Cloth details = cloth_detail child rows (name, cloth Item, BOM flag, GSM).
    - TWO checkbox-driven combination views (the user's mandate): tick the
      combination attributes → the grid regenerates via
      ipd_ui.get_combination(doc, attrs, "Cutting" | "Cloth"). Checked
      attribute columns are display-only; "Dia" picks Dia values, "Weight" is a
      number, "Cloth" selects one of the cloth names; a header input fills a
      whole column (Desk "Fill").
    - Checkbox options = ipd_ui.get_stiching_in_stage_attributes(+ set attr for
      set items); checked state = cutting_attributes / cloth_attributes rows.
  Save contract: cloth_detail + cutting_attributes + cloth_attributes child rows
  and cutting_items_json / cutting_cloths_json — each JSON written ONLY when its
  grid is hydrated and non-empty (Desk validate parity: never wipe stored data
  with an unopened view). Deliberate deviation: Desk's "Update Cloth Items"
  button is unnecessary — Cloth options derive reactively from the cloth rows.

  DOCUMENT-level edit mode: `editing` prop from IPDConfigView (one Edit/Save/
  Cancel for the whole IPD); exposes validate() + apply(ipd) for the single save.
-->
<template>
	<section class="panel ct-panel">
		<div class="panel-head">
			<h3>Cutting</h3>
			<span class="panel-meta">{{ cloths.length }} cloth(s)</span>
		</div>

		<!-- Cloth details -->
		<div class="ct-block">
			<div class="pk-block-head"><span class="pk-bt">Cloth details</span></div>
			<table class="pk-table" data-testid="ct-cloths">
				<thead>
					<tr>
						<th>Name</th>
						<th>Cloth item</th>
						<th class="num">BOM</th>
						<th class="num">GSM</th>
						<th v-if="editing" class="act" />
					</tr>
				</thead>
				<tbody>
					<tr v-for="(r, i) in cloths" :key="i">
						<td>
							<input v-if="editing" v-model="r.name1" class="ct-text" />
							<span v-else>{{ r.name1 }}</span>
						</td>
						<td>
							<!-- Commit on SELECT; clearing is allowed (empty commits ""). -->
							<LinkField
								v-if="editing"
								:model-value="r.cloth"
								target-doctype="Item"
								:filters="{ disabled: 0 }"
								class="ct-link"
								@item-select="(e) => (r.cloth = e.value)"
								@update:model-value="(v) => { if (!v) r.cloth = '' }"
							/>
							<span v-else>{{ r.cloth }}</span>
						</td>
						<td class="num">
							<input v-if="editing" v-model="r.is_bom_item" type="checkbox" />
							<span v-else>{{ r.is_bom_item ? "Yes" : "" }}</span>
						</td>
						<td class="num">
							<input v-if="editing" v-model.number="r.required_gsm" type="number" min="0" class="ct-num" />
							<span v-else>{{ r.required_gsm || "—" }}</span>
						</td>
						<td v-if="editing" class="act">
							<button class="ct-rm" type="button" title="Remove" @click="cloths.splice(i, 1)">×</button>
						</td>
					</tr>
					<tr v-if="!cloths.length">
						<td :colspan="editing ? 5 : 4" class="pk-empty">No cloths</td>
					</tr>
				</tbody>
			</table>
			<Button
				v-if="editing"
				size="small"
				text
				label="+ Row"
				@click="cloths.push({ name1: '', cloth: '', is_bom_item: false, required_gsm: 0 })"
			/>
		</div>

		<!-- Cutting combination -->
		<CombinationPivot
			v-if="combinable"
			title="Cutting combination"
			test-id="ct-cutting"
			:editing="editing"
			:options="attrOptions"
			v-model:checked="cuttingChecked"
			:grid="cuttingGrid"
			:read-only-columns="cuttingChecked"
			:mapping-search="packValueSearch"
			:select-options="clothNames"
			:building="buildingCut"
			:build-disabled="!clothNames.length"
			@build="buildCutting"
		/>

		<!-- Cloth mapping combination -->
		<CombinationPivot
			v-if="combinable"
			title="Cloth mapping"
			test-id="ct-clothmap"
			:editing="editing"
			:options="attrOptions"
			v-model:checked="clothChecked"
			:grid="clothGrid"
			:read-only-columns="clothChecked"
			:mapping-search="packValueSearch"
			:select-options="clothNames"
			:building="buildingCloth"
			:build-disabled="!clothNames.length"
			@build="buildCloth"
		/>
		<div v-if="!combinable" class="pk-empty">
			Set the stitching input stage and dependent attribute first (Advance Settings).
		</div>
	</section>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import Button from "primevue/button";
import LinkField from "@/components/LinkField.vue";
import CombinationPivot from "./CombinationPivot.vue";
import { callMethod } from "@/api/client";
import { useAppToast } from "@/composables/useToast";
import { mappingSearch, findBlankCell, stableStringify } from "./combinationCells";

const props = defineProps({
	doc: { type: Object, required: true },
	editing: { type: Boolean, default: false },
});

const toast = useAppToast();

const buildingCut = ref(false);
const buildingCloth = ref(false);
const cloths = ref([]);
const attrOptions = ref([]);
const cuttingChecked = ref([]);
const clothChecked = ref([]);
const cuttingGrid = ref(null);
const clothGrid = ref(null);
let storedCuttingChecked = 0;
let storedClothChecked = 0;

// Desk mounts the combination widgets only for staged garment IPDs.
const combinable = computed(() => !!props.doc.stiching_in_stage && !!props.doc.dependent_attribute);

const packingMapping = computed(() => {
	const row = (props.doc.item_attributes || []).find((a) => a.attribute === props.doc.packing_attribute);
	return row?.mapping || null;
});
const packValueSearch = (q) => mappingSearch(packingMapping.value)(q);
// Only COMPLETE cloth rows count anywhere (Cloth options, combinations) — an
// incomplete row blocks the save instead of being silently dropped.
const clothNames = computed(() => cloths.value.filter((r) => r.name1 && r.cloth).map((r) => r.name1));

// Corrupt stored JSON must BLOCK the save (m5): hydrating it to null and
// then writing would silently overwrite data a fix-in-Desk could recover.
let corruptJson = null;
function parseJson(v, label) {
	if (!v) return null;
	if (typeof v === "string") {
		try {
			return JSON.parse(v);
		} catch {
			corruptJson = corruptJson || label;
			return null;
		}
	}
	return v;
}

// IMP-2: child-row `name` rides hydrate → apply so untouched rows round-trip
// in place (no delete+recreate churn); new rows are legitimately nameless.
let cuttingAttrRowNames = {};
let clothAttrRowNames = {};
// Version-noise guards: skip writing a JSON that hasn't actually changed.
let cutGridBaseline = "null";
let clothGridBaseline = "null";
async function hydrate() {
	const d = props.doc;
	corruptJson = null;
	cloths.value = (d.cloth_detail || []).map((r) => ({
		name: r.name,
		name1: r.name1,
		cloth: r.cloth,
		is_bom_item: !!r.is_bom_item,
		required_gsm: r.required_gsm ?? 0,
	}));
	cuttingChecked.value = (d.cutting_attributes || []).map((r) => r.attribute).filter(Boolean);
	clothChecked.value = (d.cloth_attributes || []).map((r) => r.attribute).filter(Boolean);
	cuttingAttrRowNames = Object.fromEntries((d.cutting_attributes || []).map((r) => [r.attribute, r.name]));
	clothAttrRowNames = Object.fromEntries((d.cloth_attributes || []).map((r) => [r.attribute, r.name]));
	storedCuttingChecked = cuttingChecked.value.length;
	storedClothChecked = clothChecked.value.length;
	const cj = parseJson(d.cutting_items_json, "Cutting combination");
	cuttingGrid.value = cj && (cj.items || []).length ? cj : null;
	cutGridBaseline = stableStringify(cuttingGrid.value);
	const cc = parseJson(d.cutting_cloths_json, "Cloth mapping");
	clothGrid.value = cc && (cc.items || []).length ? cc : null;
	// Baseline mirrors the exact candidate apply() would build (select_list is
	// re-appended there, which shifts JSON key order) — else every save rewrites
	// a content-equal value and pollutes the Version trail.
	clothGridBaseline = stableStringify(
		clothGrid.value ? { ...clothGrid.value, select_list: clothNames.value } : null,
	);
	if (combinable.value && !attrOptions.value.length) {
		try {
			// Desk get_stich_in_attributes(+ set attribute for set items).
			const attrs = await callMethod("essdee_yrp.ipd_ui.get_stiching_in_stage_attributes", {
				dependent_attribute_mapping: d.dependent_attribute_mapping,
				stiching_in_stage: d.stiching_in_stage,
				item: d.item,
			});
			const list = [...(attrs || [])];
			if (d.is_set_item && d.set_item_attribute && !list.includes(d.set_item_attribute)) {
				list.push(d.set_item_attribute);
			}
			attrOptions.value = list;
		} catch (e) {
			toast.error("Attributes unavailable", e.message);
		}
	}
}
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

// IMP-3: per-target build generations — rapid toggles fire get_combination
// per change and responses can return out of order; only the LAST request may
// write the grid (same pattern as the hydrate gen guard).
const buildGen = { Cutting: 0, Cloth: 0 };
async function buildCombination(kind, checked, target, busy, evt) {
	// Desk get_cutting_combination / get_cloth_combination guards. Only the
	// Cloth side needs cloth rows programmatically (Desk parity) — the Cutting
	// side must keep rebuilding on partial unticks even with no cloth rows.
	if (kind === "Cloth" && !clothNames.value.length) {
		toast.error("Missing", "Fill the cloth details first");
		return;
	}
	if (!checked.length) {
		// Untick-all is the deliberate-clear path — silent when toggle-driven
		// (m1); an explicit Build click with nothing ticked still explains.
		buildGen[kind]++;
		target.value = null;
		if (!evt?.fromToggle) toast.error("No attributes", "Tick the attributes to make the combination");
		return;
	}
	const g = ++buildGen[kind];
	busy.value = true;
	try {
		const res = await callMethod("essdee_yrp.ipd_ui.get_combination", {
			doc_name: props.doc.name,
			attributes: checked,
			combination_type: kind,
			cloth_list: kind === "Cloth" ? clothNames.value : null,
		});
		if (g === buildGen[kind]) target.value = res;
	} catch (e) {
		toast.error("Build failed", e.message);
	} finally {
		busy.value = false;
	}
}
const buildCutting = (evt) => buildCombination("Cutting", cuttingChecked.value, cuttingGrid, buildingCut, evt);
const buildCloth = (evt) => buildCombination("Cloth", clothChecked.value, clothGrid, buildingCloth, evt);

function clothRowIsBlank(r) {
	return !r.name1 && !r.cloth && !r.required_gsm && !r.is_bom_item;
}
const activeCloths = () => cloths.value.filter((r) => !clothRowIsBlank(r));

// ── document-level save contract (called by IPDConfigView) ──
function validate() {
	if (corruptJson) {
		return `${corruptJson}: stored data is unreadable — fix it in Desk before saving here`;
	}
	// Desk blocks incomplete reqd child rows — never silently drop them.
	// Row numbers reference the VISIBLE positions (blank drafts included).
	const badCloth = cloths.value
		.map((r, i) => (!clothRowIsBlank(r) && (!r.name1 || !r.cloth) ? i + 1 : 0))
		.filter(Boolean);
	if (badCloth.length) return `Row(s) ${badCloth.join(", ")}: name and cloth item are both required`;
	for (const [label, grid] of [
		["Cutting combination", cuttingGrid.value],
		["Cloth mapping", clothGrid.value],
	]) {
		if (!grid) continue;
		if (label === "Cloth mapping") {
			// Desk get_data parity: every mapped cloth must still exist in the list.
			for (const row of grid.items || []) {
				if (row.Cloth && !clothNames.value.includes(row.Cloth)) {
					return `${label}: some cloth items are not in the cloth details list`;
				}
			}
		}
		const blank = findBlankCell(grid.items, grid.attributes);
		if (blank) return `${label}: fill all the combinations (${blank})`;
	}
	return null;
}
function apply(ipd) {
	ipd.cloth_detail = activeCloths().map((r) => ({
		doctype: "Item Production Detail Cloth Detail",
		...(r.name ? { name: r.name } : {}),
		name1: r.name1,
		cloth: r.cloth,
		is_bom_item: r.is_bom_item ? 1 : 0,
		required_gsm: r.required_gsm || 0,
	}));
	ipd.cutting_attributes = cuttingChecked.value.map((a) => ({
		doctype: "Cutting Attribute Detail",
		...(cuttingAttrRowNames[a] ? { name: cuttingAttrRowNames[a] } : {}),
		attribute: a,
	}));
	ipd.cloth_attributes = clothChecked.value.map((a) => ({
		doctype: "Cutting Attribute Detail",
		...(clothAttrRowNames[a] ? { name: clothAttrRowNames[a] } : {}),
		attribute: a,
	}));
	// Desk validate parity: write each JSON only when its grid holds rows —
	// preserve stored data when the view never rendered/regenerated. But
	// UNTICKING ALL attributes is a deliberate clear (Desk on_change writes
	// {}), detected as: stored attributes existed and are now all unticked.
	// (A legacy doc with JSON but no stored attribute rows is left intact.)
	if (!cuttingChecked.value.length && storedCuttingChecked > 0) {
		ipd.cutting_items_json = {};
	} else if (
		cuttingGrid.value &&
		(cuttingGrid.value.items || []).length &&
		stableStringify(cuttingGrid.value) !== cutGridBaseline
	) {
		ipd.cutting_items_json = cuttingGrid.value;
	}
	if (!clothChecked.value.length && storedClothChecked > 0) {
		ipd.cutting_cloths_json = {};
	} else if (clothGrid.value && (clothGrid.value.items || []).length) {
		const candidate = { ...clothGrid.value, select_list: clothNames.value };
		// NOTE: the server's sync_cutting_cloth_select_list still re-assigns this
		// field (str→dict) on every validate, so one content-equal Version entry
		// remains even when we skip — that's pre-existing Desk-parity behavior.
		if (stableStringify(candidate) !== clothGridBaseline) ipd.cutting_cloths_json = candidate;
	}
}
defineExpose({ validate, apply });
</script>
