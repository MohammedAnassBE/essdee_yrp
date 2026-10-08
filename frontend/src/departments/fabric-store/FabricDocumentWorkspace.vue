<template>
	<section
		class="fabric-document-workspace erp-card"
		:class="[`fabric-document-workspace--${presentation}`, { 'fabric-document-workspace--compact-mobile-rail': compactMobileRail }]"
		:aria-busy="loading"
	>
		<div class="fabric-document-workspace__chrome">
		<header class="fabric-document-workspace__header">
			<InlinePageNavigation v-if="presentation === 'page'" :title-target="headingId" />
			<slot name="header" :record="record" :workspace="workspace" :heading-id="headingId">
				<div class="fabric-document-workspace__identity">
					<div>
						<h1 :id="headingId">{{ title }}</h1>
						<span>{{ record.name || "New document" }}</span>
					</div>
					<DocumentStatusBadge v-if="record.status" :docstatus="record.docstatus" :label="record.status" />
				</div>
			</slot>

			<div class="fabric-document-workspace__header-actions">
				<Button
					v-if="presentation === 'embedded'"
					icon="pi pi-times"
					severity="secondary"
					text
					rounded
					aria-label="Close workspace"
					:disabled="Boolean(acting)"
					@click="requestClose"
				/>
			</div>
		</header>

		<div v-if="!loading" class="fabric-document-workspace__commandbar" aria-label="Document actions">
			<div class="fabric-document-workspace__domain-actions">
				<slot name="header-actions" :workspace="workspace" :acting="acting" />
			</div>
			<div class="fabric-document-workspace__lifecycle-actions">
				<Button v-if="showLifecycleActions && capabilities.cancel" :label="capabilityLabel('cancel', 'Cancel Document')" icon="pi pi-ban" severity="danger" outlined :loading="acting === 'cancel'" :disabled="Boolean(acting)" @click="emit('action', 'cancel')" />
				<Button v-if="showLifecycleActions && capabilities.amend" :label="capabilityLabel('amend', 'Amend')" icon="pi pi-copy" severity="secondary" outlined :loading="acting === 'amend'" :disabled="Boolean(acting)" @click="emit('action', 'amend')" />
				<Button v-if="showLifecycleActions && capabilities.save" :label="capabilityLabel('save', 'Save')" icon="pi pi-save" severity="secondary" outlined :loading="acting === 'save'" :disabled="Boolean(acting)" @click="emit('action', 'save')" />
				<Button v-if="showLifecycleActions && capabilities.submit" :label="capabilityLabel('submit', 'Submit')" icon="pi pi-check" :loading="acting === 'submit'" :disabled="Boolean(acting)" @click="emit('action', 'submit')" />
				<Button
					v-if="record.name"
					icon="pi pi-refresh"
					severity="secondary"
					text
					rounded
					aria-label="Refresh"
					:loading="acting === 'reload'"
					:disabled="Boolean(acting)"
					@click="emit('reload')"
				/>
				<DocumentPrintButton
					v-if="canPrint"
					:doctype="record.doctype || doctype"
					:name="record.name"
					:formats="workspace.print_formats || []"
					:disabled="Boolean(acting)"
				/>
			</div>
		</div>
		</div>

		<div v-if="loading" class="fabric-document-workspace__loading" aria-label="Loading document">
			<Skeleton height="3.5rem" />
			<Skeleton height="10rem" />
			<Skeleton height="18rem" />
		</div>
		<div v-else class="fabric-document-workspace__content" tabindex="0" role="region" :aria-label="`${title} document content`">
			<div v-if="error && !hasWorkspace" class="fabric-document-workspace__error-recovery">
				<i class="pi pi-cloud-times" aria-hidden="true" />
				<div><strong>{{ title }} could not be loaded</strong><span>{{ error || "Try loading the document again." }}</span></div>
				<Button label="Retry" icon="pi pi-refresh" severity="secondary" outlined :loading="acting === 'reload'" @click="emit('reload')" />
			</div>
			<template v-if="hasWorkspace">
				<div class="fabric-document-workspace__columns">
					<aside class="fabric-document-workspace__rail" aria-label="Document totals and context" :tabindex="compactMobileRail ? 0 : undefined">
						<slot name="rail" :workspace="workspace">
							<div v-for="total in workspace.totals || []" :key="total.fieldname" class="fabric-document-workspace__metric">
								<span>{{ total.label }}</span>
								<strong>{{ formatValue(total.value) }}</strong>
							</div>
						</slot>
					</aside>
					<div class="fabric-document-workspace__main">
						<section v-if="$slots.fields" class="fabric-document-workspace__fields">
							<slot name="fields" :workspace="workspace" />
						</section>
						<section v-if="$slots['secondary-fields']" class="fabric-document-workspace__secondary-fields">
							<slot name="secondary-fields" :workspace="workspace" />
						</section>
						<section v-if="$slots.matrix" class="fabric-document-workspace__matrix">
							<slot name="matrix" :workspace="workspace" />
						</section>
						<div v-if="$slots['after-matrix']" class="fabric-document-workspace__after-matrix">
							<slot name="after-matrix" :workspace="workspace" />
						</div>
					</div>
				</div>
				<section v-if="$slots.panel" class="fabric-document-workspace__panel">
					<slot name="panel" :workspace="workspace" />
				</section>
			</template>
		</div>

	</section>

	<DocumentErrorDialog
		:message="hasWorkspace ? error : ''"
		:title="`${title} could not be completed`"
	/>

	<Dialog v-model:visible="discardVisible" class="erp-dialog--sm" modal header="Discard unsaved changes?" :closable="false">
		<p class="fabric-document-workspace__discard-copy">This document has unsaved changes. Close it and discard those changes?</p>
		<template #footer>
			<Button label="Keep Editing" severity="secondary" text @click="keepEditing" />
			<Button label="Discard Changes" severity="danger" @click="discardChanges" />
		</template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import Skeleton from "primevue/skeleton"
