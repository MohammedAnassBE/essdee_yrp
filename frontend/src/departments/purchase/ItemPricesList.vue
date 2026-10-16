<template>
	<DepartmentPage title="Item Prices" back-to="/purchase" back-label="Purchase" :show-title="false" flat full-width inline-navigation>
		<section class="purchase-prices-page erp-workspace" aria-label="Item Prices">
			<WorkspaceLoadError v-if="error" :message="error" :loading="loading" @retry="load" />
			<div v-else-if="loading" class="purchase-prices-page__loading" aria-label="Loading Item Prices"><ListPageSkeleton /></div>
			<Message v-else-if="!capability" severity="warn" :closable="false">
				You do not have permission to view Item Prices.
			</Message>
			<ListView
				v-else
				doctype="YRP Item Price"
				title="Item Prices"
				eyebrow="Purchase"
				subtitle="Supplier prices, quantity slabs and approval"
				search-placeholder="Search Item Prices…"
				name-column-label="Item Price"
				row-mark="ITP"
				min-table-width="980px"
				status-field="workflow_state"
				:status-options="capability.workflow_states || []"
				:initial-status="itemPriceListInitialStatus(capability || {})"
				:default-columns="columns"
				:column-labels="columnLabels"
				:unsortable-columns="['price']"
				:excluded-filter-fields="['price']"
				:allow-bulk-actions="false"
				viewport-bounded
				clickable
				@loaded="loadPriceSummaries"
				@row-click="openPrice"
			>
				<template #toolbar-actions>
					<Button v-if="capability?.can_create" label="Create Price" icon="pi pi-plus" @click="createPrice" />
				</template>
				<template #cell-workflow_state="{ value }"><DocumentStatusBadge :label="value" /></template>
				<template #cell-price="{ row }"><span class="purchase-prices-page__price">{{ itemPriceSummaryLabel(priceSummaries[row.name]) }}</span></template>
			</ListView>
		</section>
	</DepartmentPage>
</template>

<script setup>
import Button from "primevue/button"
import Message from "primevue/message"
import { onMounted, ref } from "vue"
import { useRouter } from "vue-router"

import { getItemPriceSummaries, getPurchaseCapabilities } from "../../api/purchase.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import ListView from "../../components/common/ListView.vue"
import ListPageSkeleton from "../../components/common/ListPageSkeleton.vue"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import DocumentStatusBadge from "../../components/documents/DocumentStatusBadge.vue"
import { openListDocument } from "../../router/listDocumentNavigation.js"
import { PURCHASE_ROUTES, itemPriceListInitialStatus, itemPriceSummaryLabel } from "./purchaseViews.js"

const router = useRouter()
const loading = ref(true)
const error = ref("")
const capability = ref(null)
const columns = ["workflow_state", "item_name", "supplier", "uom", "price", "from_date", "to_date"]
const columnLabels = { item_name: "Item", from_date: "Valid From", to_date: "Valid To", workflow_state: "Status" }
const priceSummaries = ref({})
let priceSummarySequence = 0

async function load() {
	loading.value = true
	error.value = ""
	try {
		capability.value = (await getPurchaseCapabilities())?.sections?.item_prices || null
	} catch (reason) {
		capability.value = null
		error.value = reason?.message || "Unable to load Item Prices."
	} finally {
		loading.value = false
	}
}

async function loadPriceSummaries(payload) {
	const sequence = ++priceSummarySequence
	const names = (payload?.rows || []).map((row) => row.name)
	priceSummaries.value = {}
	if (!names.length) return
	try {
		const summaries = await getItemPriceSummaries(names)
		if (sequence === priceSummarySequence) priceSummaries.value = summaries || {}
	} catch {
		if (sequence === priceSummarySequence) priceSummaries.value = Object.fromEntries(names.map((name) => [name, { slab_count: 0 }]))
	}
}

function openPrice(row, snapshot) {
	return openListDocument(router, row, snapshot, { routeName: PURCHASE_ROUTES.itemPrice, paramName: "priceId" })
}

function createPrice() {
	router.push({ name: PURCHASE_ROUTES.itemPriceNew })
}

onMounted(load)
</script>

<style scoped>
.purchase-prices-page { min-width: 0; }
.purchase-prices-page__price { font-variant-numeric: tabular-nums; white-space: nowrap; }
.purchase-prices-page__loading { display: grid; gap: 16px; padding: clamp(14px, 2vw, 22px); }
</style>
