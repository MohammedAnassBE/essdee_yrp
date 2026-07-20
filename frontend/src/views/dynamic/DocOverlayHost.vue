<!--
  DocOverlayHost — hosts the EXISTING DocDetail (view mode AND create mode)
  inside overlays, driven by the LIST page's route query + the layout's
  structural knobs (spec §6.4; server vocab in yrp/api/ui_config.py):

    ?detail=<name>  → DocDetail (view) in
                        detail.position "right"        → Drawer, right
                        detail.position "bottom-sheet" → Drawer, bottom (~85vh)
                        detail.position "center"       → Dialog, modal
    ?new=1          → DocDetail (create) in a Dialog when entry.mode "popup",
                      anchored per entry.popupPosition (9-position grid).
                      Any OTHER seed query params (e.g. work_order=…) pass
                      through untouched — DocDetail's applyCreateFormQuery
                      reads them off the same route.
    ?new=1 + dcEntry.variant "size-matrix" (Delivery Challan lists only)
                    → DocDetail (create) in a BOTTOM Drawer (demo-7's DC
                      entry sheet), with the WO quick-pick chips (+ Job-worker
                      chips when dcEntry.supplierPicker is "chips") ABOVE the
                      form. The DC-specific knob overrides entry.mode here.

  Close/back protocol: the opener (DynamicListPage) PUSHES the query, so the
  browser Back button closes the overlay; every in-overlay close path
  (X / Escape / scrim / discard / delete / saved) router.replace-removes the
  `detail` + `new` keys instead. A dirty form gets the same "Discard unsaved
  changes?" confirm the full-page route-leave guard shows — X/scrim/Escape via
  onRequestClose (query-only changes never fire onBeforeRouteLeave, so the
  host runs it via DocDetail's exposed state), Back/forward via the host's
  onBeforeRouteUpdate guard (update guards DO fire on query-only navigations).
  Escape is host-owned (closeOnEscape=false everywhere here): it closes the
  host only when no nested PrimeVue overlay sits above it.

  BOUNDARY (parity law): overlays only ever intercept LIST-PAGE interactions.
  Direct path navigation — /web/:docRoute/:id from home tiles, the palette,
  deep links, and forward-action pushes like /delivery-challan/new?work_order=…
  — keeps rendering full-page regardless of these knobs. A hand-typed
  ?detail=/?new= with NO knob active renders nothing (knob absent = today).

  PERMISSIONS: arrangement never grants capability — the embedded DocDetail is
  the same component with the same canRead/canCreate/canSubmit/canCancel gates;
  no config key here ever feeds a server query.
-->
<template>
	<!-- Detail: right drawer / bottom sheet.
	     closeOnEscape=false on all four host overlays: PrimeVue 4 Drawer AND
	     Dialog each bind their own document-level Escape listener with no
	     topmost check, so one Escape inside a nested modal (Print / SMS /
	     e-Waybill / a confirm) would close the inner modal AND this host.
	     The host owns Escape instead (onHostKeydown) and acts only when no
	     nested overlay is open above it. -->
	<Drawer
		:visible="drawerVisible"
		:position="detailPosition === 'bottom-sheet' ? 'bottom' : 'right'"
		:header="overlayTitle"
		:blockScroll="true"
		:closeOnEscape="false"
		class="esd-doc-overlay-drawer"
		:class="detailPosition === 'bottom-sheet' ? 'esd-doc-overlay-drawer--bottom' : 'esd-doc-overlay-drawer--right'"
		@update:visible="onVisibleChange"
	>
		<DocDetail
			v-if="drawerVisible && detailName"
			ref="detailRef"
			:key="'ov-' + detailName"
			:doc-route="docRoute"
			:id="detailName"
			embedded
			@close="closeOverlay"
			@saved="onSaved"
		/>
	</Drawer>

	<!-- Detail: centered modal dialog -->
	<Dialog
		:visible="centerVisible"
		modal
		:dismissableMask="true"
		:closeOnEscape="false"
		:header="overlayTitle"
		:blockScroll="true"
		class="esd-doc-overlay-dialog"
		:style="{ width: 'min(1080px, 94vw)' }"
		@update:visible="onVisibleChange"
	>
		<DocDetail
			v-if="centerVisible && detailName"
			ref="detailRef"
			:key="'ov-' + detailName"
			:doc-route="docRoute"
			:id="detailName"
			embedded
			@close="closeOverlay"
			@saved="onSaved"
		/>
	</Dialog>

	<!-- Entry: create popup (entry.mode "popup") -->
	<Dialog
		:visible="entryVisible"
		modal
		:dismissableMask="true"
		:closeOnEscape="false"
		:position="entryDialogPosition"
		:header="createTitle"
		:blockScroll="true"
		class="esd-doc-overlay-dialog esd-doc-overlay-dialog--entry"
		:style="{ width: 'min(1080px, 94vw)' }"
		@update:visible="onVisibleChange"
	>
		<DocDetail
			v-if="entryVisible"
			ref="createRef"
			key="ov-new"
			:doc-route="docRoute"
			id="new"
			embedded
			@close="closeOverlay"
			@saved="onSaved"
		/>
	</Dialog>

	<!-- Entry: DC bottom-sheet family (dcEntry.variant "size-matrix" / "sheet-tiles"
	     / "touch-rows"). The real /web DC form already IS the size-pivot editor —
	     the sheet only re-hosts the SAME embedded create-mode DocDetail (same
	     autofill, same buildPayload/onSave save path) and adds the quick-pick
	     chip strips above it. The variant/qtyControl only restyle the SAME grid
	     (qtyControl flows through DocDetail); no bespoke deliverable render, no
	     new save path. -->
	<Drawer
		:visible="dcSheetVisible"
		position="bottom"
		:header="createTitle"
		:blockScroll="true"
		:closeOnEscape="false"
		class="esd-doc-overlay-drawer esd-doc-overlay-drawer--bottom"
		:class="dcVariant ? 'esd-dc-sheet--' + dcVariant : null"
		@update:visible="onVisibleChange"
	>
		<DcEntryChips
			v-if="dcSheetVisible"
			show-wo-chips
			:show-supplier-chips="dcSupplierStrip"
			:supplier-style="dcSupplierStyle"
			:active-work-order="dcPickedWo"
			:active-supplier="dcPickedSupplier"
			@pick-wo="onPickWo"
			@pick-supplier="onPickSupplier"
		/>
		<DocDetail
			v-if="dcSheetVisible"
			ref="createRef"
			key="ov-new"
			:doc-route="docRoute"
			id="new"
			embedded
			@close="closeOverlay"
			@saved="onSaved"
		/>
	</Drawer>

	<!-- Entry: DC wizard-steps (dcEntry.variant "wizard-steps", demo-2). A
	     centered Dialog. The PrimeVue Stepper is the step-header SHELL only; the
	     step content is hand-rolled and the embedded create-mode DocDetail stays
	     mounted (v-show) across steps so its form state — and the SAME
	     buildPayload/onSave save path — survives the WO -> Items -> Job-worker ->
	     Review walk. Steps 1 & 3 are quick-pick helpers that relay through the
	     form's setFormField exactly as the size-matrix chips do; step 4 fires the
	     form's own onSave via the exposed save(). -->
	<Dialog
		:visible="dcWizardVisible"
		modal
		:dismissableMask="true"
		:closeOnEscape="false"
		:header="createTitle"
		:blockScroll="true"
		class="esd-doc-overlay-dialog esd-dc-wizard"
		:style="{ width: 'min(1080px, 94vw)' }"
		@update:visible="onVisibleChange"
	>
		<template v-if="dcWizardVisible">
			<Stepper :value="wizardStep" linear class="esd-dc-wizard-steps">
				<StepList>
					<Step value="1">Work Order</Step>
					<Step value="2">Items</Step>
					<Step value="3">Job-worker</Step>
					<Step value="4">Review</Step>
				</StepList>
			</Stepper>

			<!-- Step 1: Work Order picker.
			     A chip tap auto-fills + auto-advances (onWizardPickWo). But the
			     strip only lists the 8 most-recent submitted WOs, so on a busy
			     floor the target WO may not be a chip (or the strip may be empty) —
			     the search box below reaches ANY submitted/open Work Order through
			     the SAME setFormField relay, so step 1 is never a dead-end. And
			     "Continue to form" keeps the form's OWN work_order Link (step 2)
			     as a third always-available path — step 1 is a helper, never a
			     gate, matching every other DC entry variant. -->
			<div v-show="wizardStep === '1'" class="esd-dc-wizard-panel">
				<DcEntryChips
					show-wo-chips
					:active-work-order="dcPickedWo"
					@pick-wo="onWizardPickWo"
				/>
				<div class="esd-dc-wizard-search">
					<label class="esd-dc-wizard-search-label">Or search any Work Order</label>
					<LinkField
						v-model="wizardWoSearch"
						target-doctype="Work Order"
						:filters="WO_SEARCH_FILTERS"
						:dropdown="false"
						placeholder="Search Work Order by number…"
						@item-select="onWizardWoSearchSelect"
					/>
				</div>
				<p class="esd-dc-wizard-hint">Pick a recent Work Order, search for any Work Order above, or Continue and set it on the form — its deliverable items load either way.</p>
				<div class="esd-dc-wizard-nav">
					<button type="button" class="esd-dc-wizard-btn ghost" @click="onRequestClose">Cancel</button>
					<button type="button" class="esd-dc-wizard-btn primary" @click="wizardStep = '2'">Continue to form →</button>
				</div>
			</div>

			<!-- Step 2: the SAME embedded create form (kept mounted across steps) -->
			<div v-show="wizardStep === '2'" class="esd-dc-wizard-panel esd-dc-wizard-panel--doc">
				<DocDetail
					v-if="dcWizardVisible"
					ref="createRef"
					key="ov-new"
					:doc-route="docRoute"
					id="new"
					embedded
					@close="closeOverlay"
					@saved="onSaved"
				/>
				<div class="esd-dc-wizard-nav">
					<button type="button" class="esd-dc-wizard-btn ghost" @click="wizardStep = '1'">← Back</button>
					<button type="button" class="esd-dc-wizard-btn primary" @click="wizardStep = '3'">Continue →</button>
				</div>
			</div>

			<!-- Step 3: Job-worker quick-pick -->
			<div v-show="wizardStep === '3'" class="esd-dc-wizard-panel">
				<DcEntryChips
					show-supplier-chips
					:supplier-style="dcSupplierStyle"
					:active-supplier="dcPickedSupplier"
					@pick-supplier="onWizardPickSupplier"
				/>
				<p class="esd-dc-wizard-hint">Choose the Job-worker (or set it on the form in the previous step).</p>
				<div class="esd-dc-wizard-nav">
					<button type="button" class="esd-dc-wizard-btn ghost" @click="wizardStep = '2'">← Back</button>
					<button type="button" class="esd-dc-wizard-btn primary" @click="wizardStep = '4'">Continue →</button>
				</div>
			</div>

			<!-- Step 4: Review + Save (fires the form's own onSave) -->
			<div v-show="wizardStep === '4'" class="esd-dc-wizard-panel">
				<div class="esd-dc-wizard-summary">
					<div class="esd-dc-wizard-srow"><span>Work Order</span><strong>{{ dcPickedWo || "— set on the form" }}</strong></div>
					<div class="esd-dc-wizard-srow"><span>Job-worker</span><strong>{{ dcPickedSupplier || "— set on the form" }}</strong></div>
					<p class="esd-dc-wizard-hint">Review the quantities you entered in the Items step, then save. Missing required fields are flagged on the form.</p>
				</div>
				<div class="esd-dc-wizard-nav">
					<button type="button" class="esd-dc-wizard-btn ghost" @click="wizardStep = '3'">← Back</button>
					<button type="button" class="esd-dc-wizard-btn primary" @click="onWizardSave">Save Delivery Challan</button>
				</div>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { onBeforeRouteUpdate, useRoute, useRouter } from "vue-router"
import Dialog from "primevue/dialog"
import Drawer from "primevue/drawer"
// PrimeVue Stepper (installed 4.5.5) is the wizard-steps SHELL — the step header
// only. The step CONTENT is hand-rolled below and the embedded DocDetail stays
// mounted across steps (v-show), so no StepPanels: StepPanels unmount the
// inactive panel, which would drop the create form's state between steps.
import Stepper from "primevue/stepper"
import StepList from "primevue/steplist"
import Step from "primevue/step"
import { useUiConfigStore } from "@yrp/web-engine"
import { useAppConfirm } from "@/composables/useConfirm"
import { useAppToast } from "@/composables/useToast"
import { getRegistryByRoute } from "@/config/doctypes"
import DcEntryChips from "./DcEntryChips.vue"
import DocDetail from "./DocDetail.vue"
// The SAME Link/typeahead component the create form uses for its own work_order
// field — reused in wizard step 1 so the user can reach ANY submitted/open Work
// Order, not just the recent-8 quick-pick chips.
import LinkField from "@/components/LinkField.vue"

const props = defineProps({
	docRoute: { type: String, required: true },
})

// saved <name> — an embedded DocDetail create/save succeeded; the overlay is
// already closing — the host list should refresh its rows/counts. (The success
// toast already fired inside DocDetail — same as today; no double-toast here.)
const emit = defineEmits(["saved"])

const route = useRoute()
const router = useRouter()
const uiStore = useUiConfigStore()
const confirm = useAppConfirm()
const toast = useAppToast()
const registry = computed(() => getRegistryByRoute(props.docRoute))

// ── Query protocol ──────────────────────────────────────────────────────────
const detailName = computed(() => {
	const raw = route.query.detail
	const v = Array.isArray(raw) ? raw[0] : raw
	return typeof v === "string" && v ? v : null
})
const createOpen = computed(() => route.query.new === "1")

// ── Knob gates (null-safe store getters; absent knob = nothing renders) ────
const detailPosition = computed(() => {
	const p = uiStore.detailKnob?.position
	return p === "right" || p === "center" || p === "bottom-sheet" ? p : null
})
const entryPopup = computed(() => uiStore.entryKnob?.mode === "popup")

// ── DC entry variants (dcEntry knob — Delivery Challan lists ONLY) ─────────
// The same ?new=1 opens a DC-specific entry overlay INSTEAD of the entry.mode
// popup — the doctype-specific knob wins over the generic `entry` for DC. Two
// overlay shapes, all re-hosting the SAME embedded create-mode DocDetail (same
// autofill, same buildPayload/onSave save path — presentation only):
//   BOTTOM-SHEET family (bottom Drawer + WO/Job-worker quick-pick chips):
//     "size-matrix" (demo-7), "sheet-tiles" (demo-3), "touch-rows" (demo-4).
//     They differ only by qtyControl / supplierPicker and a cosmetic body class.
//   "wizard-steps" (demo-2): a centered Dialog with a PrimeVue Stepper shell
//     guiding WO pick -> Items -> Job-worker -> Review + Save.
// Knob absent / other variants / other doctypes → all stay false and nothing
// changes (parity law).
const dcVariant = computed(() =>
	props.docRoute === "delivery-challan" ? uiStore.dcEntryKnob?.variant || null : null,
)
const DC_BOTTOM_SHEET_VARIANTS = new Set(["size-matrix", "sheet-tiles", "touch-rows"])
const dcBottomSheet = computed(() => DC_BOTTOM_SHEET_VARIANTS.has(dcVariant.value))
const dcWizard = computed(() => dcVariant.value === "wizard-steps")
const dcOverlayActive = computed(() => dcBottomSheet.value || dcWizard.value)
// supplierPicker "chips"/"buttons" → Job-worker quick-pick strip (the STYLE
// differs); "select"/absent → the form's untouched Link field only.
const dcSupplierPicker = computed(() => uiStore.dcEntryKnob?.supplierPicker || "select")
const dcSupplierStrip = computed(() => dcSupplierPicker.value === "chips" || dcSupplierPicker.value === "buttons")
const dcSupplierStyle = computed(() => (dcSupplierPicker.value === "buttons" ? "buttons" : "chips"))

const drawerVisible = computed(
	() => !!detailName.value && (detailPosition.value === "right" || detailPosition.value === "bottom-sheet"),
)
const centerVisible = computed(() => !!detailName.value && detailPosition.value === "center")
const entryVisible = computed(() => createOpen.value && entryPopup.value && !dcOverlayActive.value)
const dcSheetVisible = computed(() => createOpen.value && dcBottomSheet.value)
const dcWizardVisible = computed(() => createOpen.value && dcWizard.value)

// entry.popupPosition uses the server's hyphenated 9-position vocabulary
// ("top-left" …); PrimeVue Dialog's `position` prop wants the unhyphenated
// form. Off-vocabulary values fall back to center (soft, mirrors the server's
// warn-don't-block stance).
const PV_DIALOG_POSITIONS = new Set(["center", "top", "bottom", "left", "right", "topleft", "topright", "bottomleft", "bottomright"])
const entryDialogPosition = computed(() => {
	const p = String(uiStore.entryKnob?.popupPosition || "center").replace(/-/g, "")
	return PV_DIALOG_POSITIONS.has(p) ? p : "center"
})

const overlayTitle = computed(() => registry.value?.label || props.docRoute)
const createTitle = computed(() => `New ${overlayTitle.value}`)

// ── Close protocol ──────────────────────────────────────────────────────────
const detailRef = ref(null)
const createRef = ref(null)

// ── Chip picks (size-matrix sheet) ──────────────────────────────────────────
// A chip relays through the embedded DocDetail's setFormField — the SAME
// assign + onFieldChanged path a LinkField pick runs, so the DC autofill
// (get_work_order_defaults → header fields + size-pivot grid loadData)
// provably fires. The picked values are tracked here ONLY to highlight the
// active chip; the form state stays inside DocDetail.
const dcPickedWo = ref("")
const dcPickedSupplier = ref("")
// wizard-steps step-1 typeahead value (transient — cleared after a pick relays).
const wizardWoSearch = ref("")
// Desk parity (delivery_challan.js set_query / config/fields/delivery-challan.js):
// a DC targets ONLY submitted, not-closed Work Orders — the SAME filter the
// form's own work_order Link search uses. LinkField's default search runs
// searchLink("Work Order", q, filters), so step 1 reaches EVERY valid WO, not
// just the recent-8 chips.
const WO_SEARCH_FILTERS = { docstatus: 1, open_status: ["!=", "Close"] }
// wizard-steps active step ("1".."4"), reset with the picks whenever the DC
// entry overlay (sheet OR wizard) closes.
const wizardStep = ref("1")
watch(
	() => dcSheetVisible.value || dcWizardVisible.value,
	(open) => {
		if (!open) {
			dcPickedWo.value = ""
			dcPickedSupplier.value = ""
			wizardWoSearch.value = ""
			wizardStep.value = "1"
		}
	},
)
// setFormField returns false while the embedded create form is still building
// (its getdoctype round-trip usually outlasts the chips' small getList) — a
// pick landing in that window would otherwise highlight the chip while the
// field was never set and the autofill never ran. Highlight only a pick that
// actually landed; tell the user to re-tap otherwise.
async function onPickWo(name) {
	if (await createRef.value?.setFormField("work_order", name)) dcPickedWo.value = name
	else toast.info("Form is still loading", "Tap the Work Order again in a moment.")
}
async function onPickSupplier(name) {
	if (await createRef.value?.setFormField("supplier", name)) dcPickedSupplier.value = name
	else toast.info("Form is still loading", "Tap the Job-worker again in a moment.")
}

// ── wizard-steps handlers ────────────────────────────────────────────────────
// Same setFormField relay as the sheet chips (identical assign + autofill
// cascade); the wizard only adds step navigation. A WO pick auto-advances to the
// Items step (demo-2). Save fires the embedded form's own onSave via the exposed
// save() — the SAME buildPayload/onSave/useDoc.save path, and the create still
// emits `saved` for onSaved to close + refresh the list.
async function onWizardPickWo(name) {
	if (await createRef.value?.setFormField("work_order", name)) {
		dcPickedWo.value = name
		wizardStep.value = "2"
	} else {
		toast.info("Form is still loading", "Tap the Work Order again in a moment.")
	}
}
async function onWizardPickSupplier(name) {
	if (await createRef.value?.setFormField("supplier", name)) dcPickedSupplier.value = name
	else toast.info("Form is still loading", "Tap the Job-worker again in a moment.")
}
// Step-1 typeahead select (any submitted/open WO, not just the recent-8 chips):
// relay through the SAME onWizardPickWo path the chips use — identical
// setFormField autofill + auto-advance to the Items step — then clear the
// transient search text.
async function onWizardWoSearchSelect(e) {
	const name = e?.value || ""
	if (!name) return
	wizardWoSearch.value = ""
	await onWizardPickWo(name)
}
// Save fires the embedded form's own onSave via the exposed save() — the SAME
// buildPayload/onSave/useDoc.save path. onSave resolves `false` when it was
// BLOCKED (a missing required field, or a server reject): its red field +
// banner live INSIDE the step-2 form, which is display:none on the Review step.
// Every real form field (work_order, supplier, warehouses, the size-pivot grid)
// lives on step 2, so that IS the step containing the first invalid field —
// return there to reveal the form (banner + reddened field). onSave's own
// focus/scroll fired while the form was still hidden (display:none → no-op), so
// after the step is visible we re-run focusFirstInvalid on nextTick to actually
// bring the offending field into view + focus it — never just a toast. A
// successful save resolves `true` and the overlay closes via onSaved.
async function onWizardSave() {
	if ((await createRef.value?.save?.()) === false) {
		wizardStep.value = "2"
		await nextTick()
		createRef.value?.focusFirstInvalid?.()
	}
}

// Remove our query keys (detail + new) — the ONLY state the overlay owns.
// Seed params that arrived with ?new=1 and the list's own filters/status keys
// are left untouched (the list-page watcher only reacts to filters/status).
function closeOverlay() {
	const q = { ...route.query }
	delete q.detail
	delete q.new
	router.replace({ query: q })
}

// The embedded instance currently showing (create overlays own createRef;
// the detail overlays own detailRef).
function activeInstance() {
	return entryVisible.value || dcSheetVisible.value || dcWizardVisible.value ? createRef.value : detailRef.value
}

// X / scrim / host-Escape all land here. Query-only route changes never fire
// onBeforeRouteLeave, so the host mirrors DocDetail's dirty guard before
// actually closing (the overlay stays open until we replace the query — the
// `visible` props are pure route-derived computeds).
function onRequestClose() {
	const inst = activeInstance()
	if (inst?.isFormMode && inst?.isDirty) {
		confirm.require({
			header: "Discard unsaved changes?",
			message: "You have unsaved changes on this form. Close without saving?",
			icon: "pi pi-exclamation-triangle",
			acceptLabel: "Discard",
			acceptClass: "p-button-danger",
			rejectLabel: "Keep editing",
			accept: () => {
				// Clear the dirty flag BEFORE removing the query (DocDetail's own
				// route-leave accept does the same) so the route-update guard below
				// doesn't chain this confirm into a second one.
				inst.isDirty = false
				closeOverlay()
			},
		})
		return
	}
	closeOverlay()
}

function onVisibleChange(v) {
	if (!v) onRequestClose()
}

// ── Back-button dirty guard ─────────────────────────────────────────────────
// The opener PUSHES ?detail/?new so Back closes the overlay — but a query-only
// history pop stays on the same route record: onBeforeRouteLeave never fires
// and the `visible` computeds would simply unmount a dirty embedded form (15
// typed size-matrix cells gone on the most natural tablet gesture). Query-only
// navigations DO fire update guards (same pattern as IPDConfigView), so run
// the identical "Discard unsaved changes?" confirm here. Covers Back/forward
// AND programmatic query removals; navigations that keep our keys untouched
// (list filter/status changes) pass straight through — parity intact.
function overlayQueryOf(query) {
	const raw = query?.detail
	const detail = Array.isArray(raw) ? raw[0] : raw
	return `${typeof detail === "string" ? detail : ""}|${query?.new === "1" ? "1" : ""}`
}
onBeforeRouteUpdate((to, from, next) => {
	if (overlayQueryOf(to.query) === overlayQueryOf(from.query)) return next()
	const inst = activeInstance()
	if (!(inst?.isFormMode && inst?.isDirty)) return next()
	confirm.require({
		header: "Discard unsaved changes?",
		message: "You have unsaved changes on this form. Close without saving?",
		icon: "pi pi-exclamation-triangle",
		acceptLabel: "Discard",
		acceptClass: "p-button-danger",
		rejectLabel: "Keep editing",
		accept: () => {
			inst.isDirty = false
			next()
		},
		reject: () => next(false),
	})
})

// ── Host-owned Escape ───────────────────────────────────────────────────────
// PrimeVue 4's Drawer and Dialog each bind an independent document keydown
// listener with no topmost arbitration — with a nested modal (Print / SMS /
// e-Waybill / any confirm) open inside the host overlay, one Escape would
// close BOTH layers. The host overlays render with closeOnEscape=false and
// this single handler closes the host only when it is the topmost layer: any
// foreign PrimeVue overlay in the DOM (a dialog/drawer mask that is not ours,
// a popup menu, a popover, an open picker panel) swallows the press. Inner
// modals keep their own Escape handling untouched.
function hasForeignOverlayOpen() {
	for (const mask of document.querySelectorAll(".p-dialog-mask, .p-drawer-mask")) {
		if (!mask.querySelector(".esd-doc-overlay-dialog, .esd-doc-overlay-drawer")) return true
	}
	return !!document.querySelector(
		".p-menu-overlay, .p-tieredmenu-overlay, .p-popover, .p-select-overlay, .p-autocomplete-overlay, .p-multiselect-overlay, .p-datepicker-panel",
	)
}
function onHostKeydown(e) {
	if (e.code !== "Escape" || e.isComposing) return
	if (!(drawerVisible.value || centerVisible.value || entryVisible.value || dcSheetVisible.value || dcWizardVisible.value)) return
	if (hasForeignOverlayOpen()) return
	onRequestClose()
}
onMounted(() => document.addEventListener("keydown", onHostKeydown))
onBeforeUnmount(() => document.removeEventListener("keydown", onHostKeydown))

// A successful create/save inside the overlay: close it, then tell the list
// page to refresh (rows + tab counts).
function onSaved(name) {
	closeOverlay()
	emit("saved", name)
}
</script>

<!-- Unscoped on purpose: Drawer/Dialog teleport to <body>, so scoped rules
     never reach them. Everything is namespaced under esd-doc-overlay-*. -->
<style>
.esd-doc-overlay-drawer--right {
	width: min(720px, 92vw) !important;
}
@media (max-width: 640px) {
	.esd-doc-overlay-drawer--right {
		width: 100vw !important;
	}
}
.esd-doc-overlay-drawer--bottom {
	height: 85vh !important;
}
.esd-doc-overlay-drawer .p-drawer-content {
	overflow-y: auto;
	background: var(--esd-bg);
}
.esd-doc-overlay-dialog {
	max-height: 92vh;
}
.esd-doc-overlay-dialog .p-dialog-content {
	overflow-y: auto;
	background: var(--esd-bg);
}

/* ── DC entry: wizard-steps (item 5) ── */
.esd-dc-wizard-steps {
	margin-bottom: 14px;
}
.esd-dc-wizard-panel {
	display: flex;
	flex-direction: column;
	gap: 14px;
}
.esd-dc-wizard-hint {
	font-size: 0.82rem;
	color: var(--esd-muted);
	margin: 0;
}
/* Step-1 "search any Work Order" typeahead — the escape hatch past the recent-8
   chips. Same LinkField the form uses, laid out as a labelled row. */
.esd-dc-wizard-search {
	display: flex;
	flex-direction: column;
	gap: 6px;
}
.esd-dc-wizard-search-label {
	font-size: 0.72rem;
	font-weight: 600;
	text-transform: uppercase;
	letter-spacing: 0.04em;
	color: var(--esd-muted);
}
.esd-dc-wizard-nav {
	display: flex;
	justify-content: space-between;
	gap: 10px;
	padding-top: 6px;
	border-top: 1px dashed var(--esd-line);
	margin-top: 4px;
}
.esd-dc-wizard-btn {
	border: 1px solid var(--esd-line);
	border-radius: 8px;
	padding: 9px 18px;
	font-size: 0.88rem;
	font-weight: 600;
	cursor: pointer;
	background: var(--esd-card);
	color: var(--esd-ink-2);
	transition: border-color 0.15s, background 0.15s, color 0.15s;
}
.esd-dc-wizard-btn.ghost:hover {
	border-color: var(--esd-accent2);
	color: var(--esd-ink);
}
.esd-dc-wizard-btn.primary {
	background: var(--esd-accent2);
	border-color: var(--esd-accent2);
	color: var(--esd-on-accent, #fff);
}
.esd-dc-wizard-btn.primary:hover {
	filter: brightness(1.05);
}
.esd-dc-wizard-summary {
	display: flex;
	flex-direction: column;
	gap: 10px;
	padding: 14px 16px;
	background: var(--esd-card);
	border: 1px solid var(--esd-line);
	border-radius: 10px;
}
.esd-dc-wizard-srow {
	display: flex;
	justify-content: space-between;
	gap: 12px;
	font-size: 0.9rem;
}
.esd-dc-wizard-srow span {
	color: var(--esd-muted);
}
.esd-dc-wizard-srow strong {
	color: var(--esd-ink);
	font-weight: 700;
}

/* ── DC entry: sheet-tiles / touch-rows cosmetic body accents (item 5).
   The grid itself is the SAME DocDetail size-pivot editor; qtyControl does the
   real touch sizing. These only add a little breathing room. ── */
.esd-dc-sheet--touch-rows .p-drawer-content {
	font-size: 1.02rem;
}
.esd-dc-sheet--sheet-tiles .child-editor {
	border-radius: 12px;
}
</style>
