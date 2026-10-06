<template>
	<DepartmentPage
		title="Cutting Plan"
		accent="#079669"
		back-to="/cutting/plans"
		back-label="Cutting Plans"
		:show-title="false"
		flat
		full-width
	>
		<div v-if="checkingEditor" class="cutting-plan-probe erp-workspace" aria-label="Loading Cutting Plan">
			<Skeleton height="76px" />
			<Skeleton height="420px" />
		</div>
		<div v-else-if="showDraftEditor" class="cutting-plan-editor-route erp-workspace">
			<CuttingPlanEditor
				:name="cuttingPlanId"
				:initial-payload="editorProbe"
				@saved="editorSaved"
				@cancel="router.push('/cutting/plans')"
			/>
		</div>
		<div v-else class="cutting-plan-layout cutting-plan-frame erp-workspace" :class="{ 'cutting-plan-layout--without-sidebar': !showSidebar }">
			<FormView
				ref="formView"
				doctype="SD YRP Cutting Plan"
				:name="cuttingPlanId"
				title="Cutting Plan"
				initial-mode="view"
				:readonly="!workspaceData.permissions?.can_write"
				:include-fields="detailFields"
				compact
				@loaded="documentLoaded"
				@saved="documentLoaded"
			>
				<template #header-meta="{ doc }">
					<div class="cutting-plan-header-meta">
						<Tag
							v-if="doc.cp_status"
							class="cutting-plan-status"
							:value="doc.cp_status"
							:severity="statusSeverity(doc.cp_status)"
							rounded
						/>
						<span class="cutting-plan-header-fact cutting-plan-header-fact--lot" :title="doc.lot || 'No Lot'">
							<small>Lot</small>
							<strong>{{ doc.lot || "—" }}</strong>
						</span>
						<span class="cutting-plan-header-fact cutting-plan-header-fact--item" :title="doc.item || 'No Item'">
							<small>Item</small>
							<strong>{{ doc.item || "—" }}</strong>
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
					<CuttingPlanActions
						:doc="doc"
						:data="workspaceData"
						@refresh="refreshPage"
					/>
				</template>
				<template #view="{ doc, meta }">
					<div class="cutting-plan-main">
						<CuttingPlanTabs
							:doc="doc"
							:meta="meta"
							:data="workspaceData"
							:loading="workspaceLoading"
							:error="workspaceError"
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
				:error="workspaceError"
				@refresh="refreshPage"
			/>
		</div>
	</DepartmentPage>
</template>

<script setup>
import Skeleton from "primevue/skeleton"
import Tag from "primevue/tag"
import { computed, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"

import { getCuttingPlanEditor } from "../api/cuttingPlanEditor.js"
import { callMethod } from "../api/frappe.js"
import DepartmentPage from "../components/DepartmentPage.vue"
import FormView from "../components/common/FormView.vue"
import CuttingPlanActions from "./cutting/CuttingPlanActions.vue"
import DocumentPrintButton from "./cutting/DocumentPrintButton.vue"
import CuttingPlanSidebar from "./cutting/CuttingPlanSidebar.vue"
import CuttingPlanTabs from "./cutting/CuttingPlanTabs.vue"
import CuttingPlanEditor from "./cutting/plan/CuttingPlanEditor.vue"

const route = useRoute()
const router = useRouter()
const cuttingPlanId = computed(() => String(route.params.cuttingPlanId || ""))
const checkingEditor = ref(true)
const editorProbe = ref(null)
const showDraftEditor = computed(() => Boolean(
	editorProbe.value?.record?.docstatus === 0
	&& editorProbe.value?.permissions?.can_write,
))
const workspaceData = ref({})
const workspaceLoading = ref(true)
const workspaceError = ref("")
const formView = ref(null)
let loadSequence = 0
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

async function documentLoaded(payload) {
	const document = payload?.doc || payload
	if (!document?.name) return
	const sequence = ++loadSequence
	workspaceLoading.value = true
	workspaceError.value = ""
	try {
		const data = await callMethod(
			"essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan.sd_yrp_cutting_plan.get_web_view_data",
			{ cutting_plan: document.name },
		)
		if (sequence === loadSequence) workspaceData.value = data || {}
	} catch (reason) {
		if (sequence === loadSequence) workspaceError.value = reason.message || "Unable to load Cutting Plan details."
	} finally {
		if (sequence === loadSequence) workspaceLoading.value = false
	}
}

function refreshPage() {
	formView.value?.reload()
}

async function probeEditor() {
	checkingEditor.value = true
	editorProbe.value = null
	try {
		editorProbe.value = await getCuttingPlanEditor(cuttingPlanId.value)
	} catch {
		// FormView remains the read-only fallback and will expose its own load error.
	} finally {
		checkingEditor.value = false
	}
}

function editorSaved(record) {
	editorProbe.value = {
		...editorProbe.value,
		record: { ...(editorProbe.value?.record || {}), ...record },
	}
}

watch(cuttingPlanId, probeEditor, { immediate: true })

function statusSeverity(status) {
	if (status === "Completed") return "success"
	if (["Fabric Partially Received", "Partially Completed"].includes(status)) return "warn"
	if (status === "Cut Panel Dispatch Pending") return "danger"
	if (["Ready to Cut", "Cutting In Progress"].includes(status)) return "info"
	return "secondary"
}
</script>

<style scoped>
.cutting-plan-probe {
	display: grid;
	gap: var(--erp-space-3);
}

.cutting-plan-editor-route {
	width: 100%;
	max-width: 1800px;
	min-width: 0;
	margin: 0 auto;
}

.cutting-plan-layout {
	display: grid;
	grid-template-columns: minmax(0, 4fr) minmax(286px, 1fr);
	align-items: stretch;
	gap: var(--erp-space-3);
	height: calc(100dvh - var(--erp-shell-header-height) - 97px);
	min-height: 0;
	overflow: hidden;
}

.cutting-plan-layout--without-sidebar {
	grid-template-columns: minmax(0, 1fr);
}

.cutting-plan-layout > :first-child {
	height: 100%;
	min-width: 0;
	min-height: 0;
}

.cutting-plan-layout :deep(.common-form-view) {
	display: flex;
	height: 100%;
	min-height: 0;
	padding: 14px;
	background: var(--erp-surface);
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-panel-radius);
	box-shadow: var(--erp-shadow-card);
	flex-direction: column;
}

