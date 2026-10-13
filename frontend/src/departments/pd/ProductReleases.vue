<template>
	<ListView
		doctype="SD YRP Product Release"
		title="Product Releases"
		eyebrow="PD"
		search-placeholder="Search Product Releases…"
		name-column-label="Product Release"
		row-mark="REL"
		min-table-width="980px"
		:default-columns="defaultColumns"
		:allow-bulk-actions="false"
		viewport-bounded
		clickable
		@row-click="openProductRelease"
	/>
</template>

<script setup>
import { useRouter } from "vue-router"

import ListView from "../../components/common/ListView.vue"
import { openListDocument } from "../../router/listDocumentNavigation.js"
import { PD_ROUTES } from "./pdViews.js"

defineProps({ capability: { type: Object, required: true } })

const router = useRouter()
const defaultColumns = ["product", "style_no", "tech_pack_no", "product_group", "season"]

function openProductRelease(row, snapshot) {
	return openListDocument(router, row, snapshot, {
		routeName: PD_ROUTES.release,
		paramName: "releaseId",
	})
}
</script>
