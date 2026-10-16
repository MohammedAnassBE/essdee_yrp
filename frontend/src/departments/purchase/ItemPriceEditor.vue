<template>
	<DepartmentPage title="Item Price" :back-to="backTo" :back-label="backLabel" :show-title="false" flat full-width inline-navigation>
		<div class="price-editor-page erp-workspace">
			<section class="price-editor erp-card erp-editor-shell" aria-label="Item Price editor" :aria-busy="loading">
				<header class="erp-editor-header price-editor__header">
					<div class="price-editor__leading">
						<InlinePageNavigation :title-target="headingId" />
						<div class="price-editor__identity"><span>Purchase · Item Price</span><div class="price-editor__title"><h1 class="erp-doc-title" :id="headingId">{{ hasSavedRecord ? effectiveName : "Create Price" }}</h1><DocumentStatusBadge v-if="editor.workflow?.state" :label="editor.workflow.state" /></div></div>
					</div>
					<div class="erp-editor-actions">
						<Button label="Cancel" icon="pi pi-times" severity="secondary" text :disabled="saving" @click="cancel" />
						<DocumentSaveButton v-if="!loading && !loadError" :show-submit="Boolean(saveAction)" :submit-label="`Save & ${saveAction?.label || ''}`" :loading="Boolean(saving)" :disabled="!canSave" @save="save(false)" @submit="save(true)" />
					</div>
				</header>

				<div v-if="loading" class="price-editor__loading"><Skeleton height="180px" /><Skeleton height="320px" /></div>
				<WorkspaceLoadError v-else-if="loadError" :message="loadError" :loading="loading" @retry="load" />
				<form v-else class="price-editor__body" @submit.prevent="save(false)">
					<Message v-if="editor.unit_mismatch" severity="error" :closable="false">{{ editor.unit_mismatch_message }}</Message>
					<div class="price-editor__card-grid">
						<section class="price-editor__section">
							<header><div><span>Item</span><h2>Item &amp; supplier</h2></div><small>Choose the Item and its supplier.</small></header>
							<div class="price-editor__fields">
								<LinkField :model-value="form.item_name" :label="`${fieldLabel('item_name', 'Item')} *`" doctype="Item" required :filters="itemFilters" :show-open-button="false" :disabled="Boolean(saving) || itemLoading" @update:model-value="changeItem" />
								<LinkField :model-value="form.supplier" :label="`${fieldLabel('supplier', 'Supplier')} *`" doctype="Supplier" required :filters="{ disabled: 0 }" :show-open-button="false" show-clear :disabled="Boolean(saving)" @update:model-value="changeSupplier" @select="supplierName = $event.label" />
								<label v-if="form.supplier" class="price-field"><span class="erp-field-label">{{ fieldLabel("supplier_name", "Supplier Name") }}</span><InputText :model-value="supplierName" disabled fluid /></label>
							</div>
						</section>
						<section class="price-editor__section">
							<header><div><span>Validity</span><h2>UOM &amp; validity</h2></div><small>UOM follows the Item.</small></header>
							<div class="price-editor__fields">
								<label class="price-field"><span class="erp-field-label">{{ fieldLabel("uom", "UOM") }}<span class="erp-required-mark" aria-hidden="true">*</span></span><InputText v-model="form.uom" disabled fluid /></label>
								<DateField v-model="form.from_date" :label="fieldLabel('from_date', 'From Date')" required :max-date="itemPriceDateLimit(form.to_date)" :disabled="Boolean(saving)" />
								<DateField v-model="form.to_date" :label="fieldLabel('to_date', 'To Date')" show-clear :min-date="itemPriceDateLimit(form.from_date)" :disabled="Boolean(saving)" />
							</div>
						</section>
						<section class="price-editor__section">
							<header><div><span>Tax</span><h2>Tax &amp; approval</h2></div><small>Approval is recorded by the workflow.</small></header>
							<div class="price-editor__fields">
								<label class="price-field"><span class="erp-field-label">{{ fieldLabel("tax", "Tax Slab") }}<span class="erp-required-mark" aria-hidden="true">*</span></span><Select v-model="form.tax" :options="editor.options?.tax_slabs || []" option-label="label" option-value="value" filter show-clear fluid :aria-label="fieldLabel('tax', 'Tax Slab')" :disabled="Boolean(saving)" /></label>
								<label v-if="editor.values?.approved_by" class="price-field"><span class="erp-field-label">{{ fieldLabel("approved_by", "Approved By") }}</span><InputText :model-value="editor.values.approved_by" disabled fluid /></label>
							</div>
						</section>
					</div>

					<section class="price-editor__section price-editor__values">
						<header>
							<div><span>Pricing</span><h2>Price Values</h2></div>
							<Button label="Add Row" icon="pi pi-plus" severity="secondary" outlined size="small" :disabled="Boolean(saving)" @click="addTier" />
						</header>
						<div class="price-editor__attribute">
							<div class="price-editor__check">
								<label><Checkbox v-model="dependsOnAttribute" binary input-id="item-price-depends-on-attribute" :disabled="Boolean(saving) || !editor.attributes?.length" /><span>{{ fieldLabel("depends_on_attribute", "Depends On Attribute") }}</span></label>
								<small v-if="attributeHint">{{ attributeHint }}</small>
							</div>
							<label v-if="dependsOnAttribute" class="price-field"><span class="erp-field-label">{{ fieldLabel("attribute", "Attribute") }}<span class="erp-required-mark" aria-hidden="true">*</span></span><Select :model-value="form.attribute" :options="editor.attributes || []" option-label="attribute" option-value="attribute" fluid :aria-label="fieldLabel('attribute', 'Attribute')" :disabled="Boolean(saving)" @update:model-value="changeAttribute" /></label>
						</div>
						<DataTable v-if="form.item_price_values.length" :value="form.item_price_values" data-key="key" size="small" scrollable class="erp-data-table price-values-grid">
							<Column header="No." class="price-values-grid__index"><template #body="{ index }">{{ index + 1 }}</template></Column>
							<Column v-if="dependsOnAttribute" class="price-values-grid__attribute">
								<template #header><span>{{ tierLabel("attribute_value", "Attribute Value") }}<span class="erp-required-mark" aria-hidden="true">*</span></span></template>
								<template #body="{ data, index }"><Select v-model="data.attribute_value" :options="attributeValues" option-label="label" option-value="name" filter fluid :aria-label="`${tierLabel('attribute_value', 'Attribute Value')} ${index + 1}`" :disabled="Boolean(saving) || !form.attribute" /></template>
							</Column>
							<Column v-for="fieldname in NUMBER_FIELDS" :key="fieldname" class="price-values-grid__number">
								<template #header><span>{{ tierLabel(fieldname, fieldname) }}<span class="erp-required-mark" aria-hidden="true">*</span></span></template>
								<template #body="{ data, index }"><InputNumber v-model="data[fieldname]" :min="0" :max-fraction-digits="tierPrecision(fieldname)" :use-grouping="false" fluid :aria-label="`${tierLabel(fieldname, fieldname)} ${index + 1}`" :disabled="Boolean(saving)" /></template>
							</Column>
							<Column class="price-values-grid__remove"><template #body="{ index }"><Button icon="pi pi-trash" severity="danger" text rounded :aria-label="`Remove row ${index + 1}`" :disabled="Boolean(saving)" @click="removeTier(index)" /></template></Column>
						</DataTable>
						<div v-else class="price-tier-empty">Add at least one row.</div>
					</section>
				</form>
			</section>
		</div>
		<DocumentConfirmationDialog v-model:visible="discardVisible" title="Discard unsaved changes?" message="Your unsaved Item Price changes will be lost." confirm-label="Discard Changes" cancel-label="Keep Editing" confirm-icon="pi pi-trash" severity="danger" @update:visible="discardVisibilityChanged" @confirm="discardChanges" />
		<DocumentErrorDialog :message="actionError" title="Item Price could not be saved" @dismiss="actionError = ''" />
	</DepartmentPage>
