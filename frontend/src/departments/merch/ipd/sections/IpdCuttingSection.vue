<template>
	<IpdSection :section-key="sectionKey">
		<div class="ipd-section-stack">
			<template v-if="part === 'cloths'">
				<h3 class="ipd-subhead">
					<small>Names are used in the cloth and accessory grids</small>
					<Button v-if="!editor.readonly" label="Add cloth" icon="pi pi-plus" size="small" text @click="addCloth" />
				</h3>
				<EntryGrid
					v-if="cloths.rows.length"
					ref="clothGrid" validation-field="cloth_detail"
					title="Cloth Detail"
					row-header-label="#"
					:rows="cloths.rows"
					:columns="CLOTH_COLUMNS"
					:model-value="cloths.model"
					:readonly="editor.readonly"
					:errors="editor.gridErrors('cloth_detail')"
					:toolbar="[]"
					:fill-shortcuts="false"
					:removable-rows="!editor.readonly"
					@update:model-value="updateCloths"
					@remove-row="removeCloth"
				/>
				<p v-else class="erp-help-text">No cloths yet.</p>
				<p v-if="duplicates.length" class="ipd-grid-notice ipd-grid-notice--error" role="alert"><i class="pi pi-exclamation-circle" aria-hidden="true" />Cloth names must be unique: {{ duplicates.join(", ") }}</p>
			</template>
			<IpdFields v-if="part === 'consumption'" :fields="fields" :section="sectionKey" />
			<IpdPanelWiseGrids v-if="panelWise && part !== 'cloths'" ref="panelGrids" :part="part" />
			<template v-if="part === 'consumption' && !panelWise">
				<div id="ipd-edit-cutting_attributes" tabindex="-1" aria-label="Cutting attributes">
					<IpdChoiceChips label="Cutting attributes" :choices="choices" :selected="draft.cutting_attributes || []" :readonly="editor.readonly" empty-text="Set the stitching in stage and the dependent attribute to choose cutting attributes." @toggle="(value, on) => toggleList('cutting_attributes', value, on)" />
				</div>
				<IpdGridNotice grid-key="cutting_items" :empty="!cutting.rows.length" section="cutting" field="cutting_items_json" />
				<EntryGrid
					v-if="cutting.rows.length"
					ref="cuttingGrid" validation-field="cutting_items_json"
					title="Consumption per piece"
					unit-hint="Dia · weight kg"
					:row-header-label="cutting.rowHeaderLabel"
					:rows="cutting.rows"
					:columns="cutting.columns"
					:model-value="cutting.model"
					:readonly="editor.readonly"
					:errors="editor.gridErrors('cutting_items_json')"
					:toolbar="[]"
					:fill-shortcuts="false"
					@update:model-value="updateItems('cutting_items_json', CUTTING_CARRY, $event)"
				/>
			</template>
			<template v-if="part === 'mapping' && !panelWise">
				<div id="ipd-edit-cloth_attributes" tabindex="-1" aria-label="Cloth attributes">
					<IpdChoiceChips label="Cloth attributes" :choices="clothChoices" :selected="draft.cloth_attributes || []" :readonly="editor.readonly" @toggle="(value, on) => toggleList('cloth_attributes', value, on)" />
				</div>
				<IpdGridNotice grid-key="cutting_cloths" :empty="!clothItems.rows.length" section="cutting" field="cutting_cloths_json" />
				<EntryGrid
					v-if="clothItems.rows.length"
					ref="clothItemsGrid" validation-field="cutting_cloths_json"
					title="Cloth by combination"
					:row-header-label="clothItems.rowHeaderLabel"
					:rows="clothItems.rows"
					:columns="clothItems.columns"
					:model-value="clothItems.model"
					:readonly="editor.readonly"
					:errors="editor.gridErrors('cutting_cloths_json')"
					:toolbar="[]"
					:fill-shortcuts="false"
					@update:model-value="updateItems('cutting_cloths_json', CLOTH_CARRY, $event)"
				/>
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
import { clothNames } from "./attributeValues.js"
import { clothDetailChanges, duplicateClothNames } from "./clothRename.js"
import { choiceList, itemsFromModel, itemsGrid, removeTableRow, tableFromModel, tableGrid, toggleChoice } from "./garmentGrids.js"
import IpdChoiceChips from "./IpdChoiceChips.vue"
import IpdFields from "./IpdFields.vue"
import IpdGridNotice from "./IpdGridNotice.vue"
import IpdPanelWiseGrids from "./IpdPanelWiseGrids.vue"
import { useSectionFocus } from "./sectionFocus.js"
import "./sections.css"

