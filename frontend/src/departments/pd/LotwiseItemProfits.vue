<template>
	<ListView
		doctype="SD YRP Lotwise Item Profit"
		title="Lotwise Item Profit"
		eyebrow="PD"
		search-placeholder="Search Lotwise Item Profit…"
		name-column-label="Costing Sheet"
		row-mark="CST"
		min-table-width="1180px"
		status-field="lot_costing_type"
		:status-options="Object.keys(LOTWISE_STATUS_COLOURS)"
		:default-columns="defaultColumns"
		viewport-bounded
		clickable
		@row-click="openLotwiseItemProfit"
	>
		<template #toolbar-actions>
			<Button
				v-if="capability.can_create"
				label="Create Lotwise Item Profit"
				icon="pi pi-plus"
				@click="createLotwiseItemProfit"
			/>
		</template>
		<template #cell-lot_costing_type="{ value }">
			<DocumentStatusBadge :label="value" />
		</template>
	</ListView>
</template>

<script setup>
import Button from "primevue/button"
import { useRouter } from "vue-router"

import ListView from "../../components/common/ListView.vue"
import DocumentStatusBadge from "../../components/documents/DocumentStatusBadge.vue"
import { openListDocument } from "../../router/listDocumentNavigation.js"
import { LOTWISE_STATUS_COLOURS, PD_ROUTES } from "./pdViews.js"

defineProps({ capability: { type: Object, required: true } })

const router = useRouter()
const defaultColumns = [
	"product",
	"item",
	"lot",
	"lot_costing_type",
	"total_qty",
	"avg_rate_per_piece",
	"profit_percent_markdown",
]

function openLotwiseItemProfit(row, snapshot) {
	return openListDocument(router, row, snapshot, {
		routeName: PD_ROUTES.lotwise,
		paramName: "profitId",
	})
}

function createLotwiseItemProfit() {
	router.push({ name: PD_ROUTES.lotwiseNew })
}
</script>
