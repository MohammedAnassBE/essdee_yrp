<!--
  EmblishmentSection — /web port of the Desk IPD "Emblishment" tab.

  Desk parity: the tab is a single JSON-driven widget — a map of
  { process_name: [panel values] } stored in the doc field
  emblishment_details_json and saved WITH the document. Panels come from the
  stitching attribute's mapping (essdee_yrp.ipd_ui.get_attr_mapping_details).

  DOCUMENT-level edit mode: `editing` prop from IPDConfigView (one Edit/Save/
  Cancel for the whole IPD); exposes validate() + apply(ipd) for the single save.
-->
<template>
	<section class="panel em-panel">
		<div class="panel-head">
			<h3>Emblishment</h3>
			<span class="panel-meta">{{ Object.keys(entries).length }} process(es)</span>
		</div>

		<table v-if="Object.keys(entries).length" class="em-table" data-testid="em-rows">
			<thead>
				<tr><th>Process</th><th>{{ doc.stiching_attribute || "Panels" }}</th><th v-if="editing" class="act" /></tr>
			</thead>
			<tbody>
				<tr v-for="(panels, proc) in entries" :key="proc">
					<td>{{ proc }}</td>
					<td><span v-for="p in panels" :key="p" class="em-chip">{{ p }}</span></td>
					<td v-if="editing" class="act">
						<button class="em-rm" type="button" title="Remove" @click="removeEntry(proc)">×</button>
					</td>
				</tr>
			</tbody>
		</table>
		<div v-else class="em-empty">No emblishment processes</div>

		<!-- Add flow: pick a Process, tick panels, Add -->
		<div v-if="editing" class="em-add">
			<LinkField
				:model-value="newProcess"
				target-doctype="Process"
				placeholder="Process"
				class="em-link"
				@item-select="(e) => (newProcess = e.value)"
				@update:model-value="(v) => { if (!v) newProcess = '' }"
			/>
			<div v-if="newProcess" class="em-checks">
				<label v-for="p in panelOptions" :key="p" class="em-check">
					<input v-model="newPanels" type="checkbox" :value="p" />
					{{ p }}
				</label>
			</div>
			<Button
				v-if="newProcess"
				size="small"
				label="Add"
				data-testid="em-add"
				:disabled="!newPanels.length"
				@click="addEntry"
			/>
		</div>
	</section>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import Button from "primevue/button";
import LinkField from "@/components/LinkField.vue";
import { callMethod } from "@/api/client";
import { stableStringify } from "./combinationCells";
import { useAppToast } from "@/composables/useToast";

const props = defineProps({
	doc: { type: Object, required: true },
	editing: { type: Boolean, default: false },
});

const toast = useAppToast();

const entries = ref({});
const panelOptions = ref([]);
const newProcess = ref("");
const newPanels = ref([]);

// Stitching attribute's mapping (Desk: frm.stiching_attribute_mapping)
const stichingMapping = computed(() => {
	const row = (props.doc.item_attributes || []).find((a) => a.attribute === props.doc.stiching_attribute);
	return row?.mapping || null;
});

let entriesCorrupt = false;
let entriesBaseline = "{}"; // Version-noise guard: skip write when untouched
function hydrate() {
	let j = props.doc.emblishment_details_json;
	entriesCorrupt = false;
	if (typeof j === "string") {
		try {
			j = JSON.parse(j);
		} catch {
			// m5: unreadable stored JSON blocks the save, never overwritten.
			j = null;
			entriesCorrupt = true;
		}
	}
	entries.value = j && typeof j === "object" && !Array.isArray(j) ? { ...j } : {};
	entriesBaseline = stableStringify(entries.value);
	newProcess.value = "";
	newPanels.value = [];
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

// Panels track the CURRENT doc's stitching mapping — the component is reused
// across garment→garment navigation, so a mount-once fetch would show the
// previous IPD's panels.
watch(
	stichingMapping,
	async (mapping) => {
		if (!mapping) {
			panelOptions.value = [];
			return;
		}
		try {
			panelOptions.value =
				(await callMethod("essdee_yrp.ipd_ui.get_attr_mapping_details", { mapping })) || [];
		} catch (e) {
			panelOptions.value = [];
			toast.error("Panels unavailable", e.message);
		}
	},
	{ immediate: true },
);

// Desk parity: picking a process pre-ticks every panel; untick to narrow.
watch(newProcess, (proc) => {
	newPanels.value = proc ? [...panelOptions.value] : [];
});

function addEntry() {
	if (!newProcess.value || !newPanels.value.length) return;
	entries.value = { ...entries.value, [newProcess.value]: [...newPanels.value] };
	newProcess.value = "";
	newPanels.value = [];
}
function removeEntry(proc) {
	const e = { ...entries.value };
	delete e[proc];
	entries.value = e;
}

// ── document-level save contract (called by IPDConfigView) ──
function validate() {
	if (entriesCorrupt) {
		return "Stored emblishment data is unreadable — fix it in Desk before saving here";
	}
	return null;
}
function apply(ipd) {
	if (stableStringify(entries.value) !== entriesBaseline) {
		ipd.emblishment_details_json = entries.value;
	}
}
defineExpose({ validate, apply });
</script>
