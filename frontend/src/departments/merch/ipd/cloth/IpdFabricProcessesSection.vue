<template>
	<IpdSection :section-key="sectionKey">
		<template v-if="!readonly" #actions>
			<Button label="Add process" icon="pi pi-plus" text severity="secondary" size="small" @click="addProcess" />
		</template>
		<div class="ipd-cloth-stack">
			<EntryGrid
				v-if="processes.rows.value.length"
				ref="processGrid" validation-field="fabric_processes"
				:rows="processes.keys.value"
				:columns="PROCESS_COLUMNS"
				:model-value="processes.model.value"
				:readonly="readonly"
				:errors="processes.errors.value"
				title="Fabric Processes"
				meta="Run in sequence order"
				aria-label="Fabric processes"
				row-header-label="#"
				:toolbar="['fillDown', 'paste', 'clear']"
				:removable-rows="!readonly"
				@update:model-value="updateProcesses"
				@remove-row="removeProcessRow"
			/>
			<p v-else class="erp-empty-state erp-empty-state--compact ipd-cloth-empty">No fabric processes. Add knitting first, then dyeing or compacting.</p>
			<EntryGrid
				v-if="mappings.rows.value.length"
				ref="mappingGrid" validation-field="fabric_value_mappings"
				:rows="mappings.keys.value"
				:columns="mappingColumns"
				:model-value="mappings.model.value"
				:readonly="readonly"
				:errors="mappings.errors.value"
				title="Fabric Value Mappings"
				meta="Rows with the same sequence and index form one rule"
				aria-label="Fabric value mappings"
				row-header-label="#"
				:toolbar="['fillDown', 'paste', 'clear']"
				:removable-rows="!readonly"
				@update:model-value="updateMappings"
				@remove-row="mappings.remove"
			>
				<template v-if="!readonly" #toolbar>
					<Button label="Add rule row" icon="pi pi-plus" text severity="secondary" size="small" :disabled="!processes.rows.value.length" @click="addMapping" />
				</template>
			</EntryGrid>
			<Button v-else-if="!readonly && processes.rows.value.length" class="ipd-cloth-add" label="Add what a process changes" icon="pi pi-plus" outlined severity="secondary" size="small" @click="addMapping" />
			<p v-if="orphans" class="ipd-cloth-strip ipd-cloth-strip--error" role="status">
				<i class="pi pi-exclamation-circle" aria-hidden="true" />
				{{ orphans === 1 ? "1 rule row points" : `${orphans} rule rows point` }} to a sequence with no process.
			</p>
		</div>
	</IpdSection>
</template>

<script setup>
import { computed, ref } from "vue"
import Button from "primevue/button"

import EntryGrid from "../../../../components/common/EntryGrid.vue"
import IpdSection from "../IpdSection.vue"
import { applyProcessEdit, modelToRows, newMappingRow, newProcessRow, orphanMappingCount, removeProcess, withStoredOptions } from "./clothGrids.js"
import { useClothSection, useClothTable, useGridFocus } from "./useClothTable.js"
import "./cloth.css"

const props = defineProps({
	sectionKey: { type: String, required: true },
	readonly: { type: Boolean, default: false },
})

const PROCESS_FIELDS = ["sequence", "fabric_process", "input_item", "output_item", "quantity_ratio"]
const PROCESS_COLUMNS = [
	{ key: "sequence", label: "Sequence", type: "number", min: 0, precision: 0 },
	{ key: "fabric_process", label: "Process", type: "link", fieldtype: "Link", link_doctype: "YRP Process", doctype: "YRP Process", filters: { is_cloth_process: 1 } },
	{ key: "input_item", label: "Input Item", type: "link", fieldtype: "Link", link_doctype: "Item", doctype: "Item" },
	{ key: "output_item", label: "Output Item", type: "link", fieldtype: "Link", link_doctype: "Item", doctype: "Item" },
	{ key: "quantity_ratio", label: "Quantity Ratio", type: "number", min: 0 },
]
const MAPPING_FIELDS = ["sequence", "mapping_index", "attribute", "role", "from_value", "to_value"]

const { editor, readonly, cloth } = useClothSection(props)
const processes = useClothTable(editor, "fabric_processes", PROCESS_FIELDS)
const mappings = useClothTable(editor, "fabric_value_mappings", MAPPING_FIELDS)
const processGrid = ref(null)
const mappingGrid = ref(null)

const sequences = computed(() => [...new Set(processes.rows.value.map((row) => row.sequence).filter((value) => value !== null && value !== undefined))])
const attributes = computed(() => withStoredOptions((editor.draft.item_attributes || []).map((row) => row.attribute).filter(Boolean), mappings.rows.value, ["attribute"]))
const mappingColumns = computed(() => [
	{ key: "sequence", label: "Sequence", type: "select", options: withStoredOptions(sequences.value, mappings.rows.value, ["sequence"]) },
	{ key: "mapping_index", label: "Mapping Index", type: "number", min: 0, precision: 0 },
	{ key: "attribute", fieldtype: "Link", link_doctype: "Item Attribute", label: "Attribute", type: "select", options: attributes.value },
	{ key: "role", label: "Role", type: "select", options: cloth.value.mapping_roles || ["Change", "Introduce", "Pin", "Consume"] },
	{ key: "from_value", label: "From Value", type: "text" },
	{ key: "to_value", label: "To Value", type: "text" },
])
const orphans = computed(() => orphanMappingCount(processes.rows.value, mappings.rows.value))

function writeBoth(next) {
	editor.setValues({ fabric_processes: next.processes, fabric_value_mappings: next.mappings })
}

function updateProcesses(model) {
	writeBoth(applyProcessEdit(processes.rows.value, mappings.rows.value, modelToRows(processes.rows.value, model, PROCESS_FIELDS)))
}

function updateMappings(model) {
	writeBoth({ processes: processes.rows.value, mappings: modelToRows(mappings.rows.value, model, MAPPING_FIELDS) })
}

function removeProcessRow(key) {
	writeBoth(removeProcess(processes.rows.value, mappings.rows.value, key))
}

function addProcess() {
	const defaultInput = editor.draft.yarn_ratio_details?.[0]?.yarn_item || ""
	writeBoth({ processes: [...processes.rows.value, newProcessRow(processes.rows.value, { item: editor.draft.item, defaultInput })], mappings: mappings.rows.value })
}

function addMapping() {
	writeBoth({ processes: processes.rows.value, mappings: [...mappings.rows.value, newMappingRow(processes.rows.value, mappings.rows.value)] })
}

useGridFocus(editor, props.sectionKey, {
	fabric_processes: { grid: processGrid, firstRow: () => processes.keys.value[0]?.key, firstColumn: "fabric_process" },
	fabric_value_mappings: { grid: mappingGrid, firstRow: () => mappings.keys.value[0]?.key, firstColumn: "attribute" },
})
</script>

<style scoped>
.ipd-cloth-add {
	justify-self: start;
}
</style>
