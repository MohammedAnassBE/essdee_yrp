<template>
	<Button
		type="button"
		class="document-print-button"
		:label="label"
		icon="pi pi-print"
		severity="secondary"
		outlined
		:disabled="disabled || !name || !normalisedFormats.length"
		@click="handleClick"
	/>
	<Menu
		v-if="normalisedFormats.length > 1"
		ref="menu"
		:model="menuItems"
		popup
		:base-z-index="5000"
		class="erp-print-menu"
	/>
</template>

<script setup>
import Button from "primevue/button"
import Menu from "primevue/menu"
import { computed, ref } from "vue"

const props = defineProps({
	doctype: { type: String, required: true },
	name: { type: String, default: "" },
	formats: { type: Array, default: () => [] },
	label: { type: String, default: "Print" },
	disabled: { type: Boolean, default: false },
})

const menu = ref(null)
const normalisedFormats = computed(() => props.formats
	.map((item) => typeof item === "string" ? { label: item, format: item } : item)
	.filter((item) => item?.format))
const menuItems = computed(() => normalisedFormats.value.map((item) => ({
	label: item.label || item.format,
	icon: "pi pi-file-pdf",
	command: () => openPrint(item.format),
})))

function handleClick(event) {
	if (normalisedFormats.value.length === 1) openPrint(normalisedFormats.value[0].format)
	else menu.value?.toggle(event)
}

function openPrint(format) {
	const query = new URLSearchParams({
		doctype: props.doctype,
		name: props.name,
		trigger_print: "1",
		format,
		no_letterhead: "1",
	})
	window.open(`/printview?${query.toString()}`, "_blank", "noopener")
}
</script>

<style>
.erp-print-menu {
	z-index: 9999 !important;
}

.document-print-button.p-button {
	min-height: var(--erp-control-height);
	border-radius: var(--erp-control-radius);
}
</style>
