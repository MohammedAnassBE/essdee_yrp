<template>
	<DepartmentPage
		title="Cutting Plan"
		:back-to="backTo"
		:back-label="backLabel"
		:show-title="false"
		flat
		full-width
		:inline-navigation="!checkingEditor && !showEditor"
	>
		<div v-if="checkingEditor" class="cutting-plan-probe erp-workspace" aria-label="Loading Cutting Plan">
			<Skeleton height="76px" />
			<Skeleton height="420px" />
		</div>
		<div v-else-if="showEditor" class="cutting-plan-editor-route erp-workspace">
			<CuttingPlanEditor
				:name="cuttingPlanId"
				:initial-payload="editorProbe"
				@saved="editorSaved"
				@cancel="cancelEditor"
			>
				<template #document-actions="{ busy, dirty }">
					<DocumentPrintButton doctype="SD YRP Cutting Plan" :name="cuttingPlanId" :docstatus="editorProbe?.record?.docstatus" :disabled="busy" />
					<DocumentDeleteButton doctype="SD YRP Cutting Plan" :name="cuttingPlanId" :docstatus="editorProbe?.record?.docstatus" :disabled="busy || dirty" :redirect-to="backTo" />
				</template>
			</CuttingPlanEditor>
		</div>
		<div v-else-if="workspaceError && !workspaceReady" class="cutting-plan-probe erp-workspace">
			<WorkspaceLoadError title="Cutting Plan unavailable" :message="workspaceError" :loading="workspaceLoading" @retry="retryWorkspace" />
		</div>
		<div v-else class="cutting-plan-layout cutting-plan-frame erp-workspace" :class="{ 'cutting-plan-layout--without-sidebar': !showSidebar }">
			<FormView
				ref="formView"
				doctype="SD YRP Cutting Plan"
				:name="cuttingPlanId"
				title="Cutting Plan"
				initial-mode="view"
				readonly
				:include-fields="detailFields"
				compact
				@loaded="documentLoaded"
				@saved="documentSaved"
			>
				<template #header-meta="{ doc }">
					<div class="cutting-plan-header-meta">
						<DocumentStatusBadge
							v-if="doc.cp_status"
							class="cutting-plan-status"
							:docstatus="doc.docstatus"
							:label="doc.cp_status"
						/>
						<span class="cutting-plan-header-fact cutting-plan-header-fact--lot" :title="doc.lot || 'No Lot'">
							<small>Lot</small>
							<strong><DocumentLink doctype="SD YRP Lot" :name="doc.lot" :label="doc.lot || '—'" /></strong>
						</span>
						<span class="cutting-plan-header-fact cutting-plan-header-fact--item" :title="doc.item || 'No Item'">
							<small>Item</small>
							<strong><DocumentLink doctype="Item" :name="doc.item" :label="doc.item || '—'" /></strong>
						</span>
					</div>
				</template>
				<template #header-actions="{ doc }">
					<DocumentPrintButton
						v-if="workspaceData.permissions?.can_print"
						doctype="SD YRP Cutting Plan"
						:name="doc.name"
						:formats="workspaceData.print_formats || []"
						:disabled="workspaceLoading"
					/>
					<DocumentDeleteButton doctype="SD YRP Cutting Plan" :name="doc.name" :docstatus="doc.docstatus" :disabled="workspaceLoading" :redirect-to="backTo" />
					<CuttingPlanActions
						:doc="doc"
						:data="workspaceData"
						@refresh="refreshPage"
					/>
					<Button
						v-if="canEditSubmitted"
						label="Edit"
						icon="pi pi-pencil"
						severity="secondary"
						outlined
						@click="editingSubmitted = true"
					/>
				</template>
				<template #view="{ doc, meta }">
					<div class="cutting-plan-main">
						<Message v-if="workspaceError" severity="error" :closable="false">
							<div class="cutting-plan-workspace-error"><span>{{ workspaceError }}</span><Button label="Retry" icon="pi pi-refresh" severity="danger" outlined size="small" :loading="workspaceLoading" @click="retryWorkspace" /></div>
						</Message>
						<CuttingPlanTabs
							:doc="doc"
							:meta="meta"
							:data="workspaceData"
							:loading="workspaceLoading"
							:error="''"
							@refresh="refreshPage"
						/>
					</div>
				</template>
			</FormView>

			<CuttingPlanSidebar
				v-if="showSidebar"
				:cutting-plan="cuttingPlanId"
				:data="workspaceData"
				:loading="workspaceLoading"
				:error="''"
				@refresh="refreshPage"
			/>
		</div>
	</DepartmentPage>
