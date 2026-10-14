<template>
	<DepartmentPage title="Item" back-to="/purchase/items" back-label="Items" :show-title="false" flat full-width inline-navigation>
		<section class="purchase-record erp-card" aria-label="Item page" :aria-busy="loading">
			<header class="purchase-record__header">
				<InlinePageNavigation title-target="purchase-item-title" show-document-navigation :current-name="itemId" document-label="Item" :navigation-disabled="loading || acting" />
				<div class="purchase-record__identity">
					<span>Purchase · Item</span>
					<div><h1 id="purchase-item-title">{{ itemId }}</h1><DocumentStatusBadge :label="hasAttributes ? 'Variants' : 'Plain'" /><DocumentStatusBadge v-if="Number(values.disabled)" label="Disabled" /></div>
				</div>
				<dl v-if="!loading && !loadError" class="purchase-record__facts">
					<div><dt>Item Group</dt><dd>{{ values.item_group || "—" }}</dd></div>
					<div><dt>UOM</dt><dd>{{ values.stock_uom || "—" }}</dd></div>
					<div><dt>Variants</dt><dd>{{ workspace.variant_count || 0 }}</dd></div>
				</dl>
				<DocumentActionStrip v-if="actions.length" :actions="actions" />
			</header>

			<div v-if="loading" class="purchase-record__loading"><Skeleton height="180px" /><Skeleton height="300px" /></div>
			<WorkspaceLoadError v-else-if="loadError" :message="loadError" :loading="loading" @retry="load" />
			<div v-else class="purchase-record__content">
				<section class="purchase-record-card">
					<header><div><span>Configuration</span><h2>Attributes</h2></div><strong>{{ values.attributes?.length || 0 }}</strong></header>
					<Message v-if="workspace.attributes_locked" severity="warn" :closable="false">{{ workspace.attribute_lock_message || "Locked: variants exist" }}</Message>
					<div v-if="values.attributes?.length" class="item-attributes">
						<div v-for="row in values.attributes" :key="row.attribute"><strong>{{ row.attribute }}</strong><div><span v-for="value in row.values" :key="value.name || value.label">{{ value.label || value }}</span></div></div>
					</div>
					<div v-else class="purchase-record-empty">No variant attributes. This is a plain item.</div>
				</section>

				<section class="purchase-record-card">
					<header>
						<div><span>Commercial</span><h2>Active prices</h2></div>
						<Button v-if="priceCapability?.can_create" label="Add price" icon="pi pi-plus" size="small" @click="addPrice" />
					</header>
					<DataTable v-if="workspace.active_prices?.length" :value="workspace.active_prices" size="small" scrollable class="active-prices-table">
						<Column field="supplier_name" header="Supplier"><template #body="{ data }"><RouterLink :to="pricePath(data.name)">{{ data.supplier_name || data.supplier || "—" }}</RouterLink></template></Column>
						<Column header="Valid"><template #body="{ data }">{{ dateRange(data.from_date, data.to_date) }}</template></Column>
						<Column field="attribute" header="Attribute"><template #body="{ data }">{{ data.attribute || "All" }}</template></Column>
					<Column header="Price tiers"><template #body="{ data }"><div class="active-price-tiers"><div v-for="(tier, index) in activePriceTiers(data)" :key="`${tier.attribute_value || 'all'}-${tier.moq}-${index}`"><strong v-if="data.depends_on_attribute">{{ tier.attribute_value_label || tier.attribute_value || "—" }}</strong><span>{{ tier.moq ?? 0 }} → {{ tier.price ?? "—" }}</span><small>{{ tier.lead_time ?? "—" }} days</small></div></div></template></Column>
					</DataTable>
					<div v-else class="purchase-record-empty">No active supplier prices.</div>
				</section>
			</div>
		</section>

		<DocumentConfirmationDialog v-model:visible="toggleVisible" :title="`${pendingToggle?.label || toggleLabel} Item?`" :message="`${pendingToggle?.label || toggleLabel} ${pendingToggle?.name || itemId}?`" :confirm-label="pendingToggle?.label || toggleLabel" :confirm-icon="pendingToggle?.disabled ? 'pi pi-check' : 'pi pi-ban'" :severity="pendingToggle?.disabled ? 'success' : 'danger'" :busy="acting" @confirm="toggleDisabled" />
		<DocumentErrorDialog :message="actionError" title="Item could not be updated" @dismiss="actionError = ''" />
	</DepartmentPage>
</template>

