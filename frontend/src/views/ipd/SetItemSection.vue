<!--
  SetItemSection — /web port of the Desk IPD "Set Item" tab (garment IPDs).

  Desk parity (item_production_detail.js + CombinationItemDetail widget):
    - Header: is_set_item, set_item_attribute (restricted to the doc's own
      item_attributes), major_attribute_value (restricted to the set attribute's
      mapping values).
    - "Build combination" = Desk get_set_item_combination →
      essdee_yrp.ipd_ui.get_new_combination(set mapping, packing rows, major value).
    - The grid is the CHECK-DRIVEN COMBINATION VIEW: one column per set-part,
      one row per packing value; each cell picks a value from the PACKING
      attribute's mapping (Desk cell get_query). Never the raw child table.
  Save contract: the grid is sent as the transient `set_item_detail` JSON on the
  doc (Desk validate does the same); the server's validate rebuilds the
  set_item_combination_details child table. Stored rows are read back through
  the same whitelisted fetch_combination_items the Desk onload uses.

  DOCUMENT-level edit mode: `editing` prop from IPDConfigView (one Edit/Save/
  Cancel for the whole IPD); exposes validate() + apply(ipd) for the single save.
-->
<template>
	<section class="panel si-panel">
		<div class="panel-head">
			<h3>Set Item</h3>
			<span class="panel-meta">{{ grid ? (grid.values || []).length + " row(s)" : "—" }}</span>
		</div>

		<div class="si-facts">
			<div class="pf">
				<span class="pl">Set item</span>
				<input v-if="editing" v-model="form.is_set_item" type="checkbox" data-testid="si-isset" />
				<span v-else class="pv">{{ doc.is_set_item ? "Yes" : "No" }}</span>
			</div>
			<div v-if="form.is_set_item" class="pf">
				<span class="pl">Attribute <span class="req">*</span></span>
				<LinkField
					v-if="editing"
					:model-value="form.set_item_attribute"
					target-doctype="Item Attribute"
					:search-handler="attrSearch"
					class="si-link"
					data-testid="si-attr"
					@item-select="(e) => (form.set_item_attribute = e.value)"
				/>
				<span v-else class="pv">{{ doc.set_item_attribute || "—" }}</span>
			</div>
			<div v-if="form.is_set_item && form.set_item_attribute" class="pf">
				<span class="pl">Major value <span class="req">*</span></span>
				<LinkField
					v-if="editing"
					:model-value="form.major_attribute_value"
					target-doctype="Item Attribute Value"
					:search-handler="setValueSearch"
					class="si-link"
					data-testid="si-major"
					@item-select="(e) => (form.major_attribute_value = e.value)"
				/>
				<span v-else class="pv">{{ doc.major_attribute_value || "—" }}</span>
			</div>
		</div>

		<!-- Combination grid -->
		<div v-if="form.is_set_item" class="si-block">
			<div class="pk-block-head">
				<span class="pk-bt">Combination</span>
				<Button
					v-if="editing && form.set_item_attribute && form.major_attribute_value"
					size="small"
					text
					label="Build combination"
					data-testid="si-build"
					:loading="building"
					@click="buildCombination"
				/>
			</div>
			<table v-if="grid && (grid.values || []).length" class="pk-table si-table" data-testid="si-grid">
				<thead>
					<tr>
						<th v-for="a in grid.attributes" :key="a">{{ a }}</th>
					</tr>
				</thead>
				<tbody>
					<tr v-for="(row, ri) in grid.values" :key="ri">
						<td v-for="a in grid.attributes" :key="a">
							<!-- Commit on SELECT only — free-typed text never lands in the
							     combination JSON (no server validation behind it). -->
							<LinkField
								v-if="editing"
								:model-value="row.val[a] || ''"
								target-doctype="Item Attribute Value"
								:search-handler="packValueSearch"
								class="si-link"
								@item-select="(e) => (row.val[a] = e.value)"
							/>
							<span v-else>{{ row.val[a] || "—" }}</span>
						</td>
					</tr>
				</tbody>
			</table>
			<div v-else class="pk-empty">No combination yet</div>
		</div>
		<div v-else class="pk-empty">Not a set item</div>
	</section>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import Button from "primevue/button";
import LinkField from "@/components/LinkField.vue";
import { callMethod } from "@/api/client";
import { useAppToast } from "@/composables/useToast";
import { mappingSearch, stableStringify } from "./combinationCells";

const props = defineProps({
	doc: { type: Object, required: true },
	editing: { type: Boolean, default: false },
});

const toast = useAppToast();

const building = ref(false);
const form = ref({});
const grid = ref(null); // { attributes: [...parts], values: [{ major_attribute, val: {part: colour} }] }

