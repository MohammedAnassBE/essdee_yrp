<template>
	<section
		class="fabric-document-workspace erp-card"
		:class="[`fabric-document-workspace--${presentation}`, { 'fabric-document-workspace--compact-mobile-rail': compactMobileRail }]"
		:aria-busy="loading"
	>
		<div class="fabric-document-workspace__chrome">
		<header class="fabric-document-workspace__header erp-page-header">
			<InlinePageNavigation
				v-if="presentation === 'page'"
				:title-target="headingId"
				:show-document-navigation="Boolean(record.name)"
				:current-name="record.name || ''"
				:document-label="title"
				:navigation-disabled="dirty || Boolean(acting)"
			/>
			<div class="fabric-document-workspace__heading">
				<slot name="header" :record="record" :workspace="workspace" :heading-id="headingId">
					<div class="fabric-document-workspace__identity">
						<div>
							<h1 class="erp-doc-title" :id="headingId">{{ title }}</h1>
							<span class="erp-doc-id">{{ record.name || "New document" }}</span>
						</div>
						<DocumentStatusBadge v-if="record.status" :docstatus="record.docstatus" :label="record.status" />
					</div>
				</slot>
			</div>

			<div class="fabric-document-workspace__header-actions">
				<DocumentSaveState v-if="showSaveState" :saving="acting === 'save'" :dirty="dirty" :saved-at="savedAt" />
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
			<fieldset class="fabric-document-workspace__action-set" :disabled="isDeleted">
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
					:loading="acting === 'reload' || live.reloading.value"
					:disabled="Boolean(acting)"
					@click="requestRefresh"
				/>
				<CustomPrintButtons v-if="doctype === 'SD YRP Lot'" :doctype="doctype" :record="{ ...record, has_cloth_program: workspace.has_cloth_program ?? record.has_cloth_program }" :permissions="workspace.permissions" :disabled="Boolean(acting)" />
				<DocumentPrintButton
					v-if="canPrint"
					:doctype="record.doctype || doctype"
					:name="record.name"
					:formats="workspace.permissions?.can_print === undefined ? null : (workspace.print_formats || [])"
					:label="printLabel"
					:docstatus="record.docstatus"
					:disabled="Boolean(acting)"
				/>
				<DocumentDeleteButton
					:document-label="title"
					v-if="showDelete && record.name"
					:doctype="record.doctype || doctype"
					:name="record.name"
					:docstatus="record.docstatus"
					:doc-permissions="workspace.doc_permissions ?? null"
					:disabled="Boolean(acting) || dirty"
					:redirect="presentation !== 'embedded'"
					@deleted="handleDeleted"
				/>
			</div>
			</fieldset>
		</div>
		<DocumentLiveBar v-if="!loading" class="fabric-document-workspace__remote-change" :state="live.state.value" :modified-at="live.remoteModified.value" :dirty="dirty" :reloading="live.reloading.value || acting === 'reload'" @reload="live.refresh()" />
		</div>

		<div v-if="loading" class="fabric-document-workspace__loading" aria-label="Loading document">
			<div class="fabric-document-workspace__loading-rail erp-skeleton-card">
				<div v-for="metric in 4" :key="metric" class="fabric-document-workspace__loading-metric erp-skeleton-field">
					<span class="erp-skeleton erp-skeleton--line" />
					<span class="erp-skeleton erp-skeleton--line" />
				</div>
			</div>
			<div class="fabric-document-workspace__loading-main erp-skeleton-card">
				<span class="erp-skeleton erp-skeleton--title" />
				<div class="fabric-document-workspace__loading-fields">
					<div v-for="field in 6" :key="field" class="erp-skeleton-field">
						<span class="erp-skeleton erp-skeleton--line" />
						<span class="erp-skeleton erp-skeleton--input" />
					</div>
				</div>
				<div class="erp-skeleton-table">
					<div class="erp-skeleton-table__header"><span v-for="column in 4" :key="column" class="erp-skeleton erp-skeleton--line" /></div>
					<div v-for="row in 4" :key="row" class="erp-skeleton-table__row"><span v-for="column in 4" :key="column" class="erp-skeleton erp-skeleton--line" /></div>
				</div>
			</div>
		</div>
		<div v-else class="fabric-document-workspace__content" tabindex="0" role="region" :aria-label="`${title} document content`">
			<div v-if="error && !hasWorkspace" class="fabric-document-workspace__error-recovery">
				<i class="pi pi-cloud-times" aria-hidden="true" />
				<div><strong>{{ title }} could not be loaded</strong><span>{{ error || "Try loading the document again." }}</span></div>
				<Button label="Retry" icon="pi pi-refresh" severity="secondary" outlined :loading="acting === 'reload'" @click="emit('reload')" />
			</div>
			<template v-if="hasWorkspace">
				<div class="fabric-document-workspace__columns" :class="{ 'fabric-document-workspace__columns--without-rail': !showRail }">
					<aside v-if="showRail" class="fabric-document-workspace__rail" aria-label="Document totals and context" :tabindex="compactMobileRail ? 0 : undefined">
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
				<DocumentActivity v-if="showActivity" :doctype="record.doctype || doctype" :name="record.name || ''" :record="record" :initial-page="workspace.activity ?? null" />
			</template>
		</div>

	</section>

	<DocumentErrorDialog
		:message="hasWorkspace && !isStaleDocumentError(error) ? error : ''"
		:title="`${title} could not be completed`"
	/>

	<DocumentConfirmationDialog
		v-model:visible="refreshConfirmVisible"
		title="Discard your changes?"
		message="Refreshing shows the latest saved document and discards your unsaved edits."
		confirm-label="Discard and Refresh"
		cancel-label="Keep Editing"
		confirm-icon="pi pi-refresh"
		severity="warn"
		@confirm="confirmRefresh"
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
import { computed, getCurrentInstance, onBeforeUnmount, onMounted, provide, ref, watch } from "vue"
import { onBeforeRouteLeave } from "vue-router"

