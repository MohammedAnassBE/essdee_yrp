<template>
	<DepartmentPage title="Item" back-to="/purchase/items" back-label="Items" :show-title="false" flat full-width inline-navigation>
		<div class="purchase-record-page erp-workspace">
		<section class="purchase-record erp-card" aria-label="Item page" :aria-busy="loading">
			<header class="purchase-record__header erp-page-header">
				<InlinePageNavigation title-target="purchase-item-title" show-document-navigation :current-name="itemId" document-label="Item" :navigation-disabled="loading || acting" />
				<div class="purchase-record__identity">
					<span>Purchase · Item</span>
					<div><h1 class="erp-doc-title" id="purchase-item-title">{{ itemId }}</h1><DocumentStatusBadge :label="hasAttributes ? 'Variants' : 'Plain'" /><DocumentStatusBadge v-if="Number(values.disabled)" label="Disabled" /></div>
				</div>
				<dl v-if="!loading && !loadError" class="purchase-record__facts">
					<div v-if="values.name && values.name !== itemId"><dt>{{ fieldLabel("name", "Item Name") }}</dt><dd>{{ values.name }}</dd></div>
					<div><dt>{{ fieldLabel("item_group", "Item Group") }}</dt><dd>{{ values.item_group || "—" }}</dd></div>
					<div><dt>{{ fieldLabel("stock_uom", "Default Unit of Measure") }}</dt><dd>{{ values.stock_uom || "—" }}</dd></div>
					<div v-if="hasAttributes"><dt>{{ fieldLabel("primary_attribute", "Primary Attribute") }}</dt><dd>{{ values.primary_attribute || "—" }}</dd></div>
					<div v-if="hasAttributes"><dt>{{ fieldLabel("dependent_attribute", "Dependent Attribute") }}</dt><dd>{{ values.dependent_attribute || "—" }}</dd></div>
					<div><dt>Variants</dt><dd>{{ workspace.variant_count || 0 }}</dd></div>
				</dl>
				<DocumentDeleteButton doctype="Item" :name="itemId" :docstatus="values.docstatus" :disabled="loading || acting" redirect-to="/purchase/items" />
					<DocumentPrintButton doctype="Item" :name="itemId" :docstatus="values.docstatus" :disabled="loading || acting" />
					<DocumentActionStrip class="erp-page-header__actions" v-if="actions.length" :actions="actions" />
			</header>

			<div v-if="loading" class="purchase-record__loading"><Skeleton height="180px" /><Skeleton height="300px" /></div>
			<WorkspaceLoadError v-else-if="loadError" :message="loadError" :loading="loading" @retry="load" />
			<div v-else class="purchase-record__content">
				<Message v-for="message in stageMessages" :key="message" severity="error" :closable="false">{{ message }}</Message>
				<Message v-for="warning in tableWarnings" :key="warning" severity="warn" :closable="false">{{ warning }}</Message>
				<section class="purchase-record-card">
					<header><div><span>Configuration</span><h2>Attributes</h2></div><strong>{{ values.attributes?.length || 0 }}</strong></header>
					<Message class="erp-attention-note" v-if="workspace.attributes_locked" severity="warn" :closable="false">{{ workspace.attribute_lock_message || "Locked: variants exist" }}</Message>
					<ItemAttributeValues v-if="values.attributes?.length" :attributes="values.attributes" />
					<div v-else class="purchase-record-empty">No variant attributes. This is a plain item.</div>
					<ItemDependentAttributeTable v-if="values.dependent_attribute && dependentRows.length" :dependent-attribute="values.dependent_attribute" :rows="dependentRows" :attributes="combinationAttributes" :problems="stageProblems" />
				</section>
				<ItemUomConversions :values="values" :field="workspace.fields?.uoms" />
				<ItemAdditionalParameters :values="values" :field="workspace.fields?.additional_parameters" :problems="parameterProblems" />
				<ItemMasterFields part="details" :values="values" :fields="workspace.fields" />
				<ItemYarnRatio v-if="Number(values.is_cloth_item)" :values="values" :field="workspace.fields?.yarn_ratio_details" />

				<section class="purchase-record-card">
					<header>
						<div><span>Commercial</span><h2>Item Prices</h2></div>
						<Button v-if="priceCapability?.can_create" label="Add price" icon="pi pi-plus" severity="secondary" outlined size="small" @click="addPrice" />
					</header>
					<DataTable v-if="itemPrices.length" :value="itemPrices" size="small" scrollable row-hover class="item-prices-table erp-data-table" @row-click="openPrice($event.data)">
						<Column field="name" header="Item Price"><template #body="{ data }"><RouterLink :to="pricePath(data.name)" @click.stop>{{ data.name }}</RouterLink></template></Column>
						<Column field="supplier_name" header="Supplier"><template #body="{ data }">{{ data.supplier_name || data.supplier || "—" }}</template></Column>
						<Column header="Status"><template #body="{ data }"><span class="item-price-status"><DocumentStatusBadge :label="data.workflow_state" :docstatus="data.docstatus" /><small v-if="data.is_current">Current</small></span></template></Column>
						<Column header="Valid"><template #body="{ data }">{{ dateRange(data.from_date, data.to_date) }}</template></Column>
						<Column field="uom" header="UOM"><template #body="{ data }">{{ data.uom || "—" }}</template></Column>
						<Column header="Price slabs"><template #body="{ data }"><div class="active-price-tiers"><div v-for="(tier, index) in activePriceTiers(data)" :key="`${tier.attribute_value || 'all'}-${tier.moq}-${index}`"><strong v-if="data.depends_on_attribute">{{ tier.attribute_value_label || tier.attribute_value || "—" }}</strong><span>{{ tier.moq ?? 0 }} → {{ tier.price ?? "—" }}</span><small>{{ tier.lead_time ?? "—" }} days</small></div></div></template></Column>
					</DataTable>
					<div v-else class="purchase-record-empty">No Item Prices for this item.</div>
				</section>
				<ItemMasterFields part="description" :values="values" :fields="workspace.fields" />
			</div>
		</section>

		</div>
		<DocumentConfirmationDialog v-model:visible="toggleVisible" :title="`${pendingToggle?.label || toggleLabel} Item?`" :message="`${pendingToggle?.label || toggleLabel} ${pendingToggle?.name || itemId}?`" :confirm-label="pendingToggle?.label || toggleLabel" :confirm-icon="pendingToggle?.disabled ? 'pi pi-check' : 'pi pi-ban'" :severity="pendingToggle?.disabled ? 'success' : 'danger'" :busy="acting" @confirm="toggleDisabled" />
		<DocumentErrorDialog :message="actionError" title="Item could not be updated" @dismiss="actionError = ''" />
	</DepartmentPage>
