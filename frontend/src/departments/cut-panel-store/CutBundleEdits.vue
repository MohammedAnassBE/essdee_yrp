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
			<template #cell-docstatus="{ value }"><span class="cut-bundle-status" :class="`cut-bundle-status--${value}`">{{ statusLabel(value) }}</span></template>
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
import CutBundleEditDialog from "./CutBundleEditDialog.vue"

defineProps({ capability: { type: Object, required: true } })
const listView = ref(null)
const dialogVisible = ref(false)
const selectedName = ref("")
const defaultColumns = ["lot", "item", "warehouse", "posting_date", "printed_time", "docstatus"]

function statusLabel(value) { return ({ 0: "Draft", 1: "Submitted", 2: "Cancelled" })[Number(value)] || "Unknown" }

function createEdit() { selectedName.value = ""; dialogVisible.value = true }
function openEdit(row) { if (!row?.name) return; selectedName.value = row.name; dialogVisible.value = true }
async function changed() { await listView.value?.refresh?.() }
</script>

<style scoped>
.cut-bundle-edits { min-width: 0; }
.cut-bundle-status { display: inline-flex; padding: 3px 8px; border-radius: var(--erp-pill-radius); background: var(--erp-surface-muted); color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 760; }
.cut-bundle-status--1 { background: var(--erp-accent-soft); color: var(--erp-accent-hover); }
.cut-bundle-status--2 { background: #fff1f1; color: #b42318; }
</style>
