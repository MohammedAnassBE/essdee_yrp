<template>
	<Dialog
		:visible="visible"
		modal
		maximizable
		:dismissable-mask="false"
		:style="{ width: 'min(96vw, 1540px)' }"
		:header="record?.name ? `Cut Panel Movement · ${record.name}` : 'New Cut Panel Movement'"
		class="erp-cut-panel-movement-dialog erp-entity-dialog"
		@update:visible="emit('update:visible', $event)"
	>
		<div v-if="loading" class="movement-dialog__loading"><Skeleton v-for="index in 7" :key="index" height="3rem" /></div>
		<div v-else class="movement-dialog__body">
			<section class="movement-document-card">
				<header><span>DOCUMENT</span><h3>Movement source & posting</h3><em>{{ record?.status || "Draft" }}</em></header>
				<div class="movement-document-grid">
					<LinkField v-model="form.lot" doctype="SD YRP Lot" label="Lot" required :disabled="Boolean(record) || busy" @update:model-value="sourceChanged" />
					<LinkField v-model="form.from_warehouse" doctype="Supplier" label="From Warehouse" required :disabled="Boolean(record) || busy" @update:model-value="sourceChanged" />
					<div class="movement-context-value"><span>Item</span><strong>{{ editor.context?.item || "Derived from Lot" }}</strong></div>
					<DateField v-model="form.posting_date" label="Posting Date" required :disabled="!form.edit_posting_date_and_time || busy" />
					<TimeField v-model="form.posting_time" label="Posting Time" required :disabled="!form.edit_posting_date_and_time || busy" />
					<label class="movement-toggle"><span>Edit Posting Date and Time</span><ToggleSwitch v-model="form.edit_posting_date_and_time" :disabled="busy" /></label>
				</div>
			</section>

			<CutPanelMovementEditor
				ref="movementEditor"
				:model-value="movementData"
				:context="editor.context"
				:record="record"
				:editable="canEdit"
				:generated="generated"
				:show-generate="canEdit"
				:generating="acting === 'generate'"
				@update:model-value="replaceMovement"
				@generate="generateBundles"
			/>
		</div>

		<template #footer>
			<div class="movement-dialog__footer">
				<span>{{ hasSelection ? selectionSummaryText : "Generate current stock, then select what is moving." }}</span>
				<div>
					<Button label="Close" severity="secondary" text :disabled="busy" @click="emit('update:visible', false)" />
					<Button v-if="record?.permissions?.can_cancel" label="Cancel" icon="pi pi-ban" severity="danger" outlined :disabled="busy" @click="requestCommand('cancel')" />
					<Button v-if="record?.permissions?.can_submit" label="Submit" icon="pi pi-check" severity="secondary" outlined :disabled="busy || !hasSelection" @click="requestCommand('submit')" />
					<Button v-if="canEdit" label="Save" icon="pi pi-save" :loading="acting === 'save'" :disabled="busy || !generated" @click="save" />
				</div>
			</div>
		</template>
	</Dialog>

	<DocumentConfirmationDialog
		v-model:visible="confirmationVisible"
		:title="pendingCommand === 'cancel' ? 'Cancel Cut Panel Movement?' : 'Submit Cut Panel Movement?'"
		:message="pendingCommand === 'cancel' ? `Cancel ${record?.name}?` : `Submit ${record?.name}? Stock will be validated again before submission.`"
		:confirm-label="pendingCommand === 'cancel' ? 'Cancel Movement' : 'Submit Movement'"
		:severity="pendingCommand === 'cancel' ? 'danger' : 'success'"
		:busy="acting === pendingCommand"
		@confirm="confirmCommand"
	/>
	<DocumentErrorDialog :message="error" title="Cut Panel Movement action failed" @dismiss="error = ''" />
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import Skeleton from "primevue/skeleton"
import ToggleSwitch from "primevue/toggleswitch"
import { computed, reactive, ref, watch } from "vue"

import { executeCutPanelMovementCommand, generateCutPanelMovementBundles, getCutPanelMovementEditor, saveCutPanelMovement } from "../../api/cutPanelStore.js"
import DateField from "../../components/common/DateField.vue"
import LinkField from "../../components/common/LinkField.vue"
import TimeField from "../../components/common/TimeField.vue"
import DocumentConfirmationDialog from "../../components/documents/DocumentConfirmationDialog.vue"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import CutPanelMovementEditor from "../cutting/CutPanelMovementEditor.vue"

const props = defineProps({ visible: Boolean, movement: { type: String, default: "" } })
const emit = defineEmits(["update:visible", "changed"])
const loading = ref(false)
const acting = ref("")
const error = ref("")
const generated = ref(false)
const confirmationVisible = ref(false)
const pendingCommand = ref("")
const movementEditor = ref(null)
const editor = reactive({ context: {}, permissions: {}, record: null })
const form = reactive({ lot: "", from_warehouse: "", posting_date: "", posting_time: "", edit_posting_date_and_time: false })
const movementData = reactive(emptyMovement())
const record = computed(() => editor.record)
const busy = computed(() => Boolean(acting.value))
const canEdit = computed(() => record.value ? Boolean(record.value.permissions?.can_write) : Boolean(editor.permissions?.can_create))
const hasSelection = computed(() => Boolean(movementEditor.value?.hasSelection))
const selectionSummaryText = computed(() => movementEditor.value?.selectionSummaryText || "")

