<template>
	<Dialog
		v-model:visible="visible"
		modal
		dismissable-mask
		:header="title"
		class="related-records-dialog"
		:aria-label="title"
		@hide="emit('closed')"
	>
		<div class="related-records-dialog__body">
			<ListView
				:doctype="doctype"
				:title="title"
				:filters="baseFilters"
				:initial-advanced-filters="filters"
				:default-columns="defaultColumns"
				:column-labels="columnLabels"
				:status-field="statusField"
				:status-options="statusOptions"
				:row-mark="rowMark"
				:navigation-enabled="false"
				:allow-bulk-actions="false"
				viewport-bounded
				@update:advanced-filters="filters = $event"
				@row-click="openRow"
			/>
		</div>
	</Dialog>
</template>

<script setup>
import Dialog from "primevue/dialog"

import ListView from "../common/ListView.vue"

defineProps({
	title: { type: String, required: true },
	doctype: { type: String, required: true },
	baseFilters: { type: [Array, Object], default: () => [] },
	defaultColumns: { type: Array, default: () => [] },
	columnLabels: { type: Object, default: () => ({}) },
	statusField: { type: String, default: "" },
	statusOptions: { type: Array, default: () => [] },
	rowMark: { type: String, default: "DOC" },
})

const visible = defineModel("visible", { type: Boolean, default: false })
const filters = defineModel("filters", { type: Array, default: () => [] })
const emit = defineEmits(["open", "closed"])

function openRow(row) {
	emit("open", row)
}
</script>

<style>
.related-records-dialog.p-dialog {
	display: flex;
	width: min(96vw, 1480px);
	max-height: 92dvh;
	flex-direction: column;
}

.related-records-dialog .p-dialog-content {
	display: flex;
	min-height: 0;
	padding: 0;
	flex: 1 1 auto;
}

.related-records-dialog__body {
	display: flex;
	width: 100%;
	height: min(78dvh, 840px);
	min-height: 420px;
}

.related-records-dialog .common-list-view--viewport-bounded {
	height: 100%;
}

.related-records-dialog .list-page-head {
	padding: 2px 0 0;
}

@media (max-width: 620px) {
	.related-records-dialog.p-dialog {
		width: 100vw;
		height: 100dvh;
		max-height: 100dvh;
		margin: 0;
		border-radius: 0;
	}

	.related-records-dialog__body {
		height: auto;
		min-height: 0;
		flex: 1 1 auto;
	}

	.related-records-dialog .common-list-view--viewport-bounded {
		height: auto;
		overflow-y: auto;
	}
}
</style>
