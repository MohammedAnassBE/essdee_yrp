<template>
	<DepartmentPage title="Item" :back-to="backTo" :back-label="backLabel" :show-title="false" flat full-width>
		<section class="purchase-editor erp-card erp-editor-shell" aria-label="Item editor" :aria-busy="loading">
			<header class="purchase-editor__header">
				<div>
					<span>Purchase · Item</span>
					<h1>{{ isEdit ? (itemId || "Item") : "Create Item" }}</h1>
				</div>
				<div class="purchase-editor__actions">
					<Button label="Cancel" severity="secondary" text :disabled="saving" @click="cancel" />
					<Button :label="isEdit ? 'Save Item' : 'Create Item'" icon="pi pi-save" :loading="saving" :disabled="!canSave" @click="save" />
				</div>
			</header>

			<div v-if="loading" class="purchase-editor__loading"><Skeleton height="180px" /><Skeleton height="300px" /></div>
			<WorkspaceLoadError v-else-if="loadError" :message="loadError" :loading="loading" @retry="load" />
			<form v-else class="purchase-editor__body" @submit.prevent="save">
				<Message v-if="!canEditPermission" severity="warn" :closable="false">You do not have permission to edit this Item.</Message>
				<section class="purchase-form-section">
					<header><span>01</span><div><h2>Basics</h2><p>Identity and purchasing defaults.</p></div></header>
					<div class="purchase-form-grid">
						<label class="purchase-field"><span>Name <b>*</b></span><InputText v-model="form.name" fluid :disabled="formDisabled" /></label>
						<LinkField v-model="form.brand" label="Brand" doctype="Brand" show-clear :show-open-button="false" :disabled="formDisabled" />
						<label class="purchase-field"><span>Item Group <b>*</b></span><Select v-model="form.item_group" :options="editor.options?.item_groups || []" option-label="label" option-value="value" filter show-clear fluid :disabled="formDisabled" /></label>
						<label class="purchase-field"><span>Unit <b>*</b></span><Select v-model="form.stock_uom" :options="editor.options?.uoms || []" option-label="label" option-value="value" filter show-clear fluid :disabled="formDisabled || Boolean(editor.fields?.stock_uom?.read_only)" /></label>
						<label class="purchase-field"><span>HSN</span><InputText v-model="form.gst_hsn_code" fluid :disabled="formDisabled" /></label>
					</div>
					<p class="purchase-code-hint">Saved as: <code>{{ savedAs || "—" }}</code></p>
				</section>

				<section class="purchase-form-section">
					<header class="purchase-form-section__attribute-head">
						<span>02</span><div><h2>Attributes</h2><p>Choose the allowed values used to create variants.</p></div>
						<Button v-if="!attributesLocked" label="Add attribute" icon="pi pi-plus" severity="secondary" outlined size="small" :disabled="formDisabled || !availableAttributes.length" @click="addAttribute" />
					</header>
					<Message v-if="attributesLocked" severity="warn" :closable="false">{{ editor.attribute_lock_message || "Locked: variants exist" }}</Message>
					<div v-if="form.attributes.length" class="attribute-rows">
						<article v-for="(row, index) in form.attributes" :key="row.key" class="attribute-row">
							<label class="purchase-field"><span>Attribute</span><Select :model-value="row.attribute" :options="attributeChoices(row)" option-label="label" option-value="value" filter fluid :disabled="formDisabled || attributesLocked" @update:model-value="changeAttribute(row, $event)" /></label>
							<div class="attribute-values">
								<div v-if="row.all_values_allowed" class="attribute-values__all"><strong>All values allowed</strong><span>This mapping stays unrestricted.</span></div>
								<MultiSelectField v-else :model-value="row.values" label="Allowed values" :options="row.available_values || []" option-label="label" option-value="label" placeholder="Select values" :loading="row.loading" :disabled="formDisabled || attributesLocked || !row.attribute" @update:model-value="updateAttributeValues(row, $event)" @filter="searchAttributeOptions(row, $event)" />
								<div v-if="canCreateAttributeValue && row.attribute" class="attribute-values__new">
									<InputText v-model="row.new_value" :placeholder="`New ${row.attribute} value`" fluid :disabled="formDisabled || row.adding_value" @keydown.enter.prevent="addNewAttributeValue(row)" />
									<Button label="Add value" icon="pi pi-plus" severity="secondary" outlined size="small" :loading="row.adding_value" :disabled="formDisabled || !String(row.new_value || '').trim()" @click="addNewAttributeValue(row)" />
								</div>
							</div>
							<Button v-if="!attributesLocked" icon="pi pi-trash" severity="danger" text rounded :aria-label="`Remove attribute ${index + 1}`" :disabled="formDisabled" @click="removeAttribute(index)" />
						</article>
					</div>
					<div v-else class="attribute-empty"><i class="pi pi-sliders-h" /><span>No attributes. This will be saved as a plain item.</span></div>
					<label v-if="form.attributes.length >= 2" class="purchase-field purchase-field--main"><span>Main attribute</span><Select v-model="form.primary_attribute" :options="selectedAttributeOptions" option-label="label" option-value="value" fluid :disabled="formDisabled || attributesLocked" /></label>
				</section>
			</form>

			<footer v-if="!loading && !loadError" class="purchase-editor__footer">
				<span><i class="pi pi-info-circle" /> {{ itemKindLabel(form.attributes) }}</span>
			</footer>
		</section>
		<DocumentErrorDialog :message="actionError" title="Item could not be saved" @dismiss="actionError = ''" />
	</DepartmentPage>
