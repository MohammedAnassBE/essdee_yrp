<template>
	<DepartmentPage title="Item Price" back-to="/purchase/item-prices" back-label="Item Prices" :show-title="false" flat full-width inline-navigation>
		<section class="item-price-frame">
			<FabricDocumentWorkspace :show-delete="false" doctype="YRP Item Price" title="Item Price" :workspace="workspace" :loading="loading" :error="loadError" :acting="acting" :show-lifecycle-actions="false" @reload="load">
				<template #header="{ record: header, headingId }">
					<div class="item-price-page__identity">
						<div><h1 class="erp-doc-title" :id="headingId">Item Price</h1><span class="erp-doc-id">{{ header.name }}</span></div>
						<DocumentStatusBadge :docstatus="header.docstatus" :label="header.workflow_state" />
						<div class="item-price-page__facts" role="region" aria-label="Item Price context" tabindex="0">
							<div><span>{{ fieldLabel("item_name", "Item") }}</span><strong :title="header.item_name">{{ header.item_name || "—" }}</strong></div>
							<div><span>{{ fieldLabel("supplier", "Supplier") }}</span><strong :title="header.supplier_name || header.supplier">{{ header.supplier_name || header.supplier || "—" }}</strong></div>
							<div><span>{{ fieldLabel("from_date", "From Date") }}</span><strong>{{ formatDate(header.from_date) }}</strong></div>
						</div>
					</div>
				</template>

				<template #header-actions>
					<DocumentActionStrip v-if="actions.length" :actions="actions" />
				</template>

				<template #fields>
					<DocumentOverview :fields="overviewFields" :definitions="ITEM_PRICE_SECTIONS" include-empty aria-label="Item Price overview" id-prefix="item-price-overview" />
					<section class="item-price-values" aria-labelledby="item-price-values-title">
						<header>
							<div class="item-price-values__icon" aria-hidden="true"><i class="pi pi-list" /></div>
							<div><h2 id="item-price-values-title">Price Values</h2><p>MOQ slabs with price and lead time</p></div>
						</header>
						<dl class="item-price-values__facts">
							<div><dt>{{ fieldLabel("depends_on_attribute", "Depends On Attribute") }}</dt><dd>{{ record.depends_on_attribute ? "Yes" : "No" }}</dd></div>
							<div v-if="record.depends_on_attribute"><dt>{{ fieldLabel("attribute", "Attribute") }}</dt><dd>{{ record.attribute || "—" }}</dd></div>
						</dl>
						<div class="item-price-values__body">
						<DataTable v-if="tiers.length" :value="tiers" size="small" scrollable class="erp-data-table item-price-values__table">
							<Column header="No." class="item-price-values__index"><template #body="{ index }">{{ index + 1 }}</template></Column>
							<Column v-if="record.depends_on_attribute" :header="tierLabel('attribute_value', 'Attribute Value')"><template #body="{ data }">{{ data.attribute_value_label || data.attribute_value || "—" }}</template></Column>
							<Column v-for="fieldname in NUMBER_COLUMNS" :key="fieldname" :header="tierLabel(fieldname, fieldname)" class="item-price-values__number"><template #body="{ data }">{{ formatTier(fieldname, data[fieldname]) }}</template></Column>
						</DataTable>
						<div v-else class="erp-empty-state"><span class="erp-empty-state__text">No price values.</span></div>
						</div>
					</section>
				</template>

				<template #rail>
					<section class="price-timeline">
						<header><span>Timeline</span><strong>{{ workspace.timeline?.length || 0 }}</strong></header>
						<div v-if="workspace.timeline?.length" class="price-timeline__list">
							<article v-for="entry in workspace.timeline" :key="entry.name">
								<div><strong>{{ entry.label }}</strong><small>{{ timelineDate(entry.creation) }}</small></div>
								<p>{{ entry.content }}</p>
								<small v-if="entry.by && !entry.content?.includes(entry.by)">{{ entry.by }}</small>
							</article>
						</div>
						<div v-else class="price-history__empty erp-empty-state erp-empty-state--compact"><span class="erp-empty-state__text">No timeline entries.</span></div>
					</section>
					<section class="price-history">
						<header><span>Versions</span><strong>{{ workspace.history?.length || 0 }}</strong></header>
						<div v-if="workspace.history?.length" class="price-history__list">
							<RouterLink v-for="entry in workspace.history" :key="entry.name" :to="historyPath(entry.name)">
								<div><strong>{{ entry.name }}</strong><DocumentStatusBadge :label="entry.workflow_state" /></div>
								<span>{{ formatDate(entry.from_date) }} → {{ entry.to_date ? formatDate(entry.to_date) : "Open" }}</span>
								<small v-if="itemPriceApprovedBy(entry)">Approved by {{ itemPriceApprovedBy(entry) }}</small>
							</RouterLink>
						</div>
						<div v-else class="price-history__empty erp-empty-state erp-empty-state--compact"><span class="erp-empty-state__text">No earlier versions.</span></div>
					</section>
				</template>
			</FabricDocumentWorkspace>
		</section>

		<ItemPriceActionDialog v-model:visible="actionVisible" :action="selectedAction" :busy="Boolean(acting)" @confirm="runWorkflowAction" />
		<DocumentConfirmationDialog v-model:visible="deleteVisible" title="Delete Item Price?" :message="`Delete ${pendingDelete?.name || priceId}? This cannot be undone.`" confirm-label="Delete Price" confirm-icon="pi pi-trash" severity="danger" :busy="Boolean(acting)" @confirm="deletePrice" />
		<DocumentErrorDialog :message="actionError" title="Item Price action failed" @dismiss="actionError = ''" />
	</DepartmentPage>
