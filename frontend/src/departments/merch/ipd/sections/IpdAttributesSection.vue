<template>
	<IpdSection :section-key="sectionKey">
		<div ref="attributeSection" id="ipd-edit-item_attributes" class="ipd-section-stack" tabindex="-1">
			<p v-if="editor.isNew" class="erp-help-text">Attribute values are copied from the Item when you create the IPD.</p>
			<div v-else class="ipd-chip-cards">
				<div v-for="card in cards" :key="card.attribute" :data-attribute="card.attribute" tabindex="-1">
					<IpdAttributeChips
						:attribute="card.attribute"
						:values="card.values"
						:roles="card.roles"
						:editable="card.editable"
						:note="card.note"
						:empty-text="card.emptyText"
					/>
				</div>
			</div>
			<IpdFields :fields="quantityFields" />
		</div>
	</IpdSection>
</template>

<script setup>
import { computed, inject, shallowRef } from "vue"

import IpdSection from "../IpdSection.vue"
import { IPD_EDITOR_KEY } from "../useIpdEditor.js"
import { focusElement } from "../ipdFocus.js"
import { useSectionFocus } from "./sectionFocus.js"
import IpdAttributeChips from "./IpdAttributeChips.vue"
import IpdFields from "./IpdFields.vue"
import "./sections.css"

const ROLE_FIELDS = [["primary", "primary_item_attribute"], ["dependent", "dependent_attribute"], ["packing", "packing_attribute"], ["stitching", "stiching_attribute"], ["set", "set_item_attribute"]]

const props = defineProps({
	sectionKey: { type: String, required: true },
	readonly: { type: Boolean, default: false },
})
const editor = inject(IPD_EDITOR_KEY)
const attributeSection = shallowRef(null)
const rows = computed(() => editor.draft.item_attributes || [])
const contextByAttribute = computed(() => new Map((editor.context?.attributes || []).map((entry) => [entry.attribute, entry])))
const quantityFields = computed(() => [
	{ fieldname: "additional_cloth", label: "Additional Cloth %", fieldtype: "Float", disabled: Boolean(Number(editor.draft.is_cloth_item)) },
	{ fieldname: "stiching_attribute_quantity", label: "Stiching Attribute Quantity", fieldtype: "Int", disabled: Boolean(Number(editor.draft.is_cloth_item)) },
])
const cards = computed(() => rows.value.filter((row) => row.attribute).map((row) => {
	const entry = contextByAttribute.value.get(row.attribute)
	const roles = ROLE_FIELDS.filter(([, fieldname]) => editor.draft[fieldname] === row.attribute).map(([role]) => role)
	return { attribute: row.attribute, values: entry?.values || [], roles, ...access(row, entry, roles) }
}))

useSectionFocus(editor, props.sectionKey, { item_attributes: () => ({ focusCell: focusAttribute }) })
function focusAttribute(rowKey) {
	const attribute = rowKey ?? rows.value[0]?.attribute
	const target = [...(attributeSection.value?.querySelectorAll('[data-attribute]') || [])]
		.find((card) => card.dataset.attribute === attribute)
	return focusElement(target || attributeSection.value)
}

function access(row, entry, roles) {
	if (editor.readonly) return { editable: false, note: "", emptyText: "No values." }
	if (!entry || !row.mapping) return { editable: false, note: "", emptyText: "Save the IPD to start this value list." }
	if (entry.numeric) return { editable: false, note: "Numeric values come from the attribute itself.", emptyText: "No values." }
	if (entry.is_shared) return { editable: false, note: "This list is shared with another document. Edit it there.", emptyText: "No values." }
	if (roles.includes("dependent")) return { editable: false, note: "Stages come from the Item.", emptyText: "No values." }
	return { editable: true, note: "", emptyText: "No values yet." }
}
</script>
