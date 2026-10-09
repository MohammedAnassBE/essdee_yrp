<template>
	<section class="common-form-view" :class="{ 'common-form-view--compact': compact }" :aria-busy="loading">
		<header class="form-toolbar">
			<InlinePageNavigation
				:title-target="headingId"
				:show-document-navigation="Boolean(documentName)"
				:current-name="documentName"
				:document-label="heading"
				:navigation-disabled="mode === 'edit' || saving || loading"
			/>
			<div class="form-toolbar__identity">
				<h2 :id="headingId">{{ heading }}</h2>
				<div class="form-toolbar__meta">
					<small>{{ documentName ? documentName : `New ${doctype}` }}</small>
					<slot name="header-meta" :doc="form" :meta="meta" :loading="loading" />
				</div>
			</div>
			<div class="form-toolbar__actions">
				<template v-if="!loadFailed">
					<slot name="header-actions" :doc="form" :meta="meta" :loading="loading" :mode="mode" />
					<Button
						v-if="mode === 'edit' && (documentName || showCancel)"
						label="Cancel"
						severity="secondary"
						text
						:disabled="saving"
						@click="cancelEditing"
					/>
					<Button
						v-if="mode === 'view' && !readonly"
						class="form-edit-button"
						icon="pi pi-pencil"
						label="Edit"
						severity="secondary"
						outlined
						:disabled="loading"
						@click="mode = 'edit'"
					/>
					<Button
						v-else-if="mode === 'edit'"
						icon="pi pi-save"
						:label="documentName ? 'Save' : 'Create'"
						:loading="saving"
						:disabled="loading || readonly"
						@click="save"
					/>
				</template>
			</div>
		</header>

		<DocumentErrorDialog
			:message="loadFailed ? '' : error"
			:title="`${heading} could not be saved`"
		/>
		<Message v-if="success" severity="success" :closable="false">{{ success }}</Message>

		<div v-if="loading" class="form-loading" role="status" aria-live="polite" aria-label="Loading form">
			<Skeleton v-for="index in 8" :key="index" height="3rem" />
		</div>
		<section v-else-if="loadFailed" class="form-load-error" role="alert">
			<i class="pi pi-cloud-times" aria-hidden="true" />
			<div><strong>{{ heading }} could not be loaded</strong><span>{{ error || "Try loading the document again." }}</span></div>
			<Button label="Retry" icon="pi pi-refresh" severity="secondary" outlined @click="load" />
		</section>

		<form v-else-if="mode === 'edit'" class="form-body" @submit.prevent="save">
			<div v-if="requiresPromptName" class="form-section">
				<div class="form-section__columns">
					<div class="form-section__column">
						<FormField
							:field="promptNameField"
							:model-value="form.name"
							:form="form"
							required
							:invalid="Boolean(fieldErrors.name)"
							:error="fieldErrors.name || ''"
							@update:model-value="setValue('name', $event)"
						/>
					</div>
				</div>
			</div>

			<template v-for="tab in layout" :key="tab.key">
				<h3 v-if="layout.length > 1 || tab.label" class="form-tab-title">
					{{ tab.label || "Details" }}
				</h3>
				<section v-for="section in tab.sections" :key="section.key" class="form-section">
					<header v-if="section.label" class="form-section__header">
						<h3>{{ section.label }}</h3>
					</header>
					<div v-if="section.columns.some((column) => column.length)" class="form-section__columns">
						<div
							v-for="(column, columnIndex) in section.columns"
							:key="columnIndex"
							class="form-section__column"
						>
							<FormField
								v-for="field in column"
								:key="field.fieldname"
								:field="field"
								:model-value="form[field.fieldname]"
								:form="form"
								:disabled="readonly || isReadOnly(field)"
								:required="isRequired(field)"
								:invalid="Boolean(fieldErrors[field.fieldname])"
								:error="fieldErrors[field.fieldname] || ''"
								@update:model-value="setValue(field.fieldname, $event)"
							/>
						</div>
					</div>

					<ChildTableField
						v-for="table in section.tables"
						:key="table.fieldname"
						:field="table"
						:model-value="form[table.fieldname] || []"
						:child-meta="metaByName[table.options]"
						:disabled="readonly || isReadOnly(table)"
						:errors="childErrors[table.fieldname] || {}"
						@update:model-value="setValue(table.fieldname, $event)"
					/>
				</section>
			</template>
		</form>

		<template v-else>
			<slot name="view" :doc="form" :meta="meta">
				<div class="form-read-view">
					<template v-for="tab in layout" :key="tab.key">
				<h3 v-if="layout.length > 1 || tab.label" class="form-tab-title">
					{{ tab.label || "Details" }}
				</h3>
				<section v-for="section in tab.sections" :key="section.key" class="form-section view-section">
					<header v-if="section.label" class="form-section__header">
						<h3>{{ section.label }}</h3>
					</header>
					<div
						v-if="viewAsFields && section.columns.some((column) => column.length)"
						class="form-section__columns form-section__columns--read"
					>
						<div
							v-for="(column, columnIndex) in section.columns"
							:key="columnIndex"
							class="form-section__column"
						>
							<FormField
								v-for="field in column"
								:key="field.fieldname"
								:field="field"
								:model-value="form[field.fieldname]"
								:form="form"
								disabled
								:required="isRequired(field)"
								:show-open-button="false"
							/>
						</div>
					</div>
					<div v-else-if="sectionFields(section).length" class="view-field-grid">
						<div
							v-for="field in sectionFields(section)"
							:key="field.fieldname"
							class="view-field"
							:class="{ 'view-field--wide': isWideReadField(field) }"
						>
							<span class="view-field__label">{{ field.label || field.fieldname }}</span>
							<a
								v-if="field.fieldtype === 'Link' && hasValue(form[field.fieldname])"
								class="view-field__value view-field__link"
								:href="webDocumentPath(field.options, form[field.fieldname])"
								target="_blank"
								rel="noopener"
							>
								{{ displayValue(form[field.fieldname], field) }}
							</a>
							<span v-else class="view-field__value">
								{{ displayValue(form[field.fieldname], field) }}
							</span>
						</div>
					</div>

					<section v-for="table in section.tables" :key="table.fieldname" class="view-table">
						<header>
							<h4>{{ table.label || table.fieldname }}</h4>
							<span>{{ (form[table.fieldname] || []).length }} rows</span>
						</header>
						<DataTable
							:value="form[table.fieldname] || []"
							scrollable
							size="small"
							:pt="{ tableContainer: { tabindex: 0, role: 'region', 'aria-label': `${table.label || table.fieldname} rows` } }"
						>
							<Column
								v-for="column in childViewColumns(table)"
								:key="column.fieldname"
								:field="column.fieldname"
								:header="column.label || column.fieldname"
							>
								<template #body="{ data }">
									{{ displayValue(data[column.fieldname], column) }}
								</template>
							</Column>
							<template #empty>
								<div class="view-table__empty">No rows.</div>
							</template>
						</DataTable>
					</section>
				</section>
					</template>
				</div>
			</slot>
		</template>
	</section>
