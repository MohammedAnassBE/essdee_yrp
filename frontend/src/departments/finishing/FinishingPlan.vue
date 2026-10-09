<template>
	<DepartmentPage title="Finishing Plan" accent="#087c91" back-to="/finishing/plans" back-label="Finishing Plans" :show-title="false" flat full-width inline-navigation>
		<div v-if="loading && !ready" class="finishing-plan__probe erp-workspace" aria-label="Loading Finishing Plan"><Skeleton height="64px" /><Skeleton height="420px" /></div>
		<div v-else-if="loadError && !ready" class="finishing-plan__probe erp-workspace">
			<WorkspaceLoadError title="Finishing Plan unavailable" :message="loadError" :loading="loading" @retry="load" />
		</div>
		<section v-else class="finishing-plan erp-workspace erp-card" aria-label="Finishing Plan details" :aria-busy="loading">
			<header class="finishing-plan__header">
				<InlinePageNavigation
					title-target="finishing-plan-title"
					show-document-navigation
					:current-name="finishingPlanId"
					document-label="Finishing Plan"
					:navigation-disabled="loading || busy"
				/>
				<div class="finishing-plan__identity">
					<div class="finishing-plan__title"><h1 id="finishing-plan-title">Finishing Plan</h1><span>{{ finishingPlanId }}</span></div>
					<div class="finishing-plan__meta">
						<DocumentStatusBadge :label="record.fp_status || 'Planned'" />
						<span v-for="fact in headerFacts" :key="fact.label" class="finishing-plan__fact" :class="`finishing-plan__fact--${fact.key}`" :title="fact.value">
							<small>{{ fact.label }}</small><strong>{{ fact.value || "—" }}</strong>
						</span>
					</div>
				</div>
				<div class="finishing-plan__actions">
					<DocumentPrintButton v-if="workspace.permissions?.can_print" doctype="SD YRP Finishing Plan" :name="finishingPlanId" :formats="workspace.print_formats || []" :disabled="loading || busy" />
					<FinishingPlanActions :workspace="workspace" :busy="busy" @command="(command) => runCommand(command)" @entry="openEntry" />
				</div>
			</header>
			<Message v-if="workspace.locked" severity="warn" :closable="false" class="finishing-plan__notice">
				<strong>{{ record.fp_status }}</strong> — this Finishing Plan is locked. Creating new entries has been disabled.
			</Message>
			<FinishingPlanTabs
				:name="finishingPlanId"
				:workspace="workspace"
				:version="version"
				:busy="busy"
				@open="openDocument"
				@cancel="confirmCancel"
				@upload="uploadProfitAndLoss"
				@delete-document="confirmDeleteProfitAndLoss"
				@entry="openEntry"
				@transfer="confirmLotTransfer"
			/>
		</section>
		<FinishingEntryDialog v-if="entryAction" v-model:visible="entryOpen" :action="entryAction" :name="finishingPlanId" :workspace="workspace" :busy="busy" @submit="submitEntry" />
		<RelatedDocumentWorkspaceDialog
			v-model:visible="relatedDocumentOpen"
			:doctype="openedDocument.doctype"
			:name="openedDocument.name"
			@changed="documentChanged"
			@closed="relatedDocumentOpen = false"
		/>
		<DocumentTransactionDialog
			v-model:visible="documentOpen"
			:doctype="openedDocument.doctype"
			:name="openedDocument.name"
			:show-edit="false"
			@changed="documentChanged"
		/>
		<DocumentErrorDialog :message="actionError" title="Finishing Plan action failed" @dismiss="actionError = ''" />
	</DepartmentPage>
</template>

