<!--
  FabricProcessesSection — the /web IPD "Fabric Processes" entry (master half
  of the master-detail), rendered as a panel inside IPDConfigView for cloth
  IPDs (doc.is_cloth_item).

  RE-PORT of the Desk master-detail entry:
    Desk references:
      - essdee_yrp/public/js/Fabric/FabricProcesses.vue (overview cards, add
        bar, openEdit reverse-mapping + guards, writeBack payload — the
        byte-truth for behavior, 2026-07-07 UI rebuild)
      - essdee_yrp/public/js/item_production_detail.js
        (fabric_processes_payload / fabric_processes_write_back /
        fabric_processes_catalog — how the widget is fed and persisted)

  Byte-faithful (data contracts + behavior):
    - Steps rebuilt from the sibling child tables fabric_processes +
      fabric_value_mappings (sorted by sequence; mappings matched by sequence,
      ordered by mapping_index) — identical to Desk load_data.
    - editable = approval_status !== "Approved" (Desk: frm.is_new() ||
      status !== "Approved"; /web only ever shows saved IPDs).
    - default conversion input = the IPD's yarn_item, NEVER the cloth item;
      attributes = distinct item_attributes[].attribute.
    - Add bar lists ALL Process names minus the ones already used; the shape
      is fetched from essdee_yrp.fabric_ipd.get_process_transform (same
      whitelisted endpoint the Desk xcalls).
    - openEdit guards refuse unrepresentable steps (foreign roles on a
      conversion, multi-attribute holds, >1 Pin per rule, idle with mappings)
      with the Desk's exact reasoning, instead of silently dropping data.
    - Persisted rows identical to Desk fabric_processes_write_back: both
      tables cleared and rewritten from the steps model; matrices regenerate
      server-side on save (fabric_ipd.sync_fabric_process_matrices on_update).

  Adapted for /web:
    - frm write-back + user Ctrl+S → immediate persistence through the SAME
      mechanism IPDConfigView uses for its BOM / process child rows:
      frappe.client.get the full IPD, replace the two child arrays, then
      frappe.client.save; emit "saved" so the parent reloads doc + matrices.
    - frappe.msgprint guard refusals → toast.warn; select → PrimeVue Select.

  Props: { doc } (the loaded IPD document — steps rebuild whenever it changes).
  Emits: saved (after any successful persist — parent reloadView).
-->
<template>
	<section class="panel fabproc">
		<div class="panel-head">
			<h3>Fabric Processes</h3>
			<span class="panel-meta">{{ steps.length }} step(s)</span>
		</div>
		<div class="panel-body">
			<!-- ══════════════ OVERVIEW ══════════════ -->
			<template v-if="view === 'overview'">
				<div v-if="!steps.length" class="fp-empty">
					No fabric processes yet. Add the first step — yarn dyeing, knitting, dyeing, compacting, printing, washing.
				</div>

				<div class="fp-cards">
					<div v-for="(step, si) in steps" :key="step.sequence" class="fp-card" :class="'fp-' + shapeOf(step).key">
						<div class="fp-seq">{{ si + 1 }}</div>
						<div class="fp-name">{{ step.fabric_process || "(no process)" }}</div>
						<span class="fp-badge" :class="'b-' + shapeOf(step).key">{{ shapeOf(step).label }}</span>
						<div class="fp-card-actions">
							<button v-if="editable" class="fp-edit" type="button" data-testid="fp-edit" :data-process="step.fabric_process" :disabled="saving" @click="openEdit(si)">Edit</button>
							<button v-if="editable" class="fp-rm" type="button" data-testid="fp-remove" :data-process="step.fabric_process" title="Remove step" :disabled="saving" @click="removeStep(si)">×</button>
						</div>

						<div class="fp-flow">
							<span class="fp-item">{{ step.input_item || step.output_item }}</span>
							<template v-if="hasConversion(step)">
								<span class="fp-arrow">→</span>
								<span class="fp-item">{{ step.output_item }}</span>
							</template>
							<span v-else class="fp-same">same item</span>
							<span v-if="ratioLabel(step)" class="fp-ratio">{{ ratioLabel(step) }}</span>
						</div>

						<div class="fp-summary">
							<!-- Compact glance-label; full rule detail is in the Edit pop-up. -->
							<span class="fp-summary-text">{{ shortSummaryOf(step) }}</span>
						</div>
					</div>
				</div>

				<div v-if="editable" class="fp-addbar">
					<div class="fp-addbar-field">
						<label>Add a process</label>
						<Select
							v-model="addProcessSel"
							:options="availableProcesses"
							placeholder="Pick a process…"
							filter
							:loading="catalogLoading"
							data-testid="fp-process-select"
							fluid
						/>
					</div>
					<Button
						:label="adding ? 'Reading process…' : 'Add & define →'"
						data-testid="fp-add-btn"
						:disabled="!addProcessSel || adding || saving"
						:loading="adding"
						@click="addProcess"
					/>
				</div>
				<div v-if="!editable" class="fp-locked">
					<i class="pi pi-lock" />
					{{ doc?.approval_status === "Approved"
						? "This IPD is approved — fabric processes are read-only."
						: "You don't have write permission on IPDs — fabric processes are read-only." }}
				</div>
			</template>

			<!-- ══════════════ DETAIL EDITOR ══════════════ -->
			<FabricStepEditor
				v-else-if="view === 'edit' && draft"
				:key="editSession"
				:draft="draft"
				:attributes="attributes"
				:itemName="doc.item || ''"
				:saving="saving"
				@save="onEditorSave"
				@cancel="cancelEdit"
			/>
		</div>
	</section>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import Select from "primevue/select";