<script setup>
import Button from "primevue/button"
import Column from "primevue/column"
import DataTable from "primevue/datatable"
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import { computed, ref, watch } from "vue"
import { RouterLink, useRouter } from "vue-router"

import { getItemEditor, getPurchaseCapabilities, updateItem } from "../../api/purchase.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import DocumentActionStrip from "../../components/documents/DocumentActionStrip.vue"
import DocumentConfirmationDialog from "../../components/documents/DocumentConfirmationDialog.vue"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import DocumentStatusBadge from "../../components/documents/DocumentStatusBadge.vue"
import InlinePageNavigation from "../../components/navigation/InlinePageNavigation.vue"
import { PURCHASE_ROUTES, activePriceTiers, captureRecordTarget, isCurrentRecordRequest, itemSaveValues } from "./purchaseViews.js"

const props = defineProps({ itemId: { type: String, required: true } })
const router = useRouter()
const workspace = ref({})
const priceCapability = ref(null)
const loading = ref(true)
const loadError = ref("")
const actionError = ref("")
const toggleVisible = ref(false)
const acting = ref(false)
const pendingToggle = ref(null)
let loadSequence = 0

const values = computed(() => workspace.value.values || {})
const hasAttributes = computed(() => Boolean(values.value.attributes?.length))
const toggleLabel = computed(() => Number(values.value.disabled) ? "Enable" : "Disable")
const actions = computed(() => {
	if (loading.value || loadError.value || !workspace.value.permissions?.can_write) return []
	return [
		{ key: "edit", label: "Edit", icon: "pi pi-pencil", menuOnly: true, disabled: acting.value, command: editItem },
		{ key: "toggle", label: toggleLabel.value, icon: Number(values.value.disabled) ? "pi pi-check" : "pi pi-ban", menuOnly: true, disabled: acting.value, command: openToggle },
	]
})

async function load() {
	const sequence = ++loadSequence
	const requestedName = props.itemId
	loading.value = true
	loadError.value = ""
	actionError.value = ""
	workspace.value = {}
	priceCapability.value = null
	toggleVisible.value = false
	pendingToggle.value = null
	try {
		const [itemPayload, capabilities] = await Promise.all([getItemEditor(requestedName), getPurchaseCapabilities()])
		if (isCurrentRecordRequest(requestedName, props.itemId, sequence, loadSequence)) {
			workspace.value = itemPayload || {}
			priceCapability.value = capabilities?.sections?.item_prices || null
		}
	} catch (reason) {
		if (isCurrentRecordRequest(requestedName, props.itemId, sequence, loadSequence)) loadError.value = reason?.message || "Unable to load this Item."
	} finally {
		if (isCurrentRecordRequest(requestedName, props.itemId, sequence, loadSequence)) loading.value = false
	}
}

function editItem() {
	router.push({ name: PURCHASE_ROUTES.itemEdit, params: { itemId: props.itemId } })
}

function addPrice() {
	router.push({ name: PURCHASE_ROUTES.itemPriceNew, query: { item: props.itemId } })
}

function pricePath(name) {
	return { name: PURCHASE_ROUTES.itemPrice, params: { priceId: name } }
}

function openToggle() {
	const target = captureRecordTarget({ name: props.itemId, modified: workspace.value.modified }, props.itemId)
	pendingToggle.value = {
		...target,
		disabled: Number(values.value.disabled),
		label: Number(values.value.disabled) ? "Enable" : "Disable",
		values: itemSaveValues(values.value, { defaultSinglePrimary: false }),
	}
	toggleVisible.value = true
}

async function toggleDisabled() {
	const target = pendingToggle.value
	if (!target?.name) return
	const sequence = loadSequence
	acting.value = true
	actionError.value = ""
	try {
		const payload = await updateItem(target.name, {
			...target.values,
			disabled: target.disabled ? 0 : 1,
		}, target.modified)
		if (isCurrentRecordRequest(target.name, props.itemId, sequence, loadSequence)) {
			workspace.value = payload || {}
			toggleVisible.value = false
			pendingToggle.value = null
		}
	} catch (reason) {
		if (isCurrentRecordRequest(target.name, props.itemId, sequence, loadSequence)) actionError.value = reason?.message || `Unable to ${target.label.toLowerCase()} this Item.`
	} finally {
		acting.value = false
	}
}

function dateRange(fromDate, toDate) {
	return `${fromDate || "—"} → ${toDate || "Open"}`
}

watch(() => props.itemId, load, { immediate: true })
</script>