import CustomPrintButtons from "../../components/documents/CustomPrintButtons.vue"
import DocumentActivity from "../../components/documents/DocumentActivity.vue"
import DocumentConfirmationDialog from "../../components/documents/DocumentConfirmationDialog.vue"
import DocumentDeleteButton from "../../components/documents/DocumentDeleteButton.vue"
import DocumentPrintButton from "../../components/documents/DocumentPrintButton.vue"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import DocumentLiveBar from "../../components/documents/DocumentLiveBar.vue"
import DocumentSaveState from "../../components/documents/DocumentSaveState.vue"
import DocumentStatusBadge from "../../components/documents/DocumentStatusBadge.vue"
import InlinePageNavigation from "../../components/navigation/InlinePageNavigation.vue"
import { useLiveDocument } from "../../composables/useLiveDocument.js"
import { DOCUMENT_DELETED_KEY, isStaleDocumentError, takeSavedHandoff } from "../../utils/documentLiveState.js"

const props = defineProps({
	doctype: { type: String, required: true },
	title: { type: String, required: true },
	workspace: { type: Object, default: () => ({}) },
	presentation: { type: String, default: "page", validator: (value) => ["page", "embedded"].includes(value) },
	loading: { type: Boolean, default: false },
	error: { type: String, default: "" },
	dirty: { type: Boolean, default: false },
	acting: { type: String, default: "" },
	printLabel: { type: String, default: "Print" },
	showDelete: { type: Boolean, default: true },
	showLifecycleActions: { type: Boolean, default: true },
	compactMobileRail: { type: Boolean, default: false },
	showRail: { type: Boolean, default: true },
	showActivity: { type: Boolean, default: true },
	/** Background reload for live updates (keeps tab, scroll and focus). Without it a remote change only shows the bar. */
	liveReload: { type: Function, default: null },
	showSaveState: { type: Boolean, default: true },
})
const emit = defineEmits(["reload", "action", "close", "deleted", "live-state"])
const instance = getCurrentInstance()
const headingId = computed(() => `${props.doctype.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-workspace-title`)