import Button from "primevue/button";
import { callMethod, getList } from "@/api/client";
import { useAppToast } from "@/composables/useToast";
import { useAppConfirm } from "@/composables/useConfirm";
import { usePermissions } from "@/composables/usePermissions";
import FabricStepEditor from "./FabricStepEditor.vue";
import {
	blankDraft,
	blankGroup,
	blankRule,
	hasConversion,
	num,
	ratioLabel,
	shapeOf,
	shortSummaryOf,
} from "./fabricShapes";
import { loadValues } from "./fabricValues";

const props = defineProps({
	// The loaded Item Production Detail document (getDoc result). Steps rebuild
	// whenever it changes (immediate watch — never onMounted-once).
	doc: { type: Object, required: true },
});
const emit = defineEmits(["saved"]);

const toast = useAppToast();
const confirm = useAppConfirm();
const { canWrite } = usePermissions();

const steps = ref([]);
const view = ref("overview");
const draft = ref(null);
const editSession = ref(0); // remount key so FabricStepEditor binds one draft per open
const addProcessSel = ref(null);
const adding = ref(false);
const saving = ref(false);

// Desk: editable = frm.is_new() || approval_status !== "Approved". /web only
// renders saved IPDs, so the is_new() half falls away. Also gated on write
// permission — read-only users must not see Edit/Remove/Add at all.
const editable = computed(
	() => props.doc?.approval_status !== "Approved" && canWrite("Item Production Detail"),
);
const attributes = computed(() =>
	[...new Set((props.doc?.item_attributes || []).map((a) => a.attribute).filter(Boolean))],
);
// Conversion input defaults to the IPD's yarn (yarn → cloth); NEVER the cloth
// item — a conversion's input and output must be distinct.
const defaultInput = computed(() => props.doc?.yarn_item || props.doc?.item || null);

// ---- load (Desk load_data: rebuild steps from the sibling child tables) -----
watch(
	() => props.doc,
	(doc) => {
		const maps = doc?.fabric_value_mappings || [];
		steps.value = (doc?.fabric_processes || [])
			.slice()
			.sort((a, b) => num(a.sequence) - num(b.sequence))
			.map((p) => ({
				sequence: num(p.sequence),
				fabric_process: p.fabric_process || "",
				input_item: p.input_item || "",
				output_item: p.output_item || "",
				quantity_ratio: p.quantity_ratio == null ? 1 : Number(p.quantity_ratio),
				mappings: maps
					.filter((m) => num(m.sequence) === num(p.sequence))
					.sort((a, b) => num(a.mapping_index) - num(b.mapping_index))
					.map((m) => ({
						mapping_index: num(m.mapping_index),
						attribute: m.attribute || "",
						role: m.role || "Change",
						from_value: m.from_value || "",
						to_value: m.to_value || "",
					})),
			}));
		// A reload lands back on the overview (fresh doc = fresh truth).
		view.value = "overview";
		draft.value = null;
		addProcessSel.value = null;
		attributes.value.forEach((a) => loadValues(a));
	},
	{ immediate: true },
);

