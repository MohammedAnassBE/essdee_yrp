<template>
	<IpdSection :section-key="sectionKey">
		<template #actions>
			<Button v-if="part === 'bom' && !editor.readonly" label="Add row" icon="pi pi-plus" size="small" outlined @click="addBom" />
		</template>
		<div class="ipd-section-stack">
			<template v-if="part === 'bom'">
				<EntryGrid
					v-if="bom.rows.length"
					ref="bomGrid" validation-field="item_bom"
					title="Item BOM"
					row-header-label="#"
					:rows="bom.rows"
					:columns="bomColumns"
					:model-value="bom.model"
					:readonly="editor.readonly"
					:errors="editor.gridErrors('item_bom')"
					:toolbar="[]"
					:fill-shortcuts="false"
					:removable-rows="!editor.readonly"
					@update:model-value="updateBom"
					@remove-row="removeBom"
				/>
				<p v-else class="erp-help-text">No BOM rows yet.</p>
				<div v-if="mapped.length" class="ipd-chip-cards" aria-label="Attribute mapped BOM rows">
					<article v-for="entry in mapped" :key="entry.key" class="ipd-chip-card">
						<header>
							<h3>{{ entry.item }} Mapping</h3>
							<Button v-if="entry.canEdit" :label="editor.readonly ? 'View' : 'Edit'" size="small" text @click="openMapping(entry)" />
						</header>
						<p v-for="(line, index) in entry.lines" :key="index" class="erp-help-text bom-mapping-line">{{ line }}</p>
						<small v-if="entry.total > entry.lines.length" class="erp-help-text">+{{ entry.total - entry.lines.length }} more</small>
						<small v-if="entry.note" class="erp-help-text">{{ entry.note }}</small>
					</article>
				</div>
			</template>
			<template v-if="part === 'accessories'">
				<p v-if="!accessoryNames.rows.length && !clothAccessory.rows.length" class="erp-help-text">No accessory items.</p>
				<EntryGrid
					v-if="accessoryNames.rows.length"
					ref="accessoryNamesGrid" validation-field="accessory_clothtype_json"
					title="Accessory names"
					row-header-label="Accessory"
					:rows="accessoryNames.rows"
					:columns="accessoryNames.columns"
					:model-value="accessoryNames.model"
					:readonly="editor.readonly"
					:toolbar="[]"
					:fill-shortcuts="false"
					:removable-rows="!editor.readonly"
					@update:model-value="updateAccessoryParts"
					@remove-row="removeAccessory"
				/>
				<div v-if="!editor.readonly" class="ipd-inline-add">
					<InputText v-model="newAccessory" placeholder="Accessory name" aria-label="Accessory name" @keydown.enter.prevent="addAccessory" />
					<Select v-if="isSet" v-model="newPart" :options="setParts" :placeholder="draft.set_item_attribute || 'Part'" :aria-label="draft.set_item_attribute || 'Part'" />
					<Button label="Add accessory" icon="pi pi-plus" size="small" outlined :disabled="!canAddAccessory" @click="addAccessory" />
				</div>
				<IpdChoiceChips v-if="accessoryNames.rows.length" label="Accessory attributes" :choices="accessoryChoices" :selected="draft.accessory_attributes || []" :readonly="editor.readonly" @toggle="toggleAccessoryAttribute" />
				<IpdGridNotice grid-key="cloth_accessory" :empty="!clothAccessory.rows.length" section="accessories" field="cloth_accessory_json" :detail="clothAccessoryValidation.summary" />
				<EntryGrid
					v-if="clothAccessory.rows.length"
					ref="clothAccessoryGrid" validation-field="cloth_accessory_json"
					title="Accessory consumption"
					:row-header-label="clothAccessory.rowHeaderLabel"
					:rows="clothAccessory.rows"
					:columns="clothAccessory.columns"
					:model-value="clothAccessory.model"
					:readonly="editor.readonly"
					:errors="clothAccessoryValidation.errors"
					:toolbar="[]"
					:fill-shortcuts="false"
					@update:model-value="updateClothAccessory"
				/>
			</template>
			<template v-if="part === 'stitching'">
				<p v-if="!stitchingAccessory.rows.length" class="erp-help-text">Accessory colours appear after accessory items are added.</p>
				<IpdGridNotice grid-key="stiching_accessory" :empty="!stitchingAccessory.rows.length" section="accessories" field="stiching_accessory_json" :detail="stitchingAccessoryValidation.summary" />
				<EntryGrid
					v-if="stitchingAccessory.rows.length"
					ref="stitchingAccessoryRef" validation-field="stiching_accessory_json"
					title="Accessory colour and cloth"
					:row-header-label="stitchingAccessory.rowHeaderLabel"
					:rows="stitchingAccessory.rows"
					:columns="stitchingAccessory.columns"
					:model-value="stitchingAccessory.model"
					:readonly="editor.readonly"
					:errors="stitchingAccessoryValidation.errors"
					:toolbar="[]"
					:fill-shortcuts="false"
					@update:model-value="updateStitchingAccessory"
				/>
			</template>
		</div>
		<BomMappingDialog v-model:visible="mappingVisible" :bom-row="mappingRow" :item-name="mappingItem" :readonly="editor.readonly" />
	</IpdSection>
