<template>
	<div class="fabproc">
		<!-- ══════════════ OVERVIEW ══════════════ -->
		<template v-if="view === 'overview'">
			<p class="fp-lede">{{ __("Each fabric step is one card: what goes in, what comes out, and a one-line summary of what changes. Click Edit to choose which attribute(s) change and enter the values.") }}</p>

			<div class="fp-legend">
				<span><span class="fp-badge b-conv">{{ __("Item conversion") }}</span> {{ __("item A → item B") }}</span>
				<span><span class="fp-badge b-swap">{{ __("Attribute swap") }}</span> {{ __("same item, a value flips") }}</span>
				<span><span class="fp-badge b-combo">{{ __("Combination") }}</span> {{ __("attributes change together") }}</span>
				<span><span class="fp-badge b-idle">{{ __("Identity") }}</span> {{ __("nothing changes · no matrix") }}</span>
			</div>

			<div v-if="!steps.length" class="fp-empty">
				{{ __("No fabric processes yet. Add the first step — yarn dyeing, knitting, dyeing, compacting, printing, washing.") }}
			</div>

			<div class="fp-cards">
				<div v-for="(step, si) in steps" :key="step.sequence" class="fp-card" :class="'fp-' + shapeOf(step).key">
					<div class="fp-seq">{{ si + 1 }}</div>
					<div class="fp-name">{{ step.fabric_process || __("(no process)") }}</div>
					<span class="fp-badge" :class="'b-' + shapeOf(step).key">{{ shapeOf(step).label }}</span>
					<div class="fp-card-actions">
						<button v-if="editable" class="fp-edit" data-testid="fp-edit" :data-process="step.fabric_process" @click="openEdit(si)">{{ __("Edit") }}</button>
						<button v-if="editable" class="fp-rm" data-testid="fp-remove" :data-process="step.fabric_process" :title="__('Remove step')" @click="removeStep(si)">×</button>
					</div>

					<div class="fp-flow">
						<span class="fp-item">{{ step.input_item || step.output_item }}</span>
						<template v-if="hasConversion(step)">
							<span class="fp-arrow">→</span>
							<span class="fp-item">{{ step.output_item }}</span>
						</template>
						<span v-else class="fp-same">{{ __("same item") }}</span>
						<span v-if="ratioLabel(step)" class="fp-ratio">{{ ratioLabel(step) }}</span>
					</div>

					<div class="fp-summary">
						<span class="fp-summary-label">{{ __("What changes") }}</span>
						<span class="fp-summary-text" v-html="summaryOf(step)"></span>
					</div>
				</div>
			</div>

			<div v-if="editable" class="fp-addbar">
				<div class="fp-addbar-field">
					<label>{{ __("Add a process") }}</label>
					<select v-model="addProcessSel" data-testid="fp-process-select">
						<option value="">{{ __("Pick a process…") }}</option>
						<option v-for="p in availableProcesses" :key="p" :value="p">{{ p }}</option>
					</select>
				</div>
				<button class="fp-btn" data-testid="fp-add-btn" :disabled="!addProcessSel || adding" @click="addProcess">
					{{ adding ? __("Reading process…") : __("Add & define →") }}
				</button>
			</div>
		</template>

		<!-- ══════════════ DETAIL EDITOR ══════════════ -->
		<template v-else-if="view === 'edit' && draft">
			<nav class="fp-crumbs">
				<a data-testid="fp-back" @click="cancelEdit">{{ __("Processes") }}</a>
				<span class="fp-sep">/</span>
				<span class="fp-crumb-cur">{{ draft.fabric_process }}</span>
			</nav>

			<div class="fp-edit-head">
				<div class="fp-edit-title">
					{{ draft.fabric_process }}
					<span class="fp-badge" :class="'b-' + draftBadge.key">{{ draftBadge.label }}</span>
				</div>
				<div class="fp-edit-flow">
					<span class="fp-item">{{ draft.input_item || draft.output_item }}</span>
					<template v-if="draft.shapeKey === 'conv'">
						<span class="fp-arrow">→</span><span class="fp-item">{{ draft.output_item || __("(pick output)") }}</span>
					</template>
					<span v-else class="fp-same">{{ __("same item") }}</span>
				</div>
			</div>

			<!-- CONVERSION: distinct items + introduce 1..N attributes -->
			<template v-if="draft.shapeKey === 'conv'">
				<section class="fp-panel">
					<div class="fp-panel-head">{{ __("Items — a conversion consumes one item and produces another") }}</div>
					<div class="fp-panel-body fp-row">
						<label class="fp-field">
							<span>{{ __("Input item (consumed)") }}</span>
							<div ref="inputMount" class="fp-linkmount" data-testid="fp-input-item"></div>
						</label>
						<label class="fp-field">
							<span>{{ __("Output item (produced)") }}</span>
							<div ref="outputMount" class="fp-linkmount" data-testid="fp-output-item"></div>
						</label>
						<label class="fp-field fp-narrow">
							<span>{{ __("Qty ratio (out / in)") }}</span>
							<input v-model.number="draft.quantity_ratio" type="number" min="0" step="0.01" data-testid="fp-ratio" />
						</label>
					</div>
					<div v-if="draft.input_item && draft.output_item && draft.input_item === draft.output_item" class="fp-warn">
						{{ __("A conversion's input and output must be different items.") }}
					</div>
					<div v-else-if="!draft.input_item" class="fp-warn">
						{{ __("Pick the consumed item — a conversion needs a distinct input.") }}
					</div>
				</section>

				<section class="fp-panel fp-panel-hero">
					<div class="fp-panel-head">① {{ __("Which attribute(s) does the new item gain?") }}</div>
					<div class="fp-panel-body">
						<div v-if="consumeMode" class="fp-help">{{ __("Pick each attribute the output carries — its values are entered per rule below.") }}</div>
						<div v-else class="fp-help">{{ __("Add each attribute the output carries. One varies (type several values); another may be a single default (e.g. a greige colour).") }}</div>
						<div v-for="(intro, ii) in draft.introduce" :key="ii" class="fp-intro-row">
							<div class="fp-intro-attr">
								<select v-model="intro.attr" class="fp-mini-select" @change="loadValues(intro.attr)">
									<option value="">{{ __("(pick attribute)") }}</option>
									<option v-for="a in introduceOptions(ii)" :key="a" :value="a">{{ a }}</option>
								</select>
								<button v-if="draft.introduce.length > 1" class="fp-chip-x" :title="__('remove')" @click="draft.introduce.splice(ii, 1)">×</button>
							</div>
							<div v-if="!consumeMode" class="fp-chipbox">
								<span v-for="(v, vi) in intro.chips" :key="v" class="fp-chip c-introduce">
									{{ v }}
									<button class="fp-chip-x" @click="intro.chips.splice(vi, 1)">×</button>
								</span>
								<input
									v-model="intro.input"
									:data-testid="'fp-introduce-input-' + ii"
									type="text"
									:list="'fpvals-' + intro.attr"
									:placeholder="__('type a value, press Enter')"
									@keydown.enter.prevent="addChip(intro)"
								/>
							</div>
						</div>
						<button v-if="unusedIntroduceAttrs.length" class="fp-link" data-testid="fp-add-introduce" @click="addIntroduceAttr">+ {{ __("introduce another attribute") }}</button>
						<template v-if="!consumeMode">
							<div v-if="introduceCombos > 0" class="fp-preview">{{ introduceCombos }} {{ __("output combination(s) will be generated") }}</div>
							<div v-else class="fp-preview fp-mut">{{ __("No attributes introduced — a pure item swap (no matrix generated).") }}</div>
						</template>
					</div>
				</section>

				<section class="fp-panel">
					<div class="fp-panel-head">② {{ __("Which input attribute(s) are consumed?") }}</div>
					<div class="fp-panel-body">
						<div class="fp-help">{{ __("Pick these only when a SPECIFIC input value must be consumed — leave empty to consume any.") }}</div>
						<div class="fp-selected-attrs">
							<button
								v-for="a in consumeAttrOptions"
								:key="a"
								type="button"
								class="fp-toggle"
								:class="{ on: draft.consume_attrs.includes(a) }"
								:data-testid="'fp-consume-attr-' + a"
								@click="toggleConsumeAttr(a)"
							>{{ a }}</button>
							<span v-if="!consumeAttrOptions.length" class="fp-mut" style="font-size: var(--text-sm)">{{ draft.input_item ? __("The input item declares no attributes.") : __("Pick the input item to see its attributes.") }}</span>
						</div>
					</div>
				</section>

				<section v-if="consumeMode" class="fp-panel fp-panel-hero">
					<div class="fp-panel-head">③ {{ __("Enter each rule — consumed input → produced output") }}</div>
					<div class="fp-panel-body">
						<div class="fp-help">{{ __("Each rule pairs one consumed input combination with the output combination it produces.") }}</div>
						<div v-for="(rule, ri) in draft.rules" :key="ri" class="fp-combo">
							<div class="fp-combo-head">
								{{ __("Rule") }} {{ ri + 1 }}
								<button v-if="draft.rules.length > 1" class="fp-chip-x" :title="__('remove rule')" :data-testid="'fp-remove-rule-' + ri" @click="draft.rules.splice(ri, 1)">×</button>
							</div>
							<div class="fp-rule-body">
								<div class="fp-rule-side">
									<div v-for="attr in consumedAttrsList" :key="attr" class="fp-pair">
										<span class="fp-cell-attr">{{ attr }}</span>
										<input v-model="rule.in[attr]" type="text" :list="'fpvals-' + attr" :placeholder="__('consumed value')" :data-testid="'fp-rule-from-' + ri + '-' + attr" />
									</div>
								</div>
								<span class="fp-arrow">→</span>
								<div class="fp-rule-side">
									<div v-for="attr in introducedAttrsList" :key="attr" class="fp-pair">
										<span class="fp-cell-attr">{{ attr }}</span>
										<input v-model="rule.out[attr]" type="text" :list="'fpvals-' + attr" :placeholder="__('produced value')" :data-testid="'fp-rule-to-' + ri + '-' + attr" />
									</div>
									<div v-if="!introducedAttrsList.length" class="fp-mut" style="font-size: var(--text-sm); padding: 4px 0">{{ __("nothing introduced — the consumed attribute is dropped") }}</div>
								</div>
							</div>
						</div>
						<button class="fp-link" data-testid="fp-add-rule" @click="addRule">+ {{ __("another rule") }}</button>
						<div v-if="completeRuleCount > 0" class="fp-preview">{{ completeRuleCount }} {{ __("rule(s) will be generated") }}</div>
						<div v-else class="fp-preview fp-mut">{{ __("Fill every value in at least one rule.") }}</div>
					</div>
				</section>
			</template>

			<!-- CHANGE: 1..N attributes change, per-group from → to -->
			<template v-else-if="draft.shapeKey === 'change'">
				<section class="fp-panel fp-panel-hero">
					<div class="fp-panel-head">① {{ __("Which attribute(s) change?") }}</div>
					<div class="fp-panel-body">
						<div class="fp-selected-attrs">
							<span v-for="(a, ai) in draft.change_attrs" :key="a" class="fp-chip c-combo">
								{{ a }}
								<button v-if="draft.change_attrs.length > 1" class="fp-chip-x" @click="removeChangeAttr(ai)">×</button>
							</span>
							<select v-if="unusedChangeAttrs.length" v-model="addChangeAttrSel" class="fp-mini-select" data-testid="fp-add-change-attr" @change="onAddChangeAttr">
								<option value="">+ {{ __("add a second attribute") }}</option>
								<option v-for="a in unusedChangeAttrs" :key="a" :value="a">{{ a }}</option>
							</select>
						</div>
						<div class="fp-help" style="margin-top:8px">{{ draft.change_attrs.length > 1 ? __("These attributes change TOGETHER — one combined group per transition.") : __("Add a second attribute to change two things together in one step.") }}</div>
					</div>
				</section>

				<section class="fp-panel fp-panel-hero">
					<div class="fp-panel-head">② {{ __("Enter each transition — from → to") }}</div>
					<div class="fp-panel-body">
						<div v-for="(grp, gi) in draft.groups" :key="gi" class="fp-combo">
							<div class="fp-combo-head">
								{{ draft.change_attrs.length > 1 ? __("Combination") : __("Transition") }} {{ gi + 1 }}
								<button v-if="draft.groups.length > 1" class="fp-chip-x" @click="draft.groups.splice(gi, 1)">×</button>
							</div>
							<div v-for="attr in draft.change_attrs" :key="attr" class="fp-pair">
								<span class="fp-cell-attr">{{ attr }}</span>
								<input v-model="grp[attr].from" type="text" :list="'fpvals-' + attr" :placeholder="__('from')" :data-testid="'fp-from-' + gi + '-' + attr" />
								<span class="fp-arrow">→</span>
								<input v-model="grp[attr].to" type="text" :list="'fpvals-' + attr" :placeholder="__('to')" :data-testid="'fp-to-' + gi + '-' + attr" />
							</div>
							<div v-if="draft.pin_attr" class="fp-pair fp-pin-when">
								<span class="fp-cell-attr">{{ __("when") }} {{ draft.pin_attr }} =</span>
								<input v-model="grp.__pin" type="text" :list="'fpvals-' + draft.pin_attr" :placeholder="__('any')" :data-testid="'fp-when-' + gi" />
							</div>
						</div>
						<button class="fp-link" data-testid="fp-add-group" @click="addGroup">+ {{ draft.change_attrs.length > 1 ? __("another combination") : __("another transition") }}</button>
					</div>
				</section>

				<section class="fp-panel">
					<div class="fp-panel-head">{{ __("Hold (pin) an attribute — optional") }}</div>
					<div class="fp-panel-body fp-row">
						<div class="fp-help" style="flex-basis: 100%">{{ __("Attributes you don't mention carry through UNCHANGED automatically — no entry needed. Holding an attribute LIMITS each transition above to one value of it — enter that value per rule in the 'when … =' field that appears on every transition (blank = any).") }}</div>
						<label class="fp-field fp-narrow">
							<span>{{ __("Hold attribute") }}</span>
							<select v-model="draft.pin_attr" @change="onPinAttrChange">
								<option value="">{{ __("(hold nothing)") }}</option>
								<option v-for="a in pinOptions" :key="a" :value="a">{{ a }}</option>
							</select>
						</label>
					</div>
				</section>
			</template>

			<!-- IDENTITY -->
			<template v-else>
				<section class="fp-panel">
					<div class="fp-panel-head">{{ __("What changes") }}</div>
					<div class="fp-panel-body">
						<div class="fp-hint b-idle">{{ __("Nothing — pass-through. The item is unchanged and no matrix is built.") }}</div>
					</div>
				</section>
			</template>

			<div class="fp-edit-foot">
				<button class="fp-btn" data-testid="fp-save-step" :disabled="!canSave" @click="saveDraft">{{ __("Save step") }}</button>
				<button class="fp-btn-ghost" data-testid="fp-cancel" @click="cancelEdit">{{ __("Cancel") }}</button>
			</div>
		</template>

		<!-- value autocompletes -->
		<datalist v-for="(vals, attr) in valueCache" :id="'fpvals-' + attr" :key="attr">
			<option v-for="v in vals" :key="v" :value="v"></option>
		</datalist>
	</div>