</template>

<script setup>
import DocumentLink from "../components/common/DocumentLink.vue"
import DocumentDeleteButton from "../components/documents/DocumentDeleteButton.vue"
import Skeleton from "primevue/skeleton"
import Message from "primevue/message"
import Button from "primevue/button"
import { computed, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"

import { getCuttingPlanEditor } from "../api/cuttingPlanEditor.js"
import { callMethod } from "../api/frappe.js"
import DepartmentPage from "../components/DepartmentPage.vue"
import FormView from "../components/common/FormView.vue"
import WorkspaceLoadError from "../components/common/WorkspaceLoadError.vue"
import DocumentStatusBadge from "../components/documents/DocumentStatusBadge.vue"
import CuttingPlanActions from "./cutting/CuttingPlanActions.vue"
import DocumentPrintButton from "./cutting/DocumentPrintButton.vue"
import CuttingPlanSidebar from "./cutting/CuttingPlanSidebar.vue"
import CuttingPlanTabs from "./cutting/CuttingPlanTabs.vue"
import CuttingPlanEditor from "./cutting/plan/CuttingPlanEditor.vue"

const props = defineProps({
	backTo: { type: String, default: "/cutting/plans" },
	backLabel: { type: String, default: "Cutting Plans" },
})

const route = useRoute()
const router = useRouter()
const cuttingPlanId = computed(() => String(route.params.cuttingPlanId || ""))
const checkingEditor = ref(true)
const editorProbe = ref(null)
const editingSubmitted = ref(false)
const showDraftEditor = computed(() => Boolean(
	editorProbe.value?.record?.docstatus === 0
	&& editorProbe.value?.permissions?.can_write,
))
const canEditSubmitted = computed(() => Boolean(
	editorProbe.value?.record?.docstatus === 1
	&& editorProbe.value?.permissions?.can_update_after_submit,
))
const showSubmittedEditor = computed(() => canEditSubmitted.value && editingSubmitted.value)
const showEditor = computed(() => showDraftEditor.value || showSubmittedEditor.value)
const workspaceData = ref({})
const workspaceLoading = ref(true)
const workspaceError = ref("")
const workspaceReady = ref(false)
const currentDocument = ref(null)
const formView = ref(null)
let loadSequence = 0
let probeSequence = 0
let suppressNextLoaded = false
let pendingView = null
const showSidebar = computed(() => Boolean(
	workspaceLoading.value
	|| workspaceData.value.permissions?.can_read_marker
	|| workspaceData.value.permissions?.can_read_laysheet
))

const detailFields = [
	"is_manual_entry",
	"maximum_no_of_plys",
	"cutting_start_date",
	"no_of_colours",
	"maximum_allow_percent",
	"piece_weight_tolerance",
	"cutting_location",
	"cutting_end_date",
	"work_order",
	"open_status",
	"no_of_colours_completed",
]

function loadView(name) {
	return callMethod(
		"essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan.sd_yrp_cutting_plan.get_web_view_data",
		{ cutting_plan: name },
	)
}

async function documentLoaded(payload, force = false) {
	const document = payload?.doc || payload
	if (!document?.name) return
	if (!force && suppressNextLoaded && currentDocument.value?.name === document.name) {
		suppressNextLoaded = false
		currentDocument.value = document
		return
	}
	const remountsFormAfterSuccess = force && !workspaceReady.value && Boolean(workspaceError.value)
	currentDocument.value = document
	const sequence = ++loadSequence
	workspaceLoading.value = true
	if (workspaceReady.value) workspaceError.value = ""
	try {
		const pending = !force && pendingView?.name === document.name ? pendingView.promise : null
		pendingView = null
		const data = await (pending || loadView(document.name))
		if (sequence === loadSequence) {
			workspaceData.value = data || {}
			workspaceReady.value = true
			if (remountsFormAfterSuccess) suppressNextLoaded = true
			workspaceError.value = ""
		}
	} catch (reason) {
		if (sequence === loadSequence) workspaceError.value = reason.message || "Unable to load Cutting Plan details."
	} finally {
		if (sequence === loadSequence) workspaceLoading.value = false
	}
}

function documentSaved(payload) { return documentLoaded(payload, true) }

function retryWorkspace() {
	if (currentDocument.value?.name) return documentLoaded(currentDocument.value, true)
	formView.value?.reload()
}

function refreshPage() {
	formView.value?.reload()
}

async function probeEditor() {
	const sequence = ++probeSequence
	const requestedId = cuttingPlanId.value
	loadSequence += 1
	checkingEditor.value = true
	editingSubmitted.value = false
	editorProbe.value = null
	workspaceData.value = {}
	workspaceError.value = ""
	workspaceReady.value = false
	currentDocument.value = null
	suppressNextLoaded = false
	pendingView = null
	try {
		const data = await getCuttingPlanEditor(requestedId)
		if (sequence !== probeSequence || requestedId !== cuttingPlanId.value) return
		editorProbe.value = data
		if (data?.record?.docstatus === 1) {
			const promise = loadView(requestedId)
			promise.catch(() => {}) // The form load consumes and displays this error.
			pendingView = { name: requestedId, promise }
		}
	} catch {
		// FormView remains the read-only fallback and will expose its own load error.
	} finally {
		if (sequence === probeSequence && requestedId === cuttingPlanId.value) checkingEditor.value = false
	}
}

function editorSaved(record) {
	pendingView = null
	loadSequence += 1
	suppressNextLoaded = false
	editorProbe.value = {
		...editorProbe.value,
		record: { ...(editorProbe.value?.record || {}), ...record },
	}
	if (Number(record?.docstatus) === 1) editingSubmitted.value = false
}

function cancelEditor() {
	if (showSubmittedEditor.value) {
		editingSubmitted.value = false
		return
	}
	router.push(props.backTo)
}

watch(cuttingPlanId, probeEditor, { immediate: true })

</script>

<style scoped>
.cutting-plan-probe {
	display: grid;
	gap: var(--erp-space-3);
}

.cutting-plan-workspace-error {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: var(--erp-space-3);
}

@media (max-width: 620px) {
	.cutting-plan-workspace-error { align-items: stretch; flex-direction: column; }
}

.cutting-plan-editor-route {
	width: 100%;
	min-width: 0;
}
.cutting-plan-layout {
	display: grid;
	grid-template-columns: minmax(0, 4fr) minmax(300px, 1fr);
	align-items: stretch;
	gap: var(--erp-space-3);
	height: calc(100dvh - var(--erp-shell-header-height) - 44px);
	min-height: 0;
	overflow: hidden;
}

.cutting-plan-layout--without-sidebar {
	grid-template-columns: minmax(0, 1fr);
}
.cutting-plan-layout > * {
	height: 100%;
	min-width: 0;
	min-height: 0;
}
.cutting-plan-layout :deep(.common-form-view) {
	display: flex;
	height: 100%;
	min-height: 0;
	overflow: hidden;
	padding: 0;
	background: var(--erp-surface);
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-panel-radius);
	box-shadow: var(--erp-shadow-card);
	flex-direction: column;
}
.cutting-plan-layout :deep(.form-toolbar) {
	min-height: 64px;
	padding: 10px 14px;
	background: var(--erp-surface);
	border: 0;
	border-bottom: 1px solid var(--erp-border);
	border-radius: 0;
	box-shadow: none;
}

