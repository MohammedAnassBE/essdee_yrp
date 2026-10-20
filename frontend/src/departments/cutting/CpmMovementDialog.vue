<template>
	<Dialog
		:visible="visible"
		modal
		:dismissable-mask="!busy"
		maximizable
		:closable="!busy"
		:close-on-escape="!busy"
		:header="record?.name ? `Edit Cut Panel Movement · ${record.name}` : 'Create Cut Panel Movement'"
		class="erp-cpm-dialog erp-entity-dialog erp-dialog--xl"
		@update:visible="emit('update:visible', $event)"
	>
		<div v-if="loading" class="erp-dialog-loading"><Skeleton v-for="index in 7" :key="index" height="3.25rem" /></div>
		<div v-else class="erp-dialog-stack">
			<Message v-if="editor.create_blocker && !record" severity="warn" :closable="false">{{ editor.create_blocker }}</Message>
			<Message v-if="success" severity="success" :closable="false">{{ success }}</Message>
			<section class="erp-context-strip">
				<div><span>Lot</span><strong>{{ editor.context?.lot || "—" }}</strong></div>
				<div><span>Item</span><strong>{{ editor.context?.item || "—" }}</strong></div>
				<div><span>From Location</span><strong>{{ editor.context?.source_supplier || "—" }}</strong></div>
				<div><span>Warehouse</span><strong>{{ editor.context?.source_warehouse || "—" }}</strong></div>
				<div><span>Status</span><strong><DocumentStatusBadge :docstatus="record?.docstatus" :label="status" /></strong></div>
			</section>
			<CutPanelMovementEditor
				ref="movementEditor"
				:model-value="movementData"
				:context="editor.context"
				:record="record"
				:editable="canEdit"
				:generated="generated"
				:show-generate="canEdit && !record"
				:generating="generating"
				@update:model-value="replaceMovement"
				@generate="generateBundles"
			/>
		</div>

		<template #footer>
			<div class="erp-dialog-footer">
				<div class="erp-footer-summary" :class="{ 'erp-footer-summary--active': hasSelection }"><i :class="hasSelection ? 'pi pi-check-circle' : 'pi pi-info-circle'" /><span>{{ hasSelection ? selectionSummaryText : "Select at least one bundle, panel, collapsed quantity, or accessory weight." }}</span></div>
				<div class="erp-footer-actions">
					<Button label="Close" severity="secondary" text :disabled="saving" @click="emit('update:visible', false)" />
					<DocumentDeleteButton v-if="record?.name" doctype="SD YRP Cut Panel Movement" :name="record.name" :docstatus="record.docstatus" :disabled="saving" :redirect="false" @deleted="documentDeleted" />
					<DocumentPrintButton v-if="record?.permissions?.can_print" doctype="SD YRP Cut Panel Movement" :name="record.name" :formats="record.print_formats || []" :disabled="saving" />
					<Button v-if="record?.permissions?.can_cancel" label="Cancel Movement" icon="pi pi-ban" severity="danger" outlined :loading="saving && saveMode === 'cancel'" @click="cancelMovement" />
					<DocumentSaveButton :saved="Boolean(record?.name)" :dirty="dirty" :docstatus="Number(record?.docstatus || 0)" :document-label="`Cut Panel Movement ${record?.name || ''}`.trim()" :show-save="canEdit" :show-submit="canSubmit" :save-disabled="!generated" :submit-disabled="!hasSelection" :loading="saving" @save="save(false)" @submit="save(true)" />
				</div>
			</div>
		</template>
	</Dialog>
	<DocumentErrorDialog :message="error" title="Cut Panel Movement was not saved" @dismiss="error = ''" />
</template>

<script setup>
import DocumentDeleteButton from "../../components/documents/DocumentDeleteButton.vue"
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import { computed, reactive, ref, watch } from "vue"

import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import DocumentStatusBadge from "../../components/documents/DocumentStatusBadge.vue"
import { useActionConfirmation } from "../../utils/useActionConfirmation.js"
import CutPanelMovementEditor from "./CutPanelMovementEditor.vue"
import DocumentSaveButton from "../../components/documents/DocumentSaveButton.vue"
import DocumentPrintButton from "./DocumentPrintButton.vue"
import { changeMovementStatus, generateMovementBundles, getMovementEditor, saveMovement } from "./cpmApi.js"

