<template>
	<div class="list-page">
		<!-- Header -->
		<div class="page-head">
			<div>
				<h1 class="page-title">{{ registry?.label || docRoute }}</h1>
				<p v-if="!doctype" class="page-sub">unknown route</p>
			</div>
			<div class="head-actions">
				<IconField v-if="!accessDenied">
					<InputIcon class="pi pi-search" />
					<InputText
						v-model="searchQuery"
						placeholder="Search…"
						@keyup.enter="onSearch"
					/>
				</IconField>
				<Button
					v-if="doctype && !accessDenied && eligibleColumns.length"
					label="Columns"
					icon="pi pi-sliders-h"
					severity="secondary"
					outlined
					size="small"
					@click="showColumnsModal = true"
				/>
				<Button
					v-if="doctype && !accessDenied"
					:label="advFilters.length ? `Filter (${advFilters.length})` : 'Filter'"
					icon="pi pi-filter"
					severity="secondary"
					outlined
					size="small"
					@click="showFilterPanel = true"
				/>
				<Button
					v-if="isAdmin || hasRole('System Manager')"
					label="Open in Desk"
					icon="pi pi-external-link"
					severity="secondary"
					outlined
					size="small"
					@click="openListInDesk"
				/>
				<Button
					v-if="doctype && canCreate(doctype)"
					label="New"
					icon="pi pi-plus"
					size="small"
					@click="onNew"
				/>
			</div>
		</div>

		<!-- Realtime: records changed elsewhere while a bulk selection is active.
		     We don't auto-refresh (that would drop the selection) — offer a manual
		     refresh pill instead. With no selection, the list refetches silently. -->
		<div v-if="pendingUpdates" class="rt-pending">
			<i class="pi pi-bolt" />
			<span>New updates are available.</span>
			<button type="button" class="rt-pending__btn" @click="refreshListNow">Refresh</button>
		</div>

		<!-- Tab strip (meta-derived: status mode / docstatus mode / none — see CUSTOM_UI §6.3) -->
		<Tabs v-if="tabMode" :value="activeTab" @update:value="onTabChange">
			<TabList>
				<Tab
					v-for="t in statusTabs"
					:key="tabValueKey(t.value)"
					:value="tabValueKey(t.value)"
				>
					{{ t.label }}
					<span class="tab-count">{{ t.count }}</span>
				</Tab>
			</TabList>
		</Tabs>

		<!-- Date tabs -->
		<div v-if="dateTabField" class="date-tabs">
			<button
				v-for="t in dateTabOptions"
				:key="t.value"
				class="date-tab"
				:class="{ active: activeDateTab === t.value }"
				@click="onDateTabChange(t.value)"
			>
				{{ t.label }}
			</button>
		</div>

		<!-- Active base filter (implicit URL filter, CUSTOM_UI §6.4). Read-only
		     chip + clear — NOT the deferred interactive Filter popover. -->
		<div v-if="hasBaseFilter" class="base-filter-row">
			<span class="base-filter-chip">
				<i class="pi pi-filter" />
				{{ baseFilterLabel }}
				<button
					class="chip-clear"
					type="button"
					aria-label="Clear filter"
					@click="clearBaseFilter"
				>
					<i class="pi pi-times" />
				</button>
			</span>
		</div>

		<!-- Active interactive filters (Filter popover) — each chip clears one. -->
		<div v-if="filterChips.length" class="adv-filter-row">
			<span v-for="(chip, i) in filterChips" :key="i" class="adv-filter-chip">
				{{ chip }}
				<button class="chip-clear" type="button" aria-label="Remove filter" @click="removeAdvFilter(i)">
					<i class="pi pi-times" />
				</button>
			</span>
			<button class="adv-filter-clear" type="button" @click="clearAdvFilters">Clear all</button>
		</div>

		<!-- Error -->
		<Message v-if="errorMsg" severity="error" :closable="false" class="list-error">
			{{ accessDenied ? `You don’t have access to ${registry?.label || doctype}. Ask an administrator if you need it.` : errorMsg }}
			<template #icon><i class="pi pi-exclamation-triangle" /></template>
		</Message>
		<Message
			v-if="bulkError"
			severity="error"
			closable
			class="list-error"
			@close="bulkError = null"
		>
			<div class="bulk-error">
				<div class="bulk-error__title">{{ bulkError.title }}</div>
				<div
					v-for="(line, i) in bulkError.lines"
					:key="i"
					class="bulk-error__line"
				>{{ line }}</div>
			</div>
		</Message>

		<div v-if="showBulkBar" class="bulk-bar">
			<div class="bulk-bar__summary">
				<span class="bulk-count">{{ selectedRows.length }} selected</span>
				<span v-if="selectedDraftRows.length" class="bulk-hint">
					{{ selectedDraftRows.length }} draft
				</span>
				<span v-if="selectedSubmittedRows.length" class="bulk-hint">
					{{ selectedSubmittedRows.length }} submitted
				</span>
			</div>
			<div class="bulk-bar__actions">
				<Button
					v-if="canBulkEdit"
					label="Edit"
					icon="pi pi-pencil"
					size="small"
					severity="secondary"
					outlined
					:disabled="!selectedRows.length || !!bulkActing"
					:loading="bulkActing === 'edit' || bulkEditLoading"
					@click="openBulkEditDialog"
				/>
				<Button
					v-if="isSubmittable && canSubmit(doctype)"
					:label="`Submit (${selectedDraftRows.length})`"
					icon="pi pi-arrow-right"
					size="small"
					:disabled="!selectedDraftRows.length || !!bulkActing"
					:loading="bulkActing === 'submit'"
					@click="onBulkSubmit"
				/>
				<Button
					v-if="isSubmittable && canCancel(doctype)"
					:label="`Cancel (${selectedSubmittedRows.length})`"
					icon="pi pi-ban"
					size="small"
					severity="danger"
					outlined
					:disabled="!selectedSubmittedRows.length || !!bulkActing"
					:loading="bulkActing === 'cancel'"
					@click="onBulkCancel"
				/>
				<Button
					icon="pi pi-times"
					severity="secondary"
					text
					rounded
					size="small"
					aria-label="Clear selection"
					:disabled="!!bulkActing"
					@click="clearSelection"
				/>
			</div>
		</div>

		<!-- dcEntry.variant "inline-grid" (demo-5, Delivery Challan only): a
		     collapsible embedded create-mode DocDetail ABOVE the list — no
		     overlay, no navigation. "+ New" expands it; save/discard collapse
		     it (save also refreshes rows + tab counts). Knob absent or other
		     doctypes → this block never renders (parity law). -->
		<section
			v-if="inlineEntryOpen && dcEntryVariant === 'inline-grid'"
			class="dc-inline-entry"
			aria-label="Inline entry panel"
		>
			<DcEntryChips
				v-if="dcInlineSupplierChips"
				show-supplier-chips
				:active-supplier="inlinePickedSupplier"
				@pick-supplier="onInlinePickSupplier"
			/>
			<DocDetail
				ref="inlineEntryRef"
				key="dc-inline-new"
				:doc-route="props.docRoute"
				id="new"
				embedded
				@close="onInlineEntryClose"
				@saved="onInlineEntrySaved"
			/>
		</section>

		<!-- Table (the DEFAULT presentation — layouts without a variant knob render
		     EXACTLY this, byte-identical to today; parity law) -->
		<DataTable
			v-if="listVariant === 'table'"
			:value="rows"
			v-model:selection="selectedRows"
			:loading="loading"
			dataKey="name"
			class="esd-table"
			:rowHover="true"
			:rowClass="rowClass"
			@row-click="onRowClick"
		>
			<Column
				v-if="showBulkSelection"
				selectionMode="multiple"
				headerStyle="width: 42px"
				bodyStyle="width: 42px; text-align: center"
			/>
			<Column field="name" header="Name" :sortable="true">
				<template #body="{ data }">
					<span class="esd-mono">{{ data.name }}</span>
				</template>
			</Column>

			<Column
				v-for="col in listColumns"
				:key="col.field"
				:field="col.field"
				:header="col.label"
				:sortable="true"
			>
				<template #body="{ data }">
					<span v-if="col.type === 'Date'">{{ formatDate(data[col.field]) }}</span>
					<span v-else-if="col.type === 'Datetime'">{{ formatDate(data[col.field]) }}</span>
					<span v-else-if="col.type === 'Currency'">{{ formatNumber(data[col.field]) }}</span>
					<!-- Q1: a Link column shows the human name, not the code. -->
					<span v-else-if="col.isLink && data[col.field]">{{ linkName(col, data) }}</span>
					<span v-else>{{ data[col.field] ?? "—" }}</span>
				</template>
			</Column>

			<Column v-if="isSubmittable || isWorkflow" header="Status" :style="{ width: '130px' }">
				<template #body="{ data }">
					<Tag
						class="list-status"
						:value="statusLabel(data)"
						:severity="rowSeverity(data)"
						rounded
					/>
				</template>
			</Column>

			<!-- Q8: persistent "this row opens" affordance (tablets have no hover). -->
			<Column :style="{ width: '36px' }" bodyStyle="text-align:center;padding-left:0;padding-right:0">
				<template #body>
					<i class="pi pi-chevron-right row-chevron" />
				</template>
			</Column>

			<template #empty>
				<div class="esd-empty">
					<i class="pi pi-inbox" />
					<p class="esd-empty__text">
						{{ hasAnyFilter ? "No records match the current filters" : "No records found" }}
					</p>
					<!-- Q14: on a truly empty (unfiltered) list, offer the first create. -->
					<Button
						v-if="doctype && canCreate(doctype) && !hasAnyFilter"
						:label="`Create the first ${registry?.label || doctype}`"
						icon="pi pi-plus"
						size="small"
						@click="onNew"
					/>
				</div>
			</template>
		</DataTable>

		<!-- Cards / Kanban (layout knob listViews[dt].variant — demo _template §7).
		     Pure presentation over the SAME fetch layer: search, filters, tabs and
		     the paginator above/below all keep operating on listState unchanged. -->
		<ListCards
			v-else-if="listVariant === 'cards'"
			:rows="rows"
			:columns="variantColumns"
			:title-field="variantTitleField"
			:title-of="variantTitleOf"
			:status-of="variantStatusOf"
			:cell-value="variantCellValue"
			:loading="loading"
			@open="onCardOpen"
		/>
		<ListKanban
			v-else
			:rows="rows"
			:columns="variantColumns"
			:title-field="variantTitleField"
			:title-of="variantTitleOf"
			:status-of="variantStatusOf"
			:cell-value="variantCellValue"
			:group-of="kanbanGroupOf"
			:group-field="kanbanGroupField"
			:loading="loading"
			@open="onCardOpen"
		/>
		<!-- Shared empty state for the card/kanban variants (mirrors the table's
		     #empty slot, incl. the Q14 first-create offer on a truly empty list). -->
		<div v-if="listVariant !== 'table' && !loading && !rows.length" class="esd-empty variant-empty">
			<i class="pi pi-inbox" />
			<p class="esd-empty__text">
				{{ hasAnyFilter ? "No records match the current filters" : "No records found" }}
			</p>
			<Button
				v-if="doctype && canCreate(doctype) && !hasAnyFilter"
				:label="`Create the first ${registry?.label || doctype}`"
				icon="pi pi-plus"
				size="small"
				@click="onNew"
			/>
		</div>

		<!-- Paginator -->
		<Paginator
			v-if="totalCount > pageSize"
			:rows="pageSize"
			:totalRecords="totalCount"
			:first="(page - 1) * pageSize"
			@page="onPage"
		/>

		<!-- Detail / entry overlays (layout structural knobs). Renders nothing
		     unless a knob is active AND the ?detail=/?new= query is present —
		     the parity-law default (no knob) leaves this completely inert. -->
		<DocOverlayHost
			v-if="doctype && (overlayDetailActive || overlayEntryActive)"
			:doc-route="props.docRoute"
			@saved="onOverlaySaved"
		/>

		<ColumnCustomizerModal
			v-model:visible="showColumnsModal"
			:doctype="doctype"
			:columns="modalColumns"
			@saved="onColumnsSaved"
		/>

		<FilterPanel
			v-model:visible="showFilterPanel"
			:doctype="doctype"
			:model-value="advFilters"
			@apply="onApplyFilters"
		/>

		<Dialog
			v-model:visible="showBulkEditDialog"
			header="Bulk Edit"
			modal
			class="bulk-edit-dialog"
			:style="{ width: 'min(560px, calc(100vw - 32px))' }"
		>
			<div class="bulk-edit-form">
				<div class="bulk-edit-selected">
					<span class="bulk-count">{{ selectedRows.length }} selected</span>
					<span v-if="selectedCancelledRows.length" class="bulk-hint">
						{{ selectedCancelledRows.length }} cancelled
					</span>
				</div>

				<div class="bulk-edit-field">
					<label class="field-label" for="bulk-edit-field">Field</label>
					<Select
						id="bulk-edit-field"
						v-model="bulkEditSelectedKey"
						:options="bulkEditFieldOptions"
						optionLabel="label"
						optionValue="key"
						:loading="bulkEditLoading"
						placeholder="Select field"
						filter
						class="fld"
						fluid
					/>
				</div>

				<div v-if="bulkEditSelectedField" class="bulk-edit-field">
					<label class="field-label" for="bulk-edit-value">Value</label>

					<Textarea
						v-if="bulkEditInputKind === 'textarea'"
						id="bulk-edit-value"
						v-model="bulkEditValue"
						rows="3"
						autoResize
						class="fld"
					/>

					<InputNumber
						v-else-if="bulkEditInputKind === 'number'"
						id="bulk-edit-value"
						v-model="bulkEditValue"
						:minFractionDigits="bulkNumberFractions.min"
						:maxFractionDigits="bulkNumberFractions.max"
						class="fld"
						fluid
					/>

					<DatePicker
						v-else-if="bulkEditInputKind === 'date'"
						inputId="bulk-edit-value"
						:modelValue="toDateObj(bulkEditValue)"
						@update:modelValue="bulkEditValue = fromDateObj($event, false)"
						dateFormat="dd-mm-yy"
						showIcon
						iconDisplay="input"
						class="fld"
						fluid
					/>

					<DatePicker
						v-else-if="bulkEditInputKind === 'datetime'"
						inputId="bulk-edit-value"
						:modelValue="toDateObj(bulkEditValue)"
						@update:modelValue="bulkEditValue = fromDateObj($event, true)"
						dateFormat="dd-mm-yy"
						showTime
						hourFormat="24"
						showIcon
						iconDisplay="input"
						class="fld"
						fluid
					/>

					<div v-else-if="bulkEditInputKind === 'check'" class="fld-check">
						<ToggleSwitch
							inputId="bulk-edit-value"
							:modelValue="!!bulkEditValue"
							@update:modelValue="bulkEditValue = $event ? 1 : 0"
						/>
						<span class="check-label">{{ bulkEditValue ? "Yes" : "No" }}</span>
					</div>

					<Select
						v-else-if="bulkEditInputKind === 'select'"
						id="bulk-edit-value"
						v-model="bulkEditValue"
						:options="bulkEditSelectOptions"
						showClear
						placeholder="Select value"
						class="fld"
						fluid
					/>

					<LinkField
						v-else-if="bulkEditInputKind === 'link'"
						v-model="bulkEditValue"
						:target-doctype="bulkEditSelectedField.options"
						class="fld"
					/>

					<InputText
						v-else
						id="bulk-edit-value"
						v-model="bulkEditValue"
						class="fld"
					/>

					<p v-if="bulkEditValueIsEmpty" class="bulk-edit-help">
						Empty value will clear this field where validation allows.
					</p>
				</div>
			</div>
			<template #footer>
				<Button
					label="Cancel"
					severity="secondary"
					text
					:disabled="bulkEditApplying"
					@click="showBulkEditDialog = false"
				/>
				<Button
					:label="bulkEditApplyLabel"
					icon="pi pi-check"
					:disabled="!bulkEditSelectedField || bulkEditLoading || bulkEditApplying"
					:loading="bulkEditApplying"
					@click="onBulkEditApply"
				/>
			</template>
		</Dialog>
	</div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, shallowRef, watch } from "vue"
