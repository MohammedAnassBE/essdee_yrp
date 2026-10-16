<template>
	<IpdSection :section-key="sectionKey">
		<div class="ipd-section-stack">
			<IpdFields :fields="fields" :section="sectionKey" />
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
const fields = computed(() => [
	{ fieldname: "item", label: "Item", fieldtype: "Link", options: "Item", filters: { has_variants: 1, disabled: 0 }, required: true, disabled: !editor.isNew, help: editor.isNew ? "" : "Item is fixed once the IPD exists. Use New version from… to copy to another item." },
	{ fieldname: "description", label: "Description", fieldtype: "Small Text" },
	{ fieldname: "tech_pack_version", label: "Tech Pack Version", fieldtype: "Data" },
	{ fieldname: "pattern_version", label: "Pattern Version", fieldtype: "Data" },
	{ fieldname: "copied_from", label: "Copied From", disabled: true },
	{ fieldname: "approval_status", label: "Approval Status", disabled: true },
	{ fieldname: "approved_by", label: "Approved By", disabled: true },
])
</script>