</template>

<script setup>
import Button from "primevue/button"
import Column from "primevue/column"
import DataTable from "primevue/datatable"
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import { computed, reactive, ref, watch } from "vue"

import { createDoc, getDoc, getMeta, updateDoc } from "../../api/frappe.js"
import { webDocumentPath } from "../../router/webDocumentRoutes.js"
import ChildTableField from "./ChildTableField.vue"
import FormField from "./FormField.vue"
import DocumentErrorDialog from "../documents/DocumentErrorDialog.vue"
import { plainTextFromHtml } from "../../utils/documentValues.js"
import InlinePageNavigation from "../navigation/InlinePageNavigation.vue"

const props = defineProps({
	doctype: { type: String, required: true },
	name: { type: String, default: "" },
	title: { type: String, default: "" },
	initialValues: { type: Object, default: () => ({}) },
	readonly: { type: Boolean, default: false },
	excludeFields: { type: Array, default: () => [] },
	includeFields: { type: Array, default: () => [] },
	viewAsFields: { type: Boolean, default: false },
	compact: { type: Boolean, default: false },
	showCancel: { type: Boolean, default: false },
	initialMode: {
		type: String,
		default: "auto",
		validator: (value) => ["auto", "view", "edit"].includes(value),
	},
})

const emit = defineEmits(["saved", "loaded", "cancel", "change"])
const headingId = computed(() => `${props.doctype.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-form-title`)

const noValueFieldtypes = new Set([
	"Section Break",
	"Column Break",
	"Tab Break",
	"HTML",
	"Button",
	"Heading",
	"Fold",
	"Image",
	"Attach Image",
	"Signature",
])

