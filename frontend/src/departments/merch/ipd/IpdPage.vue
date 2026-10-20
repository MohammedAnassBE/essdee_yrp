<template>
	<DepartmentPage title="Item Production Detail" back-to="/merch/item-production-details" back-label="Item Production Details" :show-title="false" flat full-width inline-navigation>
		<section class="merch-ipd-frame">
			<FabricDocumentWorkspace
				doctype="YRP Item Production Detail"
				title="Item Production Detail"
				:workspace="shellWorkspace"
				:loading="loading"
				:error="loadError || (isStaleWriteError(actionError) ? '' : actionError)"
				:acting="acting"
				:show-lifecycle-actions="false"
				@reload="load(true)"
			>
				<template #header="{ headingId }">
					<IpdIdentity
						:name="record.name || ipdId"
						:item="values.item || ''"
						:item-name="record.item_name || ''"
						:status="record.approval_status || ''"
						:version="record.version || ''"
						:tech-pack="values.tech_pack_version || ''"
						:pattern="values.pattern_version || ''"
						:heading-id="headingId"
					/>
				</template>
				<template #header-actions><DocumentActionStrip class="ipd-actions" :actions="stripActions" /></template>
				<template #matrix>
					<IpdSections ref="frame" :tabs="IPD_TABS" :doc="values" readonly>
						<template #before>
							<IpdCopyBanner v-if="record.copied_from" :source="workspace.source || { name: record.copied_from }" :changes="changes" @show-changes="openChanges" />
							<p v-if="lockNote" class="ipd-lock-note"><i class="pi pi-lock" aria-hidden="true" />{{ lockNote }}</p>
						</template>
					</IpdSections>
				</template>
				<template #rail>
					<IpdChecksRail :checks="checks" :running="checksRunning" :sections="sections" :used-by="workspace.used_by || []" :approval="approval" :show-checks="Boolean(checks) || checksRunning" @go-to="goTo" />
				</template>
			</FabricDocumentWorkspace>
		</section>
		<IpdChangesDialog v-model:visible="changesVisible" :source="record.copied_from || ''" :changes="changes || []" :loading="changesLoading" :error="changesError" />
		<IpdCopyDialog v-model:visible="copyVisible" :source="record.name || ipdId" @copied="openCopied" />
		<DocumentConfirmationDialog
			v-model:visible="revertVisible"
			title="Revert approval?"
			:message="revertMessage"
			confirm-label="Revert Approval"
			confirm-icon="pi pi-undo"
			cancel-label="Keep Approved"
			severity="warn"
			:busy="acting === 'revert_approval'"
			@confirm="runCommand('revert_approval')"
		/>
		<DocumentErrorDialog :message="isStaleWriteError(actionError) ? actionError : ''" retry-label="Reload" @dismiss="actionError = ''" @retry="load(true)" />
	</DepartmentPage>
</template>