// Desk declarations(): mapping of the chosen set attribute / packing attribute.
const setMapping = computed(() => {
	const row = (props.doc.item_attributes || []).find((a) => a.attribute === form.value.set_item_attribute);
	return row?.mapping || null;
});
const packingMapping = computed(() => {
	const row = (props.doc.item_attributes || []).find((a) => a.attribute === props.doc.packing_attribute);
	return row?.mapping || null;
});

const setValueSearch = (q) => mappingSearch(setMapping.value)(q);
const packValueSearch = (q) => mappingSearch(packingMapping.value)(q);
// Only the doc's own attributes (Desk setAttributeQuery).
async function attrSearch(q) {
	const attrs = (props.doc.item_attributes || []).map((a) => a.attribute).filter(Boolean);
	const t = (q || "").toLowerCase();
	return attrs.filter((a) => a.toLowerCase().includes(t)).map((a) => ({ name: a }));
}

// Generation guard: a Build clicked before the stored-grid fetch resolves must
// not be overwritten by the late fetch result.
let gen = 0;
// Version-noise guard: the transient set_item_detail triggers a server-side
// rebuild of the combination child table — only send it when the grid really
// changed, or every save deletes+recreates identical rows.
let gridBaseline = "null";
async function hydrate() {
	const g = ++gen;
	const d = props.doc;
	form.value = {
		is_set_item: !!d.is_set_item,
		set_item_attribute: d.set_item_attribute || "",
		major_attribute_value: d.major_attribute_value || "",
	};
	grid.value = null;
	gridBaseline = "null";
	if (d.is_set_item && (d.set_item_combination_details || []).length) {
		try {
			// Same server transform the Desk onload uses on the stored child rows.
			const res = await callMethod("essdee_yrp.ipd_ui.fetch_combination_items", {
				combination_items: d.set_item_combination_details,
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
// Desk regenerates on set_item_attribute / major_attribute_value triggers —
// a changed basis invalidates the current combination, so force a rebuild.
watch(
	() => [form.value.set_item_attribute, form.value.major_attribute_value],
	(next, prev) => {
		if (!props.editing || !prev) return;
		if (next[0] !== prev[0] || next[1] !== prev[1]) grid.value = null;
	},
);

async function buildCombination() {
	if (!setMapping.value) {
		toast.error("No mapping", "Pick a set attribute that belongs to this item.");
		return;
	}
	building.value = true;
	gen++; // a pending hydrate fetch must not stomp the fresh build
	try {
		const res = await callMethod("essdee_yrp.ipd_ui.get_new_combination", {
			attribute_mapping_value: setMapping.value,
			packing_attribute_details: props.doc.packing_attribute_details || [],
			major_attribute_value: form.value.major_attribute_value,
		});
		grid.value = res || null;
	} catch (e) {
		toast.error("Build failed", e.message);
	} finally {
		building.value = false;
	}
}

// ── document-level save contract (called by IPDConfigView) ──
function validate() {
	// mandatory_depends_on parity: a set item requires its attribute + major value.
	if (form.value.is_set_item && (!form.value.set_item_attribute || !form.value.major_attribute_value)) {
		return "Set item needs both the attribute and the major value";
	}
	// Desk auto-rebuilds on attribute/major changes; here a changed basis with
	// no rebuilt grid would leave the STORED combination rows (old basis) alive.
	const basisChanged =
		form.value.set_item_attribute !== (props.doc.set_item_attribute || "") ||
		form.value.major_attribute_value !== (props.doc.major_attribute_value || "");
	if (form.value.is_set_item && basisChanged && !grid.value) {
		return "Rebuild needed — Build the combination first";
	}
	// Desk CombinationItemDetail.get_data(): every cell must be filled.
	if (form.value.is_set_item && grid.value) {
		for (const row of grid.value.values || []) {
			for (const a of grid.value.attributes || []) {
				if (!row.val[a]) return "Fill all the combinations";
			}
		}
	}
	return null;
}
function apply(ipd) {
	ipd.is_set_item = form.value.is_set_item ? 1 : 0;
	ipd.set_item_attribute = form.value.is_set_item ? form.value.set_item_attribute || "" : "";
	ipd.major_attribute_value = form.value.is_set_item ? form.value.major_attribute_value || "" : "";
	// Transient field consumed by the server validate (Desk parity): only when
	// the grid is hydrated — never wipe stored combinations with an empty view.
	if (form.value.is_set_item && grid.value && (grid.value.values || []).length) {
		if (stableStringify(grid.value) !== gridBaseline) {
			ipd.set_item_detail = JSON.stringify(grid.value);
		}
	}
}
defineExpose({ validate, apply });
</script>