const discardVisible = ref(false)
let pendingNavigation = null
const record = computed(() => props.workspace.record || {})
const capabilities = computed(() => props.workspace.capabilities || {})
const hasWorkspace = computed(() => Boolean(Object.keys(props.workspace || {}).length))
const canPrint = computed(() => Boolean(record.value.name && (props.workspace.permissions?.can_print === undefined || props.workspace.permissions.can_print)))

const savedAt = ref(props.presentation === "page" ? takeSavedHandoff() : null)
const live = useLiveDocument({
	doctype: () => record.value.doctype || props.doctype,
	name: () => record.value.name || "",
	localModified: () => record.value.modified,
	isDirty: () => props.dirty || !props.liveReload,
	isBusy: () => Boolean(props.acting) || props.loading,
	reload: async (options) => (props.liveReload ? props.liveReload(options) : emit("reload")),
})
const refreshConfirmVisible = ref(false)
/** Toolbar Refresh: the background path when the page has one (after a discard confirm), else the page's own reload. */
function requestRefresh() {
	if (!props.liveReload) return emit("reload")
	if (props.dirty) refreshConfirmVisible.value = true
	else live.refresh({ discard: false })
}
function confirmRefresh() {
	refreshConfirmVisible.value = false
	live.refresh()
}
const isDeleted = computed(() => live.state.value === "deleted")
provide(DOCUMENT_DELETED_KEY, isDeleted)
watch(() => live.state.value, (state) => emit("live-state", state))
watch(() => isStaleDocumentError(props.error), (stale) => { if (stale) live.handleSaveError(props.error) })
watch(() => props.acting, (next, previous) => { if (previous === "save" && !next && !props.error) savedAt.value = Date.now() })
watch(() => record.value.name, (_name, previous) => { if (previous) savedAt.value = null })