import { computed, onBeforeUnmount, onMounted, ref } from "vue"
import { onBeforeRouteLeave } from "vue-router"

import DocumentPrintButton from "../../components/documents/DocumentPrintButton.vue"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import DocumentStatusBadge from "../../components/documents/DocumentStatusBadge.vue"
import InlinePageNavigation from "../../components/navigation/InlinePageNavigation.vue"

const props = defineProps({
	doctype: { type: String, required: true },
	title: { type: String, required: true },
	workspace: { type: Object, default: () => ({}) },
	presentation: { type: String, default: "page", validator: (value) => ["page", "embedded"].includes(value) },
	loading: { type: Boolean, default: false },
	error: { type: String, default: "" },
	dirty: { type: Boolean, default: false },
	acting: { type: String, default: "" },
	showLifecycleActions: { type: Boolean, default: true },
	compactMobileRail: { type: Boolean, default: false },
})
const emit = defineEmits(["reload", "action", "close"])
const headingId = computed(() => `${props.doctype.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-workspace-title`)

const discardVisible = ref(false)
let pendingNavigation = null
const record = computed(() => props.workspace.record || {})
const capabilities = computed(() => props.workspace.capabilities || {})
const hasWorkspace = computed(() => Boolean(Object.keys(props.workspace || {}).length))
const canPrint = computed(() => Boolean(record.value.name && props.workspace.permissions?.can_print))

function capabilityLabel(name, fallback) { return name === "save" ? fallback : capabilities.value[name]?.label || fallback }
function formatValue(value) {
	if (value === null || value === undefined || value === "") return "—"
	return typeof value === "number" ? value.toLocaleString("en-IN", { maximumFractionDigits: 3 }) : String(value)
}
function requestClose() {
	if (props.dirty) { discardVisible.value = true; return }
	emit("close")
}
function keepEditing() {
	discardVisible.value = false
	if (pendingNavigation) { pendingNavigation(false); pendingNavigation = null }
}
function discardChanges() {
	discardVisible.value = false
	if (pendingNavigation) {
		const next = pendingNavigation
		pendingNavigation = null
		next()
		return
	}
	emit("close")
}
function beforeUnload(event) {
	if (!props.dirty) return
	event.preventDefault()
	event.returnValue = ""
}

onBeforeRouteLeave((_to, _from, next) => {
	if (!props.dirty) return next()
	pendingNavigation = next
	discardVisible.value = true
})
onMounted(() => window.addEventListener("beforeunload", beforeUnload))
onBeforeUnmount(() => window.removeEventListener("beforeunload", beforeUnload))
</script>