</template>

<script setup>
import DocumentPrintButton from "../../components/documents/DocumentPrintButton.vue"
import DocumentDeleteButton from "../../components/documents/DocumentDeleteButton.vue"
import Button from "primevue/button"
import Column from "primevue/column"
import DataTable from "primevue/datatable"
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import { computed, ref, watch } from "vue"
import { RouterLink, useRouter } from "vue-router"

import { getItemEditor, getPurchaseCapabilities, setItemDisabled } from "../../api/purchase.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import DocumentActionStrip from "../../components/documents/DocumentActionStrip.vue"
import DocumentConfirmationDialog from "../../components/documents/DocumentConfirmationDialog.vue"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import DocumentStatusBadge from "../../components/documents/DocumentStatusBadge.vue"
import InlinePageNavigation from "../../components/navigation/InlinePageNavigation.vue"
import { formatDocumentOverviewValue } from "../../utils/documentOverview.js"
import ItemAttributeValues from "./item/ItemAttributeValues.vue"
import ItemDependentAttributeTable from "./item/ItemDependentAttributeTable.vue"
import ItemAdditionalParameters from "./item/ItemAdditionalParameters.vue"
import ItemMasterFields from "./item/ItemMasterFields.vue"
import ItemUomConversions from "./item/ItemUomConversions.vue"
import ItemYarnRatio from "./item/ItemYarnRatio.vue"
import { duplicateParameterProblems, itemTableWarnings, stageAttributeProblems, stageConversionProblems, stageVariantNameProblems, uniqueProblemMessages } from "./item/itemTables.js"
import { PURCHASE_ROUTES, activePriceTiers, captureRecordTarget, dependentDetailRows, isCurrentRecordRequest, itemCombinationAttributes, itemEditorValues } from "./purchaseViews.js"

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
const itemPrices = computed(() => workspace.value.item_prices || [])
const dependentRows = computed(() => dependentDetailRows(itemEditorValues(values.value), values.value.stock_uom))
const stageProblems = computed(() => [...stageConversionProblems(values.value), ...stageAttributeProblems(values.value), ...stageVariantNameProblems(values.value)])
const stageMessages = computed(() => uniqueProblemMessages(stageProblems.value))
const parameterProblems = computed(() => duplicateParameterProblems(values.value.additional_parameters))
const tableWarnings = computed(() => itemTableWarnings(values.value, workspace.value))
const combinationAttributes = computed(() => itemCombinationAttributes(values.value, workspace.value.options?.numeric_attributes))
const toggleLabel = computed(() => Number(values.value.disabled) ? "Enable" : "Disable")
const actions = computed(() => {
	if (loading.value || loadError.value || !workspace.value.permissions?.can_write) return []
	return [
		{ key: "edit", label: "Edit", icon: "pi pi-pencil", primary: true, disabled: acting.value, command: editItem },
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

function fieldLabel(fieldname, fallback) {
	return workspace.value.fields?.[fieldname]?.label || fallback
}

function openPrice(price) {
	router.push(pricePath(price.name))
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
		const payload = await setItemDisabled(target.name, target.disabled ? 0 : 1, target.modified)
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
	const format = (value) => formatDocumentOverviewValue({ fieldtype: "Date", value })
	return `${fromDate ? format(fromDate) : "—"} → ${toDate ? format(toDate) : "Open"}`
}

watch(() => props.itemId, load, { immediate: true })
</script>

<style scoped>
.purchase-record-page { width: 100%; min-width: 0; }
.purchase-record {
	display: flex;
	width: 100%;
	min-width: 0;
	overflow: hidden;
	flex-direction: column;
	border: 0;
	background: transparent;
	box-shadow: none;
}
.purchase-record__header {
	padding: 13px 0;
	margin-bottom: 0;
	border-bottom: 1px solid var(--erp-border);
	background: var(--erp-bg);
	box-shadow: none;
}
.purchase-record__identity { display: grid; min-width: 0; gap: 4px; }
.purchase-record-card header span {
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	font-weight: 700;
	letter-spacing: .045em;
	text-transform: uppercase;
}
.purchase-record__identity > span {
 color: var(--erp-text-muted);
 font-size: var(--erp-font-size-min);
 font-weight: var(--erp-font-weight-semibold);
 letter-spacing: .06em;
 text-transform: uppercase;
}
.purchase-record__identity > div { display: flex; min-width: 0; align-items: center; gap: 8px; }
.purchase-record__identity h1 {
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
}
.purchase-record__facts { display: flex; min-width: 0; margin: 0 0 0 auto; }
.purchase-record__facts div { display: grid; min-width: 90px; max-width: 180px; gap: 2px; padding: 0 12px; border-left: 1px solid var(--erp-border); }
.purchase-record__facts dt {
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	font-weight: var(--erp-font-weight-semibold);
	letter-spacing: .03em;
	text-transform: uppercase;
}
.purchase-record__facts dd {
	margin: 0;
	overflow: hidden;
	color: var(--erp-text);
	font-size: var(--erp-font-size-table);
	font-weight: var(--erp-font-weight-semibold);
	text-overflow: ellipsis;
	white-space: nowrap;
}
.purchase-record__loading, .purchase-record__content { display: grid; gap: 16px; padding: clamp(14px, 2vw, 22px) 0 14px; }
.purchase-record__content { grid-template-columns: minmax(0, 1fr); align-items: start; }
.purchase-record-card { display: grid; min-width: 0; gap: 14px; padding: 17px; border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); background: var(--erp-surface); box-shadow: var(--erp-shadow-xs); }
.purchase-record-card > header { display: flex; align-items: center; justify-content: space-between; gap: 14px; }
.purchase-record-card h2 {
	margin: 2px 0 0;
	color: var(--erp-text);
	font-size: var(--erp-font-size-section);
}
.purchase-record-card header > strong { display: grid; width: 34px; height: 34px; color: var(--erp-accent-hover); border-radius: 50%; background: var(--erp-accent-soft); place-items: center; }
.purchase-record-empty { display: grid; min-height: 90px; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); border: 1px dashed var(--erp-border-strong); border-radius: var(--erp-control-radius); place-items: center; }
.item-prices-table :deep(tbody > tr) { cursor: pointer; }
.item-price-status { display: inline-flex; align-items: center; gap: var(--erp-space-2); white-space: nowrap; }
.item-price-status small { color: var(--erp-success-text); font-size: var(--erp-font-size-min); font-weight: 700; text-transform: uppercase; }
.item-prices-table {
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-control-radius);
	overflow: hidden;
}
.item-prices-table a {
	color: var(--erp-accent-ink);
	font-weight: 600;
	text-decoration: none;
}
.active-price-tiers { display: grid; gap: 5px; }
.active-price-tiers > div { display: grid; grid-template-columns: minmax(70px, auto) auto auto; align-items: baseline; gap: 8px; }
.active-price-tiers strong { color: var(--erp-text); font-size: var(--erp-font-size-min); }
.active-price-tiers span {
	color: var(--erp-text);
	font-size: var(--erp-font-size-caption);
	font-weight: 600;
	font-variant-numeric: tabular-nums;
}
.active-price-tiers small { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); white-space: nowrap; }
@media (max-width: 980px) { .purchase-record__header { align-items: flex-start; flex-wrap: wrap; } .purchase-record__facts { width: 100%; margin: 0; order: 3; } .purchase-record__facts div:first-child { padding-left: 0; border-left: 0; } .purchase-record__content { grid-template-columns: 1fr; } }
@media (max-width: 620px) {
	.purchase-record__header {
		display: grid;
		grid-template-columns: auto minmax(0, 1fr);
		align-items: center;
		gap: 6px 10px;
		padding: 8px 0;
	}
	.purchase-record__header:has(> .document-action-strip) > .purchase-record__identity { grid-column: 1 / -1; grid-row: 2; }
	.purchase-record__header > :deep(.document-action-strip) { grid-column: 2; grid-row: 1; width: auto; justify-self: end; }
	.purchase-record__identity > span { display: none; }
	.purchase-record__identity :deep(.document-status-badge) { flex-shrink: 0; }
	.purchase-record__facts { display: grid; grid-column: 1 / -1; grid-template-columns: repeat(3, minmax(0, 1fr)); }
	.purchase-record__facts div { min-width: 0; padding-inline: 8px; }
	.purchase-record__facts dd { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; white-space: normal; }
	.purchase-record-card {
		padding: var(--erp-space-3);
	}
}
</style>