// ---- Process catalog (Desk fabric_processes_catalog: every Process name) ----
const allProcesses = ref([]);
const catalogLoading = ref(false);
async function loadCatalog() {
	catalogLoading.value = true;
	try {
		const { data } = await getList("Process", {
			fields: ["name"],
			order_by: "name asc",
			limit_page_length: 0,
		});
		allProcesses.value = (data || []).map((r) => r.name);
	} catch (e) {
		allProcesses.value = [];
		toast.warn("Processes", e.message);
	} finally {
		catalogLoading.value = false;
	}
}
loadCatalog();

const usedProcesses = computed(() => steps.value.map((s) => s.fabric_process).filter(Boolean));
const availableProcesses = computed(() => allProcesses.value.filter((p) => !usedProcesses.value.includes(p)));

// ---- add / edit navigation ---------------------------------------------------

async function fetchShape(process) {
	try {
		const t = await callMethod("essdee_yrp.fabric_ipd.get_process_transform", { process });
		const key = t.shape === "conversion" ? "conv"
			: t.shape === "swap" || t.shape === "multi_swap" ? "change"
			: "idle";
		return { key, change_attributes: t.change_attributes || [] };
	} catch (_) {
		return { key: "idle", change_attributes: [] };
	}
}

function nextSequence() {
	const seqs = steps.value.map((s) => num(s.sequence)).filter((s) => s > 0);
	return seqs.length ? Math.max(...seqs) + 10 : 10;
}

function openDraft(d) {
	draft.value = d;
	editSession.value += 1;
	view.value = "edit";
}

async function addProcess() {
	if (!addProcessSel.value) return;
	adding.value = true;
	const shape = await fetchShape(addProcessSel.value);
	adding.value = false;
	const seq = nextSequence();
	const d = blankDraft(addProcessSel.value, seq, shape.key, shape.change_attributes, {
		item: props.doc.item || "",
		defaultInput: defaultInput.value || "",
		attributes: attributes.value,
	});
	if (d.shapeKey === "change") {
		if (!d.change_attrs.length) d.change_attrs = [attributes.value[0] || ""].filter(Boolean);
		d.groups = [blankGroup(d.change_attrs)];
	}
	d.introduce.forEach((x) => x.attr && loadValues(x.attr));
	d.change_attrs.forEach((a) => a && loadValues(a));
	addProcessSel.value = null;
	openDraft(d);
}