</template>

<script setup>
import Button from "primevue/button"
import Checkbox from "primevue/checkbox"
import Column from "primevue/column"
import DataTable from "primevue/datatable"
import InputNumber from "primevue/inputnumber"
import InputText from "primevue/inputtext"
import Message from "primevue/message"
import Select from "primevue/select"
import Skeleton from "primevue/skeleton"
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue"
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from "vue-router"

import { executeItemPriceAction, getItemPriceEditor, saveItemPrice } from "../../api/purchase.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import InlinePageNavigation from "../../components/navigation/InlinePageNavigation.vue"
import DateField from "../../components/common/DateField.vue"
import LinkField from "../../components/common/LinkField.vue"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import DocumentConfirmationDialog from "../../components/documents/DocumentConfirmationDialog.vue"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import DocumentSaveButton from "../../components/documents/DocumentSaveButton.vue"
import DocumentStatusBadge from "../../components/documents/DocumentStatusBadge.vue"
import { preserveListNavigationState } from "../../router/listDocumentNavigation.js"
import { PURCHASE_ROUTES, itemPriceAttributeHint, itemPriceAttributeValues, itemPriceCanSave, itemPriceDateLimit, itemPriceFieldLabel, itemPriceEditorRequestKey, itemPriceEditorValues, itemPriceSaveAction, itemPriceSaveValues, itemPriceTierPrecision, savedItemPriceIdentity } from "./purchaseViews.js"