import { useRouter, useRoute } from "vue-router"
import DataTable from "primevue/datatable"
import Column from "primevue/column"
import Button from "primevue/button"
import InputText from "primevue/inputtext"
import IconField from "primevue/iconfield"
import InputIcon from "primevue/inputicon"
import Tabs from "primevue/tabs"
import TabList from "primevue/tablist"
import Tab from "primevue/tab"
import Tag from "primevue/tag"
import Paginator from "primevue/paginator"
import Message from "primevue/message"
import Dialog from "primevue/dialog"
import Select from "primevue/select"
import Textarea from "primevue/textarea"
import InputNumber from "primevue/inputnumber"
import DatePicker from "primevue/datepicker"
import ToggleSwitch from "primevue/toggleswitch"
import { useDocList } from "@/composables/useDocList"
import { captureListContext } from "@/composables/useListContext"
import { useRealtime } from "@/composables/useRealtime"
import { usePermissions } from "@/composables/usePermissions"
import { useLinkTitles } from "@/composables/useLinkTitles"
import { useAppConfirm } from "@/composables/useConfirm"
import { useAppToast } from "@/composables/useToast"
import { useUiConfigStore } from "@yrp/web-engine"
import { getRegistryByRoute, WORKFLOW_SEVERITY } from "@/config/doctypes"
import { getFieldLabel } from "@/config/fields"
import { getMeta, getCount, callMethod, submitDoc, cancelDoc, getBulkEditFields, bulkUpdateField, errorLines } from "@/api/client"
import ColumnCustomizerModal from "@/components/ColumnCustomizerModal.vue"
import FilterPanel from "@/components/FilterPanel.vue"
import LinkField from "@/components/LinkField.vue"
import ListCards from "@/components/list/ListCards.vue"
import ListKanban from "@/components/list/ListKanban.vue"
import DcEntryChips from "@/views/dynamic/DcEntryChips.vue"
import DocDetail from "@/views/dynamic/DocDetail.vue"
import DocOverlayHost from "@/views/dynamic/DocOverlayHost.vue"

const props = defineProps({
	docRoute: { type: String, required: true },
})

const router = useRouter()
const route = useRoute()
const { canCreate, canWrite, canSubmit, canCancel, isAdmin, hasRole } = usePermissions()
const linkTitles = useLinkTitles()
const confirm = useAppConfirm()
const toast = useAppToast()

const registry = computed(() => getRegistryByRoute(props.docRoute))
const doctype = computed(() => registry.value?.doctype || "")
const isWorkflow = computed(() => registry.value?.isWorkflow || false)
const meta = shallowRef(null)            // parent DocType meta (docs[0]), cached per route
const isSubmittable = computed(
	() => !isWorkflow.value && (registry.value?.isSubmittable || Number(meta.value?.is_submittable) === 1),
)
const workflowStates = computed(() => registry.value?.workflowStates || [])
const dateTabField = computed(() => registry.value?.dateTabs || null)

// Tree view: any DocType flagged is_tree (Item Group, …) can show a hierarchical
// card tree instead of the flat list. Detected from meta at runtime — generic.

// ── Columns: meta-driven, overlaid with the user's saved per-user choice (#2) ──
// No hardcoded listFields: defaults come from the DocType meta (`in_list_view`),
// the user can pick + reorder via the Customize Columns modal, and the choice is
// stored in the `User Listview` doctype (base yrp).
const NON_LISTABLE = new Set([
	"Table", "Table MultiSelect", "Text Editor", "Long Text", "Small Text", "Text",
	"HTML", "HTML Editor", "Code", "Markdown Editor", "Section Break", "Column Break",
	"Tab Break", "Fold", "Heading", "Button", "Image", "Geolocation", "Signature",
])
const userColumns = ref(null) // saved [{fieldname, enabled, …}] for this user+doctype, or null
const showColumnsModal = ref(false)
const showFilterPanel = ref(false)
const advFilters = ref([]) // active interactive filters (Frappe tuples)
const filterChips = ref([]) // display labels aligned 1:1 with advFilters
const selectedRows = ref([])
const bulkActing = ref(null)
const bulkError = ref(null)
const showBulkEditDialog = ref(false)
const bulkEditLoading = ref(false)
const bulkEditApplying = ref(false)
const bulkEditFieldsFor = ref("")
const bulkEditFields = ref([])
const bulkEditSelectedKey = ref("")
const bulkEditValue = ref(null)

const selectedDraftRows = computed(() =>
	selectedRows.value.filter((row) => Number(row.docstatus) === 0),
)
const selectedSubmittedRows = computed(() =>
	selectedRows.value.filter((row) => Number(row.docstatus) === 1),
)
const selectedCancelledRows = computed(() =>
	selectedRows.value.filter((row) => Number(row.docstatus) === 2),
)