// Open the editor for an existing step — reverse persisted mappings back into
// the editor's shape-specific fields. Guards refuse unrepresentable steps
// (mirrors the Desk openEdit refusals verbatim).
function openEdit(si) {
	const step = steps.value[si];
	const shp = shapeOf(step);
	const shapeKey = shp.key === "conv" ? "conv" : shp.key === "idle" ? "idle" : "change";
	// GUARD: the conversion editor can only represent Introduce (chips mode) or
	// Consume+Introduce (rules mode). A conv step carrying any OTHER role (e.g. a
	// grid/API-authored Pin on a conversion) would be silently DROPPED on save —
	// refuse to open instead of destroying data the editor can't show.
	const refuse = (why) => {
		toast.warn(
			"Cannot edit this step here",
			`${why} — editing it here would silently rewrite or drop those entries. Adjust them via the underlying value-mapping table instead.`,
		);
	};
	if (shapeKey === "conv") {
		const hasConsume = step.mappings.some((m) => m.role === "Consume");
		const representable = hasConsume ? ["Consume", "Introduce"] : ["Introduce"];
		const foreign = [...new Set(step.mappings.map((m) => m.role).filter((r) => !representable.includes(r)))];
		if (foreign.length) {
			refuse(`This conversion step carries ${foreign.join(", ")} entries the editor cannot represent`);
			return;
		}
	}
	if (shapeKey === "change") {
		// The change editor holds ONE attribute per step — its held value is
		// entered per rule, so distinct held VALUES are editable here. Pins
		// spanning several ATTRIBUTES (or two Pin rows inside one rule) still
		// can't be shown: saving would collapse them onto the single hold attribute.
		const pins = step.mappings.filter((m) => m.role === "Pin");
		const pinAttrs = [...new Set(pins.map((m) => m.attribute))];
		if (pinAttrs.length > 1) {
			refuse(`This step holds ${pinAttrs.length} different attributes across its rules (${pinAttrs.join(", ")})`);
			return;
		}
		const pinsPerRule = {};
		pins.forEach((m) => { pinsPerRule[m.mapping_index] = (pinsPerRule[m.mapping_index] || 0) + 1; });
		if (Object.values(pinsPerRule).some((c) => c > 1)) {
			refuse("This step carries more than one hold entry inside a single rule");
			return;
		}
	}
	if (shapeKey === "idle" && step.mappings.length) {
		// An idle-classified step with mappings (e.g. Pin-only rows) would save
		// back as mappings: [] and its matrix would disappear.
		refuse("This step carries value-mapping entries the identity editor does not show");
		return;
	}
	const d = blankDraft(step.fabric_process, step.sequence, shapeKey, [], {
		item: props.doc.item || "",
		defaultInput: defaultInput.value || "",
		attributes: attributes.value,
	});
	d.index = si;
	d.input_item = step.input_item;
	d.output_item = step.output_item;
	d.quantity_ratio = step.quantity_ratio;

	const groups = {};
	step.mappings.forEach((m) => {
		(groups[m.mapping_index] = groups[m.mapping_index] || []).push(m);
	});
	const groupKeys = Object.keys(groups).sort((a, b) => num(a) - num(b));

	if (shapeKey === "conv" && step.mappings.some((m) => m.role === "Consume")) {
		// RULES MODE — rebuild consume_attrs + introduce attrs (first-seen order)
		// and one rule per mapping_index group. Chips stay empty: values live in
		// the rules, so untoggling every consumed attribute deliberately does NOT
		// fall back to a silent cross-product of the rule values.
		const cons = [];
		const intros = [];
		step.mappings.forEach((m) => {
			if (m.role === "Consume" && !cons.includes(m.attribute)) cons.push(m.attribute);
			if (m.role === "Introduce" && !intros.includes(m.attribute)) intros.push(m.attribute);
		});
		d.consume_attrs = cons;
		d.introduce = intros.length
			? intros.map((a) => ({ attr: a, chips: [], input: "" }))
			: [{ attr: "", chips: [], input: "" }];
		d.rules = groupKeys.map((k) => {
			const r = { in: {}, out: {} };
			groups[k].forEach((m) => {
				if (m.role === "Consume") r.in[m.attribute] = m.from_value || "";
				else if (m.role === "Introduce") r.out[m.attribute] = m.to_value || "";
			});
			return r;
		});
		if (!d.rules.length) d.rules = [blankRule(d)];
	} else if (shapeKey === "conv") {
		// Rebuild introduce[] as {attr, chips[distinct values]} preserving first-seen order.
		const byAttr = {};
		const order = [];
		step.mappings.filter((m) => m.role === "Introduce" && m.to_value).forEach((m) => {
			if (!(m.attribute in byAttr)) { byAttr[m.attribute] = []; order.push(m.attribute); }
			if (!byAttr[m.attribute].includes(m.to_value)) byAttr[m.attribute].push(m.to_value);
		});
		d.introduce = order.length
			? order.map((a) => ({ attr: a, chips: byAttr[a], input: "" }))
			: [{ attr: "", chips: [], input: "" }];
	} else if (shapeKey === "change") {
		const changeAttrs = [];
		step.mappings.filter((m) => m.role === "Change").forEach((m) => {
			if (!changeAttrs.includes(m.attribute)) changeAttrs.push(m.attribute);
		});
		d.change_attrs = changeAttrs.length ? changeAttrs : [attributes.value[0] || ""].filter(Boolean);
		d.groups = groupKeys.map((k) => {
			const g = {};
			d.change_attrs.forEach((a) => {
				const c = groups[k].find((m) => m.role === "Change" && m.attribute === a);
				g[a] = { from: (c && c.from_value) || "", to: (c && c.to_value) || "" };
			});
			// This rule's own held value — blank stays blank (= any).
			const p = groups[k].find((m) => m.role === "Pin");
			g.__pin = (p && p.from_value) || "";
			return g;
		});
		if (!d.groups.length) d.groups = [blankGroup(d.change_attrs)];
		// The guard above ensured every Pin row names the SAME single attribute.
		const anyPin = step.mappings.find((m) => m.role === "Pin");
		if (anyPin) d.pin_attr = anyPin.attribute;
	}
	[...(d.introduce || []).map((x) => x.attr), ...(d.consume_attrs || []), ...d.change_attrs, d.pin_attr]
		.forEach((a) => a && loadValues(a));
	openDraft(d);
}

function cancelEdit() {
	if (saving.value) return;
	draft.value = null;
	view.value = "overview";
}