</template>

<script setup>
import Column from "primevue/column"
import DataTable from "primevue/datatable"
import { computed, ref, watch } from "vue"
import { RouterLink, useRouter } from "vue-router"

import { deleteItemPrice, executeItemPriceAction, getItemPriceWorkspace } from "../../api/purchase.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import DocumentActionStrip from "../../components/documents/DocumentActionStrip.vue"
import DocumentConfirmationDialog from "../../components/documents/DocumentConfirmationDialog.vue"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import DocumentOverview from "../../components/documents/DocumentOverview.vue"
import DocumentStatusBadge from "../../components/documents/DocumentStatusBadge.vue"
import { formatDocumentOverviewValue } from "../../utils/documentOverview.js"
import FabricDocumentWorkspace from "../fabric-store/FabricDocumentWorkspace.vue"
import { ITEM_PRICE_SECTIONS, PURCHASE_ROUTES, activePriceTiers, captureRecordTarget, isCurrentRecordRequest, itemPriceActionItems, itemPriceApprovedBy, itemPriceFieldLabel, itemPriceOverviewFields, itemPriceTierValue } from "./purchaseViews.js"
import ItemPriceActionDialog from "./ItemPriceActionDialog.vue"

const props = defineProps({ priceId: { type: String, required: true } })
const router = useRouter()
const workspace = ref({})
const loading = ref(true)
const loadError = ref("")
const actionError = ref("")
const acting = ref("")
const actionVisible = ref(false)
const deleteVisible = ref(false)
const selectedAction = ref(null)
const pendingDelete = ref(null)
let loadSequence = 0

const record = computed(() => workspace.value.record || {})
const NUMBER_COLUMNS = ["moq", "price", "lead_time"]
const overviewFields = computed(() => itemPriceOverviewFields(workspace.value))
const tiers = computed(() => activePriceTiers({ tiers: workspace.value.tiers }))
const actions = computed(() => {
	if (loading.value || loadError.value) return []
	return itemPriceActionItems(workspace.value, {
		workflow: openWorkflowAction,
		edit: editPrice,
		delete: openDelete,
	}).map((action) => ({ ...action, loading: acting.value === action.key, disabled: Boolean(acting.value) }))
})

async function load() {
	const sequence = ++loadSequence
	const requestedName = props.priceId
	loading.value = true
	loadError.value = ""
	actionError.value = ""
	workspace.value = {}
	actionVisible.value = false
	deleteVisible.value = false
	selectedAction.value = null
	pendingDelete.value = null
	try {
		const payload = await getItemPriceWorkspace(requestedName)
		if (isCurrentRecordRequest(requestedName, props.priceId, sequence, loadSequence)) workspace.value = payload || {}
	} catch (reason) {
		if (isCurrentRecordRequest(requestedName, props.priceId, sequence, loadSequence)) loadError.value = reason?.message || "Unable to load this Item Price."
	} finally {
		if (isCurrentRecordRequest(requestedName, props.priceId, sequence, loadSequence)) loading.value = false
	}
}