<script setup>
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import { useToast } from "primevue/usetoast"
import { computed, reactive, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"

import { executeFinishingPlanCommand, getFinishingPlanWorkspace } from "../../api/finishing.js"
import { uploadFile } from "../../api/frappe.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import DocumentPrintButton from "../../components/documents/DocumentPrintButton.vue"
import DocumentStatusBadge from "../../components/documents/DocumentStatusBadge.vue"
import DocumentTransactionDialog from "../../components/documents/DocumentTransactionDialog.vue"
import InlinePageNavigation from "../../components/navigation/InlinePageNavigation.vue"
import { useActionConfirmation } from "../../utils/useActionConfirmation.js"
import RelatedDocumentWorkspaceDialog from "../fabric-store/RelatedDocumentWorkspaceDialog.vue"
import { webDocumentPath } from "../../router/webDocumentRoutes.js"
import FinishingEntryDialog from "./FinishingEntryDialog.vue"
import FinishingPlanActions from "./FinishingPlanActions.vue"
import FinishingPlanTabs from "./FinishingPlanTabs.vue"
import "./finishing.css"

const route = useRoute()
const router = useRouter()
const toast = useToast()
const confirmAction = useActionConfirmation()
const finishingPlanId = computed(() => String(route.params.finishingPlanId || ""))
const workspace = ref({})
const record = computed(() => workspace.value.record || {})
const loading = ref(true)
const ready = ref(false)
const loadError = ref("")
const busy = ref(false)
const actionError = ref("")
const version = ref(0)
const documentOpen = ref(false)
const relatedDocumentOpen = ref(false)
const entryOpen = ref(false)
const entryAction = ref("")
const RELATED_DOCUMENT_DOCTYPES = new Set(["YRP Delivery Challan", "YRP Goods Received Note"])
const openedDocument = reactive({ doctype: "YRP Delivery Challan", name: "" })
const headerFacts = computed(() => [
	{ key: "lot", label: "Lot", value: record.value.lot },
	{ key: "item", label: "Item", value: record.value.item },
	{ key: "work-order", label: "Work Order", value: record.value.work_order },
	{ key: "pieces-per-box", label: "Pcs / Box", value: record.value.pieces_per_box },
])
const successMessages = {
	request_audit: "Status set to Ready for Audit.",
	complete_audit: "Status set to Audit Completed.",
	complete_ocr: "Status set to OCR Completed.",
	fetch_rejected_quantity: "Finishing Plan quantities refreshed.",
	cancel_linked_document: "Document cancelled.",
	add_p_and_l_document: "P & L document saved.",
	delete_p_and_l_document: "P & L document deleted.",
	create_delivery_challan: "Delivery Challan created.",
	return_items: "Items returned.",
	convert_to_loose_piece: "Items converted to loose pieces.",
	create_grn: "Goods Received Note created.",
	dispatch_box: "Boxes dispatched.",
	add_ironing_excess: "Ironing excess added.",
	return_pack: "Packed pieces returned.",
	lot_transfer: "Items transferred.",
	create_alternative_plan: "Alternative plan created.",
	update_alternative_quantity: "Alternate lot quantity updated.",
}
let loadSequence = 0

async function load() {
	const sequence = ++loadSequence
	const name = finishingPlanId.value
	loading.value = true
	loadError.value = ""
	try {
		const data = await getFinishingPlanWorkspace(name)
		if (sequence !== loadSequence) return
		workspace.value = data || {}
		ready.value = true
	} catch (reason) {
		if (sequence === loadSequence) loadError.value = reason?.message || "Unable to load this Finishing Plan."
	} finally {
		if (sequence === loadSequence) loading.value = false
	}
}

async function runCommand(command, payload = {}) {
	if (busy.value) return null
	busy.value = true
	actionError.value = ""
	try {
		const { result = null, ...data } = await executeFinishingPlanCommand(finishingPlanId.value, command, payload, record.value.modified) || {}
		workspace.value = data
		version.value += 1
		toast.add({ severity: "success", summary: successMessages[command], detail: result?.name || finishingPlanId.value, life: 3500 })
		return { result }
	} catch (reason) {
		actionError.value = reason?.message || "Unable to complete this Finishing Plan action."
		return null
	} finally {
		busy.value = false
	}
}

function openEntry(action) {
	entryAction.value = action
	entryOpen.value = true
}

async function submitEntry(action, payload) {
	const outcome = await runCommand(action, payload)
	if (!outcome) return
	entryOpen.value = false
	openResult(outcome.result)
}

function openResult(result) {
	if (!result?.doctype || !result?.name) return
	if (result.doctype === "YRP Work Order") {
		router.push(webDocumentPath(result.doctype, result.name).replace(/^\/web/, ""))
		return
	}
	openDocument(result.doctype, result.name)
}

function confirmLotTransfer(transfers) {
	confirmAction({
		header: "Transfer the items?",
		message: "Are you sure want to transfer the items?",
		acceptLabel: "Transfer",
		acceptIcon: "pi pi-arrow-right-arrow-left",
		acceptSeverity: "primary",
		rejectLabel: "No",
		accept: async () => openResult((await runCommand("lot_transfer", { transfers }))?.result),
	})
}

function openDocument(doctype, name) {
	Object.assign(openedDocument, { doctype, name })
	if (RELATED_DOCUMENT_DOCTYPES.has(doctype)) relatedDocumentOpen.value = true
	else documentOpen.value = true
}

function documentChanged() {
	load().then(() => { version.value += 1 })
}

function confirmCancel(doctype, name) {
	confirmAction({
		header: `Cancel ${name}?`,
		message: `Cancel ${doctype} ${name}? This reverses its stock and quantities on this Finishing Plan.`,
		acceptLabel: "Cancel Document",
		acceptIcon: "pi pi-ban",
		accept: () => runCommand("cancel_linked_document", { doctype, name }),
	})
}

async function uploadProfitAndLoss({ file, comments }) {
	if (busy.value) return
	busy.value = true
	let uploaded = null
	try {
		uploaded = await uploadFile(file, { doctype: "SD YRP Finishing Plan", docname: finishingPlanId.value, isPrivate: 1 })
	} catch (reason) {
		actionError.value = reason?.message || "Unable to upload this file."
	} finally {
		busy.value = false
	}
	if (uploaded?.file_url) await runCommand("add_p_and_l_document", { file_url: uploaded.file_url, comments })
}

function confirmDeleteProfitAndLoss(document) {
	confirmAction({
		header: "Delete P & L document?",
		message: `Delete ${String(document.file || "").split("/").pop()}? This cannot be undone.`,
		acceptLabel: "Delete Document",
		acceptIcon: "pi pi-trash",
		accept: () => runCommand("delete_p_and_l_document", { document: document.name }),
	})
}

watch(finishingPlanId, () => {
	ready.value = false
	workspace.value = {}
	load()
}, { immediate: true })
</script>

<style scoped>
.finishing-plan__probe { display: grid; gap: var(--erp-space-3); }
.finishing-plan { display: flex; min-width: 0; padding: 12px 14px; flex-direction: column; gap: 8px; border-top: 3px solid var(--accent, var(--erp-accent)); }
.finishing-plan__header { display: flex; align-items: center; justify-content: space-between; gap: 14px; min-height: 48px; padding-bottom: 10px; border-bottom: 1px solid var(--erp-border); }
.finishing-plan__header > :first-child { flex: 0 0 auto; }
.finishing-plan__identity { display: flex; flex: 1 1 auto; align-items: center; gap: 14px; min-width: 0; }
.finishing-plan__title { display: grid; gap: 3px; min-width: 0; }
.finishing-plan__title h1 { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-title); font-weight: 760; letter-spacing: -0.025em; line-height: 1.05; white-space: nowrap; }
.finishing-plan__title > span { overflow: hidden; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); font-weight: 620; font-variant-numeric: tabular-nums; text-overflow: ellipsis; white-space: nowrap; }
.finishing-plan__meta { display: flex; align-items: center; gap: 12px; min-width: 0; }
.finishing-plan__fact { display: grid; gap: 2px; min-width: 0; max-width: 220px; padding-left: 12px; border-left: 1px solid var(--erp-border); }
.finishing-plan__fact small { color: var(--erp-text-muted); font-size: var(--erp-font-size-label); font-weight: 720; letter-spacing: .035em; line-height: 1; text-transform: uppercase; }
.finishing-plan__fact strong { overflow: hidden; color: var(--erp-text); font-size: var(--erp-font-size-table); font-weight: 730; text-overflow: ellipsis; white-space: nowrap; }
.finishing-plan__fact--item { max-width: 300px; }
.finishing-plan__actions { display: flex; flex: 0 0 auto; align-items: center; gap: 7px; }
.finishing-plan__notice { margin: 0; }
@media (max-width: 1100px) {
	.finishing-plan__header { align-items: flex-start; flex-wrap: wrap; }
	.finishing-plan__identity { flex-basis: calc(100% - 140px); }
	.finishing-plan__actions { margin-left: auto; }
}
@media (max-width: 700px) {
	.finishing-plan { padding: 10px; }
	.finishing-plan__identity { align-items: flex-start; flex-direction: column; gap: 8px; }
	.finishing-plan__meta { flex-wrap: wrap; gap: 8px 12px; }
	.finishing-plan__meta > .finishing-plan__fact:nth-child(2) { padding-left: 0; border-left: 0; }
	.finishing-plan__fact, .finishing-plan__fact--item { max-width: 100%; }
	.finishing-plan__actions { width: 100%; justify-content: flex-start; flex-wrap: wrap; }
}
</style>
