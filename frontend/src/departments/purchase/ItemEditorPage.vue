<template>
	<DepartmentPage title="Item" :back-to="backTo" :back-label="backLabel" :show-title="false" flat full-width inline-navigation>
		<div class="purchase-editor-page erp-workspace">
			<section class="purchase-editor erp-card erp-editor-shell" aria-label="Item editor" :aria-busy="loading">
				<header class="erp-editor-header purchase-editor__header">
					<div class="purchase-editor__leading">
						<InlinePageNavigation :title-target="headingId" />
						<div class="purchase-editor__identity">
							<span>Purchase · Item</span>
							<div class="purchase-editor__title"><h1 :id="headingId">{{ isEdit ? (itemId || "Item") : "Create Item" }}</h1><DocumentStatusBadge :label="itemKindLabel(form.attributes)" /></div>
						</div>
					</div>
					<div class="erp-editor-actions">
						<Button label="Cancel" icon="pi pi-times" severity="secondary" text :disabled="saving" @click="cancel" />
						<Button :label="isEdit ? 'Save Item' : 'Create Item'" icon="pi pi-save" :loading="saving" :disabled="!canSave" @click="save" />
					</div>
				</header>

				<div v-if="loading" class="purchase-editor__loading"><Skeleton height="180px" /><Skeleton height="300px" /></div>
				<WorkspaceLoadError v-else-if="loadError" :message="loadError" :loading="loading" @retry="load" />
				<form v-else class="purchase-editor__body" @submit.prevent="save">
					<Message v-if="!canEditPermission" severity="warn" :closable="false">You do not have permission to edit this Item.</Message>
					<section class="purchase-form-section">
						<header><div><span>BASICS</span><h2>Identity &amp; purchasing defaults</h2></div></header>
						<div class="purchase-form-section__content">
							<div class="purchase-form-grid">
								<label class="purchase-field"><span>Name <b>*</b></span><InputText v-model="form.name" fluid :disabled="formDisabled" /></label>
								<LinkField v-model="form.brand" label="Brand" doctype="Brand" show-clear :show-open-button="false" :disabled="formDisabled" />
								<label class="purchase-field"><span>Item Group <b>*</b></span><Select v-model="form.item_group" :options="editor.options?.item_groups || []" option-label="label" option-value="value" filter show-clear fluid :disabled="formDisabled" /></label>
								<label class="purchase-field"><span>Unit <b>*</b></span><Select v-model="form.stock_uom" :options="editor.options?.uoms || []" option-label="label" option-value="value" filter show-clear fluid :disabled="formDisabled || Boolean(editor.fields?.stock_uom?.read_only)" /></label>
								<LinkField v-model="form.gst_hsn_code" label="HSN" doctype="GST HSN Code" show-clear :show-open-button="false" :disabled="formDisabled" />
								<p class="purchase-code-hint">Saved as: <code>{{ savedAs || "—" }}</code></p>
						</div>
						</div>
					</section>

					<section class="purchase-form-section">
						<header class="purchase-form-section__attribute-head">
							<div><span>ATTRIBUTES</span><h2>Variant attributes</h2></div>
							<Button v-if="canEditAttributes" label="Add attribute" icon="pi pi-plus" severity="secondary" outlined size="small" :disabled="formDisabled || hasBlankAttribute" @click="addAttribute" />
						</header>
						<div class="purchase-form-section__content">
							<Message v-if="attributesLocked" severity="warn" :closable="false">{{ editor.attribute_lock_message || "Locked: variants exist" }}</Message>
							<div v-if="form.attributes.length" class="attribute-rows">
								<article v-for="(row, index) in form.attributes" :key="row.key" class="attribute-row">
									<LinkField :ref="(field) => { attributeFields[row.key] = field }" :model-value="row.attribute" label="Attribute *" doctype="Item Attribute" :filters="otherAttributeFilter(row)" :show-open-button="false" required :disabled="formDisabled || attributesLocked" @update:model-value="changeAttribute(row, $event)" />
									<Button v-if="canEditAttributes" icon="pi pi-trash" severity="danger" text rounded :aria-label="`Remove attribute ${index + 1}`" :disabled="formDisabled" @click="removeAttribute(index)" />
								</article>
							</div>
							<div v-else class="attribute-empty"><i class="pi pi-sliders-h" /><span>No attributes. This will be saved as a plain item.</span></div>
							<div v-if="form.attributes.length >= 2" class="purchase-form-grid"><label class="purchase-field purchase-field--main"><span>Main attribute</span><Select v-model="form.primary_attribute" :options="selectedAttributeOptions" option-label="label" option-value="value" fluid :disabled="formDisabled || attributesLocked" /></label></div>
							<ItemAttributeValues v-if="selectedAttributeOptions.length" :attributes="form.attributes" :editable="canEditAttributes && !formDisabled" @edit="openValues" />
						</div>
					</section>
				</form>

			</section>
		</div>
		<ItemAttributeValuesDialog v-model:visible="valuesVisible" :attribute="valuesRow?.attribute || ''" :values="valuesRow?.values || []" :new-values="valuesRow?.new_values || []" :can-create="canCreateAttributeValue" @apply="applyValues" />
		<DocumentErrorDialog :message="actionError" title="Item could not be saved" @dismiss="actionError = ''" />
	</DepartmentPage>
