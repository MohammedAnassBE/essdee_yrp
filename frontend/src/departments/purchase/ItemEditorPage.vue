<template>
	<DepartmentPage title="Item" :back-to="backTo" :back-label="backLabel" :show-title="false" flat full-width inline-navigation>
		<div class="purchase-editor-page erp-workspace">
			<section class="purchase-editor erp-card erp-editor-shell" aria-label="Item editor" :aria-busy="loading">
				<header class="erp-editor-header purchase-editor__header">
					<div class="purchase-editor__leading">
						<InlinePageNavigation :title-target="headingId" />
						<div class="purchase-editor__identity">
							<span>Purchase · Item</span>
							<div class="purchase-editor__title"><h1 class="erp-doc-title" :id="headingId">{{ isEdit ? (itemId || "Item") : "Create Item" }}</h1><DocumentStatusBadge :label="itemKindLabel(form.attributes)" /></div>
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
					<Message v-for="warning in tableWarnings" :key="warning" severity="warn" :closable="false">{{ warning }}</Message>
					<section class="purchase-form-section">
						<header><div><span>BASICS</span><h2>Identity &amp; purchasing defaults</h2></div></header>
						<div class="purchase-form-section__content">
							<div class="purchase-form-grid">
								<label class="purchase-field"><span class="erp-field-label">{{ fieldLabel("name", "Item Name") }} <b>*</b></span><InputText v-model="form.name" fluid :disabled="formDisabled" /></label>
								<LinkField v-model="form.brand" :label="fieldLabel('brand', 'Brand')" doctype="Brand" show-clear :show-open-button="false" :disabled="formDisabled" />
								<label class="purchase-field"><span class="erp-field-label">{{ fieldLabel("item_group", "Item Group") }} <b>*</b></span><Select v-model="form.item_group" :options="editor.options?.item_groups || []" option-label="label" option-value="value" filter show-clear fluid :disabled="formDisabled" /></label>
								<label class="purchase-field"><span class="erp-field-label">{{ fieldLabel("stock_uom", "Default Unit of Measure") }} <b>*</b></span><Select v-model="form.stock_uom" :options="editor.options?.uoms || []" option-label="label" option-value="value" filter show-clear fluid :disabled="formDisabled || Boolean(editor.fields?.stock_uom?.read_only)" /></label>
								<LinkField v-model="form.gst_hsn_code" :label="fieldLabel('gst_hsn_code', 'HSN/SAC')" doctype="GST HSN Code" show-clear :show-open-button="false" :disabled="formDisabled" />
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
							<Message v-if="attributesLocked" severity="warn" :closable="false">{{ editor.attribute_lock_message || "Attributes are locked because variants exist. Values can still be added or removed." }}</Message>
							<label v-if="canEditAttributes && form.attributes.length" class="attribute-select-all"><input type="checkbox" class="attribute-checkbox" data-row-select :checked="attributeSelection.isAllSelected.value" :indeterminate="attributeSelection.isPartlySelected.value" :disabled="!attributeKeys.length" aria-label="Select all attributes" @change="attributeSelection.toggleAll($event.target.checked)"><span>Select all</span></label>
							<div v-if="form.attributes.length" class="attribute-rows">
								<article v-for="(row, index) in form.attributes" :key="row.key" class="attribute-row" :class="{ 'attribute-row--selectable': canEditAttributes }">
									<input v-if="canEditAttributes" type="checkbox" class="attribute-checkbox" data-row-select tabindex="-1" :checked="attributeSelection.isSelected(row.key)" :disabled="!attributeKeys.includes(row.key)" :aria-label="`Select attribute ${index + 1}`" @change="attributeSelection.toggle(row.key, $event.target.checked)">
									<LinkField :ref="(field) => { attributeFields[row.key] = field }" :model-value="row.attribute" label="Attribute *" doctype="Item Attribute" :filters="otherAttributeFilter(row)" :show-open-button="false" required :disabled="formDisabled || attributesLocked" @update:model-value="changeAttribute(row, $event)" />
								</article>
							</div>
							<footer v-if="attributeSelection.selected.value.length" class="attribute-selection">
								<span>{{ attributeSelection.selected.value.length }} selected</span>
								<Button label="Delete" icon="pi pi-trash" severity="danger" size="small" :disabled="formDisabled" @click="deleteSelectedAttributes" />
							</footer>
							<div v-if="!form.attributes.length" class="attribute-empty"><i class="pi pi-sliders-h" /><span>No attributes. This will be saved as a plain item.</span></div>
							<div v-if="selectedAttributeOptions.length" class="purchase-form-grid">
								<label class="purchase-field purchase-field--primary"><span class="erp-field-label">{{ fieldLabel("primary_attribute", "Primary Attribute") }}</span><Select v-model="form.primary_attribute" :options="selectedAttributeOptions" option-label="label" option-value="value" show-clear fluid :disabled="formDisabled || !attributeEditing.primary" @update:model-value="changePrimary" /></label>
								<label class="purchase-field purchase-field--dependent"><span class="erp-field-label">{{ fieldLabel("dependent_attribute", "Dependent Attribute") }}</span><Select v-model="form.dependent_attribute" :options="dependentAttributeOptions" option-label="label" option-value="value" show-clear fluid placeholder="None" :disabled="formDisabled || !attributeEditing.dependent" /></label>
							</div>
							<ItemAttributeValues v-if="selectedAttributeOptions.length" :attributes="form.attributes" :editable="attributeEditing.values && !formDisabled" @edit="openValues" />
							<Message v-if="dependentProblem" class="purchase-dependent-problem" severity="error" :closable="false">{{ dependentProblem }}</Message>
							<ItemDependentAttributeTable v-if="form.dependent_attribute && form.dependent_details.length" :dependent-attribute="form.dependent_attribute" :rows="form.dependent_details" :attributes="combinationAttributes" :editable="canEditPermission && !formDisabled" :uoms="form.uoms" :problems="tableProblems" />
						</div>
					</section>
					<ItemUomConversions :values="form" :field="editor.fields?.uoms" editable :disabled="formDisabled" :problems="problemsFor('uoms')" />
					<ItemAdditionalParameters :values="form" :field="editor.fields?.additional_parameters" editable :disabled="formDisabled" :problems="problemsFor('additional_parameters')" />
					<ItemMasterFields part="details" :values="form" :fields="editor.fields" :categories="editor.options?.categories" editable :disabled="formDisabled" :problems="problemsFor('po_excess_allowed_percentage')" />
					<ItemYarnRatio v-if="Number(form.is_cloth_item)" :values="form" :item-name="currentName || savedAs" :field="editor.fields?.yarn_ratio_details" editable :disabled="formDisabled" :problems="problemsFor('yarn_ratio_details')" />
					<ItemMasterFields part="description" :values="form" :fields="editor.fields" editable :disabled="formDisabled" />
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
import { useRowSelection } from "../../components/common/childGrid/rowSelection.js"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import { preserveListNavigationState } from "../../router/listDocumentNavigation.js"
import ItemAttributeValues from "./item/ItemAttributeValues.vue"
import ItemAttributeValuesDialog from "./item/ItemAttributeValuesDialog.vue"
import ItemDependentAttributeTable from "./item/ItemDependentAttributeTable.vue"
import ItemAdditionalParameters from "./item/ItemAdditionalParameters.vue"
import ItemMasterFields from "./item/ItemMasterFields.vue"
import ItemUomConversions from "./item/ItemUomConversions.vue"
import ItemYarnRatio from "./item/ItemYarnRatio.vue"
import { itemAttributeEditing, itemTableProblems, itemTableWarnings, stockUomRows } from "./item/itemTables.js"
import { takeNewDocumentDefaults, withNewDocumentDefaults } from "../../utils/newDocumentDefaults.js"
import { PURCHASE_ROUTES, dependentDetailRows, itemCanSave, itemCodeHint, itemCombinationAttributes, itemDependentProblem, itemDependentValues, itemEditorValues, itemKindLabel, itemSaveValues, resetAttributeRow, storedAttributeMappings } from "./purchaseViews.js"

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
const attributeRowsChanged = ref(false)
const valuesVisible = ref(false)
const valuesAttribute = ref("")
const attributeFields = {}
let rowSequence = 0
let loadSequence = 0
const takenDefaults = takeNewDocumentDefaults("Item")
let filterDefaults = props.itemId || route.params.itemId || route.query.duplicate_from ? {} : takenDefaults

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
const attributeEditing = computed(() => itemAttributeEditing(editor.value, canEditPermission.value))
const canEditAttributes = computed(() => attributeEditing.value.rows)
const canCreateAttributeValue = computed(() => attributeEditing.value.createValues)
const storedMappings = computed(() => storedAttributeMappings(editor.value.values?.attributes))
const valuesRow = computed(() => form.attributes.find((row) => row.attribute && row.attribute === valuesAttribute.value) || null)
const formDisabled = computed(() => saving.value || !canEditPermission.value)
const attributeKeys = computed(() => canEditAttributes.value && !formDisabled.value ? form.attributes.map((row) => row.key) : [])
const attributeSelection = useRowSelection(attributeKeys)
const canSave = computed(() => !loading.value && !saving.value && canEditPermission.value && itemCanSave(form))
const dependentAttributeOptions = computed(() => selectedAttributeOptions.value.filter((option) => option.value !== form.primary_attribute))
const combinationAttributes = computed(() => itemCombinationAttributes(form, editor.value.options?.numeric_attributes))
const dependentProblem = computed(() => itemDependentProblem(form))
const tableProblems = computed(() => itemTableProblems(form))
const tableWarnings = computed(() => itemTableWarnings(form, editor.value, editor.value.values))
const problemsFor = (field) => tableProblems.value.filter((problem) => problem.field === field)

