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
						:toolbar="[]"
						:fill-shortcuts="false"
						totals="row"
						@update:model-value="updateQuantities"
					/>
				</template>
				<p v-if="Number(draft.auto_calculate)" class="erp-help-text">Auto calculate is on: quantities are not used and Packing Combo is the pieces per box.</p>
				<IpdFields :fields="mappingFields" :section="sectionKey" :apply="(fieldname, value) => apply({ [fieldname]: value })" />
				<IpdFields v-if="basedOnMapping" class="ipd-packing-mode-fields" :fields="modeFields" :section="sectionKey" :apply="(fieldname, value) => apply({ [fieldname]: value })" />
				<template v-if="basedOnMapping && draft.packing_mode === 'Size Ratio Packing'">
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
						:toolbar="[]"
						:fill-shortcuts="false"
						totals="row"
						@update:model-value="updateSizes"
					/>
				</template>
				<template v-if="basedOnMapping && !draft.packing_mode">
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
						:toolbar="[]"
						:fill-shortcuts="false"
						@update:model-value="updateAssortment"
					/>
				</template>
			</template>
		</div>
	</IpdSection>
</template>

<script setup>
import { computed, inject, onBeforeUnmount, onMounted, ref } from "vue"

import EntryGrid from "../../../../components/common/EntryGrid.vue"
import IpdSection from "../IpdSection.vue"
import { IPD_EDITOR_KEY } from "../useIpdEditor.js"
import { assortmentFromModel, assortmentGrid, packingRow, tableFromModel, tableGrid } from "./garmentGrids.js"
import IpdChoiceChips from "./IpdChoiceChips.vue"
import IpdFields from "./IpdFields.vue"
import IpdGridNotice from "./IpdGridNotice.vue"
import { isComboDerived, packingChanges } from "./packingSection.js"
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
const basedOnMapping = computed(() => Boolean(Number(draft.value.based_on_other_attribute_mapping)))
const mappingFields = [{ fieldname: "based_on_other_attribute_mapping", label: "Based on Other Attribute Mapping", fieldtype: "Check" }]
const modeFields = computed(() => {
	const stored = editor.fields?.packing_mode
	const options = editor.context?.packing_modes ?? editor.context?.options?.packing_modes ?? stored?.options ?? ["", "Size Ratio Packing", "Size Wise Packing"]
	return [{
		fieldname: "packing_mode", label: "Packing Mode", fieldtype: "Select",
		options: ["", ...(Array.isArray(options) ? options : options.split("\n")).filter(Boolean)],
		// FormField renders the metadata description itself; use help only for the fallback.
		help: stored?.description ? "" : "Size Ratio Packing: one box mixes sizes in a ratio that sums to Packing Combo. Size Wise Packing: each size is packed in its own box with its own pieces per box.",
	}]
})
const packingChoices = computed(() => {
	const values = (editor.context?.attributes || []).find((entry) => entry.attribute === draft.value.packing_attribute)?.values || []
	return [...new Set([...values, ...selectedValues.value])]
})
const selectedValues = computed(() => (draft.value.packing_attribute_details || []).map((row) => row.attribute_value))
const showQuantities = computed(() => !Number(draft.value.auto_calculate) && selectedValues.value.length > 0)
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
	const changes = packingChanges(draft.value, patch)
	if (Object.hasOwn(patch, "based_on_other_attribute_mapping")) {
		// Desk has no checkbox handler: preserve stored size rows until the mode changes.
		for (const [fieldname, value] of Object.entries(changes)) {
			editor.setValue(fieldname, value, { skipGrids: new Set(["packing_sizes"]) })
		}
	} else {
		editor.setValues(changes)
	}
}
function togglePacking(value, on) {
	apply({ packing_attribute_details: editor.toggledRows("packing_attribute_details", "attribute_value", value, on, packingRow) })
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

<style scoped>
/* Match one Packing Details column, including the shared field grid's gap. */
.ipd-packing-mode-fields.ipd-fields {
	grid-template-columns: repeat(2, minmax(0, 1fr));
}

@media (max-width: 620px) {
	.ipd-packing-mode-fields.ipd-fields {
		grid-template-columns: minmax(0, 1fr);
	}
}
</style>