</template>

<script setup>
// ---------------------------------------------------------------------------
// Fabric Processes — master-detail Desk entry (2026-07-07 UI rebuild).
//
// OVERVIEW: one glanceable card per process step (name, in→out, shape badge,
// one-line "what changes" summary) with an Edit button, plus an Add-process bar.
//
// DETAIL EDITOR (per step, modelled on the Item BOM attribute-mapping editor —
// select which attribute(s), then enter values):
//   CONVERSION  → distinct input/output items + Introduce 1..N attributes. Each
//                 introduced attribute carries its own value(s); the editor takes
//                 the CROSS-PRODUCT of those value sets into output groups (so
//                 Knitting = Dia {14,16,18} × Colour {greige} → 3 cloth combos,
//                 each stamped with its Dia + the default greige Colour).
//                 OPTIONALLY the INPUT item's attributes can be marked consumed
//                 (panel ②): once ≥1 is picked the editor switches to RULES MODE
//                 — the chip cross-product is replaced by explicit rules (panel
//                 ③), each pairing one consumed input combination with one
//                 produced output combination. One mapping_index per complete
//                 rule: role Consume rows stamp the input side (attribute +
//                 from_value, to_value empty), role Introduce rows stamp the
//                 output side. A rule with no introduced attribute DROPS the
//                 consumed attribute. Zero consumed attrs = exactly the old
//                 cross-product behavior.
//   CHANGE      → 1..N attributes that change TOGETHER; a table of from→to
//                 transitions (one combined group each). 1 attr = attribute swap,
//                 ≥2 attrs = combination. An optional held (Pin) attribute — ONE
//                 attribute per step, but its held value is entered PER
//                 transition ("when <attr> = …", blank = any), so dia-wise
//                 dyeing / colour-wise compacting maps stay editable here.
//   IDENTITY    → nothing changes (no matrix).
//
// It OWNS entry, not storage: on Save it writes BOTH sibling child tables
// (fabric_processes + fabric_value_mappings, keyed by sequence + mapping_index)
// back through frm (via the injected on_change) so a normal Ctrl/Cmd+S persists
// them and sync_fabric_process_matrices regenerates the matrices. Data model
// unchanged. Roles: Change = value swap (attr both sides, from→to); Introduce =
// new attribute (output side only); Pin = passthrough (blank = wildcard);
// Consume = consumed input attribute (input side only, concrete from_value —
// never a wildcard), grouped with its rule's Introduce rows by mapping_index.
// ---------------------------------------------------------------------------
import { computed, nextTick, reactive, ref, watch } from "vue";