<style scoped>
.purchase-record { display: flex; width: min(1380px, 100%); min-width: 0; min-height: 560px; margin: 0 auto; overflow: hidden; flex-direction: column; border-top: 3px solid var(--erp-accent); }
.purchase-record__header { display: flex; min-width: 0; align-items: center; gap: 18px; padding: 13px clamp(16px, 2vw, 24px); border-bottom: 1px solid var(--erp-border); background: color-mix(in srgb, var(--erp-surface) 96%, var(--erp-accent-soft)); }
.purchase-record__identity { display: grid; min-width: 0; gap: 4px; }
.purchase-record__identity > span, .purchase-record-card header span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 750; letter-spacing: .045em; text-transform: uppercase; }
.purchase-record__identity > div { display: flex; min-width: 0; align-items: center; gap: 8px; }
.purchase-record__identity h1 { margin: 0; overflow: hidden; color: var(--erp-text); font-size: clamp(20px, 2vw, 25px); letter-spacing: -.025em; text-overflow: ellipsis; white-space: nowrap; }
.purchase-record__facts { display: flex; min-width: 0; margin: 0 0 0 auto; }
.purchase-record__facts div { display: grid; min-width: 90px; max-width: 180px; gap: 2px; padding: 0 12px; border-left: 1px solid var(--erp-border); }
.purchase-record__facts dt { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 720; text-transform: uppercase; }
.purchase-record__facts dd { margin: 0; overflow: hidden; color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 720; text-overflow: ellipsis; white-space: nowrap; }
.purchase-record__loading, .purchase-record__content { display: grid; gap: 16px; padding: clamp(14px, 2vw, 22px); }
.purchase-record__content { grid-template-columns: minmax(0, .8fr) minmax(0, 1.2fr); align-items: start; }
.purchase-record-card { display: grid; min-width: 0; gap: 14px; padding: 17px; border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); background: var(--erp-surface); box-shadow: var(--erp-shadow-xs); }
.purchase-record-card > header { display: flex; align-items: center; justify-content: space-between; gap: 14px; }
.purchase-record-card h2 { margin: 2px 0 0; color: var(--erp-text); font-size: 1rem; }
.purchase-record-card header > strong { display: grid; width: 34px; height: 34px; color: var(--erp-accent-hover); border-radius: 50%; background: var(--erp-accent-soft); place-items: center; }
.item-attributes { display: grid; gap: 10px; }
.item-attributes > div { display: grid; gap: 8px; padding: 11px; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); background: var(--erp-surface-muted); }
.item-attributes strong { color: var(--erp-text); font-size: var(--erp-font-size-caption); }
.item-attributes > div > div { display: flex; gap: 6px; flex-wrap: wrap; }
.item-attributes span { padding: 4px 8px; color: var(--erp-accent-hover); font-size: var(--erp-font-size-min); font-weight: 700; border: 1px solid color-mix(in srgb, var(--erp-accent) 20%, var(--erp-border)); border-radius: var(--erp-pill-radius); background: var(--erp-accent-soft); }
.purchase-record-empty { display: grid; min-height: 90px; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); border: 1px dashed var(--erp-border-strong); border-radius: var(--erp-control-radius); place-items: center; }
.active-prices-table { border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); overflow: hidden; }
.active-prices-table a { color: var(--erp-accent); font-weight: 700; text-decoration: none; }
.active-price-tiers { display: grid; gap: 5px; }
.active-price-tiers > div { display: grid; grid-template-columns: minmax(70px, auto) auto auto; align-items: baseline; gap: 8px; }
.active-price-tiers strong { color: var(--erp-text); font-size: var(--erp-font-size-min); }
.active-price-tiers span { color: var(--erp-accent-hover); font-size: var(--erp-font-size-caption); font-weight: 720; }
.active-price-tiers small { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); white-space: nowrap; }
@media (max-width: 980px) { .purchase-record__header { align-items: flex-start; flex-wrap: wrap; } .purchase-record__facts { width: 100%; margin: 0; order: 3; } .purchase-record__facts div:first-child { padding-left: 0; border-left: 0; } .purchase-record__content { grid-template-columns: 1fr; } }
@media (max-width: 620px) { .purchase-record__identity > div { align-items: flex-start; flex-wrap: wrap; } .purchase-record__header > :deep(.document-action-strip) { width: auto; margin-left: auto; } .purchase-record__facts { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); } .purchase-record__facts div { min-width: 0; padding-inline: 8px; } .purchase-record__facts dd { white-space: normal; } }
</style>
