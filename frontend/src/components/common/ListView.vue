<template>
	<section
		class="common-list-view"
		:class="{
			'common-list-view--viewport-bounded': viewportBounded,
			'common-list-view--empty': isEmptyResult,
			'common-list-view--filters-open': mobileQuickFiltersOpen,
		}"
	>
		<header class="list-page-head">
			<div class="list-title-block">
				<span v-if="eyebrow" class="list-eyebrow">{{ eyebrow }}</span>
				<div class="list-title-line">
					<InlinePageNavigation v-if="navigationEnabled" :title-target="headingId" />
					<div>
						<h1 :id="headingId">{{ title || doctype }}</h1>
						<p v-if="subtitle">{{ subtitle }}</p>
					</div>
				</div>
			</div>
			<div class="list-toolbar__actions">
				<div class="list-toolbar__primary"><slot name="toolbar-actions"></slot></div>
				<span class="list-search">
					<i class="pi pi-search" aria-hidden="true"></i>
					<InputText
						v-model="search"
						:placeholder="searchPlaceholder"
						:aria-label="searchPlaceholder"
						@keyup.enter="applySearch"
					/>
				</span>
				<div class="list-toolbar__secondary">
					<Button
						class="list-filter-action"
						:class="{ 'list-filter-action--active': activeFilterCount }"
						icon="pi pi-filter"
						label="Filters"
						severity="secondary"
						outlined
						:badge="activeFilterCount ? String(activeFilterCount) : undefined"
						@click="showFilters = true"
					/>
					<Button
						icon="pi pi-sliders-h"
						label="Columns"
						severity="secondary"
						outlined
						:disabled="!allowedFieldsReady"
						@click="openColumnsDialog"
					/>
					<Button
						icon="pi pi-refresh"
						label="Refresh"
						severity="secondary"
						text
						rounded
						aria-label="Refresh"
						:loading="loading"
						@click="refresh"
					/>
					<Button
						class="list-clear-filter-action"
						:class="{ 'list-clear-filter-action--active': hasActiveQuery }"
						icon="pi pi-filter-slash"
						label="Clear Filters"
						severity="secondary"
						outlined
						:disabled="!hasActiveQuery"
						@click="clearFilters"
					/>
				</div>
			</div>
		</header>

		<button
			v-if="standardFilterFields.length"
			type="button"
			class="mobile-quick-filter-toggle"
			:class="{ 'mobile-quick-filter-toggle--active': activeQuickFilterCount }"
			:aria-label="activeQuickFilterCount ? `Quick filters, ${activeQuickFilterCount} active` : 'Quick filters'"
			:aria-expanded="mobileQuickFiltersOpen"
			@click="mobileQuickFiltersOpen = !mobileQuickFiltersOpen"
		>
			<span><i class="pi pi-sliders-h" aria-hidden="true"></i> Quick filters</span>
			<span v-if="activeQuickFilterCount" class="mobile-quick-filter-toggle__count">{{ activeQuickFilterCount }}</span>
			<i class="pi" :class="mobileQuickFiltersOpen ? 'pi-chevron-up' : 'pi-chevron-down'" aria-hidden="true"></i>
		</button>

		<ListviewQuickFilters
			v-if="standardFilterFields.length"
			v-model="quickFilters"
			class="list-quick-filters"
			:class="{ 'list-quick-filters--open': mobileQuickFiltersOpen }"
			:fields="standardFilterFields"
			@change="quickFiltersChanged"
		/>

		<nav
			v-if="statusTabs.length"
			class="list-status-tabs"
			aria-label="Status filters"
		>
			<button
				v-for="tab in statusTabs"
				:key="tab.value || '__all__'"
				type="button"
				class="list-status-tab"
				:class="{ 'list-status-tab--active': activeStatus === tab.value }"
				:aria-pressed="activeStatus === tab.value"
				:disabled="!metadataReady"
				@click="selectStatus(tab.value)"
			>
				<span v-if="tab.value !== ''" class="list-status-tab__dot" :class="statusTone(tab.label)"></span>
				{{ tab.label }}
				<span class="list-status-tab__count">{{ tab.count }}</span>
			</button>
		</nav>
		<label
			v-if="statusTabs.length"
			class="list-status-select"
		>
			<span>Status</span>
			<Select
				:model-value="activeStatus"
				:options="statusSelectOptions"
				option-label="label"
				option-value="value"
				:placeholder="statusSelectOptions[0]?.label || 'All statuses'"
				aria-label="Status filter"
				fluid
				:disabled="!metadataReady"
				@update:model-value="selectStatus"
			/>
		</label>

		<div v-if="error" class="list-load-error" role="alert">
			<span class="list-load-error__icon" aria-hidden="true"><i class="pi pi-exclamation-circle"></i></span>
			<div>
				<strong>Unable to load {{ title || doctype }}</strong>
				<span>{{ error }}</span>
			</div>
			<Button label="Retry" icon="pi pi-refresh" severity="danger" outlined :loading="loading" @click="retryLoad" />
		</div>
		<Message v-if="bulkNotice" severity="success" closable @close="bulkNotice = ''">
			{{ bulkNotice }}
		</Message>
		<Message v-if="bulkError" severity="error" closable @close="bulkError = null">
			<div class="bulk-message">
				<strong>{{ bulkError.title }}</strong>
				<span v-for="line in bulkError.lines" :key="line">{{ line }}</span>
			</div>
		</Message>

		<div v-if="showBulkBar" class="bulk-bar">
			<div class="bulk-bar__summary">
				<strong>{{ selectedRows.length }} selected</strong>
				<span v-if="selectedDraftRows.length">{{ selectedDraftRows.length }} draft</span>
				<span v-if="selectedSubmittedRows.length">{{ selectedSubmittedRows.length }} submitted</span>
			</div>
			<div class="bulk-bar__actions">
				<Button
					v-if="canBulkEdit"
					label="Edit"
					icon="pi pi-pencil"
					severity="secondary"
					outlined
					size="small"
					:disabled="Boolean(bulkActing)"
					:loading="bulkActing === 'edit' || bulkEditLoading"
					@click="openBulkEditDialog"
				/>
				<Button
					v-if="isSubmittable && canBulkSubmit"
					:label="`Submit (${selectedDraftRows.length})`"
					icon="pi pi-arrow-right"
					size="small"
					:disabled="!selectedDraftRows.length || Boolean(bulkActing)"
					:loading="bulkActing === 'submit'"
					@click="requestBulkAction('submit')"
				/>
				<Button
					v-if="isSubmittable && canBulkCancel"
					:label="`Cancel (${selectedSubmittedRows.length})`"
					icon="pi pi-ban"
					severity="danger"
					outlined
					size="small"
					:disabled="!selectedSubmittedRows.length || Boolean(bulkActing)"
					:loading="bulkActing === 'cancel'"
					@click="requestBulkAction('cancel')"
				/>
				<Button
					icon="pi pi-times"
					severity="secondary"
					text
					rounded
					size="small"
					aria-label="Clear selection"
					:disabled="Boolean(bulkActing)"
					@click="clearSelection"
				/>
			</div>
		</div>

		<div v-if="!error" class="list-table-frame">
			<div v-if="loading && !rows.length" class="list-loading" aria-label="Loading records">
				<Skeleton v-for="index in 6" :key="index" class="list-loading-skeleton" height="42px" />
			</div>
			<DataTable
				v-else
				:value="rows"
				v-model:selection="selectedRows"
				:loading="loading"
				data-key="name"
				:sort-field="sortField"
				:sort-order="sortOrder"
				class="premium-list-table"
				lazy
				row-hover
				scrollable
				:pt="{ tableContainer: { tabindex: 0, role: 'region', 'aria-label': `${title || doctype} records` } }"
				:table-style="{ minWidth: minTableWidth }"
				:row-class="rowClass"
				@sort="sortChanged"
				@row-click="rowClicked"
			>
				<Column
					v-if="showBulkSelection"
					selection-mode="multiple"
					header-style="width: 44px"
					body-style="width: 44px; text-align: center"
				/>
				<Column
					v-for="column in activeColumns"
					:key="column.fieldname"
					:field="column.fieldname"
					:header="columnLabel(column)"
					:header-class="isNumericColumn(column) ? 'list-number-column' : ''"
					:body-class="isNumericColumn(column) ? 'list-number-column' : ''"
					sortable
				>
					<template #body="{ data }">
						<slot :name="`cell-${column.fieldname}`" :row="data" :value="data[column.fieldname]">
							<div v-if="column.fieldname === 'name'" class="list-document-cell">
								<strong :title="displayValue(data[column.fieldname], column, data)">{{ displayValue(data[column.fieldname], column, data) }}</strong>
							</div>
							<img
								v-else-if="isImageColumn(column) && hasFilterValue(data[column.fieldname])"
								class="list-image-value"
								:src="String(data[column.fieldname])"
								:alt="columnLabel(column)"
								loading="lazy"
							/>
							<DocumentStatusBadge
								v-else-if="isStatusColumn(column) && hasFilterValue(data[column.fieldname])"
								:docstatus="column.fieldname === 'docstatus' ? data[column.fieldname] : null"
								:label="column.fieldname === 'docstatus' ? '' : String(data[column.fieldname])"
							/>
							<span
								v-else-if="column.fieldtype === 'Link'"
								class="list-link-value"
								:class="`list-link-value--${column.fieldname}`"
								:title="displayValue(data[column.fieldname], column, data)"
							>
								{{ displayValue(data[column.fieldname], column, data) }}
							</span>
							<span v-else class="list-plain-value" :title="displayValue(data[column.fieldname], column, data)">
								{{ displayValue(data[column.fieldname], column, data) }}
							</span>
						</slot>
					</template>
				</Column>
				<Column v-if="$slots.actions" header="" frozen align-frozen="right">
					<template #body="{ data }">
						<slot name="actions" :row="data"></slot>
					</template>
				</Column>
				<Column v-if="clickable" header="" class="list-chevron-column">
					<template #body="{ data }">
						<button
							type="button"
							class="list-row-open"
							:aria-label="`Open ${data.name || 'record'}`"
							:title="`Open ${data.name || 'record'}`"
							@click.stop="openRow(data)"
						>
							<i class="pi pi-chevron-right list-row-chevron" aria-hidden="true"></i>
						</button>
					</template>
				</Column>
				<template #empty>
					<div class="list-empty">
						<span class="list-empty__icon"><i class="pi pi-inbox" aria-hidden="true"></i></span>
						<strong>No records found</strong>
						<span>{{ hasActiveQuery ? 'Try changing the search or filters.' : `No ${title || doctype} records are available yet.` }}</span>
					</div>
				</template>
			</DataTable>
			<div v-if="rows.length" class="mobile-list-records" role="list" :aria-label="`${title || doctype} records`">
				<article
					v-for="row in rows"
					:key="row.name"
					class="mobile-list-record"
					role="listitem"
				>
					<header :class="{ 'mobile-list-record__header--without-selection': !showBulkSelection }">
						<label v-if="showBulkSelection" class="mobile-list-record__select" @click.stop>
							<input type="checkbox" :checked="isRowSelected(row)" :aria-label="`Select ${row.name || 'record'}`" @change="toggleMobileSelection(row, $event)" />
						</label>
						<div class="mobile-list-record__identity">
							<span>{{ columnLabel(mobileColumns[0]) }}</span>
							<slot :name="`cell-${mobileColumns[0]?.fieldname}`" :row="row" :value="row[mobileColumns[0]?.fieldname]">
								<strong>{{ displayValue(row[mobileColumns[0]?.fieldname], mobileColumns[0], row) }}</strong>
							</slot>
						</div>
						<button v-if="clickable" type="button" class="mobile-list-record__open" :aria-label="`Open ${row.name || 'record'}`" @click="openRow(row)">
							<i class="pi pi-chevron-right" aria-hidden="true"></i>
						</button>
					</header>
					<div v-if="mobileColumns.length > 1" class="mobile-list-record__facts">
						<div v-for="column in mobileColumns.slice(1)" :key="column.fieldname">
							<span>{{ columnLabel(column) }}</span>
							<slot :name="`cell-${column.fieldname}`" :row="row" :value="row[column.fieldname]">
								<img
									v-if="isImageColumn(column) && hasFilterValue(row[column.fieldname])"
									class="list-image-value"
									:src="String(row[column.fieldname])"
									:alt="columnLabel(column)"
									loading="lazy"
								/>
								<DocumentStatusBadge
									v-else-if="isStatusColumn(column) && hasFilterValue(row[column.fieldname])"
									:docstatus="column.fieldname === 'docstatus' ? row[column.fieldname] : null"
									:label="column.fieldname === 'docstatus' ? '' : String(row[column.fieldname])"
								/>
								<strong v-else>{{ displayValue(row[column.fieldname], column, row) }}</strong>
							</slot>
						</div>
					</div>
					<div v-if="$slots.actions" class="mobile-list-record__actions" @click.stop>
						<slot name="actions" :row="row"></slot>
					</div>
				</article>
			</div>
			<div v-else-if="!loading" class="mobile-list-empty">
				<span class="list-empty__icon"><i class="pi pi-inbox" aria-hidden="true"></i></span>
				<strong>No records found</strong>
				<span>{{ hasActiveQuery ? 'Try changing the search or filters.' : `No ${title || doctype} records are available yet.` }}</span>
			</div>
		</div>

		<Paginator
			v-if="!error && total > pageSize"
			:first="first"
			:rows="pageSize"
			:total-records="total"
			:rows-per-page-options="[10, 20, 50, 100]"
			@page="pageChanged"
		/>

		<UserListviewColumns
			v-model:visible="showColumns"
			:doctype="doctype"
			:columns="columnOptions"
			:settings-ready="allowedFieldsReady"
			:view-fields="viewFields"
			@saved="columnsSaved"
		/>
		<ListviewFilters
			v-model:visible="showFilters"
			v-model="advancedFilters"
			:doctype="doctype"
			:fields="filterFields"
			@apply="filtersApplied"
		/>

		<Dialog
			v-model:visible="showBulkEdit"
			header="Bulk Edit"
			modal
			class="erp-dialog--md"
		>
			<div class="bulk-edit-form">
				<div class="bulk-edit-selection">{{ selectedRows.length }} records selected</div>
				<label class="bulk-edit-field">
					<span>Field</span>
					<Select
						v-model="bulkEditFieldKey"
						:options="bulkEditFields"
						option-label="label"
						option-value="key"
						:loading="bulkEditLoading"
						placeholder="Select field"
						filter
						fluid
					/>
				</label>
				<FormField
					v-if="bulkEditField"
					v-model="bulkEditValue"
					:field="bulkEditField"
					:show-open-button="false"
				/>
				<small v-if="bulkEditField && isEmptyBulkValue" class="bulk-edit-help">
					Leaving the value empty clears this field where validation allows.
				</small>
			</div>
			<template #footer>
				<Button
					label="Cancel"
					severity="secondary"
					text
					:disabled="bulkEditApplying"
					@click="showBulkEdit = false"
				/>
				<Button
					:label="`Update ${selectedRows.length} record${selectedRows.length === 1 ? '' : 's'}`"
					icon="pi pi-check"
					:disabled="!bulkEditField || bulkEditLoading || bulkEditApplying"
					:loading="bulkEditApplying"
					@click="applyBulkEdit"
				/>
			</template>
		</Dialog>

		<Dialog
			v-model:visible="showBulkConfirm"
			:header="bulkConfirmTitle"
			modal
			class="erp-dialog--sm"
		>
			<p class="bulk-confirm-copy">{{ bulkConfirmMessage }}</p>
			<template #footer>
				<Button
					label="Keep"
					severity="secondary"
					text
					@click="showBulkConfirm = false"
				/>
				<Button
					:label="pendingBulkAction === 'submit' ? 'Submit' : 'Cancel Documents'"
					:severity="pendingBulkAction === 'cancel' ? 'danger' : undefined"
					@click="confirmBulkAction"
				/>
			</template>
		</Dialog>
	</section>
