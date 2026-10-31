<template>
	<section class="merch-ipd-frame">
		<FabricDocumentWorkspace
			doctype="YRP Item Production Detail"
			title="Item Production Detail"
			:workspace="shellWorkspace"
			:loading="loading"
			:error="loadError || (hasStaleError ? actionError : '')"
			:dirty="isDirty && !navigatingInternally"
			:acting="acting"
			:show-lifecycle-actions="false"
			:show-save-state="false"
			:live-reload="refresh"
			@reload="requestReload"
		>
			<template #header="{ headingId }">
				<IpdIdentity
					:name="record.name || ''"
					:item="draft.item || ''"
					:item-name="record.item_name || ''"
					:status="record.approval_status || ''"
					:version="record.version || ''"
					:tech-pack="draft.tech_pack_version || ''"
					:pattern="draft.pattern_version || ''"
					:draft-state="acting === 'save' ? 'saving' : isDirty ? 'dirty' : 'saved'"
					:saved-at="savedAt"
					:heading-id="headingId"
					editing
				/>
			</template>
			<template #header-actions><DocumentActionStrip class="ipd-actions" :actions="stripActions" /></template>
			<template #matrix>
				<IpdSections
					ref="frame"
					:tabs="IPD_TABS"
					:doc="draft"
					:is-new="isNew"
					@leave-first-section="createDraft"
				>
					<template #before>
						<IpdCopyBanner v-if="record.copied_from" :source="payload?.source" :changes="changes" @show-changes="openChanges" />
					</template>
				</IpdSections>
			</template>
			<template #rail>
				<IpdChecksRail :checks="checks" :running="checksRunning" :used-by="payload?.used_by || []" :show-checks="!isNew" show-keys @go-to="goTo" />
			</template>
		</FabricDocumentWorkspace>
		<IpdCopyDialog v-model:visible="copyVisible" :source="copySource" @copied="openCopied" />
		<IpdChangesDialog v-model:visible="changesVisible" :source="payload?.source?.name || ''" :changes="changes || []" :loading="changesLoading" :error="changesError" />
		<DocumentConfirmationDialog v-model:visible="reloadVisible" title="Discard unsaved changes?" message="Reloading replaces your unsaved changes with the saved IPD." confirm-label="Discard and reload" cancel-label="Keep editing" severity="warn" @confirm="confirmReload" />
		<DocumentErrorDialog
			:message="hasStaleError || locatingSaveProblem ? '' : actionError"
			title="Item Production Detail could not be completed"
			@dismiss="actionError = ''"
			@after-hide="focusSaveProblemAfterClose"
		/>
	</section>
</template>

<script setup>
import { computed, nextTick, provide, ref, watch } from "vue"
import { useRouter } from "vue-router"

import { getIpdChanges } from "../../../api/merch.js"
import DocumentActionStrip from "../../../components/documents/DocumentActionStrip.vue"
import DocumentConfirmationDialog from "../../../components/documents/DocumentConfirmationDialog.vue"
import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"
import FabricDocumentWorkspace from "../../fabric-store/FabricDocumentWorkspace.vue"
import { ipdEditRoute } from "../merchViews.js"
import IpdChangesDialog from "./IpdChangesDialog.vue"
import IpdChecksRail from "./IpdChecksRail.vue"
import IpdCopyBanner from "./IpdCopyBanner.vue"
import IpdCopyDialog from "./IpdCopyDialog.vue"
import IpdIdentity from "./IpdIdentity.vue"
import IpdSections from "./IpdSections.vue"
import { IPD_TABS } from "./ipdTabs.js"
import { goToProblem } from "./ipdFocus.js"
import { ENTRY_GRID_INVALID_KEY } from "../../../components/common/entryGrid.js"
import { IPD_EDITOR_KEY, useIpdEditor } from "./useIpdEditor.js"
import "./ipd.css"

const props = defineProps({ ipdId: { type: String, default: "" } })
const router = useRouter()
const editor = useIpdEditor(props.ipdId)
const {
	payload, draft, record, isNew, checks, checksRunning, loading, acting, loadError, actionError, savedAt,
	isDirty, hasStaleError, navigatingInternally, shellWorkspace, actions, load, refresh, save, createDraft, runChecks, approve, regenerate, cancel,
	followName, focusProblem, firstInvalidCell,
} = editor
provide(IPD_EDITOR_KEY, editor.api)
provide(ENTRY_GRID_INVALID_KEY, editor.invalidRegistry)

const frame = ref(null)
const copyVisible = ref(false)
const copySource = ref("")
const changesVisible = ref(false)
const changes = ref(null)
const changesLoading = ref(false)
const changesError = ref("")
const reloadVisible = ref(false)
const locatingSaveProblem = ref(false)
let saveProblem = null
let changesSequence = 0

const handlers = {
	save: saveAndFocus, approve, cancel,
	run_checks: runChecks,
	regenerate_process_matrix: regenerate,
	copy_from: () => openCopy(""),
	new_version: () => openCopy(record.value.name),
	show_changes: openChanges,
}
const stripActions = computed(() => actions.value.map((action) => ({ ...action, command: handlers[action.key] })))

function openCopy(source) {
	copySource.value = source || ""
	copyVisible.value = true
}
function openCopied(name) {
	return router.push(ipdEditRoute(name))
}
async function loadChanges() {
	const sequence = ++changesSequence
	if (!record.value.copied_from || !payload.value?.source?.name) { changes.value = null; return }
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
function openChanges() {
	changesVisible.value = true
	if (changes.value === null) loadChanges()
}
async function saveAndFocus() {
	saveProblem = null
	locatingSaveProblem.value = true
	try {
		await save()
		if (!actionError.value || hasStaleError.value) return
		saveProblem = firstInvalidCell.value
		if (!saveProblem) {
			const result = await runChecks()
			saveProblem = result?.problems?.[0] || null
		}
		if (saveProblem) await focusSaveProblem(saveProblem)
	} finally {
		locatingSaveProblem.value = false
	}
}
async function focusSaveProblem(problem) {
	if (problem.focusCell) {
		await frame.value?.jumpTo(problem.tab, { focus: false })
		if (problem.focusCell(problem.row_key, problem.column)) return
	}
	await goTo(problem)
}
async function focusSaveProblemAfterClose() {
	const problem = saveProblem
	saveProblem = null
	if (!problem) return
	// Let the shared dialog finish its deferred restoration of the opener.
	await nextTick()
	await new Promise((resolve) => window.requestAnimationFrame(() => window.requestAnimationFrame(resolve)))
	if (frame.value && !actionError.value && !locatingSaveProblem.value) await focusSaveProblem(problem)
}
async function goTo(problem) {
	return goToProblem(problem, frame.value, focusProblem)
}
function requestReload() {
	if (isDirty.value) { reloadVisible.value = true; return }
	load(record.value.name)
}
function confirmReload() {
	reloadVisible.value = false
	load(record.value.name)
}

watch(() => props.ipdId, followName)
watch(() => record.value.modified, loadChanges)
</script>
