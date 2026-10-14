<template>
	<DepartmentPage title="Items" back-to="/purchase" back-label="Purchase" :show-title="false" flat full-width inline-navigation>
		<section class="purchase-items-page erp-workspace" aria-label="Purchase items">
			<WorkspaceLoadError v-if="error" :message="error" :loading="loading" @retry="load" />
			<Message v-else-if="!loading && !capability" severity="warn" :closable="false">
				You do not have permission to view Items.
			</Message>
			<template v-else>
				<nav class="purchase-list-modes" aria-label="Item quick filters">
					<button
						v-for="option in modes"
						:key="option.value"
						type="button"
						:class="{ 'purchase-list-modes__active': mode === option.value }"
						:aria-pressed="mode === option.value"
						@click="mode = option.value"
					>
						{{ option.label }}
					</button>
				</nav>
				<ListView
					:key="mode"
					doctype="Item"
					title="Items"
					eyebrow="Purchase"
					subtitle="Templates and plain purchase items"
					search-placeholder="Search Items…"
					name-column-label="Item"
					row-mark="ITM"
					min-table-width="900px"
					:filters="itemListFilters(mode)"
					:excluded-filter-fields="['variant_of']"
					:default-columns="columns"
					:column-labels="columnLabels"
					:allow-bulk-actions="false"
					viewport-bounded
					clickable
					@loaded="loadAttributeCounts"
					@row-click="openItem"
				>
					<template #toolbar-actions>
						<Button v-if="capability?.can_create" label="Create Item" icon="pi pi-plus" @click="createItem" />
					</template>
					<template #cell-has_variants="{ row }">
						<span>{{ itemAttributeCountLabel(attributeCounts[row.name]) }}</span>
					</template>
					<template #cell-disabled="{ value }">
						<DocumentStatusBadge :label="Number(value) ? 'Disabled' : 'Enabled'" />
					</template>
				</ListView>
			</template>
		</section>
	</DepartmentPage>
</template>

<script setup>
import Button from "primevue/button"
import Message from "primevue/message"
import { onMounted, ref } from "vue"
import { useRouter } from "vue-router"

import { getItemAttributeCounts, getPurchaseCapabilities } from "../../api/purchase.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import ListView from "../../components/common/ListView.vue"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import DocumentStatusBadge from "../../components/documents/DocumentStatusBadge.vue"
import { openListDocument } from "../../router/listDocumentNavigation.js"
import { PURCHASE_ROUTES, itemAttributeCountLabel, itemListFilters } from "./purchaseViews.js"

const router = useRouter()
const loading = ref(true)
const error = ref("")
const capability = ref(null)
const attributeCounts = ref({})
const mode = ref("purchase")
let attributeCountSequence = 0
const modes = [
	{ label: "Purchase items", value: "purchase" },
	{ label: "All", value: "all" },
	{ label: "Disabled", value: "disabled" },
]
const columns = ["item_group", "stock_uom", "has_variants", "disabled"]
const columnLabels = { stock_uom: "UOM", has_variants: "Attributes" }

async function load() {
	loading.value = true
	error.value = ""
	try {
		capability.value = (await getPurchaseCapabilities())?.sections?.items || null
	} catch (reason) {
		capability.value = null
		error.value = reason?.message || "Unable to load Items."
	} finally {
		loading.value = false
	}
}

function openItem(row, snapshot) {
	return openListDocument(router, row, snapshot, { routeName: PURCHASE_ROUTES.item, paramName: "itemId" })
}

async function loadAttributeCounts(payload) {
	const sequence = ++attributeCountSequence
	const rows = payload?.rows || []
	attributeCounts.value = Object.fromEntries(rows.map((row) => [row.name, null]))
	if (!rows.length) return
	try {
		const counts = await getItemAttributeCounts(rows.map((row) => row.name))
		if (sequence !== attributeCountSequence) return
		attributeCounts.value = Object.fromEntries(
			rows.map((row) => [row.name, Number(counts?.[row.name] || 0)]),
		)
	} catch {
		if (sequence !== attributeCountSequence) return
		attributeCounts.value = Object.fromEntries(
			rows.map((row) => [row.name, Number(row.has_variants) ? null : 0]),
		)
	}
}

function createItem() {
	router.push({ name: PURCHASE_ROUTES.itemNew })
}

onMounted(load)
</script>

<style scoped>
.purchase-items-page { display: grid; min-width: 0; gap: 10px; }
.purchase-list-modes { display: flex; width: fit-content; max-width: 100%; gap: 4px; padding: 4px; overflow-x: auto; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); background: var(--erp-surface-muted); }
.purchase-list-modes button { min-height: 32px; padding: 5px 12px; color: var(--erp-text-muted); font: inherit; font-size: var(--erp-font-size-caption); font-weight: 700; white-space: nowrap; cursor: pointer; border: 0; border-radius: calc(var(--erp-control-radius) - 2px); background: transparent; }
.purchase-list-modes button:hover { color: var(--erp-text); background: var(--erp-surface); }
.purchase-list-modes__active { color: var(--erp-accent-hover) !important; background: var(--erp-surface) !important; box-shadow: var(--erp-shadow-xs); }
@media (max-width: 620px) { .purchase-list-modes { width: 100%; } .purchase-list-modes button { flex: 1 0 auto; } }
</style>
