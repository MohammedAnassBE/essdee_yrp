<template>
	<IpdSection :section-key="sectionKey">
		<template #actions>
			<label v-if="!editor.readonly" class="ipd-toggle">
				<ToggleSwitch :model-value="isOn" input-id="ipd-edit-is_set_item" @update:model-value="toggle" />
				<span>Is Set Item</span>
			</label>
		</template>
		<p v-if="editor.readonly" id="ipd-edit-is_set_item" class="erp-help-text" tabindex="-1">Is Set Item: {{ isOn ? "Yes" : "No" }}</p>
		<div v-if="isOn" class="ipd-section-stack">
			<IpdFields :fields="fields" :section="sectionKey" />
			<IpdGridNotice grid-key="set_combination" :empty="!grid.rows.length" section="set_item" field="set_item_detail" />
			<EntryGrid
				v-if="grid.rows.length"
				ref="setGrid" validation-field="set_item_detail"
				title="Colour of each part"
				meta="Rows follow the packing colours"
				:row-header-label="draft.packing_attribute || 'Colour'"
				:rows="grid.rows"
				:columns="grid.columns"
				:model-value="grid.model"
				:readonly="editor.readonly"
				:errors="editor.gridErrors('set_item_detail')"
				:toolbar="['fillRight', 'fillDown', 'paste', 'clear']"
				@update:model-value="update"
			/>
			<p v-else-if="!draft.major_attribute_value" class="erp-help-text">Choose the set attribute and its major part to build the colour grid.</p>
		</div>
		<p v-else class="erp-help-text">{{ offReason }}</p>
	</IpdSection>
</template>

<script setup>
import ToggleSwitch from "primevue/toggleswitch"
import { computed, inject, ref } from "vue"

import EntryGrid from "../../../../components/common/EntryGrid.vue"
import IpdSection from "../IpdSection.vue"
import { IPD_EDITOR_KEY } from "../useIpdEditor.js"
import { attributeNames, attributeValues } from "./attributeValues.js"
import { combinationFromModel, combinationGrid } from "./garmentGrids.js"
import IpdFields from "./IpdFields.vue"
import IpdGridNotice from "./IpdGridNotice.vue"
import { useSectionFocus } from "./sectionFocus.js"
import "./sections.css"

const props = defineProps({
	sectionKey: { type: String, required: true },
	readonly: { type: Boolean, default: false },
})
const editor = inject(IPD_EDITOR_KEY)
const setGrid = ref(null)
const draft = computed(() => editor.draft)
const isOn = computed(() => Boolean(Number(draft.value.is_set_item)))
const offReason = "Off. This style is not sold as a set."
const fields = computed(() => [
	{ fieldname: "set_item_attribute", label: "Set Item Attribute", fieldtype: "Select", options: attributeNames(draft.value), required: true },
	{ fieldname: "major_attribute_value", label: "Major Attribute Value", fieldtype: "Select", options: attributeValues(editor, draft.value.set_item_attribute), required: true, hidden: !draft.value.set_item_attribute },
])
const grid = computed(() => combinationGrid(draft.value.set_item_detail, { options: attributeValues(editor, draft.value.packing_attribute) }))

useSectionFocus(editor, props.sectionKey, { set_item_detail: () => setGrid.value })

function toggle(on) {
	if (!on) { editor.setValue("is_set_item", 0); return }
	const patch = { is_set_item: 1 }
	if (!draft.value.set_item_attribute && attributeNames(draft.value).includes("Part")) patch.set_item_attribute = "Part"
	editor.setValues(patch)
}
function update(model) {
	editor.setValue("set_item_detail", combinationFromModel(draft.value.set_item_detail, model))
}
</script>