const props = defineProps({ visible: Boolean, cuttingPlan: { type: String, required: true }, movement: { type: String, default: "" } })
const emit = defineEmits(["update:visible", "changed"])
const confirmAction = useActionConfirmation()
const movementEditor = ref(null)
const loading = ref(false)
const saving = ref(false)
const generating = ref(false)
const hasGenerated = ref(false)
const saveMode = ref("")
const error = ref("")
const success = ref("")
const savedDraft = ref(null)
const editor = reactive({ context: {}, defaults: {}, permissions: {}, record: null })
const movementData = reactive(emptyMovement())
const cleanSignature = ref("")
const signature = computed(() => JSON.stringify({ defaults: editor.defaults, movementData }))
const dirty = computed(() => !loading.value && signature.value !== cleanSignature.value)
let loadSequence = 0
let actionSequence = 0
const record = computed(() => editor.record)
const canEdit = computed(() => record.value ? Boolean(record.value.permissions?.can_write) : Boolean(editor.permissions?.can_create) && !editor.create_blocker)
const canSubmit = computed(() => canEdit.value && Boolean(record.value ? record.value.permissions?.can_submit : editor.permissions?.can_submit))
const status = computed(() => record.value?.status || "Draft")
const generated = computed(() => hasGenerated.value)
const hasSelection = computed(() => Boolean(movementEditor.value?.hasSelection))
const selectionSummaryText = computed(() => movementEditor.value?.selectionSummaryText || "")
const busy = computed(() => saving.value || generating.value)

watch(() => [props.visible, props.movement, props.cuttingPlan], ([visible]) => {
	if (visible) load()
	else {
		loadSequence += 1
		actionSequence += 1
		loading.value = false
		saving.value = false
		generating.value = false
		if (savedDraft.value) { emit("changed", savedDraft.value); savedDraft.value = null }
	}
})

async function load() {
	const sequence = ++loadSequence
	actionSequence += 1
	const requestedMovement = props.movement
	const requestedCuttingPlan = props.cuttingPlan
	loading.value = true; error.value = ""; success.value = ""; hasGenerated.value = false
	for (const key of Object.keys(editor)) delete editor[key]
	Object.assign(editor, { context: {}, defaults: {}, permissions: {}, record: null })
	replaceMovement({})
	try {
		const data = await getMovementEditor(requestedCuttingPlan, requestedMovement)
		if (loadIsStale(sequence, requestedMovement, requestedCuttingPlan)) return
		Object.assign(editor, data || {})
		replaceMovement(data?.movement_data || data?.record?.movement_data || {})
		hasGenerated.value = Boolean(data?.record)
		cleanSignature.value = signature.value
	} catch (reason) {
		if (!loadIsStale(sequence, requestedMovement, requestedCuttingPlan)) error.value = reason.message || "Unable to load the Cut Panel Movement."
	} finally {
		if (!loadIsStale(sequence, requestedMovement, requestedCuttingPlan)) loading.value = false
	}
}

function loadIsStale(sequence, requestedMovement, requestedCuttingPlan) {
	return sequence !== loadSequence || !props.visible || requestedMovement !== props.movement || requestedCuttingPlan !== props.cuttingPlan
}

function actionIsStale(sequence, requestedMovement, requestedCuttingPlan, requestedLoadSequence) {
	return sequence !== actionSequence || requestedLoadSequence !== loadSequence || !props.visible || requestedMovement !== props.movement || requestedCuttingPlan !== props.cuttingPlan
}

async function generateBundles() {
	if (editor.create_blocker) { error.value = editor.create_blocker; return }
	const sequence = ++actionSequence
	const requestedMovement = props.movement
	const requestedCuttingPlan = props.cuttingPlan
	const requestedLoadSequence = loadSequence
	const postingDate = editor.defaults?.posting_date
	const postingTime = editor.defaults?.posting_time
	generating.value = true; error.value = ""
	try {
		const data = await generateMovementBundles(requestedCuttingPlan, postingDate, postingTime)
		if (actionIsStale(sequence, requestedMovement, requestedCuttingPlan, requestedLoadSequence)) return
		replaceMovement(data || {}); hasGenerated.value = true
	} catch (reason) {
		if (!actionIsStale(sequence, requestedMovement, requestedCuttingPlan, requestedLoadSequence)) error.value = reason.message || "Unable to generate the available bundles."
	} finally {
		if (!actionIsStale(sequence, requestedMovement, requestedCuttingPlan, requestedLoadSequence)) generating.value = false
	}
}