const props = defineProps({ priceId: { type: String, default: "" } })
const headingId = "purchase-item-price-editor-title"
const route = useRoute()
const router = useRouter()
const editor = ref({})
const form = reactive(itemPriceEditorValues())
const loading = ref(true)
const itemLoading = ref(false)
const loadError = ref("")
const actionError = ref("")
const saving = ref("")
const persistedName = ref("")
const persistedModified = ref("")
const cleanSignature = ref("")
const discardVisible = ref(false)
const supplierName = ref("")
const NUMBER_FIELDS = ["moq", "price", "lead_time"]
let tierSequence = 0
let loadSequence = 0
let itemSequence = 0
let allowNavigation = false
let pendingNavigation = null
let isAlive = true

const isEdit = computed(() => Boolean(props.priceId || route.params.priceId))
const currentName = computed(() => String(props.priceId || route.params.priceId || ""))
const effectiveName = computed(() => currentName.value || persistedName.value)
const hasSavedRecord = computed(() => Boolean(effectiveName.value))
const backTo = computed(() => hasSavedRecord.value ? `/purchase/item-prices/${encodeURIComponent(effectiveName.value)}` : "/purchase/item-prices")
const backLabel = computed(() => hasSavedRecord.value ? "Item Price" : "Item Prices")
const itemFilters = { variant_of: ["is", "not set"], disabled: 0 }
const requestKey = computed(() => itemPriceEditorRequestKey({
	name: currentName.value,
	routeName: route.name,
	item: route.query.item,
	supplier: route.query.supplier,
}))
const formSignature = computed(() => JSON.stringify(itemPriceSaveValues(form, attributeValues.value)))
const dirty = computed(() => !loading.value && formSignature.value !== cleanSignature.value)
const dependsOnAttribute = computed({
	get: () => Boolean(Number(form.depends_on_attribute)),
	set: (value) => {
		form.depends_on_attribute = value ? 1 : 0
		if (!value) {
			form.attribute = ""
			for (const row of form.item_price_values) row.attribute_value = ""
		}
	},
})
const attributeValues = computed(() => itemPriceAttributeValues(editor.value.attributes || [], form.attribute))
const attributeHint = computed(() => itemPriceAttributeHint(form.item_name, editor.value.attributes || []))
const canSave = computed(() => !loading.value && !itemLoading.value && itemPriceCanSave(form))
const saveAction = computed(() => itemPriceSaveAction(editor.value))

function fieldLabel(fieldname, fallback) {
	return itemPriceFieldLabel(editor.value.fields, fieldname, fallback)
}

function tierLabel(fieldname, fallback) {
	return itemPriceFieldLabel(editor.value.tier_fields, fieldname, fallback)
}

function tierPrecision(fieldname) {
	return itemPriceTierPrecision(editor.value.tier_fields, fieldname)
}

function newTier(row = {}) {
	return { moq: row.moq ?? null, price: row.price ?? null, lead_time: row.lead_time ?? null, attribute_value: row.attribute_value || "", key: `tier-${++tierSequence}` }
}

function applyEditor(payload, requestedName = "", context = {}) {
	editor.value = payload || {}
	persistedName.value = requestedName
	persistedModified.value = requestedName ? payload?.modified || "" : ""
	const values = itemPriceEditorValues(payload?.values || {})
	Object.assign(form, values, { item_price_values: values.item_price_values.map(newTier) })
	supplierName.value = payload?.values?.supplier_name || ""
	if (!isEdit.value) {
		if (context.item) form.item_name = context.item
		if (context.supplier) form.supplier = context.supplier
	}
	if (!form.item_price_values.length) addTier()
	cleanSignature.value = formSignature.value
	allowNavigation = false
}