const CUTTING_CARRY = ["Dia", "Weight", "Required GSM"]
const CLOTH_CARRY = ["Cloth"]
const CLOTH_FIELDS = ["name1", "cloth", "required_gsm", "is_bom_item"]
const CLOTH_COLUMNS = [
	{ key: "name1", label: "Name", type: "text" },
	{ key: "cloth", label: "Cloth", type: "link", fieldtype: "Link", link_doctype: "Item", doctype: "Item" },
	{ key: "required_gsm", label: "Required GSM", type: "number", min: 0 },
	{ key: "is_bom_item", label: "Is BOM Item", type: "check" },
]

const props = defineProps({
	part: { type: String, required: true },
	sectionKey: { type: String, required: true },
	readonly: { type: Boolean, default: false },
})
const editor = inject(IPD_EDITOR_KEY)
const clothGrid = ref(null)
const cuttingGrid = ref(null)
const clothItemsGrid = ref(null)
const panelGrids = ref(null)
const draft = computed(() => editor.draft)
const panelWise = computed(() => Boolean(Number(draft.value.enable_panel_wise_consumption_matrix)))
const fields = computed(() => [
	{ fieldname: "enable_panel_wise_consumption_matrix", label: "Enable Panel-wise Consumption Matrix", fieldtype: "Check" },
])
const choices = computed(() => choiceList(editor.context?.cutting_attribute_choices || [], draft.value.cutting_attributes))
const clothChoices = computed(() => choiceList(editor.context?.cutting_attribute_choices || [], draft.value.cloth_attributes))
const cloths = computed(() => tableGrid(draft.value.cloth_detail, CLOTH_FIELDS))
const duplicates = computed(() => duplicateClothNames(draft.value.cloth_detail))
const cutting = computed(() => itemsGrid(draft.value.cutting_items_json, CUTTING_CARRY, { attributeColumns: true, diaOptions: editor.context?.cutting?.dia_values || [] }))
const clothItems = computed(() => itemsGrid(draft.value.cutting_cloths_json, CLOTH_CARRY, { attributeColumns: true, clothOptions: clothNames(draft.value) }))

useSectionFocus(editor, props.sectionKey, {
	cloth_detail: () => clothGrid.value,
	cutting_items_json: () => cuttingGrid.value,
	cutting_cloths_json: () => clothItemsGrid.value,
	panel_wise_consumption_matrix_json: () => panelGrids.value,
	panel_wise_cloth_mapping_json: () => panelGrids.value,
}, props.part)

function toggleList(fieldname, value, on) {
	const all = fieldname === "cutting_attributes" ? choices.value : clothChoices.value
	editor.setValue(fieldname, toggleChoice(all, draft.value[fieldname], value, on))
}
function updateCloths(model) {
	const rows = tableFromModel(draft.value.cloth_detail, model, CLOTH_FIELDS)
		.map((row) => ({ ...row, required_gsm: row.required_gsm ?? 0, is_bom_item: Number(row.is_bom_item) ? 1 : 0 }))
	editor.setValues(clothDetailChanges(draft.value, rows))
}
function addCloth() {
	editor.setValue("cloth_detail", [...(draft.value.cloth_detail || []), { name1: null, cloth: null, required_gsm: 0, is_bom_item: 0 }])
}
function removeCloth(key) {
	editor.setValue("cloth_detail", removeTableRow(draft.value.cloth_detail, key))
}
function updateItems(fieldname, carry, model) {
	editor.setValue(fieldname, itemsFromModel(draft.value[fieldname], model, carry))
}
</script>
