<template>
	<IpdSection :section-key="sectionKey" :class="{ 'ipd-packing-details': part === 'details' }">
		<div class="ipd-section-stack">
			<IpdFields :fields="fields" :section="sectionKey" :apply="(fieldname, value) => apply({ [fieldname]: value })" />
			<template v-if="part === 'values'">
				<IpdChoiceChips
					ref="packingValues"
					:label="`${draft.packing_attribute || 'Packing'} values in one box`"
					:choices="packingChoices"
					:selected="selectedValues"
					:readonly="editor.readonly"
					empty-text="Choose a packing attribute with values first."
					@toggle="togglePacking"
				/>
				<template v-if="showQuantities">
					<EntryGrid
						ref="quantityGrid" validation-field="packing_attribute_details"
						title="Packing Attribute Details"
						:meta="`Packing attribute: ${draft.packing_attribute || '—'}`"
						row-header-label="Attribute Value"
						:rows="quantity.rows"
						:columns="QUANTITY_COLUMNS"
						:model-value="quantity.model"
						:readonly="editor.readonly"
						:errors="editor.gridErrors('packing_attribute_details')"
						:toolbar="['fillDown', 'paste', 'clear']"
						totals="row"
						@update:model-value="updateQuantities"
					/>
				</template>
				<p v-else-if="mode === 'colour' && selectedValues.length" class="erp-help-text">Auto calculate is on: quantities are not used and Packing Combo is the pieces per box.</p>
				<div class="ipd-packing-mode">
					<span class="erp-field-label">Packing Mode</span>
					<SelectButton v-if="!editor.readonly" :model-value="mode" :options="PACKING_MODES" option-label="label" option-value="value" :allow-empty="false" size="small" aria-label="Packing mode" @update:model-value="changeMode" />
					<span v-else class="erp-count-badge">{{ modeLabel }}</span>
				</div>
				<template v-if="mode === 'ratio'">
					<IpdGridNotice grid-key="packing_sizes" />
					<EntryGrid
						ref="sizeGrid" validation-field="packing_size_details"
						title="Packing Size Details"
						row-header-label="Size"
						:rows="sizes.rows"
						:columns="SIZE_COLUMNS"
						:model-value="sizes.model"
						:readonly="editor.readonly"
						:errors="editor.gridErrors('packing_size_details')"
						:toolbar="['fillDown', 'paste', 'clear']"
						totals="row"
						@update:model-value="updateSizes"
					/>
				</template>
				<p v-if="mode === 'wise'" class="ipd-grid-notice ipd-grid-notice--ok"><i class="pi pi-check-circle" aria-hidden="true" />Size wise packing: one piece per box.</p>
				<template v-if="mode === 'assortment'">
					<IpdGridNotice grid-key="packing_assortment" :empty="!assortment.rows.length" />
					<EntryGrid
						v-if="assortment.rows.length"
						ref="assortmentGridRef" validation-field="packing_assortment_json"
						title="Box assortment"
						:row-header-label="assortment.rowHeaderLabel"
						:rows="assortment.rows"
						:columns="assortment.columns"
						:model-value="assortment.model"
						:readonly="editor.readonly"
						:toolbar="['fillDown', 'paste', 'clear']"
						@update:model-value="updateAssortment"
					/>
				</template>
			</template>
		</div>
	</IpdSection>
</template>

<script setup>
import SelectButton from "primevue/selectbutton"
import { computed, inject, onBeforeUnmount, onMounted, ref } from "vue"

import EntryGrid from "../../../../components/common/EntryGrid.vue"
import IpdSection from "../IpdSection.vue"
import { IPD_EDITOR_KEY } from "../useIpdEditor.js"
import { assortmentFromModel, assortmentGrid, packingRow, tableFromModel, tableGrid, toggleValueRow } from "./garmentGrids.js"
import IpdChoiceChips from "./IpdChoiceChips.vue"
import IpdFields from "./IpdFields.vue"
import IpdGridNotice from "./IpdGridNotice.vue"
import { PACKING_MODES, isComboDerived, packingChanges, packingModeOf, packingModePatch } from "./packingSection.js"
import { useSectionFocus } from "./sectionFocus.js"
import "./sections.css"

