<!--
  ClothAccessorySection — /web port of the Desk IPD "Cloth Accessory" tab.

  Desk parity (item_production_detail.js + AccessoryItems / ClothAccessory /
  ClothAccessoryCombination widgets):
    - Accessory list = accessory_clothtype_json ({accessory: part|null}) with an
      add flow (name + part when set item) and per-row delete.
    - Accessory combination (cloth_accessory_json) = the checkbox-driven pivot:
      tick attributes → ipd_ui.get_combination(doc, attrs, "Accessory"); checked
      attribute + Accessory columns display-only, Dia/Weight enterable.
    - Stiching accessory (stiching_accessory_json) = one row per accessory ×
      colour via ipd_ui.get_stiching_accessory_combination: the user only picks
      the Accessory Colour (packing values) and Cloth (from cloth details),
      with fill-down for both (Desk "Fill"). Never a raw child table or JSON.
  Save contract: accessory_attributes child rows + the three JSON doc fields —
  each grid JSON written ONLY when hydrated and non-empty (Desk validate
  parity); the accessory list dict is always written (Desk writes it whenever
  the widget exists).

  DOCUMENT-level edit mode: `editing` prop from IPDConfigView (one Edit/Save/
  Cancel for the whole IPD); exposes validate() + apply(ipd) for the single save.
-->
<template>
	<section class="panel ca-panel">
		<div class="panel-head">
			<h3>Cloth Accessory</h3>
			<span class="panel-meta">{{ Object.keys(accessories).length }} accessorie(s)</span>
		</div>

		<div v-if="!gatesOk" class="pk-empty">
			Fill the cloth details (Cutting) and the stitching input stage / dependent
			attribute (Advance Settings) first.
		</div>

		<!-- Accessory list (accessory_clothtype_json) -->
		<div v-if="gatesOk" class="ca-block">
			<div class="pk-block-head"><span class="pk-bt">Accessories</span></div>
			<table v-if="Object.keys(accessories).length" class="pk-table ca-list" data-testid="ca-list">
				<thead>
					<tr>
						<th>Accessory</th>
						<th v-if="doc.is_set_item">Part</th>
						<th v-if="editing" class="act" />
					</tr>
				</thead>
				<tbody>
					<tr v-for="(part, name) in accessories" :key="name">
						<td>{{ name }}</td>
						<td v-if="doc.is_set_item">{{ part || "—" }}</td>
						<td v-if="editing" class="act">
							<button class="ca-rm" type="button" title="Remove" @click="removeAccessory(name)">×</button>
						</td>
					</tr>
				</tbody>
			</table>
			<div v-else class="pk-empty">No accessories</div>
			<div v-if="editing" class="ca-add">
				<input v-model="newAccessory" class="ca-text" placeholder="Accessory name" data-testid="ca-newname" />
				<LinkField
					v-if="doc.is_set_item"
					:model-value="newPart"
					target-doctype="Item Attribute Value"
					:search-handler="setValueSearch"
					class="ca-link"
					placeholder="Part"
					@item-select="(e) => (newPart = e.value)"
				/>
				<Button size="small" text label="+ Add" data-testid="ca-add" @click="addAccessory" />
			</div>
		</div>

		<!-- Accessory combination (cloth_accessory_json) -->
		<CombinationPivot
			v-if="gatesOk && hasAccessories"
			title="Accessory combination"
			test-id="ca-comb"
			:editing="editing"
			:options="attrOptions"
			v-model:checked="accChecked"
			:grid="accGrid"
			:read-only-columns="accChecked"
			:mapping-search="packValueSearch"
			:select-options="clothNames"
			:building="buildingAcc"
			@build="buildAccessory"
		/>

		<!-- Stiching accessory (stiching_accessory_json) -->
		<div v-if="gatesOk && hasAccessories" class="ca-block">
			<div class="pk-block-head">
				<span class="pk-bt">Stiching accessory</span>
				<Button
					v-if="editing"
					size="small"
					text
					label="Build"
					data-testid="ca-stichacc-build"
					:loading="buildingStich"
					@click="buildStichAccessory"
				/>
			</div>
			<div v-if="stichGrid && (stichGrid.items || []).length" class="ca-scroll">
				<table class="pk-table" data-testid="ca-stichacc">
					<thead>
						<tr>
							<th>Accessory</th>
							<th v-if="stichGrid.is_set_item">{{ stichGrid.set_attr }}</th>
							<th>Major colour</th>
							<th>
								<div>Accessory colour</div>
								<div v-if="editing" class="ca-fill">
									<LinkField
										:model-value="fillColour"
										target-doctype="Item Attribute Value"
										:search-handler="packValueSearch"
										class="ca-link"
										@item-select="(e) => (fillColour = e.value)"
									/>
									<button class="ca-fillbtn" type="button" @click="fillAll('accessory_colour', fillColour)">Fill</button>
								</div>
							</th>
							<th>
								<div>Cloth</div>
								<div v-if="editing" class="ca-fill">
									<Select v-model="fillCloth" :options="clothNames" size="small" class="ca-select" />
									<button class="ca-fillbtn" type="button" @click="fillAll('cloth_type', fillCloth)">Fill</button>
								</div>
							</th>
						</tr>
					</thead>
					<tbody>
						<tr v-for="(row, ri) in stichGrid.items" :key="ri">
							<td>{{ row.accessory }}</td>
							<td v-if="stichGrid.is_set_item">{{ row[stichGrid.set_attr] || "—" }}</td>
							<td>
								{{ row.major_colour }}
								<span v-if="row.major_attr_value" class="ca-muted">({{ row.major_attr_value }})</span>
							</td>
							<td>
								<!-- Commit on SELECT only — typed text never lands in the JSON. -->
							<LinkField
									v-if="editing"
									:model-value="row.accessory_colour || ''"
									target-doctype="Item Attribute Value"
									:search-handler="packValueSearch"
									class="ca-link"
									@item-select="(e) => (row.accessory_colour = e.value)"
								/>
								<span v-else>{{ row.accessory_colour || "—" }}</span>
							</td>
							<td>
								<Select
									v-if="editing"
									v-model="row.cloth_type"
									:options="clothNames"
									size="small"
									class="ca-select"
								/>
								<span v-else>{{ row.cloth_type || "—" }}</span>
							</td>
						</tr>
					</tbody>
				</table>
			</div>
			<div v-else class="pk-empty">No stiching accessory rows yet</div>
		</div>
	</section>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import Button from "primevue/button";