.cutting-plan-layout :deep(.form-toolbar__identity) {
	gap: 4px;
	min-width: 0;
}
.cutting-plan-layout :deep(.form-toolbar h2) {
	color: var(--erp-text);
	font-size: var(--erp-font-size-title);
	font-weight: 700;
	letter-spacing: -0.025em;
	line-height: 1.05;
}

.cutting-plan-layout :deep(.form-toolbar__meta) {
	gap: 9px;
	min-width: 0;
}

.cutting-plan-layout :deep(.form-toolbar__meta > small) {
	flex: 0 0 auto;
	white-space: nowrap;
}

.cutting-plan-layout :deep(.form-toolbar small) {
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-caption);
	font-weight: 600;
	font-variant-numeric: tabular-nums;
}
.cutting-plan-layout :deep(.form-toolbar__actions .p-button) {
	min-height: var(--erp-control-height);
	white-space: nowrap;
}

.cutting-plan-main {
	display: grid;
	grid-template-rows: minmax(0, 1fr);
	flex: 1;
	min-width: 0;
	min-height: 0;
	overflow: hidden;
	padding: 14px;
}
:deep(.cutting-plan-status.p-tag) {
	flex: 0 0 auto;
	padding: 0.22rem 0.58rem;
	border: 0;
	font-size: var(--erp-font-size-min);
	font-weight: 600;
}

