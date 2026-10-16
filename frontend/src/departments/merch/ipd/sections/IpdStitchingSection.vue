<template>
	<IpdSection :section-key="sectionKey">
		<div class="ipd-section-stack">
			<template v-if="part === 'items'">
				<IpdChoiceChips
					:label="`${draft.stiching_attribute || 'Panel'} values in one piece`"
					:choices="panelChoices"
					:selected="panels"
					:readonly="editor.readonly"
					empty-text="Choose a stitching attribute with values first."
					@toggle="togglePanel"
				/>
				<EntryGrid
					v-if="panelGrid.rows.length"
					ref="panelGridRef"
					title="Stiching Item Details"
					:meta="isSet ? 'One default panel per part' : ''"
					:row-header-label="draft.stiching_attribute || 'Panel'"
					:rows="panelGrid.rows"
					:columns="panelColumns"
					:model-value="panelGrid.model"
					:readonly="editor.readonly"
					:errors="editor.gridErrors('stiching_item_details')"
					:toolbar="['fillDown', 'paste', 'clear']"
					:removable-rows="!editor.readonly"
					@update:model-value="updatePanels"
					@remove-row="togglePanel($event, false)"
				/>
			</template>
			<IpdFields v-if="part === 'details'" :fields="fields" :section="sectionKey" />
			<template v-if="part === 'combination'">
				<IpdFields :fields="[{ fieldname: 'is_same_packing_attribute', label: 'Is Same Packing Attribute', fieldtype: 'Check' }]" :section="sectionKey" />
				<IpdGridNotice v-if="!isSame" grid-key="stitching_combination" :empty="!combination.rows.length" />
				<EntryGrid
					v-if="combination.rows.length"
					ref="combinationGridRef"
					title="Colour of each panel"
					:meta="isSame ? (isSet ? 'Same as packing colour: each panel takes its part colour' : 'Same as packing colour: each panel takes the row colour') : 'Rows follow the packing colours'"
					:row-header-label="draft.packing_attribute || 'Colour'"
					:rows="combination.rows"
					:columns="combination.columns"
					:model-value="combination.model"
					:readonly="editor.readonly || isSame"
					:errors="editor.gridErrors('stiching_item_detail')"
					:toolbar="['fillRight', 'fillDown', 'paste', 'clear']"
					@update:model-value="updateCombination"
				/>
			</template>
			<template v-if="part === 'bundles' && panels.length">
					<h3 class="ipd-subhead">
						Add Groups
						<small>{{ markers.rows.length ? "Every panel must be in one group" : "No groups" }}</small>
						<Button v-if="!editor.readonly" label="Add group" icon="pi pi-plus" size="small" text @click="addGroup" />
					</h3>
					<EntryGrid
						v-if="markers.rows.length"
						ref="markerGridRef"
						title="Panels cut together"
						row-header-label="Group"
						:rows="markers.rows"
						:columns="markers.columns"
						:model-value="markers.model"
						:readonly="editor.readonly"
						:toolbar="[]"
						:removable-rows="!editor.readonly"
						@update:model-value="updateMarkers"
						@remove-row="removeGroup"
					/>
					<p v-for="problem in markerProblems" :key="problem.message" class="ipd-grid-notice ipd-grid-notice--error" role="alert"><i class="pi pi-exclamation-circle" aria-hidden="true" />{{ problem.message }}</p>
			</template>
		</div>
	</IpdSection>
</template>

<script setup>
import Button from "primevue/button"
import { computed, inject, ref } from "vue"

import EntryGrid from "../../../../components/common/EntryGrid.vue"
import IpdSection from "../IpdSection.vue"
import { IPD_EDITOR_KEY } from "../useIpdEditor.js"
import { attributeValues } from "./attributeValues.js"
import {
	applyDefaultRadio,
	bundleGroupProblems,
	combinationFromModel,
	combinationGrid,
	markerFromModel,
	markerGrid,
	stitchingRow,
	tableFromModel,
	tableGrid,
	toggleValueRow,
} from "./garmentGrids.js"
import IpdChoiceChips from "./IpdChoiceChips.vue"
import IpdFields from "./IpdFields.vue"
import IpdGridNotice from "./IpdGridNotice.vue"
import { useSectionFocus } from "./sectionFocus.js"
import "./sections.css"