</template>

<script setup>
import Button from "primevue/button"
import Column from "primevue/column"
import DataTable from "primevue/datatable"
import Dialog from "primevue/dialog"
import InputText from "primevue/inputtext"
import Message from "primevue/message"
import Paginator from "primevue/paginator"
import Select from "primevue/select"
import Skeleton from "primevue/skeleton"
import { computed, onBeforeUnmount, ref, watch } from "vue"
import { useRoute } from "vue-router"

import {
	bulkUpdateField,
	cancelDoc,
	getBulkEditFields,
	getCount,
	getList,
	getMeta,
	getUserListview,
	submitDoc,
} from "../../api/frappe.js"
import DocumentStatusBadge from "../documents/DocumentStatusBadge.vue"
import InlinePageNavigation from "../navigation/InlinePageNavigation.vue"
import FormField from "./FormField.vue"
import {
	activeCurrencyReferences,
	buildColumnOptions,
	createListInitialisationGuard,
	currencyReferenceField,
	frappeStandardFilterFields,
} from "./listColumns.js"
import ListviewFilters from "./ListviewFilters.vue"
import ListviewQuickFilters from "./ListviewQuickFilters.vue"
import UserListviewColumns from "./UserListviewColumns.vue"
import {
	createListNavigationState,
	deterministicOrder,
	navigationStorageKey,
	readNavigationState,
} from "../../utils/listNavigation.js"

const props = defineProps({
	doctype: { type: String, required: true },
	title: { type: String, default: "" },
	eyebrow: { type: String, default: "" },
	subtitle: { type: String, default: "" },
	searchPlaceholder: { type: String, default: "Search records…" },
	nameColumnLabel: { type: String, default: "Document" },
	columnLabels: { type: Object, default: () => ({}) },
	linkFilters: { type: Object, default: () => ({}) },
	rowMark: { type: String, default: "DOC" },
	filters: { type: [Array, Object], default: () => [] },
	initialAdvancedFilters: { type: Array, default: () => [] },
	excludedFilterFields: { type: Array, default: () => [] },
	defaultOrderBy: { type: String, default: "modified desc" },
	defaultColumns: { type: Array, default: () => [] },
	initialPageSize: { type: Number, default: 20 },
	minTableWidth: { type: String, default: "900px" },
	clickable: { type: Boolean, default: true },
	statusField: { type: String, default: "" },
	statusOptions: { type: Array, default: () => [] },
	initialStatus: { type: [String, Number], default: "" },
	viewportBounded: { type: Boolean, default: false },
	allowBulkActions: { type: Boolean, default: true },
	selectable: { type: Boolean, default: false },
	navigationEnabled: { type: Boolean, default: true },
})

const emit = defineEmits(["row-click", "loaded", "selection-change", "update:advancedFilters"])
const route = useRoute()
const headingId = computed(() => `${props.doctype.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-list-title`)

const filterExcludedFieldtypes = new Set([
	"Section Break",
	"Column Break",
	"Tab Break",
	"Attachment Gallery",
	"HTML",
	"Button",
	"Heading",
	"Fold",
	"Table",
	"Table MultiSelect",
	"Image",
])