</template>

<script setup>
import Button from "primevue/button"
import InputText from "primevue/inputtext"
import Select from "primevue/select"
import { computed, inject, ref } from "vue"

import EntryGrid from "../../../../components/common/EntryGrid.vue"
import IpdSection from "../IpdSection.vue"
import { IPD_EDITOR_KEY } from "../useIpdEditor.js"
import { attributeValues, clothNames } from "./attributeValues.js"
import BomMappingDialog from "./BomMappingDialog.vue"
import { mappingCardLines } from "./bomMapping.js"
import {
	choiceList,
	itemsFromModel,
	itemsGrid,
	missingCellErrors,
	removeTableRow,
	stitchingAccessoryFromModel,
	stitchingAccessoryGrid,
	tableFromModel,
	tableGrid,
	toggleChoice,
} from "./garmentGrids.js"
import IpdChoiceChips from "./IpdChoiceChips.vue"
import IpdGridNotice from "./IpdGridNotice.vue"
import { useSectionFocus } from "./sectionFocus.js"
import "./sections.css"

const BOM_FIELDS = ["item", "process_name", "qty_of_product", "qty_of_bom_item", "uom", "dependent_attribute_value", "based_on_attribute_mapping", "wastage_pct"]
const BOM_WRITABLE = BOM_FIELDS.filter((field) => field !== "uom")
const ACCESSORY_CARRY = ["Dia", "Weight"]

const props = defineProps({
	part: { type: String, required: true },
	sectionKey: { type: String, required: true },
	readonly: { type: Boolean, default: false },
})
const editor = inject(IPD_EDITOR_KEY)
const bomGrid = ref(null)
const accessoryNamesGrid = ref(null)
const clothAccessoryGrid = ref(null)
const stitchingAccessoryRef = ref(null)
const newAccessory = ref("")
const newPart = ref(null)
const mappingVisible = ref(false)
const mappingRow = ref("")
const mappingItem = ref("")
const draft = computed(() => editor.draft)
const isSet = computed(() => Boolean(Number(draft.value.is_set_item)))
const setParts = computed(() => attributeValues(editor, draft.value.set_item_attribute))
const bom = computed(() => tableGrid(draft.value.item_bom, BOM_FIELDS))
const bomColumns = computed(() => [
	{ key: "item", label: "Item", type: "link", doctype: "Item", filters: { disabled: 0 } },
	{ key: "process_name", label: "Process Name", type: "link", doctype: "YRP Process" },
	...(draft.value.dependent_attribute ? [{ key: "dependent_attribute_value", label: "Dependent Attribute Value", type: "value", options: editor.context?.stage_values || [] }] : []),
	{ key: "qty_of_product", label: "Qty of Product", type: "number", min: 0 },
	{ key: "qty_of_bom_item", label: "Qty of BOM Item", type: "number", min: 0 },
	{ key: "uom", label: "UOM", type: "text", readonly: true },
	{ key: "based_on_attribute_mapping", label: "Based on Attribute Mapping", type: "check" },
	{ key: "wastage_pct", label: "Wastage %", type: "number", min: 0 },
])
const mapped = computed(() => (draft.value.item_bom || []).filter((row) => Number(row.based_on_attribute_mapping)).map((row, index) => {
	const detail = row.name ? editor.context?.bom_mappings?.[row.name] : null
	const note = !detail ? "Save the IPD to create this mapping" : detail.is_shared ? "Shared with another document" : ""
	return { key: row.name || `new:${index}`, name: row.name, item: row.item || "New row", ...mappingCardLines(detail), canEdit: Boolean(detail) && (!detail.is_shared || editor.readonly), note }
}))
const accessoryNames = computed(() => {
	const entries = Object.entries(draft.value.accessory_clothtype_json || {})
	return {
		rows: entries.map(([name]) => ({ key: name, label: name })),
		columns: isSet.value ? [{ key: "part", label: draft.value.set_item_attribute || "Part", type: "value", options: setParts.value }] : [{ key: "part", label: "Part", type: "text", readonly: true }],
		model: Object.fromEntries(entries.map(([name, part]) => [name, { part }])),
	}
})
const canAddAccessory = computed(() => Boolean(newAccessory.value) && !(newAccessory.value in (draft.value.accessory_clothtype_json || {})) && (!isSet.value || Boolean(newPart.value)))
const accessoryChoices = computed(() => choiceList(editor.context?.cutting_attribute_choices || [], draft.value.accessory_attributes))
const clothAccessory = computed(() => itemsGrid(draft.value.cloth_accessory_json, ACCESSORY_CARRY, { attributeColumns: true, diaOptions: editor.context?.cutting?.dia_values || [] }))
const clothAccessoryValidation = computed(() => missingCellErrors(clothAccessory.value, editor.gridErrors("cloth_accessory_json")))
const stitchingAccessory = computed(() => stitchingAccessoryGrid(draft.value.stiching_accessory_json, {
	colourOptions: attributeValues(editor, draft.value.packing_attribute), clothOptions: clothNames(draft.value),
}))
const stitchingAccessoryValidation = computed(() => missingCellErrors(stitchingAccessory.value, editor.gridErrors("stiching_accessory_json"), (value, column) => (
	column.key === "cloth_type" && !clothNames(draft.value).includes(value) ? "Choose a cloth from Cloth Details" : false
)))

