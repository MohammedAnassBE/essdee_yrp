<template>
	<IpdSection :section-key="sectionKey">
		<div class="ipd-section-stack">
			<IpdFields v-if="editor.isNew" class="ipd-item-details-wide" :fields="itemFields" :section="sectionKey" />
			<IpdFields class="ipd-item-details-row" :fields="fields" :section="sectionKey" />
			<IpdFields class="ipd-item-details-wide" :fields="descriptionFields" :section="sectionKey" />
		</div>
	</IpdSection>
</template>

<script setup>
import { computed, inject } from "vue"

import IpdSection from "../IpdSection.vue"
import { IPD_EDITOR_KEY } from "../useIpdEditor.js"
import IpdFields from "./IpdFields.vue"
import "./sections.css"

defineProps({
	sectionKey: { type: String, required: true },
	readonly: { type: Boolean, default: false },
})
const editor = inject(IPD_EDITOR_KEY)
const attributeNames = computed(() => (editor.draft.item_attributes || []).map((row) => row.attribute).filter(Boolean))
const itemFields = [
	{ fieldname: "item", label: "Item", fieldtype: "Link", options: "Item", filters: { has_variants: 1, disabled: 0 }, required: true },
]
const descriptionFields = [{ fieldname: "description", label: "Description", fieldtype: "Small Text" }]
const fields = computed(() => [
	{ fieldname: "primary_item_attribute", label: "Primary Item Attribute", fieldtype: "Select", options: attributeNames.value, disabled: !editor.isNew },
	{ fieldname: "dependent_attribute", label: "Dependent Attribute", fieldtype: "Select", options: attributeNames.value, disabled: !editor.isNew },
	{ fieldname: "tech_pack_version", label: "Tech Pack Version", fieldtype: "Data" },
	{ fieldname: "pattern_version", label: "Pattern Version", fieldtype: "Data" },
	{ fieldname: "copied_from", label: "Copied From", disabled: true },
	{ fieldname: "approved_by", label: "Approved By", disabled: true },
])
</script>