const QUANTITY_COLUMNS = [{ key: "quantity", label: "Quantity", type: "number", min: 0 }]
const SIZE_COLUMNS = [{ key: "quantity", label: "Quantity", type: "number", precision: 0, min: 0 }]

const props = defineProps({
	part: { type: String, required: true },
	sectionKey: { type: String, required: true },
	readonly: { type: Boolean, default: false },
})
const editor = inject(IPD_EDITOR_KEY)
const quantityGrid = ref(null)
const assortmentGridRef = ref(null)
const sizeGrid = ref(null)
const packingValues = ref(null)
const draft = computed(() => editor.draft)
const mode = computed(() => packingModeOf(draft.value))
const modeLabel = computed(() => PACKING_MODES.find((entry) => entry.value === mode.value)?.label || "")
const packingChoices = computed(() => {
	const values = (editor.context?.attributes || []).find((entry) => entry.attribute === draft.value.packing_attribute)?.values || []
	return [...new Set([...values, ...selectedValues.value])]
})
const selectedValues = computed(() => (draft.value.packing_attribute_details || []).map((row) => row.attribute_value))
const showQuantities = computed(() => mode.value === "colour" && !Number(draft.value.auto_calculate) && selectedValues.value.length > 0)
const quantity = computed(() => tableGrid(draft.value.packing_attribute_details, ["quantity"], { keyField: "attribute_value" }))
const sizes = computed(() => tableGrid(draft.value.packing_size_details, ["quantity"], { keyField: "attribute_value" }))
const assortment = computed(() => assortmentGrid(draft.value.packing_assortment_json))
const fields = computed(() => {
	const derived = isComboDerived(draft.value)
	return props.part === 'details' ? [
		{ fieldname: "packing_combo", label: "Packing Combo", fieldtype: "Int", disabled: derived, help: "Pcs per Box" },
		{ fieldname: "packing_attribute_no", label: "Packing Attribute No", fieldtype: "Int", disabled: true, help: "Unique number of attribute values that will be put into a box." },
	] : [{ fieldname: "auto_calculate", label: "Auto Calculate", fieldtype: "Check" }]
})

useSectionFocus(editor, props.sectionKey, { packing_attribute_details: () => quantityGrid.value, packing_size_details: () => sizeGrid.value, packing_assortment_json: () => assortmentGridRef.value }, props.part)
let unregisterValues
onMounted(() => { unregisterValues = editor.registerFocus('packing_values', () => Boolean(draft.value.packing_attribute && packingValues.value?.focus())) })
onBeforeUnmount(() => unregisterValues?.())

function apply(patch) {
	editor.setValues(packingChanges(draft.value, patch))
}
function changeMode(next) {
	if (next && next !== mode.value) apply(packingModePatch(next))
}
function togglePacking(value, on) {
	apply({ packing_attribute_details: toggleValueRow(draft.value.packing_attribute_details, "attribute_value", value, on, packingRow) })
}
function updateQuantities(model) {
	apply({ packing_attribute_details: tableFromModel(draft.value.packing_attribute_details, model, ["quantity"], { keyField: "attribute_value" }).map(zeroBlank) })
}
function updateSizes(model) {
	apply({ packing_size_details: tableFromModel(draft.value.packing_size_details, model, ["quantity"], { keyField: "attribute_value" }).map(zeroBlank) })
}
function zeroBlank(row) {
	return row.quantity === null ? { ...row, quantity: 0 } : row
}
function updateAssortment(model) {
	editor.setValue("packing_assortment_json", assortmentFromModel(draft.value.packing_assortment_json, model))
}
</script>