const steps = ref([]);
const editable = ref(true);
const item = ref(null);
const defaultInput = ref(null);
const attributes = ref([]);
const usedProcesses = ref([]);
const allProcesses = ref([]);
const valueCache = reactive({});
let onChange = null;

const view = ref("overview");
const draft = ref(null);
const addProcessSel = ref("");
const adding = ref(false);
const addChangeAttrSel = ref("");

// Real Frappe Link(Item) controls for a conversion's input/output items — a plain
// text box can't validate an Item, and input/output must be distinct real items
// (mirrors EditBOMAttributeMapping's make_control usage).
const inputMount = ref(null);
const outputMount = ref(null);
let inputCtrl = null;
let outputCtrl = null;

function mountItemControls() {
	if (!draft.value || draft.value.shapeKey !== "conv") return;
	if (!inputMount.value || !outputMount.value) return;
	$(inputMount.value).empty();
	$(outputMount.value).empty();
	inputCtrl = frappe.ui.form.make_control({
		parent: inputMount.value,
		df: {
			fieldtype: "Link", options: "Item", fieldname: "fp_input_item",
			placeholder: __("Pick the consumed item…"),
			change() { if (draft.value) draft.value.input_item = (inputCtrl.get_value() || ""); },
		},
		render_input: true,
	});
	inputCtrl.set_value(draft.value.input_item || "");
	outputCtrl = frappe.ui.form.make_control({
		parent: outputMount.value,
		df: {
			fieldtype: "Link", options: "Item", fieldname: "fp_output_item",
			placeholder: __("Pick the produced item…"),
			change() { if (draft.value) draft.value.output_item = (outputCtrl.get_value() || ""); },
		},
		render_input: true,
	});
	outputCtrl.set_value(draft.value.output_item || "");
}

function syncItemControls() {
	if (inputCtrl) draft.value.input_item = inputCtrl.get_value() || "";
	if (outputCtrl) draft.value.output_item = outputCtrl.get_value() || "";
}

// Empty the mount nodes while they are still in the DOM so the Frappe Link
// controls' Awesomplete document-listeners are released (avoids a leaked
// listener per conversion-editor open). Called on leaving the editor.
function disposeItemControls() {
	if (inputMount.value) $(inputMount.value).empty();
	if (outputMount.value) $(outputMount.value).empty();
	inputCtrl = null;
	outputCtrl = null;
}

// (Re)mount the Item controls whenever we enter a conversion editor.
watch(
	[view, () => (draft.value ? draft.value.shapeKey : null)],
	async ([v, k]) => {
		if (v === "edit" && k === "conv") { await nextTick(); mountItemControls(); }
		else { inputCtrl = null; outputCtrl = null; }
	},
	{ flush: "post" }
);

// Fetch the INPUT item's attribute names (for the consumed-attribute toggles)
// whenever a conversion editor is open and its input item is set/changed — the
// Link control's change handler updates draft.input_item, so watching it covers
// both editor-open and item-change. Cached per item; a failed fetch = [].
watch(
	() => (view.value === "edit" && draft.value && draft.value.shapeKey === "conv" ? draft.value.input_item : null),
	(it) => { if (it) loadInputAttrs(it); }
);

const num = (v) => (v == null || v === "" ? 0 : Number(v));
const esc = (v) => frappe.utils.escape_html(v == null ? "" : String(v));

// ---- load / persist -------------------------------------------------------

function load_data(payload, on_change) {
	onChange = on_change || onChange;
	editable.value = payload.editable !== false;
	item.value = payload.item || null;
	defaultInput.value = payload.default_input || payload.item || null;
	attributes.value = payload.attributes || [];
	allProcesses.value = payload.all_processes || [];
	const maps = payload.mappings || [];
	steps.value = (payload.processes || [])
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
	usedProcesses.value = steps.value.map((s) => s.fabric_process).filter(Boolean);
	view.value = "overview";
	draft.value = null;
	addProcessSel.value = "";
	attributes.value.forEach((a) => loadValues(a));
}