.cutting-plan-layout :deep(.form-toolbar) {
	min-height: 52px;
	padding: 0 0 12px;
	border-bottom: 1px solid var(--erp-border);
}

.cutting-plan-layout :deep(.form-toolbar__identity) {
	gap: 4px;
	min-width: 0;
}

.cutting-plan-layout :deep(.form-toolbar h2) {
	color: var(--erp-text);
	font-size: var(--erp-font-size-title);
	font-weight: 760;
	letter-spacing: -0.025em;
	line-height: 1.05;
}

.cutting-plan-layout :deep(.form-toolbar__meta) {
	gap: 9px;
	min-width: 0;
}

.cutting-plan-layout :deep(.form-toolbar small) {
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-caption);
	font-weight: 600;
	font-variant-numeric: tabular-nums;
}

.cutting-plan-layout :deep(.form-toolbar__actions .p-button) {
	min-height: var(--erp-control-height);
	padding: 0.52rem 0.86rem;
	color: var(--erp-text);
	background: var(--erp-surface);
	border-color: var(--erp-border-strong);
	border-radius: var(--erp-control-radius);
	box-shadow: none;
	font-weight: 650;
}

.cutting-plan-layout :deep(.form-toolbar__actions .p-button:hover) {
	color: var(--erp-accent-hover);
	background: var(--erp-accent-soft);
	border-color: color-mix(in srgb, var(--erp-accent) 35%, white);
}

.cutting-plan-main {
	display: grid;
	grid-template-rows: minmax(0, 1fr);
	flex: 1;
	min-width: 0;
	min-height: 0;
	overflow: hidden;
}

:deep(.cutting-plan-status.p-tag) {
	flex: 0 0 auto;
	padding: 0.22rem 0.58rem;
	border: 1px solid color-mix(in srgb, var(--erp-accent) 14%, transparent);
	font-size: var(--erp-font-size-min);
	font-weight: 750;
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
	font-size: 11.5px;
	font-weight: 650;
	letter-spacing: 0.04em;
	text-transform: uppercase;
}

.cutting-plan-header-fact strong {
	min-width: 0;
	overflow: hidden;
	color: var(--erp-text);
	font-size: 13.5px;
	font-weight: 720;
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
		padding: 12px;
	}

	.cutting-plan-main {
		display: grid;
		overflow: visible;
	}
}

@media (max-width: 720px) {
	.cutting-plan-layout :deep(.form-toolbar) {
		align-items: flex-start;
		flex-wrap: wrap;
	}

	.cutting-plan-header-meta {
		flex-wrap: wrap;
	}

	.cutting-plan-header-fact--item {
		max-width: calc(100vw - 110px);
	}
}
</style>