function openWorkflowAction(action) {
	const target = captureRecordTarget(record.value, props.priceId)
	selectedAction.value = { ...action, documentName: target.name, expectedModified: target.modified }
	actionVisible.value = true
}

async function runWorkflowAction() {
	const action = selectedAction.value
	if (!action?.documentName) return
	const sequence = loadSequence
	acting.value = `workflow-${String(action.action || "action").toLowerCase().replaceAll(" ", "-")}`
	actionError.value = ""
	try {
		const payload = await executeItemPriceAction(action.documentName, action.action, action.expectedModified)
		if (isCurrentRecordRequest(action.documentName, props.priceId, sequence, loadSequence)) {
			workspace.value = payload || {}
			actionVisible.value = false
			selectedAction.value = null
		}
	} catch (reason) {
		if (isCurrentRecordRequest(action.documentName, props.priceId, sequence, loadSequence)) actionError.value = reason?.message || `Unable to ${String(action.label || action.action).toLowerCase()} this Item Price.`
	} finally {
		acting.value = ""
	}
}

function editPrice() {
	router.push({ name: PURCHASE_ROUTES.itemPriceEdit, params: { priceId: props.priceId } })
}

function openDelete() {
	pendingDelete.value = captureRecordTarget(record.value, props.priceId)
	deleteVisible.value = true
}

async function deletePrice() {
	const target = pendingDelete.value
	if (!target?.name) return
	const sequence = loadSequence
	acting.value = "delete"
	actionError.value = ""
	try {
		await deleteItemPrice(target.name, target.modified)
		if (isCurrentRecordRequest(target.name, props.priceId, sequence, loadSequence)) {
			deleteVisible.value = false
			pendingDelete.value = null
			await router.replace({ name: PURCHASE_ROUTES.itemPrices })
		}
	} catch (reason) {
		if (isCurrentRecordRequest(target.name, props.priceId, sequence, loadSequence)) actionError.value = reason?.message || "Unable to delete this Item Price."
	} finally {
		acting.value = ""
	}
}

function historyPath(name) {
	return { name: PURCHASE_ROUTES.itemPrice, params: { priceId: name } }
}

function fieldLabel(fieldname, fallback) {
	return itemPriceFieldLabel(workspace.value.fields, fieldname, fallback)
}

function tierLabel(fieldname, fallback) {
	return itemPriceFieldLabel(workspace.value.tier_fields, fieldname, fallback)
}

function formatTier(fieldname, value) {
	return itemPriceTierValue(workspace.value.tier_fields?.[fieldname], value)
}

function formatDate(value) {
	return formatDocumentOverviewValue({ fieldtype: "Date", value })
}

function timelineDate(value) {
	if (!value) return ""
	const date = new Date(String(value).replace(" ", "T"))
	return Number.isNaN(date.getTime()) ? String(value) : new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date)
}

watch(() => props.priceId, load, { immediate: true })
</script>

