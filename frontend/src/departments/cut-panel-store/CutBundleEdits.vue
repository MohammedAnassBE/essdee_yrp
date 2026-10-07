<template>
	<div class="cut-bundle-edits">
		<ListView
			ref="listView"
			doctype="SD YRP Cut Bundle Edit"
			title="Cut Bundle Edits"
			search-placeholder="Search Cut Bundle Edits…"
			name-column-label="Cut Bundle Edit"
			row-mark="CBE"
			min-table-width="1050px"
			:default-columns="defaultColumns"
			:column-labels="{ docstatus: 'Status' }"
			:allow-bulk-actions="false"
			viewport-bounded
			clickable
			@row-click="openEdit"
		>
			<template #cell-docstatus="{ value }"><DocumentStatusBadge :docstatus="value" /></template>
			<template #toolbar-actions>
				<Button v-if="capability.can_create" label="Create Cut Bundle Edit" icon="pi pi-plus" @click="createEdit" />
			</template>
		</ListView>
		<CutBundleEditDialog v-model:visible="dialogVisible" :document-name="selectedName" @changed="changed" />
	</div>
</template>

<script setup>
import Button from "primevue/button"
import { ref } from "vue"

import ListView from "../../components/common/ListView.vue"
import DocumentStatusBadge from "../../components/documents/DocumentStatusBadge.vue"
import CutBundleEditDialog from "./CutBundleEditDialog.vue"

defineProps({ capability: { type: Object, required: true } })
const listView = ref(null)
const dialogVisible = ref(false)
const selectedName = ref("")
const defaultColumns = ["lot", "item", "warehouse", "posting_date", "printed_time", "docstatus"]

function createEdit() { selectedName.value = ""; dialogVisible.value = true }
function openEdit(row) { if (!row?.name) return; selectedName.value = row.name; dialogVisible.value = true }
async function changed() { await listView.value?.refresh?.() }
</script>

<style scoped>
.cut-bundle-edits { min-width: 0; }
</style>