function writeBack() {
	usedProcesses.value = steps.value.map((s) => s.fabric_process).filter(Boolean);
	if (!onChange) return;
	const processes = steps.value.map((s) => ({
		sequence: s.sequence,
		fabric_process: s.fabric_process,
		input_item: s.input_item || null,
		output_item: s.output_item || null,
		quantity_ratio: s.quantity_ratio == null ? 1 : s.quantity_ratio,
	}));
	const mappings = [];
	steps.value.forEach((s) =>
		s.mappings.forEach((m) =>
			mappings.push({
				sequence: s.sequence,
				mapping_index: m.mapping_index,
				attribute: m.attribute,
				role: m.role,
				from_value: m.from_value || "",
				to_value: m.to_value || "",
			})
		)
	);
	onChange({ processes, mappings });
}

// ---- shape / card display -------------------------------------------------

function shapeOf(step) {
	const hasIntro = step.mappings.some((m) => m.role === "Introduce");
	const hasConsume = step.mappings.some((m) => m.role === "Consume");
	const changeAttrs = new Set(step.mappings.filter((m) => m.role === "Change").map((m) => m.attribute));
	if (hasIntro || hasConsume || (step.input_item && step.output_item && step.input_item !== step.output_item))
		return { key: "conv", label: __("Item conversion") };
	if (changeAttrs.size > 1) return { key: "combo", label: __("Combination") };
	if (changeAttrs.size === 1) return { key: "swap", label: __("Attribute swap") };
	return { key: "idle", label: __("Identity") };
}

function hasConversion(step) {
	return step.input_item && step.output_item && step.input_item !== step.output_item;
}

function ratioLabel(step) {
	const r = Number(step.quantity_ratio);
	return r && r !== 1 ? `×${r} ${__("out/in")}` : "";
}

// Escape + join values with " · "; when every value shares the same trailing
// word the suffix is written once at the end ("14 Dia", "15 Dia", "16 Dia" →
// "14 · 15 · 16 Dia") so long dia/value runs stay readable. Returns HTML.
function joinVals(vals) {
	const parts = vals.map((v) => String(v == null ? "" : v).split(" "));
	if (vals.length > 1 && parts.every((p) => p.length > 1)) {
		const suffix = parts[0][parts[0].length - 1];
		if (suffix && parts.every((p) => p[p.length - 1] === suffix)) {
			return parts.map((p) => esc(p.slice(0, -1).join(" "))).join(" · ") + " " + esc(suffix);
		}
	}
	return vals.map(esc).join(" · ");
}

// Cap a summary at `max` items — the rest folds into a muted "+N more".
function capItems(items, max = 4) {
	if (items.length <= max) return items.join(" ; ");
	return items.slice(0, max).join(" ; ") + ` <span class="fp-mut">${esc(__("+{0} more", [items.length - max]))}</span>`;
}

// One-line "what changes" summary for the overview card. Aggregated so a
// 25-rule map reads as a handful of lines, not a wall of text.
function summaryOf(step) {
	const key = shapeOf(step).key;
	// Introduce (conversion, chips mode) grouped by attribute -> distinct values.
	const introByAttr = {};
	const introOrder = [];
	step.mappings.filter((m) => m.role === "Introduce" && m.to_value).forEach((m) => {
		if (!introByAttr[m.attribute]) { introByAttr[m.attribute] = []; introOrder.push(m.attribute); }
		if (!introByAttr[m.attribute].includes(m.to_value)) introByAttr[m.attribute].push(m.to_value);
	});
	const introParts = introOrder.map((a) => `<b>${esc(a)}</b>: ${joinVals(introByAttr[a])}`);
	// Consume rules (rules-mode conversion): value-only sides like the WO popup
	// ("Navy → 14 Dia · Navy", no attribute labels). Rules sharing the SAME
	// consumed side whose introduced sides differ in exactly ONE attribute merge
	// into one line ("Navy → 14 · 15 · 16 Dia") — a constant introduced value
	// identical to a consumed pair is the carry-through and drops off the right.
	const ruleTexts = [];
	if (step.mappings.some((m) => m.role === "Consume")) {
		const byIdx = {};
		step.mappings.filter((m) => m.role === "Consume" || m.role === "Introduce").forEach((m) => {
			(byIdx[m.mapping_index] = byIdx[m.mapping_index] || []).push(m);
		});
		const rules = [];
		Object.keys(byIdx)
			.sort((a, b) => num(a) - num(b))
			.forEach((k) => {
				const cons = byIdx[k].filter((m) => m.role === "Consume").map((m) => ({ attr: m.attribute, val: m.from_value || "" }));
				if (!cons.length) return;
				const intros = byIdx[k].filter((m) => m.role === "Introduce").map((m) => ({ attr: m.attribute, val: m.to_value || "" }));
				rules.push({ side: cons.map((c) => c.attr + "\u0001" + c.val).join("\u0002"), cons, intros });
			});
		const bySide = {};
		const sideOrder = [];
		rules.forEach((r) => {
			if (!bySide[r.side]) { bySide[r.side] = []; sideOrder.push(r.side); }
			bySide[r.side].push(r);
		});
		// The single introduced attribute whose value varies across the batch —
		// null when the attr sets differ, or when ≠1 attribute varies.
		const varyingIntroAttr = (batch) => {
			const attrs = batch[0].intros.map((x) => x.attr);
			if (!attrs.length) return null;
			for (const r of batch) {
				if (r.intros.length !== attrs.length || !r.intros.every((x, i) => x.attr === attrs[i])) return null;
			}
			const varying = attrs.filter((a, i) => batch.some((r) => r.intros[i].val !== batch[0].intros[i].val));
			return varying.length === 1 ? varying[0] : null;
		};
		const ruleText = (cons, rightParts) => {
			const left = cons.map((c) => esc(c.val || "—")).join(" · ");
			return rightParts.length ? `${left} → ${rightParts.join(" · ")}` : `${left} → <span class="fp-mut">${__("dropped")}</span>`;
		};
		sideOrder.forEach((side) => {
			const batch = bySide[side];
			const varying = batch.length > 1 ? varyingIntroAttr(batch) : null;
			if (varying) {
				const rightParts = [];
				batch[0].intros.forEach((x, i) => {
					if (x.attr === varying) {
						const vals = [];
						batch.forEach((r) => { if (!vals.includes(r.intros[i].val || "—")) vals.push(r.intros[i].val || "—"); });
						rightParts.push(joinVals(vals));
					} else if (!batch[0].cons.some((c) => c.attr === x.attr && c.val === x.val)) {
						rightParts.push(esc(x.val || "—"));
					}
				});
				ruleTexts.push(ruleText(batch[0].cons, rightParts));
			} else {
				batch.forEach((r) => ruleTexts.push(ruleText(r.cons, r.intros.map((x) => esc(x.val || "—")))));
			}
		});
	}
	// Change/Pin groups — groups sharing the SAME transition (identical from→to
	// across all change attrs) render once, with their held values merged.
	const groups = {};
	step.mappings.filter((m) => m.role !== "Introduce").forEach((m) => {
		(groups[m.mapping_index] = groups[m.mapping_index] || []).push(m);
	});
	const changeAgg = [];
	const aggByKey = {};
	Object.keys(groups)
		.sort((a, b) => num(a) - num(b))
		.forEach((k) => {
			const changes = groups[k].filter((m) => m.role === "Change");
			if (!changes.length) return;
			const aggKey = changes.map((c) => `${c.attribute}\u0001${c.from_value || ""}\u0001${c.to_value || ""}`).join("\u0002");
			let agg = aggByKey[aggKey];
			if (!agg) { agg = aggByKey[aggKey] = { changes, pinOrder: [], pinVals: {} }; changeAgg.push(agg); }
			groups[k].filter((m) => m.role === "Pin" && m.from_value).forEach((p) => {
				if (!agg.pinVals[p.attribute]) { agg.pinVals[p.attribute] = []; agg.pinOrder.push(p.attribute); }
				if (!agg.pinVals[p.attribute].includes(p.from_value)) agg.pinVals[p.attribute].push(p.from_value);
			});
		});
	const groupTexts = changeAgg.map((agg) => {
		const attrs = agg.changes.map((c) => esc(c.attribute)).join(" · ");
		const froms = agg.changes.map((c) => esc(c.from_value || "—")).join(" · ");
		const tos = agg.changes.map((c) => esc(c.to_value || "—")).join(" · ");
		const pinTxt = agg.pinOrder.length
			? ` <span class="fp-mut">(${__("held")} ${agg.pinOrder.map((a) => esc(a) + " " + joinVals(agg.pinVals[a])).join(", ")})</span>`
			: "";
		return `<b>${attrs}</b>: ${froms} → ${tos}${pinTxt}`;
	});

	if (key === "conv") {
		if (ruleTexts.length) return capItems(ruleTexts);
		if (introParts.length) return `${__("Introduces")} ${introParts.join("; ")}`;
		return `${__("Converts")} ${esc(step.input_item)} → ${esc(step.output_item)} <span class="fp-mut">(${__("no attribute change · no matrix")})</span>`;
	}
	if (key === "combo") return `${__("Together")} — ${capItems(groupTexts)}`;
	if (key === "swap") return capItems(groupTexts);
	return `<span class="fp-mut">${__("Nothing changes · no matrix")}</span>`;
}