function capabilityLabel(name, fallback) { return name === "save" ? fallback : capabilities.value[name]?.label || fallback }
function formatValue(value) {
	if (value === null || value === undefined || value === "") return "—"
	return typeof value === "number" ? value.toLocaleString("en-IN", { maximumFractionDigits: 3 }) : String(value)
}
function handleDeleted() {
	const handled = Boolean(instance.vnode.props?.onDeleted)
	emit("deleted")
	if (props.presentation === "embedded" && !handled) emit("close")
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
.fabric-document-workspace :deep(.document-field-group-grid__card) {
	border: 0;
	border-radius: 0;
	background: transparent;
	box-shadow: none;
}
.fabric-document-workspace {
	display: flex;
	width: 100%;
	min-width: 0;
	min-height: 0;
	overflow: hidden;
	flex-direction: column;
	border-color: var(--erp-border);
	background: var(--erp-surface);
	box-shadow: var(--erp-shadow-card);
}
.fabric-document-workspace--page {
	height: calc(100dvh - var(--erp-shell-header-height) - 44px);
	min-height: min(620px, calc(100dvh - var(--erp-shell-header-height) - 44px));
}
.fabric-document-workspace--embedded { height: min(82dvh, 920px); border: 0; box-shadow: none; }
.fabric-document-workspace--embedded .fabric-document-workspace__header { min-height: 48px; padding-block: 5px; }
.fabric-document-workspace__chrome {
	position: relative;
	z-index: var(--erp-layer-sticky);
	flex: 0 0 auto;
	background: var(--erp-surface);
	box-shadow: none;
}
.fabric-document-workspace__header {
	min-height: 52px;
	padding: 10px var(--erp-space-4);
	margin-bottom: 0;
	border-bottom: 1px solid var(--erp-border);
	background: var(--erp-surface);
}
.fabric-document-workspace__heading { min-width: 0; flex: 1 1 auto; }
.fabric-document-workspace__identity { display: flex; min-width: 0; align-items: center; gap: 12px; }
.fabric-document-workspace__identity > div { display: grid; min-width: 0; gap: 2px; }

.fabric-document-workspace__header-actions, .fabric-document-workspace__domain-actions, .fabric-document-workspace__lifecycle-actions { display: flex; align-items: center; gap: 6px; }
.fabric-document-workspace__header-actions { flex: 0 0 auto; margin-left: auto; }
.fabric-document-workspace__commandbar { display: flex; min-height: 42px; align-items: center; justify-content: space-between; gap: 6px 12px; padding: 4px var(--erp-space-4); border-bottom: 1px solid var(--erp-border); background: var(--erp-surface); flex-wrap: nowrap; }
.fabric-document-workspace__domain-actions, .fabric-document-workspace__lifecycle-actions { min-width: 0; flex-wrap: nowrap; }
.fabric-document-workspace__lifecycle-actions { justify-content: flex-end; margin-left: auto; }
.fabric-document-workspace__remote-change { margin: var(--erp-space-2) var(--erp-space-4); }
.fabric-document-workspace__action-set { display: contents; min-width: 0; margin: 0; padding: 0; border: 0; }
.fabric-document-workspace__loading, .fabric-document-workspace__content {
	min-height: 0;
	flex: 1;
	padding: clamp(10px, 1.2vw, 18px);
	background: var(--erp-surface-soft);
}
.fabric-document-workspace__loading {
	display: grid;
	min-width: 0;
	grid-template-areas: "main rail";
	grid-template-columns: minmax(0, 1fr) minmax(260px, 288px);
	align-content: start;
	align-items: start;
	gap: clamp(12px, 1.3vw, 20px);
	overflow-y: auto;
}
.fabric-document-workspace__loading-rail {
	grid-area: rail;
	gap: 0;
	padding: 0;
}
.fabric-document-workspace__loading-main {
	grid-area: main;
}
.fabric-document-workspace__loading-metric {
	min-height: 70px;
	align-content: center;
	padding: 11px 13px;
	border-bottom: 1px solid var(--erp-border-subtle);
}
.fabric-document-workspace__loading-metric:last-child {
	border-bottom: 0;
}
.fabric-document-workspace__loading-metric > .erp-skeleton:first-child {
	width: 40%;
}
.fabric-document-workspace__loading-metric > .erp-skeleton:last-child {
	width: 60%;
	height: 16px;
}
.fabric-document-workspace__loading-fields {
	display: grid;
	grid-template-columns: repeat(2, minmax(0, 1fr));
	gap: 14px;
}
.fabric-document-workspace__content { display: grid; grid-template-rows: minmax(0, 1fr) auto; overflow: hidden; }
.fabric-document-workspace__error-recovery { display: grid; min-height: 230px; align-content: center; justify-items: center; gap: 9px; padding: var(--erp-space-5); color: var(--erp-text-muted); text-align: center; border: 1px dashed var(--erp-border-strong); border-radius: var(--erp-panel-radius); background: var(--erp-surface); }
.fabric-document-workspace__error-recovery > i {
	color: var(--erp-danger);
	font-size: var(--erp-font-size-title);
}
.fabric-document-workspace__error-recovery > div { display: grid; gap: 4px; }
.fabric-document-workspace__error-recovery strong { color: var(--erp-text); }
.fabric-document-workspace__error-recovery span { font-size: var(--erp-font-size-caption); }
.fabric-document-workspace__columns { display: grid; min-height: 0; grid-template-areas: "main rail"; grid-template-columns: minmax(0, 1fr) minmax(260px, 288px); align-items: stretch; gap: clamp(12px, 1.3vw, 20px); }
.fabric-document-workspace__main, .fabric-document-workspace__fields, .fabric-document-workspace__matrix, .fabric-document-workspace__secondary-fields, .fabric-document-workspace__after-matrix, .fabric-document-workspace__rail, .fabric-document-workspace__panel { display: grid; min-width: 0; gap: var(--erp-space-3); }
.fabric-document-workspace__main { min-height: 0; grid-area: main; align-content: start; overflow-y: auto; overscroll-behavior: contain; scrollbar-gutter: stable; }
.fabric-document-workspace__rail {
	grid-area: rail;
	min-height: 0;
	height: 100%;
	align-content: start;
	gap: 0;
	overflow: hidden;
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-panel-radius);
	background: var(--erp-surface);
}
.fabric-document-workspace__metric {
	display: grid;
	min-width: 0;
	min-height: 70px;
	align-content: center;
	gap: 4px;
	padding: 11px 13px;
	border-bottom: 1px solid var(--erp-border-subtle);
	background: var(--erp-surface);
}
.fabric-document-workspace__metric span {
	min-width: 0;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	font-weight: 700;
	letter-spacing: .07em;
	text-transform: uppercase;
	overflow-wrap: anywhere;
}
.fabric-document-workspace__metric strong {
	min-width: 0;
	color: var(--erp-text);
	font-size: var(--erp-font-size-section);
	font-weight: 700;
	letter-spacing: -.01em;
	font-variant-numeric: tabular-nums;
	overflow-wrap: anywhere;
}
.fabric-document-workspace__panel { margin-top: var(--erp-space-3); }
.fabric-document-workspace__discard-copy { margin: 0; color: var(--erp-text-muted); line-height: 1.55; }
@media (min-width: 621px) { .fabric-document-workspace__content { --erp-control-height: 36px; } }
@media (max-width: 900px) {
	.fabric-document-workspace__loading {
		grid-template-areas: "main" "rail";
		grid-template-columns: minmax(0, 1fr);
	}
	.fabric-document-workspace--page {
		height: auto;
		min-height: 0;
		overflow: visible;
	}
	.fabric-document-workspace__content {
		display: block;
		overflow: visible;
	}
	.fabric-document-workspace--embedded .fabric-document-workspace__content {
		overflow-y: auto;
		scrollbar-gutter: stable;
	}
	.fabric-document-workspace__columns {
		min-height: auto;
		grid-template-areas: "main" "rail";
		grid-template-columns: 1fr;
		align-items: start;
	}
	.fabric-document-workspace__main {
		min-height: auto;
		overflow: visible;
		scrollbar-gutter: auto;
	}
	.fabric-document-workspace__rail {
		height: auto;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 1px;
		background: var(--erp-border);
	}
	.fabric-document-workspace__rail > :deep(*) {
		min-width: 0;
		border-bottom: 0;
		background: var(--erp-surface);
	}
	.fabric-document-workspace__rail :deep(.fabric-document-workspace__metric-group),
	.fabric-document-workspace__rail > :deep(:nth-child(odd):last-child) {
		grid-column: 1 / -1;
	}
	.fabric-document-workspace--compact-mobile-rail .fabric-document-workspace__columns {
		grid-template-areas: "rail" "main";
	}
}
@media (max-width: 620px) {
	.fabric-document-workspace--page {
		border-right: 0;
		border-left: 0;
		border-radius: 0;
	} .fabric-document-workspace--embedded { height: 100%; min-height: 0; } .fabric-document-workspace__header { min-height: 52px; padding: 7px var(--erp-space-3); } .fabric-document-workspace__commandbar { align-items: center; gap: 4px; padding: 4px var(--erp-space-3); flex-wrap: nowrap; overflow-x: auto; overflow-y: hidden; scrollbar-width: thin; } .fabric-document-workspace__domain-actions, .fabric-document-workspace__lifecycle-actions { width: auto; min-width: max-content; justify-content: flex-start; margin-left: 0; } .fabric-document-workspace__domain-actions { flex: 1 0 auto; } .fabric-document-workspace__lifecycle-actions { gap: 2px; flex: 0 0 auto; } .fabric-document-workspace__lifecycle-actions :deep(.document-print-button) { width: var(--erp-control-height); padding-inline: 0; } .fabric-document-workspace__lifecycle-actions :deep(.document-print-button .p-button-label) { display: none; } .fabric-document-workspace__content { padding: var(--erp-space-2); }
}
.fabric-document-workspace__metric:last-child {
	border-bottom: 0;
}
.fabric-document-workspace__columns.fabric-document-workspace__columns--without-rail { grid-template-areas: "main"; grid-template-columns: minmax(0, 1fr); }
</style>
