<template>
	<DepartmentPage title="Item Price" back-to="/purchase/item-prices" back-label="Item Prices" :show-title="false" flat full-width inline-navigation>
		<section class="price-page erp-card" aria-label="Item Price page" :aria-busy="loading">
			<header class="price-page__header">
				<InlinePageNavigation title-target="item-price-title" show-document-navigation :current-name="priceId" document-label="Item Price" :navigation-disabled="loading || Boolean(acting)" />
				<div class="price-page__identity"><span>Purchase · Item Price</span><div><h1 id="item-price-title">{{ priceId }}</h1><DocumentStatusBadge :label="record.workflow_state || 'Draft'" /></div></div>
				<dl v-if="!loading && !loadError" class="price-page__facts">
					<div><dt>Item</dt><dd>{{ record.item_name || "—" }}</dd></div>
					<div><dt>Supplier</dt><dd>{{ record.supplier_name || record.supplier || "—" }}</dd></div>
					<div><dt>Validity</dt><dd>{{ dateRange(record.from_date, record.to_date) }}</dd></div>
				</dl>
				<DocumentActionStrip v-if="actions.length" :actions="actions" />
			</header>

			<div v-if="loading" class="price-page__loading"><Skeleton height="220px" /><Skeleton height="280px" /></div>
			<WorkspaceLoadError v-else-if="loadError" :message="loadError" :loading="loading" @retry="load" />
			<div v-else class="price-page__content">
				<main class="price-page__main">
					<section class="price-summary-card">
						<header><div><span>Commercial terms</span><h2>Price slabs</h2></div><strong>{{ record.uom || "—" }}</strong></header>
						<div class="price-summary-facts"><div><span>Tax slab</span><strong>{{ record.tax || "—" }}</strong></div><div><span>Attribute</span><strong>{{ record.depends_on_attribute ? record.attribute : "Not used" }}</strong></div><div><span>Approved by</span><strong>{{ record.approved_by || "—" }}</strong></div></div>
						<div v-if="tierGroups.length" class="price-groups">
							<section v-for="group in tierGroups" :key="group.key" class="price-group">
								<h3 v-if="record.depends_on_attribute">{{ group.label }}</h3>
								<DataTable :value="group.rows" size="small" scrollable>
									<Column field="moq" header="From qty" />
									<Column field="price" header="Price (excl. tax)" />
									<Column field="lead_time" header="Lead time"><template #body="{ data }">{{ data.lead_time }} days</template></Column>
								</DataTable>
							</section>
						</div>
						<div v-else class="price-page-empty">No price slabs.</div>
					</section>
				</main>

				<aside class="price-rail" aria-label="Item Price timeline and versions">
					<section class="price-timeline">
						<header><span>Timeline</span><strong>{{ workspace.timeline?.length || 0 }}</strong></header>
						<div v-if="workspace.timeline?.length" class="price-timeline__list">
							<article v-for="entry in workspace.timeline" :key="entry.name">
								<div><strong>{{ entry.label }}</strong><small>{{ timelineDate(entry.creation) }}</small></div>
								<p>{{ entry.content }}</p>
								<span v-if="entry.by">{{ entry.by }}</span>
							</article>
						</div>
						<div v-else class="price-history__empty">No timeline entries.</div>
					</section>
					<section class="price-history">
						<header><span>Versions</span><strong>{{ workspace.history?.length || 0 }}</strong></header>
						<div v-if="workspace.history?.length" class="price-history__list">
							<RouterLink v-for="entry in workspace.history" :key="entry.name" :to="historyPath(entry.name)">
								<div><strong>{{ entry.name }}</strong><DocumentStatusBadge :label="entry.workflow_state || 'Draft'" /></div>
								<span>{{ dateRange(entry.from_date, entry.to_date) }}</span>
								<small v-if="entry.approved_by">Approved by {{ entry.approved_by }}</small>
							</RouterLink>
						</div>
						<div v-else class="price-history__empty">No earlier versions.</div>
					</section>
				</aside>
			</div>
		</section>

		<ItemPriceActionDialog v-model:visible="actionVisible" :action="selectedAction" :busy="Boolean(acting)" @confirm="runWorkflowAction" />
		<DocumentConfirmationDialog v-model:visible="deleteVisible" title="Delete draft Item Price?" :message="`Delete ${pendingDelete?.name || priceId}? This cannot be undone.`" confirm-label="Delete Price" confirm-icon="pi pi-trash" severity="danger" :busy="Boolean(acting)" @confirm="deletePrice" />
		<DocumentErrorDialog :message="actionError" title="Item Price action failed" @dismiss="actionError = ''" />
	</DepartmentPage>
</template>

<script setup>
import Column from "primevue/column"
import DataTable from "primevue/datatable"
import Skeleton from "primevue/skeleton"
import { computed, ref, watch } from "vue"
import { RouterLink, useRouter } from "vue-router"

import { deleteItemPrice, executeItemPriceAction, getItemPriceWorkspace } from "../../api/purchase.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import DocumentActionStrip from "../../components/documents/DocumentActionStrip.vue"
import DocumentConfirmationDialog from "../../components/documents/DocumentConfirmationDialog.vue"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import DocumentStatusBadge from "../../components/documents/DocumentStatusBadge.vue"
import InlinePageNavigation from "../../components/navigation/InlinePageNavigation.vue"
import { PURCHASE_ROUTES, captureRecordTarget, isCurrentRecordRequest, itemPriceActionItems, itemPriceGroups } from "./purchaseViews.js"
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
const tierGroups = computed(() => itemPriceGroups(workspace.value.tiers || []))
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

function dateRange(fromDate, toDate) {
	return `${fromDate || "—"} → ${toDate || "Open"}`
}