// ---- add / edit navigation ------------------------------------------------

const availableProcesses = computed(() =>
	allProcesses.value.filter((p) => !usedProcesses.value.includes(p))
);

const draftBadge = computed(() => {
	const d = draft.value;
	if (!d) return { key: "idle", label: "" };
	if (d.shapeKey === "conv") return { key: "conv", label: __("Item conversion") };
	if (d.shapeKey === "change") {
		return d.change_attrs.length > 1
			? { key: "combo", label: __("Combination") }
			: { key: "swap", label: __("Attribute swap") };
	}
	return { key: "idle", label: __("Identity") };
});

async function fetchShape(process) {
	try {
		const t = await frappe.xcall("essdee_yrp.fabric_ipd.get_process_transform", { process });
		const key = t.shape === "conversion" ? "conv"
			: t.shape === "swap" || t.shape === "multi_swap" ? "change"
			: "idle";
		return { key, change_attributes: t.change_attributes || [] };
	} catch (e) {
		return { key: "idle", change_attributes: [] };
	}
}

function blankDraft(process, seq, shapeKey, changeAttrs) {
	return {
		index: null,
		sequence: seq,
		fabric_process: process,
		shapeKey,
		input_item: shapeKey === "conv" ? (defaultInput.value || "") : (item.value || ""),
		output_item: item.value || "",
		quantity_ratio: 1,
		// conversion
		introduce: [{ attr: attributes.value.includes("Dia") ? "Dia" : (attributes.value[0] || ""), chips: [], input: "" }],
		// conversion, rules mode — consumed INPUT attributes + per-rule correspondence
		consume_attrs: [],
		rules: [],
		// change
		change_attrs: (changeAttrs && changeAttrs.length ? changeAttrs.slice() : [attributes.value[0] || ""]).filter(Boolean),
		groups: [],
		pin_attr: "",
	};
}

async function addProcess() {
	if (!addProcessSel.value) return;
	adding.value = true;
	const shape = await fetchShape(addProcessSel.value);
	adding.value = false;
	const seq = nextSequence();
	const d = blankDraft(addProcessSel.value, seq, shape.key, shape.change_attributes);
	if (d.shapeKey === "change") {
		if (!d.change_attrs.length) d.change_attrs = [attributes.value[0] || ""].filter(Boolean);
		d.groups = [blankGroup(d.change_attrs)];
	}
	d.introduce.forEach((x) => x.attr && loadValues(x.attr));
	d.change_attrs.forEach((a) => a && loadValues(a));
	addProcessSel.value = "";
	draft.value = d;
	view.value = "edit";
}

// Open the editor for an existing step — reverse persisted mappings back into
// the editor's shape-specific fields.
function openEdit(si) {
	const step = steps.value[si];
	const shp = shapeOf(step);
	const shapeKey = shp.key === "conv" ? "conv" : shp.key === "idle" ? "idle" : "change";
	// GUARD: the conversion editor can only represent Introduce (chips mode) or
	// Consume+Introduce (rules mode). A conv step carrying any OTHER role (e.g. a
	// grid/API-authored Pin on a conversion) would be silently DROPPED on save —
	// refuse to open instead of destroying data the editor can't show.
	const refuse = (why) => {
		frappe.msgprint({
			title: __("Cannot edit this step here"),
			indicator: "orange",
			message: __(
				"{0} — editing it here would silently rewrite or drop those entries. Adjust them via the underlying value-mapping table instead.",
				[why]
			),
		});
	};
	if (shapeKey === "conv") {
		const hasConsume = step.mappings.some((m) => m.role === "Consume");
		const representable = hasConsume ? ["Consume", "Introduce"] : ["Introduce"];
		const foreign = [...new Set(step.mappings.map((m) => m.role).filter((r) => !representable.includes(r)))];
		if (foreign.length) {
			refuse(__("This conversion step carries {0} entries the editor cannot represent", [frappe.utils.escape_html(foreign.join(", "))]));
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
			refuse(__("This step holds {0} different attributes across its rules ({1})", [pinAttrs.length, frappe.utils.escape_html(pinAttrs.join(", "))]));
			return;
		}
		const pinsPerRule = {};
		pins.forEach((m) => { pinsPerRule[m.mapping_index] = (pinsPerRule[m.mapping_index] || 0) + 1; });
		if (Object.values(pinsPerRule).some((c) => c > 1)) {
			refuse(__("This step carries more than one hold entry inside a single rule"));
			return;
		}
	}
	if (shapeKey === "idle" && step.mappings.length) {
		// An idle-classified step with mappings (e.g. Pin-only rows) would save
		// back as mappings: [] and its matrix would disappear.
		refuse(__("This step carries value-mapping entries the identity editor does not show"));
		return;
	}
	const d = blankDraft(step.fabric_process, step.sequence, shapeKey, []);
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
	[...(d.introduce || []).map((x) => x.attr), ...(d.consume_attrs || []), ...d.change_attrs, d.pin_attr].forEach((a) => a && loadValues(a));
	draft.value = d;
	view.value = "edit";
}

function cancelEdit() {
	disposeItemControls();
	draft.value = null;
	view.value = "overview";
}

// ---- conversion: introduce attributes -------------------------------------

