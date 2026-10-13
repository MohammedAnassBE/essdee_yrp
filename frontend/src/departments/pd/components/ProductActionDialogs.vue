<template>
	<DocumentConfirmationDialog
		:visible="releaseVisible"
		title="Release Tech Pack?"
		message="Are you sure you want to release Tech Pack?"
		confirm-label="Release Tech Pack"
		confirm-icon="pi pi-send"
		severity="primary"
		:busy="acting === 'release'"
		@update:visible="emit('update:release-visible', $event)"
		@confirm="emit('confirm-release')"
	/>
	<DocumentConfirmationDialog
		:visible="deleteVisible"
		title="Delete Product?"
		:message="`Delete ${deleteTarget?.name || 'this Product'}? This action cannot be undone.`"
		confirm-label="Delete Product"
		confirm-icon="pi pi-trash"
		:busy="acting === 'delete'"
		@update:visible="emit('update:delete-visible', $event)"
		@confirm="emit('confirm-delete')"
	/>
	<DocumentConfirmationDialog
		:visible="discardVisible"
		title="Discard unsaved changes?"
		message="This Product has unsaved changes. Leave and discard those changes?"
		confirm-label="Discard Changes"
		:busy="false"
		@update:visible="emit('update:discard-visible', $event)"
		@confirm="emit('discard-changes')"
	/>
	<DocumentErrorDialog
		:message="actionError"
		title="Product action could not be completed"
		:retry-label="hasStaleError ? 'Reload' : ''"
		@dismiss="emit('dismiss-error')"
		@retry="emit('reload')"
	/>
</template>

<script setup>
import DocumentConfirmationDialog from "../../../components/documents/DocumentConfirmationDialog.vue"
import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"

defineProps({
	releaseVisible: { type: Boolean, default: false },
	deleteVisible: { type: Boolean, default: false },
	discardVisible: { type: Boolean, default: false },
	deleteTarget: { type: Object, default: null },
	acting: { type: String, default: "" },
	actionError: { type: String, default: "" },
	hasStaleError: { type: Boolean, default: false },
})
const emit = defineEmits([
	"update:release-visible",
	"update:delete-visible",
	"update:discard-visible",
	"confirm-release",
	"confirm-delete",
	"discard-changes",
	"dismiss-error",
	"reload",
])
</script>