<style scoped>
.fabric-document-workspace { display: flex; width: 100%; min-width: 0; min-height: 0; overflow: hidden; flex-direction: column; border-color: var(--erp-border); background: var(--erp-surface); box-shadow: var(--erp-shadow-sm); }
.fabric-document-workspace--page { height: calc(100dvh - var(--erp-shell-header-height) - 97px); min-height: min(620px, calc(100dvh - var(--erp-shell-header-height) - 97px)); }
.fabric-document-workspace--embedded { height: min(82dvh, 920px); border: 0; box-shadow: none; }
.fabric-document-workspace--embedded .fabric-document-workspace__header { min-height: 48px; padding-block: 6px; }
.fabric-document-workspace__chrome { position: relative; z-index: var(--erp-layer-sticky); flex: 0 0 auto; background: var(--erp-surface); box-shadow: 0 3px 10px rgb(16 24 40 / 4%); }
.fabric-document-workspace__header { display: flex; min-height: 52px; align-items: center; justify-content: space-between; gap: var(--erp-space-3); padding: 7px clamp(14px, 1.4vw, 22px); border-top: 3px solid var(--erp-accent); border-bottom: 1px solid var(--erp-border); background: color-mix(in srgb, var(--erp-surface) 97%, var(--erp-accent-soft)); }
.fabric-document-workspace__identity { display: flex; min-width: 0; align-items: center; gap: 12px; }
.fabric-document-workspace__identity > div { display: grid; min-width: 0; gap: 2px; }
.fabric-document-workspace__identity h1 { margin: 0; color: var(--erp-text); font-size: 19px; line-height: 1.15; letter-spacing: -.018em; }
.fabric-document-workspace__identity span { overflow: hidden; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); font-weight: 650; text-overflow: ellipsis; white-space: nowrap; font-variant-numeric: tabular-nums; }
.fabric-document-workspace__header-actions, .fabric-document-workspace__domain-actions, .fabric-document-workspace__lifecycle-actions { display: flex; align-items: center; gap: 6px; }
.fabric-document-workspace__commandbar { display: flex; min-height: 42px; align-items: center; justify-content: space-between; gap: 6px 12px; padding: 4px clamp(14px, 1.4vw, 22px); border-bottom: 1px solid var(--erp-border); background: var(--erp-surface); flex-wrap: nowrap; }
.fabric-document-workspace__domain-actions, .fabric-document-workspace__lifecycle-actions { min-width: 0; flex-wrap: nowrap; }
.fabric-document-workspace__lifecycle-actions { justify-content: flex-end; margin-left: auto; }
.fabric-document-workspace__commandbar :deep(.p-button) { transition: color 150ms ease-out, background-color 150ms ease-out, border-color 150ms ease-out, transform 150ms ease-out; }
.fabric-document-workspace__commandbar :deep(.p-button:active:not(:disabled)) { transform: scale(.96); }
.fabric-document-workspace__loading, .fabric-document-workspace__content { min-height: 0; flex: 1; padding: clamp(10px, 1.2vw, 18px); background: color-mix(in srgb, var(--erp-bg) 80%, white); }
.fabric-document-workspace__loading { display: grid; align-content: start; gap: var(--erp-space-3); }
.fabric-document-workspace__content { overflow-y: auto; scrollbar-gutter: stable; }
.fabric-document-workspace__error-recovery { display: grid; min-height: 230px; align-content: center; justify-items: center; gap: 9px; padding: var(--erp-space-5); color: var(--erp-text-muted); text-align: center; border: 1px dashed var(--erp-border-strong); border-radius: var(--erp-panel-radius); background: var(--erp-surface); }
.fabric-document-workspace__error-recovery > i { color: var(--erp-danger); font-size: 25px; }
.fabric-document-workspace__error-recovery > div { display: grid; gap: 4px; }
.fabric-document-workspace__error-recovery strong { color: var(--erp-text); }
.fabric-document-workspace__error-recovery span { font-size: var(--erp-font-size-caption); }
.fabric-document-workspace__columns { display: grid; grid-template-areas: "main rail"; grid-template-columns: minmax(0, 1fr) minmax(260px, 288px); align-items: start; gap: clamp(12px, 1.3vw, 20px); }
.fabric-document-workspace__main, .fabric-document-workspace__fields, .fabric-document-workspace__matrix, .fabric-document-workspace__secondary-fields, .fabric-document-workspace__after-matrix, .fabric-document-workspace__rail, .fabric-document-workspace__panel { display: grid; min-width: 0; gap: var(--erp-space-3); }
.fabric-document-workspace__main { grid-area: main; }
.fabric-document-workspace__rail { position: sticky; top: 0; align-content: start; gap: 0; overflow: hidden; border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); background: var(--erp-surface); }
.fabric-document-workspace__rail { grid-area: rail; }
.fabric-document-workspace__metric { display: grid; min-height: 70px; align-content: center; gap: 4px; padding: 11px 13px; border: 1px solid color-mix(in srgb, var(--erp-accent) 20%, var(--erp-border)); border-radius: var(--erp-control-radius); background: color-mix(in srgb, var(--erp-accent-soft) 76%, white); box-shadow: inset 3px 0 0 color-mix(in srgb, var(--erp-accent) 76%, white); }
.fabric-document-workspace__metric span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 750; letter-spacing: .035em; text-transform: uppercase; }
.fabric-document-workspace__metric strong { color: var(--erp-accent-hover); font-size: 21px; font-weight: 780; font-variant-numeric: tabular-nums; }
.fabric-document-workspace__panel { margin-top: var(--erp-space-3); }
.fabric-document-workspace__discard-copy { margin: 0; color: var(--erp-text-muted); line-height: 1.55; }
@media (min-width: 621px) { .fabric-document-workspace__content { --erp-control-height: 36px; } }
@media (max-width: 900px) {
	.fabric-document-workspace__columns { grid-template-areas: "main" "rail"; grid-template-columns: 1fr; }
	.fabric-document-workspace__rail { position: static; grid-template-columns: repeat(2, minmax(0, 1fr)); }
	.fabric-document-workspace__rail > :nth-child(odd):not(:last-child) { border-right: 1px solid var(--erp-border); }
	.fabric-document-workspace__rail :deep(.fabric-document-workspace__metric-group) { grid-column: 1 / -1; }
	.fabric-document-workspace--compact-mobile-rail .fabric-document-workspace__columns { grid-template-areas: "rail" "main"; }
	.fabric-document-workspace--compact-mobile-rail .fabric-document-workspace__rail { display: flex; overflow-x: auto; overflow-y: hidden; scroll-snap-type: x proximity; scrollbar-width: thin; -webkit-mask-image: linear-gradient(to right, #000 0, #000 calc(100% - 18px), transparent 100%); mask-image: linear-gradient(to right, #000 0, #000 calc(100% - 18px), transparent 100%); }
	.fabric-document-workspace--compact-mobile-rail .fabric-document-workspace__rail:focus-visible { outline: 2px solid var(--erp-accent-dark); outline-offset: 2px; }
	.fabric-document-workspace--compact-mobile-rail .fabric-document-workspace__rail :deep(.fabric-document-workspace__metric-group) { display: contents; }
	.fabric-document-workspace--compact-mobile-rail .fabric-document-workspace__rail > *,
	.fabric-document-workspace--compact-mobile-rail .fabric-document-workspace__rail :deep(.fabric-document-workspace__metric-group > *) { box-sizing: border-box; width: clamp(168px, 42vw, 220px); height: 76px; min-height: 76px; flex: 0 0 auto; border-right: 1px solid var(--erp-border); border-bottom: 0; scroll-snap-align: start; }
}
@media (max-width: 620px) { .fabric-document-workspace--page { height: calc(100dvh - var(--erp-shell-header-height) - 76px); min-height: 0; border-right: 0; border-left: 0; border-radius: 0; } .fabric-document-workspace--embedded { height: 100%; min-height: 0; } .fabric-document-workspace__header { min-height: 52px; padding: 7px var(--erp-space-3); } .fabric-document-workspace__commandbar { align-items: center; gap: 4px; padding: 4px var(--erp-space-3); flex-wrap: nowrap; overflow-x: auto; overflow-y: hidden; scrollbar-width: thin; } .fabric-document-workspace__domain-actions, .fabric-document-workspace__lifecycle-actions { width: auto; min-width: max-content; justify-content: flex-start; margin-left: 0; } .fabric-document-workspace__domain-actions { flex: 1 0 auto; } .fabric-document-workspace__lifecycle-actions { gap: 2px; flex: 0 0 auto; } .fabric-document-workspace__lifecycle-actions :deep(.document-print-button) { width: var(--erp-control-height); padding-inline: 0; } .fabric-document-workspace__lifecycle-actions :deep(.document-print-button .p-button-label) { display: none; } .fabric-document-workspace__content { padding: var(--erp-space-2); } }
@media (prefers-reduced-motion: reduce) { .fabric-document-workspace__commandbar :deep(.p-button) { transition: none; } .fabric-document-workspace__commandbar :deep(.p-button:active:not(:disabled)) { transform: none; } }
</style>