function introduceOptions(ii) {
	// This row's own attr + any attribute not used by another introduce row.
	const used = draft.value.introduce.map((x, i) => (i === ii ? null : x.attr)).filter(Boolean);
	return attributes.value.filter((a) => !used.includes(a));
}
const unusedIntroduceAttrs = computed(() => {
	if (!draft.value) return [];
	const used = draft.value.introduce.map((x) => x.attr).filter(Boolean);
	return attributes.value.filter((a) => !used.includes(a));
});
function addIntroduceAttr() {
	const a = unusedIntroduceAttrs.value[0] || "";
	draft.value.introduce.push({ attr: a, chips: [], input: "" });
	if (a) loadValues(a);
}
function addChip(intro) {
	const v = (intro.input || "").trim();
	if (!v) return;
	if (!intro.chips.includes(v)) intro.chips.push(v);
	intro.input = "";
}
const introduceCombos = computed(() => {
	if (!draft.value || draft.value.shapeKey !== "conv") return 0;
	const sets = draft.value.introduce.filter((x) => x.attr && x.chips.length).map((x) => x.chips.length);
	return sets.length ? sets.reduce((a, b) => a * b, 1) : 0;
});

// ---- conversion: consumed input attributes + rules (role Consume) ----------

// Attribute names of the conversion's INPUT item (the IPD's own attributes
// describe the OUTPUT side — a converted input may carry different ones).
const inputAttrCache = reactive({});
async function loadInputAttrs(itemName) {
	if (!itemName || inputAttrCache[itemName]) return;
	inputAttrCache[itemName] = [];
	try {
		const attrs = await frappe.xcall("essdee_yrp.fabric_ipd.get_item_attributes", { item: itemName });
		inputAttrCache[itemName] = attrs || [];
	} catch (e) {
		inputAttrCache[itemName] = [];
	}
}

// Rules mode = a conversion with ≥1 consumed input attribute. Zero consumed
// attributes keeps the plain Introduce cross-product (today's behavior).
const consumeMode = computed(() =>
	Boolean(draft.value && draft.value.shapeKey === "conv" && draft.value.consume_attrs.length)
);
const consumeAttrOptions = computed(() => {
	const d = draft.value;
	if (!d || d.shapeKey !== "conv") return [];
	const fetched = (d.input_item && inputAttrCache[d.input_item]) || [];
	// Already-selected attrs stay listed even when the fetch fails or the input
	// item changes, so a persisted step can always be untoggled.
	return [...fetched, ...d.consume_attrs.filter((a) => !fetched.includes(a))];
});
const consumedAttrsList = computed(() =>
	draft.value ? draft.value.consume_attrs.filter(Boolean) : []
);
const introducedAttrsList = computed(() =>
	draft.value ? draft.value.introduce.map((x) => x.attr).filter(Boolean) : []
);
function toggleConsumeAttr(a) {
	const d = draft.value;
	const i = d.consume_attrs.indexOf(a);
	if (i >= 0) d.consume_attrs.splice(i, 1);
	else { d.consume_attrs.push(a); loadValues(a); }
	if (d.consume_attrs.length && !d.rules.length) d.rules = [blankRule(d)];
}
// A rule pairs one consumed input combination with one produced output
// combination. Missing keys read as "" (v-model creates them on first type).
function blankRule(d) {
	const r = { in: {}, out: {} };
	d.consume_attrs.forEach((a) => { r.in[a] = ""; });
	d.introduce.map((x) => x.attr).filter(Boolean).forEach((a) => { r.out[a] = ""; });
	return r;
}
function addRule() {
	draft.value.rules.push(blankRule(draft.value));
}
// Complete = every consumed from-value AND every introduced to-value filled.
// No introduced attribute at all is still complete — that DROPS the consumed
// attribute (consume it, introduce no replacement).
function isCompleteRule(d, r) {
	return (
		d.consume_attrs.filter(Boolean).every((a) => r.in && r.in[a]) &&
		d.introduce.map((x) => x.attr).filter(Boolean).every((a) => r.out && r.out[a])
	);
}
const completeRuleCount = computed(() => {
	const d = draft.value;
	if (!d || d.shapeKey !== "conv" || !d.consume_attrs.length) return 0;
	return d.rules.filter((r) => isCompleteRule(d, r)).length;
});

// ---- change: attributes + groups + pin ------------------------------------

function blankGroup(attrs) {
	const g = {};
	(attrs || []).forEach((a) => { g[a] = { from: "", to: "" }; });
	// Per-rule held value ("__" prefix so it can never collide with an
	// attribute key living on the same object). Blank = any.
	g.__pin = "";
	return g;
}
const unusedChangeAttrs = computed(() =>
	draft.value ? attributes.value.filter((a) => !draft.value.change_attrs.includes(a)) : []
);
const pinOptions = computed(() =>
	draft.value ? attributes.value.filter((a) => !draft.value.change_attrs.includes(a)) : []
);
function onAddChangeAttr() {
	const a = addChangeAttrSel.value;
	addChangeAttrSel.value = "";
	if (!a || draft.value.change_attrs.includes(a)) return;
	draft.value.change_attrs.push(a);
	draft.value.groups.forEach((g) => { if (!g[a]) g[a] = { from: "", to: "" }; });
	loadValues(a);
}
function removeChangeAttr(ai) {
	const a = draft.value.change_attrs[ai];
	draft.value.change_attrs.splice(ai, 1);
	draft.value.groups.forEach((g) => delete g[a]);
	if (draft.value.pin_attr === a) {
		draft.value.pin_attr = "";
		draft.value.groups.forEach((g) => { g.__pin = ""; });
	}
}
// Changing the hold ATTRIBUTE invalidates every rule's held value (they were
// values of the previous attribute) — clear them and load the new autocomplete.
function onPinAttrChange() {
	draft.value.groups.forEach((g) => { g.__pin = ""; });
	if (draft.value.pin_attr) loadValues(draft.value.pin_attr);
}
function addGroup() {
	draft.value.groups.push(blankGroup(draft.value.change_attrs));
}

// ---- save the draft back into steps ---------------------------------------

const canSave = computed(() => {
	const d = draft.value;
	if (!d) return false;
	if (d.shapeKey === "conv") {
		const itemsOk = Boolean(d.input_item && d.output_item && d.input_item !== d.output_item);
		if (!d.consume_attrs.length) return itemsOk;
		return itemsOk && d.rules.some((r) => isCompleteRule(d, r));
	}
	if (d.shapeKey === "change") {
		return d.change_attrs.length && d.groups.some((g) => d.change_attrs.every((a) => g[a] && g[a].from && g[a].to));
	}
	return true; // identity
});

function nextSequence() {
	const seqs = steps.value.map((s) => num(s.sequence)).filter((s) => s > 0);
	return seqs.length ? Math.max(...seqs) + 10 : 10;
}

function crossProduct(lists) {
	return lists.reduce((acc, list) => {
		const out = [];
		acc.forEach((a) => list.forEach((v) => out.push([...a, v])));
		return out;
	}, [[]]);
}