const form = reactive({})
const metas = ref([])
const loading = ref(false)
const saving = ref(false)
const error = ref("")
const loadFailed = ref(false)
const success = ref("")
const fieldErrors = reactive({})
const childErrors = reactive({})
const documentName = ref("")
const mode = ref("edit")
let cleanDocument = {}
let loadSequence = 0

const metaByName = computed(() =>
	Object.fromEntries(metas.value.filter((meta) => meta?.name).map((meta) => [meta.name, meta])),
)
const meta = computed(() => metaByName.value[props.doctype] || metas.value[0] || null)
const heading = computed(() => props.title || meta.value?.label || props.doctype)
const requiresPromptName = computed(
	() => !documentName.value && String(meta.value?.autoname || "").toLowerCase() === "prompt",
)
const promptNameField = {
	fieldname: "name",
	fieldtype: "Data",
	label: "Name",
	reqd: 1,
}
const excludedFields = computed(() => new Set(props.excludeFields))
const includedFields = computed(() => new Set(props.includeFields))
const layoutFieldtypes = new Set(["Section Break", "Column Break", "Tab Break"])

const visibleFields = computed(() =>
	(meta.value?.fields || []).filter(
		(field) =>
			field.fieldname &&
			!field.hidden &&
			!excludedFields.value.has(field.fieldname) &&
			(!includedFields.value.size ||
				layoutFieldtypes.has(field.fieldtype) ||
				includedFields.value.has(field.fieldname)) &&
			isVisible(field),
	),
)

const layout = computed(() => buildLayout(visibleFields.value))

watch(
	() => [props.doctype, props.name],
	() => load(),
	{ immediate: true },
)

async function load() {
	const sequence = ++loadSequence
	loading.value = true
	loadFailed.value = false
	error.value = ""
	success.value = ""
	clearObject(fieldErrors)
	clearObject(childErrors)
	try {
		const [loadedMetas, document] = await Promise.all([
			getMeta(props.doctype),
			props.name ? getDoc(props.doctype, props.name) : Promise.resolve(null),
		])
		if (sequence !== loadSequence) return
		metas.value = loadedMetas
		documentName.value = document?.name || ""
		replaceForm(buildInitialValues(loadedMetas, document))
		cleanDocument = clone(form)
		mode.value = resolveInitialMode(Boolean(document))
		emit("loaded", { doc: { ...form }, meta: meta.value })
	} catch (reason) {
		if (sequence !== loadSequence) return
		loadFailed.value = true
		error.value = reason.message || `Unable to load ${props.doctype}.`
		metas.value = []
		documentName.value = ""
		replaceForm({})
		cleanDocument = {}
		mode.value = "view"
	} finally {
		if (sequence === loadSequence) loading.value = false
	}
}

function buildInitialValues(loadedMetas, document) {
	if (document) return document
	const parentMeta = loadedMetas.find((row) => row.name === props.doctype) || loadedMetas[0]
	const values = {}
	for (const field of parentMeta?.fields || []) {
		if (!field.fieldname || noValueFieldtypes.has(field.fieldtype)) continue
		if (["Table", "Table MultiSelect"].includes(field.fieldtype)) {
			values[field.fieldname] = []
		} else if (field.default !== undefined && field.default !== null) {
			values[field.fieldname] = normaliseDefault(field)
		}
	}
	return { ...values, ...props.initialValues }
}

function normaliseDefault(field) {
	if (field.fieldtype === "Check") return Number(field.default) ? 1 : 0
	if (field.fieldtype === "Date" && String(field.default).toLowerCase() === "today") return localDateValue(new Date())
	if (field.fieldtype === "Time" && String(field.default).toLowerCase() === "now") return localTimeValue(new Date())
	return field.default
}