<script setup>
import { useToast } from "primevue/usetoast"
import { computed, provide, reactive, readonly, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"

import { checkIpd, executeIpdCommand, getIpdChanges, getIpdWorkspace } from "../../../api/merch.js"
import DepartmentPage from "../../../components/DepartmentPage.vue"
import DocumentActionStrip from "../../../components/documents/DocumentActionStrip.vue"
import DocumentConfirmationDialog from "../../../components/documents/DocumentConfirmationDialog.vue"
import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"
import { preserveListNavigationState } from "../../../router/listDocumentNavigation.js"
import FabricDocumentWorkspace from "../../fabric-store/FabricDocumentWorkspace.vue"
import { ipdEditRoute } from "../merchViews.js"
import IpdChecksRail from "./IpdChecksRail.vue"
import IpdCopyDialog from "./IpdCopyDialog.vue"
import IpdIdentity from "./IpdIdentity.vue"
import IpdSections from "./IpdSections.vue"
import IpdCopyBanner from "./IpdCopyBanner.vue"
import IpdChangesDialog from "./IpdChangesDialog.vue"
import { IPD_TABS } from "./ipdTabs.js"
import { createFocusRegistry, goToProblem } from "./ipdFocus.js"
import { gridErrors, isStaleWriteError, problemsFor, recordActions, sectionStates, sectionsFor } from "./ipdEditor.js"
import { IPD_EDITOR_KEY } from "./useIpdEditor.js"
import "./ipd.css"

const props = defineProps({ ipdId: { type: String, required: true } })
const route = useRoute()
const router = useRouter()
const toast = useToast()
const workspace = ref({})
const loading = ref(true)
const loadError = ref("")
const actionError = ref("")
const acting = ref("")
const checks = ref(null)
const checksRunning = ref(false)
const copyVisible = ref(false)
const revertVisible = ref(false)
const frame = ref(null)
const { registerFocus, focusProblem } = createFocusRegistry()
const changesVisible = ref(false)
const changes = ref(null)
const changesLoading = ref(false)
const changesError = ref("")
let changesSequence = 0
async function openChanges() {
	changesVisible.value = true
	const sequence = ++changesSequence
	changesLoading.value = true
	changesError.value = ""
	try {
		const result = await getIpdChanges(record.value.name)
		if (sequence === changesSequence) changes.value = result?.changes || []
	} catch (reason) {
		if (sequence === changesSequence) changesError.value = reason?.message || "Unable to load the changes."
	} finally {
		if (sequence === changesSequence) changesLoading.value = false
	}
}
let loadSequence = 0
let checkSequence = 0

const record = computed(() => workspace.value.record || {})
const values = computed(() => workspace.value.values || {})
const capabilities = computed(() => workspace.value.capabilities || {})
const approved = computed(() => record.value.approval_status === "Approved")
const sections = computed(() => sectionsFor(Boolean(record.value.is_cloth_item)))
const states = computed(() => sectionStates(sections.value, values.value, checks.value))
const shellWorkspace = computed(() => loading.value || !record.value.name ? {} : { ...workspace.value, record: { ...record.value, doctype: "YRP Item Production Detail" } })
const approval = computed(() => record.value.name ? { status: record.value.approval_status, approvedBy: record.value.approved_by_name || record.value.approved_by || "" } : null)
const lockNote = computed(() => {
	if (approved.value) {
		const by = approval.value?.approvedBy ? `Approved by ${approval.value.approvedBy}. ` : "Approved. "
		return by + (capabilities.value.revert_approval?.allowed ? "Revert approval to edit." : "Create a new version to change it.")
	}
	return workspace.value.permissions?.can_write ? "" : "You can view this IPD. Editing needs write permission."
})
const lots = computed(() => (workspace.value.used_by || []).find((entry) => entry.is_current)?.lots || [])
const revertMessage = computed(() => lots.value.length
	? `Lots ${lots.value.join(", ")} use this IPD. Reverting lets merchandisers edit it again; the lots keep the values they copied.`
	: "No lots use this IPD yet. Reverting lets merchandisers edit it again.")

const readOnlyApi = reactive({
	draft: computed(() => readonly(values.value)), context: computed(() => workspace.value.context || {}),
	grids: {}, gridDrift: {}, fields: computed(() => workspace.value.fields || {}), record, checks, isNew: false, sections, states, readonly: true,
	problemsFor: (sectionKey) => problemsFor(checks.value, sectionKey),
	cellError: (field, rowKey, column) => gridErrors(checks.value, field)?.[rowKey]?.[column ?? ""] || "",
	gridErrors: (field) => gridErrors(checks.value, field),
	setValue: () => {}, setRows: () => {}, setJson: () => {}, setValues: () => {}, refreshGrids: () => {}, applyGrid: () => {},
	saveAttributeValues: () => Promise.reject(new Error("This IPD is read only.")),
	valueUsage: () => Promise.resolve({}), saveBomMapping: () => Promise.reject(new Error("This IPD is read only.")),
	registerFocus, fieldSchema: (fieldname) => ({ fieldname, label: fieldname, fieldtype: "Data" }),
})
provide(IPD_EDITOR_KEY, readOnlyApi)

const handlers = {
	edit: openEditor,
	approve: () => runCommand("approve"),
	revert_approval: () => { revertVisible.value = true },
	run_checks: runChecks,
	new_version: () => { copyVisible.value = true },
	regenerate_process_matrix: () => runCommand("regenerate_process_matrix"),
}
const stripActions = computed(() => recordActions({ approved: approved.value, capabilities: capabilities.value, acting: acting.value, problemCount: checks.value?.problems?.length || 0 })
	.map((action) => ({ ...action, command: handlers[action.key] })))

async function load(refresh = false) {
	const sequence = ++loadSequence
	const requested = props.ipdId
	loading.value = !refresh
	acting.value = refresh ? "reload" : ""
	loadError.value = ""
	actionError.value = ""
	checks.value = null
	try {
		const result = await getIpdWorkspace(requested)
		if (sequence === loadSequence && requested === props.ipdId) workspace.value = result
	} catch (reason) {
		if (sequence === loadSequence) loadError.value = reason?.message || "Unable to load this IPD."
	} finally {
		if (sequence === loadSequence) { loading.value = false; acting.value = "" }
	}
}
async function runChecks() {
	const sequence = ++checkSequence
	checksRunning.value = true
	try {
		const result = await checkIpd(record.value.name, null)
		if (sequence === checkSequence) checks.value = result
	} catch (reason) {
		if (sequence === checkSequence) actionError.value = reason?.message || "Unable to run the checks."
	} finally {
		if (sequence === checkSequence) checksRunning.value = false
	}
}
async function runCommand(command) {
	if (acting.value) return
	acting.value = command
	actionError.value = ""
	try {
		workspace.value = await executeIpdCommand(record.value.name, command, { expectedModified: record.value.modified })
		revertVisible.value = false
		checks.value = null
		toast.add({ severity: "success", summary: capabilities.value[command]?.label || "Done", detail: record.value.name, life: 3500 })
	} catch (reason) {
		actionError.value = reason?.message || "Unable to complete this action."
		revertVisible.value = false
	} finally {
		acting.value = ""
	}
}
function openEditor() {
	return router.push(ipdEditRoute(record.value.name, { hash: route.hash, state: preserveListNavigationState(record.value.name, record.value.modified) }))
}
function openCopied(name) {
	return router.push(ipdEditRoute(name))
}
async function goTo(problem) {
	return goToProblem(problem, frame.value, focusProblem)
}

watch(() => props.ipdId, () => load(), { immediate: true })
</script>
