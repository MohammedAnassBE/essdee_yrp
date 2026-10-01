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
		<div class="cutting-plan-layout erp-workspace" :class="{ 'cutting-plan-layout--without-sidebar': !showSidebar }">
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
					<Tag
						v-if="doc.cp_status"
						class="cutting-plan-status"
						:value="doc.cp_status"
						:severity="statusSeverity(doc.cp_status)"
						rounded
					/>
				</template>
				<template #header-actions="{ doc }">
					<DocumentPrintButton
						v-if="workspaceData.permissions?.can_print"
						doctype="SD YRP Cutting Plan"
						:name="doc.name"
						:formats="workspaceData.print_formats || []"
						:disabled="workspaceLoading"
					/>
				</template>
				<template #view="{ doc, meta }">
					<div class="cutting-plan-main">
						<CuttingPlanActions
							:doc="doc"
							:data="workspaceData"
							@refresh="refreshPage"
							@show-summary="showSummary"
						/>
						<CuttingPlanTabs
							ref="cuttingTabs"
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
import Tag from "primevue/tag"
import { computed, ref } from "vue"
import { useRoute } from "vue-router"

import { callMethod } from "../api/frappe.js"
import DepartmentPage from "../components/DepartmentPage.vue"
import FormView from "../components/common/FormView.vue"
import CuttingPlanActions from "./cutting/CuttingPlanActions.vue"
import DocumentPrintButton from "./cutting/DocumentPrintButton.vue"
import CuttingPlanSidebar from "./cutting/CuttingPlanSidebar.vue"
import CuttingPlanTabs from "./cutting/CuttingPlanTabs.vue"

const route = useRoute()
const cuttingPlanId = computed(() => String(route.params.cuttingPlanId || ""))
const workspaceData = ref({})
const workspaceLoading = ref(true)
const workspaceError = ref("")
const formView = ref(null)
const cuttingTabs = ref(null)
let loadSequence = 0
const showSidebar = computed(() => Boolean(
	workspaceLoading.value
	|| workspaceData.value.permissions?.can_read_marker
	|| workspaceData.value.permissions?.can_read_laysheet
))

const detailFields = [
	"is_manual_entry",
	"lot",
	"maximum_no_of_plys",
	"lay_no",
	"cutting_start_date",
	"cp_status",
	"no_of_colours",
	"item",
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

function showSummary() {
	cuttingTabs.value?.activate("summary")
}

function statusSeverity(status) {
	if (status === "Completed") return "success"
	if (["Fabric Partially Received", "Partially Completed"].includes(status)) return "warn"
	if (status === "Cut Panel Dispatch Pending") return "danger"
	if (["Ready to Cut", "Cutting In Progress"].includes(status)) return "info"
	return "secondary"
}
</script>

<style scoped>
.cutting-plan-layout {
	display: grid;
	grid-template-columns: minmax(0, 4fr) minmax(286px, 1fr);
	align-items: stretch;
	gap: 12px;
	height: calc(100dvh - 97px);
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
	padding: 14px 14px 12px;
	background: rgb(255 255 255 / 96%);
	border: 1px solid #dfe9e4;
	border-radius: 14px;
	box-shadow: 0 10px 32px rgb(30 74 51 / 7%);
	flex-direction: column;
}

.cutting-plan-layout :deep(.form-toolbar) {
	min-height: 54px;
	padding: 0 0 10px;
}

.cutting-plan-layout :deep(.form-toolbar__identity) {
	gap: 4px;
}

.cutting-plan-layout :deep(.form-toolbar h2) {
	color: #172b3f;
	font-size: 1.48rem;
	font-weight: 780;
	letter-spacing: -0.025em;
	line-height: 1.05;
}

.cutting-plan-layout :deep(.form-toolbar__meta) {
	gap: 9px;
}

.cutting-plan-layout :deep(.form-toolbar small) {
	color: #6f8078;
	font-size: 0.78rem;
	font-weight: 550;
}

.cutting-plan-layout :deep(.form-toolbar__actions .p-button) {
	min-height: 36px;
	padding: 0.52rem 0.86rem;
	color: #35506a;
	background: #fff;
	border-color: #d7e2e9;
	border-radius: 9px;
	box-shadow: 0 1px 2px rgb(27 55 43 / 3%);
	font-weight: 650;
}

.cutting-plan-layout :deep(.form-toolbar__actions .p-button:hover) {
	color: #136c4a;
	background: #f7fbf9;
	border-color: #b8d3c5;
}

.cutting-plan-main {
	display: grid;
	grid-template-rows: auto minmax(0, 1fr);
	flex: 1;
	gap: 8px;
	min-width: 0;
	min-height: 0;
	overflow: hidden;
}

:deep(.cutting-plan-status.p-tag) {
	padding: 0.22rem 0.58rem;
	border: 1px solid rgb(31 126 83 / 9%);
	font-size: 0.68rem;
	font-weight: 750;
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
</style>
