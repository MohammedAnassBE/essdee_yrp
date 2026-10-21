<template>
	<DepartmentPage title="Quality Inspection" back-to="/quality/inspections" back-label="Inspections" :show-title="false" flat full-width inline-navigation>
		<section class="purchase-lot-frame merch-lot-frame quality-inspection-frame" :aria-busy="Boolean(acting)">
			<FabricDocumentWorkspace :doctype="INSPECTION_DOCTYPE" title="Quality Inspection" :workspace="workspace" :loading="loading" :error="loadError"
				:acting="acting" :show-lifecycle-actions="false" :show-delete="false" @reload="load">
				<template #header="{ record, headingId }">
					<div class="quality-inspection-header">
						<div class="quality-inspection-header__title">
							<h1 class="erp-doc-title" :id="headingId">{{ record.name }}</h1>
							<DocumentStatusBadge :docstatus="record.docstatus" />
							<InspectionResultBadge :result="record.result" />
							<span v-if="resultSummary.isManual" class="quality-manual-override" :title="resultSummary.note">Manual override</span>
							<small v-if="resultSummary.isManual || resultSummary.calculated !== resultSummary.result" class="quality-calculated-result">Calculated: {{ resultSummary.calculated || '—' }}</small>
						</div>
						<InspectionSummary :record="record" header />
					</div>
				</template>
				<template #header-actions>
					<DocumentActionStrip :actions="actions">
						<template v-if="workspace.actions?.submit?.allowed" #primary>
							<DocumentSaveButton class="document-action-strip__primary" saved :dirty="false" :show-save="false" show-submit
								:docstatus="Number(record.docstatus)" :document-label="`Quality Inspection ${record.name}`" :disabled="Boolean(acting)" :loading="acting === 'submit'" @submit="submit" />
						</template>
					</DocumentActionStrip>
				</template>
				<template #matrix>
					<Tabs v-model:value="activeTab" scrollable class="lot-tabs erp-tabs">
						<TabList class="lot-tablist">
							<Tab v-for="tab in INSPECTION_TABS" :key="tab.key" :value="tab.key">{{ tab.label }}<span v-if="tab.key === 'debits'">{{ workspace.debit_details?.length || 0 }}</span></Tab>
						</TabList>
						<TabPanels class="lot-panels">
							<TabPanel v-if="activeTab === 'inspection'" value="inspection"><InspectionSummary :record="record" :selection="workspace.colour_size_data || {}" /></TabPanel>
							<TabPanel v-if="activeTab === 'details'" value="details"><DocumentOverview :fields="detailFields" :definitions="INSPECTION_DETAIL_SECTIONS" id-prefix="quality-inspection" aria-label="Inspection details" /></TabPanel>
							<TabPanel v-if="activeTab === 'debits'" value="debits">
								<InspectionDebitDetails v-if="workspace.debit_details?.length" :debits="workspace.debit_details" />
								<p v-else class="quality-empty-state">No debits raised for this inspection.</p>
							</TabPanel>
						</TabPanels>
					</Tabs>
				</template>
				<template #rail>
					<div class="quality-rail-metric quality-result-metric">
						<span>Result</span><InspectionResultBadge :result="record.result" />
						<div class="quality-result-details">
							<span v-if="resultSummary.isManual" class="quality-manual-override" :title="resultSummary.note">Manual override</span>
							<small class="quality-calculated-result">Calculated: {{ resultSummary.calculated || '—' }}</small>
						</div>
					</div>
					<div v-if="record.inspector_name || record.inspector" class="quality-rail-metric"><span>Inspector</span><strong>{{ record.inspector_name || record.inspector }}</strong></div>
					<InspectionApprovalSheet :key="currentName" :src="record.upload_quality_approval_sheet" />
				</template>
			</FabricDocumentWorkspace>
			<DocumentDeleteButton v-if="workspace.actions?.delete?.allowed" ref="deleteControl" :show-trigger="false" :doctype="INSPECTION_DOCTYPE" :name="record.name" :docstatus="record.docstatus" :disabled="Boolean(acting)" redirect-to="/quality/inspections" />
		</section>
		<InspectionResultDialog :key="`result-${currentName}`" v-model:visible="resultVisible" :busy="acting === 'update_status'" @confirm="updateResult" />
		<InspectionDebitDialog :key="`debit-${currentName}`" v-model:visible="debitVisible" :busy="acting === 'create_debit'" @confirm="createDebit" />
		<DocumentConfirmationDialog v-model:visible="cancelVisible" title="Cancel inspection?" :message="`Cancel Quality Inspection ${record.name}?`" confirm-label="Cancel Inspection" :busy="Boolean(acting)" @confirm="cancel" />
		<DocumentErrorDialog :message="error" @dismiss="error = ''" />
	</DepartmentPage>