async function load() {
	const sequence = ++loadSequence
	const requestedName = currentName.value
	const requestedKey = requestKey.value
	const context = {
		item: requestedName ? "" : String(route.query.item || ""),
		supplier: requestedName ? "" : String(route.query.supplier || ""),
	}
	itemSequence += 1
	itemLoading.value = false
	loading.value = true
	loadError.value = ""
	actionError.value = ""
	persistedName.value = requestedName
	persistedModified.value = ""
	try {
		const payload = await getItemPriceEditor(requestedName || null, context.item || null)
		if (isAlive && sequence === loadSequence && requestKey.value === requestedKey) applyEditor(payload, requestedName, context)
	} catch (reason) {
		if (isAlive && sequence === loadSequence && requestKey.value === requestedKey) loadError.value = reason?.message || "Unable to load the Item Price editor."
	} finally {
		if (isAlive && sequence === loadSequence && requestKey.value === requestedKey) loading.value = false
	}
}

async function changeItem(item) {
	if ((item || "") === form.item_name) return
	const sequence = ++itemSequence
	form.item_name = item || ""
	form.uom = ""
	form.attribute = ""
	form.depends_on_attribute = 0
	for (const row of form.item_price_values) row.attribute_value = ""
	if (!item) {
		editor.value = { ...editor.value, attributes: [] }
		itemLoading.value = false
		return
	}
	itemLoading.value = true
	try {
		const payload = await getItemPriceEditor(null, item)
		if (sequence !== itemSequence || form.item_name !== item) return
		editor.value = { ...editor.value, attributes: payload?.attributes || [], options: payload?.options || editor.value.options }
		form.uom = payload?.values?.uom || ""
		if (!form.tax) form.tax = payload?.values?.tax || ""
		if (!form.from_date) form.from_date = payload?.values?.from_date || ""
	} catch (reason) {
		if (sequence === itemSequence) actionError.value = reason?.message || "Unable to load this Item's pricing options."
	} finally {
		if (sequence === itemSequence) itemLoading.value = false
	}
}

function changeSupplier(supplier) {
	form.supplier = supplier || ""
	if (!supplier) supplierName.value = ""
}

function changeAttribute(attribute) {
	form.attribute = attribute || ""
	for (const row of form.item_price_values) row.attribute_value = ""
}

function addTier() {
	form.item_price_values.push(newTier())
}

function removeTier(index) {
	form.item_price_values.splice(index, 1)
}

async function save(applyAction) {
	const action = applyAction ? saveAction.value : null
	if (!canSave.value || (applyAction && !action) || saving.value) return
	saving.value = applyAction ? "action" : "save"
	actionError.value = ""
	let savedIdentity = { name: "", modified: "" }
	try {
		let workspace = await saveItemPrice(itemPriceSaveValues(form, attributeValues.value), {
			name: effectiveName.value || null,
			expectedModified: persistedModified.value || editor.value.modified,
		})
		savedIdentity = savedItemPriceIdentity(workspace)
		if (!savedIdentity.name) throw new Error("The saved Item Price name was not returned.")
		persistedName.value = savedIdentity.name
		persistedModified.value = savedIdentity.modified
		editor.value = { ...editor.value, modified: savedIdentity.modified }
		cleanSignature.value = formSignature.value
		if (action) {
			if (!workspace?.actions?.some((row) => row.action === action.action)) throw new Error(`${action.label} is not allowed for this Item Price.`)
			workspace = await executeItemPriceAction(savedIdentity.name, action.action, savedIdentity.modified)
		}
		const record = workspace?.record || {}
		if (!record.name) throw new Error("The saved Item Price name was not returned.")
		allowNavigation = true
		await router.replace({
			name: PURCHASE_ROUTES.itemPrice,
			params: { priceId: record.name },
			state: preserveListNavigationState(record.name, record.modified),
		})
	} catch (reason) {
		const message = reason?.message || "Unable to save this Item Price."
		actionError.value = action && savedIdentity.name
			? `${savedIdentity.name} was saved, but ${action.label} could not be applied. ${message}`
			: message
	} finally {
		saving.value = ""
	}
}

function cancel() {
	router.push(backTo.value)
}

function discardVisibilityChanged(visible) {
	if (visible || !pendingNavigation) return
	pendingNavigation(false)
	pendingNavigation = null
}