import Select from "primevue/select";
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

const buildingAcc = ref(false);
const buildingStich = ref(false);
const accessories = ref({});
const newAccessory = ref("");
const newPart = ref("");
const attrOptions = ref([]);
const accChecked = ref([]);
const accGrid = ref(null);
const stichGrid = ref(null);
let storedAccChecked = 0;
const fillColour = ref("");
const fillCloth = ref("");

const hasAccessories = computed(() => Object.keys(accessories.value).length > 0);
// Desk mounts the accessory widgets only when the stitching input stage +
// dependent attribute are set AND cloth details exist.
const gatesOk = computed(
	() => !!props.doc.stiching_in_stage && !!props.doc.dependent_attribute && clothNames.value.length > 0,
);

const packingMapping = computed(() => {
	const row = (props.doc.item_attributes || []).find((a) => a.attribute === props.doc.packing_attribute);
	return row?.mapping || null;
});
const setMapping = computed(() => {
	const row = (props.doc.item_attributes || []).find((a) => a.attribute === props.doc.set_item_attribute);
	return row?.mapping || null;
});
const packValueSearch = (q) => mappingSearch(packingMapping.value)(q);
const setValueSearch = (q) => mappingSearch(setMapping.value)(q);
const clothNames = computed(() =>
	(props.doc.cloth_detail || []).map((r) => r.name1).filter(Boolean),
);

// Corrupt stored JSON must BLOCK the save (m5) instead of silently
// hydrating to a fallback and overwriting recoverable data.
let corruptJson = null;
function parseJson(v, fallback, label) {
	if (!v) return fallback;
	if (typeof v === "string") {
		try {
			return JSON.parse(v);
		} catch {
			corruptJson = corruptJson || label;
			return fallback;
		}
	}
	return v;
}

