<template>
	<section class="pd-product-workspace" aria-label="Product workspace">
		<div v-if="loading" class="pd-product-workspace__loading" aria-label="Loading Product">
			<Skeleton height="5.5rem" />
			<Skeleton height="3.25rem" />
			<Skeleton height="22rem" />
		</div>
		<WorkspaceLoadError
			v-else-if="loadError"
			title="Product could not be loaded"
			:message="loadError"
			:loading="loading"
			@retry="emit('retry')"
		/>
		<template v-else-if="hasWorkspace">
			<ProductWorkspaceHeader
				:record="record"
				:actions="actions"
				:print-formats="workspace.print_formats || []"
				:mode="mode"
				:is-set-item="isSetItem"
				:busy="busy"
				:saving="saving"
				:can-save="canSave"
				:can-print="canPrint"
				@cancel="emit('cancel')"
				@save="emit('save')"
			/>
			<Message v-if="copySource" severity="info" closable @close="emit('dismiss-copy')">
				Copied from {{ copySource }}. Silhouette and graphic designs are not copied.
			</Message>

			<p v-if="mode === 'edit' && !isNew" class="pd-product-workspace__upload-hint">
				Save or cancel your edits to upload images.
			</p>

			<ProductWorkspaceTabs
				:active-tab="activeTab"
				:visible-tabs="visibleTabs"
				:workspace="workspace"
				:record="record"
				:form="form"
				:images="images"
				:meta-by-name="metaByName"
				:colour-tables="colourTables"
				:trim-colours="trimColours"
				:is-new="isNew"
				:is-set-item="isSetItem"
				:fields-disabled="fieldsDisabled"
				:can-edit-images="canEditImages"
				:can-upload-images="canUploadImages"
				:can-create-costing="canCreateCosting"
				:media-busy="mediaBusy"
				@update:active-tab="emit('update:active-tab', $event)"
				@update-field="forwardFieldUpdate"
				@update-image-group="forwardImageUpdate"
				@operation-started="emit('operation-started')"
				@operation-finished="emit('operation-finished', $event)"
			/>
		</template>
	</section>
</template>

<script setup>
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"

import WorkspaceLoadError from "../../../components/common/WorkspaceLoadError.vue"
import ProductWorkspaceHeader from "./ProductWorkspaceHeader.vue"
import ProductWorkspaceTabs from "./ProductWorkspaceTabs.vue"

defineProps({
	workspace: { type: Object, required: true }, record: { type: Object, required: true },
	form: { type: Object, required: true }, images: { type: Object, required: true },
	metaByName: { type: Object, required: true }, actions: { type: Array, required: true },
	visibleTabs: { type: Array, required: true }, colourTables: { type: Array, required: true },
	trimColours: { type: Array, required: true }, activeTab: { type: String, required: true },
	mode: { type: String, required: true }, loadError: { type: String, default: "" },
	loading: { type: Boolean, default: false }, hasWorkspace: { type: Boolean, default: false },
	isNew: { type: Boolean, default: false }, isSetItem: { type: Boolean, default: false },
	busy: { type: Boolean, default: false }, saving: { type: Boolean, default: false },
	canSave: { type: Boolean, default: false }, canPrint: { type: Boolean, default: false },
	fieldsDisabled: { type: Boolean, default: false }, canEditImages: { type: Boolean, default: false },
	canUploadImages: { type: Boolean, default: false }, canCreateCosting: { type: Boolean, default: false },
	mediaBusy: { type: Boolean, default: false },
	copySource: { type: String, default: "" },
})
const emit = defineEmits([
	"retry", "cancel", "save", "update:active-tab", "update-field", "update-image-group",
	"operation-started", "operation-finished", "dismiss-copy",
])

function forwardFieldUpdate(fieldname, value) {
	emit("update-field", fieldname, value)
}

function forwardImageUpdate(group, rows) {
	emit("update-image-group", group, rows)
}
</script>