function saveDraft() {
	syncItemControls();
	if (!canSave.value) return;
	const d = draft.value;
	const mappings = [];

	if (d.shapeKey === "conv" && d.consume_attrs.length) {
		// RULES MODE — one mapping_index per COMPLETE rule (incomplete rules are
		// filtered exactly like the Change branch filters groups): Consume rows
		// stamp the consumed input values, Introduce rows the produced output.
		const consAttrs = d.consume_attrs.filter(Boolean);
		const introAttrs = d.introduce.map((x) => x.attr).filter(Boolean);
		const validRules = d.rules.filter((r) => isCompleteRule(d, r));
		validRules.forEach((r, idx) => {
			consAttrs.forEach((a) => {
				mappings.push({ mapping_index: idx, attribute: a, role: "Consume", from_value: r.in[a], to_value: "" });
			});
			introAttrs.forEach((a) => {
				mappings.push({ mapping_index: idx, attribute: a, role: "Introduce", from_value: "", to_value: r.out[a] });
			});
		});
	} else if (d.shapeKey === "conv") {
		// Commit any value still typed in a chip input (user clicked Save step
		// without pressing Enter) so it is not silently dropped.
		d.introduce.forEach((x) => addChip(x));
		// Cross-product the introduced value sets into one group per combination;
		// each combination stamps every introduced attribute (Introduce, output-only).
		const active = d.introduce.filter((x) => x.attr && x.chips.length);
		const combos = active.length ? crossProduct(active.map((x) => x.chips)) : [];
		combos.forEach((combo, idx) => {
			active.forEach((x, k) => {
				mappings.push({ mapping_index: idx, attribute: x.attr, role: "Introduce", from_value: "", to_value: combo[k] });
			});
		});
	} else if (d.shapeKey === "change") {
		const validGroups = d.groups.filter((g) => d.change_attrs.every((a) => g[a] && g[a].from && g[a].to));
		validGroups.forEach((g, idx) => {
			d.change_attrs.forEach((a) => {
				mappings.push({ mapping_index: idx, attribute: a, role: "Change", from_value: g[a].from, to_value: g[a].to });
			});
			// One Pin per rule: the hold ATTRIBUTE is step-wide, the held VALUE is
			// this rule's own ("when <attr> = …", blank = any/wildcard). Emitted
			// after the Change rows with the same mapping_index — matching the
			// seeded order so an untouched open→save round-trips identically.
			if (d.pin_attr) {
				const pv = g.__pin || "";
				mappings.push({ mapping_index: idx, attribute: d.pin_attr, role: "Pin", from_value: pv, to_value: pv });
			}
		});
	}

	const step = {
		sequence: d.sequence,
		fabric_process: d.fabric_process,
		input_item: d.shapeKey === "conv" ? d.input_item : (item.value || d.input_item || ""),
		output_item: d.shapeKey === "conv" ? d.output_item : (item.value || ""),
		quantity_ratio: d.shapeKey === "conv" ? (Number(d.quantity_ratio) || 1) : 1,
		mappings,
	};

	if (d.index == null) steps.value.push(step);
	else steps.value.splice(d.index, 1, step);
	writeBack();
	cancelEdit();
}

function removeStep(si) {
	steps.value.splice(si, 1);
	writeBack();
}

// ---- value autocompletes --------------------------------------------------

async function loadValues(attr) {
	if (!attr || valueCache[attr]) return;
	valueCache[attr] = [];
	try {
		const rows = await frappe.db.get_list("Item Attribute Value", {
			filters: { attribute_name: attr },
			fields: ["name"],
			limit: 0,
			order_by: "name asc",
		});
		valueCache[attr] = rows.map((r) => r.name);
	} catch (e) {
		valueCache[attr] = [];
	}
}

defineExpose({ load_data, get_steps: () => JSON.parse(JSON.stringify(steps.value)) });
</script>

<style scoped>
.fabproc { margin-top: 4px; }
.fp-lede { color: var(--text-muted); font-size: var(--text-md); margin: 0 0 12px; max-width: 74ch; }
.fp-legend { display: flex; flex-wrap: wrap; gap: 16px; margin: 0 0 14px; font-size: var(--text-sm); color: var(--text-muted); }
.fp-legend > span { display: inline-flex; align-items: center; gap: 7px; }
.fp-empty { color: var(--text-muted); font-size: var(--text-md); padding: 10px 0; }
.fp-mut { color: var(--text-muted); }