const rows = ref([])
const total = ref(0)
const loading = ref(false)
const error = ref("")
const search = ref("")
const appliedSearch = ref("")
const first = ref(0)
const pageSize = ref(props.initialPageSize)
const sortField = ref(props.defaultOrderBy.split(" ")[0] || "modified")
const sortOrder = ref(props.defaultOrderBy.toLowerCase().endsWith(" asc") ? 1 : -1)
const metaFields = ref([])
const metaDocuments = ref([])
const doctypeMeta = ref(null)
const allowedFields = ref([])
const currencyFields = ref({})
const allowedFieldsReady = ref(false)
const metadataReady = ref(false)
const userColumns = ref(null)
const advancedFilters = ref(cloneFilters(props.initialAdvancedFilters))
const quickFilters = ref({})
const appliedQuickFilters = ref({})
const mobileQuickFiltersOpen = ref(false)
const showColumns = ref(false)
const showFilters = ref(false)
const activeStatus = ref("")
const statusCounts = ref({})
const selectedRows = ref([])
const bulkActing = ref("")
const bulkNotice = ref("")
const bulkError = ref(null)
const showBulkEdit = ref(false)
const bulkEditLoading = ref(false)
const bulkEditApplying = ref(false)
const bulkEditFields = ref([])
const bulkEditFieldsFor = ref("")
const bulkEditFieldKey = ref("")
const bulkEditValue = ref("")
const showBulkConfirm = ref(false)
const pendingBulkAction = ref("")
const pendingBulkRows = ref([])
let loadSequence = 0
let searchTimer = null
let quickFilterTimer = null
const quickFilterDelay = 1000
let restoredNavigationKey = ""
const initialisationGuard = createListInitialisationGuard()

const eligibleFields = computed(() => allowedFields.value.map((field) => ({
	fieldname: field.fieldname,
	fieldtype: field.fieldtype || "Data",
	label: field.label || field.fieldname,
	options: field.options || "",
	precision: field.precision,
	hidden: Boolean(field.hidden),
	doctype: props.doctype,
	link_filters: props.linkFilters[field.fieldname] ?? field.link_filters ?? "",
	inListView: Boolean(field.in_list_view),
	inStandardFilter: Boolean(field.in_standard_filter),
})))

function isFilterableField(field) {
	return Boolean(
		field?.fieldname &&
		!field.is_virtual &&
		!filterExcludedFieldtypes.has(field.fieldtype),
	)
}

function filterField(field, doctype, tableLabel = "") {
	const label = field.label || field.fieldname
	return {
		fieldname: field.fieldname,
		fieldtype: field.fieldtype || "Data",
		label,
		displayLabel: tableLabel ? `${label} (${tableLabel})` : label,
		doctype,
		options: field.options || "",
		precision: field.precision,
		link_filters: tableLabel
			? field.link_filters ?? ""
			: props.linkFilters[field.fieldname] ?? field.link_filters ?? "",
	}
}

function sortFilterFields(fields) {
	return fields.sort((left, right) =>
		String(left.displayLabel || left.label).localeCompare(String(right.displayLabel || right.label)),
	)
}

const standardFilterFields = computed(() => {
	const excluded = new Set(props.excludedFilterFields)
	return eligibleFields.value.filter((field) => field.inStandardFilter && !field.hidden && !excluded.has(field.fieldname))
})

const hasActiveQuery = computed(
	() => Boolean(
		appliedSearch.value ||
		advancedFilters.value.length ||
		activeStatus.value ||
		Object.values(quickFilters.value).some((value) => hasFilterValue(value)),
	),
)
const activeQuickFilterCount = computed(() =>
	standardFilterFields.value.filter((field) => hasFilterValue(quickFilters.value[field.fieldname])).length,
)
const isSubmittable = computed(() => Boolean(Number(doctypeMeta.value?.is_submittable)))
const detectedStatusField = computed(() => {
	if (props.statusField) return props.statusField
	const selectableStatus = ["status", "workflow_state"]
		.map((fieldname) => metaFields.value.find((field) => field.fieldname === fieldname))
		.find((field) => field?.fieldtype === "Select" && selectFieldOptions(field).length)
	if (selectableStatus) return selectableStatus.fieldname
	return isSubmittable.value ? "docstatus" : ""
})
const effectiveStatusField = computed(() => {
	if (!allowedFieldsReady.value) return detectedStatusField.value
	return allowedFields.value.some((field) => field.fieldname === detectedStatusField.value)
		? detectedStatusField.value
		: ""
})
const effectiveStatusOptions = computed(() => {
	if (props.statusOptions.length) return props.statusOptions
	if (effectiveStatusField.value === "docstatus") {
		return [
			{ label: "Draft", value: "0" },
			{ label: "Submitted", value: "1" },
			{ label: "Cancelled", value: "2" },
		]
	}
	const field = metaFields.value.find((candidate) => candidate.fieldname === effectiveStatusField.value)
	return selectFieldOptions(field)
})
const viewFields = computed(() => [
	...new Set([...props.defaultColumns, detectedStatusField.value].filter(Boolean)),
])
const activeFilterCount = computed(() => {
	const statusIsSeparate = Boolean(
		hasFilterValue(activeStatus.value) &&
		!standardFilterFields.value.some((field) => field.fieldname === effectiveStatusField.value),
	)
	return Number(Boolean(appliedSearch.value)) + advancedFilters.value.length + activeQuickFilterCount.value + Number(statusIsSeparate)
})
const isEmptyResult = computed(() =>
	metadataReady.value && !loading.value && !error.value && rows.value.length === 0,
)

const canBulkEdit = computed(() => hasDoctypePermission("write"))
const canBulkSubmit = computed(() => hasDoctypePermission("submit"))
const canBulkCancel = computed(() => hasDoctypePermission("cancel"))
const showBulkSelection = computed(
	() => props.selectable || (props.allowBulkActions
		&& (canBulkEdit.value || (isSubmittable.value && (canBulkSubmit.value || canBulkCancel.value)))),
)
const showBulkBar = computed(() => props.allowBulkActions && showBulkSelection.value && selectedRows.value.length > 0)
const selectedDraftRows = computed(() =>
	selectedRows.value.filter((row) => Number(row.docstatus) === 0),
)
const selectedSubmittedRows = computed(() =>
	selectedRows.value.filter((row) => Number(row.docstatus) === 1),
)
const bulkEditField = computed(
	() => bulkEditFields.value.find((field) => field.key === bulkEditFieldKey.value) || null,
)
const isEmptyBulkValue = computed(
	() => bulkEditValue.value === null || bulkEditValue.value === undefined || bulkEditValue.value === "",
)
const bulkConfirmTitle = computed(() => {
	const count = pendingBulkRows.value.length
	return `${pendingBulkAction.value === "submit" ? "Submit" : "Cancel"} ${count} document${count === 1 ? "" : "s"}`
})
const bulkConfirmMessage = computed(() => {
	const count = pendingBulkRows.value.length
	const action = pendingBulkAction.value === "submit" ? "Submit" : "Cancel"
	const effect = pendingBulkAction.value === "submit"
		? "All normal validations will run."
		: "This can reverse submitted effects."
	return `${action} ${count} selected ${titleForMessage()} document${count === 1 ? "" : "s"}? ${effect}`
})

const columnOptions = computed(() =>
	buildColumnOptions(eligibleFields.value, userColumns.value, props.defaultColumns)
		.map((column) => ({ ...column, label: columnLabel(column) })),
)

const activeColumns = computed(() => [
	{ fieldname: "name", fieldtype: "Data", label: "Name" },
	...columnOptions.value.filter((column) => column.enabled && column.fieldname !== "name"),
])
const mobileColumns = computed(() => {
	const columns = activeColumns.value
	if (columns.length <= 4) return columns
	const primary = columns[0]
	const statusFields = new Set([effectiveStatusField.value, "docstatus", "status", "workflow_state"].filter(Boolean))
	const status = columns.find((column) => statusFields.has(column.fieldname))
	const facts = columns.slice(1).filter((column) => column !== status).slice(0, status ? 2 : 3)
	return [primary, ...facts, ...(status ? [status] : [])].filter(Boolean)
})

const activeCurrencyFields = computed(() =>
	activeCurrencyReferences(activeColumns.value, currencyFields.value),
)

const filterFields = computed(() => {
	const excluded = new Set(props.excludedFilterFields)
	const metaByName = new Map(metaDocuments.value.map((meta) => [meta.name, meta]))
	const parentFields = [
		...frappeStandardFilterFields
			.filter((field) => field.fieldname !== "docstatus" || isSubmittable.value)
			.map((field) => ({
				...field,
				doctype: props.doctype,
				options: field.fieldname === "name" ? props.doctype : field.options || "",
			})),
		...metaFields.value
			.filter(isFilterableField)
			.map((field) => filterField(field, props.doctype)),
	]

	const childFields = metaFields.value
		.filter((field) => ["Table", "Table MultiSelect"].includes(field.fieldtype) && field.options)
		.flatMap((tableField) => {
			const childMeta = metaByName.get(tableField.options)
			if (!childMeta) return []
			let fields = (childMeta.fields || []).filter(isFilterableField)
			if (tableField.fieldtype === "Table MultiSelect") {
				const linkField = fields.find((field) => field.fieldtype === "Link")
				fields = linkField ? [linkField] : []
			}
			return fields.map((field) => filterField(field, childMeta.name, tableField.label || childMeta.name))
		})

	const seen = new Set()
	return [...sortFilterFields(parentFields), ...sortFilterFields(childFields)].filter((field) => {
		if (field.doctype === props.doctype && excluded.has(field.fieldname)) return false
		const key = `${field.doctype}::${field.fieldname}`
		if (seen.has(key)) return false
		seen.add(key)
		return true
	})
})