function fieldLabel(fieldname, fallback) {
	return editor.value.fields?.[fieldname]?.label || fallback
}

function changePrimary(attribute) {
	if (attribute && attribute === form.dependent_attribute) form.dependent_attribute = ""
}

function syncDependentDetails() {
	form.dependent_details = dependentDetailRows(form, form.stock_uom, {
		preserveExisting: Boolean(form.dependent_mapping_modified) && form.dependent_attribute === editor.value.values?.dependent_attribute,
	})
	for (const row of form.dependent_details) row.uom ||= form.stock_uom
}

function newRow(row = {}) {
	return { values: [], new_values: [], ...row, key: `attribute-${++rowSequence}` }
}

function applyEditor(payload) {
	editor.value = payload || {}
	const values = itemEditorValues(payload?.values || {})
	Object.assign(form, values, { attributes: values.attributes.map(newRow) })
	attributeRowsChanged.value = false
}

async function load() {
	const sequence = ++loadSequence
	loading.value = true
	loadError.value = ""
	actionError.value = ""
	try {
		const duplicateFrom = currentName.value ? null : route.query.duplicate_from || null
		const payload = await getItemEditor(currentName.value || null, duplicateFrom)
		if (sequence === loadSequence) {
			applyEditor(payload)
			if (!currentName.value) applyFilterDefaults()
		}
	} catch (reason) {
		if (sequence === loadSequence) loadError.value = reason?.message || "Unable to load the Item editor."
	} finally {
		if (sequence === loadSequence) loading.value = false
	}
}

