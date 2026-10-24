<template>
	<section class="item-conversions" aria-label="Item Conversions">
		<ListView
			ref="listView"
			:doctype="capability.doctype"
			title="Item Conversions"
			search-placeholder="Search Item Conversions…"
			name-column-label="Item Conversion"
			row-mark="IC"
			min-table-width="980px"
			:default-columns="['warehouse', 'from_item', 'to_item', 'posting_date', 'from_total_amount']"
			viewport-bounded
			clickable
			@row-click="openDocument"
		>
			<template #toolbar-actions>
				<Button v-if="capability.can_create" class="list-primary-action" label="Create New" icon="pi pi-plus" @click="createDocument" />
			</template>
		</ListView>

		<ItemConversionDialog v-model:visible="documentVisible" :name="selectedName" :new-defaults="newDefaults" @changed="documentChanged" />
	</section>
</template>

<script setup>
import Button from "primevue/button"
import { ref } from "vue"

import ListView from "../../../components/common/ListView.vue"
import { takeNewDocumentDefaults } from "../../../utils/newDocumentDefaults.js"
import ItemConversionDialog from "./ItemConversionDialog.vue"

const props = defineProps({ capability: { type: Object, required: true } })

const listView = ref(null)
const documentVisible = ref(false)
const selectedName = ref("")
const newDefaults = ref({})

function createDocument() {
	newDefaults.value = takeNewDocumentDefaults(props.capability.doctype)
	selectedName.value = ""
	documentVisible.value = true
}
function openDocument(row) {
	newDefaults.value = {}
	selectedName.value = row.name
	documentVisible.value = true
}
function documentChanged() { listView.value?.refresh?.(true) }
</script>

<style scoped>
.item-conversions { display: grid; min-width: 0; }

@media (min-width: 1025px) {
	.item-conversions {
		height: calc(100dvh - var(--erp-shell-header-height) - 80px);
		min-height: 0;
		overflow: hidden;
	}

	.item-conversions :deep(.common-list-view--viewport-bounded) { height: 100%; }
}
</style>