const fetchFields = computed(() => {
	const allowed = new Set([
		...eligibleFields.value.map((field) => field.fieldname),
		...activeCurrencyFields.value,
	])
	return [...new Set([
		...activeColumns.value.map((column) => column.fieldname),
		...activeCurrencyFields.value,
		...(effectiveStatusField.value ? [effectiveStatusField.value] : []),
		"modified",
		...(isSubmittable.value ? ["docstatus"] : []),
	])].filter((fieldname) => allowed.has(fieldname))
})

const statusTabs = computed(() => {
	if (!effectiveStatusField.value || !effectiveStatusOptions.value.length) return []
	return [
		{ label: "All", value: "", count: statusCounts.value.__all__ ?? total.value },
		...effectiveStatusOptions.value.map((option) => {
			const value = typeof option === "string" ? option : option.value
			const label = typeof option === "string" ? option : option.label
			return { label, value, count: statusCounts.value[value] ?? 0 }
		}),
	]
})

const statusSelectOptions = computed(() => statusTabs.value.map((tab) => ({
	...tab,
	label: `${tab.label} (${tab.count})`,
})))

watch(
	() => [props.doctype, JSON.stringify(props.filters)],
	() => initialise(),
	{ immediate: true },
)

watch(
	() => props.initialAdvancedFilters,
	(filters) => {
		const next = cloneFilters(filters)
		if (JSON.stringify(next) === JSON.stringify(advancedFilters.value)) return
		advancedFilters.value = next
		first.value = 0
		if (metadataReady.value) reload(true)
	},
	{ deep: true },
)

watch(bulkEditFieldKey, () => {
	bulkEditValue.value = defaultBulkValue(bulkEditField.value)
})

watch(selectedRows, (selection) => emit("selection-change", [...selection]))

function baseFilters() {
	if (Array.isArray(props.filters)) return [...props.filters]
	return Object.entries(props.filters || {}).map(([fieldname, value]) => [fieldname, "=", value])
}

function cloneFilters(filters) {
	return Array.isArray(filters)
		? filters.filter(Array.isArray).map((filter) => [...filter])
		: []
}

function hasFilterValue(value) {
	return value !== null && value !== undefined && value !== ""
}

function selectFieldOptions(field) {
	return String(field?.options || "")
		.split("\n")
		.map((option) => option.trim())
		.filter(Boolean)
}

function hasDoctypePermission(action) {
	const user = window.frappe?.boot?.user || {}
	const sessionUser = window.frappe?.session?.user || user.name || user.email
	if (sessionUser === "Administrator") return true
	const allowed = user[`can_${action}`]
	return Array.isArray(allowed) && allowed.includes(props.doctype)
}

function quickFilterTuples({ excludeStatus = false } = {}) {
	return standardFilterFields.value.flatMap((field) => {
		if (excludeStatus && field.fieldname === effectiveStatusField.value) return []
		const value = appliedQuickFilters.value[field.fieldname]
		return hasFilterValue(value) ? [[field.fieldname, "=", value]] : []
	})
}

function allFilters() {
	const filters = [...baseFilters(), ...advancedFilters.value, ...quickFilterTuples()]
	if (
		effectiveStatusField.value &&
		hasFilterValue(activeStatus.value) &&
		!standardFilterFields.value.some((field) => field.fieldname === effectiveStatusField.value)
	) {
		filters.push([effectiveStatusField.value, "=", activeStatus.value])
	}
	if (appliedSearch.value.trim()) {
		filters.push(["name", "like", `%${appliedSearch.value.trim()}%`])
	}
	return filters
}

async function initialise() {
	if (quickFilterTimer) {
		clearTimeout(quickFilterTimer)
		quickFilterTimer = null
	}
	const doctype = props.doctype
	const request = initialisationGuard.begin(doctype)
	const sequence = ++loadSequence
	loading.value = true
	error.value = ""
	metadataReady.value = false
	first.value = 0
	advancedFilters.value = cloneFilters(props.initialAdvancedFilters)
	quickFilters.value = {}
	appliedQuickFilters.value = {}
	activeStatus.value = props.initialStatus
	restoreNavigationState()
	clearSelection()
	bulkNotice.value = ""
	bulkError.value = null
	allowedFields.value = []
	currencyFields.value = {}
	allowedFieldsReady.value = false
	userColumns.value = null
	try {
		const metas = await getMeta(doctype)
		if (!initialisationGuard.isCurrent(request, props.doctype)) return
		const meta = metas.find((row) => row.name === doctype) || metas[0]
		doctypeMeta.value = meta || null
		metaDocuments.value = metas
		metaFields.value = meta?.fields || []
		const listview = await getUserListview(doctype, viewFields.value)
		if (!initialisationGuard.isCurrent(request, props.doctype)) return
		allowedFields.value = Array.isArray(listview?.fields) ? listview.fields : []
		currencyFields.value = listview.currency_fields || {}
		allowedFieldsReady.value = true
		userColumns.value = Array.isArray(listview?.columns) ? listview.columns : null
		metadataReady.value = true
		await Promise.all([loadRows(sequence), loadStatusCounts(sequence)])
	} catch (reason) {
		if (!initialisationGuard.isCurrent(request, props.doctype)) return
		error.value = reason.message || `Unable to load ${doctype}.`
		metaDocuments.value = []
		allowedFields.value = []
		currencyFields.value = {}
		allowedFieldsReady.value = false
		rows.value = []
		total.value = 0
	} finally {
		if (sequence === loadSequence) loading.value = false
	}
}

async function loadStatusCounts(existingSequence = loadSequence) {
	if (!effectiveStatusField.value || !effectiveStatusOptions.value.length) {
		statusCounts.value = {}
		return
	}
	const filters = [
		...baseFilters(),
		...advancedFilters.value,
		...quickFilterTuples({ excludeStatus: true }),
	]
	if (appliedSearch.value.trim()) filters.push(["name", "like", `%${appliedSearch.value.trim()}%`])
	try {
		const values = effectiveStatusOptions.value.map((option) =>
			typeof option === "string" ? option : option.value,
		)
		const counts = await Promise.all([
			getCount(props.doctype, filters),
			...values.map((value) =>
				getCount(props.doctype, [...filters, [effectiveStatusField.value, "=", value]]),
			),
		])
		if (existingSequence !== loadSequence) return
		statusCounts.value = Object.fromEntries([
			["__all__", counts[0]],
			...values.map((value, index) => [value, counts[index + 1]]),
		])
	} catch {
		if (existingSequence === loadSequence) statusCounts.value = { __all__: total.value }
	}
}

async function loadRows(existingSequence = null) {
	const sequence = existingSequence || ++loadSequence
	loading.value = true
	error.value = ""
	try {
		const filters = allFilters()
		const orderBy = deterministicOrder(sortField.value, sortOrder.value === 1 ? "asc" : "desc")
		const [data, count] = await Promise.all([
			getList(props.doctype, {
				fields: fetchFields.value,
				filters,
				orderBy,
				start: first.value,
				pageLength: pageSize.value,
			}),
			getCount(props.doctype, filters),
		])
		if (sequence !== loadSequence) return
		rows.value = data
		total.value = count
		clearSelection()
		emit("loaded", { rows: data, total: count })
	} catch (reason) {
		if (sequence !== loadSequence) return
		error.value = reason.message || `Unable to load ${props.doctype}.`
		rows.value = []
		total.value = 0
	} finally {
		if (sequence === loadSequence) loading.value = false
	}
}

function reload(includeCounts = false) {
	if (!metadataReady.value) return Promise.resolve([])
	const sequence = ++loadSequence
	const tasks = [loadRows(sequence)]
	if (includeCounts) tasks.push(loadStatusCounts(sequence))
	return Promise.all(tasks)
}

function applySearch() {
	if (searchTimer) {
		clearTimeout(searchTimer)
		searchTimer = null
	}
	if (appliedSearch.value === search.value.trim()) return
	appliedSearch.value = search.value.trim()
	first.value = 0
	reload(true)
}

function filtersApplied(filters) {
	advancedFilters.value = cloneFilters(filters)
	emit("update:advancedFilters", cloneFilters(advancedFilters.value))
	first.value = 0
	reload(true)
}

async function columnsSaved() {
	const doctype = props.doctype
	const request = initialisationGuard.snapshot(doctype)
	try {
		const listview = await getUserListview(doctype, viewFields.value)
		if (!initialisationGuard.isCurrent(request, props.doctype)) return
		allowedFields.value = listview.fields
		currencyFields.value = listview.currency_fields || {}
		allowedFieldsReady.value = true
		userColumns.value = listview.columns
		first.value = 0
		await reload()
	} catch (reason) {
		if (!initialisationGuard.isCurrent(request, props.doctype)) return
		error.value = reason.message || `Unable to load ${doctype}.`
	}
}

function pageChanged(event) {
	first.value = event.first
	pageSize.value = event.rows
	reload()
}

function sortChanged(event) {
	sortField.value = event.sortField || "modified"
	sortOrder.value = event.sortOrder || -1
	first.value = 0
	reload()
}

function selectStatus(value) {
	if (!metadataReady.value) return
	if (activeStatus.value === value) return
	activeStatus.value = value
	const values = { ...quickFilters.value }
	if (hasFilterValue(value)) values[effectiveStatusField.value] = value
	else delete values[effectiveStatusField.value]
	quickFilters.value = values
	const appliedValues = { ...appliedQuickFilters.value }
	if (hasFilterValue(value)) appliedValues[effectiveStatusField.value] = value
	else delete appliedValues[effectiveStatusField.value]
	appliedQuickFilters.value = appliedValues
	first.value = 0
	reload()
}