</template>

<script setup>
import Tab from "primevue/tab"
import TabList from "primevue/tablist"
import TabPanel from "primevue/tabpanel"
import TabPanels from "primevue/tabpanels"
import Tabs from "primevue/tabs"
import { useToast } from "primevue/usetoast"
import { computed, onBeforeUnmount, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { cancelDoc, submitDoc } from "../../api/frappe.js"
import { createInspectionDebit, getInspectionWorkspace, updateInspectionResult } from "../../api/quality.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import DocumentActionStrip from "../../components/documents/DocumentActionStrip.vue"
import DocumentConfirmationDialog from "../../components/documents/DocumentConfirmationDialog.vue"
import DocumentDeleteButton from "../../components/documents/DocumentDeleteButton.vue"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import DocumentSaveButton from "../../components/documents/DocumentSaveButton.vue"
import DocumentStatusBadge from "../../components/documents/DocumentStatusBadge.vue"
import InspectionDebitDetails from "./components/InspectionDebitDetails.vue"
import InspectionDebitDialog from "./components/InspectionDebitDialog.vue"
import InspectionResultDialog from "./components/InspectionResultDialog.vue"
import DocumentOverview from "../../components/documents/DocumentOverview.vue"
import { preserveListNavigationState } from "../../router/listDocumentNavigation.js"
import FabricDocumentWorkspace from "../fabric-store/FabricDocumentWorkspace.vue"
import InspectionApprovalSheet from "./components/InspectionApprovalSheet.vue"
import InspectionResultBadge from "./components/InspectionResultBadge.vue"
import InspectionSummary from "./components/InspectionSummary.vue"
import { INSPECTION_DOCTYPE, INSPECTION_TABS, INSPECTION_DETAIL_SECTIONS, copyText, inspectionActionItems, inspectionDetailFields, inspectionResultSummary, inspectionShareCaption } from "./qualityViews.js"
import "../purchase/lot/lot.css"
import "../merch/lot/merchLot.css"
import "./quality.css"

const props = defineProps({ inspectionId: { type: String, default: "" } })
const route = useRoute()
const router = useRouter()
const toast = useToast()
const workspace = ref({})
const loading = ref(true)
const loadError = ref("")
const error = ref("")
const acting = ref("")
const resultVisible = ref(false)
const debitVisible = ref(false)
const cancelVisible = ref(false)
const deleteControl = ref(null)
const currentName = computed(() => props.inspectionId || String(route.params.inspectionId || ""))
const record = computed(() => workspace.value.record || {})
const resultSummary = computed(() => inspectionResultSummary(record.value))
const detailFields = computed(() => inspectionDetailFields(record.value))
const activeTab = computed({
	get: () => INSPECTION_TABS.some((tab) => tab.key === route.query.tab) ? route.query.tab : "inspection",
	set: (tab) => router.replace({ query: { ...route.query, tab }, state: preserveListNavigationState() }),
})
let active = true
let loadSequence = 0
const actions = computed(() => {
	const items = inspectionActionItems(workspace.value.actions, {
		submit,
		edit: () => router.push(`/quality/inspections/${encodeURIComponent(record.value.name)}/edit`),
		amend: () => router.push(`/quality/inspections/new?amend_from=${encodeURIComponent(record.value.name)}`),
		update_status: () => { resultVisible.value = true },
		create_debit: () => { debitVisible.value = true },
		share,
		cancel: () => { cancelVisible.value = true },
		delete: () => deleteControl.value?.open(),
	})
	return items.map((action) => ({ ...action, disabled: Boolean(acting.value) || Boolean(action.disabled) }))
})

async function load() {
	const sequence = ++loadSequence
	loading.value = true
	loadError.value = ""
	try {
		const payload = await getInspectionWorkspace(currentName.value)
		if (active && sequence === loadSequence) workspace.value = payload
	} catch (reason) {
		if (active && sequence === loadSequence) loadError.value = reason?.message || "Unable to load inspection."
	} finally {
		if (active && sequence === loadSequence) loading.value = false
	}
}

async function run(key, operation, summary) {
	if (acting.value || !workspace.value.actions?.[key]?.allowed) return
	const name = currentName.value
	acting.value = key
	error.value = ""
	try {
		const result = await operation({ ...record.value })
		if (!active || currentName.value !== name) return
		resultVisible.value = debitVisible.value = cancelVisible.value = false
		toast.add({ severity: "success", summary: typeof summary === "function" ? summary(result) : summary, life: 3500 })
		await load()
	} catch (reason) {
		if (active && currentName.value === name) error.value = reason?.message || "Unable to complete inspection action."
	} finally {
		if (active && currentName.value === name) acting.value = ""
	}
}

function submit() {
	return run("submit", (doc) => submitDoc(INSPECTION_DOCTYPE, doc.name, doc.modified), "Inspection submitted")
}
function cancel() {
	return run("cancel", (doc) => cancelDoc(INSPECTION_DOCTYPE, doc.name, doc.modified), "Inspection cancelled")
}
function updateResult(result) {
	return run("update_status", (doc) => updateInspectionResult(doc.name, result, doc.modified), "Inspection status updated")
}
function createDebit(values) {
	return run("create_debit", (doc) => createInspectionDebit(doc.name, values), (debit) => `Debit ${debit.name} created`)
}

async function share() {
	if (acting.value || !workspace.value.actions?.share?.allowed) return
	acting.value = "share"
	let copied = false
	try {
		const caption = inspectionShareCaption(record.value, workspace.value.colour_size_data || {})
		copied = await copyText(caption)
		if (navigator.share && record.value.upload_quality_approval_sheet) {
			const url = `/api/method/frappe.handler.download_file?file_url=${encodeURIComponent(record.value.upload_quality_approval_sheet)}`
			const response = await fetch(url, { credentials: "include" })
			if (!response.ok) throw new Error("Unable to download approval sheet.")
			const blob = await response.blob()
			const data = { text: caption, files: [new File([blob], record.value.upload_quality_approval_sheet.split("/").pop(), { type: blob.type })] }
			if (!navigator.canShare || navigator.canShare(data)) {
				await navigator.share(data)
				return
			}
		}
	} catch (reason) {
		if (reason?.name !== "AbortError") {
			if (active) error.value = copied ? "Sharing failed, but inspection details were copied." : reason?.message || "Unable to share inspection."
			return
		}
	} finally {
		if (active) acting.value = ""
	}
	if (active && !copied) error.value = "Unable to copy inspection details on this device."
	else if (active) toast.add({ severity: "success", summary: "Inspection details copied", life: 3500 })
}

watch(currentName, () => {
	workspace.value = {}
	resultVisible.value = debitVisible.value = cancelVisible.value = false
	acting.value = error.value = ""
	load()
}, { immediate: true })
onBeforeUnmount(() => { active = false; ++loadSequence })
</script>