const bulkEditFieldOptions = computed(() =>
	bulkEditFields.value.map((field) => ({
		...field,
		label: field.is_child_field
			? field.label
			: (getFieldLabel(doctype.value, field.fieldname) || field.label || field.fieldname),
	})),
)
const bulkEditSelectedField = computed(() =>
	bulkEditFieldOptions.value.find((field) => field.key === bulkEditSelectedKey.value) || null,
)
const bulkEditInputKind = computed(() => bulkInputKind(bulkEditSelectedField.value))
const bulkEditSelectOptions = computed(() => {
	const field = bulkEditSelectedField.value
	if (!field || field.fieldtype !== "Select") return []
	return String(field.options || "")
		.split("\n")
		.map((option) => option.trim())
		.filter(Boolean)
})
const bulkNumberFractions = computed(() => {
	const fieldtype = bulkEditSelectedField.value?.fieldtype
	if (fieldtype === "Int" || fieldtype === "Long Int") return { min: 0, max: 0 }
	if (fieldtype === "Currency") return { min: 2, max: 2 }
	if (fieldtype === "Percent") return { min: 0, max: 2 }
	return { min: 0, max: 6 }
})
const bulkEditValueIsEmpty = computed(() =>
	bulkEditValue.value === null || bulkEditValue.value === undefined || bulkEditValue.value === "",
)
const bulkEditApplyLabel = computed(() =>
	`Update ${selectedRows.value.length} ${plural(selectedRows.value.length, "record")}`,
)

function bulkInputKind(field) {
	if (!field) return "text"
	const ft = field.fieldtype
	if (["Text", "Long Text", "Code", "Text Editor", "Markdown Editor", "HTML Editor", "JSON", "Geolocation", "Signature"].includes(ft)) {
		return "textarea"
	}
	if (["Int", "Long Int", "Float", "Percent", "Currency", "Duration", "Rating"].includes(ft)) return "number"
	if (ft === "Date") return "date"
	if (ft === "Datetime") return "datetime"
	if (ft === "Check") return "check"
	if (ft === "Select") return "select"
	if (ft === "Link") return "link"
	return "text"
}

function defaultBulkValue(field) {
	if (!field) return ""
	if (field.fieldtype === "Check") return 0
	if (field.fieldtype === "Select") {
		const options = String(field.options || "")
			.split("\n")
			.map((option) => option.trim())
			.filter(Boolean)
		if (/status/i.test(field.fieldname || field.label || "")) return options[0] || ""
	}
	return ""
}

watch(bulkEditSelectedKey, () => {
	bulkEditValue.value = defaultBulkValue(bulkEditSelectedField.value)
})

function clearSelection() {
	selectedRows.value = []
}

function colType(ft) {
	if (ft === "Date") return "Date"
	if (ft === "Datetime") return "Datetime"
	if (ft === "Currency") return "Currency"
	return undefined
}

// Every field a user could pick as a column (from meta, minus name + non-listable).
const eligibleColumns = computed(() => {
	const out = []
	for (const f of meta.value?.fields || []) {
		if (f.fieldname === "name" || f.hidden) continue
		if (NON_LISTABLE.has(f.fieldtype)) continue
		out.push({
			field: f.fieldname,
			// Q18: SPA label override (supplier → "Job-worker") must reach the list
			// column HEADER too, not just detail/form — else the same field reads
			// differently across screens. modalColumns inherits this label.
			label: getFieldLabel(doctype.value, f.fieldname) || f.label || f.fieldname,
			type: colType(f.fieldtype),
			fieldtype: f.fieldtype,
			in_list_view: !!f.in_list_view,
			// Q1: Link columns resolve to a human name (target from meta options).
			isLink: f.fieldtype === "Link",
			linkTarget: f.fieldtype === "Link" ? (f.options || "") : "",
		})
	}
	return out
})

// Layout-tier default columns from the active UI layout (spec §7.3):
// resolved `listViews[doctype].columns` mapped onto the meta-eligible fields
// (unknown fields drop silently; the layout's label wins when it names one).
// The Default layout seeds `listViews: {}` so this tier resolves null and
// today's rendering is untouched.
const uiStore = useUiConfigStore()
const layoutColumns = computed(() => {
	const cols = uiStore.listColumns(doctype.value)
	if (!Array.isArray(cols) || !cols.length) return null
	const byField = new Map(eligibleColumns.value.map((c) => [c.field, c]))
	const out = []
	for (const lc of cols) {
		if (!lc || !lc.field || lc.field === "name") continue
		const e = byField.get(lc.field)
		if (e) out.push(lc.label ? { ...e, label: lc.label } : e)
	}
	return out.length ? out : null
})

// Columns rendered in the table (spec §7.3 precedence, highest wins):
// per-user saved User Listview (enabled, in saved order) → layout-tier
// listViews columns → meta `in_list_view` defaults → none (only the
// always-present Name column).
const listColumns = computed(() => {
	const byField = new Map(eligibleColumns.value.map((c) => [c.field, c]))
	if (Array.isArray(userColumns.value) && userColumns.value.length) {
		const cols = []
		for (const uc of userColumns.value) {
			if (!uc.enabled || uc.fieldname === "name") continue
			const e = byField.get(uc.fieldname)
			if (e) cols.push(e)
		}
		return cols
	}
	if (layoutColumns.value) return layoutColumns.value
	return eligibleColumns.value.filter((c) => c.in_list_view)
})

// ── List presentation variant (layout knob — spec §6.4, demo _template §7) ──
// listViews[dt].variant: "table" (DEFAULT — byte-identical to today) | "cards"
// | "kanban"; kanban groups by listViews[dt].groupBy. Variants are PURE
// presentation over the same fetch layer: search, filters, tabs, paginator and
// permissions all keep operating on listState unchanged.
const listViewCfg = computed(() => uiStore.active.listViews?.[doctype.value] || {})
const metaFieldSet = computed(() => new Set((meta.value?.fields || []).map((f) => f.fieldname)))
const hasStatusSignal = computed(
	() => isSubmittable.value || isWorkflow.value || metaFieldSet.value.has("status"),
)

// Kanban's group source: the layout's groupBy when it's a real meta field.
const kanbanGroupField = computed(() => {
	const g = listViewCfg.value.groupBy
	return typeof g === "string" && g && metaFieldSet.value.has(g) ? g : ""
})

const listVariant = computed(() => {
	const v = listViewCfg.value.variant
	if (v === "cards") return "cards"
	// Kanban with neither a valid groupBy nor any status signal has nothing to
	// group by → table (demo renderKanban parity). A missing/invalid groupBy
	// WITH a status signal falls back to status-grouping.
	if (v === "kanban") return kanbanGroupField.value || hasStatusSignal.value ? "kanban" : "table"
	return "table"
})

// ── Detail / entry overlays (layout structural knobs — spec §6.4) ───────────
// detail.position right|center|bottom-sheet → row/card clicks open the record
// as ?detail=<name> on THIS route and DocOverlayHost renders the embedded
// DocDetail in a Drawer/Dialog. entry.mode "popup" → the New buttons open
// ?new=1 (create Dialog) instead of routing to /:docRoute/new. Knob absent or
// "page" → today's router.push EXACTLY (parity law).
//
// BOUNDARY: these knobs only ever intercept LIST-PAGE interactions (row/card
// clicks + the New buttons on this page). Direct path navigation —
// /web/:docRoute/:id from home tiles, the palette, deep links, and
// forward-action pushes like /delivery-challan/new?work_order=… — keeps
// rendering full-page regardless of the knobs.
//
// EXCLUDED routes: doctypes whose /:id (or /new) paths are pre-empted by
// EXPLICIT rich routes (router/index.js: IPDConfig, ProcessMatrix, BOMMapping,
// IPDCreate). Their clicks must keep reaching those rich views — the generic
// DocDetail overlay would silently bypass them.
const OVERLAY_EXCLUDED_ROUTES = new Set([
	"item-production-detail",
	"ipd-process-matrix",
	"item-bom-attribute-mapping",
])
const overlayDetailActive = computed(() => {
	if (OVERLAY_EXCLUDED_ROUTES.has(props.docRoute)) return false
	const p = uiStore.detailKnob?.position
	return p === "right" || p === "center" || p === "bottom-sheet"
})
const overlayEntryActive = computed(
	() =>
		!OVERLAY_EXCLUDED_ROUTES.has(props.docRoute) &&
		(uiStore.entryKnob?.mode === "popup" || dcEntryVariant.value === "size-matrix"),
)

// ── DC entry variants (dcEntry knob — Delivery Challan ONLY, spec §6.4) ────
// "size-matrix" (demo-7): + New opens the bottom-sheet entry hosted by
// DocOverlayHost — same pushed ?new=1 protocol as the entry popup; the host
// picks the sheet over the popup for DC. "inline-grid" (demo-5): + New
// expands an embedded create-mode DocDetail ABOVE the list — no overlay, no
// navigation. Knob absent, other variants (form-grid…), or other doctypes →
// + New behaves exactly as today (parity law). qtyControl: only "input" (the
// existing size-pivot grid inputs) is implemented — other values are ignored
// client-side; the server already soft-warns on them.
const dcEntryVariant = computed(() => {
	if (props.docRoute !== "delivery-challan") return null
	const v = uiStore.dcEntryKnob?.variant
	return v === "size-matrix" || v === "inline-grid" ? v : null
})
// supplierPicker "chips" in the INLINE panel (the sheet's chips live in
// DocOverlayHost); "select"/absent → the form's untouched Link field only.
const dcInlineSupplierChips = computed(
	() => dcEntryVariant.value === "inline-grid" && uiStore.dcEntryKnob?.supplierPicker === "chips",
)

// Inline-grid entry panel state. A live knob change (or a route change — the
// variant computed flips to null) closes a stale panel so it never hosts a
// form the layout no longer asks for.
const inlineEntryOpen = ref(false)
const inlineEntryRef = ref(null)
const inlinePickedSupplier = ref("") // active-chip highlight only
watch(dcEntryVariant, (v) => {
	if (v !== "inline-grid") inlineEntryOpen.value = false
})
watch(inlineEntryOpen, (v) => {
	if (!v) inlinePickedSupplier.value = ""
})

function onInlineEntryClose() {
	inlineEntryOpen.value = false
}
// Save inside the panel: collapse + refresh rows and tab counts (the success
// toast already fired inside DocDetail — same as the overlay host).
function onInlineEntrySaved() {
	inlineEntryOpen.value = false
	refreshListNow()
}
// Cancel = the embedded form's own Discard button (it runs DocDetail's
// internal dirty confirm, then emits `close` → collapse). The panel adds no
// chrome of its own: the form's "New <label>" header + Discard/Save ARE the
// panel head — a second title/✕ here would just duplicate them.
// Chip pick → the embedded DocDetail's setFormField: the SAME assign +
// onFieldChanged path a LinkField pick runs (see DocOverlayHost). It returns
// false while the create form is still building (form = {} until the meta
// round-trip finishes) — highlight only a pick that actually landed.
async function onInlinePickSupplier(name) {
	if (await inlineEntryRef.value?.setFormField("supplier", name)) inlinePickedSupplier.value = name
	else toast.info("Form is still loading", "Tap the Job-worker again in a moment.")
}