/* ---- overview cards ---- */
.fp-cards { display: flex; flex-direction: column; gap: 10px; }
.fp-card {
	position: relative;
	display: grid;
	grid-template-columns: 30px 1fr auto;
	gap: 4px 12px;
	align-items: center;
	background: var(--card-bg, var(--fg-color));
	border: 1px solid var(--border-color);
	border-left: 3px solid var(--gray-400, #9da5b3);
	border-radius: var(--border-radius-lg, 10px);
	padding: 12px 14px;
	box-shadow: var(--card-shadow, 0 1px 2px rgba(0,0,0,.06));
}
.fp-conv { border-left-color: var(--blue-500, #2490ef); }
.fp-swap { border-left-color: var(--green-500, #28a745); }
.fp-combo { border-left-color: var(--purple-500, #7c3aed); }
.fp-idle { border-left-color: var(--gray-400, #9da5b3); }

.fp-seq {
	grid-row: 1 / 4;
	width: 30px; height: 30px; border-radius: 8px;
	background: var(--control-bg, var(--subtle-fg)); color: var(--text-muted);
	font-weight: 700; font-size: 13px; display: grid; place-items: center;
	font-variant-numeric: tabular-nums; align-self: start;
}
.fp-name { font-weight: 600; font-size: var(--text-lg); }
.fp-badge {
	font-size: var(--text-xs); font-weight: 600; letter-spacing: .02em;
	padding: 2px 9px; border-radius: 7px; white-space: nowrap;
}
.b-conv { background: var(--blue-100, #e3edfe); color: var(--blue-700, #175cd3); }
.b-swap { background: var(--green-100, #d1fadf); color: var(--green-700, #027a48); }
.b-combo { background: var(--purple-100, #ede7fe); color: var(--purple-700, #6231d3); }
.b-idle { background: var(--bg-gray, #eceff3); color: var(--text-muted); }

.fp-card-actions { display: inline-flex; align-items: center; gap: 8px; }
.fp-edit {
	border: 1px solid var(--border-color); background: var(--control-bg, transparent);
	color: var(--text-color); border-radius: 6px; padding: 3px 12px; cursor: pointer; font-size: var(--text-sm); font-weight: 500;
}
.fp-edit:hover { border-color: var(--primary, #2490ef); color: var(--primary, #2490ef); }
.fp-rm {
	border: 1px solid var(--border-color); background: var(--control-bg, transparent);
	color: var(--text-muted); width: 26px; height: 26px; border-radius: 6px; cursor: pointer; font-size: 15px; line-height: 1;
}
.fp-rm:hover { color: var(--red-500, #e03636); border-color: var(--red-500, #e03636); }

.fp-flow { grid-column: 2 / 4; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: var(--text-md); color: var(--text-muted); margin-top: 2px; }
.fp-item { background: var(--control-bg, var(--subtle-fg)); border: 1px solid var(--border-color); border-radius: 6px; padding: 2px 8px; color: var(--text-color); font-weight: 500; }
.fp-arrow { color: var(--text-muted); font-weight: 700; }
.fp-same, .fp-ratio { color: var(--text-muted); font-size: var(--text-sm); }

.fp-summary { grid-column: 2 / 4; margin-top: 8px; padding-top: 8px; border-top: 1px dashed var(--border-color); display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.fp-summary-label { font-size: var(--text-xs); text-transform: uppercase; letter-spacing: .06em; color: var(--text-muted); font-weight: 700; white-space: nowrap; }
.fp-summary-text { font-size: var(--text-md); color: var(--text-color); }
.fp-summary-text :deep(b) { font-weight: 600; }

/* ---- add bar ---- */
.fp-addbar { margin-top: 16px; display: flex; align-items: flex-end; gap: 12px; background: var(--card-bg, var(--fg-color)); border: 1px dashed var(--border-color); border-radius: var(--border-radius-lg, 10px); padding: 14px 15px; }
.fp-addbar-field { display: flex; flex-direction: column; gap: 5px; flex: 0 0 320px; max-width: 320px; }
.fp-addbar-field label { font-size: var(--text-xs); text-transform: uppercase; letter-spacing: .05em; color: var(--text-muted); font-weight: 600; }

/* ---- detail editor ---- */
.fp-crumbs { display: flex; align-items: center; gap: 8px; font-size: var(--text-sm); color: var(--text-muted); margin-bottom: 10px; }
.fp-crumbs a { cursor: pointer; color: var(--primary, #2490ef); }
.fp-crumbs a:hover { text-decoration: underline; }
.fp-sep { color: var(--text-muted); }
.fp-crumb-cur { color: var(--text-color); font-weight: 600; }
.fp-edit-head { margin-bottom: 14px; }
.fp-edit-title { font-size: var(--text-xl); font-weight: 700; display: flex; align-items: center; gap: 10px; }
.fp-edit-flow { margin-top: 6px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: var(--text-md); color: var(--text-muted); }

.fp-panel { border: 1px solid var(--border-color); border-radius: var(--border-radius-lg, 10px); margin-bottom: 12px; overflow: hidden; background: var(--card-bg, var(--fg-color)); }
.fp-panel-hero { border-color: var(--blue-300, #93c5fd); }
.fp-panel-head { padding: 9px 14px; background: var(--subtle-fg, var(--control-bg)); border-bottom: 1px solid var(--border-color); font-size: var(--text-sm); font-weight: 700; color: var(--text-color); }
.fp-panel-hero .fp-panel-head { background: var(--blue-50, rgba(36,144,239,.07)); color: var(--blue-700, #175cd3); }
.fp-panel-body { padding: 14px; }
.fp-help { font-size: var(--text-sm); color: var(--text-muted); margin-bottom: 8px; }
.fp-preview { margin-top: 8px; font-size: var(--text-sm); color: var(--blue-700, #175cd3); font-weight: 600; }
.fp-preview.fp-mut { color: var(--text-muted); font-weight: 400; }
.fp-row { display: flex; flex-wrap: wrap; gap: 12px; }
.fp-field { display: flex; flex-direction: column; gap: 4px; min-width: 180px; flex: 1; }
.fp-field.fp-narrow { flex: 0 0 200px; min-width: 160px; }
.fp-field > span { font-size: var(--text-xs); text-transform: uppercase; letter-spacing: .05em; color: var(--text-muted); font-weight: 600; }
.fp-panel-body select, .fp-panel-body input, .fp-addbar select {
	font: inherit; font-size: var(--text-md); color: var(--text-color);
	background: var(--control-bg, var(--fg-color)); border: 1px solid var(--border-color);
	border-radius: var(--border-radius, 6px); padding: 7px 10px; width: 100%;
}
.fp-mini-select { width: auto !important; max-width: 240px; }
.fp-intro-row { display: flex; align-items: flex-start; gap: 12px; margin-bottom: 10px; flex-wrap: wrap; }
.fp-intro-attr { display: flex; align-items: center; gap: 6px; flex: 0 0 220px; }
.fp-intro-row .fp-chipbox { flex: 1; min-width: 220px; }
.fp-chipbox { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; border: 1px solid var(--border-color); border-radius: var(--border-radius, 6px); background: var(--control-bg, var(--fg-color)); padding: 6px 8px; min-height: 38px; }
.fp-chipbox input { border: none !important; background: transparent !important; padding: 2px 4px !important; flex: 1; min-width: 120px; }
.fp-chipbox input:focus { outline: none; }
.fp-chip { display: inline-flex; align-items: center; gap: 6px; background: var(--control-bg, var(--subtle-fg)); border: 1px solid var(--border-color); border-radius: 7px; padding: 3px 6px 3px 10px; font-size: var(--text-sm); color: var(--text-color); }
.fp-chip.c-introduce { border-color: var(--blue-300, #93c5fd); }
.fp-chip.c-combo { border-color: var(--purple-300, #c4b5fd); }
.fp-chip-x { border: none; background: transparent; color: var(--text-muted); cursor: pointer; font-size: 14px; line-height: 1; padding: 0; }
.fp-chip-x:hover { color: var(--red-500, #e03636); }
.fp-selected-attrs { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.fp-toggle {
	border: 1px solid var(--border-color); background: var(--control-bg, transparent);
	color: var(--text-color); border-radius: 7px; padding: 4px 12px; cursor: pointer;
	font: inherit; font-size: var(--text-sm); font-weight: 500;
}
.fp-toggle:hover { border-color: var(--primary, #2490ef); color: var(--primary, #2490ef); }
.fp-toggle.on { background: var(--blue-100, #e3edfe); border-color: var(--blue-500, #2490ef); color: var(--blue-700, #175cd3); font-weight: 600; }
.fp-rule-body { display: flex; align-items: flex-start; gap: 14px; flex-wrap: wrap; }
.fp-rule-body > .fp-arrow { align-self: center; }
.fp-rule-side { display: flex; flex-direction: column; min-width: 220px; }
.fp-pair { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.fp-pair input { max-width: 220px; }
.fp-pin-when { margin-top: 2px; padding-top: 8px; border-top: 1px dashed var(--border-color); }
.fp-pin-when .fp-cell-attr { min-width: 74px; white-space: nowrap; font-weight: 500; }
.fp-cell-attr { min-width: 74px; font-size: var(--text-sm); color: var(--text-muted); font-weight: 600; }
.fp-combo { border: 1px solid var(--border-color); border-radius: var(--border-radius, 6px); padding: 10px; margin-bottom: 8px; }
.fp-combo-head { font-size: var(--text-sm); color: var(--text-muted); font-weight: 600; margin-bottom: 6px; display: flex; gap: 8px; align-items: center; }
.fp-link { border: none; background: transparent; color: var(--primary, #2490ef); cursor: pointer; font-size: var(--text-sm); padding: 2px 0; text-align: left; }
.fp-hint { font-size: var(--text-md); color: var(--text-color); padding: 4px 0; }
.fp-warn { margin: 10px 14px 2px; font-size: var(--text-sm); color: var(--red-600, #c0392b); }
/* Frappe make_control Link fields mounted inline — drop their built-in label so
   they sit under our own field caption. */
.fp-linkmount :deep(.control-label) { display: none; }
.fp-linkmount :deep(.frappe-control) { margin: 0; }
.fp-linkmount :deep(.control-input-wrapper) { margin: 0; }

.fp-edit-foot { display: flex; gap: 10px; margin-top: 6px; }
.fp-btn { appearance: none; border: none; background: var(--primary, #2490ef); color: #fff; font: inherit; font-weight: 600; font-size: var(--text-md); padding: 8px 18px; border-radius: var(--border-radius, 6px); cursor: pointer; }
.fp-btn:disabled { opacity: .45; cursor: not-allowed; }
.fp-btn-ghost { appearance: none; border: 1px solid var(--border-color); background: var(--control-bg, transparent); color: var(--text-color); font: inherit; font-weight: 500; font-size: var(--text-md); padding: 8px 16px; border-radius: var(--border-radius, 6px); cursor: pointer; }
</style>
