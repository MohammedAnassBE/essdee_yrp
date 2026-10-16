<template>
	<IpdSection :section-key="sectionKey">
		<template #actions>
			<Button v-if="part === 'general' && !editor.readonly" label="Add process" icon="pi pi-plus" size="small" outlined @click="addProcess" />
		</template>
		<div class="ipd-section-stack">
			<template v-if="part === 'general'">
				<EntryGrid
					v-if="processes.rows.length"
					ref="processGrid" validation-field="ipd_processes"
					title="IPD Processes"
					row-header-label="#"
					:rows="processes.rows"
					:columns="processColumns"
					:model-value="processes.model"
					:readonly="editor.readonly"
					:errors="editor.gridErrors('ipd_processes')"
					:toolbar="[]"
					:fill-shortcuts="false"
					:removable-rows="!editor.readonly"
					@update:model-value="updateProcesses"
					@remove-row="removeProcess"
				/>
				<p v-else class="erp-help-text">No processes yet.</p>
				<p v-if="stageMismatches && !editor.readonly" class="ipd-grid-notice ipd-grid-notice--warning" role="status">
					<i class="pi pi-exclamation-triangle" aria-hidden="true" />
					<span>{{ stageMismatches }} {{ stageMismatches === 1 ? "row has" : "rows have" }} a different out stage from an older version. Stage shows the in stage.</span>
					<Button label="Use it for both" size="small" text @click="syncStages" />
				</p>
			</template>
			<template v-if="part === 'embellishment'">
				<EntryGrid
					v-if="embellishment.rows.length"
					ref="embellishmentGridRef" validation-field="emblishment_details_json"
					title="Embellishment"
					row-header-label="Process"
					:rows="embellishment.rows"
					:columns="embellishment.columns"
					:model-value="embellishment.model"
					:readonly="editor.readonly"
					:toolbar="[]"
					:fill-shortcuts="false"
					:removable-rows="!editor.readonly"
					@update:model-value="updateEmbellishment"
					@remove-row="removeEmbellishmentProcess"
				/>
				<p v-else class="erp-help-text">No embellishment.</p>
				<p v-if="embellishment.rows.length" class="erp-help-text">Embellishment processes use the stitching in stage when saved.</p>
				<p v-if="orphanProcess" class="ipd-grid-notice" role="status">
					<i class="pi pi-info-circle" aria-hidden="true" />
					<span>{{ orphanProcess }} still has a row in Processes.</span>
					<Button label="Remove that row too" size="small" text @click="removeOrphan" />
				</p>
				<div v-if="!editor.readonly" class="ipd-inline-add">
					<LinkField v-model="newEmbellishment" doctype="YRP Process" placeholder="Embellishment process" aria-label="Embellishment process" input-id="ipd-edit-new-embellishment" :show-open-button="false" />
					<Button label="Add embellishment" icon="pi pi-plus" size="small" outlined :disabled="!newEmbellishment || newEmbellishment in (draft.emblishment_details_json || {})" @click="addEmbellishmentProcess" />
				</div>
				<p v-if="error" class="ipd-grid-notice ipd-grid-notice--error" role="alert"><i class="pi pi-exclamation-circle" aria-hidden="true" />{{ error }}</p>
			</template>
			<details v-if="part === 'general' && migrated.length">
				<summary class="ipd-subhead">Migrated process rows <small>{{ migrated.length }}</small></summary>
				<table class="ipd-simple-table">
					<thead><tr><th scope="col">Process</th><th scope="col">Stage</th></tr></thead>
					<tbody><tr v-for="(row, index) in migrated" :key="row.name || index"><td>{{ row.process_name || "—" }}</td><td>{{ row.stage || "—" }}</td></tr></tbody>
				</table>
			</details>
		</div>
	</IpdSection>
</template>

<script setup>
import Button from "primevue/button"
import { computed, inject, ref } from "vue"

import EntryGrid from "../../../../components/common/EntryGrid.vue"
import LinkField from "../../../../components/common/LinkField.vue"
import IpdSection from "../IpdSection.vue"
import { IPD_EDITOR_KEY } from "../useIpdEditor.js"
import { attributeValues } from "./attributeValues.js"
import { addEmbellishment, embellishmentFromModel, embellishmentGrid, hasStageMismatch, processRowsFromModel, removeEmbellishment, removeTableRow, syncProcessStages, tableGrid } from "./garmentGrids.js"
import { useSectionFocus } from "./sectionFocus.js"
import "./sections.css"

const PROCESS_FIELDS = ["process_name", "process_item", "in_stage"]

const props = defineProps({
	part: { type: String, required: true },
	sectionKey: { type: String, required: true },
	readonly: { type: Boolean, default: false },
})
const editor = inject(IPD_EDITOR_KEY)
const processGrid = ref(null)
const embellishmentGridRef = ref(null)
const newEmbellishment = ref("")
const orphanProcess = ref("")
const error = ref("")
const draft = computed(() => editor.draft)
const stages = computed(() => editor.context?.stage_values || [])
const panels = computed(() => attributeValues(editor, draft.value.stiching_attribute))
const processes = computed(() => tableGrid(draft.value.ipd_processes, PROCESS_FIELDS))
const processColumns = computed(() => [
	{ key: "process_name", label: "Process", type: "link", doctype: "YRP Process" },
	{ key: "process_item", label: "Process Item", type: "link", doctype: "Item" },
	{ key: "in_stage", label: "Stage", type: "value", options: stages.value },
])
const stageMismatches = computed(() => (draft.value.ipd_processes || []).filter(hasStageMismatch).length)
const embellishment = computed(() => embellishmentGrid(draft.value.emblishment_details_json || {}, panels.value))
const migrated = computed(() => Array.isArray(draft.value.original_process_rows) ? draft.value.original_process_rows : [])

useSectionFocus(editor, props.sectionKey, { ipd_processes: () => processGrid.value, emblishment_details_json: () => embellishmentGridRef.value }, props.part)

function updateProcesses(model) {
	editor.setValue("ipd_processes", processRowsFromModel(draft.value.ipd_processes || [], model, PROCESS_FIELDS))
}
function syncStages() {
	editor.setValue("ipd_processes", syncProcessStages(draft.value.ipd_processes))
}
function addProcess() {
	editor.setValue("ipd_processes", [...(draft.value.ipd_processes || []), { process_name: null, process_item: null, in_stage: null, out_stage: null }])
}
function removeProcess(key) {
	editor.setValue("ipd_processes", removeTableRow(draft.value.ipd_processes, key))
}
function updateEmbellishment(model) {
	editor.setValue("emblishment_details_json", embellishmentFromModel(draft.value.emblishment_details_json || {}, model, panels.value))
}
function addEmbellishmentProcess() {
	error.value = ""
	try {
		editor.setValue("emblishment_details_json", addEmbellishment(draft.value.emblishment_details_json, newEmbellishment.value, panels.value))
		newEmbellishment.value = ""
	} catch (reason) {
		error.value = reason.message
	}
}
function removeEmbellishmentProcess(process) {
	editor.setValue("emblishment_details_json", removeEmbellishment(draft.value.emblishment_details_json, process))
	orphanProcess.value = (draft.value.ipd_processes || []).some((row) => row.process_name === process) ? process : ""
}
function removeOrphan() {
	editor.setValue("ipd_processes", (draft.value.ipd_processes || []).filter((row) => row.process_name !== orphanProcess.value))
	orphanProcess.value = ""
}
</script>