function openColumnsDialog() {
	if (!allowedFieldsReady.value) return
	showColumns.value = true
}

function quickFiltersChanged({ values, field }) {
	quickFilters.value = values
	if (!field || field.fieldname === effectiveStatusField.value) {
		activeStatus.value = hasFilterValue(values[effectiveStatusField.value])
			? values[effectiveStatusField.value]
			: ""
	}
	first.value = 0

	if (quickFilterTimer) clearTimeout(quickFilterTimer)
	quickFilterTimer = setTimeout(() => {
		quickFilterTimer = null
		appliedQuickFilters.value = { ...quickFilters.value }
		reload(true)
	}, quickFilterDelay)
}

function refresh() {
	return reload(true)
}

function retryLoad() {
	return metadataReady.value ? refresh() : initialise()
}

function clearFilters() {
	if (quickFilterTimer) {
		clearTimeout(quickFilterTimer)
		quickFilterTimer = null
	}
	search.value = ""
	appliedSearch.value = ""
	advancedFilters.value = []
	emit("update:advancedFilters", [])
	quickFilters.value = {}
	appliedQuickFilters.value = {}
	activeStatus.value = ""
	first.value = 0
	reload(true)
}

function clearSelection() {
	selectedRows.value = []
}

function isRowSelected(row) {
	return selectedRows.value.some((selected) => selected.name === row.name)
}

function toggleMobileSelection(row, event) {
	if (event.target.checked) selectedRows.value = [...selectedRows.value.filter((selected) => selected.name !== row.name), row]
	else selectedRows.value = selectedRows.value.filter((selected) => selected.name !== row.name)
}

function titleForMessage() {
	return props.title || props.doctype
}

function defaultBulkValue(field) {
	if (!field) return ""
	if (field.fieldtype === "Check") return 0
	if (field.fieldtype === "Select" && /status/i.test(field.fieldname || field.label || "")) {
		return String(field.options || "")
			.split("\n")
			.map((option) => option.trim())
			.filter(Boolean)[0] || ""
	}
	return ""
}

function bulkFailureLines(failures) {
	const lines = failures.slice(0, 8).map((failure) => {
		const message = failure.message || failure.error?.message || "Failed"
		return `${failure.name}: ${message}`
	})
	if (failures.length > 8) lines.push(`${failures.length - 8} more failed`)
	return lines
}

async function loadBulkFields() {
	if (bulkEditFieldsFor.value === props.doctype && bulkEditFields.value.length) {
		return bulkEditFields.value
	}
	bulkEditLoading.value = true
	try {
		const fields = await getBulkEditFields(props.doctype)
		bulkEditFields.value = Array.isArray(fields) ? fields : []
		bulkEditFieldsFor.value = props.doctype
		const preferred = bulkEditFields.value.find((field) =>
			/status/i.test(field.fieldname || field.label || ""),
		)
		bulkEditFieldKey.value = (preferred || bulkEditFields.value[0])?.key || ""
		return bulkEditFields.value
	} catch (reason) {
		bulkError.value = {
			title: "Could not load editable fields",
			lines: [reason.message || "Failed"],
		}
		return []
	} finally {
		bulkEditLoading.value = false
	}
}

async function openBulkEditDialog() {
	if (!selectedRows.value.length) return
	bulkError.value = null
	bulkNotice.value = ""
	showBulkEdit.value = true
	const fields = await loadBulkFields()
	if (!fields.length) {
		showBulkEdit.value = false
		bulkError.value = {
			title: "No editable fields",
			lines: ["No writable fields are available for your permissions."],
		}
	}
}

async function refreshAfterBulk() {
	clearSelection()
	await reload(true)
}

async function applyBulkEdit() {
	const field = bulkEditField.value
	const names = selectedRows.value.map((row) => row.name).filter(Boolean)
	if (!field || !names.length) return
	bulkActing.value = "edit"
	bulkEditApplying.value = true
	bulkError.value = null
	bulkNotice.value = ""
	try {
		const result = await bulkUpdateField(props.doctype, names, field, bulkEditValue.value)
		const updated = Array.isArray(result?.updated) ? result.updated : []
		const failures = Array.isArray(result?.failures) ? result.failures : []
		showBulkEdit.value = false
		await refreshAfterBulk()
		if (failures.length) {
			bulkError.value = {
				title: updated.length ? "Bulk edit partially completed" : "Bulk edit failed",
				lines: bulkFailureLines(failures),
			}
		} else {
			bulkNotice.value = `${updated.length} record${updated.length === 1 ? "" : "s"} updated.`
		}
	} catch (reason) {
		bulkError.value = { title: "Bulk edit failed", lines: [reason.message || "Failed"] }
	} finally {
		bulkActing.value = ""
		bulkEditApplying.value = false
	}
}

function requestBulkAction(action) {
	const candidates = action === "submit" ? selectedDraftRows.value : selectedSubmittedRows.value
	if (!candidates.length) return
	pendingBulkAction.value = action
	pendingBulkRows.value = [...candidates]
	showBulkConfirm.value = true
}

async function confirmBulkAction() {
	const action = pendingBulkAction.value
	const candidates = [...pendingBulkRows.value]
	showBulkConfirm.value = false
	await runBulkAction(action, candidates)
}

async function runBulkAction(action, candidates) {
	if (!candidates.length) return
	bulkActing.value = action
	bulkError.value = null
	bulkNotice.value = ""
	let completed = 0
	const failures = []
	try {
		for (const row of candidates) {
			try {
				if (action === "submit") await submitDoc(props.doctype, row.name, row.modified)
				else await cancelDoc(props.doctype, row.name, row.modified)
				completed += 1
			} catch (reason) {
				failures.push({ name: row.name, message: reason.message || "Failed" })
			}
		}
		await refreshAfterBulk()
		if (failures.length) {
			bulkError.value = {
				title: completed
					? `Bulk ${action} partially completed`
					: `Bulk ${action} failed`,
				lines: bulkFailureLines(failures),
			}
		} else {
			const result = action === "submit" ? "submitted" : "cancelled"
			bulkNotice.value = `${completed} document${completed === 1 ? "" : "s"} ${result}.`
		}
	} finally {
		bulkActing.value = ""
		pendingBulkAction.value = ""
		pendingBulkRows.value = []
	}
}

function rowClicked(event) {
	const target = event?.originalEvent?.target
	if (target?.closest?.(".p-checkbox, .p-selection-column, button, a, input, textarea, select")) return
	if (props.clickable) emit("row-click", event.data, navigationSnapshot(event.data))
}

function openRow(row) {
	if (props.clickable) emit("row-click", row, navigationSnapshot(row))
}

function navigationSnapshot(row) {
	if (!props.navigationEnabled || !route.name) return null
	const rowIndex = rows.value.findIndex((candidate) => candidate === row || candidate?.name === row?.name)
	if (rowIndex < 0) return null
	const direction = sortOrder.value === 1 ? "asc" : "desc"
	return createListNavigationState({
		sourceRouteName: String(route.name),
		sourceFullPath: route.fullPath,
		doctype: props.doctype,
		filters: allFilters(),
		baseFilters: baseFilters(),
		advancedFilters: advancedFilters.value,
		quickFilters: appliedQuickFilters.value,
		status: activeStatus.value,
		search: appliedSearch.value,
		sortField: sortField.value,
		sortOrder: direction,
		orderBy: deterministicOrder(sortField.value, direction),
		pageStart: first.value,
		pageSize: pageSize.value,
		globalIndex: first.value + rowIndex,
		total: total.value,
	})
}

function restoreNavigationState() {
	if (!props.navigationEnabled || !route.name || typeof window === "undefined") return
	const key = navigationStorageKey(String(route.name), props.doctype)
	if (restoredNavigationKey === key) return
	const state = readNavigationState(window.sessionStorage, key)
	if (!state || state.sourceRouteName !== String(route.name) || state.doctype !== props.doctype) return
	restoredNavigationKey = key
	search.value = state.search
	appliedSearch.value = state.search
	advancedFilters.value = state.advancedFilters
	quickFilters.value = { ...state.quickFilters }
	appliedQuickFilters.value = { ...state.quickFilters }
	activeStatus.value = state.status
	first.value = state.pageStart
	pageSize.value = state.pageSize
	sortField.value = state.sortField
	sortOrder.value = state.sortOrder === "asc" ? 1 : -1
}

function rowClass(row) {
	const classes = ["premium-list-row"]
	if (props.clickable) classes.push("premium-list-row--clickable")
	if (effectiveStatusField.value && hasFilterValue(row?.[effectiveStatusField.value])) {
		const value = row[effectiveStatusField.value]
		const option = effectiveStatusOptions.value.find((candidate) => String(typeof candidate === "string" ? candidate : candidate.value) === String(value))
		const label = typeof option === "string" ? option : option?.label
		classes.push(`premium-list-row--${statusTone(label || value)}`)
	}
	return classes.join(" ")
}

function isStatusColumn(column) {
	return [effectiveStatusField.value, "docstatus", "status", "workflow_state"]
		.filter(Boolean)
		.includes(column?.fieldname)
}

function isImageColumn(column) {
	return ["Attach Image", "Signature"].includes(column?.fieldtype)
}

function statusTone(status) {
	const value = String(status || "").toLowerCase()
	if (["completed", "fully", "closed"].some((token) => value.includes(token)) && !value.includes("partially")) return "success"
	if (value.includes("pending") || value.includes("cancel") || value.includes("reject") || value.includes("overdue")) return "danger"
	if (value.includes("partial") || value.includes("draft") || value.startsWith("to ") || value.includes("close request")) return "warning"
	if (value.includes("submitted") || value.includes("progress") || value.includes("ready") || value.includes("planned")) return "info"
	return "neutral"
}