const PANEL_FIELDS = ["quantity", "category", "set_item_attribute_value", "is_default"]

const props = defineProps({
	part: { type: String, required: true },
	sectionKey: { type: String, required: true },
	readonly: { type: Boolean, default: false },
})
const editor = inject(IPD_EDITOR_KEY)
const panelGridRef = ref(null)
const combinationGridRef = ref(null)
const markerGridRef = ref(null)
const draft = computed(() => editor.draft)
const isSet = computed(() => Boolean(Number(draft.value.is_set_item)))
const panels = computed(() => (draft.value.stiching_item_details || []).map((row) => row.stiching_attribute_value))
const panelChoices = computed(() => [...new Set([...attributeValues(editor, draft.value.stiching_attribute), ...panels.value])])
const fields = computed(() => [
	{ fieldname: "stiching_major_attribute_value", label: "Stiching Major Attribute Value", fieldtype: "Select", options: panelChoices.value },
])
const panelGrid = computed(() => tableGrid(draft.value.stiching_item_details, PANEL_FIELDS, { keyField: "stiching_attribute_value" }))
const panelColumns = computed(() => [
	{ key: "quantity", label: "Quantity", type: "number", precision: 0, min: 0 },
	{ key: "category", label: "Category", type: "select", options: editor.context?.options?.stitching_categories || [] },
	...(isSet.value ? [
		{ key: "set_item_attribute_value", label: "Set Item Attribute Value", type: "value", options: attributeValues(editor, draft.value.set_item_attribute) },
		{ key: "is_default", label: "Is Default", type: "check" },
	] : []),
])
const isSame = computed(() => Boolean(Number(draft.value.is_same_packing_attribute)))
const combination = computed(() => combinationGrid(isSame.value && !editor.readonly && editor.grids?.stitching_combination ? editor.grids.stitching_combination : draft.value.stiching_item_detail, {
	options: attributeValues(editor, draft.value.packing_attribute), readonlyColumn: draft.value.stiching_major_attribute_value,
}))
const markers = computed(() => markerGrid(draft.value.marker_groups || [], panels.value))
const markerProblems = computed(() => bundleGroupProblems(draft.value.marker_groups || [], panels.value))

useSectionFocus(editor, props.sectionKey, {
	stiching_item_details: () => panelGridRef.value,
	stiching_item_detail: () => combinationGridRef.value,
	marker_groups: () => markerGridRef.value,
}, props.part)

function togglePanel(panel, on) {
	editor.setValue("stiching_item_details", toggleValueRow(draft.value.stiching_item_details, "stiching_attribute_value", panel, on, stitchingRow))
}
function updatePanels(model) {
	const before = draft.value.stiching_item_details || []
	const after = tableFromModel(before, model, PANEL_FIELDS, { keyField: "stiching_attribute_value" })
		.map((row) => ({ ...row, quantity: row.quantity ?? 0, is_default: Number(row.is_default) ? 1 : 0 }))
	editor.setValue("stiching_item_details", applyDefaultRadio(before, after))
}
function updateCombination(model) {
	editor.setValue("stiching_item_detail", combinationFromModel(draft.value.stiching_item_detail, model))
}
function updateMarkers(model) {
	editor.setValue("marker_groups", markerFromModel(draft.value.marker_groups || [], model, panels.value))
}
function addGroup() {
	editor.setValue("marker_groups", [...(draft.value.marker_groups || []), []])
}
function removeGroup(key) {
	editor.setValue("marker_groups", (draft.value.marker_groups || []).filter((_group, index) => `group-${index}` !== key))
}
</script>