// The overlay reported a successful create/save: refresh rows + tab counts
// (the overlay itself closed already; the success toast fired in DocDetail).
function onOverlaySaved() {
	refreshListNow()
}

// Cards/kanban follow the SAME §7.3 column precedence the table uses (enabled
// per-user User Listview columns in saved order → layout listViews columns →
// meta `in_list_view` defaults), so rendering, search and the Columns modal
// agree on every variant — the user's column management sits on top of
// whatever presentation the layout chose.
const variantColumns = computed(() => listColumns.value)

// Bold card title: layout-named field (listViews[dt].titleField) > meta
// title_field > the first non-status key column; docname as the row fallback.
const variantTitleField = computed(() => {
	const t = listViewCfg.value.titleField
	if (typeof t === "string" && t && metaFieldSet.value.has(t)) return t
	const mt = meta.value?.title_field
	if (mt && mt !== "name" && metaFieldSet.value.has(mt)) return mt
	const c = variantColumns.value.find((col) => col.field !== "status")
	return c ? c.field : ""
})
const titleColDesc = computed(
	() => eligibleColumns.value.find((c) => c.field === variantTitleField.value) || null,
)
const groupColDesc = computed(
	() => eligibleColumns.value.find((c) => c.field === kanbanGroupField.value) || null,
)

function variantTitleOf(row) {
	const f = variantTitleField.value
	if (!f) return row.name
	const v = titleColDesc.value ? variantCellValue(titleColDesc.value, row) : row[f]
	return v === null || v === undefined || v === "" || v === "—" ? row.name : String(v)
}

// Status chip text for a card: same source order as the table's Status tag
// (workflow_state > status > docstatus); "" (no signal) = no chip, no tint.
function variantStatusOf(row) {
	if (isWorkflow.value && row.workflow_state) return row.workflow_state
	if (typeof row.status === "string" && row.status) return row.status
	if (isSubmittable.value) return DOCSTATUS_LABELS[row.docstatus] || ""
	return ""
}

// Mirror of the table's cell body: dates dd-mm-yyyy, Indian-grouped numbers,
// Link codes resolved to human names.
function variantCellValue(col, row) {
	if (col.type === "Date" || col.type === "Datetime") return formatDate(row[col.field])
	if (col.type === "Currency") return formatNumber(row[col.field])
	if (col.isLink && row[col.field]) return linkName(col, row)
	return row[col.field] ?? "—"
}

// Kanban column label for a row: the groupBy field's formatted value (blank →
// "—"), else the synthesized status when grouping fell back to it.
function kanbanGroupOf(row) {
	if (!kanbanGroupField.value) return variantStatusOf(row) || "—"
	const raw = row[kanbanGroupField.value]
	if (raw === null || raw === undefined || raw === "") return "—"
	return groupColDesc.value ? String(variantCellValue(groupColDesc.value, row)) : String(raw)
}

// Card/kanban click → detail, exactly like a table row click (same nav-context
// capture so the detail page's prev/next arrows step through this list, and
// the same detail-overlay knob interception — ALL list variants behave alike).
function onCardOpen(row) {
	const name = row?.name
	if (!name) return
	captureNavContext()
	if (overlayDetailActive.value) {
		router.push({ query: { ...route.query, detail: name } })
		return
	}
	router.push(`/${props.docRoute}/${encodeURIComponent(name)}`)
}

// Fields offered in the Customize Columns modal: every eligible field, marked
// enabled + ordered per the saved config (else the layout-tier columns when
// the active layout sets them — so the modal opens showing what is actually
// rendered — else meta `in_list_view` defaults). Saving still writes User
// Listview, which then outranks the layout tier (§7.3).
const modalColumns = computed(() => {
	const eligible = eligibleColumns.value
	if (Array.isArray(userColumns.value) && userColumns.value.length) {
		const byField = new Map(eligible.map((c) => [c.field, c]))
		const ordered = []
		const seen = new Set()
		for (const uc of userColumns.value) {
			const e = byField.get(uc.fieldname)
			if (!e) continue
			ordered.push({ fieldname: e.field, label: e.label, fieldtype: e.fieldtype, enabled: !!uc.enabled })
			seen.add(e.field)
		}
		for (const e of eligible) {
			if (!seen.has(e.field)) {
				ordered.push({ fieldname: e.field, label: e.label, fieldtype: e.fieldtype, enabled: false })
			}
		}
		return ordered
	}
	if (layoutColumns.value) {
		const ordered = []
		const seen = new Set()
		for (const c of layoutColumns.value) {
			ordered.push({ fieldname: c.field, label: c.label, fieldtype: c.fieldtype, enabled: true })
			seen.add(c.field)
		}
		for (const e of eligible) {
			if (!seen.has(e.field)) {
				ordered.push({ fieldname: e.field, label: e.label, fieldtype: e.fieldtype, enabled: false })
			}
		}
		return ordered
	}
	return eligible.map((e) => ({ fieldname: e.field, label: e.label, fieldtype: e.fieldtype, enabled: !!e.in_list_view }))
})

async function getUserColumns(dt) {
	try {
		const r = await callMethod(
			"yrp.yrp.doctype.user_listview.user_listview.get_user_listview",
			{ doctype_name: dt },
		)
		return Array.isArray(r) ? r : null
	} catch (_) {
		return null
	}
}

// After the user saves/reset columns: reload the saved config and re-create the
// list query (fields changed) while preserving the active tab/date/search filters.
async function onColumnsSaved() {
	showColumnsModal.value = false
	const dt = doctype.value
	if (!dt || !listState.value) return
	clearSelection()
	userColumns.value = await getUserColumns(dt)
	const prev = listState.value
	const next = useDocList(dt, {
		fields: fetchFields.value,
		defaultFilters: { ...prev.filters },
		orderBy: prev.currentOrderBy.value,
		pageSize,
		immediate: false,
	})
	if (prev.orFilters.value) next.setOrFilters(prev.orFilters.value)
	next.page.value = prev.page.value
	listState.value = next
	appliedQuerySig = variantQuerySig.value // rebuilt with the new columns — no double fetch
	next.fetch()
}

const fetchFields = computed(() => {
	const fields = ["name"]
	for (const c of listColumns.value) {
		if (!fields.includes(c.field)) fields.push(c.field)
	}
	// Card/kanban variants need their own key columns + title + group + status
	// sources. Guarded by the variant so the table's query stays IDENTICAL.
	if (listVariant.value !== "table") {
		for (const c of variantColumns.value) {
			if (!fields.includes(c.field)) fields.push(c.field)
		}
		if (variantTitleField.value && !fields.includes(variantTitleField.value)) {
			fields.push(variantTitleField.value)
		}
		if (kanbanGroupField.value && !fields.includes(kanbanGroupField.value)) {
			fields.push(kanbanGroupField.value)
		}
		if (metaFieldSet.value.has("status") && !fields.includes("status")) fields.push("status")
		if (!fields.includes("docstatus")) fields.push("docstatus")
	}
	if (isSubmittable.value && !fields.includes("docstatus")) fields.push("docstatus")
	if (isWorkflow.value && !fields.includes("workflow_state")) fields.push("workflow_state")
	return fields
})

const searchableFields = computed(() => {
	// name + any non-date column is a reasonable search target
	const f = ["name"]
	for (const c of listColumns.value) {
		if (c.type !== "Date" && c.type !== "Datetime" && c.type !== "Currency") {
			f.push(c.field)
		}
	}
	return f
})

// ── Route-query base filter (CUSTOM_UI §6.4 — implicit filter via URL) ──
// Queue cards / cross-doc links deep-link here with `?filters=<json>` where the
// JSON is an array of [field, op, value] triples. We parse it into a base
// filter that ANDs with EVERYTHING: it seeds the row query (via the list's
// defaultFilters) and is folded into baseFilters() so the per-tab counts also
// reflect the deep-linked context. It composes with — never replaces — the
// date-tab and status/docstatus-tab logic below.
//
// `routeBaseFilters` is a {field: value} object ready for getCount / setFilter,
// where value is either a scalar or an [op, value] pair. `routeBaseFields`
// tracks which keys we own so a query change can cleanly retract the old ones.
const routeBaseFilters = ref({})
const routeBaseFields = ref([])
const hasBaseFilter = computed(() => routeBaseFields.value.length > 0)

// Parse route.query.filters (a JSON array of [field, op, value]) into the
// {field: value} object form. Tolerant of junk: anything unparseable yields {}.
function parseRouteFilters() {
	const raw = route.query.filters
	if (!raw || typeof raw !== "string") return {}
	let arr
	try {
		arr = JSON.parse(raw)
	} catch (_) {
		return {}
	}
	if (!Array.isArray(arr)) return {}
	const obj = {}
	for (const t of arr) {
		if (!Array.isArray(t) || t.length < 2) continue
		const [field, op, value] = t
		if (typeof field !== "string" || !field) continue
		// 2-element triple [field, value] means equality; 3-element carries op.
		obj[field] = t.length >= 3 ? [op, value] : op
	}
	return obj
}

// A short, human label for the active base-filter chip. We don't try to render
// every operator — just signal that a context filter is in effect.
const baseFilterLabel = computed(() => {
	const n = routeBaseFields.value.length
	if (n === 0) return ""
	return n === 1 ? "Filtered" : `Filtered (${n})`
})

// ── Tab strip (meta-derived; CUSTOM_UI §6.3) ──
// tabMode is one of: "status", "docstatus", or null (no tab strip).
// statusTabs holds the rendered tabs: [{ label, value, count }]. For status
// mode `value` is the status string (or null for All); for docstatus mode it
// is the docstatus number-as-string ("0"/"1"/"2", or null for All).
const statusOptions = ref([])            // ordered, non-blank Select options of the `status` field
const tabMode = ref(null)
const statusTabs = ref([])
const activeTab = ref("all")
const activeDateTab = ref("all")
const searchQuery = ref("")
// Live-search debounce state (see onSearch + the searchQuery watch below).
let searchTimer = null
let lastSearched = ""
// `?status=<value>` deep-link: a status to preselect once tabs are built.
const pendingStatus = ref(null)

const DOCSTATUS_TABS = [
	{ label: "Draft", value: "0", docstatus: 0 },
	{ label: "Submitted", value: "1", docstatus: 1 },
	{ label: "Cancelled", value: "2", docstatus: 2 },
]