function displayValue(value, column, row = {}) {
	if (value === null || value === undefined || value === "") return "—"
	if (column.fieldtype === "Check") return Number(value) ? "Yes" : "No"
	if (Array.isArray(value)) return value.join(", ")
	if (["Date", "Datetime"].includes(column.fieldtype)) {
		const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/)
		if (match) {
			const date = `${match[3]}-${match[2]}-${match[1]}`
			return column.fieldtype === "Datetime" && match[4] ? `${date} · ${match[4]}:${match[5]}` : date
		}
	}
	if (column.fieldtype === "Currency") {
		const reference = currencyReferenceField(column, currencyFields.value)
		const currency = reference ? row?.[reference] : ""
		const amount = Number(value).toLocaleString("en-IN", { maximumFractionDigits: 2 })
		return currency ? `${currency} ${amount}` : amount
	}
	if (["Int", "Float"].includes(column.fieldtype) && Number.isFinite(Number(value))) {
		return Number(value).toLocaleString("en-IN", { maximumFractionDigits: column.fieldtype === "Int" ? 0 : 3 })
	}
	if (column.fieldtype === "Percent" && Number.isFinite(Number(value))) return `${Number(value).toLocaleString("en-IN", { maximumFractionDigits: 2 })}%`
	return value
}

function columnLabel(column) {
	if (column.fieldname === "name") return props.nameColumnLabel
	return props.columnLabels[column.fieldname] || column.label
}

function isNumericColumn(column) {
	return ["Int", "Float", "Currency", "Percent"].includes(column?.fieldtype)
}

watch(search, () => {
	if (searchTimer) clearTimeout(searchTimer)
	searchTimer = setTimeout(() => {
		searchTimer = null
		applySearch()
	}, 300)
})

onBeforeUnmount(() => {
	if (searchTimer) clearTimeout(searchTimer)
	if (quickFilterTimer) clearTimeout(quickFilterTimer)
})

defineExpose({ refresh: reload })
</script>

<style scoped>
.common-list-view {
	--list-accent: var(--erp-accent);
	--list-accent-dark: var(--erp-accent-hover);
	--list-accent-soft: color-mix(in srgb, var(--list-accent) 9%, white);
	--list-ink: var(--erp-text);
	--list-muted: var(--erp-text-muted);
	--list-line: var(--erp-border);
	--list-surface: var(--erp-surface);

	display: grid;
	gap: 12px;
	width: 100%;
	padding: 10px;
	background: transparent;
	border: 0;
	border-radius: 0;
	box-shadow: none;
}

.common-list-view--viewport-bounded {
	display: flex;
	height: calc(100dvh - var(--erp-shell-header-height) - 94px);
	min-height: 0;
	overflow: hidden;
	flex-direction: column;
}

.common-list-view--viewport-bounded > :not(.list-table-frame) {
	flex: 0 0 auto;
}

.common-list-view--viewport-bounded .list-table-frame {
	min-height: 0;
	flex: 1 1 auto;
}

.common-list-view--viewport-bounded :deep(.premium-list-table) {
	display: flex;
	height: 100%;
	min-height: 0;
	flex-direction: column;
}

.common-list-view--viewport-bounded :deep(.premium-list-table .p-datatable-table-container) {
	min-height: 0;
	overflow: auto;
	flex: 1 1 auto;
}

@media (min-width: 1025px) {
	.common-list-view--viewport-bounded.common-list-view--empty {
		height: auto;
		overflow: visible;
	}

	.common-list-view--viewport-bounded.common-list-view--empty .list-table-frame {
		height: 252px;
		min-height: 252px;
		flex: none;
	}
}

.list-page-head {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 16px;
	padding: 0;
}

.list-title-block {
	display: grid;
	gap: 2px;
	min-width: 160px;
}

.list-title-line {
	display: flex;
	min-width: 0;
	align-items: center;
	gap: 10px;
}

.list-title-line > div { min-width: 0; }

.list-title-block::before { content: none; }

.list-eyebrow {
	color: var(--list-accent-dark);
	font-size: var(--erp-font-size-min);
	font-weight: 800;
	letter-spacing: 0.13em;
	text-transform: uppercase;
}

.list-title-block h1 {
	margin: 0;
	color: var(--list-ink);
	font-size: 1.45rem;
	font-weight: 740;
	letter-spacing: -0.025em;
	line-height: var(--erp-line-height-tight);
}

.list-title-block p {
	margin: 3px 0 0;
	color: var(--list-muted);
	font-size: 0.86rem;
}

.list-toolbar__actions {
	display: flex;
	align-items: center;
	gap: 6px;
	flex-wrap: wrap;
	justify-content: flex-end;
	padding: 0;
}

.list-toolbar__primary,
.list-toolbar__secondary {
	display: contents;
}

.mobile-quick-filter-toggle {
	display: none;
}

.list-search {
	position: relative;
	display: flex;
	align-items: center;
	min-width: 0;
}

.list-search > i {
	position: absolute;
	left: 11px;
	z-index: 1;
	color: color-mix(in srgb, var(--list-accent) 55%, var(--erp-text-muted));
	transition: color var(--erp-transition-fast);
}

.list-search :deep(input) {
	width: min(278px, 27vw);
	height: var(--erp-control-height);
	padding-left: 34px;
	background: var(--list-surface);
	border-color: var(--list-line);
	border-radius: var(--erp-control-radius);
	box-shadow: none;
	transition:
		border-color 160ms ease,
		box-shadow 160ms ease;
}

.list-search:focus-within > i {
	color: var(--list-accent-dark);
}

.list-search :deep(input:focus) {
	border-color: color-mix(in srgb, var(--list-accent) 50%, white);
	box-shadow: 0 0 0 3px color-mix(in srgb, var(--list-accent) 12%, transparent);
}

.list-toolbar__actions :deep(.p-button) {
	height: var(--erp-control-height);
	min-height: var(--erp-control-height);
	background: var(--erp-surface);
	border-color: var(--list-line);
	border-radius: var(--erp-control-radius);
	font-weight: 650;
	box-shadow: none;
	transition:
		transform 150ms ease,
		border-color 150ms ease,
		box-shadow 150ms ease,
		background 150ms ease;
}

.list-toolbar__actions :deep(.p-button:not(:disabled):hover) {
	background: var(--list-accent-soft);
	border-color: color-mix(in srgb, var(--list-accent) 34%, white);
	box-shadow: var(--erp-shadow-xs);
}

.list-toolbar__actions :deep(.p-button.list-filter-action--active) {
	color: var(--list-accent-dark);
	background: var(--list-accent-soft);
	border-color: color-mix(in srgb, var(--list-accent) 38%, white);
}

.list-toolbar__actions :deep(.p-button.list-clear-filter-action--active) {
	color: var(--erp-danger);
	background: var(--erp-danger-soft);
	border-color: color-mix(in srgb, var(--erp-danger) 28%, white);
}

.list-toolbar__actions :deep(.p-button.list-primary-action),
.list-toolbar__primary :deep(.p-button) {
	color: #fff;
	background: var(--list-accent);
	border-color: var(--list-accent);
	box-shadow: none;
}

.list-toolbar__actions :deep(.p-button.list-primary-action:not(:disabled):hover),
.list-toolbar__primary :deep(.p-button:not(:disabled):hover) {
	color: #fff;
	background: var(--list-accent-dark);
	border-color: var(--list-accent-dark);
	box-shadow: var(--erp-shadow-xs);
}

.bulk-message {
	display: grid;
	gap: 4px;
}

.list-load-error {
	display: grid;
	grid-template-columns: auto minmax(0, 1fr) auto;
	align-items: center;
	gap: 12px;
	padding: 11px 12px;
	color: var(--erp-text-secondary);
	background: var(--erp-danger-soft);
	border: 1px solid color-mix(in srgb, var(--erp-danger) 24%, white);
	border-radius: var(--erp-control-radius);
}

.list-load-error__icon {
	display: grid;
	width: 34px;
	height: 34px;
	color: var(--erp-danger);
	background: var(--erp-surface);
	border-radius: 50%;
	place-items: center;
}

.list-load-error > div { display: grid; gap: 2px; min-width: 0; }
.list-load-error strong { color: var(--erp-text); font-size: var(--erp-font-size-table); }
.list-load-error > div > span { overflow-wrap: anywhere; font-size: var(--erp-font-size-caption); }

.bulk-message span {
	font-size: 0.78rem;
}

.bulk-bar {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 12px;
	padding: 11px 14px;
	background: var(--list-accent-soft);
	border: 1px solid color-mix(in srgb, var(--list-accent) 25%, white);
	border-radius: var(--erp-control-radius);
}

.bulk-bar__summary,
.bulk-bar__actions {
	display: flex;
	align-items: center;
	gap: 8px;
	flex-wrap: wrap;
}

.bulk-bar__summary strong {
	color: var(--list-accent-dark);
	font-size: 0.8rem;
}

.bulk-bar__summary span {
	padding: 3px 7px;
	color: var(--list-muted);
	font-size: var(--erp-font-size-min);
	font-weight: 700;
	background: var(--erp-surface);
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-pill-radius);
}

.bulk-edit-form {
	display: grid;
	gap: 16px;
}

.bulk-edit-selection {
	width: fit-content;
	padding: 5px 9px;
	color: var(--list-accent-dark);
	font-size: 0.74rem;
	font-weight: 750;
	background: var(--list-accent-soft);
	border-radius: 999px;
}

.bulk-edit-field {
	display: grid;
	gap: 6px;
	color: var(--erp-text-secondary);
	font-size: 0.8rem;
	font-weight: 650;
}

