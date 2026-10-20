<template>
	<Button
		v-if="action !== 'none'"
		class="document-save-button"
		:label="action === 'submit' ? submitLabel : saveLabel"
		:icon="action === 'submit' ? 'pi pi-check' : 'pi pi-save'"
		:loading="loading"
		:aria-busy="loading"
		:disabled="actionDisabled"
		@click="performAction"
	/>
</template>

<script setup>
import Button from "primevue/button"
import { computed } from "vue"
import { getDocumentPrimaryAction } from "./documentPrimaryAction.js"
import { useActionConfirmation } from "../../utils/useActionConfirmation.js"

const props = defineProps({
	saved: { type: Boolean, default: false },
	dirty: { type: Boolean, default: true },
	docstatus: { type: Number, default: 0 },
	allowUpdateAfterSubmit: { type: Boolean, default: false },
	documentLabel: { type: String, default: "" },
	confirmSubmit: { type: Boolean, default: true },
	showSave: { type: Boolean, default: true },
	showSubmit: { type: Boolean, default: false },
	saveLabel: { type: String, default: "Save" },
	submitLabel: { type: String, default: "Submit" },
	loading: { type: Boolean, default: false },
	disabled: { type: Boolean, default: false },
	saveDisabled: { type: Boolean, default: false },
	submitDisabled: { type: Boolean, default: false },
})
const emit = defineEmits(["save", "submit"])
const confirmAction = useActionConfirmation()
const action = computed(() => getDocumentPrimaryAction(props))
const actionDisabled = computed(() => props.loading || props.disabled || action.value === "save-disabled" || (action.value === "submit" ? props.submitDisabled : props.saveDisabled))
function performAction() {
	if (actionDisabled.value || action.value === "none") return
	if (action.value !== "submit") return emit("save")
	if (!props.confirmSubmit) return emit("submit")
	confirmAction({
		header: "Confirm",
		message: `Permanently Submit ${props.documentLabel || "this document"}?`,
		acceptLabel: "Submit",
		acceptSeverity: "primary",
		acceptIcon: "pi pi-check",
		rejectLabel: "Cancel",
		accept: () => emit("submit"),
	})
}
</script>

<style scoped>
.document-save-button { white-space: nowrap; }
</style>