function discardChanges() {
	discardVisible.value = false
	allowNavigation = true
	const next = pendingNavigation
	pendingNavigation = null
	next?.()
}

function guardUnsavedChanges(_to, _from, next) {
	if (allowNavigation || !dirty.value) return next()
	pendingNavigation = next
	discardVisible.value = true
}

function beforeUnload(event) {
	if (!dirty.value) return
	event.preventDefault()
	event.returnValue = ""
}

onBeforeRouteLeave(guardUnsavedChanges)
onBeforeRouteUpdate(guardUnsavedChanges)
onMounted(() => window.addEventListener("beforeunload", beforeUnload))
onBeforeUnmount(() => {
	isAlive = false
	loadSequence += 1
	itemSequence += 1
	if (pendingNavigation) pendingNavigation(false)
	pendingNavigation = null
	window.removeEventListener("beforeunload", beforeUnload)
})
watch(requestKey, load, { immediate: true })
</script>

<style scoped>
.price-editor-page { width: 100%; min-width: 0; }
.price-editor { display: flex; min-width: 0; min-height: calc(100dvh - var(--erp-shell-header-height) - 98px); flex-direction: column; gap: var(--erp-space-3); }
.price-editor__header > .price-editor__leading { display: flex; min-width: 0; align-items: center; gap: var(--erp-space-3); }
.price-editor__identity { min-width: 0; }
.price-editor__identity > span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 730; letter-spacing: .04em; text-transform: uppercase; }
.price-editor__header h1 { margin: 0; color: var(--erp-text); }
.price-editor__header .price-editor__identity h1 { overflow: hidden; min-width: 0; text-overflow: ellipsis; white-space: nowrap; }
.price-editor__title { display: flex; min-width: 0; align-items: center; gap: var(--erp-space-2); }
.price-editor__title :deep(.document-status-badge) { flex-shrink: 0; }
.price-editor__loading, .price-editor__body { display: grid; min-width: 0; gap: var(--erp-space-3); }
.price-editor__card-grid { display: grid; min-width: 0; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--erp-space-3); }
.price-editor__section { display: grid; min-width: 0; align-content: start; gap: var(--erp-space-3); padding: clamp(14px, 1.4vw, 22px); border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); background: var(--erp-surface); box-shadow: var(--erp-shadow-card); }
.price-editor__section > header { display: flex; flex-wrap: wrap; align-items: end; justify-content: space-between; gap: 4px 12px; }
.price-editor__section > header span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 600; letter-spacing: .04em; text-transform: uppercase; }
.price-editor__section h2 { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-section); }
.price-editor__section small { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.price-editor__fields { display: grid; min-width: 0; gap: 11px 14px; }
.price-field { display: grid; min-width: 0; gap: 6px; }
.price-editor__attribute { display: grid; grid-template-columns: repeat(2, minmax(0, 320px)); align-items: end; gap: 11px 28px; }
.price-editor__check { display: grid; min-height: var(--erp-control-height); align-content: center; gap: 3px; }
.price-editor__check label { display: flex; align-items: center; gap: 9px; color: var(--erp-text); font-size: var(--erp-font-size-table); font-weight: var(--erp-font-weight-medium); }
.price-values-grid { overflow: hidden; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); }
.price-values-grid :deep(td) { padding-block: 5px; }
.price-values-grid :deep(.price-values-grid__index) { width: 52px; color: var(--erp-text-muted); text-align: center; }
.price-values-grid :deep(.price-values-grid__attribute) { min-width: 200px; }
.price-values-grid :deep(.price-values-grid__number) { min-width: 130px; }
.price-values-grid :deep(.price-values-grid__number input) { text-align: right; font-variant-numeric: tabular-nums; }
.price-values-grid :deep(.price-values-grid__remove) { width: 52px; text-align: center; }
.price-tier-empty { display: grid; min-height: 90px; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); border: 1px dashed var(--erp-border-strong); border-radius: var(--erp-control-radius); place-items: center; }
@media (max-width: 1100px) { .price-editor__card-grid { grid-template-columns: 1fr; } .price-editor__fields { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 620px) {
	.price-editor__fields, .price-editor__attribute { grid-template-columns: 1fr; }
	.price-editor__identity > span { display: none; }
	.price-editor__section { padding: var(--erp-space-3); }
}
</style>
