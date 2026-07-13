<!--
  StichingSection — /web port of the Desk IPD "Stiching" tab (garment IPDs).

  Desk parity (item_production_detail.js + CombinationItemDetail + BundleGroup):
    - Header: stiching_major_attribute_value (restricted to the stiching
      attribute's mapping), is_same_packing_attribute.
    - Panels table = stiching_item_details child rows (panel, qty, category,
      + set part / default when is_set_item). "Fetch panels" = Desk
      get_stiching_attribute_values → ipd_ui.get_mapping_attribute_values.
    - "Build combination" = Desk get_stiching_item_combination →
      ipd_ui.get_new_combination(stich mapping, packing rows, major panel,
      is_same_packing_attribute, doc_name). The grid (columns = panels, one row
      per packing value, cells pick packing values; the major panel's column is
      display-only) is the combination VIEW — never the raw child table.
    - Bundle groups = cutting_marker_groups displayed/edited as panel groups;
      saved through the transient `marker_details` (Desk BundleGroup contract:
      no duplicate panel across groups; group all panels or none).
  Save contract: stiching_item_details child rows + transient
  `stiching_item_detail` JSON (only when the grid is hydrated — never wipes
  stored combinations) + `marker_details`. Stored combination rows are read
  back via fetch_combination_items (same transform the Desk onload uses).

  DOCUMENT-level edit mode: `editing` prop from IPDConfigView (one Edit/Save/
  Cancel for the whole IPD); exposes validate() + apply(ipd) for the single save.
-->
<template>
	<section class="panel st-panel">
		<div class="panel-head">
			<h3>Stiching</h3>
			<span class="panel-meta">{{ rows.length }} panel(s)</span>
		</div>

		<div class="st-facts">
			<div class="pf">
				<span class="pl">Attribute</span>
				<span class="pv">{{ doc.stiching_attribute || "—" }}</span>
			</div>
			<div v-if="doc.stiching_attribute" class="pf">
				<span class="pl">Major panel</span>
				<LinkField
					v-if="editing"
					:model-value="form.stiching_major_attribute_value"
					target-doctype="Item Attribute Value"
					:search-handler="stichValueSearch"
					class="st-link"
					data-testid="st-major"
					@item-select="(e) => (form.stiching_major_attribute_value = e.value)"
				/>
				<span v-else class="pv">{{ doc.stiching_major_attribute_value || "—" }}</span>
			</div>
			<div class="pf">
				<span class="pl">Same packing value</span>
				<input v-if="editing" v-model="form.is_same_packing_attribute" type="checkbox" data-testid="st-same" />
				<span v-else class="pv">{{ doc.is_same_packing_attribute ? "Yes" : "No" }}</span>
			</div>
		</div>

		<!-- Panels table (stiching_item_details) -->
		<div class="st-block">
			<div class="pk-block-head">
				<span class="pk-bt">Panels</span>
				<Button
					v-if="editing && form.stiching_major_attribute_value"
					size="small"
					text
					label="Fetch panels"
					data-testid="st-fetch"
					:loading="fetching"
					@click="fetchPanels"
				/>
			</div>
			<table class="pk-table" data-testid="st-panels">
				<thead>
					<tr>
						<th>Panel</th>
						<th class="num">Qty</th>
						<th>Category <span class="req">*</span></th>
						<th v-if="doc.is_set_item">Part <span class="req">*</span></th>
						<th v-if="doc.is_set_item" class="num">Default</th>
						<th v-if="editing" class="act" />
					</tr>
				</thead>
				<tbody>
					<tr v-for="(r, i) in rows" :key="i">
						<td>
							<LinkField
								v-if="editing"
								:model-value="r.stiching_attribute_value || ''"
								target-doctype="Item Attribute Value"
								:search-handler="stichValueSearch"
								class="st-link"
								@item-select="(e) => (r.stiching_attribute_value = e.value)"
							/>
							<span v-else>{{ r.stiching_attribute_value }}</span>
						</td>
						<td class="num">
							<input v-if="editing" v-model.number="r.quantity" type="number" min="0" class="st-num" />
							<span v-else>{{ r.quantity }}</span>
						</td>
						<td>
							<Select
								v-if="editing"
								v-model="r.category"
								:options="CATEGORIES"
								size="small"
								class="st-cat"
							/>
							<span v-else>{{ r.category }}</span>
						</td>
						<td v-if="doc.is_set_item">
							<LinkField
								v-if="editing"
								:model-value="r.set_item_attribute_value || ''"
								target-doctype="Item Attribute Value"
								:search-handler="setValueSearch"
								class="st-link"
								@item-select="(e) => (r.set_item_attribute_value = e.value)"
							/>
							<span v-else>{{ r.set_item_attribute_value }}</span>
						</td>
						<td v-if="doc.is_set_item" class="num">
							<input v-if="editing" v-model="r.is_default" type="checkbox" />
							<span v-else>{{ r.is_default ? "Yes" : "" }}</span>
						</td>
						<td v-if="editing" class="act">
							<button class="st-rm" type="button" title="Remove" @click="rows.splice(i, 1)">×</button>
						</td>
					</tr>
					<tr v-if="!rows.length">
						<td :colspan="editing ? 6 : 5" class="pk-empty">No panels</td>
					</tr>
				</tbody>
			</table>
			<Button
				v-if="editing"
				size="small"
				text
				label="+ Row"
				@click="rows.push({ stiching_attribute_value: '', quantity: 0, category: '', set_item_attribute_value: '', is_default: false })"
			/>
		</div>

		<!-- Combination grid -->
		<div class="st-block">
			<div class="pk-block-head">
				<span class="pk-bt">Combination</span>
				<Button
					v-if="editing"
					size="small"
					text
					label="Build combination"
					data-testid="st-build"
					:loading="building"
					@click="buildCombination"
				/>
			</div>
			<table v-if="grid && (grid.values || []).length" class="pk-table st-table" data-testid="st-grid">
				<thead>
					<tr>
						<th v-for="a in grid.attributes" :key="a">{{ a }}</th>
					</tr>
				</thead>
				<tbody>
					<tr v-for="(row, ri) in grid.values" :key="ri">
						<td v-for="a in grid.attributes" :key="a">
							<!-- Desk parity: the major panel's column is display-only. -->
							<span v-if="a === form.stiching_major_attribute_value">{{ row.val[a] || "—" }}</span>
							<!-- Commit on SELECT only — free-typed text never lands in the
							     combination JSON (no server validation behind it). -->
							<LinkField
								v-else-if="editing"
								:model-value="row.val[a] || ''"
								target-doctype="Item Attribute Value"
								:search-handler="packValueSearch"
								class="st-link"
								@item-select="(e) => (row.val[a] = e.value)"
							/>
							<span v-else>{{ row.val[a] || "—" }}</span>
						</td>
					</tr>
				</tbody>
			</table>
			<div v-else class="pk-empty">No combination yet</div>
		</div>

		<!-- Bundle groups (cutting markers) -->
		<div class="st-block">
			<div class="pk-block-head"><span class="pk-bt">Bundle groups</span></div>
			<table v-if="groups.length" class="pk-table" data-testid="st-groups">
				<thead>
					<tr>
						<th>Panels</th>
						<th v-if="editing" class="act" />
					</tr>
				</thead>
				<tbody>
					<tr v-for="(g, gi) in groups" :key="gi">
						<td>
							<MultiSelect
								v-if="editing"
								v-model="g.selected"
								:options="panelOptions"
								display="chip"
								size="small"
								class="st-ms"
							/>
							<span v-else>{{ g.selected.join(", ") }}</span>
						</td>
						<td v-if="editing" class="act">
							<button class="st-rm" type="button" title="Remove" @click="groups.splice(gi, 1)">×</button>
						</td>
					</tr>
				</tbody>
			</table>
			<div v-else class="pk-empty">No groups</div>
			<Button v-if="editing" size="small" text label="+ Group" @click="groups.push({ selected: [] })" />
		</div>
	</section>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import Button from "primevue/button";
import Select from "primevue/select";
import MultiSelect from "primevue/multiselect";
import LinkField from "@/components/LinkField.vue";
import { callMethod } from "@/api/client";
import { useAppToast } from "@/composables/useToast";
import { mappingSearch, stableStringify } from "./combinationCells";

const props = defineProps({
	doc: { type: Object, required: true },
	editing: { type: Boolean, default: false },
});

const toast = useAppToast();

const CATEGORIES = ["Body", "Cut & Sew", "Main Panel", "Placket", "Shorts", "Rib"];

const fetching = ref(false);
const building = ref(false);
const form = ref({});
const rows = ref([]);
const grid = ref(null);
const groups = ref([]);

// Desk declarations(): the mappings of the stiching / set / packing attributes.
const stichMapping = computed(() => {
	const row = (props.doc.item_attributes || []).find((a) => a.attribute === props.doc.stiching_attribute);
	return row?.mapping || null;
});
const setMapping = computed(() => {
	const row = (props.doc.item_attributes || []).find((a) => a.attribute === props.doc.set_item_attribute);
	return row?.mapping || null;
});
const packingMapping = computed(() => {
	const row = (props.doc.item_attributes || []).find((a) => a.attribute === props.doc.packing_attribute);
	return row?.mapping || null;
});
const stichValueSearch = (q) => mappingSearch(stichMapping.value)(q);
const setValueSearch = (q) => mappingSearch(setMapping.value)(q);
const packValueSearch = (q) => mappingSearch(packingMapping.value)(q);

const panelOptions = computed(() =>
	rows.value.map((r) => r.stiching_attribute_value).filter(Boolean),
);

// Generation guard: a Build clicked before the stored-grid fetch resolves must
// not be overwritten by the late fetch result.
let gen = 0;
let storedGroupCount = 0;
let panelsBaseline = "";
let gridRebuilt = false;
// Version-noise guards: transient JSONs trigger server-side rebuilds — send
// them only when the underlying view actually changed.
let gridBaseline = "null";
let groupsBaseline = "[]";
const panelsKey = () =>
	rows.value
		.map((r) => `${r.stiching_attribute_value}|${r.set_item_attribute_value}`)
		.filter((k) => k !== "|")
		.join(",");
async function hydrate() {
	const g = ++gen;
	const d = props.doc;
	form.value = {
		stiching_major_attribute_value: d.stiching_major_attribute_value || "",
		is_same_packing_attribute: !!d.is_same_packing_attribute,
	};
	rows.value = (d.stiching_item_details || []).map((r) => ({
		name: r.name, // IMP-2: untouched rows round-trip in place
		stiching_attribute_value: r.stiching_attribute_value,
		quantity: r.quantity ?? 0,
		category: r.category || "Body",
		set_item_attribute_value: r.set_item_attribute_value || "",
		is_default: !!r.is_default,
	}));
	// IMP-5: the combination grid's columns ARE the panels — a panel/part
	// change invalidates it (SetItem changed-basis rule).
	panelsBaseline = panelsKey();
	gridRebuilt = false;
	groups.value = (d.cutting_marker_groups || []).map((g) => ({
		selected: (g.group_panels || "").split(",").filter(Boolean),
	}));
	storedGroupCount = groups.value.length;
	groupsBaseline = stableStringify(groups.value);
	grid.value = null;
	gridBaseline = "null";
	if ((d.stiching_item_combination_details || []).length) {
		try {
			const res = await callMethod("essdee_yrp.ipd_ui.fetch_combination_items", {
				combination_items: d.stiching_item_combination_details,
			});
			if (g === gen) {
				grid.value = res;
				gridBaseline = stableStringify(grid.value);
			}
		} catch (e) {
			toast.error("Combination unavailable", e.message);
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

async function fetchPanels() {
	if (!stichMapping.value) {
		toast.error("No mapping", "Set the stiching attribute first (Advance Settings).");
		return;
	}
	fetching.value = true;
	try {
		const res = await callMethod("essdee_yrp.ipd_ui.get_mapping_attribute_values", {
			attribute_mapping_value: stichMapping.value,
			attribute_no: null,
		});
		rows.value = (res || []).map((r) => ({
			stiching_attribute_value: r.stiching_attribute_value,
			quantity: 0,
			category: "",
			set_item_attribute_value: "",
			is_default: false,
		}));
	} catch (e) {
		toast.error("Fetch failed", e.message);
	} finally {
		fetching.value = false;
	}
}

async function buildCombination() {
	// Desk get_stiching_item_combination guards.
	if (!props.doc.stiching_attribute) return;
	if (!form.value.stiching_major_attribute_value) {
		toast.error("Missing", "Set the major panel first");
		return;
	}
	if (!rows.value.length) {
		toast.error("Missing", "Set the panels first");
		return;
	}
	building.value = true;
	gen++; // a pending hydrate fetch must not stomp the fresh build
	try {
		const res = await callMethod("essdee_yrp.ipd_ui.get_new_combination", {
			attribute_mapping_value: stichMapping.value,
			packing_attribute_details: props.doc.packing_attribute_details || [],
			major_attribute_value: form.value.stiching_major_attribute_value,
			is_same_packing_attribute: form.value.is_same_packing_attribute ? 1 : 0,
			doc_name: props.doc.name,
		});
		grid.value = res || null;
		gridRebuilt = true;
	} catch (e) {
		toast.error("Build failed", e.message);
	} finally {
		building.value = false;
	}
}

function validateGroups() {
	// Desk BundleGroup.get_items(): no panel twice; group all panels or none.
	const seen = [];
	for (const g of groups.value) {
		for (const p of g.selected) {
			if (seen.includes(p)) return `Panel ${p} is grouped multiple times`;
			seen.push(p);
		}
	}
	// Compare against the FILLED panel rows — a blank draft row must not make
	// "group all panels" unreachable.
	const filled = rows.value.filter((r) => r.stiching_attribute_value).length;
	if (seen.length && seen.length !== filled) return "Select all the panels";
	return null;
}

function rowIsBlank(r) {
	return !r.stiching_attribute_value && !r.quantity && !r.category && !r.set_item_attribute_value && !r.is_default;
}
const activeRows = () => rows.value.filter((r) => !rowIsBlank(r));

// ── document-level save contract (called by IPDConfigView) ──
function validate() {
	// Desk blocks incomplete child rows with reqd errors — never silently drop
	// them. Fully blank draft rows are ignored; row numbers reference the
	// VISIBLE positions (blank drafts counted).
	const bad = (pred) =>
		rows.value.map((r, i) => (!rowIsBlank(r) && pred(r) ? i + 1 : 0)).filter(Boolean);
	const badPanel = bad((r) => !r.stiching_attribute_value);
	if (badPanel.length) return `Row(s) ${badPanel.join(", ")}: panel value is required`;
	const badCat = bad((r) => !r.category);
	if (badCat.length) return `Row(s) ${badCat.join(", ")}: category is required`;
	const active = activeRows();
	if (props.doc.is_set_item) {
		// Desk updateChildTableReqd: Part (+ default choice) required for set items.
		const badPart = bad((r) => !r.set_item_attribute_value);
		if (badPart.length) return `Row(s) ${badPart.join(", ")}: part is required for a set item`;
		const parts = [...new Set(active.map((r) => r.set_item_attribute_value))];
		const noDefault = parts.filter((p) => !active.some((r) => r.set_item_attribute_value === p && r.is_default));
		if (noDefault.length) return `Mark a default panel for: ${noDefault.join(", ")}`;
	}
	// IMP-5: panels changed since hydrate → the hydrated combination grid is
	// built on the OLD panel set; require a rebuild before save.
	if (grid.value && !gridRebuilt && panelsKey() !== panelsBaseline) {
		return "Panels changed — build the combination again first";
	}
	if (grid.value) {
		for (const row of grid.value.values || []) {
			for (const a of grid.value.attributes || []) {
				if (!row.val[a]) return "Fill all the combinations";
			}
		}
	}
	return validateGroups();
}
function apply(ipd) {
	ipd.stiching_major_attribute_value = form.value.stiching_major_attribute_value || "";
	ipd.is_same_packing_attribute = form.value.is_same_packing_attribute ? 1 : 0;
	ipd.stiching_item_details = activeRows()
		.filter((r) => r.stiching_attribute_value)
		.map((r) => ({
			doctype: "Stiching Item Detail",
			...(r.name ? { name: r.name } : {}),
			stiching_attribute_value: r.stiching_attribute_value,
			quantity: r.quantity || 0,
			category: r.category || "Body",
			set_item_attribute_value: r.set_item_attribute_value || "",
			is_default: r.is_default ? 1 : 0,
		}));
	// Transient JSONs consumed by the server validate (Desk parity): only when
	// hydrated — never wipe stored data with an unopened view.
	if (grid.value && (grid.value.values || []).length) {
		if (stableStringify(grid.value) !== gridBaseline) {
			ipd.stiching_item_detail = JSON.stringify(grid.value);
		}
	}
	const groupsNow = stableStringify(groups.value);
	if (groups.value.length && groupsNow !== groupsBaseline) {
		ipd.marker_details = groups.value.map((g) => ({ selected: [...g.selected] }));
	} else if (!groups.value.length && storedGroupCount > 0) {
		// Stored groups existed and the user deleted them all: send one empty
		// group so the server clears the table (deliberate improvement over
		// Desk, whose empty-list early-return can never persist a clear).
		ipd.marker_details = [{ selected: [] }];
	}
}
defineExpose({ validate, apply });
</script>