useSectionFocus(editor, props.sectionKey, {
	item_bom: () => bomGrid.value,
	accessory_clothtype_json: () => accessoryNamesGrid.value,
	cloth_accessory_json: () => clothAccessoryGrid.value,
	stiching_accessory_json: () => stitchingAccessoryRef.value,
}, props.part)

function updateBom(model) {
	const rows = tableFromModel(draft.value.item_bom, model, BOM_WRITABLE).map((row) => ({
		...row,
		qty_of_product: row.qty_of_product ?? 0,
		qty_of_bom_item: row.qty_of_bom_item ?? 0,
		wastage_pct: row.wastage_pct ?? 0,
		based_on_attribute_mapping: Number(row.based_on_attribute_mapping) ? 1 : 0,
	}))
	editor.setValue("item_bom", rows)
}
function addBom() {
	editor.setValue("item_bom", [...(draft.value.item_bom || []), { item: null, process_name: null, qty_of_product: 1, qty_of_bom_item: 1, dependent_attribute_value: null, based_on_attribute_mapping: 0, wastage_pct: 0 }])
}
function removeBom(key) {
	editor.setValue("item_bom", removeTableRow(draft.value.item_bom, key))
}
function openMapping(entry) {
	mappingRow.value = entry.name
	mappingItem.value = entry.item
	mappingVisible.value = true
}
function addAccessory() {
	if (!canAddAccessory.value) return
	editor.setValue("accessory_clothtype_json", { ...(draft.value.accessory_clothtype_json || {}), [newAccessory.value]: isSet.value ? newPart.value : null })
	newAccessory.value = ""
	newPart.value = null
}
function removeAccessory(name) {
	editor.setValue("accessory_clothtype_json", Object.fromEntries(Object.entries(draft.value.accessory_clothtype_json || {}).filter(([key]) => key !== name)))
}
function updateAccessoryParts(model) {
	editor.setValue("accessory_clothtype_json", Object.fromEntries(Object.entries(draft.value.accessory_clothtype_json || {}).map(([name, part]) => [name, name in model ? model[name]?.part ?? null : part])))
}
function toggleAccessoryAttribute(value, on) {
	editor.setValue("accessory_attributes", toggleChoice(accessoryChoices.value, draft.value.accessory_attributes, value, on))
}
function updateClothAccessory(model) {
	editor.setValue("cloth_accessory_json", itemsFromModel(draft.value.cloth_accessory_json, model, ACCESSORY_CARRY))
}
function updateStitchingAccessory(model) {
	editor.setValue("stiching_accessory_json", stitchingAccessoryFromModel(draft.value.stiching_accessory_json, model))
}
</script>

<style scoped>
.bom-mapping-line { margin: 0; overflow-wrap: anywhere; }
</style>