function localDateValue(value) {
	return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`
}

function localTimeValue(value) {
	return `${String(value.getHours()).padStart(2, "0")}:${String(value.getMinutes()).padStart(2, "0")}:${String(value.getSeconds()).padStart(2, "0")}`
}

function replaceForm(values) {
	clearObject(form)
	Object.assign(form, values || {})
}

function clone(value) {
	return JSON.parse(JSON.stringify(value || {}))
}

function resolveInitialMode(hasDocument) {
	if (props.readonly) return "view"
	if (props.initialMode !== "auto") return props.initialMode
	return hasDocument ? "view" : "edit"
}

function cancelEditing() {
	if (!documentName.value) {
		emit("cancel")
		return
	}
	replaceForm(cleanDocument)
	clearObject(fieldErrors)
	clearObject(childErrors)
	error.value = ""
	success.value = ""
	mode.value = "view"
}

function clearObject(object) {
	for (const key of Object.keys(object)) delete object[key]
}

function setValue(fieldname, value) {
	form[fieldname] = value
	delete fieldErrors[fieldname]
	error.value = ""
	success.value = ""
	emit("change", { fieldname, value, doc: form })
}

function isVisible(field) {
	return evaluateCondition(field.depends_on, true)
}

function isRequired(field) {
	return Boolean(field.reqd) || evaluateCondition(field.mandatory_depends_on, false)
}

function isReadOnly(field) {
	return Boolean(field.read_only) || evaluateCondition(field.read_only_depends_on, false)
}

function evaluateCondition(condition, fallback) {
	if (!condition) return fallback
	const expression = String(condition).replace(/^eval:/, "").trim()
	const direct = expression.match(/^!?doc\.([A-Za-z0-9_]+)$/)
	if (direct) {
		const value = Boolean(form[direct[1]])
		return expression.startsWith("!") ? !value : value
	}
	const fieldname = expression.match(/^[A-Za-z0-9_]+$/)?.[0]
	if (fieldname) return Boolean(form[fieldname])

	const comparison = expression.match(
		/^doc\.([A-Za-z0-9_]+)\s*(===|==|!==|!=)\s*['"]([^'"]*)['"]$/,
	)
	if (comparison) {
		const matches = String(form[comparison[1]] ?? "") === comparison[3]
		return ["!=", "!=="].includes(comparison[2]) ? !matches : matches
	}
	return fallback
}

function buildLayout(fields) {
	const tabs = []
	let tab = createTab("", "main")
	let section = createSection("", "main-section")
	let column = section.columns[0]
	tab.sections.push(section)
	tabs.push(tab)

	for (const field of fields) {
		if (field.fieldtype === "Tab Break") {
			tab = createTab(field.label || "Details", field.fieldname)
			section = createSection("", `${field.fieldname}-section`)
			column = section.columns[0]
			tab.sections.push(section)
			tabs.push(tab)
			continue
		}
		if (field.fieldtype === "Section Break") {
			section = createSection(field.label || "", field.fieldname)
			column = section.columns[0]
			tab.sections.push(section)
			continue
		}
		if (field.fieldtype === "Column Break") {
			column = []
			section.columns.push(column)
			continue
		}
		if (["Table", "Table MultiSelect"].includes(field.fieldtype)) {
			section.tables.push(field)
			continue
		}
		if (!noValueFieldtypes.has(field.fieldtype)) column.push(field)
	}

	return tabs
		.map((currentTab) => ({
			...currentTab,
			sections: currentTab.sections.filter(
				(currentSection) =>
					currentSection.tables.length || currentSection.columns.some((fieldsInColumn) => fieldsInColumn.length),
			),
		}))
		.filter((currentTab) => currentTab.sections.length)
}

function createTab(label, key) {
	return { label, key, sections: [] }
}

function createSection(label, key) {
	return { label, key, columns: [[]], tables: [] }
}

function sectionFields(section) {
	return section.columns.flat()
}

function isWideReadField(field) {
	if (["Text", "Small Text", "Long Text", "Text Editor", "Code", "Markdown"].includes(field.fieldtype)) return true
	return /(?:address details|comments?|description|terms?(?: and)? conditions?)/i.test(`${field.label || ""} ${field.fieldname || ""}`)
}

function childViewColumns(table) {
	const fields = (metaByName.value[table.options]?.fields || []).filter(
		(field) => field.fieldname && !field.hidden && !noValueFieldtypes.has(field.fieldtype),
	)
	const preferred = fields.filter((field) => field.in_list_view || field.reqd)
	return preferred.length ? preferred : fields.slice(0, 6)
}

function displayValue(value, field) {
	if (value === null || value === undefined || value === "") return "—"
	if (field.fieldtype === "Check") return Number(value) ? "Yes" : "No"
	if (Array.isArray(value)) return value.join(", ")
	if (typeof value === "object") return JSON.stringify(value)
	return typeof value === "string" ? plainTextFromHtml(value) : value
}

function validate() {
	clearObject(fieldErrors)
	clearObject(childErrors)
	if (requiresPromptName.value && !hasValue(form.name)) fieldErrors.name = "Name is required."

	for (const field of visibleFields.value) {
		if (["Table", "Table MultiSelect"].includes(field.fieldtype)) {
			validateChildTable(field)
			continue
		}
		if (noValueFieldtypes.has(field.fieldtype) || !isRequired(field)) continue
		if (!hasValue(form[field.fieldname])) {
			fieldErrors[field.fieldname] = `${field.label || field.fieldname} is required.`
		}
	}
	return !Object.keys(fieldErrors).length && !Object.keys(childErrors).length
}

function validateChildTable(table) {
	const rows = form[table.fieldname] || []
	if (isRequired(table) && !rows.length) {
		fieldErrors[table.fieldname] = `${table.label || table.fieldname} requires at least one row.`
		return
	}
	const errors = {}
	const childMeta = metaByName.value[table.options]
	for (const [rowIndex, row] of rows.entries()) {
		for (const field of childMeta?.fields || []) {
			if (!field.fieldname || field.hidden || !field.reqd || noValueFieldtypes.has(field.fieldtype)) continue
			if (!hasValue(row[field.fieldname])) {
				errors[`${rowIndex}.${field.fieldname}`] = `${field.label || field.fieldname} is required.`
			}
		}
	}
	if (Object.keys(errors).length) childErrors[table.fieldname] = errors
}

function hasValue(value) {
	return value !== null && value !== undefined && value !== ""
}

function payload() {
	const values = {}
	for (const field of meta.value?.fields || []) {
		if (!field.fieldname || noValueFieldtypes.has(field.fieldtype)) continue
		if (Object.hasOwn(form, field.fieldname)) values[field.fieldname] = form[field.fieldname]
	}
	if (requiresPromptName.value && form.name) values.name = form.name
	return values
}

async function save() {
	if (loading.value || saving.value || loadFailed.value || props.readonly || !meta.value) return
	error.value = ""
	success.value = ""
	if (!validate()) {
		error.value = ""
		return
	}

	saving.value = true
	try {
		const saved = documentName.value
			? await updateDoc(props.doctype, documentName.value, payload())
			: await createDoc(props.doctype, payload())
		documentName.value = saved?.name || documentName.value
		replaceForm(saved || form)
		cleanDocument = clone(form)
		mode.value = "view"
		success.value = `${props.doctype} ${documentName.value || "document"} saved.`
		emit("saved", saved)
	} catch (reason) {
		error.value = reason.message || `Unable to save ${props.doctype}.`
	} finally {
		saving.value = false
	}
}

defineExpose({ save, reload: load, doc: form, mode })
</script>

<style scoped>
.common-form-view {
	display: grid;
	gap: 14px;
}

.common-form-view--compact {
	gap: 10px;
}

.form-toolbar,
.form-toolbar__actions,
.form-section__header {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 12px;
}

.form-toolbar {
	min-height: 58px;
	padding: 10px 12px 10px 16px;
	justify-content: flex-start;
	background: var(--erp-surface);
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-panel-radius);
	box-shadow: var(--erp-shadow-xs);
}

.form-toolbar h2 {
	margin: 0;
	color: var(--erp-text);
	font-size: 1.12rem;
	font-weight: 760;
	letter-spacing: -0.018em;
}

.form-toolbar__identity {
	display: grid;
	min-width: 0;
	flex: 1 1 auto;
	gap: 2px;
}

.form-toolbar__meta {
	display: flex;
	align-items: center;
	gap: 8px;
	min-height: 20px;
}

.form-toolbar small {
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.form-toolbar__actions {
	flex: 0 0 auto;
	flex-wrap: nowrap;
	margin-left: auto;
}

.form-toolbar__actions :deep(.p-button) {
	min-height: var(--erp-control-height);
	white-space: nowrap;
}

.form-loading {
	display: grid;
	grid-template-columns: repeat(2, minmax(0, 1fr));
	gap: 16px;
}

.form-load-error {
	display: grid;
	min-height: 220px;
	padding: var(--erp-space-6);
	place-content: center;
	justify-items: center;
	gap: 10px;
	color: var(--erp-text-muted);
	text-align: center;
	background: var(--erp-surface);
	border: 1px dashed var(--erp-border-strong);
	border-radius: var(--erp-panel-radius);
}

.form-load-error > i { color: var(--erp-danger); font-size: 24px; }
.form-load-error > div { display: grid; gap: 4px; }
.form-load-error strong { color: var(--erp-text); }
.form-load-error span { max-width: 520px; font-size: var(--erp-font-size-caption); }

.form-body,
.form-read-view {
	display: grid;
	gap: 14px;
}

.form-tab-title {
	margin: 8px 0 0;
	padding: 0 2px 8px;
	color: var(--erp-accent-hover);
	font-size: 0.9rem;
	font-weight: 780;
	letter-spacing: -0.01em;
	border-bottom: 1px solid var(--erp-border-strong);
}

.form-section {
	display: grid;
	gap: 15px;
	padding: 16px;
	background: var(--erp-surface);
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-panel-radius);
	box-shadow: none;
}

.form-section__header h3 {
	margin: 0;
	color: var(--erp-text);
	font-size: 0.9rem;
	font-weight: 740;
}

.form-section__columns {
	display: grid;
	grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
	gap: 18px 24px;
}

.form-section__column {
	display: grid;
	align-content: start;
	gap: 13px;
	min-width: 0;
}

.common-form-view--compact .form-body,
.common-form-view--compact .form-read-view {
	gap: 10px;
}

.common-form-view--compact .form-section {
	gap: 12px;
	padding: 14px 16px;
}

.common-form-view--compact .form-section__columns {
	grid-template-columns: repeat(2, minmax(0, 1fr));
	gap: 28px;
}

.common-form-view--compact .form-section__column {
	gap: 12px;
}

.common-form-view--compact :deep(.form-field) {
	gap: 4px;
}

.common-form-view--compact :deep(.p-inputtext),
.common-form-view--compact :deep(.p-inputnumber-input),
.common-form-view--compact :deep(.p-select-label) {
	min-height: 34px;
	padding-block: 6px;
}

.view-field-grid {
	display: grid;
	grid-template-columns: repeat(4, minmax(0, 1fr));
	grid-auto-flow: dense;
	gap: 1px;
	overflow: hidden;
	background: var(--erp-border);
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-panel-radius);
}

.view-field {
	display: flex;
	min-height: 54px;
	padding: 9px 12px;
	background: var(--erp-surface);
	flex-direction: column;
	justify-content: center;
}

.view-field--wide {
	grid-column: span 2;
}

.view-field__value {
	color: var(--erp-text);
	font-size: var(--erp-font-size-table);
	font-weight: 650;
	overflow-wrap: anywhere;
	white-space: pre-line;
}

.view-field__link {
	color: var(--erp-accent-hover);
	text-decoration: none;
}

.view-field__link:hover,
.view-field__link:focus-visible {
	text-decoration: underline;
}

.view-field__link:focus-visible {
	border-radius: 3px;
	outline: 2px solid var(--erp-accent-dark);
	outline-offset: 2px;
}

.view-field__label {
	margin-bottom: 3px;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	font-weight: 650;
	letter-spacing: 0.015em;
}

.view-table {
	display: grid;
	gap: 10px;
}

.view-table > header {
	display: flex;
	align-items: center;
	justify-content: space-between;
}

.view-table h4 {
	margin: 0;
	font-size: 0.9rem;
}

.view-table header span {
	color: var(--erp-text-muted);
	font-size: 0.72rem;
}

.view-table__empty {
	padding: 22px;
	color: var(--erp-text-muted);
	text-align: center;
}

@media (max-width: 1100px) {
	.view-field-grid {
		grid-template-columns: repeat(2, minmax(0, 1fr));
	}
}

@media (max-width: 700px) {
	.form-toolbar {
		align-items: flex-start;
		flex-direction: column;
	}

	.form-toolbar__actions {
		width: 100%;
		justify-content: flex-start;
		flex-wrap: wrap;
		margin-left: 0;
	}

	.form-toolbar__actions :deep(.p-button) {
		flex: 1 1 auto;
	}

	.form-loading,
	.form-section__columns,
	.view-field-grid {
		grid-template-columns: 1fr;
	}

	.view-field--wide {
		grid-column: span 1;
	}

	.common-form-view--compact .form-section__columns {
		grid-template-columns: 1fr;
	}

	.form-section {
		padding: 14px;
	}
}
</style>
