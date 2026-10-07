<template>
	<div class="box-sticker-prints">
		<ListView
			ref="listView"
			doctype="SD YRP Box Sticker Print"
			title="Box Sticker Prints"
			search-placeholder="Search Box Sticker Prints…"
			name-column-label="Box Sticker Print"
			row-mark="BSP"
			min-table-width="900px"
			:default-columns="defaultColumns"
			:column-labels="{ fg_item: 'Item', docstatus: 'Status' }"
			:allow-bulk-actions="false"
			viewport-bounded
			clickable
			@row-click="openPrint"
		>
			<template #cell-docstatus="{ value }">
				<span class="box-sticker-status" :class="`box-sticker-status--${value}`">{{ statusLabel(value) }}</span>
			</template>
			<template #toolbar-actions>
				<Button v-if="capability.can_create" label="Create Box Sticker Print" icon="pi pi-plus" @click="createPrint" />
			</template>
		</ListView>

		<BoxStickerPrintDialog
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
import BoxStickerPrintDialog from "./BoxStickerPrintDialog.vue"

defineProps({ capability: { type: Object, required: true } })

const listView = ref(null)
const dialogVisible = ref(false)
const selectedName = ref("")
const defaultColumns = ["lot", "fg_item", "print_format", "docstatus"]

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
.box-sticker-prints { min-width: 0; }
.box-sticker-status { display: inline-flex; padding: 3px 8px; border-radius: var(--erp-pill-radius); background: var(--erp-surface-muted); color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 760; }
.box-sticker-status--1 { background: var(--erp-accent-soft); color: var(--erp-accent-hover); }
.box-sticker-status--2 { background: var(--erp-danger-soft); color: var(--erp-danger); }
</style>