function applyFilterDefaults() {
	const defaults = Object.fromEntries(Object.entries(filterDefaults).filter(([key]) => key !== "name" && key in form && !Array.isArray(form[key])))
	filterDefaults = {}
	Object.assign(form, withNewDocumentDefaults(form, defaults))
}

function otherAttributeFilter(row) {
	const others = [...selectedNames.value].filter((attribute) => attribute !== row.attribute)
	return others.length ? { name: ["not in", others] } : {}
}

async function addAttribute() {
	const row = newRow({ attribute: "", all_values_allowed: true })
	form.attributes.push(row)
	attributeRowsChanged.value = true
	await nextTick()
	attributeFields[row.key]?.focus()
}

function removeAttribute(index) {
	form.attributes.splice(index, 1)
	attributeRowsChanged.value = true
	if (!selectedNames.value.has(form.primary_attribute)) form.primary_attribute = ""
	if (!selectedNames.value.has(form.dependent_attribute)) form.dependent_attribute = ""
}

function deleteSelectedAttributes() {
	return attributeSelection.removeSelected((key) => removeAttribute(form.attributes.findIndex((row) => row.key === key)), () => !formDisabled.value)
}

function changeAttribute(row, attribute) {
	if ((attribute || "") === row.attribute) return
	if (form.primary_attribute === row.attribute) form.primary_attribute = ""
	if (form.dependent_attribute === row.attribute) form.dependent_attribute = ""
	Object.assign(row, resetAttributeRow(storedMappings.value, attribute || ""))
	attributeRowsChanged.value = true
}

function openValues(attribute) {
	valuesAttribute.value = attribute
	valuesVisible.value = true
}

function applyValues(values, newValues) {
	if (!valuesRow.value) return
	Object.assign(valuesRow.value, { values, new_values: newValues, all_values_allowed: !values.length })
}

