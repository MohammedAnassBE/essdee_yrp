<!--
  AdvanceSettingsSection — /web port of the Desk IPD "Advance Settings" tab
  (garment IPDs): three groups of plain Link fields — Packing, Stitching,
  Cutting — saved with the document.
  Desk depends_on parity: pack in/out stage need dependent_attribute_mapping;
  stitching in/out stage need stiching_attribute. Stage pickers are restricted
  to the dependent-attribute mapping's values (Desk set_query equivalent via
  essdee_yrp.ipd_ui.get_attribute_detail_values).

  DOCUMENT-level edit mode: `editing` prop from IPDConfigView (one Edit/Save/
  Cancel for the whole IPD); exposes validate() + apply(ipd) for the single save.
-->
<template>
	<section class="panel as-panel">
		<div class="panel-head">
			<h3>Advance Settings</h3>
		</div>

		<div class="as-groups">
			<div v-for="g in groups" :key="g.title" class="as-group">
				<div class="as-gt">{{ g.title }}</div>
				<div class="as-fields">
					<template v-for="f in g.fields" :key="f.field">
						<div v-if="f.visible()" class="as-field">
							<span class="al">{{ f.label }}</span>
							<!-- Commit on SELECT; clearing is allowed (empty commits ""). -->
							<LinkField
								v-if="editing"
								:model-value="form[f.field]"
								:target-doctype="f.doctype"
								:search-handler="f.stagePick ? stageSearch : f.attrPick ? attrSearch : undefined"
								class="as-link"
								:data-testid="'as-' + f.field"
								@item-select="(e) => (form[f.field] = e.value)"
								@update:model-value="(v) => { if (!v) form[f.field] = '' }"
							/>
							<span v-else class="av">{{ doc[f.field] || "—" }}</span>
						</div>
					</template>
				</div>
			</div>
		</div>
	</section>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import LinkField from "@/components/LinkField.vue";
import { callMethod } from "@/api/client";

const props = defineProps({
	doc: { type: Object, required: true },
	editing: { type: Boolean, default: false },
});

const form = ref({});

const FIELDS = [
	"packing_process",
	"packing_attribute",
	"pack_in_stage",
	"pack_out_stage",
	"stiching_process",
	"stiching_attribute",
	"stiching_in_stage",
	"stiching_out_stage",
	"cutting_process",
];

// Desk depends_on: stage pickers appear only once their driver is set.
const groups = [
	{
		title: "Packing",
		fields: [
			{ field: "packing_process", label: "Process", doctype: "Process", visible: () => true },
			{ field: "packing_attribute", label: "Attribute *", doctype: "Item Attribute", attrPick: true, visible: () => true },
			{
				field: "pack_in_stage",
				label: "In stage",
				doctype: "Item Attribute Value",
				stagePick: true,
				visible: () => !!props.doc.dependent_attribute_mapping,
			},
			{
				field: "pack_out_stage",
				label: "Out stage",
				doctype: "Item Attribute Value",
				stagePick: true,
				visible: () => !!props.doc.dependent_attribute_mapping,
			},
		],
	},
	{
		title: "Stitching",
		fields: [
			{ field: "stiching_process", label: "Process", doctype: "Process", visible: () => true },
			{ field: "stiching_attribute", label: "Attribute", doctype: "Item Attribute", attrPick: true, visible: () => true },
			{
				field: "stiching_in_stage",
				label: "In stage",
				doctype: "Item Attribute Value",
				stagePick: true,
				visible: () => !!(props.editing ? form.value.stiching_attribute : props.doc.stiching_attribute),
			},
			{
				field: "stiching_out_stage",
				label: "Out stage",
				doctype: "Item Attribute Value",
				stagePick: true,
				visible: () => !!(props.editing ? form.value.stiching_attribute : props.doc.stiching_attribute),
			},
		],
	},
	{
		title: "Cutting",
		fields: [{ field: "cutting_process", label: "Process", doctype: "Process", visible: () => true }],
	},
];

function hydrate() {
	const f = {};
	FIELDS.forEach((k) => {
		f[k] = props.doc[k] || "";
	});
	form.value = f;
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

// Stage values = the DEPENDENT attribute's Item Item Attribute Mapping values
// (Desk parity: frm uses the item_attributes row whose attribute is
// doc.dependent_attribute — NOT the Item Dependent Attribute Mapping doc,
// which get_attribute_detail_values cannot resolve).
const dependentMapping = computed(() => {
	const row = (props.doc.item_attributes || []).find(
		(a) => a.attribute === props.doc.dependent_attribute,
	);
	return row?.mapping || null;
});

async function stageSearch(q) {
	const mapping = dependentMapping.value;
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

// Attribute pickers offer only the doc's own item_attributes (Desk setAttributeQuery).
async function attrSearch(q) {
	const txt = (q || "").toLowerCase();
	return (props.doc.item_attributes || [])
		.map((a) => a.attribute)
		.filter((a) => a && a.toLowerCase().includes(txt))
		.map((a) => ({ name: a }));
}

// ── document-level save contract (called by IPDConfigView) ──
function validate() {
	// mandatory_depends_on parity (garment IPD): packing attribute is required.
	// (pack/stitch stage fields stay server-enforced — hidden auto-mapping.)
	if (!props.doc.is_cloth_item && !form.value.packing_attribute) {
		return "Packing attribute is required";
	}
	return null;
}
function apply(ipd) {
	FIELDS.forEach((k) => {
		ipd[k] = form.value[k] || null;
	});
}
defineExpose({ validate, apply });
</script>