</template>

<script setup>
import Button from "primevue/button"
import InputText from "primevue/inputtext"
import Message from "primevue/message"
import Select from "primevue/select"
import Skeleton from "primevue/skeleton"
import { computed, nextTick, reactive, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"

import { createItem, getItemEditor, updateItem } from "../../api/purchase.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import DocumentStatusBadge from "../../components/documents/DocumentStatusBadge.vue"
import InlinePageNavigation from "../../components/navigation/InlinePageNavigation.vue"
import LinkField from "../../components/common/LinkField.vue"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import { preserveListNavigationState } from "../../router/listDocumentNavigation.js"
import ItemAttributeValues from "./item/ItemAttributeValues.vue"
import ItemAttributeValuesDialog from "./item/ItemAttributeValuesDialog.vue"
import { PURCHASE_ROUTES, itemCanSave, itemCodeHint, itemEditorValues, itemKindLabel, itemSaveValues, resetAttributeRow, storedAttributeMappings } from "./purchaseViews.js"

const props = defineProps({ itemId: { type: String, default: "" } })
const headingId = "purchase-item-editor-title"
const route = useRoute()
const router = useRouter()
const editor = ref({})
const form = reactive(itemEditorValues())
const loading = ref(true)
const saving = ref(false)
const loadError = ref("")
const actionError = ref("")
const attributesChanged = ref(false)
const valuesVisible = ref(false)
const valuesAttribute = ref("")
const attributeFields = {}
let rowSequence = 0
let loadSequence = 0

const isEdit = computed(() => Boolean(props.itemId || route.params.itemId))
const currentName = computed(() => String(props.itemId || route.params.itemId || ""))
const backTo = computed(() => isEdit.value ? `/purchase/items/${encodeURIComponent(currentName.value)}` : "/purchase/items")
const backLabel = computed(() => isEdit.value ? "Item" : "Items")
const attributesLocked = computed(() => Boolean(editor.value.attributes_locked))
const savedAs = computed(() => itemCodeHint(form.name, form.brand))
const selectedNames = computed(() => new Set(form.attributes.map((row) => row.attribute).filter(Boolean)))
const hasBlankAttribute = computed(() => form.attributes.some((row) => !row.attribute))
const selectedAttributeOptions = computed(() => form.attributes.filter((row) => row.attribute).map((row) => ({ label: row.attribute, value: row.attribute })))
const canEditPermission = computed(() => isEdit.value ? Boolean(editor.value.permissions?.can_write) : Boolean(editor.value.permissions?.can_create))
const canEditAttributes = computed(() => canEditPermission.value && !attributesLocked.value)
const canCreateAttributeValue = computed(() => canEditAttributes.value && Boolean(editor.value.permissions?.can_write_item_attribute))
const storedMappings = computed(() => storedAttributeMappings(editor.value.values?.attributes))
const valuesRow = computed(() => form.attributes.find((row) => row.attribute && row.attribute === valuesAttribute.value) || null)
const formDisabled = computed(() => saving.value || !canEditPermission.value)
const canSave = computed(() => !loading.value && !saving.value && canEditPermission.value && itemCanSave(form))

function newRow(row = {}) {
	return { values: [], new_values: [], ...row, key: `attribute-${++rowSequence}` }
}

function applyEditor(payload) {
	editor.value = payload || {}
	const values = itemEditorValues(payload?.values || {})
	Object.assign(form, values, { attributes: values.attributes.map(newRow) })
	attributesChanged.value = false
}

async function load() {
	const sequence = ++loadSequence
	loading.value = true
	loadError.value = ""
	actionError.value = ""
	try {
		const payload = await getItemEditor(currentName.value || null)
		if (sequence === loadSequence) applyEditor(payload)
	} catch (reason) {
		if (sequence === loadSequence) loadError.value = reason?.message || "Unable to load the Item editor."
	} finally {
		if (sequence === loadSequence) loading.value = false
	}
}

function otherAttributeFilter(row) {
	const others = [...selectedNames.value].filter((attribute) => attribute !== row.attribute)
	return others.length ? { name: ["not in", others] } : {}
}

async function addAttribute() {
	const row = newRow({ attribute: "", all_values_allowed: true })
	form.attributes.push(row)
	attributesChanged.value = true
	await nextTick()
	attributeFields[row.key]?.focus()
}

function removeAttribute(index) {
	form.attributes.splice(index, 1)
	attributesChanged.value = true
	if (!selectedNames.value.has(form.primary_attribute)) form.primary_attribute = ""
}

function changeAttribute(row, attribute) {
	if ((attribute || "") === row.attribute) return
	if (form.primary_attribute === row.attribute) form.primary_attribute = ""
	Object.assign(row, resetAttributeRow(storedMappings.value, attribute || ""))
	attributesChanged.value = true
}

function openValues(attribute) {
	valuesAttribute.value = attribute
	valuesVisible.value = true
}

function applyValues(values, newValues) {
	if (!valuesRow.value) return
	Object.assign(valuesRow.value, { values, new_values: newValues, all_values_allowed: !values.length })
	attributesChanged.value = true
}

async function save() {
	if (!canSave.value) return
	saving.value = true
	actionError.value = ""
	try {
		const values = itemSaveValues(form, {
			defaultSinglePrimary: !isEdit.value || attributesChanged.value,
		})
		const result = isEdit.value
			? await updateItem(currentName.value, values, editor.value.modified)
			: await createItem(values)
		const name = result?.name || currentName.value
		if (!name) throw new Error("The saved Item name was not returned.")
		await router.replace({
			name: PURCHASE_ROUTES.item,
			params: { itemId: name },
			state: preserveListNavigationState(name, result?.modified),
		})
	} catch (reason) {
		actionError.value = reason?.message || "Unable to save this Item."
	} finally {
		saving.value = false
	}
}

function cancel() {
	router.push(backTo.value)
}

watch(() => [currentName.value, route.name], load, { immediate: true })
</script>

<style scoped>
.purchase-editor-page { width: 100%; max-width: 1800px; min-width: 0; margin: 0 auto; }
.purchase-editor { display: flex; min-width: 0; min-height: calc(100dvh - var(--erp-shell-header-height) - 98px); flex-direction: column; gap: var(--erp-space-3); }
.purchase-editor__header > .purchase-editor__leading { display: flex; min-width: 0; align-items: center; gap: var(--erp-space-3); }
.purchase-editor__identity { min-width: 0; }
.purchase-editor__identity > span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 730; letter-spacing: .04em; text-transform: uppercase; }
.purchase-editor__header h1 { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-title); letter-spacing: -.025em; }
.purchase-editor__header .purchase-editor__title h1 { overflow: hidden; min-width: 0; text-overflow: ellipsis; white-space: nowrap; }
.purchase-editor__loading, .purchase-editor__body { display: grid; min-width: 0; gap: var(--erp-space-3); }
.purchase-form-section { overflow: hidden; min-width: 0; border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); background: var(--erp-surface); }
.purchase-form-section > header { display: flex; align-items: center; justify-content: space-between; gap: var(--erp-space-3); padding: 9px 13px; border-bottom: 1px solid var(--erp-border); background: var(--erp-surface-soft); }
.purchase-form-section > header span { color: var(--erp-accent-hover); font-size: var(--erp-font-size-min); font-weight: 750; letter-spacing: .05em; text-transform: uppercase; }
.purchase-form-section h2 { margin: 2px 0 0; color: var(--erp-text); font-size: 15px; }
.purchase-form-section__content { display: grid; min-width: 0; gap: var(--erp-space-3); padding: 13px; }
.purchase-form-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); align-items: end; gap: 13px 18px; }
.purchase-field { display: grid; min-width: 0; gap: 6px; color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 680; }
.purchase-field b { color: var(--erp-danger); }
.purchase-code-hint { display: flex; min-width: 0; min-height: var(--erp-control-height); align-items: center; gap: 5px; margin: 0; padding: 0 11px; border-left: 3px solid var(--erp-accent); background: var(--erp-accent-soft); }
.purchase-code-hint code { overflow-wrap: anywhere; color: var(--erp-accent-hover); font-family: inherit; font-weight: 750; }
.attribute-rows { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: var(--erp-space-3); }
.attribute-row { display: grid; min-width: 0; grid-template-columns: minmax(0, 1fr) auto; align-items: end; gap: var(--erp-space-1); }
.attribute-empty { display: flex; min-height: 90px; align-items: center; justify-content: center; gap: 9px; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); border: 1px dashed var(--erp-border-strong); border-radius: var(--erp-control-radius); }
.attribute-empty i { color: var(--erp-accent); }
@media (max-width: 900px) { .purchase-form-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
.purchase-editor__title { display: flex; min-width: 0; align-items: center; gap: var(--erp-space-2); }
.purchase-editor__title :deep(.document-status-badge) { flex-shrink: 0; }
@media (max-width: 620px) { .purchase-form-grid, .attribute-rows { grid-template-columns: minmax(0, 1fr); } .purchase-editor__identity > span { display: none; } }
</style>
