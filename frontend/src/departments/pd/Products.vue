<template>
	<ListView
		doctype="SD YRP Product"
		title="Products"
		eyebrow="PD"
		search-placeholder="Search Products…"
		name-column-label="Style No"
		row-mark="STY"
		min-table-width="1100px"
		:default-columns="defaultColumns"
		viewport-bounded
		clickable
		@row-click="openProduct"
	>
		<template #toolbar-actions>
			<Button v-if="capability.can_create" label="Create Product" icon="pi pi-plus" @click="createProduct" />
		</template>
	</ListView>
</template>

<script setup>
import Button from "primevue/button"
import { useRouter } from "vue-router"

import ListView from "../../components/common/ListView.vue"
import { openListDocument } from "../../router/listDocumentNavigation.js"
import { PD_ROUTES } from "./pdViews.js"

defineProps({ capability: { type: Object, required: true } })

const router = useRouter()
const defaultColumns = ["item_name", "product_group", "brand", "season", "is_set_item", "tech_pack_no"]

function openProduct(row, snapshot) {
	return openListDocument(router, row, snapshot, {
		routeName: PD_ROUTES.product,
		paramName: "productId",
	})
}

function createProduct() {
	router.push({ name: PD_ROUTES.productNew })
}
</script>
