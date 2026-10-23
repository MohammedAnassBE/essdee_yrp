<template>
	<span class="document-shortcuts" hidden />
</template>

<script setup>
import { useDocumentShortcuts } from "../../composables/useDocumentShortcuts.js"

/** Template hook for Ctrl/Cmd+S and Ctrl/Cmd+D; place it inside the form or dialog whose buttons it mirrors. */
const props = defineProps({
	busy: { type: Boolean, default: false },
	canSave: { type: Boolean, default: false },
	canSubmit: { type: Boolean, default: false },
	canCancel: { type: Boolean, default: false },
	submitConfirms: { type: Boolean, default: false },
	cancelConfirms: { type: Boolean, default: false },
})
const emit = defineEmits(["save", "submit", "cancel"])
useDocumentShortcuts({
	isBusy: () => props.busy,
	canSave: () => props.canSave,
	save: () => emit("save"),
	canSubmit: () => props.canSubmit,
	submit: () => emit("submit"),
	submitConfirms: () => props.submitConfirms,
	canCancel: () => props.canCancel,
	cancel: () => emit("cancel"),
	cancelConfirms: () => props.cancelConfirms,
})
</script>