<style scoped>
.item-price-frame { width: 100%; min-width: 0; }
.item-price-frame :deep(.fabric-document-workspace__rail) { overflow-y: auto; }
.item-price-page__identity { display: flex; min-width: 0; align-items: center; gap: 12px; }
.item-price-page__identity > div:first-child { display: grid; min-width: 0; gap: 2px; }
.item-price-page__identity h1 { margin: 0; color: var(--erp-text); }
.item-price-page__facts { display: flex; min-width: 0; align-items: center; gap: 18px; padding-left: 14px; border-left: 1px solid var(--erp-border); }
.item-price-page__facts > div { display: grid; min-width: 0; gap: 2px; }
.item-price-page__facts span, .price-history > header span, .price-timeline > header span {
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	font-weight: 600;
	letter-spacing: .03em;
	text-transform: uppercase;
}
.item-price-page__facts strong {
	overflow: hidden;
	max-width: 260px;
	color: var(--erp-text);
	font-size: var(--erp-font-size-md);
	font-weight: 600;
	text-overflow: ellipsis;
	white-space: nowrap;
	font-variant-numeric: tabular-nums;
}
.item-price-values { min-width: 0; overflow: hidden; border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); background: var(--erp-surface); box-shadow: var(--erp-shadow-card); }
.item-price-values > header { display: flex; align-items: center; gap: var(--erp-space-2); padding: 10px 16px; border-bottom: 1px solid var(--erp-border); background: var(--erp-surface-soft); }
.item-price-values__icon { display: inline-grid; place-items: center; color: var(--erp-accent-ink); font-size: var(--erp-font-size-table); }
.item-price-values > header > div:last-child { display: flex; min-width: 0; flex-wrap: wrap; align-items: baseline; gap: 2px var(--erp-space-2); }
.item-price-values h2 { margin: 0; color: var(--erp-text-secondary); font-size: var(--erp-font-size-table); font-weight: var(--erp-font-weight-bold); letter-spacing: .02em; }
.item-price-values header p { margin: 0; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.item-price-values__facts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 4px 28px; margin: 0; padding: 12px 18px 4px; }
.item-price-values__facts > div { display: flex; min-width: 0; flex-direction: column; gap: 2px; padding: 9px 0; border-bottom: 1px solid var(--erp-border); }
.item-price-values__facts dt { order: 2; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: var(--erp-font-weight-semibold); letter-spacing: .03em; text-transform: uppercase; }
.item-price-values__facts dd { order: 1; margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-section); font-weight: var(--erp-font-weight-semibold); }
.item-price-values__body { min-width: 0; padding: 12px 18px 18px; }
.item-price-values__table { overflow: hidden; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); }
.item-price-values__table :deep(.item-price-values__index) { width: 56px; color: var(--erp-text-muted); text-align: center; }
.item-price-values__table :deep(th.item-price-values__index .p-datatable-column-header-content) { justify-content: center; }
.item-price-values__table :deep(.item-price-values__number) { text-align: right; font-variant-numeric: tabular-nums; }
.item-price-values__table :deep(th.item-price-values__number .p-datatable-column-header-content) { justify-content: flex-end; }
.price-timeline, .price-history { display: grid; min-width: 0; border-bottom: 1px solid var(--erp-border); }
.price-history { border-bottom: 0; }
.price-history > header, .price-timeline > header { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 13px; border-bottom: 1px solid var(--erp-border-subtle); }
.price-history > header > strong, .price-timeline > header > strong { padding: 1px 7px; color: var(--erp-accent-ink); background: var(--erp-accent-soft); border-radius: var(--erp-pill-radius); font-size: var(--erp-font-size-min); }
.price-timeline__list, .price-history__list { display: grid; align-content: start; max-height: 320px; overflow: auto; overscroll-behavior: contain; }
.price-timeline__list article { display: grid; gap: 4px; padding: 10px 13px; border-bottom: 1px solid var(--erp-border-subtle); }
.price-timeline__list article:last-child, .price-history__list a:last-child { border-bottom: 0; }
.price-timeline__list article > div, .price-history__list a > div { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; }
.price-timeline__list strong, .price-timeline__list p, .price-history__list strong { color: var(--erp-text); font-size: var(--erp-font-size-caption); }
.price-timeline__list p { margin: 0; line-height: 1.35; }
.price-timeline__list small, .price-history__list span, .price-history__list small { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.price-history__list a { display: grid; gap: 5px; padding: 10px 13px; color: inherit; text-decoration: none; border-bottom: 1px solid var(--erp-border-subtle); }
.price-history__list a:hover { background: var(--erp-surface-muted); }
.price-history__empty { margin: 12px; }
@media (max-width: 1100px) { .item-price-page__identity { align-items: flex-start; flex-wrap: wrap; } }
@media (max-width: 900px) { .item-price-frame :deep(.fabric-document-workspace__rail) { grid-template-columns: 1fr; } }
@media (max-width: 650px) {
	.item-price-frame :deep(.fabric-document-workspace__header) { align-items: flex-start; }
	.item-price-page__identity { width: 100%; }
	.item-price-page__facts { display: grid; width: 100%; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px 16px; padding: 8px 0 0; border-top: 1px solid var(--erp-border); border-left: 0; }
	.item-price-values__facts { grid-template-columns: 1fr; padding: 8px 14px 4px; }
	.item-price-values__body { padding: 10px 14px 14px; }
}
</style>
