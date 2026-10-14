<template>
	<DepartmentPage title="Item Price" :back-to="backTo" :back-label="backLabel" :show-title="false" flat full-width inline-navigation>
		<div class="price-editor-page erp-workspace">
			<section class="price-editor erp-card erp-editor-shell" aria-label="Item Price editor" :aria-busy="loading">
				<header class="erp-editor-header price-editor__header">
					<div class="price-editor__leading">
						<InlinePageNavigation :title-target="headingId" />
						<div class="price-editor__identity"><span>Purchase · Item Price</span><div class="price-editor__title"><h1 :id="headingId">{{ hasSavedRecord ? effectiveName : "Create Price" }}</h1><DocumentStatusBadge v-if="editor.workflow?.state" :label="editor.workflow.state" /></div></div>
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
					<section class="price-form-section">
						<header><div><span>WHAT &amp; WHEN</span><h2>Item, supplier, tax &amp; validity</h2></div></header>
						<div class="price-form-section__content">
							<div class="price-form-grid">
								<LinkField class="price-field--required-link" :model-value="form.item_name" label="Item" doctype="Item" required :filters="itemFilters" :show-open-button="false" :disabled="Boolean(saving) || hasSavedRecord || itemLoading" @update:model-value="changeItem" />
								<LinkField class="price-field--required-link" v-model="form.supplier" label="Supplier" doctype="Supplier" required :filters="{ disabled: 0 }" :show-open-button="false" show-clear :disabled="Boolean(saving)" />
								<label class="price-field"><span>Unit</span><InputText v-model="form.uom" disabled fluid /></label>
								<label class="price-field"><span>Tax slab <b>*</b></span><Select v-model="form.tax" :options="editor.options?.tax_slabs || []" option-label="label" option-value="value" filter show-clear fluid :disabled="Boolean(saving)" /></label>
								<label class="price-field"><span>Valid from <b>*</b></span><DateField v-model="form.from_date" :disabled="Boolean(saving)" /></label>
								<label class="price-field"><span>Valid to</span><DateField v-model="form.to_date" show-clear :disabled="Boolean(saving)" /></label>
						</div>
						</div>
					</section>

					<section class="price-form-section">
						<header class="price-form-section__tier-head">
							<div><span>PRICING</span><h2>Price slabs</h2></div>
							<Button label="Add slab" icon="pi pi-plus" severity="secondary" outlined size="small" :disabled="Boolean(saving)" @click="addTier" />
						</header>
						<div class="price-form-section__content">
							<label class="price-toggle"><ToggleSwitch v-model="dependsOnAttribute" :disabled="Boolean(saving) || !editor.attributes?.length" /><span>Price differs by attribute</span></label>
							<div v-if="dependsOnAttribute" class="price-form-grid"><label class="price-field price-field--attribute"><span>Attribute <b>*</b></span><Select :model-value="form.attribute" :options="editor.attributes || []" option-label="attribute" option-value="attribute" fluid :disabled="Boolean(saving)" @update:model-value="changeAttribute" /></label></div>
							<div v-if="form.item_price_values.length" class="price-tiers">
								<article v-for="(row, index) in form.item_price_values" :key="row.key" class="price-tier" :class="{ 'price-tier--attribute': dependsOnAttribute }">
									<label v-if="dependsOnAttribute" class="price-field"><span>Attribute value</span><Select v-model="row.attribute_value" :options="attributeValues" option-label="label" option-value="name" filter fluid :disabled="Boolean(saving)" /></label>
									<label class="price-field"><span>From qty</span><InputNumber v-model="row.moq" :min="0" :max-fraction-digits="tierPrecision('moq')" :use-grouping="false" fluid :disabled="Boolean(saving)" /></label>
									<label class="price-field"><span>Price (excl. tax)</span><InputNumber v-model="row.price" :min="0" :max-fraction-digits="tierPrecision('price')" :use-grouping="false" fluid :disabled="Boolean(saving)" /></label>
									<label class="price-field"><span>Lead time (days)</span><InputNumber v-model="row.lead_time" :min="0" :max-fraction-digits="tierPrecision('lead_time')" :use-grouping="false" fluid :disabled="Boolean(saving)" /></label>
									<Button icon="pi pi-trash" severity="danger" text rounded :aria-label="`Remove slab ${index + 1}`" :disabled="Boolean(saving)" @click="removeTier(index)" />
								</article>
						</div>
						<div v-else class="price-tier-empty">Add at least one price slab.</div>
						</div>
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
import InputNumber from "primevue/inputnumber"
import InputText from "primevue/inputtext"
import Message from "primevue/message"
import Select from "primevue/select"
import Skeleton from "primevue/skeleton"
import ToggleSwitch from "primevue/toggleswitch"
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
import { PURCHASE_ROUTES, itemPriceAttributeValues, itemPriceCanSave, itemPriceEditorRequestKey, itemPriceEditorValues, itemPriceSaveAction, itemPriceSaveValues, itemPriceTierPrecision, savedItemPriceIdentity } from "./purchaseViews.js"

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
const formSignature = computed(() => JSON.stringify(itemPriceSaveValues(form)))
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
const canSave = computed(() => !loading.value && !itemLoading.value && itemPriceCanSave(form))
const saveAction = computed(() => itemPriceSaveAction(editor.value))

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
		let workspace = await saveItemPrice(itemPriceSaveValues(form), {
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
.price-editor-page { width: 100%; max-width: 1800px; min-width: 0; margin: 0 auto; }
.price-editor { display: flex; min-width: 0; min-height: calc(100dvh - var(--erp-shell-header-height) - 98px); flex-direction: column; gap: var(--erp-space-3); }
.price-editor__header > .price-editor__leading { display: flex; min-width: 0; align-items: center; gap: var(--erp-space-3); }
.price-editor__identity { min-width: 0; }
.price-editor__identity > span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 730; letter-spacing: .04em; text-transform: uppercase; }
.price-editor__header h1 { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-title); letter-spacing: -.025em; }
.price-editor__header .price-editor__identity h1 { overflow: hidden; min-width: 0; text-overflow: ellipsis; white-space: nowrap; }
.price-editor__title { display: flex; min-width: 0; align-items: center; gap: var(--erp-space-2); }
.price-editor__title :deep(.document-status-badge) { flex-shrink: 0; }
.price-editor__loading, .price-editor__body { display: grid; min-width: 0; gap: var(--erp-space-3); }
.price-form-section { overflow: hidden; min-width: 0; border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); background: var(--erp-surface); }
.price-form-section > header { display: flex; align-items: center; justify-content: space-between; gap: var(--erp-space-3); padding: 9px 13px; border-bottom: 1px solid var(--erp-border); background: var(--erp-surface-soft); }
.price-form-section > header span { color: var(--erp-accent-hover); font-size: var(--erp-font-size-min); font-weight: 750; letter-spacing: .05em; text-transform: uppercase; }
.price-form-section h2 { margin: 2px 0 0; color: var(--erp-text); font-size: 15px; }
.price-form-section__content { display: grid; min-width: 0; gap: var(--erp-space-3); padding: 13px; }
.price-form-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); align-items: end; gap: 13px 18px; }
.price-field { display: grid; min-width: 0; gap: 6px; color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 680; }
.price-field b { color: var(--erp-danger); }
.price-field--required-link :deep(.common-field__label)::after { color: var(--erp-danger); content: " *"; }
.price-toggle { display: flex; align-items: center; gap: 9px; color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 700; }
.price-tiers { display: grid; gap: 9px; }
.price-tier { display: grid; grid-template-columns: repeat(3, minmax(140px, 1fr)) auto; align-items: end; gap: 10px; padding: 12px; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); background: var(--erp-surface-muted); }
.price-tier--attribute { grid-template-columns: minmax(190px, 1.15fr) repeat(3, minmax(130px, 1fr)) auto; }
.price-tier-empty { display: grid; min-height: 90px; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); border: 1px dashed var(--erp-border-strong); border-radius: var(--erp-control-radius); place-items: center; }
@media (max-width: 900px) { .price-form-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 980px) { .price-tier, .price-tier--attribute { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 650px) { .price-tier, .price-tier--attribute { grid-template-columns: 1fr; } .price-tier > :deep(.p-button) { justify-self: end; } }
@media (max-width: 620px) { .price-form-grid { grid-template-columns: 1fr; } .price-editor__identity > span { display: none; } }
</style>