// ---- persist -------------------------------------------------------------
// The exact IPDConfigView child-table save mechanism (see saveBomRow /
// saveProcessRow there): frappe.client.get the full IPD, replace the child
// arrays, frappe.client.save. Both fabric tables are cleared and rewritten
// wholesale — identical semantics to the Desk's clear_table + add_child
// write-back — and sync_fabric_process_matrices regenerates the matrices
// server-side in the same save.
async function persistSteps(candidateSteps, successDetail) {
	saving.value = true;
	try {
		const ipd = await callMethod("frappe.client.get", {
			doctype: "Item Production Detail",
			name: props.doc.name,
		});
		// Staleness guard — the Desk write-back saves through frm and gets
		// TimestampMismatchError for free; this wholesale rewrite of both fabric
		// tables must fail loudly too, never last-writer-wins over concurrent edits.
		if (props.doc.modified && ipd.modified !== props.doc.modified) {
			toast.error(
				"Save blocked",
				"This IPD changed since you opened it — reload and retry.",
			);
			return false;
		}
		ipd.fabric_processes = candidateSteps.map((s) => ({
			doctype: "IPD Fabric Process",
			sequence: s.sequence,
			fabric_process: s.fabric_process,
			input_item: s.input_item || null,
			output_item: s.output_item || null,
			quantity_ratio: s.quantity_ratio == null ? 1 : s.quantity_ratio,
		}));
		const mappings = [];
		candidateSteps.forEach((s) =>
			s.mappings.forEach((m) =>
				mappings.push({
					doctype: "IPD Fabric Value Mapping",
					sequence: s.sequence,
					mapping_index: m.mapping_index,
					attribute: m.attribute,
					role: m.role,
					from_value: m.from_value || "",
					to_value: m.to_value || "",
				}),
			),
		);
		ipd.fabric_value_mappings = mappings;
		await callMethod("frappe.client.save", { doc: ipd });
		toast.success("Saved", successDetail);
		emit("saved"); // parent reloads the doc (+ regenerated matrices)
		return true;
	} catch (e) {
		toast.error("Save failed", e.message);
		return false;
	} finally {
		saving.value = false;
	}
}

async function onEditorSave(step) {
	const d = draft.value;
	if (!d) return;
	const candidate = steps.value.slice();
	if (d.index == null) candidate.push(step);
	else candidate.splice(d.index, 1, step);
	const ok = await persistSteps(candidate, `${step.fabric_process} step saved — matrices regenerated`);
	if (ok) {
		draft.value = null;
		view.value = "overview";
	}
	// On failure the editor stays open with the user's entries intact.
}

function removeStep(si) {
	const step = steps.value[si];
	if (!step) return;
	confirm.require({
		header: "Remove fabric step?",
		message: `Remove step ${si + 1} (${step.fabric_process || "no process"})? Its matrix will be dropped on save.`,
		acceptLabel: "Remove",
		acceptClass: "p-button-danger",
		accept: async () => {
			const candidate = steps.value.slice();
			candidate.splice(si, 1);
			await persistSteps(candidate, `${step.fabric_process || "Step"} removed`);
		},
	});
}
</script>

<style scoped>
/* Panel chrome — mirrors IPDConfigView's .panel/.panel-head (scoped styles
   don't cross component boundaries, so the band is replicated here). */
.panel {
	background: var(--esd-card);
	border: 1px solid var(--esd-line);
	border-radius: var(--radius);
	overflow: hidden;
}
.panel-head {
	display: flex;
	align-items: center;
	gap: var(--space-2);
	padding: 10px 16px;
	background: var(--esd-accent-50);
	border-bottom: 1px solid var(--esd-line);
}
.panel-head::before {
	content: "";
	width: 6px;
	height: 6px;
	border-radius: 999px;
	background: var(--esd-accent-ink);
	opacity: 0.85;
	flex: 0 0 auto;
}
.panel-head h3 {
	margin: 0;
	font-size: 13px;
	font-weight: 700;
	letter-spacing: 0.02em;
	text-transform: uppercase;
	color: var(--esd-accent-ink);
}
.panel-meta {
	margin-left: auto;
	background: var(--esd-card);
	color: var(--esd-accent-ink);
	font-size: 11px;
	font-weight: 600;
	padding: 1px 8px;
	border-radius: 999px;
}
.panel-body {
	padding: 14px 16px;
}

/* ---- overview (Desk fp-* re-expressed with esd tokens) ---- */
.fp-empty { color: var(--esd-muted); font-size: 13px; padding: 10px 0; }

