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

	<!-- Entry: DC size-matrix bottom sheet (dcEntry.variant "size-matrix",
	     demo-7). The real /web DC form already IS the size-pivot editor —
	     the sheet only re-hosts the SAME embedded create-mode DocDetail
	     (same autofill, same buildPayload/onSave save path) and adds the
	     quick-pick chip strips above it. -->
	<Drawer
		:visible="dcSheetVisible"
		position="bottom"
		:header="createTitle"
		:blockScroll="true"
		:closeOnEscape="false"
		class="esd-doc-overlay-drawer esd-doc-overlay-drawer--bottom"
		@update:visible="onVisibleChange"
	>
		<DcEntryChips
			v-if="dcSheetVisible"
			show-wo-chips
			:show-supplier-chips="dcSupplierChips"
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
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { onBeforeRouteUpdate, useRoute, useRouter } from "vue-router"
import Dialog from "primevue/dialog"
import Drawer from "primevue/drawer"
import { useUiConfigStore } from "@yrp/web-engine"
import { useAppConfirm } from "@/composables/useConfirm"
import { useAppToast } from "@/composables/useToast"
import { getRegistryByRoute } from "@/config/doctypes"
import DcEntryChips from "./DcEntryChips.vue"
import DocDetail from "./DocDetail.vue"

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

// ── DC entry variant (dcEntry knob — Delivery Challan lists ONLY) ──────────
// "size-matrix" (demo-7): the same ?new=1 opens the bottom-sheet entry
// INSTEAD of the entry.mode popup — the doctype-specific knob wins over the
// generic `entry` for DC. Knob absent / other variants / other doctypes →
// this stays false and nothing changes (parity law).
const dcSizeMatrix = computed(
	() => props.docRoute === "delivery-challan" && uiStore.dcEntryKnob?.variant === "size-matrix",
)
// supplierPicker "chips" → Job-worker quick-pick strip; "select"/absent →
// the form's untouched Link field only.
const dcSupplierChips = computed(() => uiStore.dcEntryKnob?.supplierPicker === "chips")

const drawerVisible = computed(
	() => !!detailName.value && (detailPosition.value === "right" || detailPosition.value === "bottom-sheet"),
)
const centerVisible = computed(() => !!detailName.value && detailPosition.value === "center")
const entryVisible = computed(() => createOpen.value && entryPopup.value && !dcSizeMatrix.value)
const dcSheetVisible = computed(() => createOpen.value && dcSizeMatrix.value)

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
watch(dcSheetVisible, (v) => {
	if (!v) {
		dcPickedWo.value = ""
		dcPickedSupplier.value = ""
	}
})
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
	return entryVisible.value || dcSheetVisible.value ? createRef.value : detailRef.value
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
	if (!(drawerVisible.value || centerVisible.value || entryVisible.value || dcSheetVisible.value)) return
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
</style>
