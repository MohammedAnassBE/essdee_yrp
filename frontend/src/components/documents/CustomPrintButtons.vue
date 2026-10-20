<template>
	<Button v-for="action in actions" :key="action.key" :label="action.label" icon="pi pi-print" severity="secondary" outlined :disabled="disabled" @click="print(action.url)" />
	<DocumentErrorDialog :message="error" title="Print failed" @dismiss="error = ''" />
</template>

<script setup>
import Button from "primevue/button"
import { computed, ref } from "vue"
import { useDocumentPermissions } from "../../composables/useDocumentPermissions.js"
import { getCustomPrintButtons } from "../../utils/customPrintButtons.js"
import { openPrintUrl } from "../../utils/printUrl.js"
import DocumentErrorDialog from "./DocumentErrorDialog.vue"

const props = defineProps({
	doctype: { type: String, required: true },
	record: { type: Object, default: () => ({}) },
	permissions: { type: Object, default: () => ({}) },
	disabled: { type: Boolean, default: false },
})
const permissions = useDocumentPermissions(() => [props.doctype, props.record?.name, props.record?.docstatus], () => props.permissions.can_print === undefined && props.doctype !== "SD YRP Cutting LaySheet")
const actions = computed(() => getCustomPrintButtons(props.doctype, props.record, { ...props.permissions, can_print: props.permissions.can_print ?? permissions.value?.print }))
const error = ref("")
function print(url) {
	if (props.disabled) return
	error.value = openPrintUrl(url) ? "" : "Please enable pop-ups to print."
}
</script>