.cutting-plan-header-meta {
	display: flex;
	align-items: center;
	gap: 10px;
	min-width: 0;
}

.cutting-plan-header-fact {
	display: flex;
	align-items: baseline;
	gap: 5px;
	min-width: 0;
	padding-left: 10px;
	border-left: 1px solid var(--erp-border);
	white-space: nowrap;
}
.cutting-plan-header-fact small {
	flex: 0 0 auto;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	font-weight: 600;
	letter-spacing: 0.04em;
	text-transform: uppercase;
}
.cutting-plan-header-fact strong {
	min-width: 0;
	overflow: hidden;
	color: var(--erp-text);
	font-size: var(--erp-font-size-table);
	font-weight: 700;
	text-overflow: ellipsis;
}

.cutting-plan-header-fact--lot {
	max-width: 210px;
}

.cutting-plan-header-fact--item {
	max-width: min(32vw, 410px);
}

@media (max-width: 1050px) {
	.cutting-plan-layout {
		grid-template-columns: minmax(0, 1fr);
		height: auto;
		overflow: visible;
	}

	.cutting-plan-layout > :first-child,
	.cutting-plan-layout :deep(.common-form-view) {
		height: auto;
		padding: 0;
	}

	.cutting-plan-main {
		display: grid;
		overflow: visible;
		padding: 12px;
	}
}

@media (max-width: 700px) {
	.cutting-plan-layout :deep(.form-toolbar) {
		display: grid;
		grid-template-columns: auto minmax(0, 1fr);
		align-items: start;
		gap: 8px 10px;
	}
	.cutting-plan-header-fact--item {
		max-width: calc(100vw - 110px);
	}
	.cutting-plan-layout :deep(.form-toolbar > :first-child) {
		grid-column: 1;
		grid-row: 1;
	}
	.cutting-plan-layout :deep(.form-toolbar__identity) {
		display: contents;
	}
	.cutting-plan-layout :deep(.form-toolbar h2) {
		grid-column: 2;
		grid-row: 1;
	}
	.cutting-plan-layout :deep(.form-toolbar__meta) {
		grid-column: 1 / -1;
		justify-content: flex-start;
		flex-wrap: wrap;
		gap: 6px;
	}
	.cutting-plan-layout :deep(.form-toolbar__actions) {
		grid-column: 1 / -1;
		width: 100%;
		margin-left: 0;
	}
	.cutting-plan-header-meta {
		display: contents;
	}
	.cutting-plan-header-fact {
		flex-basis: 100%;
		padding-left: 0;
		border-left: 0;
	}
}
</style>