const dateTabOptions = [
	{ label: "Today", value: "today" },
	{ label: "This Week", value: "week" },
	{ label: "This Month", value: "month" },
	{ label: "All", value: "all" },
]

function getDateRange(tab) {
	const now = new Date()
	const fmt = (d) =>
		`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
	if (tab === "today") {
		const t = fmt(now)
		return [t, t]
	}
	if (tab === "week") {
		const day = now.getDay()
		const monday = new Date(now)
		monday.setDate(now.getDate() - ((day + 6) % 7))
		const sunday = new Date(monday)
		sunday.setDate(monday.getDate() + 6)
		return [fmt(monday), fmt(sunday)]
	}
	if (tab === "month") {
		const first = new Date(now.getFullYear(), now.getMonth(), 1)
		const last = new Date(now.getFullYear(), now.getMonth() + 1, 0)
		return [fmt(first), fmt(last)]
	}
	return null
}

const pageSize = 20
const listState = shallowRef(null)

// Live knob changes while the list is mounted (a knob / store refresh —
// HomeRecent's recentStyle watch precedent): the variant, its resolved column
// set, the kanban group field and the card title field all shape the row
// QUERY (fetchFields), so a change to ANY of them re-creates the list with the
// new fields while preserving filters/tabs/search/sort — same recipe as
// onColumnsSaved. Watching the joined signature (not just listVariant) means a
// layout edit that only changes groupBy/columns/titleField refetches too — a
// kanban whose groupBy moved would otherwise collapse to one "—" column
// because the new group field was never fetched. Never fires on layouts
// without the knobs (the signature only moves when a resolved input changes).
// `variantSyncDepth` guards the initList window: a route change resets +
// reloads meta, which can transiently flip the resolved inputs — initList
// builds the fresh listState itself, so the watcher must not recreate it from
// the OUTGOING doctype's state mid-flight. `appliedQuerySig` records the
// signature the current listState was built under, so a rebuild that already
// used the new inputs (initList, onColumnsSaved) doesn't refetch twice.
let variantSyncDepth = 0 // >0 → an initList pass is in flight (counter: passes overlap)
let appliedQuerySig = null // signature the current listState was created under
const variantQuerySig = computed(() =>
	[
		listVariant.value,
		fetchFields.value.join(","),
		kanbanGroupField.value,
		variantTitleField.value,
	].join("|"),
)
watch(variantQuerySig, (sig) => {
	if (variantSyncDepth > 0) return
	if (!doctype.value || !listState.value) return
	if (sig === appliedQuerySig) return // listState already carries these inputs
	appliedQuerySig = sig
	const prev = listState.value
	const next = useDocList(doctype.value, {
		fields: fetchFields.value,
		defaultFilters: { ...prev.filters },
		orderBy: prev.currentOrderBy.value,
		pageSize,
		immediate: false,
	})
	if (prev.orFilters.value) next.setOrFilters(prev.orFilters.value)
	if (prev.advancedFilters.value?.length) next.setAdvancedFilters(prev.advancedFilters.value)
	next.page.value = prev.page.value
	listState.value = next
	next.fetch()
})

// ── Realtime: live list updates (no popup) via Frappe `list_update` ──
const realtime = useRealtime()
let listRtDispose = null // disposer for the current doctype subscription
let listRtTimer = null // debounce timer for coalescing rapid changes
const pendingUpdates = ref(false) // changes arrived while a bulk selection is active

// Re-run the CURRENT query (preserves filters/tabs/search/sort/pagination) and
// refresh tab counts. Deliberately a full refetch, NOT an in-place row merge —
// a changed row may or may not belong to the current filtered/sorted/paged view.
function refreshListNow() {
	if (listRtTimer) { clearTimeout(listRtTimer); listRtTimer = null }
	pendingUpdates.value = false
	if (listState.value) listState.value.fetch()
	if (tabMode.value) loadCounts()
}

// list_update arrived: another user created/changed/removed a record in this
// doctype. If the user has a bulk selection active, don't yank the table — show
// a "New updates" pill and refresh once they clear the selection or tap it.
// Otherwise debounce (500ms) and refetch the current view.
function onListChanged() {
	if (selectedRows.value.length > 0) {
		pendingUpdates.value = true
		return
	}
	if (listRtTimer) clearTimeout(listRtTimer)
	listRtTimer = setTimeout(() => {
		listRtTimer = null
		// Re-check: the user may have started a bulk selection during the debounce
		// window — don't yank the table out from under it; defer to the pill.
		if (selectedRows.value.length > 0) {
			pendingUpdates.value = true
			return
		}
		if (listState.value) listState.value.fetch()
		if (tabMode.value) loadCounts()
	}, 500)
}

function subscribeListRealtime() {
	if (listRtDispose) { listRtDispose(); listRtDispose = null }
	pendingUpdates.value = false
	if (doctype.value) listRtDispose = realtime.onListUpdate(doctype.value, onListChanged)
}

// When a bulk selection clears, apply any updates that arrived while it was held.
watch(() => selectedRows.value.length, (n) => {
	if (n === 0 && pendingUpdates.value) refreshListNow()
})

// The implicit base the tab counts are scoped to, as a plain {field: value}
// object suitable for getCount. It folds together (a) the route-query base
// filter — so counts reflect the deep-linked context — and (b) the date-tab
// window. Search (or_filters) is excluded. Tabs add `status`/`docstatus` on top
// of this, so all three compose with AND.
function baseFilters() {
	const f = { ...routeBaseFilters.value }
	if (dateTabField.value) {
		const range = getDateRange(activeDateTab.value)
		if (range) f[dateTabField.value] = ["between", range]
	}
	return f
}

async function initList() {
	variantSyncDepth++
	try {
		await runInitList()
	} finally {
		variantSyncDepth--
	}
}

async function runInitList() {
	if (!doctype.value) {
		if (listRtDispose) { listRtDispose(); listRtDispose = null }
		listState.value = null
		appliedQuerySig = null
		meta.value = null
		statusOptions.value = []
		tabMode.value = null
		statusTabs.value = []
		userColumns.value = null
		return
	}
	activeTab.value = "all"
	activeDateTab.value = "all"
	searchQuery.value = ""
	lastSearched = ""
	advFilters.value = []
	filterChips.value = []
	clearSelection()
	bulkError.value = null
	showBulkEditDialog.value = false
	bulkEditFieldsFor.value = ""
	bulkEditFields.value = []
	bulkEditSelectedKey.value = ""
	bulkEditValue.value = null

	// Parse the route-query base filter up front so the very first fetch carries
	// it — seed it as the list's defaultFilters.
	const base = parseRouteFilters()
	routeBaseFilters.value = base
	routeBaseFields.value = Object.keys(base)

	// `?status=<value>` convenience: preselect that status tab once tabs exist.
	pendingStatus.value =
		typeof route.query.status === "string" ? route.query.status : null

	const dt = doctype.value
	// Load meta + the user's saved columns FIRST, so listColumns (and hence
	// fetchFields) is resolved before the row query runs.
	await loadMetaAndColumns(dt)
	if (dt !== doctype.value) return

	listState.value = useDocList(doctype.value, {
		fields: fetchFields.value,
		defaultFilters: base,
		orderBy: "modified desc",
		pageSize,
		immediate: true,
	})
	appliedQuerySig = variantQuerySig.value // this listState already carries the current inputs
	subscribeListRealtime()
	await loadTabCounts(dt)
}

// Fetch the DocType meta + the user's saved columns, and decide the tab mode.
// Runs BEFORE the row query so listColumns / fetchFields resolve first.
async function loadMetaAndColumns(dt) {
	meta.value = null
	statusOptions.value = []
	tabMode.value = null
	statusTabs.value = []
	userColumns.value = null
	try {
		const [docs, uc] = await Promise.all([getMeta(dt), getUserColumns(dt)])
		// Route changed while awaiting — abandon this stale result.
		if (dt !== doctype.value) return
		const parent = docs?.[0] || null
		meta.value = parent
		userColumns.value = uc
		const statusField = (parent?.fields || []).find(
			(f) => f.fieldname === "status"
		)
		// Read the `status` Select options from meta (used by status-mode tabs). On
		// this site that resolves to the yrp Work Order's actual option list, so the
		// tabs always match the live field — no hardcoding.
		const readStatusOptions = () =>
			statusField && statusField.fieldtype === "Select"
				? (statusField.options || "")
						.split("\n")
						.map((o) => o.trim())
						.filter((o) => o.length > 0)
				: []
		// OPT-IN override: a registry `tabMode` ('status' | 'docstatus' | 'workflow')
		// wins over the automatic workflow > submittable > status > all priority. This
		// lets a submittable doctype (e.g. Work Order) drive its tab strip from the
		// many-valued `status` Select field instead of the 3-state docstatus, while
		// Submit/Cancel keep working via the detail-page buttons.
		const override = registry.value?.tabMode || null
		if (override === "status") {
			tabMode.value = "status"
			statusOptions.value = readStatusOptions()
		} else if (override === "docstatus") {
			tabMode.value = "docstatus"
		} else if (override === "workflow") {
			tabMode.value = "workflow"
		} else if (isWorkflow.value) {
			// Workflow-managed → workflow_state tabs (Draft / Approval Pending /
			// Approved / Rejected / Expired). docstatus would collapse the three
			// docstatus-0 states (Draft + Approval Pending + Rejected) into one tab.
			tabMode.value = "workflow"
		} else if (isSubmittable.value) {
			// Submittable → docstatus tabs (All/Draft/Submitted/Cancelled). yrp does
			// NOT advance the `status` field on submit (a submitted PO still reads
			// status="Draft"), so docstatus is the trustworthy Draft/Submitted/Cancelled
			// signal and it matches the row's Status tag. (Status-field option tabs are
			// only for non-submittable doctypes — see below.)
			tabMode.value = "docstatus"
		} else if (statusField && statusField.fieldtype === "Select") {
			tabMode.value = "status"
			statusOptions.value = readStatusOptions()
		} else {
			// No status field and not submittable → still show a single All tab.
			tabMode.value = "all"
		}
	} catch (_) {
		// Meta failure must not break the list — degrade to workflow/docstatus tabs
		// (both sourced independently of meta) if applicable, else no tab strip.
		if (dt !== doctype.value) return
		tabMode.value = isWorkflow.value ? "workflow" : isSubmittable.value ? "docstatus" : null
	}
}

// Compute per-tab counts (after the list exists) + apply any ?status= deep-link.
async function loadTabCounts(dt) {
	if (!tabMode.value) return
	try {
		await loadCounts()
		if (dt !== doctype.value) return
		applyPendingStatus()
	} catch (_) {
		if (dt !== doctype.value) return
		if (tabMode.value === "docstatus") statusTabs.value = buildDocstatusTabs({})
		else if (tabMode.value === "workflow") statusTabs.value = buildWorkflowTabs(workflowStates.value, [])
		else if (tabMode.value === "all") statusTabs.value = [{ label: "All", value: null, count: 0 }]
		else {
			tabMode.value = null
			statusTabs.value = []
		}
	}
}

function buildDocstatusTabs(counts) {
	const all = DOCSTATUS_TABS.reduce(
		(sum, t) => sum + (counts[t.value] || 0),
		0
	)
	return [
		{ label: "All", value: null, count: all },
		...DOCSTATUS_TABS.map((t) => ({
			label: t.label,
			value: t.value,
			count: counts[t.value] || 0,
		})),
	]
}

// Workflow tabs: All + one per workflow_state (value === the state string).
// `counts` is positional, aligned 1:1 with `states`.
function buildWorkflowTabs(states, counts) {
	const total = counts.reduce((sum, c) => sum + (c || 0), 0)
	const tabs = [{ label: "All", value: null, count: total }]
	states.forEach((s, i) => {
		tabs.push({ label: s, value: s, count: counts[i] || 0 })
	})
	return tabs
}

// Recompute the per-tab counts via parallel getCount calls, scoped to the
// current date-tab filter. Returns nothing; writes statusTabs.
async function loadCounts() {
	const dt = doctype.value
	const base = baseFilters()
	// tab counts reflect the date-tab scope, not the live search (frappe.client.get_count ignores or_filters)

	if (tabMode.value === "status") {
		const opts = statusOptions.value
		const [allCount, ...optCounts] = await Promise.all([
			getCount(dt, { ...base }),
			...opts.map((opt) => getCount(dt, { ...base, status: opt })),
		])
		if (dt !== doctype.value) return
		const tabs = [{ label: "All", value: null, count: allCount }]
		opts.forEach((opt, i) => {
			// Every status option gets a tab (even count 0), in Select-option order.
			tabs.push({ label: opt, value: opt, count: optCounts[i] || 0 })
		})
		statusTabs.value = tabs
	} else if (tabMode.value === "docstatus") {
		const [d0, d1, d2] = await Promise.all([
			getCount(dt, { ...base, docstatus: 0 }),
			getCount(dt, { ...base, docstatus: 1 }),
			getCount(dt, { ...base, docstatus: 2 }),
		])
		if (dt !== doctype.value) return
		statusTabs.value = buildDocstatusTabs({
			0: d0 || 0,
			1: d1 || 0,
			2: d2 || 0,
		})
	} else if (tabMode.value === "workflow") {
		const states = workflowStates.value
		const counts = await Promise.all(
			states.map((s) => getCount(dt, { ...base, workflow_state: s })),
		)
		if (dt !== doctype.value) return
		statusTabs.value = buildWorkflowTabs(states, counts)
	} else if (tabMode.value === "all") {
		const c = await getCount(dt, { ...base })
		if (dt !== doctype.value) return
		statusTabs.value = [{ label: "All", value: null, count: c || 0 }]
	}
	// If the active tab no longer exists (its count hit 0), fall back to All.
	if (!statusTabs.value.some((t) => tabValueKey(t.value) === activeTab.value)) {
		activeTab.value = "all"
	}
}

// PrimeVue Tab `value` must be a stable primitive; null (the All tab) maps to
// the literal "all" so the active-tab binding round-trips cleanly.
function tabValueKey(value) {
	return value === null ? "all" : String(value)
}

// Apply a `?status=<value>` deep-link by selecting that status tab, but only in
// status mode and only if the value is a real, present status tab. Consumes the
// pending value either way so it fires at most once per load.
function applyPendingStatus() {
	const want = pendingStatus.value
	pendingStatus.value = null
	if (!want || tabMode.value !== "status" || !listState.value) return
	const tab = statusTabs.value.find((t) => t.value === want)
	if (!tab) return
	activeTab.value = tabValueKey(want)
	listState.value.setFilter("status", want)
	listState.value.fetch()
}

watch(() => props.docRoute, () => initList(), { immediate: true })

// Same-path query changes (e.g. one queue card → another, both on /work-order)
// do NOT remount the component or fire the docRoute watch, so re-apply the
// base filter here: retract the old route-base fields from the row query, fold
// the new ones in, recompute the tab counts (baseFilters() reads the new base),
// then refetch. Tabs/date-tabs that the user had picked are preserved.
watch(
	() => [route.query.filters, route.query.status],
	() => {
		if (!doctype.value || !listState.value) return
		clearSelection()
		bulkError.value = null
		const next = parseRouteFilters()
		// Drop the previous route-base fields we own, unless the new base also
		// sets them (setFilter will overwrite those below).
		for (const field of routeBaseFields.value) {
			if (!(field in next)) listState.value.removeFilter(field)
		}
		routeBaseFilters.value = next
		routeBaseFields.value = Object.keys(next)
		for (const [field, value] of Object.entries(next)) {
			listState.value.setFilter(field, value)
		}
		// Honor a same-path `?status=` change too (it re-selects the status tab).
		pendingStatus.value =
			typeof route.query.status === "string" ? route.query.status : null
		// Recompute counts against the new base, then refetch rows. If the active
		// tab's count drops to 0, loadCounts() falls the selection back to All;
		// mirror that into the row filter (same as onDateTabChange) before fetch.
		const apply = async () => {
			const prevActive = activeTab.value
			if (tabMode.value) await loadCounts()
			if (!listState.value) return
			if (tabMode.value && prevActive !== "all" && activeTab.value === "all") {
				// Fall back to the route-query base value (not nothing) so a base
				// constraint on status/docstatus is preserved.
				if (tabMode.value === "status") listState.value.setFilter("status", routeBaseFilters.value?.status ?? null)
				else if (tabMode.value === "workflow") listState.value.setFilter("workflow_state", routeBaseFilters.value?.workflow_state ?? null)
				else listState.value.setFilter("docstatus", routeBaseFilters.value?.docstatus ?? null)
			}
			applyPendingStatus()
			listState.value.fetch()
		}
		apply()
	}
)

const rows = computed(() => listState.value?.data.value || [])
const errorMsg = computed(() => listState.value?.error.value || null)
// U6: detect a permission/access error → show friendly copy + hide the (useless)
// search/Columns/Filter toolbar on a denied list.
const accessDenied = computed(() => {
	const m = String(errorMsg.value || "")
	return /insufficient permission|do not have|does not have|not permitted/i.test(m)
})
const canBulkEdit = computed(() => doctype.value && !accessDenied.value && canWrite(doctype.value))
const hasSubmitCancelBulkAction = computed(
	() => doctype.value && isSubmittable.value && !accessDenied.value && (canSubmit(doctype.value) || canCancel(doctype.value)),
)
const showBulkSelection = computed(
	() => doctype.value && !accessDenied.value && (canBulkEdit.value || hasSubmitCancelBulkAction.value),
)
const showBulkBar = computed(() => showBulkSelection.value && selectedRows.value.length > 0)
const totalCount = computed(() => {
	const c = listState.value?.totalCount.value
	return typeof c === "number" ? c : 0
})
const loading = computed(() => listState.value?.loading.value || false)
const page = computed(() => listState.value?.page.value || 1)

// key is the PrimeVue Tab value ("all" for the All tab, else the status string
// or docstatus number-string). Resolve it back to the real tab descriptor and
// apply the matching row filter.
function onTabChange(key) {
	activeTab.value = key
	if (!listState.value) return
	clearSelection()
	bulkError.value = null
	const tab = statusTabs.value.find((t) => tabValueKey(t.value) === key)
	const value = tab ? tab.value : null
	if (tabMode.value === "status") {
		// Clearing to All (value === null) restores the route-query base constraint
		// on `status` (if any) rather than deleting it — so a deep-link like
		// status:["not in",[...]] survives, keeping the chip truthful.
		listState.value.setFilter("status", value === null ? (routeBaseFilters.value?.status ?? null) : value)
	} else if (tabMode.value === "docstatus") {
		listState.value.setFilter("docstatus", value === null ? (routeBaseFilters.value?.docstatus ?? null) : Number(value))
	} else if (tabMode.value === "workflow") {
		listState.value.setFilter("workflow_state", value === null ? (routeBaseFilters.value?.workflow_state ?? null) : value)
	}
	listState.value.fetch()
}

async function onDateTabChange(value) {
	activeDateTab.value = value
	if (!listState.value) return
	clearSelection()
	bulkError.value = null
	if (dateTabField.value) {
		const range = getDateRange(value)
		if (range) {
			listState.value.setFilter(dateTabField.value, ["between", range])
		} else {
			listState.value.setFilter(dateTabField.value, null)
		}
	}
	// Recompute per-tab counts for the new date window. If the active tab's
	// count drops to 0, loadCounts() falls the selection back to All; mirror
	// that into the row filter before fetching.
	const prevActive = activeTab.value
	if (tabMode.value) await loadCounts()
	if (tabMode.value && prevActive !== "all" && activeTab.value === "all") {
		// Fall back to the route-query base value (not nothing) so a base
		// constraint on status/docstatus/workflow_state is preserved.
		if (tabMode.value === "status") listState.value.setFilter("status", routeBaseFilters.value?.status ?? null)
		else if (tabMode.value === "workflow") listState.value.setFilter("workflow_state", routeBaseFilters.value?.workflow_state ?? null)
		else listState.value.setFilter("docstatus", routeBaseFilters.value?.docstatus ?? null)
	}
	listState.value.fetch()
}

function onSearch() {
	if (searchTimer) {
		clearTimeout(searchTimer)
		searchTimer = null
	}
	if (!listState.value) return
	const q = searchQuery.value.trim()
	if (q === lastSearched) return // unchanged → skip a redundant fetch
	lastSearched = q
	clearSelection()
	bulkError.value = null
	if (q) {
		listState.value.setOrFilters(
			searchableFields.value.map((f) => [f, "like", `%${q}%`])
		)
	} else {
		listState.value.clearOrFilters()
	}
	listState.value.fetch()
}

// Live search: debounce keystrokes (300ms) so the list filters as you type.
// Enter (@keyup.enter) still fires onSearch immediately and cancels the pending
// debounce; a programmatic reset that doesn't change the query is skipped.
watch(searchQuery, () => {
	if (searchTimer) clearTimeout(searchTimer)
	searchTimer = setTimeout(() => {
		searchTimer = null
		onSearch()
	}, 300)
})

onBeforeUnmount(() => {
	if (searchTimer) clearTimeout(searchTimer)
	if (listRtTimer) { clearTimeout(listRtTimer); listRtTimer = null }
	if (listRtDispose) { listRtDispose(); listRtDispose = null }
})

// ── Interactive filter popover (FilterPanel) ──────────────────────────────
// FilterPanel emits the active filters as Frappe tuples + 1:1 display labels.
// We push the tuples into listState.advancedFilters and refetch; chips mirror
// the labels so each can be cleared individually.
function applyAdvFilters() {
	if (!listState.value) return
	clearSelection()
	bulkError.value = null
	listState.value.setAdvancedFilters(advFilters.value)
	listState.value.fetch()
}
function onApplyFilters(tuples, labels) {
	advFilters.value = tuples
	filterChips.value = labels
	applyAdvFilters()
}
function removeAdvFilter(i) {
	advFilters.value.splice(i, 1)
	filterChips.value.splice(i, 1)
	applyAdvFilters()
}
function clearAdvFilters() {
	advFilters.value = []
	filterChips.value = []
	applyAdvFilters()
}

function onPage(e) {
	if (listState.value) {
		clearSelection()
		bulkError.value = null
		listState.value.setPage(e.page + 1)
	}
}

function onRowClick(e) {
	const target = e?.originalEvent?.target
	if (target?.closest?.(".p-checkbox, .p-selection-column, button, a, input, textarea, select")) return
	const name = e?.data?.name
	if (!name) return
	captureNavContext()
	// detail knob active → open the record as an overlay on THIS route (pushed,
	// so browser Back closes it). Knob absent → today's full-page push exactly.
	if (overlayDetailActive.value) {
		router.push({ query: { ...route.query, detail: name } })
		return
	}
	router.push(`/${props.docRoute}/${encodeURIComponent(name)}`)
}

// Stash the resolved list query (filters + sort) so the detail page's prev/next
// arrows step through EXACTLY this list — same active tab (e.g. Submitted), same
// filters, same sort. Frappe v15 form-navigation parity. or_filters (search) is
// intentionally excluded (get_next ignores it, matching the Desk).
function captureNavContext() {
	if (!doctype.value || !listState.value) return
	const q = listState.value.resolvedQuery()
	captureListContext(doctype.value, {
		docRoute: props.docRoute,
		orderBy: q.orderBy,
		filters: q.filters,
	})
}

function onNew() {
	// dcEntry "inline-grid" (DC only): expand the embedded create panel above
	// the list — no overlay, no navigation. Already open → it just stays open.
	if (dcEntryVariant.value === "inline-grid") {
		inlineEntryOpen.value = true
		return
	}
	// entry knob "popup" (or dcEntry "size-matrix" → the host renders a bottom
	// sheet) → open the create form as an overlay on THIS route (?new=1;
	// pushed, so Back closes it). Knob absent/"page" → today's push.
	if (overlayEntryActive.value) {
		router.push({ query: { ...route.query, new: "1" } })
		return
	}
	router.push(`/${props.docRoute}/new`)
}

// Clear the implicit base filter by navigating to the same list route with no
// query. The query watcher above retracts the base-filter fields and refetches.
function clearBaseFilter() {
	router.push(`/${props.docRoute}`)
}

function openListInDesk() {
	if (doctype.value) {
		window.open(`/app/${encodeURIComponent(doctype.value.toLowerCase().replace(/ /g, "-"))}`, "_blank")
	}
}

function plural(n, singular, pluralWord = `${singular}s`) {
	return n === 1 ? singular : pluralWord
}

function bulkFailureLines(failures) {
	const lines = []
	for (const f of failures.slice(0, 8)) {
		const msg = f.message || errorLines(f.error).join(" ") || f.error?.message || "Failed"
		lines.push(`${f.name}: ${msg}`)
	}
	if (failures.length > 8) lines.push(`${failures.length - 8} more failed`)
	return lines
}

async function refreshAfterBulk() {
	clearSelection()
	if (listState.value) await listState.value.fetch()
	if (tabMode.value) await loadCounts()
}

async function loadBulkEditFields() {
	const dt = doctype.value
	if (!dt) return []
	if (bulkEditFieldsFor.value === dt && bulkEditFields.value.length) return bulkEditFields.value

	bulkEditLoading.value = true
	try {
		const fields = await getBulkEditFields(dt)
		if (dt !== doctype.value) return []
		bulkEditFields.value = fields
		bulkEditFieldsFor.value = dt
		const preferred = fields.find((field) => /status/i.test(field.fieldname || field.label || ""))
		const selected = preferred || fields[0]
		bulkEditSelectedKey.value = selected?.key || ""
		bulkEditValue.value = defaultBulkValue(selected)
		return fields
	} catch (error) {
		const lines = errorLines(error)
		bulkError.value = { title: "Could not load editable fields", lines: lines.length ? lines : ["Failed"] }
		toast.error("Could not load fields", lines[0] || error.message || "Failed")
		return []
	} finally {
		bulkEditLoading.value = false
	}
}

async function openBulkEditDialog() {
	if (!selectedRows.value.length) {
		toast.warn("No documents selected", "Select rows to edit.")
		return
	}
	bulkError.value = null
	showBulkEditDialog.value = true
	const fields = await loadBulkEditFields()
	if (!fields.length && doctype.value) {
		showBulkEditDialog.value = false
		toast.warn("No editable fields", "No writable fields are available for your permissions.")
	}
}

async function onBulkEditApply() {
	const field = bulkEditSelectedField.value
	const dt = doctype.value
	const docnames = selectedRows.value.map((row) => row.name).filter(Boolean)
	if (!dt || !field || !docnames.length) return

	bulkActing.value = "edit"
	bulkEditApplying.value = true
	bulkError.value = null
	try {
		const result = await bulkUpdateField(dt, docnames, field, bulkEditValue.value)
		const updated = Array.isArray(result?.updated) ? result.updated : []
		const failures = Array.isArray(result?.failures) ? result.failures : []
		await refreshAfterBulk()
		showBulkEditDialog.value = false

		if (failures.length) {
			const title = updated.length ? "Bulk edit partially failed" : "Bulk edit failed"
			bulkError.value = { title, lines: bulkFailureLines(failures) }
			toast.error(title, `${updated.length} updated, ${failures.length} failed`)
		} else {
			toast.success("Updated", `${updated.length} ${plural(updated.length, "record")} updated`, 6000)
		}
	} catch (error) {
		const lines = errorLines(error)
		bulkError.value = { title: "Bulk edit failed", lines: lines.length ? lines : [error.message || "Failed"] }
		toast.error("Bulk edit failed", lines[0] || error.message || "Failed")
	} finally {
		bulkActing.value = null
		bulkEditApplying.value = false
	}
}

async function runBulkAction(action, candidates) {
	const dt = doctype.value
	const rowsToActOn = [...candidates]
	if (!dt || !rowsToActOn.length) return
	const isSubmitAction = action === "submit"
	const verb = isSubmitAction ? "submit" : "cancel"
	const past = isSubmitAction ? "submitted" : "cancelled"
	bulkActing.value = action
	bulkError.value = null
	let ok = 0
	const failures = []
	try {
		for (const row of rowsToActOn) {
			try {
				if (isSubmitAction) await submitDoc(dt, row.name)
				else await cancelDoc(dt, row.name)
				ok += 1
			} catch (error) {
				failures.push({ name: row.name, error })
			}
		}
		await refreshAfterBulk()
		if (failures.length) {
			const title = ok ? `Bulk ${verb} partially failed` : `Bulk ${verb} failed`
			bulkError.value = { title, lines: bulkFailureLines(failures) }
			toast.error(title, `${ok} ${past}, ${failures.length} failed`)
		} else {
			toast.success(
				isSubmitAction ? "Submitted" : "Cancelled",
				`${ok} ${plural(ok, "document")} ${past}`,
				6000,
			)
		}
	} finally {
		bulkActing.value = null
	}
}

function onBulkSubmit() {
	const rowsToActOn = selectedDraftRows.value
	if (!rowsToActOn.length) {
		toast.warn("No draft documents", "Select draft rows to submit.")
		return
	}
	const count = rowsToActOn.length
	confirm.require({
		header: `Submit ${count} ${plural(count, "document")}`,
		message: `Submit ${count} selected draft ${registry.value?.label || doctype.value} ${plural(count, "document")}? This runs server validations and posts stock movements where applicable.`,
		acceptLabel: "Submit",
		acceptClass: "p-button-primary",
		accept: () => runBulkAction("submit", rowsToActOn),
	})
}

function onBulkCancel() {
	const rowsToActOn = selectedSubmittedRows.value
	if (!rowsToActOn.length) {
		toast.warn("No submitted documents", "Select submitted rows to cancel.")
		return
	}
	const count = rowsToActOn.length
	confirm.require({
		header: `Cancel ${count} ${plural(count, "document")}`,
		message: `Cancel ${count} selected submitted ${registry.value?.label || doctype.value} ${plural(count, "document")}? This can reverse stock movements and other submitted effects.`,
		acceptLabel: "Cancel Documents",
		acceptClass: "p-button-danger",
		rejectLabel: "Keep",
		accept: () => runBulkAction("cancel", rowsToActOn),
	})
}

// ── formatting + status helpers ──
function toDateObj(val) {
	if (!val) return null
	if (val instanceof Date) return val
	const [datePart, timePart] = String(val).split(" ")
	const [y, m, d] = datePart.split("-").map(Number)
	if (!y || !m || !d) return null
	let hh = 0, mm = 0, ss = 0
	if (timePart) {
		const [h, mi, se] = timePart.split(":").map(Number)
		hh = h || 0
		mm = mi || 0
		ss = se || 0
	}
	const obj = new Date(y, m - 1, d, hh, mm, ss)
	return Number.isNaN(obj.getTime()) ? null : obj
}

function fromDateObj(d, withTime) {
	if (!d) return ""
	const pad = (n) => String(n).padStart(2, "0")
	const date = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
	if (!withTime) return date
	return `${date} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

function formatDate(val) {
	if (!val) return "—"
	const datePart = String(val).split(" ")[0]
	const [y, m, d] = datePart.split("-")
	return y && m && d ? `${d}-${m}-${y}` : val
}

function formatNumber(val) {
	if (val === null || val === undefined || val === "") return "—"
	const n = Number(val)
	return Number.isNaN(n) ? val : n.toLocaleString("en-IN")
}

const DOCSTATUS_LABELS = { 0: "Draft", 1: "Submitted", 2: "Cancelled" }
function statusLabel(row) {
	if (isWorkflow.value && row.workflow_state) return row.workflow_state
	return row.status || DOCSTATUS_LABELS[row.docstatus] || "—"
}
function statusSeverity(ds) {
	if (ds === 1) return "success"
	if (ds === 2) return "danger"
	return "warn"
}
// Row-aware severity: workflow_state for workflow doctypes, else docstatus.
function rowSeverity(row) {
	if (isWorkflow.value && row.workflow_state) return WORKFLOW_SEVERITY[row.workflow_state] || "warn"
	return statusSeverity(row.docstatus)
}

// Q4: a 4px coloured left bar per row (green submitted / red cancelled pop above
// a neutral draft) so the lifecycle stage reads at a glance.
function rowClass(row) {
	if (!isSubmittable.value && !isWorkflow.value) return ""
	const sev = rowSeverity(row)
	return sev === "success" ? "row-good" : sev === "danger" ? "row-danger" : "row-warn"
}

// ── Q1: resolve Link cells to human names ──
function linkName(col, row) {
	const val = row[col.field]
	if (!val) return "—"
	const sibling = row[`${col.field}_name`]
	return linkTitles.linkParts(col.linkTarget, val, sibling).primary
}
// Batch-resolve the loaded rows' Link columns (skips already-cached values).
// The card/kanban variants resolve THEIR columns (+ title/group fields) —
// the table path primes listColumns exactly as before.
function primeListLinks() {
	let colsSrc = listColumns.value
	if (listVariant.value !== "table") {
		colsSrc = [...variantColumns.value]
		for (const extra of [titleColDesc.value, groupColDesc.value]) {
			if (extra && !colsSrc.some((c) => c.field === extra.field)) colsSrc.push(extra)
		}
	}
	const cols = colsSrc.filter((c) => c.isLink && c.linkTarget)
	if (!cols.length || !rows.value.length) return
	const pairs = []
	for (const row of rows.value) {
		for (const c of cols) {
			const v = row[c.field]
			if (v && !row[`${c.field}_name`]) pairs.push({ doctype: c.linkTarget, name: v })
		}
	}
	if (pairs.length) linkTitles.prime(pairs)
}
watch(rows, primeListLinks)

// Q14: only offer "Create the first …" when the empty list isn't just filtered.
const hasAnyFilter = computed(
	() => hasBaseFilter.value || advFilters.value.length > 0 || !!searchQuery.value.trim(),
)
</script>

<style scoped>
.list-page {
	display: flex;
	flex-direction: column;
	gap: 14px;
}

.page-head {
	display: flex;
	align-items: flex-start;
	gap: 16px;
}

.page-title {
	font-size: 24px;
	font-weight: 600;
	letter-spacing: -0.01em;
	margin: 0 0 var(--space-3);
	color: var(--esd-ink);
}

.page-sub {
	font-size: 12.5px;
	color: var(--esd-muted);
	margin: 2px 0 0;
}

.head-actions {
	margin-left: auto;
	display: flex;
	gap: 8px;
	align-items: center;
}

.date-tabs {
	display: flex;
	gap: 4px;
}

.date-tab {
	display: inline-flex;
	align-items: center;
	font-size: var(--fs-xs);
	min-height: var(--ctrl-h);   /* 38px touch-target floor (was 32px) */
	padding: 6px 14px;
	border-radius: 999px;
	color: var(--esd-muted);
	cursor: pointer;
	border: 1px solid transparent;
	background: transparent;
}

.date-tab.active {
	color: var(--esd-accent-700);
	background: var(--esd-accent-50);
	border-color: var(--esd-accent);
	font-weight: 600;
}

/* Per-tab count badge on the status/docstatus tab strip (slate by default,
   emerald accent on the active tab — consistent with the design tokens). */
.tab-count {
	margin-left: 6px;
	background: var(--esd-slate-50);
	color: var(--esd-muted);
	font-size: 11px;
	font-weight: 600;
	line-height: 1.4;
	padding: 1px 7px;
	border-radius: 999px;
}

:deep(.p-tab-active) .tab-count {
	background: var(--esd-accent-50);
	color: var(--esd-accent-700);
}

.esd-table {
	border: 1px solid var(--esd-line);
	border-radius: var(--radius);
	overflow: hidden;
	background: var(--esd-card);
}

/* Card/kanban variants: give the shared empty state the table's card frame. */
.variant-empty {
	border: 1px solid var(--esd-line);
	border-radius: var(--radius);
	background: var(--esd-card);
}

:deep(.esd-table .p-datatable-tbody > tr) {
	cursor: pointer;
}

/* Taller rows (~40px) for a comfortable touch target. */
:deep(.esd-table .p-datatable-tbody > tr > td) {
	padding-top: 11px;
	padding-bottom: 11px;
	font-size: 13px;
}

.list-error {
	margin: 0;
}

.bulk-error__title {
	font-weight: 700;
	margin-bottom: 4px;
}

.bulk-error__line {
	font-size: 13px;
	line-height: 1.45;
}

.bulk-bar {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 12px;
	padding: 10px 12px;
	border: 1px solid var(--esd-line);
	border-radius: var(--radius);
	background: var(--esd-card);
}

.bulk-bar__summary,
.bulk-bar__actions {
	display: flex;
	align-items: center;
	gap: 8px;
}

.bulk-count {
	font-size: 13px;
	font-weight: 700;
	color: var(--esd-ink);
}

.bulk-hint {
	font-size: 12px;
	font-weight: 600;
	color: var(--esd-muted);
	background: var(--esd-slate-50);
	border: 1px solid var(--esd-line);
	border-radius: 999px;
	padding: 2px 8px;
}

:deep(.esd-table .p-selection-column),
:deep(.esd-table .p-checkbox) {
	cursor: default;
}

.bulk-edit-form {
	display: flex;
	flex-direction: column;
	gap: 14px;
	padding-top: 2px;
}

.bulk-edit-selected {
	display: flex;
	align-items: center;
	gap: 8px;
}

.bulk-edit-field {
	display: flex;
	flex-direction: column;
	gap: 6px;
}

.field-label {
	font-size: 12px;
	font-weight: 700;
	color: var(--esd-ink-2);
}

.fld {
	width: 100%;
}

.fld-check {
	display: inline-flex;
	align-items: center;
	gap: 10px;
	min-height: 34px;
}

.check-label {
	font-size: 13px;
	font-weight: 600;
	color: var(--esd-ink-2);
}

.bulk-edit-help {
	margin: 0;
	font-size: 12px;
	line-height: 1.45;
	color: var(--esd-muted);
}

@media (max-width: 720px) {
	.bulk-bar {
		align-items: flex-start;
		flex-direction: column;
	}

	.bulk-bar__summary,
	.bulk-bar__actions {
		flex-wrap: wrap;
	}
}

/* Active base-filter chip (implicit URL filter). Slate pill + a clear ✕. */
.base-filter-row {
	display: flex;
}

.base-filter-chip {
	display: inline-flex;
	align-items: center;
	gap: 6px;
	background: var(--esd-slate-50);
	border: 1px solid var(--esd-line);
	border-radius: 999px;
	padding: 3px 6px 3px 12px;
	font-size: 12px;
	font-weight: 600;
	color: var(--esd-ink-2);
}

.base-filter-chip > i {
	font-size: 11px;
	color: var(--esd-muted);
}

/* Interactive filter chips (Filter popover) — reuse .chip-clear for the ✕. */
.adv-filter-row {
	display: flex;
	flex-wrap: wrap;
	gap: 6px;
	align-items: center;
	margin-top: 8px;
}

.adv-filter-chip {
	display: inline-flex;
	align-items: center;
	gap: 6px;
	background: var(--esd-slate-50);
	border: 1px solid var(--esd-line);
	border-radius: 999px;
	padding: 3px 6px 3px 12px;
	font-size: 12px;
	font-weight: 600;
	color: var(--esd-ink-2);
}

.adv-filter-clear {
	border: none;
	background: transparent;
	color: var(--esd-accent-700);
	font-size: 12px;
	font-weight: 600;
	cursor: pointer;
	padding: 3px 8px;
}

.adv-filter-clear:hover {
	text-decoration: underline;
}

.chip-clear {
	display: grid;
	place-items: center;
	width: 18px;
	height: 18px;
	border: none;
	border-radius: 999px;
	background: transparent;
	color: var(--esd-muted);
	cursor: pointer;
	transition: background 0.14s, color 0.14s;
}

.chip-clear:hover {
	background: var(--esd-line);
	color: var(--esd-ink);
}

.chip-clear i {
	font-size: 10px;
}

/* ════════════ UX quick-wins (2026-06-01) ════════════ */

/* Q4: status is the anchor — bolder tag + a 4px coloured left bar per row. */
.list-status.p-tag {
	font-size: 12px;
	font-weight: 700;
}
:deep(.esd-table .p-datatable-tbody > tr.row-good > td:first-child) {
	box-shadow: inset 4px 0 0 0 var(--esd-success);
}
:deep(.esd-table .p-datatable-tbody > tr.row-danger > td:first-child) {
	box-shadow: inset 4px 0 0 0 var(--esd-danger);
}
:deep(.esd-table .p-datatable-tbody > tr.row-warn > td:first-child) {
	box-shadow: inset 4px 0 0 0 var(--esd-muted-2);
}

/* Q8: trailing chevron affordance, brightening on row hover. */
.row-chevron {
	color: var(--esd-muted-2);
	font-size: 12px;
	transition: color 0.12s, transform 0.12s;
}
:deep(.esd-table .p-datatable-tbody > tr:hover) .row-chevron {
	color: var(--esd-accent);
	transform: translateX(2px);
}

/* dcEntry "inline-grid": collapsible embedded create panel above the list */
.dc-inline-entry {
	margin: 2px 0 14px;
	padding: 12px 16px 16px;
	background: var(--esd-card);
	border: 1px solid var(--esd-line);
	border-radius: 12px;
	box-shadow: var(--esd-shadow-sm);
}
/* Realtime "new updates" pill (only while a bulk selection blocks auto-refresh) */
.rt-pending {
	display: inline-flex;
	align-items: center;
	gap: 8px;
	margin: 0 0 10px;
	padding: 6px 12px;
	font-size: 12.5px;
	color: var(--esd-accent);
	background: var(--esd-accent-50, rgba(37, 99, 235, 0.08));
	border: 1px solid var(--esd-accent);
	border-radius: var(--radius-sm, 6px);
}
.rt-pending__btn {
	border: none;
	background: var(--esd-accent);
	color: #fff;
	font-size: 12px;
	font-weight: 600;
	padding: 3px 10px;
	border-radius: 5px;
	cursor: pointer;
}
.rt-pending__btn:hover {
	filter: brightness(0.95);
}
</style>
