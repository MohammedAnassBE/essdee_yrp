<template>
	<div class="excel-sticker-prints">
		<ListView
			ref="listView"
			doctype="YRP Excel Sticker Print"
			title="Excel Sticker Prints"
			search-placeholder="Search Excel Sticker Prints…"
			name-column-label="Excel Sticker Print"
			row-mark="ESP"
			min-table-width="880px"
			:default-columns="defaultColumns"
			:column-labels="{ docstatus: 'Status', modified: 'Modified' }"
			:allow-bulk-actions="false"
			viewport-bounded
			clickable
			@row-click="openPrint"
		>
			<template #cell-docstatus="{ value }">
				<span class="excel-sticker-status" :class="`excel-sticker-status--${value}`">{{ statusLabel(value) }}</span>
			</template>
			<template #toolbar-actions>
				<Button v-if="capability.can_create" label="Create Excel Sticker Print" icon="pi pi-plus" @click="createPrint" />
			</template>
		</ListView>

		<ExcelStickerPrintDialog
			v-model:visible="dialogVisible"
			:document-name="selectedName"
			@changed="changed"
		/>
	</div>
</template>

<script setup>
import Button from "primevue/button"
import { ref } from "vue"

import ListView from "../../components/common/ListView.vue"
import ExcelStickerPrintDialog from "./ExcelStickerPrintDialog.vue"

defineProps({ capability: { type: Object, required: true } })

const listView = ref(null)
const dialogVisible = ref(false)
const selectedName = ref("")
const defaultColumns = ["excel_file", "print_format", "docstatus", "modified"]

function statusLabel(value) {
	return ({ 0: "Draft", 1: "Submitted", 2: "Cancelled" })[Number(value)] || "Unknown"
}

function createPrint() {
	selectedName.value = ""
	dialogVisible.value = true
}

function openPrint(row) {
	if (!row?.name) return
	selectedName.value = row.name
	dialogVisible.value = true
}

async function changed() {
	await listView.value?.refresh?.()
}
</script>

<style scoped>
.excel-sticker-prints { min-width: 0; }
.excel-sticker-status { display: inline-flex; padding: 3px 8px; border-radius: var(--erp-pill-radius); background: var(--erp-surface-muted); color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 760; }
.excel-sticker-status--1 { background: var(--erp-accent-soft); color: var(--erp-accent-hover); }
.excel-sticker-status--2 { background: var(--erp-danger-soft); color: var(--erp-danger); }
</style>