function timelineDate(value) {
	if (!value) return ""
	const date = new Date(String(value).replace(" ", "T"))
	return Number.isNaN(date.getTime()) ? String(value) : new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date)
}

watch(() => props.priceId, load, { immediate: true })
</script>

<style scoped>
.price-page { display: flex; width: min(1380px, 100%); min-width: 0; min-height: 580px; margin: 0 auto; overflow: hidden; flex-direction: column; border-top: 3px solid var(--erp-accent); }
.price-page__header { display: flex; min-width: 0; align-items: center; gap: 18px; padding: 13px clamp(16px, 2vw, 24px); border-bottom: 1px solid var(--erp-border); background: color-mix(in srgb, var(--erp-surface) 96%, var(--erp-accent-soft)); }
.price-page__identity { display: grid; min-width: 0; gap: 4px; }
.price-page__identity > span, .price-summary-card header span, .price-history > header span, .price-timeline > header span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 750; letter-spacing: .045em; text-transform: uppercase; }
.price-page__identity > div { display: flex; min-width: 0; align-items: center; gap: 8px; }
.price-page__identity h1 { margin: 0; overflow: hidden; color: var(--erp-text); font-size: clamp(20px, 2vw, 25px); letter-spacing: -.025em; text-overflow: ellipsis; white-space: nowrap; }
.price-page__facts { display: flex; min-width: 0; margin: 0 0 0 auto; }
.price-page__facts div { display: grid; min-width: 110px; max-width: 210px; gap: 2px; padding: 0 12px; border-left: 1px solid var(--erp-border); }
.price-page__facts dt { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 720; text-transform: uppercase; }
.price-page__facts dd { margin: 0; overflow: hidden; color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 720; text-overflow: ellipsis; white-space: nowrap; }
.price-page__loading, .price-page__content { min-width: 0; padding: clamp(14px, 2vw, 22px); }
.price-page__loading { display: grid; gap: 16px; }
.price-page__content { display: grid; grid-template-columns: minmax(0, 1fr) minmax(260px, 290px); align-items: start; gap: 16px; }
.price-summary-card, .price-history, .price-timeline { display: grid; min-width: 0; gap: 14px; border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); background: var(--erp-surface); box-shadow: var(--erp-shadow-xs); }
.price-summary-card { padding: 17px; }
.price-summary-card > header, .price-history > header, .price-timeline > header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.price-summary-card h2 { margin: 2px 0 0; color: var(--erp-text); font-size: 1rem; }
.price-summary-card > header > strong, .price-history > header > strong, .price-timeline > header > strong { color: var(--erp-accent-hover); font-size: var(--erp-font-size-caption); }
.price-summary-facts { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); overflow: hidden; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); background: var(--erp-border); gap: 1px; }
.price-summary-facts > div { display: grid; min-height: 58px; align-content: center; gap: 3px; padding: 9px 11px; background: var(--erp-surface-muted); }
.price-summary-facts span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 720; text-transform: uppercase; }
.price-summary-facts strong { color: var(--erp-text); font-size: var(--erp-font-size-caption); }
.price-groups { display: grid; gap: 12px; }
.price-group { display: grid; gap: 7px; overflow: hidden; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); }
.price-group h3 { margin: 0; padding: 9px 11px 2px; color: var(--erp-accent-hover); font-size: var(--erp-font-size-caption); }
.price-rail { display: grid; min-width: 0; gap: 16px; }
.price-history, .price-timeline { gap: 0; overflow: hidden; }
.price-history > header, .price-timeline > header { padding: 13px; border-bottom: 1px solid var(--erp-border); }
.price-timeline__list { display: grid; }
.price-timeline__list article { display: grid; gap: 5px; padding: 11px 13px; border-bottom: 1px solid var(--erp-border); }
.price-timeline__list article:last-child { border-bottom: 0; }
.price-timeline__list article > div { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; }
.price-timeline__list strong, .price-timeline__list p { color: var(--erp-text); font-size: var(--erp-font-size-caption); }
.price-timeline__list p { margin: 0; line-height: 1.35; }
.price-timeline__list small, .price-timeline__list span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.price-history__list { display: grid; }
.price-history__list a { display: grid; gap: 6px; padding: 12px 13px; color: inherit; text-decoration: none; border-bottom: 1px solid var(--erp-border); }
.price-history__list a:last-child { border-bottom: 0; }
.price-history__list a:hover { background: var(--erp-surface-muted); }
.price-history__list a > div { display: flex; align-items: center; justify-content: space-between; gap: 6px; }
.price-history__list strong { color: var(--erp-text); font-size: var(--erp-font-size-caption); }
.price-history__list span, .price-history__list small { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.price-history__empty, .price-page-empty { display: grid; min-height: 90px; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); place-items: center; }
@media (max-width: 1050px) { .price-page__header { align-items: flex-start; flex-wrap: wrap; } .price-page__facts { width: 100%; margin: 0; order: 3; } .price-page__facts div:first-child { padding-left: 0; border-left: 0; } .price-page__content { grid-template-columns: 1fr; } .price-rail { grid-template-columns: repeat(2, minmax(0, 1fr)); } .price-history__list a:nth-child(odd) { border-right: 1px solid var(--erp-border); } }
@media (max-width: 650px) { .price-page__identity > div { align-items: flex-start; flex-wrap: wrap; } .price-page__header > :deep(.document-action-strip) { width: auto; margin-left: auto; } .price-page__facts, .price-summary-facts, .price-history__list, .price-rail { grid-template-columns: 1fr; } .price-page__facts div { min-width: 0; padding: 7px 0; border-top: 1px solid var(--erp-border); border-left: 0; } .price-page__facts dd { white-space: normal; } .price-history__list a:nth-child(odd) { border-right: 0; } }
</style>