.bulk-edit-help {
	margin-top: -8px;
	color: var(--list-muted);
	font-size: 0.72rem;
}

.bulk-confirm-copy {
	margin: 0;
	color: var(--erp-text-secondary);
	font-size: 0.88rem;
	line-height: 1.55;
}

.list-status-tabs {
	display: flex;
	align-items: center;
	gap: 5px;
	overflow-x: auto;
	padding: 6px;
	background: var(--erp-surface-soft);
	border: 1px solid var(--list-line);
	border-radius: var(--erp-control-radius);
	-webkit-mask-image: linear-gradient(to right, transparent, #000 12px, #000 calc(100% - 12px), transparent);
	mask-image: linear-gradient(to right, transparent, #000 12px, #000 calc(100% - 12px), transparent);
	scrollbar-width: none;
	flex-shrink: 0;
}

.list-status-tabs::-webkit-scrollbar {
	display: none;
}

.list-status-tabs:focus-visible {
	outline: 2px solid color-mix(in srgb, var(--erp-accent) 34%, transparent);
	outline-offset: 2px;
}

.list-status-select {
	display: none;
	width: min(100%, 320px);
	gap: 5px;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	font-weight: 700;
	letter-spacing: .04em;
	text-transform: uppercase;
}

.list-status-tab {
	display: inline-flex;
	align-items: center;
	gap: 7px;
	min-height: 37px;
	padding: 7px 12px;
	white-space: nowrap;
	color: var(--list-muted);
	font: inherit;
	font-size: 0.75rem;
	font-weight: 660;
	background: transparent;
	border: 1px solid transparent;
	border-radius: 7px;
	cursor: pointer;
	transition:
		color 150ms ease,
		background 150ms ease,
		border-color 150ms ease,
		box-shadow 150ms ease,
		transform 150ms ease;
}

.list-status-tab:hover {
	color: var(--list-ink);
	background: var(--erp-surface);
	border-color: var(--erp-border);
	box-shadow: var(--erp-shadow-sm);
}

.list-status-tab:focus-visible {
	color: var(--list-accent-dark);
	outline: 2px solid var(--erp-accent-dark);
	outline-offset: 1px;
}

.list-status-tab:active {
	transform: translateY(0);
}

.list-status-tab--active {
	color: var(--list-accent-dark);
	background: var(--erp-surface);
	border-color: color-mix(in srgb, var(--list-accent) 34%, white);
	box-shadow: 0 2px 8px color-mix(in srgb, var(--list-accent) 8%, transparent);
}

.list-status-tab__dot {
	width: 7px;
	height: 7px;
	background: var(--erp-text-muted);
	border-radius: 50%;
}

.list-status-tab__dot.success {
	background: var(--erp-success);
}

.list-status-tab__dot.danger {
	background: var(--erp-danger);
}

.list-status-tab__dot.warning {
	background: var(--erp-attention);
}

.list-status-tab__dot.info {
	background: var(--erp-info);
}

.list-status-tab__count {
	min-width: 22px;
	padding: 1px 6px;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	font-weight: 750;
	text-align: center;
	background: var(--erp-surface-muted);
	border-radius: var(--erp-pill-radius);
}

.list-status-tab--active .list-status-tab__count {
	color: var(--list-accent-dark);
	background: var(--erp-surface);
}

.list-table-frame {
	position: relative;
	overflow: hidden;
	background: var(--list-surface);
	border: 1px solid var(--list-line);
	border-radius: var(--erp-panel-radius);
	box-shadow: inset 0 1px 0 rgb(255 255 255 / 72%);
}

@media (max-width: 900px) {
	.list-table-frame::after {
		position: absolute;
		z-index: calc(var(--erp-layer-sticky) + 1);
		top: 0;
		right: 0;
		bottom: 0;
		width: 15px;
		background: linear-gradient(to right, transparent, rgb(16 24 40 / 8%));
		content: "";
		pointer-events: none;
	}
}

.list-loading {
	display: grid;
	gap: 1px;
	padding: 1px;
	background: var(--erp-border);
}

.list-loading-skeleton {
	border-radius: 0;
}

.mobile-list-records,
.mobile-list-empty {
	display: none;
}

:deep(.premium-list-table .p-datatable-table) {
	border-collapse: separate;
	border-spacing: 0;
}

:deep(.premium-list-table .p-datatable-thead > tr > th) {
	position: sticky;
	top: 0;
	z-index: var(--erp-layer-sticky);
	padding: var(--erp-table-cell-pad-y) var(--erp-table-cell-pad-x);
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	font-weight: 820;
	letter-spacing: 0.075em;
	text-transform: uppercase;
	background: var(--erp-surface-muted);
	border: 0;
	border-bottom: 1px solid var(--erp-border);
}

:deep(.premium-list-table .p-datatable-tbody > tr) {
	background: var(--erp-surface);
	transition:
		background 140ms ease,
		box-shadow 140ms ease;
}

:deep(.premium-list-table .p-datatable-tbody > tr > td) {
	padding: var(--erp-table-cell-pad-y) var(--erp-table-cell-pad-x);
	color: var(--erp-text-secondary);
	font-size: 13px;
	border: 0;
	border-bottom: 1px solid var(--erp-border-subtle);
}

:deep(.premium-list-table .p-datatable-tbody > tr:last-child > td) {
	border-bottom: 0;
}

:deep(.premium-list-table .p-datatable-tbody > tr:hover) {
	background: color-mix(in srgb, var(--list-accent) 4%, white);
	box-shadow: inset 0 1px color-mix(in srgb, var(--list-accent) 8%, transparent), inset 0 -1px color-mix(in srgb, var(--list-accent) 8%, transparent);
}

:deep(.premium-list-table .p-datatable-tbody > tr.p-datatable-empty-message),
:deep(.premium-list-table .p-datatable-tbody > tr.p-datatable-empty-message:hover) {
	background: var(--erp-surface);
	box-shadow: none;
}

:deep(.premium-list-table .p-datatable-tbody > tr.p-datatable-row-selected) {
	background: color-mix(in srgb, var(--list-accent) 9%, white);
}

:deep(.premium-list-row--success > td:first-child) {
	box-shadow: inset 4px 0 var(--erp-success);
}

:deep(.premium-list-row--danger > td:first-child) {
	box-shadow: inset 4px 0 var(--erp-danger);
}

:deep(.premium-list-row--warning > td:first-child) {
	box-shadow: inset 4px 0 var(--erp-attention);
}

:deep(.premium-list-row--info > td:first-child) {
	box-shadow: inset 4px 0 var(--erp-info);
}

.list-document-cell {
	display: flex;
	align-items: center;
}

.list-document-cell strong {
	display: block;
	overflow: hidden;
	max-width: min(26vw, 280px);
	color: var(--list-ink);
	font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
	font-size: 13px;
	font-weight: 740;
	text-overflow: ellipsis;
	white-space: nowrap;
}

.list-link-value,
.list-plain-value {
	display: block;
	overflow: hidden;
	max-width: min(30vw, 340px);
	text-overflow: ellipsis;
	white-space: nowrap;
}

.list-link-value {
	color: var(--erp-text-secondary);
	font-weight: 680;
}

.list-link-value--lot {
	color: var(--list-accent-dark);
}

:deep(.premium-list-table .p-datatable-tbody > tr:hover) .list-link-value {
	color: var(--list-accent-dark);
}

.list-plain-value {
	color: var(--erp-text-secondary);
}

.list-image-value {
	display: block;
	width: 48px;
	height: 36px;
	object-fit: contain;
	background: var(--erp-surface-muted);
	border: 1px solid var(--list-line);
	border-radius: 4px;
}

:deep(.list-number-column) {
	font-variant-numeric: tabular-nums;
	text-align: right !important;
}

.list-chevron-column {
	width: 44px;
}

.list-row-open {
	display: grid;
	width: 36px;
	height: 36px;
	padding: 0;
	color: var(--erp-text-muted);
	background: transparent;
	border: 1px solid transparent;
	border-radius: var(--erp-control-radius);
	cursor: pointer;
	place-items: center;
	transition: 140ms ease;
}

:deep(.premium-list-table .p-checkbox) {
	display: grid;
	width: 36px;
	height: 36px;
	place-items: center;
}

:deep(.premium-list-table .p-checkbox-box) {
	width: 20px;
	height: 20px;
}

.list-row-open:hover {
	color: var(--list-accent-dark);
	background: var(--list-accent-soft);
	border-color: color-mix(in srgb, var(--list-accent) 22%, white);
}

.list-row-open:focus-visible {
	color: var(--list-accent-dark);
	background: var(--erp-surface);
	border-color: var(--list-accent);
	outline: 3px solid color-mix(in srgb, var(--list-accent) 16%, transparent);
	outline-offset: 1px;
}

.list-row-open:active {
	transform: translateY(1px);
}

.list-row-chevron {
	color: var(--erp-text-muted);
	font-size: 0.72rem;
	transition: 130ms ease;
}

:deep(.premium-list-row--clickable) {
	cursor: pointer;
}

:deep(.premium-list-row--clickable:hover) .list-row-chevron {
	color: var(--list-accent);
}

@media (hover: hover) {
	.list-status-tab:hover { transform: translateY(-1px); }
	:deep(.premium-list-row--clickable:hover) .list-row-chevron { transform: translateX(2px); }
}

:deep(.premium-list-row--clickable:has(.list-row-open:focus-visible)) {
	background: color-mix(in srgb, var(--list-accent) 6%, white);
	box-shadow: inset 3px 0 var(--list-accent);
}

:deep(.premium-list-table .p-datatable-table-container) {
	container-type: inline-size;
}

.list-empty {
	position: sticky;
	left: 0;
	display: flex;
	align-items: center;
	flex-direction: column;
	gap: 6px;
	box-sizing: border-box;
	width: 100cqi;
	padding: 58px 16px;
	color: var(--list-muted);
	text-align: center;
}

.list-empty__icon {
	display: grid;
	width: 46px;
	height: 46px;
	margin-bottom: 4px;
	color: var(--list-accent-dark);
	font-size: 1.2rem;
	background: var(--list-accent-soft);
	border-radius: 13px;
	place-items: center;
}

.list-empty strong {
	color: var(--list-ink);
	font-size: 0.9rem;
}

.list-empty > span:last-child {
	font-size: 0.78rem;
}

:deep(.p-paginator) {
	width: fit-content;
	max-width: 100%;
	margin: 0 auto;
	padding: 6px;
	background: var(--erp-surface);
	border: 1px solid var(--list-line);
	border-radius: var(--erp-control-radius);
}

:deep(.p-paginator-page),
:deep(.p-paginator-next),
:deep(.p-paginator-prev),
:deep(.p-paginator-first),
:deep(.p-paginator-last) {
	min-width: 34px;
	height: 34px;
	border-radius: 9px;
}

:deep(.premium-list-table .p-tag) {
	padding: 0.3rem 0.62rem;
	font-size: 0.76rem;
	font-weight: 760;
	letter-spacing: 0.005em;
	border: 1px solid rgb(255 255 255 / 64%);
	box-shadow: inset 0 -1px rgb(15 23 42 / 4%);
}

:deep(.premium-list-table .p-checkbox-box) {
	border-color: var(--erp-border-strong);
	border-radius: 6px;
	box-shadow: var(--erp-shadow-xs);
}

:deep(.premium-list-table .p-checkbox-checked .p-checkbox-box) {
	background: var(--list-accent);
	border-color: var(--list-accent);
}

@media (max-width: 1180px) {
	.list-page-head {
		align-items: stretch;
		flex-direction: column;
		gap: 14px;
	}

	.list-toolbar__actions {
		flex-wrap: nowrap;
		width: 100%;
	}

	.list-search {
		flex: 1;
	}

	.list-search :deep(input) {
		width: 100%;
	}
}

@media (max-width: 1024px) {
	.common-list-view {
		padding: 8px;
	}

	.common-list-view--viewport-bounded {
		height: auto;
		min-height: calc(100dvh - var(--erp-shell-header-height) - 76px);
		overflow: visible;
	}

	.common-list-view--viewport-bounded .list-table-frame,
	.common-list-view--viewport-bounded.common-list-view--filters-open .list-table-frame {
		min-height: 0;
		flex: none;
	}

	.common-list-view--viewport-bounded :deep(.premium-list-table) {
		height: auto;
	}

	.common-list-view--viewport-bounded :deep(.premium-list-table .p-datatable-table-container) {
		overflow-x: auto;
		overflow-y: visible;
	}

	.list-table-frame {
		overflow: visible;
	}

	.list-status-tabs {
		display: none;
	}

	.list-status-select {
		display: grid;
		width: 100%;
	}

	.list-table-frame::after {
		display: none;
	}

	.common-list-view--viewport-bounded :deep(.premium-list-table),
	:global(.premium-list-table) {
		display: none;
	}

	.mobile-list-records,
	.mobile-list-empty {
		display: grid;
	}

	.mobile-list-record {
		display: grid;
		gap: 10px;
		min-width: 0;
		padding: 12px;
		background: var(--erp-surface);
		border-bottom: 1px solid var(--erp-border-subtle);
	}

	.list-load-error {
		grid-template-columns: auto minmax(0, 1fr);
	}

	.list-load-error :deep(.p-button) {
		grid-column: 1 / -1;
		width: 100%;
		min-height: 44px;
	}

	.mobile-list-record:last-child {
		border-bottom: 0;
	}

	.mobile-list-record > header {
		display: grid;
		grid-template-columns: auto minmax(0, 1fr) auto;
		align-items: center;
		gap: 10px;
	}

	.mobile-list-record__header--without-selection {
		grid-template-columns: minmax(0, 1fr) auto !important;
	}

	.mobile-list-record__open {
		display: inline-grid;
		width: 44px;
		height: 44px;
		padding: 0;
		border: 0;
		border-radius: var(--erp-control-radius);
		background: transparent;
		color: var(--erp-text-muted);
		font-size: 12px;
		cursor: pointer;
		place-items: center;
	}

	.mobile-list-record__open:hover {
		background: var(--erp-surface-hover);
		color: var(--erp-accent-dark);
	}

	.mobile-list-record__select {
		display: grid;
		width: 44px;
		height: 44px;
		cursor: pointer;
		place-items: center;
	}

	.mobile-list-record__select input {
		width: 18px;
		height: 18px;
		accent-color: var(--erp-accent);
	}

	.mobile-list-record__identity,
	.mobile-list-record__facts > div {
		display: grid;
		min-width: 0;
		gap: 2px;
	}

	.mobile-list-record__identity span,
	.mobile-list-record__facts span {
		color: var(--erp-text-muted);
		font-size: var(--erp-font-size-min);
		font-weight: 700;
		letter-spacing: .025em;
		text-transform: uppercase;
	}

	.mobile-list-record__identity strong,
	.mobile-list-record__facts strong {
		overflow: hidden;
		color: var(--erp-text);
		font-size: var(--erp-font-size-table);
		font-weight: 650;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.mobile-list-record__identity strong {
		color: var(--erp-accent-dark);
		font-size: 14px;
	}

	.mobile-list-record__facts {
		display: grid;
		grid-template-columns: repeat(3, minmax(0, 1fr));
		gap: 8px;
	}

	.mobile-list-record__actions {
		display: flex;
		justify-content: flex-end;
		gap: 6px;
		padding-top: 2px;
	}

	.mobile-list-record__actions :deep(.p-button) {
		min-width: 44px;
		min-height: 44px;
	}

	.mobile-list-empty {
		justify-items: center;
		gap: 6px;
		padding: 44px 16px;
		color: var(--erp-text-muted);
		text-align: center;
	}

	.mobile-list-empty strong {
		color: var(--erp-text);
	}

	.list-page-head {
		align-items: stretch;
		flex-direction: column;
	}

	.list-toolbar__actions {
		display: grid;
		grid-template-columns: minmax(0, 1fr) auto;
		gap: 8px;
		justify-content: stretch;
		padding: 0;
	}

	.list-toolbar__primary {
		display: flex;
		grid-column: 2;
		grid-row: 1;
	}

	.list-toolbar__primary:empty {
		display: none;
	}

	.list-toolbar__secondary {
		display: grid;
		grid-column: 1 / -1;
		grid-row: 2;
		grid-template-columns: repeat(4, minmax(0, 1fr));
		gap: 6px;
	}

	.list-search :deep(input) {
		width: 100%;
	}

	.list-search {
		grid-column: 1;
		grid-row: 1;
		width: 100%;
	}

	.list-toolbar__primary :deep(.p-button),
	.list-toolbar__secondary :deep(.p-button) {
		justify-content: center;
		width: 100%;
		min-height: 44px;
	}

	.list-toolbar__primary :deep(.p-button) {
		width: auto;
		min-width: max-content;
		padding-inline: 14px;
	}

	.mobile-quick-filter-toggle {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 8px;
		min-height: 44px;
		padding: 0 12px;
		color: var(--list-muted);
		background: var(--erp-surface);
		border: 1px solid var(--list-line);
		border-radius: var(--erp-control-radius);
		font: inherit;
		font-size: 0.78rem;
		font-weight: 650;
		text-align: left;
	}

	.mobile-quick-filter-toggle > span:first-child {
		display: inline-flex;
		align-items: center;
		gap: 7px;
	}

	.mobile-quick-filter-toggle__count {
		margin-left: auto;
		padding: 1px 7px;
		color: var(--list-accent-dark);
		background: var(--list-accent-soft);
		border-radius: 999px;
	}

	.mobile-quick-filter-toggle--active {
		color: var(--list-accent-dark);
		background: var(--list-accent-soft);
		border-color: color-mix(in srgb, var(--list-accent) 38%, white);
	}

	.list-quick-filters {
		display: none;
	}

	.list-quick-filters--open {
		display: block;
	}

	.bulk-bar,
	.bulk-bar__actions {
		align-items: stretch;
		flex-direction: column;
	}

	.bulk-bar__actions :deep(.p-button) {
		justify-content: center;
		width: 100%;
		min-height: 44px;
	}

	.list-status-tab {
		min-height: 44px;
	}
}

@media (max-width: 540px) {
	.mobile-list-record__facts {
		grid-template-columns: repeat(2, minmax(0, 1fr));
	}
	.list-toolbar__secondary :deep(.p-button-label) {
		position: absolute;
		width: 1px;
		height: 1px;
		padding: 0;
		margin: -1px;
		overflow: hidden;
		clip: rect(0, 0, 0, 0);
		white-space: nowrap;
		border: 0;
	}

	.list-toolbar__secondary :deep(.p-button) {
		min-width: 44px;
		padding-inline: 0;
	}
}

@media (max-width: 420px) {
	.list-toolbar__actions {
		grid-template-columns: minmax(0, 1fr);
	}

	.list-search,
	.list-toolbar__primary,
	.list-toolbar__secondary {
		grid-column: 1;
	}

	.list-search { grid-row: 1; }
	.list-toolbar__primary { grid-row: 2; }
	.list-toolbar__secondary { grid-row: 3; }

	.list-toolbar__primary :deep(.p-button) {
		width: 100%;
	}
}
</style>