// IMP-2: attribute-row names ride hydrate → apply (no delete+recreate churn).
let accAttrRowNames = {};
// IMP-5: an accessory-list change invalidates the built grids — the baseline
// snapshot + rebuilt flags force a rebuild before save (SetItem basis pattern).
let accessoriesBaseline = "{}";
let accRebuilt = false;
let stichRebuilt = false;
// Version-noise guards: skip writing JSONs that haven't actually changed.
let accGridBaseline = "null";
let stichGridBaseline = "null";
async function hydrate() {
	const d = props.doc;
	corruptJson = null;
	accRebuilt = false;
	stichRebuilt = false;
	accessories.value = parseJson(d.accessory_clothtype_json, {}, "Accessories") || {};
	accessoriesBaseline = stableStringify(accessories.value);
	accChecked.value = (d.accessory_attributes || []).map((r) => r.attribute).filter(Boolean);
	accAttrRowNames = Object.fromEntries((d.accessory_attributes || []).map((r) => [r.attribute, r.name]));
	storedAccChecked = accChecked.value.length;
	const ag = parseJson(d.cloth_accessory_json, null, "Accessory combination");
	accGrid.value = ag && (ag.items || []).length ? ag : null;
	accGridBaseline = stableStringify(accGrid.value);
	const sg = parseJson(d.stiching_accessory_json, null, "Stiching accessory");
	stichGrid.value = sg && (sg.items || []).length ? sg : null;
	// Mirror apply()'s candidate shape (select_list appended) — see CuttingSection.
	stichGridBaseline = stableStringify(
		stichGrid.value ? { ...stichGrid.value, select_list: clothNames.value } : null,
	);
	newAccessory.value = "";
	newPart.value = "";
	if (!attrOptions.value.length && d.stiching_in_stage && d.dependent_attribute) {
		try {
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

function addAccessory() {
	const name = (newAccessory.value || "").trim();
	if (!name) {
		toast.error("Missing", "Enter the accessory name");
		return;
	}
	if (props.doc.is_set_item && !newPart.value) {
		toast.error("Missing", `Enter the ${props.doc.set_item_attribute} value`);
		return;
	}
	accessories.value = { ...accessories.value, [name]: props.doc.is_set_item ? newPart.value : null };
	newAccessory.value = "";
	newPart.value = "";
}
function removeAccessory(name) {
	const next = { ...accessories.value };
	delete next[name];
	accessories.value = next;
}

// IMP-3: last-request-wins generations for both builds (rapid toggles).
let accBuildGen = 0;
let stichBuildGen = 0;
async function buildAccessory(evt) {
	if (!accChecked.value.length) {
		// Untick-all deliberate clear: silent when toggle-driven (m1).
		accBuildGen++;
		accGrid.value = null;
		if (!evt?.fromToggle) toast.error("No attributes", "Tick the attributes to make the combination");
		return;
	}
	const g = ++accBuildGen;
	buildingAcc.value = true;
	try {
		const res = await callMethod("essdee_yrp.ipd_ui.get_combination", {
			doc_name: props.doc.name,
			attributes: accChecked.value,
			combination_type: "Accessory",
		});
		if (g === accBuildGen) {
			accGrid.value = res;
			accRebuilt = true;
		}
	} catch (e) {
		toast.error("Build failed", e.message);
	} finally {
		buildingAcc.value = false;
	}
}

async function buildStichAccessory() {
	const g = ++stichBuildGen;
	buildingStich.value = true;
	try {
		const res = await callMethod("essdee_yrp.ipd_ui.get_stiching_accessory_combination", {
			cloth_list: clothNames.value,
			doc_name: props.doc.name,
		});
		if (g === stichBuildGen) {
			stichGrid.value = res;
			stichRebuilt = true;
		}
	} catch (e) {
		toast.error("Build failed", e.message);
	} finally {
		buildingStich.value = false;
	}
}

function fillAll(key, value) {
	if (!value) return;
	(stichGrid.value?.items || []).forEach((row) => {
		row[key] = value;
	});
}

// ── document-level save contract (called by IPDConfigView) ──
function validate() {
	if (corruptJson) {
		return `${corruptJson}: stored data is unreadable — fix it in Desk before saving here`;
	}
	// IMP-5: adding/removing an accessory invalidates the built grids — require
	// a rebuild before save (mirrors the SetItem changed-basis rule).
	if (stableStringify(accessories.value) !== accessoriesBaseline) {
		if (accGrid.value && !accRebuilt) return "Accessories changed — build the accessory combination again first";
		if (stichGrid.value && !stichRebuilt) return "Accessories changed — build the stiching accessory again first";
	}
	if (accGrid.value) {
		const blank = findBlankCell(accGrid.value.items, accGrid.value.attributes);
		if (blank) return `Accessory combination: fill all the combinations (${blank})`;
	}
	if (stichGrid.value) {
		for (const row of stichGrid.value.items || []) {
			if (!row.accessory_colour || !row.cloth_type) {
				return "Stiching accessory: fill all the combinations";
			}
			if (!clothNames.value.includes(row.cloth_type)) {
				return "Stiching accessory: some cloths are not in the cloth details list";
			}
		}
	}
	return null;
}
function apply(ipd) {
	// Desk writes the accessory dict whenever the widget exists; we narrow that
	// to actual changes so untouched saves stay Version-clean.
	if (stableStringify(accessories.value) !== accessoriesBaseline) {
		ipd.accessory_clothtype_json = accessories.value;
	}
	ipd.accessory_attributes = accChecked.value.map((a) => ({
		doctype: "Cutting Attribute Detail",
		...(accAttrRowNames[a] ? { name: accAttrRowNames[a] } : {}),
		attribute: a,
	}));
	// Grid JSONs only when hydrated (Desk validate parity — never wipe stored
	// data with an unopened view).
	if (!accChecked.value.length && storedAccChecked > 0) {
		// Unticking every attribute is a deliberate clear (Desk on_change {}).
		ipd.cloth_accessory_json = {};
	} else if (
		accGrid.value &&
		(accGrid.value.items || []).length &&
		stableStringify(accGrid.value) !== accGridBaseline
	) {
		ipd.cloth_accessory_json = accGrid.value;
	}
	if (stichGrid.value && (stichGrid.value.items || []).length) {
		const candidate = { ...stichGrid.value, select_list: clothNames.value };
		if (stableStringify(candidate) !== stichGridBaseline) ipd.stiching_accessory_json = candidate;
	}
}
defineExpose({ validate, apply });
</script>