watch(() => [props.visible, props.movement], ([visible]) => { if (visible) load() })

async function load() {
	loading.value = true; error.value = ""; generated.value = false
	try {
		const payload = await getCutPanelMovementEditor(props.movement)
		Object.assign(editor, payload || {})
		Object.assign(form, payload?.defaults || {})
		form.edit_posting_date_and_time = Boolean(form.edit_posting_date_and_time)
		replaceMovement(payload?.movement_data || payload?.record?.movement_data || {})
		generated.value = Boolean(payload?.record)
	} catch (reason) { error.value = reason.message || "Unable to load the Cut Panel Movement." } finally { loading.value = false }
}

function sourceChanged() { generated.value = false; replaceMovement({}) }

async function generateBundles() {
	acting.value = "generate"; error.value = ""
	try {
		const payload = await generateCutPanelMovementBundles({ ...form })
		replaceMovement(payload || {}); generated.value = true
	} catch (reason) { error.value = reason.message || "Unable to generate the available bundles." } finally { acting.value = "" }
}

async function save() {
	acting.value = "save"; error.value = ""
	try {
		const saved = await saveCutPanelMovement({ ...form, movement_data: clone(movementData) }, { name: record.value?.name, expectedModified: record.value?.modified })
		editor.record = saved; Object.assign(editor.context, { lot: saved.lot, item: saved.item, source_supplier: saved.from_warehouse }); replaceMovement(saved.movement_data || {}); generated.value = true; emit("changed", saved)
	} catch (reason) { error.value = reason.message || "Unable to save the Cut Panel Movement." } finally { acting.value = "" }
}

function requestCommand(command) { pendingCommand.value = command; confirmationVisible.value = true }
async function confirmCommand() {
	const command = pendingCommand.value; acting.value = command; error.value = ""
	try {
		const changed = await executeCutPanelMovementCommand(record.value.name, command, record.value.modified)
		editor.record = changed; replaceMovement(changed.movement_data || movementData); confirmationVisible.value = false; emit("changed", changed)
		if (command === "cancel" || command === "submit") emit("update:visible", false)
	} catch (reason) { error.value = reason.message || `Unable to ${command} the Cut Panel Movement.` } finally { acting.value = ""; pendingCommand.value = "" }
}

function replaceMovement(value) { Object.assign(movementData, emptyMovement(), clone(value)) }
function emptyMovement() { return { panels: [], data: {}, accessory_data: [], collapsed_details: [], is_set_item: 0 } }
function clone(value) { return JSON.parse(JSON.stringify(value || {})) }
</script>

<style scoped>
.movement-dialog__loading,.movement-dialog__body{display:grid;gap:12px}.movement-document-card{overflow:hidden;border:1px solid var(--erp-border);border-radius:var(--erp-panel-radius);background:var(--erp-surface)}.movement-document-card>header{display:flex;align-items:center;gap:9px;padding:11px 13px;border-bottom:1px solid var(--erp-border);background:var(--erp-surface-soft)}.movement-document-card>header span{color:var(--erp-accent-hover);font-size:var(--erp-font-size-min);font-weight:800;letter-spacing:.09em}.movement-document-card>header h3{margin:0;color:var(--erp-text);font-size:.96rem}.movement-document-card>header em{margin-left:auto;color:var(--erp-text-muted);font-size:var(--erp-font-size-caption);font-style:normal}.movement-document-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:13px;padding:13px}.movement-context-value,.movement-toggle{display:grid;align-content:start;gap:7px}.movement-context-value span,.movement-toggle span{color:var(--erp-text);font-size:var(--erp-font-size-caption);font-weight:680}.movement-context-value strong{display:flex;align-items:center;min-height:40px;padding:0 12px;border:1px solid var(--erp-border);border-radius:var(--erp-control-radius);background:var(--erp-surface-muted);color:var(--erp-text-secondary);font-size:13px}.movement-toggle{justify-items:start}.movement-dialog__footer{display:flex;align-items:center;justify-content:space-between;gap:16px;width:100%}.movement-dialog__footer>span{color:var(--erp-text-muted);font-size:var(--erp-font-size-caption)}.movement-dialog__footer>div{display:flex;gap:8px}
@media(max-width:900px){.movement-document-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:600px){.movement-document-grid{grid-template-columns:1fr}.movement-dialog__footer{align-items:stretch;flex-direction:column}.movement-dialog__footer>div{justify-content:flex-end;flex-wrap:wrap}}
</style>