async function save(submit) {
	if (submit && !hasSelection.value) { error.value = "Select at least one bundle, panel, collapsed quantity, or accessory weight."; return }
	const sequence = ++actionSequence
	const requestedMovement = props.movement
	const requestedCuttingPlan = props.cuttingPlan
	const requestedLoadSequence = loadSequence
	const requestedRecord = record.value?.name
	const expectedModified = record.value?.modified
	const request = { ...editor.defaults, movement_data: clone(movementData) }
	saving.value = true; saveMode.value = submit ? "submit" : "draft"; error.value = ""; success.value = ""
	try {
		const saved = await saveMovement(requestedCuttingPlan, request, requestedRecord, submit, expectedModified)
		if (actionIsStale(sequence, requestedMovement, requestedCuttingPlan, requestedLoadSequence)) return
		editor.record = saved; replaceMovement(saved.movement_data || {}); cleanSignature.value = signature.value; success.value = submit ? "Cut Panel Movement submitted." : "Draft movement saved."; hasGenerated.value = true
		if (submit) { savedDraft.value = null; emit("changed", saved) }
		else savedDraft.value = saved
		if (submit) emit("update:visible", false)
	} catch (reason) {
		if (!actionIsStale(sequence, requestedMovement, requestedCuttingPlan, requestedLoadSequence)) error.value = reason.message || "Unable to save the Cut Panel Movement."
	} finally {
		if (!actionIsStale(sequence, requestedMovement, requestedCuttingPlan, requestedLoadSequence)) { saving.value = false; saveMode.value = "" }
	}
}

async function cancelMovement() {
	return confirmAction({ header: "Cancel Cut Panel Movement?", message: `Cancel Cut Panel Movement ${record.value?.name}? This changes the document status and cannot be undone here.`, acceptLabel: "Cancel Movement", acceptIcon: "pi pi-ban", accept: performCancelMovement })
}

async function performCancelMovement() {
	const sequence = ++actionSequence
	const requestedMovement = props.movement
	const requestedCuttingPlan = props.cuttingPlan
	const requestedLoadSequence = loadSequence
	const requestedRecord = record.value?.name
	saving.value = true; saveMode.value = "cancel"; error.value = ""
	try {
		const changed = await changeMovementStatus(requestedCuttingPlan, requestedRecord, "cancel")
		if (actionIsStale(sequence, requestedMovement, requestedCuttingPlan, requestedLoadSequence)) return
		savedDraft.value = null; editor.record = changed; emit("changed", changed); emit("update:visible", false)
	} catch (reason) {
		if (!actionIsStale(sequence, requestedMovement, requestedCuttingPlan, requestedLoadSequence)) error.value = reason.message || "Unable to cancel the Cut Panel Movement."
	} finally {
		if (!actionIsStale(sequence, requestedMovement, requestedCuttingPlan, requestedLoadSequence)) { saving.value = false; saveMode.value = "" }
	}
}

function replaceMovement(value) { Object.assign(movementData, emptyMovement(), clone(value)) }
function emptyMovement() { return { panels: [], data: {}, accessory_data: [], collapsed_details: [], is_set_item: 0 } }
function clone(value) { return JSON.parse(JSON.stringify(value || {})) }
function documentDeleted() {
	savedDraft.value = null
	emit("update:visible", false)
	emit("changed")
}
</script>

<style scoped>
.erp-dialog-stack,.erp-dialog-loading{display:grid;gap:14px}.erp-context-strip{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));overflow:hidden;border:1px solid var(--erp-border);border-radius:var(--erp-panel-radius);background:var(--erp-surface-soft)}.erp-context-strip>div{display:grid;gap:4px;padding:11px 13px;border-right:1px solid var(--erp-border)}.erp-context-strip>div:last-child{border-right:0}.erp-context-strip span{color:var(--erp-text-muted);font-size:var(--erp-font-size-min)}.erp-context-strip strong{overflow:hidden;color:var(--erp-text);font-size:13px;text-overflow:ellipsis;white-space:nowrap}.erp-status{display:inline-flex;width:max-content;padding:3px 8px;border-radius:var(--erp-pill-radius);background:#eef2f0;color:#526159;font-size:var(--erp-font-size-min);font-style:normal;text-transform:uppercase}.erp-status--submitted{background:#e1f6eb;color:#087744}.erp-status--cancelled{background:#fde8e8;color:#b42318}.erp-dialog-footer{display:flex;align-items:center;justify-content:space-between;gap:16px;width:100%}.erp-footer-summary{display:flex;align-items:center;gap:7px;color:var(--erp-text-muted);font-size:var(--erp-font-size-min)}.erp-footer-summary--active{color:var(--erp-accent)}.erp-footer-actions{display:flex;align-items:center;justify-content:flex-end;gap:8px}@media(max-width:950px){.erp-context-strip{grid-template-columns:repeat(2,minmax(0,1fr))}.erp-dialog-footer{align-items:flex-end;flex-direction:column}.erp-footer-actions{flex-wrap:wrap}}
</style>
