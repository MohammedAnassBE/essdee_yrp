<template>
	<Dialog :visible="visible" modal class="erp-entity-dialog erp-dialog--lg" :header="`Attribute mapping · ${itemName}`" @update:visible="emit('update:visible', $event)">
		<div class="ipd-section-stack">
			<p class="erp-help-text">One line per combination. Same-attribute columns follow the item and are not listed.</p>
			<EntryGrid
				ref="grid"
				title="Mapping lines"
				row-header-label="Line"
				:rows="rows"
				:columns="columns"
				:model-value="model"
				:errors="shownErrors"
				:readonly="readonly"
				:removable-rows="!readonly"
				:toolbar="['fillDown', 'paste', 'clear']"
				@update:model-value="model = $event"
				@remove-row="removeLine"
			/>
			<p v-if="error" class="ipd-grid-notice ipd-grid-notice--error" role="alert"><i class="pi pi-exclamation-circle" aria-hidden="true" />{{ error }}</p>
		</div>
		<template #footer>
			<Button v-if="!readonly" label="Add line" icon="pi pi-plus" text severity="secondary" @click="addLine" />
			<Button label="Cancel" text severity="secondary" @click="emit('update:visible', false)" />
			<Button v-if="!readonly" label="Save mapping" icon="pi pi-save" :loading="saving" :disabled="!rows.length" @click="save" />
		</template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import { computed, inject, ref, watch } from "vue"

import EntryGrid from "../../../../components/common/EntryGrid.vue"
import { IPD_EDITOR_KEY } from "../useIpdEditor.js"
import { attributeValues } from "./attributeValues.js"
import { bomMappingColumns, bomMappingGrid, bomMappingProblems, bomMappingRows } from "./garmentGrids.js"

const props = defineProps({
	visible: { type: Boolean, default: false },
	bomRow: { type: String, default: "" },
	itemName: { type: String, default: "" },
	readonly: { type: Boolean, default: false },
})
const emit = defineEmits(["update:visible"])
const editor = inject(IPD_EDITOR_KEY)
const rows = ref([])
const model = ref({})
const saving = ref(false)
const error = ref("")
const attempted = ref(false)
let lineSequence = 0

const detail = computed(() => editor.context?.bom_mappings?.[props.bomRow] || null)
const columns = computed(() => bomMappingColumns(detail.value, (type, attribute) => type === "item" ? attributeValues(editor, attribute) : []))
const problems = computed(() => bomMappingProblems(detail.value, rows.value, model.value))
const shownErrors = computed(() => attempted.value ? problems.value : {})

watch(() => [props.visible, props.bomRow], () => {
	if (!props.visible) return
	const grid = bomMappingGrid(detail.value)
	rows.value = grid.rows
	model.value = grid.model
	error.value = ""
	attempted.value = false
}, { immediate: true })

function relabel(list) {
	return list.map((row, index) => ({ ...row, label: String(index + 1) }))
}
function addLine() {
	rows.value = relabel([...rows.value, { key: `line-${++lineSequence}`, label: "" }])
}
function removeLine(key) {
	rows.value = relabel(rows.value.filter((row) => row.key !== key))
}
async function save() {
	attempted.value = true
	if (Object.keys(problems.value).length) { error.value = "Fill every value before saving."; return }
	saving.value = true
	error.value = ""
	try {
		await editor.saveBomMapping(props.bomRow, bomMappingRows(detail.value, rows.value, model.value))
		emit("update:visible", false)
	} catch (reason) {
		error.value = reason?.message || "Unable to save this mapping."
	} finally {
		saving.value = false
	}
}
</script>
