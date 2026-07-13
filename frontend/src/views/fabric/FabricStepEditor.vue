<!--
  FabricStepEditor — per-step detail editor of the /web IPD "Fabric Processes"
  entry (the DETAIL half of the master-detail).

  RE-PORT of the Desk editor:
    Desk reference: essdee_yrp/public/js/Fabric/FabricProcesses.vue
      (detail-editor template + conversion/change/identity logic,
       2026-07-07 UI rebuild — the byte-truth for behavior).

  Byte-faithful (data contracts + behavior):
    - The three shapes and their draft model: CONVERSION (introduce chips
      cross-product mode OR Consume-rules mode with per-rule from→to),
      CHANGE (1..N attributes changing together, per-group from→to, optional
      single hold attribute whose held value is entered PER transition,
      blank = any), IDENTITY (hint only).
    - canSave gating, consume-toggle → rules-mode switch, pin-attr change
      clearing every group's held value, chip-input commit on save.
    - get_item_attributes xcall for the consumed-attribute toggles (input item
      attrs — cached per item, failed fetch = []).
    - Emitted step object identical to Desk saveDraft (buildStepFromDraft).

  Adapted for /web:
    - frappe.ui.form.make_control Link(Item) → PrimeVue AutoComplete backed by
      searchLink("Item") (same picker idiom as IPDConfigView's BOM form).
    - datalist value autocompletes → PrimeVue AutoComplete fed from the shared
      Item Attribute Value cache (fabricValues.js).
    - frappe.xcall → callMethod (same whitelisted endpoint).
    - Ctrl/Cmd+S saves the step (window keydown while the editor is mounted).

  Props: { draft } — the working object created by FabricProcessesSection
  (blankDraft / openEdit reverse-mapping); mutated in place (transient editor
  state, outside any form reactive model). Emits: save(step) / cancel.
-->
<template>
	<div class="fp-editor">
		<nav class="fp-crumbs">
			<a data-testid="fp-back" @click="$emit('cancel')">Processes</a>
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
					<span class="fp-arrow">→</span><span class="fp-item">{{ draft.output_item || "(pick output)" }}</span>
				</template>
				<span v-else class="fp-same">same item</span>
			</div>
		</div>

		<!-- CONVERSION: distinct items + introduce 1..N attributes -->
		<template v-if="draft.shapeKey === 'conv'">
			<section class="fp-panel">
				<div class="fp-panel-head">Items — a conversion consumes one item and produces another</div>
				<div class="fp-panel-body fp-row">
					<label class="fp-field">
						<span>Input item (consumed)</span>
						<AutoComplete
							v-model="draft.input_item"
							:suggestions="itemSuggestions"
							@complete="onItemComplete"
							placeholder="Pick the consumed item…"
							dropdown
							completeOnFocus
							fluid
							data-testid="fp-input-item"
						/>
					</label>
					<label class="fp-field">
						<span>Output item (produced)</span>
						<AutoComplete
							v-model="draft.output_item"
							:suggestions="itemSuggestions"
							@complete="onItemComplete"
							placeholder="Pick the produced item…"
							dropdown
							completeOnFocus
							fluid
							data-testid="fp-output-item"
						/>
					</label>
					<label class="fp-field fp-narrow">
						<span>Qty ratio (out / in)</span>
						<InputNumber
							v-model="draft.quantity_ratio"
							:min="0"
							:minFractionDigits="0"
							:maxFractionDigits="4"
							fluid
							data-testid="fp-ratio"
						/>
					</label>
				</div>
				<div v-if="draft.input_item && draft.output_item && draft.input_item === draft.output_item" class="fp-warn">
					A conversion's input and output must be different items.
				</div>
				<div v-else-if="!draft.input_item" class="fp-warn">
					Pick the consumed item — a conversion needs a distinct input.
				</div>
			</section>

			<section class="fp-panel fp-panel-hero">
				<div class="fp-panel-head">① Which attribute(s) does the new item gain?</div>
				<div class="fp-panel-body">
					<div v-if="consumeMode" class="fp-help">Pick each attribute the output carries — its values are entered per rule below.</div>
					<div v-else class="fp-help">Add each attribute the output carries. One varies (type several values); another may be a single default (e.g. a greige colour).</div>
					<div v-for="(intro, ii) in draft.introduce" :key="ii" class="fp-intro-row">
						<div class="fp-intro-attr">
							<Select
								v-model="intro.attr"
								:options="introduceOptions(ii)"
								placeholder="(pick attribute)"
								class="fp-mini-select"
								@update:modelValue="loadValues(intro.attr)"
							/>
							<button v-if="draft.introduce.length > 1" class="fp-chip-x" type="button" title="remove" @click="draft.introduce.splice(ii, 1)">×</button>
						</div>
						<div v-if="!consumeMode" class="fp-chipbox">
							<span v-for="(v, vi) in intro.chips" :key="v" class="fp-chip c-introduce">
								{{ v }}
								<button class="fp-chip-x" type="button" @click="intro.chips.splice(vi, 1)">×</button>
							</span>
							<AutoComplete
								v-model="intro.input"
								:suggestions="valSuggestions"
								@complete="onValComplete(intro.attr, $event)"
								@option-select="onChipPick(intro, $event)"
								@keydown.enter.prevent="addChip(intro)"
								placeholder="type a value, press Enter"
								completeOnFocus
								class="fp-chip-input"
								:data-testid="'fp-introduce-input-' + ii"
							/>
						</div>
					</div>
					<button v-if="unusedIntroduceAttrs.length" class="fp-link" type="button" data-testid="fp-add-introduce" @click="addIntroduceAttr">+ introduce another attribute</button>
					<template v-if="!consumeMode">
						<div v-if="introduceCombos > 0" class="fp-preview">{{ introduceCombos }} output combination(s) will be generated</div>
						<div v-else class="fp-preview fp-mut">No attributes introduced — a pure item swap (no matrix generated).</div>
					</template>
				</div>
			</section>

			<section class="fp-panel">
				<div class="fp-panel-head">② Which input attribute(s) are consumed?</div>
				<div class="fp-panel-body">
					<div class="fp-help">Pick these only when a SPECIFIC input value must be consumed — leave empty to consume any.</div>
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
						<span v-if="!consumeAttrOptions.length" class="fp-mut fp-small">{{ draft.input_item ? "The input item declares no attributes." : "Pick the input item to see its attributes." }}</span>
					</div>
				</div>
			</section>

			<section v-if="consumeMode" class="fp-panel fp-panel-hero">
				<div class="fp-panel-head">③ Enter each rule — consumed input → produced output</div>
				<div class="fp-panel-body">
					<div class="fp-help">Each rule pairs one consumed input combination with the output combination it produces.</div>
					<div v-for="(rule, ri) in draft.rules" :key="ri" class="fp-combo">
						<div class="fp-combo-head">
							Rule {{ ri + 1 }}
							<button v-if="draft.rules.length > 1" class="fp-chip-x" type="button" title="remove rule" :data-testid="'fp-remove-rule-' + ri" @click="draft.rules.splice(ri, 1)">×</button>
						</div>
						<div class="fp-rule-body">
							<div class="fp-rule-side">
								<div v-for="attr in consumedAttrsList" :key="attr" class="fp-pair">
									<span class="fp-cell-attr">{{ attr }}</span>
									<AutoComplete
										v-model="rule.in[attr]"
										:suggestions="valSuggestions"
										@complete="onValComplete(attr, $event)"
										placeholder="consumed value"
										completeOnFocus
										class="fp-val-input"
										:data-testid="'fp-rule-from-' + ri + '-' + attr"
									/>
								</div>
							</div>
							<span class="fp-arrow">→</span>
							<div class="fp-rule-side">
								<div v-for="attr in introducedAttrsList" :key="attr" class="fp-pair">
									<span class="fp-cell-attr">{{ attr }}</span>
									<AutoComplete
										v-model="rule.out[attr]"
										:suggestions="valSuggestions"
										@complete="onValComplete(attr, $event)"
										placeholder="produced value"
										completeOnFocus
										class="fp-val-input"
										:data-testid="'fp-rule-to-' + ri + '-' + attr"
									/>
								</div>
								<div v-if="!introducedAttrsList.length" class="fp-mut fp-small fp-dropped-note">nothing introduced — the consumed attribute is dropped</div>
							</div>
						</div>
					</div>
					<button class="fp-link" type="button" data-testid="fp-add-rule" @click="addRule">+ another rule</button>
					<div v-if="completeRuleCount > 0" class="fp-preview">{{ completeRuleCount }} rule(s) will be generated</div>
					<div v-else class="fp-preview fp-mut">Fill every value in at least one rule.</div>
				</div>
			</section>
		</template>

		<!-- CHANGE: 1..N attributes change, per-group from → to -->
		<template v-else-if="draft.shapeKey === 'change'">
			<section class="fp-panel fp-panel-hero">
				<div class="fp-panel-head">① Which attribute(s) change?</div>
				<div class="fp-panel-body">
					<div class="fp-selected-attrs">
						<span v-for="(a, ai) in draft.change_attrs" :key="a" class="fp-chip c-combo">
							{{ a }}
							<button v-if="draft.change_attrs.length > 1" class="fp-chip-x" type="button" @click="removeChangeAttr(ai)">×</button>
						</span>
						<Select
							v-if="unusedChangeAttrs.length"
							v-model="addChangeAttrSel"
							:options="unusedChangeAttrs"
							placeholder="+ add a second attribute"
							class="fp-mini-select"
							data-testid="fp-add-change-attr"
							@update:modelValue="onAddChangeAttr"
						/>
					</div>
					<div class="fp-help fp-help-after">{{ draft.change_attrs.length > 1 ? "These attributes change TOGETHER — one combined group per transition." : "Add a second attribute to change two things together in one step." }}</div>
				</div>
			</section>

			<section class="fp-panel fp-panel-hero">
				<div class="fp-panel-head">② Enter each transition — from → to</div>
				<div class="fp-panel-body">
					<div v-for="(grp, gi) in draft.groups" :key="gi" class="fp-combo">
						<div class="fp-combo-head">
							{{ draft.change_attrs.length > 1 ? "Combination" : "Transition" }} {{ gi + 1 }}
							<button v-if="draft.groups.length > 1" class="fp-chip-x" type="button" @click="draft.groups.splice(gi, 1)">×</button>
						</div>
						<div v-for="attr in draft.change_attrs" :key="attr" class="fp-pair">
							<span class="fp-cell-attr">{{ attr }}</span>
							<AutoComplete
								v-model="grp[attr].from"
								:suggestions="valSuggestions"
								@complete="onValComplete(attr, $event)"
								placeholder="from"
								completeOnFocus
								class="fp-val-input"
								:data-testid="'fp-from-' + gi + '-' + attr"
							/>
							<span class="fp-arrow">→</span>
							<AutoComplete
								v-model="grp[attr].to"
								:suggestions="valSuggestions"
								@complete="onValComplete(attr, $event)"
								placeholder="to"
								completeOnFocus
								class="fp-val-input"
								:data-testid="'fp-to-' + gi + '-' + attr"
							/>
						</div>
						<div v-if="draft.pin_attr" class="fp-pair fp-pin-when">
							<span class="fp-cell-attr">when {{ draft.pin_attr }} =</span>
							<AutoComplete
								v-model="grp.__pin"
								:suggestions="valSuggestions"
								@complete="onValComplete(draft.pin_attr, $event)"
								placeholder="any"
								completeOnFocus
								class="fp-val-input"
								:data-testid="'fp-when-' + gi"
							/>
						</div>
					</div>
					<button class="fp-link" type="button" data-testid="fp-add-group" @click="addGroup">+ {{ draft.change_attrs.length > 1 ? "another combination" : "another transition" }}</button>
				</div>
			</section>

			<section class="fp-panel">
				<div class="fp-panel-head">Hold (pin) an attribute — optional</div>
				<div class="fp-panel-body fp-row">
					<div class="fp-help fp-help-full">Attributes you don't mention carry through UNCHANGED automatically — no entry needed. Holding an attribute LIMITS each transition above to one value of it — enter that value per rule in the 'when … =' field that appears on every transition (blank = any).</div>
					<label class="fp-field fp-narrow">
						<span>Hold attribute</span>
						<Select
							:modelValue="draft.pin_attr || null"
							:options="pinSelectOptions"
							optionLabel="label"
							optionValue="value"
							placeholder="(hold nothing)"
							data-testid="fp-pin-attr"
							@update:modelValue="onPinSelect"
						/>
					</label>
				</div>
			</section>
		</template>

		<!-- IDENTITY -->
		<template v-else>
			<section class="fp-panel">
				<div class="fp-panel-head">What changes</div>
				<div class="fp-panel-body">
					<div class="fp-hint b-idle">Nothing — pass-through. The item is unchanged and no matrix is built.</div>
				</div>
			</section>
		</template>

		<div class="fp-edit-foot">
			<Button label="Save step" data-testid="fp-save-step" :disabled="!canSave || saving" :loading="saving" @click="saveStep" />
			<Button label="Cancel" severity="secondary" outlined data-testid="fp-cancel" :disabled="saving" @click="$emit('cancel')" />
		</div>
	</div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import AutoComplete from "primevue/autocomplete";
import InputNumber from "primevue/inputnumber";
import Select from "primevue/select";
import Button from "primevue/button";
import { callMethod, searchLink } from "@/api/client";
import { blankGroup, blankRule, buildStepFromDraft, isCompleteRule } from "./fabricShapes";
import { loadValues, suggestionsFor } from "./fabricValues";

const props = defineProps({
	// The working draft object (created by FabricProcessesSection via blankDraft /
	// the openEdit reverse-mapping). Mutated in place — transient editor state.
	draft: { type: Object, required: true },
	// The IPD's own attribute names (introduce / change / pin options).
	attributes: { type: Array, default: () => [] },
	// The IPD's produced item (stamps change/identity steps on save).
	itemName: { type: String, default: "" },
	// Parent persistence in flight — freezes the footer buttons.
	saving: { type: Boolean, default: false },
});
const emit = defineEmits(["save", "cancel"]);

const draft = props.draft; // stable identity for template terseness
const addChangeAttrSel = ref(null);

// ---- shared value autocompletes (one open at a time → one suggestions ref) --
const valSuggestions = ref([]);
function onValComplete(attr, e) {
	loadValues(attr); // warm the cache if this attribute was never loaded
	valSuggestions.value = suggestionsFor(attr, e.query);
}

// ---- Item pickers (conversion input/output) ---------------------------------
const itemSuggestions = ref([]);
async function onItemComplete(e) {
	try {
		const rows = await searchLink("Item", e.query || "", {});
		itemSuggestions.value = (rows || []).map((r) => r.name);
	} catch (_) { itemSuggestions.value = []; }
}

const draftBadge = computed(() => {
	if (draft.shapeKey === "conv") return { key: "conv", label: "Item conversion" };
	if (draft.shapeKey === "change") {
		return draft.change_attrs.length > 1
			? { key: "combo", label: "Combination" }
			: { key: "swap", label: "Attribute swap" };
	}
	return { key: "idle", label: "Identity" };
});

// ---- conversion: introduce attributes (Desk introduceOptions & co) ----------

function introduceOptions(ii) {
	// This row's own attr + any attribute not used by another introduce row.
	const used = draft.introduce.map((x, i) => (i === ii ? null : x.attr)).filter(Boolean);
	return props.attributes.filter((a) => !used.includes(a));
}
const unusedIntroduceAttrs = computed(() => {
	const used = draft.introduce.map((x) => x.attr).filter(Boolean);
	return props.attributes.filter((a) => !used.includes(a));
});
function addIntroduceAttr() {
	const a = unusedIntroduceAttrs.value[0] || "";
	draft.introduce.push({ attr: a, chips: [], input: "" });
	if (a) loadValues(a);
}
function addChip(intro) {
	const v = String(intro.input || "").trim();
	if (!v) return;
	if (!intro.chips.includes(v)) intro.chips.push(v);
	intro.input = "";
}
function onChipPick(intro, e) {
	// Suggestion clicked/Enter-selected → commit it as a chip immediately.
	intro.input = typeof e.value === "string" ? e.value : e.value?.name || "";
	addChip(intro);
}
const introduceCombos = computed(() => {
	if (draft.shapeKey !== "conv") return 0;
	const sets = draft.introduce.filter((x) => x.attr && x.chips.length).map((x) => x.chips.length);
	return sets.length ? sets.reduce((a, b) => a * b, 1) : 0;
});

// ---- conversion: consumed input attributes + rules (role Consume) -----------

// Attribute names of the conversion's INPUT item (the IPD's own attributes
// describe the OUTPUT side — a converted input may carry different ones).
// Cached per item; a failed fetch = [].
const inputAttrCache = reactive({});
async function loadInputAttrs(itemName) {
	if (!itemName || inputAttrCache[itemName]) return;
	inputAttrCache[itemName] = [];
	try {
		const attrs = await callMethod("essdee_yrp.fabric_ipd.get_item_attributes", { item: itemName });
		inputAttrCache[itemName] = attrs || [];
	} catch (_) {
		inputAttrCache[itemName] = [];
	}
}
watch(
	() => (draft.shapeKey === "conv" ? draft.input_item : null),
	(it) => { if (it) loadInputAttrs(it); },
	{ immediate: true },
);

// Rules mode = a conversion with ≥1 consumed input attribute. Zero consumed
// attributes keeps the plain Introduce cross-product.
const consumeMode = computed(() => Boolean(draft.shapeKey === "conv" && draft.consume_attrs.length));
const consumeAttrOptions = computed(() => {
	if (draft.shapeKey !== "conv") return [];
	const fetched = (draft.input_item && inputAttrCache[draft.input_item]) || [];
	// Already-selected attrs stay listed even when the fetch fails or the input
	// item changes, so a persisted step can always be untoggled.
	return [...fetched, ...draft.consume_attrs.filter((a) => !fetched.includes(a))];
});
const consumedAttrsList = computed(() => draft.consume_attrs.filter(Boolean));
const introducedAttrsList = computed(() => draft.introduce.map((x) => x.attr).filter(Boolean));
function toggleConsumeAttr(a) {
	const i = draft.consume_attrs.indexOf(a);
	if (i >= 0) draft.consume_attrs.splice(i, 1);
	else { draft.consume_attrs.push(a); loadValues(a); }
	if (draft.consume_attrs.length && !draft.rules.length) draft.rules = [blankRule(draft)];
}
function addRule() {
	draft.rules.push(blankRule(draft));
}
const completeRuleCount = computed(() => {
	if (draft.shapeKey !== "conv" || !draft.consume_attrs.length) return 0;
	return draft.rules.filter((r) => isCompleteRule(draft, r)).length;
});

// ---- change: attributes + groups + pin --------------------------------------

const unusedChangeAttrs = computed(() => props.attributes.filter((a) => !draft.change_attrs.includes(a)));
const pinOptions = computed(() => props.attributes.filter((a) => !draft.change_attrs.includes(a)));
const pinSelectOptions = computed(() => [
	{ label: "(hold nothing)", value: null },
	...pinOptions.value.map((a) => ({ label: a, value: a })),
]);
function onAddChangeAttr(a) {
	addChangeAttrSel.value = null;
	if (!a || draft.change_attrs.includes(a)) return;
	draft.change_attrs.push(a);
	draft.groups.forEach((g) => { if (!g[a]) g[a] = { from: "", to: "" }; });
	loadValues(a);
}
function removeChangeAttr(ai) {
	const a = draft.change_attrs[ai];
	draft.change_attrs.splice(ai, 1);
	draft.groups.forEach((g) => delete g[a]);
	if (draft.pin_attr === a) {
		draft.pin_attr = "";
		draft.groups.forEach((g) => { g.__pin = ""; });
	}
}
// Changing the hold ATTRIBUTE invalidates every rule's held value (they were
// values of the previous attribute) — clear them and load the new autocomplete.
function onPinSelect(v) {
	draft.pin_attr = v || "";
	draft.groups.forEach((g) => { g.__pin = ""; });
	if (draft.pin_attr) loadValues(draft.pin_attr);
}
function addGroup() {
	draft.groups.push(blankGroup(draft.change_attrs));
}

// ---- save --------------------------------------------------------------------

const canSave = computed(() => {
	const d = draft;
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

function saveStep() {
	if (!canSave.value || props.saving) return;
	// Commit any value still typed in a chip input (user clicked Save step
	// without pressing Enter) so it is not silently dropped.
	if (draft.shapeKey === "conv") draft.introduce.forEach((x) => addChip(x));
	emit("save", buildStepFromDraft(draft, props.itemName));
}

// Ctrl/Cmd+S saves the step while the editor is mounted.
function onKeydown(e) {
	const key = String(e.key || "").toLowerCase();
	if ((e.ctrlKey || e.metaKey) && key === "s") {
		e.preventDefault();
		saveStep();
	}
}
onMounted(() => window.addEventListener("keydown", onKeydown));
onBeforeUnmount(() => window.removeEventListener("keydown", onKeydown));

// Warm the value caches for every attribute the draft references (mirrors the
// Desk loadValues calls in addProcess/openEdit).
[...(draft.introduce || []).map((x) => x.attr), ...(draft.consume_attrs || []), ...(draft.change_attrs || []), draft.pin_attr]
	.forEach((a) => a && loadValues(a));
</script>

<style scoped>
/* Detail-editor styling — Desk fp-* classes re-expressed with esd-* tokens
   (dark mode flips via the token layer, no hardcoded colours except the
   shape-badge accents which carry .dark overrides below). */
.fp-editor { display: flex; flex-direction: column; }
.fp-mut { color: var(--esd-muted); }
.fp-small { font-size: 12.5px; }

.fp-crumbs { display: flex; align-items: center; gap: 8px; font-size: 12.5px; color: var(--esd-muted); margin-bottom: 10px; }
.fp-crumbs a { cursor: pointer; color: var(--esd-accent-700); }
.fp-crumbs a:hover { text-decoration: underline; }
.fp-sep { color: var(--esd-muted-2); }
.fp-crumb-cur { color: var(--esd-ink); font-weight: 600; }

.fp-edit-head { margin-bottom: 14px; }
.fp-edit-title { font-size: 17px; font-weight: 700; display: flex; align-items: center; gap: 10px; color: var(--esd-ink); }
.fp-edit-flow { margin-top: 6px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 13px; color: var(--esd-muted); }
.fp-item { background: var(--esd-slate-50); border: 1px solid var(--esd-line); border-radius: 6px; padding: 2px 8px; color: var(--esd-ink); font-weight: 500; }
.fp-arrow { color: var(--esd-muted); font-weight: 700; }
.fp-same { color: var(--esd-muted); font-size: 12.5px; }

.fp-badge { font-size: 11px; font-weight: 600; letter-spacing: 0.02em; padding: 2px 9px; border-radius: 7px; white-space: nowrap; }
.b-conv { background: #e3edfe; color: #175cd3; }
.b-swap { background: #d1fadf; color: #027a48; }
.b-combo { background: #ede7fe; color: #6231d3; }
.b-idle { background: var(--esd-slate-50); color: var(--esd-muted); }
.dark .b-conv { background: rgba(36, 144, 239, 0.18); color: #7fb5f5; }
.dark .b-swap { background: rgba(40, 167, 69, 0.18); color: #6fd598; }
.dark .b-combo { background: rgba(124, 58, 237, 0.2); color: #b79df3; }

.fp-panel { border: 1px solid var(--esd-line); border-radius: var(--radius-sm, 8px); margin-bottom: 12px; overflow: hidden; background: var(--esd-card); }
.fp-panel-hero { border-color: var(--esd-accent); }
.fp-panel-head { padding: 9px 14px; background: var(--esd-slate-50); border-bottom: 1px solid var(--esd-line); font-size: 12.5px; font-weight: 700; color: var(--esd-ink-2); }
.fp-panel-hero .fp-panel-head { background: var(--esd-accent-50); color: var(--esd-accent-ink); }
.fp-panel-body { padding: 14px; }
.fp-help { font-size: 12.5px; color: var(--esd-muted); margin-bottom: 8px; }
.fp-help-after { margin-top: 8px; margin-bottom: 0; }
.fp-help-full { flex-basis: 100%; }
.fp-preview { margin-top: 8px; font-size: 12.5px; color: var(--esd-accent-700); font-weight: 600; }
.fp-preview.fp-mut { color: var(--esd-muted); font-weight: 400; }
.fp-row { display: flex; flex-wrap: wrap; gap: 12px; }
.fp-field { display: flex; flex-direction: column; gap: 4px; min-width: 180px; flex: 1; }
.fp-field.fp-narrow { flex: 0 0 220px; min-width: 160px; }
.fp-field > span { font-size: 11.5px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--esd-muted); font-weight: 600; }
.fp-warn { margin: 10px 14px 12px; font-size: 12.5px; color: var(--esd-danger); }

.fp-mini-select { width: auto; max-width: 260px; min-width: 180px; }
.fp-intro-row { display: flex; align-items: flex-start; gap: 12px; margin-bottom: 10px; flex-wrap: wrap; }
.fp-intro-attr { display: flex; align-items: center; gap: 6px; flex: 0 0 230px; }
.fp-intro-row .fp-chipbox { flex: 1; min-width: 220px; }
.fp-chipbox { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; border: 1px solid var(--esd-line); border-radius: 6px; background: var(--esd-card); padding: 6px 8px; min-height: 40px; }
.fp-chip-input { flex: 1; min-width: 140px; }
.fp-chipbox :deep(.p-autocomplete-input) { border: none; background: transparent; box-shadow: none; padding: 2px 4px; }
.fp-chip { display: inline-flex; align-items: center; gap: 6px; background: var(--esd-slate-50); border: 1px solid var(--esd-line); border-radius: 7px; padding: 3px 6px 3px 10px; font-size: 12.5px; color: var(--esd-ink); }
.fp-chip.c-introduce { border-color: var(--esd-accent); }
.fp-chip.c-combo { border-color: #c4b5fd; }
.dark .fp-chip.c-combo { border-color: rgba(124, 58, 237, 0.6); }
.fp-chip-x { border: none; background: transparent; color: var(--esd-muted); cursor: pointer; font-size: 14px; line-height: 1; padding: 0; }
.fp-chip-x:hover { color: var(--esd-danger); }

.fp-selected-attrs { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.fp-toggle { border: 1px solid var(--esd-line); background: var(--esd-card); color: var(--esd-ink); border-radius: 7px; padding: 5px 12px; cursor: pointer; font: inherit; font-size: 12.5px; font-weight: 500; }
.fp-toggle:hover { border-color: var(--esd-accent); color: var(--esd-accent-700); }
.fp-toggle.on { background: var(--esd-accent-50); border-color: var(--esd-accent); color: var(--esd-accent-700); font-weight: 600; }

.fp-rule-body { display: flex; align-items: flex-start; gap: 14px; flex-wrap: wrap; }
.fp-rule-body > .fp-arrow { align-self: center; }
.fp-rule-side { display: flex; flex-direction: column; min-width: 230px; }
.fp-pair { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.fp-val-input { max-width: 230px; flex: 1; }
.fp-pin-when { margin-top: 2px; padding-top: 8px; border-top: 1px dashed var(--esd-line); }
.fp-pin-when .fp-cell-attr { min-width: 74px; white-space: nowrap; font-weight: 500; }
.fp-cell-attr { min-width: 74px; font-size: 12.5px; color: var(--esd-muted); font-weight: 600; }
.fp-dropped-note { padding: 4px 0; }
.fp-combo { border: 1px solid var(--esd-line); border-radius: 6px; padding: 10px; margin-bottom: 8px; background: var(--esd-card); }
.fp-combo-head { font-size: 12.5px; color: var(--esd-muted); font-weight: 600; margin-bottom: 6px; display: flex; gap: 8px; align-items: center; }
.fp-link { border: none; background: transparent; color: var(--esd-accent-700); cursor: pointer; font-size: 12.5px; padding: 2px 0; text-align: left; }
.fp-link:hover { text-decoration: underline; }
.fp-hint { font-size: 13px; color: var(--esd-ink); padding: 6px 10px; border-radius: 6px; display: inline-block; }
.fp-hint.b-idle { background: var(--esd-slate-50); color: var(--esd-muted); }

.fp-edit-foot { display: flex; gap: 10px; margin-top: 6px; }
</style>
