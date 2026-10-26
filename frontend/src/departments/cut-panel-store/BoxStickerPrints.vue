<template>
	<div class="box-sticker-prints">
		<ListView
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
				<DocumentStatusBadge :docstatus="value" />
			</template>
			<template #toolbar-actions>
				<Button v-if="capability.can_create" label="New" icon="pi pi-plus" @click="router.push({ name: newRouteName })" />
			</template>
		</ListView>
	</div>
</template>

<script setup>
import Button from "primevue/button"
import { useRouter } from "vue-router"

import ListView from "../../components/common/ListView.vue"
import DocumentStatusBadge from "../../components/documents/DocumentStatusBadge.vue"
import { openListDocument } from "../../router/listDocumentNavigation.js"

const props = defineProps({
	capability: { type: Object, required: true },
	newRouteName: { type: String, required: true },
	viewRouteName: { type: String, required: true },
})

const router = useRouter()
const defaultColumns = ["lot", "fg_item", "print_format", "docstatus"]

function openPrint(row, snapshot) {
	return openListDocument(router, row, snapshot, { routeName: props.viewRouteName, paramName: "boxStickerPrintId" })
}
</script>

<style scoped>
.box-sticker-prints { min-width: 0; }
</style>
