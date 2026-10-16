<template>
	<div class="ipd-section-stack">
		<template v-if="part === 'consumption'">
			<IpdGridNotice grid-key="panel_wise_consumption" :empty="!panels.length" section="cutting" field="panel_wise_consumption_matrix_json" />
			<template v-if="panels.length">
				<h3 class="ipd-subhead">
					Consumption per piece
					<small>{{ progress.complete }} / {{ progress.total }} complete</small>
				</h3>
				<div class="ipd-panel-tabs" role="tablist" aria-label="Panel groups">
					<Button
						v-for="panel in panels"
						:key="panel.group_id"
						role="tab"
						:aria-selected="panel.group_id === current?.group_id"
						:label="panel.panel_value"
						size="small"
						:outlined="panel.group_id !== current?.group_id"
						:severity="panel.group_id === current?.group_id ? undefined : 'secondary'"
						@click="active = panel.group_id"
					/>
				</div>
				<div v-if="!editor.readonly && singletons.length > 1" class="ipd-inline-add">
					<IpdChoiceChips label="Group panels cut as one" :choices="singletons" :selected="selectedPanels" @toggle="togglePanel" />
					<Button label="Group selected" icon="pi pi-link" size="small" outlined :disabled="selectedPanels.length < 2" @click="group" />
				</div>
				<EntryGrid
					v-if="current"
					ref="consumptionGrid"
					:title="current.panel_value"
					:unit-hint="grid.unitHint"
					:row-header-label="grid.rowHeaderLabel"
					:rows="grid.rows"
					:columns="grid.columns"
					:model-value="grid.model"
					:readonly="editor.readonly"
					:errors="errors"
					:toolbar="['fillRight', 'fillDown', 'sameForAll', 'paste', 'clear']"
					@update:model-value="update"
				>
					<template #toolbar>
						<Button v-if="!editor.readonly && panelValuesFor(current).length > 1" label="Ungroup" icon="pi pi-link" text severity="secondary" size="small" @click="ungroup" />
					</template>
				</EntryGrid>
				<p v-if="groupError" class="ipd-grid-notice ipd-grid-notice--error" role="alert"><i class="pi pi-exclamation-circle" aria-hidden="true" />{{ groupError }}</p>
			</template>
		</template>
		<template v-if="part === 'mapping'">
			<IpdGridNotice grid-key="panel_wise_cloth_mapping" :empty="!clothPanels.length" />
			<template v-if="clothPanels.length">
				<h3 class="ipd-subhead">Cloth Mapping Matrix</h3>
				<EntryGrid
					v-for="panel in clothPanels"
					:key="panel.group_id || 'all'"
					:ref="(grid) => setClothGrid(panel, grid)"
					:title="panel.panel_value || 'All panels'"
					:row-header-label="clothGrid(panel).rowHeaderLabel"
					:rows="clothGrid(panel).rows"
					:columns="clothGrid(panel).columns"
					:model-value="clothGrid(panel).model"
					:readonly="editor.readonly"
					:toolbar="['fillRight', 'fillDown', 'sameForAll', 'paste', 'clear']"
					@update:model-value="updateCloth(panel.group_id, $event)"
				/>
			</template>
		</template>
	</div>
</template>

<script setup>
import Button from "primevue/button"
import { computed, inject, nextTick, ref } from "vue"

import EntryGrid from "../../../../components/common/EntryGrid.vue"
import { KEY_SEPARATOR } from "../ipdEditor.js"
import { IPD_EDITOR_KEY } from "../useIpdEditor.js"
import {
	COLUMN_SEPARATOR,
	groupPanels,
	panelClothFromModel,
	panelClothGrid,
	panelGroupErrors,
	panelGroupFromModel,
	panelGroupGrid,
	panelProgress,
	panelValuesFor,
	toggleChoice,
	ungroupPanel,
} from "./garmentGrids.js"
import IpdChoiceChips from "./IpdChoiceChips.vue"
import IpdGridNotice from "./IpdGridNotice.vue"

const props = defineProps({ part: { type: String, required: true } })
const editor = inject(IPD_EDITOR_KEY)
const clothGrids = new Map()
function setClothGrid(panel, grid) {
	const key = panel.group_id || 'all'
	if (grid) clothGrids.set(key, grid)
	else clothGrids.delete(key)
}
const consumptionGrid = ref(null)
const active = ref("")
const selectedPanels = ref([])
const groupError = ref("")
const matrix = computed(() => editor.draft.panel_wise_consumption_matrix_json || null)
const clothMatrix = computed(() => editor.draft.panel_wise_cloth_mapping_json || null)
const panels = computed(() => matrix.value?.panels || [])
const clothPanels = computed(() => clothMatrix.value?.panels || [])
const current = computed(() => panels.value.find((panel) => panel.group_id === active.value) || panels.value[0] || null)
const singletons = computed(() => panels.value.filter((panel) => panelValuesFor(panel).length === 1).map((panel) => panelValuesFor(panel)[0]))
const diaOptions = computed(() => editor.grids?.panel_wise_consumption?.dia_values || [])
const grid = computed(() => panelGroupGrid(matrix.value, current.value, { diaOptions: diaOptions.value }))
const errors = computed(() => panelGroupErrors(editor.gridErrors("panel_wise_consumption_matrix_json"), current.value))
const progress = computed(() => panelProgress(matrix.value))

function update(model) {
	editor.setValue("panel_wise_consumption_matrix_json", panelGroupFromModel(matrix.value, current.value.group_id, model))
}
function clothGrid(panel) {
	return panelClothGrid(clothMatrix.value, panel)
}
function updateCloth(groupId, model) {
	editor.setValue("panel_wise_cloth_mapping_json", panelClothFromModel(clothMatrix.value, groupId, model))
}
function togglePanel(panel, on) {
	selectedPanels.value = toggleChoice(singletons.value, selectedPanels.value, panel, on)
}
function restructure(build) {
	groupError.value = ""
	try {
		const result = build()
		editor.setValue("panel_wise_consumption_matrix_json", result.matrix)
		active.value = result.groupId
		selectedPanels.value = []
		editor.refreshGrids(["panel_wise_cloth_mapping"])
	} catch (reason) {
		groupError.value = reason?.message || "Unable to change the panel groups."
	}
}
function group() {
	restructure(() => groupPanels(matrix.value, selectedPanels.value))
}
function ungroup() {
	restructure(() => ungroupPanel(matrix.value, current.value.group_id))
}
async function focusCell(rowKey, column, field) {
	if (field === 'panel_wise_cloth_mapping_json') {
		if (props.part !== 'mapping') return false
		if (rowKey == null) return clothGrids.values().next().value?.focusCell(null, column) || false
		const [groupId, primary] = String(rowKey).split(KEY_SEPARATOR)
		return clothGrids.get(groupId || 'all')?.focusCell(primary, column) || false
	}
	if (props.part !== 'consumption') return false
	if (rowKey == null) {
		active.value = panels.value[0]?.group_id
		await nextTick()
		return consumptionGrid.value?.focusCell(null, column) || false
	}
	const [groupId, primary] = String(rowKey).split(KEY_SEPARATOR)
	if (!panels.value.some((panel) => panel.group_id === groupId)) return false
	active.value = groupId
	await nextTick()
	return consumptionGrid.value?.focusCell(primary, `${column}${COLUMN_SEPARATOR}weight`)
}
defineExpose({ focusCell })
</script>