.fp-cards { display: flex; flex-direction: column; gap: 10px; }
.fp-card {
	position: relative;
	display: grid;
	grid-template-columns: 30px 1fr auto;
	gap: 4px 12px;
	align-items: center;
	background: var(--esd-card);
	border: 1px solid var(--esd-line);
	border-left: 3px solid var(--esd-muted-2);
	border-radius: var(--radius-sm, 8px);
	padding: 12px 14px;
	box-shadow: var(--esd-shadow-sm);
}
.fp-card.fp-conv { border-left-color: #2490ef; }
.fp-card.fp-swap { border-left-color: #28a745; }
.fp-card.fp-combo { border-left-color: #7c3aed; }
.fp-card.fp-idle { border-left-color: var(--esd-muted-2); }
.dark .fp-card.fp-conv { border-left-color: #7fb5f5; }
.dark .fp-card.fp-swap { border-left-color: #6fd598; }
.dark .fp-card.fp-combo { border-left-color: #b79df3; }

.fp-seq {
	grid-row: 1 / 4;
	width: 30px; height: 30px; border-radius: 8px;
	background: var(--esd-slate-50); color: var(--esd-muted);
	font-weight: 700; font-size: 13px; display: grid; place-items: center;
	font-variant-numeric: tabular-nums; align-self: start;
}
.fp-name { font-weight: 600; font-size: 14px; color: var(--esd-ink); }
.fp-badge {
	font-size: 11px; font-weight: 600; letter-spacing: 0.02em;
	padding: 2px 9px; border-radius: 7px; white-space: nowrap; justify-self: start;
}
.b-conv { background: #e3edfe; color: #175cd3; }
.b-swap { background: #d1fadf; color: #027a48; }
.b-combo { background: #ede7fe; color: #6231d3; }
.b-idle { background: var(--esd-slate-50); color: var(--esd-muted); }
.dark .b-conv { background: rgba(36, 144, 239, 0.18); color: #7fb5f5; }
.dark .b-swap { background: rgba(40, 167, 69, 0.18); color: #6fd598; }
.dark .b-combo { background: rgba(124, 58, 237, 0.2); color: #b79df3; }

.fp-card-actions { display: inline-flex; align-items: center; gap: 8px; grid-column: 3; grid-row: 1; }
.fp-edit {
	border: 1px solid var(--esd-line); background: var(--esd-card);
	color: var(--esd-ink); border-radius: 6px; padding: 3px 12px; cursor: pointer; font-size: 12.5px; font-weight: 500;
}
.fp-edit:hover { border-color: var(--esd-accent); color: var(--esd-accent-700); }
.fp-rm {
	border: 1px solid var(--esd-line); background: var(--esd-card);
	color: var(--esd-muted); width: 26px; height: 26px; border-radius: 6px; cursor: pointer; font-size: 15px; line-height: 1;
}
.fp-rm:hover { color: var(--esd-danger); border-color: var(--esd-danger); }
.fp-edit:disabled, .fp-rm:disabled { opacity: 0.5; cursor: not-allowed; }

.fp-flow { grid-column: 2 / 4; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 13px; color: var(--esd-muted); margin-top: 2px; }
.fp-item { background: var(--esd-slate-50); border: 1px solid var(--esd-line); border-radius: 6px; padding: 2px 8px; color: var(--esd-ink); font-weight: 500; }
.fp-arrow { color: var(--esd-muted); font-weight: 700; }
.fp-same, .fp-ratio { color: var(--esd-muted); font-size: 12.5px; }

.fp-summary { grid-column: 2 / 4; margin-top: 8px; padding-top: 8px; border-top: 1px dashed var(--esd-line); display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.fp-summary-text { font-size: 13px; color: var(--esd-ink); }

/* ---- add bar ---- */
.fp-addbar { margin-top: 16px; display: flex; flex-wrap: wrap; align-items: flex-end; gap: 12px; background: var(--esd-card); border: 1px dashed var(--esd-line); border-radius: var(--radius-sm, 8px); padding: 14px 15px; }
.fp-addbar-field { display: flex; flex-direction: column; gap: 5px; flex: 0 0 320px; max-width: 320px; }
.fp-addbar-field label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--esd-muted); font-weight: 600; }
.fp-locked { margin-top: 14px; display: flex; align-items: center; gap: 8px; color: var(--esd-muted); font-size: 12.5px; }
</style>