async function save() {
	if (!canSave.value) return
	saving.value = true
	actionError.value = ""
	try {
		const values = itemSaveValues(form, {
			defaultSinglePrimary: !isEdit.value || attributeRowsChanged.value,
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

watch(() => [currentName.value, route.name, route.query.duplicate_from], load, { immediate: true })
watch(() => form.stock_uom, (stockUom, previousStockUom) => {
	form.uoms = stockUomRows(form.uoms, stockUom, previousStockUom)
	if (!isEdit.value && !form.uoms.some((row) => row.uom === previousStockUom)) {
		for (const row of form.dependent_details) if (row.uom === previousStockUom) row.uom = stockUom
	}
})
watch(() => [form.dependent_attribute, form.primary_attribute, form.stock_uom, [...selectedNames.value].join("\u0001"), itemDependentValues(form).join("\u0001")], syncDependentDetails)
</script>

<style scoped>
.purchase-editor-page { width: 100%; min-width: 0; }
.purchase-editor { display: flex; min-width: 0; min-height: calc(100dvh - var(--erp-shell-header-height) - 98px); flex-direction: column; gap: var(--erp-space-3); }
.purchase-editor__header > .purchase-editor__leading { display: flex; min-width: 0; align-items: center; gap: var(--erp-space-3); }
.purchase-editor__identity { min-width: 0; }
.purchase-editor__identity > span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 730; letter-spacing: .04em; text-transform: uppercase; }
.purchase-editor__header h1 { margin: 0; color: var(--erp-text); }
.purchase-editor__header .purchase-editor__title h1 { overflow: hidden; min-width: 0; text-overflow: ellipsis; white-space: nowrap; }
.purchase-editor__loading, .purchase-editor__body { display: grid; min-width: 0; gap: var(--erp-space-3); }
.purchase-form-section { overflow: hidden; min-width: 0; border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); background: var(--erp-surface); }
.purchase-form-section > header { display: flex; align-items: center; justify-content: space-between; gap: var(--erp-space-3); padding: 9px 13px; border-bottom: 1px solid var(--erp-border); background: var(--erp-surface-soft); }
.purchase-form-section > header span { color: var(--erp-accent-hover); font-size: var(--erp-font-size-min); font-weight: 750; letter-spacing: .05em; text-transform: uppercase; }
.purchase-form-section h2 { margin: 2px 0 0; color: var(--erp-text); font-size: 15px; }
.purchase-form-section__content { display: grid; min-width: 0; gap: var(--erp-space-3); padding: 13px; }
.purchase-form-grid {
	display: grid;
	grid-template-columns: repeat(3, minmax(0, 1fr));
	align-items: end;
	gap: 16px 28px;
}
.purchase-field {
	display: grid;
	min-width: 0;
	gap: 6px;
}

.purchase-dependent-problem { margin: 0; }
.purchase-code-hint { display: flex; min-width: 0; min-height: var(--erp-control-height); align-items: center; gap: 5px; margin: 0; padding: 0 11px; border-left: 3px solid var(--erp-accent); background: var(--erp-accent-soft); }
.purchase-code-hint code { overflow-wrap: anywhere; color: var(--erp-accent-hover); font-family: inherit; font-weight: 750; }
.attribute-rows { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: var(--erp-space-3); }
.attribute-row { display: grid; min-width: 0; grid-template-columns: minmax(0, 1fr); align-items: end; gap: var(--erp-space-2); }
.attribute-row--selectable { grid-template-columns: auto minmax(0, 1fr); }
.attribute-row--selectable > .attribute-checkbox { margin-bottom: calc((var(--erp-control-height) - 15px) / 2); }
.attribute-select-all { display: inline-flex; align-items: center; gap: 7px; justify-self: start; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); cursor: pointer; }
.attribute-checkbox { width: 15px; height: 15px; margin: 0; vertical-align: middle; accent-color: var(--erp-accent); cursor: pointer; }
.attribute-checkbox:disabled { cursor: not-allowed; opacity: .45; }
.attribute-selection { display: flex; align-items: center; justify-content: flex-end; gap: 10px; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
.attribute-empty { display: flex; min-height: 90px; align-items: center; justify-content: center; gap: 9px; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); border: 1px dashed var(--erp-border-strong); border-radius: var(--erp-control-radius); }
.attribute-empty i { color: var(--erp-accent); }
@media (max-width: 900px) { .purchase-form-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
.purchase-editor__title { display: flex; min-width: 0; flex-wrap: wrap; align-items: center; gap: 4px var(--erp-space-2); }
.purchase-editor__title :deep(.document-status-badge) { flex-shrink: 0; }
@media (max-width: 620px) { .purchase-form-grid, .attribute-rows { grid-template-columns: minmax(0, 1fr); } .purchase-editor__identity > span { display: none; } }
@media (max-width: 620px) {
	.purchase-form-section > header,
	.purchase-form-section__content {
		padding-inline: var(--erp-space-3);
	}
}
</style>