</template>

<script setup>
import Button from "primevue/button"
import InputText from "primevue/inputtext"
import Message from "primevue/message"
import Select from "primevue/select"
import Skeleton from "primevue/skeleton"
import { computed, reactive, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"

import { createItem, getItemEditor, searchItemAttributeValues, updateItem } from "../../api/purchase.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import LinkField from "../../components/common/LinkField.vue"
import MultiSelectField from "../../components/common/MultiSelectField.vue"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import { preserveListNavigationState } from "../../router/listDocumentNavigation.js"
import { PURCHASE_ROUTES, itemAttributeSearchScope, itemCodeHint, itemEditorValues, itemKindLabel, itemSaveValues, stageItemAttributeValue, withSelectedAttributeValues } from "./purchaseViews.js"

const props = defineProps({ itemId: { type: String, default: "" } })
const route = useRoute()
const router = useRouter()
const editor = ref({})
const form = reactive(itemEditorValues())
const loading = ref(true)
const saving = ref(false)
const loadError = ref("")
const actionError = ref("")
const attributesChanged = ref(false)
let rowSequence = 0
let loadSequence = 0

const isEdit = computed(() => Boolean(props.itemId || route.params.itemId))
const currentName = computed(() => String(props.itemId || route.params.itemId || ""))
const backTo = computed(() => isEdit.value ? `/purchase/items/${encodeURIComponent(currentName.value)}` : "/purchase/items")
const backLabel = computed(() => isEdit.value ? "Item" : "Items")
const attributesLocked = computed(() => Boolean(editor.value.attributes_locked))
const savedAs = computed(() => itemCodeHint(form.name, form.brand))
const selectedNames = computed(() => new Set(form.attributes.map((row) => row.attribute).filter(Boolean)))
const availableAttributes = computed(() => (editor.value.options?.attributes || []).filter((option) => !selectedNames.value.has(option.value)))
const selectedAttributeOptions = computed(() => form.attributes.filter((row) => row.attribute).map((row) => ({ label: row.attribute, value: row.attribute })))
const canEditPermission = computed(() => isEdit.value ? Boolean(editor.value.permissions?.can_write) : Boolean(editor.value.permissions?.can_create))
const canCreateAttributeValue = computed(() => !attributesLocked.value && Boolean(editor.value.permissions?.can_write_item_attribute))
const formDisabled = computed(() => saving.value || !canEditPermission.value)
const canSave = computed(() => !loading.value && !saving.value && canEditPermission.value && Boolean(
	String(form.name || "").trim()
	&& form.item_group
	&& form.stock_uom
	&& form.attributes.every((row) => row.attribute && row.values?.length),
))

function newRow(row = {}) {
	return {
		...row,
		key: `attribute-${++rowSequence}`,
		values: (row.values || []).map((value) => typeof value === "string" ? value : value.label || value.value || value.name),
		available_values: [],
		loading: false,
		request_sequence: 0,
		new_value: "",
		adding_value: false,
	}
}

function applyEditor(payload) {
	editor.value = payload || {}
	const values = itemEditorValues(payload?.values || {})
	Object.assign(form, values, { attributes: values.attributes.map(newRow) })
	attributesChanged.value = false
	for (const row of form.attributes) loadAttributeOptions(row)
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

function attributeChoices(row) {
	return (editor.value.options?.attributes || []).filter((option) => option.value === row.attribute || !selectedNames.value.has(option.value))
}

function addAttribute() {
	form.attributes.push(newRow({ attribute: availableAttributes.value[0]?.value || "", values: [] }))
	const row = form.attributes.at(-1)
	attributesChanged.value = true
	if (row.attribute) loadAttributeOptions(row)
}

function removeAttribute(index) {
	form.attributes.splice(index, 1)
	attributesChanged.value = true
	if (!selectedNames.value.has(form.primary_attribute)) form.primary_attribute = ""
}

function changeAttribute(row, attribute) {
	row.attribute = attribute || ""
	row.values = []
	row.mapping = null
	row.mapping_modified = null
	row.all_values_allowed = false
	row.available_values = []
	row.new_value = ""
	attributesChanged.value = true
	if (row.attribute) loadAttributeOptions(row)
}

function updateAttributeValues(row, values) {
	row.values = values || []
	attributesChanged.value = true
}

function searchAttributeOptions(row, event) {
	loadAttributeOptions(row, event?.value || "")
}

async function loadAttributeOptions(row, text = "") {
	const attribute = row.attribute
	if (!attribute) return
	const sequence = ++row.request_sequence
	row.loading = true
	try {
		const options = await searchItemAttributeValues(
			attribute,
			text,
			itemAttributeSearchScope(attributesLocked.value, currentName.value),
		)
		if (row.attribute !== attribute || sequence !== row.request_sequence) return
		const selected = row.values.map((label) => ({ name: label, label }))
		row.available_values = withSelectedAttributeValues(selected, options || [])
	} catch (reason) {
		if (sequence === row.request_sequence) actionError.value = reason?.message || `Unable to load values for ${attribute}.`
	} finally {
		if (row.attribute === attribute && sequence === row.request_sequence) row.loading = false
	}
}

function addNewAttributeValue(row) {
	const label = String(row.new_value || "").trim()
	if (!label || row.adding_value || !canCreateAttributeValue.value) return
	if ((row.available_values || []).some((option) => option.label === label)) {
		actionError.value = `${label} already exists. Select it from the allowed values.`
		return
	}
	const staged = stageItemAttributeValue(row.values, row.available_values, label)
	row.values = staged.values
	row.available_values = staged.availableValues
	row.new_value = ""
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
.purchase-editor { display: flex; width: min(1180px, 100%); min-width: 0; min-height: 560px; margin: 0 auto; overflow: hidden; flex-direction: column; border-top: 3px solid var(--erp-accent); }
.purchase-editor__header { display: flex; min-height: 76px; align-items: center; justify-content: space-between; gap: 20px; padding: 14px clamp(16px, 2vw, 26px); border-bottom: 1px solid var(--erp-border); background: color-mix(in srgb, var(--erp-surface) 96%, var(--erp-accent-soft)); }
.purchase-editor__header > div:first-child { display: grid; min-width: 0; gap: 3px; }
.purchase-editor__header span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 750; letter-spacing: .05em; text-transform: uppercase; }
.purchase-editor__header h1 { margin: 0; overflow: hidden; color: var(--erp-text); font-size: clamp(20px, 2vw, 26px); letter-spacing: -.025em; text-overflow: ellipsis; white-space: nowrap; }
.purchase-editor__actions { display: flex; align-items: center; gap: 6px; }
.purchase-editor__loading, .purchase-editor__body { display: grid; min-width: 0; gap: 18px; padding: clamp(14px, 2vw, 24px); }
.purchase-form-section { display: grid; min-width: 0; gap: 16px; padding: clamp(16px, 2vw, 22px); border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); background: var(--erp-surface); box-shadow: var(--erp-shadow-xs); }
.purchase-form-section > header { display: grid; grid-template-columns: auto minmax(0, 1fr); align-items: start; gap: 10px; }
.purchase-form-section > header > span { display: grid; width: 30px; height: 30px; color: var(--erp-accent-hover); font-size: var(--erp-font-size-min); border: 1px solid color-mix(in srgb, var(--erp-accent) 28%, var(--erp-border)); border-radius: 50%; background: var(--erp-accent-soft); place-items: center; }
.purchase-form-section h2, .purchase-form-section p { margin: 0; }
.purchase-form-section h2 { color: var(--erp-text); font-size: 1rem; }
.purchase-form-section p { margin-top: 3px; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
.purchase-form-section__attribute-head { grid-template-columns: auto minmax(0, 1fr) auto !important; }
.purchase-form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.purchase-field { display: grid; min-width: 0; gap: 6px; color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 680; }
.purchase-field b { color: var(--erp-danger); }
.purchase-code-hint { padding: 9px 11px; border-left: 3px solid var(--erp-accent); background: var(--erp-accent-soft); }
.purchase-code-hint code { color: var(--erp-accent-hover); font-family: inherit; font-weight: 750; }
.attribute-rows { display: grid; gap: 10px; }
.attribute-row { display: grid; grid-template-columns: minmax(180px, .7fr) minmax(280px, 1.3fr) auto; align-items: end; gap: 10px; padding: 12px; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); background: var(--erp-surface-muted); }
.attribute-values { display: grid; min-width: 0; gap: 8px; }
.attribute-values__all { display: grid; min-height: 42px; align-content: center; gap: 2px; padding: 8px 11px; border: 1px solid color-mix(in srgb, var(--erp-accent) 24%, var(--erp-border)); border-radius: var(--erp-control-radius); background: var(--erp-accent-soft); }
.attribute-values__all strong { color: var(--erp-accent-hover); font-size: var(--erp-font-size-caption); }
.attribute-values__all span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.attribute-values__new { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 7px; }
.attribute-empty { display: flex; min-height: 90px; align-items: center; justify-content: center; gap: 9px; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); border: 1px dashed var(--erp-border-strong); border-radius: var(--erp-control-radius); }
.attribute-empty i { color: var(--erp-accent); }
.purchase-field--main { max-width: 420px; }
.purchase-editor__footer { display: flex; min-height: 54px; align-items: center; padding: 10px clamp(16px, 2vw, 26px); color: var(--erp-text-secondary); font-size: var(--erp-font-size-caption); font-weight: 700; border-top: 1px solid var(--erp-border); background: var(--erp-surface-muted); }
.purchase-editor__footer i { margin-right: 6px; color: var(--erp-accent); }
@media (max-width: 760px) { .purchase-editor__header { align-items: stretch; flex-direction: column; } .purchase-editor__actions { display: grid; grid-template-columns: 1fr 1fr; } .purchase-form-grid, .attribute-row { grid-template-columns: 1fr; } .attribute-row > :deep(.p-button) { justify-self: end; } .attribute-values__new { grid-template-columns: 1fr; } .purchase-form-section__attribute-head { grid-template-columns: auto minmax(0, 1fr) !important; } .purchase-form-section__attribute-head > :deep(.p-button) { grid-column: 1 / -1; width: 100%; } }
@media (max-width: 420px) { .purchase-editor__actions { grid-template-columns: 1fr; } }
</style>
