<template>
	<div class="delivery-challan-workspace" :class="`delivery-challan-workspace--${presentation}`">
		<FabricDocumentWorkspace
			doctype="YRP Delivery Challan"
			title="Delivery Challan"
			:workspace="workspace"
			:presentation="presentation"
			:loading="loading"
			:error="error"
			:dirty="dirty"
			:acting="acting"
			:show-lifecycle-actions="false"
			:compact-mobile-rail="Boolean(workspace.record?.name)"
			@reload="load(true)"
			@action="runWorkspaceAction"
			@close="emit('closed')"
			@deleted="documentDeleted"
		>
			<template #header="{ record, headingId }">
				<div class="delivery-challan-header__identity" :class="{ 'delivery-challan-header__identity--embedded': presentation === 'embedded' }">
					<div v-if="presentation !== 'embedded'" class="delivery-challan-header__title"><h1 :id="headingId">Delivery Challan</h1><span>{{ record.name || duplicateLabel || (loading && name ? "Loading…" : error && name ? name : "New document") }}</span></div>
					<DocumentStatusBadge v-if="hasWorkspace && presentation !== 'embedded'" :docstatus="record.docstatus" :label="record.status || statusLabel(record.docstatus)" />
					<div v-if="headerFacts.length" class="delivery-challan-header__facts" role="region" aria-label="Delivery Challan context" tabindex="0">
						<div v-for="fact in headerFacts" :key="fact.label"><span>{{ fact.label }}</span><strong :title="String(fact.value)"><DocumentLink :doctype="fact.doctype" :name="fact.name" :label="fact.value" /></strong></div>
					</div>
				</div>
			</template>

			<template #header-actions>
				<DocumentActionStrip :actions="deliveryChallanActions" />
			</template>

			<template #fields>
				<p v-if="collapsedStockNotice" class="collapsed-stock-notice" :class="{ 'is-ticked': Number(form.allow_non_bundle || 0) }" role="status">{{ collapsedStockNotice }}</p>
				<DocumentFieldGroupGrid
					v-if="canEdit && visibleFields.length"
					:groups="primaryFieldGroups"
					:facts="!canEdit"
					aria-label="Delivery Challan fields"
					root-class="delivery-challan-fields"
					card-class="delivery-challan-field-group"
					content-class="delivery-challan-field-group__grid"
				>
					<template #default="{ group }">
						<template v-if="canEdit">
							<div v-for="field in group.fields" :key="fieldKey(field)" :class="{ 'form-field--wide': ['Small Text', 'Text', 'Long Text', 'Text Editor', 'Code'].includes(field.fieldtype) }">
								<FormField
									:field="field" :reset-version="field.fieldname === 'work_order' ? sourceFieldRevision : 0"
									:model-value="form[field.fieldname]"
									:form="form"
									:required="Boolean(field.reqd || field.mandatory)"
									compact
									:search-handler="linkSearchHandler(field)"
									@update:model-value="setField(field.fieldname, $event)"
								/>
								<small v-if="addressStatus[field.fieldname]?.message" class="delivery-challan-address-message" role="status">{{ addressStatus[field.fieldname].message }} <a :href="addressCreationUrl(addressStatus[field.fieldname])" target="_blank" rel="noopener">Create address</a></small>
							</div>
						</template>
						<template v-else>
							<div v-for="field in group.fields" :key="`fact-${field.fieldname}`" class="delivery-challan-field-fact">
								<span>{{ field.label }}</span><strong :title="String(formatFieldValue(field))">{{ formatFieldValue(field) }}</strong>
							</div>
						</template>
					</template>
				</DocumentFieldGroupGrid>
				<Tabs v-else-if="hasWorkspace" v-model:value="activeTab" class="delivery-challan-tabs erp-tabs">
					<TabList><Tab value="overview">Overview</Tab><Tab value="deliverables">Deliverables <span v-if="logicalRowCount(itemGroups)">{{ logicalRowCount(itemGroups) }}</span></Tab></TabList>
					<TabPanels>
						<TabPanel value="overview"><DocumentOverview :fields="overviewFields" :definitions="overviewDefinitions" include-unclaimed :unclaimed-definition="overviewAdditionalDefinition" aria-label="Delivery Challan overview" id-prefix="delivery-challan-overview" /></TabPanel>
						<TabPanel value="deliverables">
							<div class="delivery-challan-tab-matrices">
								<section v-for="block in matrixBlocks" :key="`readonly-${block.key}`" class="delivery-challan-tab-matrix">
									<header><div><span>{{ block.kind === 'items' ? 'Deliverables' : 'Corrections' }}</span><h2>{{ block.title }}</h2></div><strong>{{ logicalRowCount(block.groups) }} rows</strong></header>
									<StockItemMatrix :dimensions="workspace.dimensions || []" :groups="block.groups" doctype="YRP Delivery Challan" group-by-item show-lot-column show-fulfillment :show-received="false" />
								</section>
								<div v-if="!matrixBlocks.length" class="delivery-challan-matrix__empty"><i class="pi pi-inbox" /><span>No Delivery Challan item rows are available.</span></div>
							</div>
						</TabPanel>
					</TabPanels>
				</Tabs>
			</template>

			<template #secondary-fields>
				<DocumentFieldGroupGrid
					v-if="canEdit && secondaryFieldGroups.length"
					:groups="secondaryFieldGroups"
					:facts="!canEdit"
					wide-last-odd
					aria-label="Additional Delivery Challan fields"
					root-class="delivery-challan-fields delivery-challan-fields--secondary"
					card-class="delivery-challan-field-group"
					content-class="delivery-challan-field-group__grid"
				>
					<template #default="{ group }">
						<template v-if="canEdit">
							<FormField v-for="field in group.fields" :key="fieldKey(field)" :field="field" :reset-version="field.fieldname === 'work_order' ? sourceFieldRevision : 0" :model-value="form[field.fieldname]" :form="form" :required="Boolean(field.reqd || field.mandatory)" compact :search-handler="linkSearchHandler(field)" @update:model-value="setField(field.fieldname, $event)" />
						</template>
						<template v-else>
							<div v-for="field in group.fields" :key="`fact-${field.fieldname}`" class="delivery-challan-field-fact"><span>{{ field.label }}</span><strong :title="String(formatFieldValue(field))">{{ formatFieldValue(field) }}</strong></div>
						</template>
					</template>
				</DocumentFieldGroupGrid>
			</template>

			<template #matrix>
				<template v-if="canEdit">
				<section
					v-for="block in matrixBlocks"
					:key="block.key"
					class="delivery-challan-matrix"
					:class="`delivery-challan-matrix--${block.kind}`"
				>
					<header class="delivery-challan-matrix__header">
						<div><span>{{ block.kind === "items" ? "Deliverables" : "Corrections" }}</span><h2>{{ block.title }}</h2></div>
						<strong>{{ logicalRowCount(block.groups) }} rows</strong>
					</header>
					<div class="delivery-challan-matrix__stack">
						<article v-for="section in itemSections(block.groups)" :key="section.key" class="delivery-challan-matrix__group">
							<header>
								<div><strong><DocumentLink doctype="Item" :name="section.name" :label="section.name || 'Unspecified item'" /></strong></div>
								<label v-if="canEditMatrixBlock(block.kind)" class="delivery-challan-matrix__fill" :title="isTableFilled(section.items, primaryValues(section.group)) ? 'Untick to remove quantity' : 'Tick to fill pending quantity'"><Checkbox :model-value="isTableFilled(section.items, primaryValues(section.group))" binary :aria-label="`Fill quantity for ${section.name || 'item'}`" @update:model-value="fillTable(section, $event)" /><span>Fill quantity</span></label>
							</header>
							<div class="erp-table-wrap delivery-challan-matrix__scroll" tabindex="0" role="region" :aria-label="`Delivery quantities for ${section.name || 'item'}`">
								<table class="erp-data-table">
									<thead><tr>
										<th v-for="column in identityColumns(section.group)" :key="column.key">{{ column.label }}</th>
									<template v-if="hasPrimaryAttribute(section.group)"><th v-for="value in primaryValues(section.group)" :key="value" class="erp-number delivery-challan-matrix__quantity-heading">{{ value }}</th></template>
									<template v-else><th class="erp-number delivery-challan-matrix__pending-heading">Pending</th><th class="erp-number delivery-challan-matrix__quantity-heading">Deliver</th><th v-if="hasSecondaryQuantity(section.group)" class="erp-number">Secondary</th></template>
										<th>Comments</th><th class="erp-number">Total</th><th>UOM</th>
									</tr></thead>
									<tbody>
										<tr v-for="(row, rowIndex) in section.items" :key="rowKey(row, rowIndex)">
											<td v-for="column in identityColumns(section.group)" :key="column.key">{{ identityValue(row, column) }}</td>
										<template v-if="hasPrimaryAttribute(section.group)">
											<td v-for="value in primaryValues(section.group)" :key="value" class="erp-number delivery-challan-matrix__quantity delivery-challan-matrix__primary-cell">
												<InputNumber :model-value="row.values[value].qty" :aria-label="matrixInputLabel('Deliver', section, row, value)" :min="0" :max-fraction-digits="3" :disabled="!canEditMatrixBlock(block.kind)" fluid @update:model-value="setDisplayQuantity(row, value, $event)" />
												<small>Pending {{ formatQty(pendingQuantity(row.values[value])) }}</small>
												<div v-if="secondaryUom(row, value)" class="delivery-challan-matrix__secondary-inline"><InputNumber :model-value="row.values[value].secondary_qty" :aria-label="matrixInputLabel('Secondary quantity for', section, row, value, secondaryUom(row, value))" :min="0" :max-fraction-digits="3" :disabled="!canEditMatrixBlock(block.kind)" fluid @update:model-value="setDisplaySecondaryQuantity(row, value, $event)" /><span><DocumentLink doctype="UOM" :name="secondaryUom(row, value)" :label="secondaryUom(row, value)" /></span></div>
											</td>
										</template>
										<template v-else>
											<td class="erp-number delivery-challan-matrix__pending">{{ formatQty(pendingQuantity(row.values.default)) }}</td>
											<td class="erp-number delivery-challan-matrix__quantity"><InputNumber :model-value="row.values.default.qty" :aria-label="matrixInputLabel('Deliver', section, row, 'default')" :min="0" :max-fraction-digits="3" :disabled="!canEditMatrixBlock(block.kind)" fluid @update:model-value="setDisplayQuantity(row, 'default', $event)" /></td>
											<td v-if="hasSecondaryQuantity(section.group)" class="erp-number delivery-challan-matrix__secondary">
												<InputNumber :model-value="row.values.default.secondary_qty" :aria-label="matrixInputLabel('Secondary quantity for', section, row, 'default', secondaryUom(row, 'default'))" :min="0" :max-fraction-digits="3" :disabled="!canEditMatrixBlock(block.kind)" fluid @update:model-value="setDisplaySecondaryQuantity(row, 'default', $event)" /><small><DocumentLink doctype="UOM" :name="secondaryUom(row, 'default')" :label="secondaryUom(row, 'default')" /></small>
											</td>
										</template>
											<td><InputText :model-value="row.comments" aria-label="Row comments" :disabled="!canEditMatrixBlock(block.kind)" @update:model-value="setDisplayComment(row, $event)" /></td><td class="erp-number delivery-challan-matrix__total">{{ formatQty(rowTotal(row)) }}</td>
											<td><DocumentLink doctype="UOM" :name="row.default_uom || row.uom" :label="row.default_uom || row.uom || '—'" /></td>
										</tr>
									</tbody>
								</table>
							</div>
						</article>
					</div>
				</section>
					<div v-if="!matrixBlocks.length" class="delivery-challan-matrix__empty"><i class="pi pi-inbox" /><span>No Delivery Challan item rows are available.</span></div>
				</template>
			</template>

			<template #after-matrix>
				<div v-if="canEdit && afterMatrixFields.length" class="delivery-challan-after-matrix" aria-label="Delivery Challan final details">
					<template v-if="canEdit">
						<FormField v-for="field in afterMatrixFields" :key="`after-${fieldKey(field)}`" :field="field" :reset-version="field.fieldname === 'work_order' ? sourceFieldRevision : 0" :model-value="form[field.fieldname]" :form="form" :required="Boolean(field.reqd || field.mandatory)" compact :search-handler="linkSearchHandler(field)" @update:model-value="setField(field.fieldname, $event)" />
					</template>
					<template v-else>
						<div v-for="field in afterMatrixFields" :key="`after-fact-${field.fieldname}`" class="delivery-challan-after-matrix__fact"><span>{{ field.label }}</span><strong>{{ formatFieldValue(field) }}</strong></div>
					</template>
				</div>
			</template>

			<template #rail>
				<div class="delivery-challan-totals fabric-document-workspace__metric-group">
				<div
					v-for="total in visibleTotals"
					:key="total.fieldname"
					class="delivery-challan-total"
					:class="{ 'delivery-challan-total--primary': primaryTotals.has(total.fieldname) && totalIsPositive(total) }"
				>
					<span>{{ total.label }}</span><strong>{{ formatTotal(total) }}</strong>
					<small v-if="dirty && serverValueTotals.has(total.fieldname)" class="delivery-challan-total__hint">Updates on save</small>
				</div>
				</div>
				<div v-if="workspace.record?.is_internal_unit" class="delivery-challan-transfer-progress">
					<span>Internal transfer</span><strong>{{ transferPercent }}%</strong>
					<div><i :style="{ width: `${transferPercent}%` }" /></div>
					<small>{{ workspace.record.transfer_complete ? "Transfer complete" : "Completion pending" }}</small>
				</div>
			</template>

			<template #panel>
				<section v-if="workspace.special_source?.active" class="delivery-challan-special-context" aria-label="Source-managed Delivery Challan context">
					<header><span>Source-managed mode</span><strong>Prepared by the originating workflow</strong></header>
					<div><span v-for="mode in workspace.special_source.modes || []" :key="mode">{{ titleCase(mode) }}</span></div>
				</section>
			</template>
		</FabricDocumentWorkspace>

		<Dialog v-model:visible="returnOpen" modal header="Return Delivery Challan" class="fabric-action-dialog erp-dialog--lg" :closable="!acting">
			<DeliveryChallanReturnPanel :context="workspace.return_context || {}" :acting="acting" :error="returnError" @create="createReturn" @close="closeReturn" />
		</Dialog>
		<FabricStockOperationDialog v-model:visible="completionEntryOpen" operation="stock_entry" :name="completionEntryName" @changed="completionEntryChanged" />
		<RelatedDocumentWorkspaceDialog v-model:visible="createdReturnOpen" doctype="YRP Goods Received Note" :name="createdReturnName" @changed="createdReturnChanged" @closed="createdReturnOpen = false" />
		<DocumentConfirmationDialog v-model:visible="lifecycleConfirmVisible" :title="lifecycleConfirmTitle" :message="lifecycleConfirmMessage" :confirm-label="lifecycleConfirmLabel" :busy="Boolean(acting)" @confirm="confirmLifecycleAction" />
		<DocumentConfirmationDialog v-model:visible="sourceConfirmVisible" title="Change Work Order?" message="Changing the Work Order replaces the current source defaults and delivery quantities. Values entered for the current source will be discarded." cancel-label="Keep Current Work Order" confirm-label="Replace Source" :busy="acting === 'preview_source'" return-focus-selector="[id^='field-work_order-']" @update:visible="sourceConfirmationVisibilityChanged" @confirm="confirmSourceChange" />
	</div>
</template>

<script setup>
import DocumentLink from "../../components/common/DocumentLink.vue"
import { groupItemsForDisplay, setAggregatedCellQuantity, setAggregatedItemField } from "../../engine/stock/groupItemsForDisplay.js"
import InputText from "primevue/inputtext"
import Checkbox from "primevue/checkbox"
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import InputNumber from "primevue/inputnumber"
import Tab from "primevue/tab"
import TabList from "primevue/tablist"
import TabPanel from "primevue/tabpanel"
import TabPanels from "primevue/tabpanels"
import Tabs from "primevue/tabs"
import { useToast } from "primevue/usetoast"
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue"
import { useRouter } from "vue-router"

import {
	executeDeliveryChallanCommand,
	getDeliveryChallanWorkspace,
	getLocationAddressStatus,
	previewDeliveryChallanSource,
	saveDeliveryChallan,
} from "../../api/fabricStore.js"
import { searchLinkedDocument } from "../../api/frappe.js"
import { deliveredQuantity, isTableFilled, pendingQuantity, rowTotal, setTableQuantities } from "../../engine/stock/deliveryChallanTotals.js"
import { fillSupplierDefaults } from "../../utils/supplierDefaults.js"
import FormField from "../../components/common/FormField.vue"
import DocumentActionStrip from "../../components/documents/DocumentActionStrip.vue"
import DocumentConfirmationDialog from "../../components/documents/DocumentConfirmationDialog.vue"
import DocumentFieldGroupGrid from "../../components/documents/DocumentFieldGroupGrid.vue"
import DocumentOverview from "../../components/documents/DocumentOverview.vue"
import DocumentStatusBadge from "../../components/documents/DocumentStatusBadge.vue"
import StockItemMatrix from "../../components/stock/StockItemMatrix.vue"
import { hasDocumentDisplayValue, plainTextFromHtml } from "../../utils/documentValues.js"
import DeliveryChallanReturnPanel from "./DeliveryChallanReturnPanel.vue"
import FabricDocumentWorkspace from "./FabricDocumentWorkspace.vue"
import { useCollapsedStockGuard } from "./collapsedStock.js"
import FabricStockOperationDialog from "./FabricStockOperationDialog.vue"
import RelatedDocumentWorkspaceDialog from "./RelatedDocumentWorkspaceDialog.vue"

const props = defineProps({
	presentation: { type: String, default: "page" },
	name: { type: String, default: "" },
	sourceContext: { type: Object, default: () => ({}) },
	duplicateRouteName: { type: String, default: "fabric-delivery-challan-new" },
})
const emit = defineEmits(["changed", "closed"])
const router = useRouter()
const toast = useToast()

const loading = ref(true)
const acting = ref("")
const error = ref("")
const addressStatus = reactive({})
const dirty = ref(false)
const editingSubmitted = ref(false)
const workspace = ref({})
const currentName = ref("")
const itemGroups = ref([])
const correctionGroups = ref([])
const returnOpen = ref(false)
const returnError = ref("")
const activeTab = ref("overview")
const completionEntryOpen = ref(false)
const completionEntryName = ref("")
const createdReturnOpen = ref(false)
const createdReturnName = ref("")
const sourceFieldRevision = ref(0)
const lifecycleConfirmVisible = ref(false)
const pendingLifecycleCommand = ref("")
const sourceConfirmVisible = ref(false)
const pendingSourceWorkOrder = ref(null)
const form = reactive({})
let loadSequence = 0
let actionSequence = 0
const primaryTotals = new Set(["total_delivered_qty", "stock_value", "total_value"])
const serverValueTotals = new Set(["stock_value", "total_value"])
const headerFieldnames = new Set(["process_name", "item", "lot", "supplier_name", "from_location_name"])
const sourceOwnedFieldnames = new Set(["from_finishing", "cutting_bulk_lay_sheet", "cutting_bulk_lay_sheet_detail", "cut_panel_movement", "loose_piece_dc", "pack_piece_dc"])
const presentationHiddenFieldnames = new Set(["received_type"])
const afterMatrixFieldnames = new Set(["is_internal_unit", "includes_packing", "additional_goods_value", "ste_transferred", "ste_transferred_percent", "is_rework"])

const capabilities = computed(() => workspace.value.capabilities || {})
const deliveryChallanActions = computed(() => {
	const busy = Boolean(acting.value)
	const actions = []
	const add = (key, fallback, icon, command, menuOnly = false) => {
		if (!capabilities.value[key]) return
		actions.push({ key, label: capabilityLabel(key, fallback), icon, command, disabled: busy, loading: acting.value === key, menuOnly })
	}
	if (editingSubmitted.value) {
		actions.push({ key: "cancel_edit", label: "Cancel Edit", icon: "pi pi-times", command: cancelSubmittedEdit, disabled: busy })
		if (dirty.value) actions.push({ key: "save", label: "Save", icon: "pi pi-save", command: () => save(false), disabled: busy, loading: acting.value === "save", primary: true })
		return actions
	}
	add("complete_transfer", "Complete Transfer", "pi pi-check-circle", completeTransfer)
	add("return", "Return", "pi pi-replay", () => { returnOpen.value = true })
	if (canOfferSubmittedEdit.value) actions.push({ key: "edit", label: "Edit", icon: "pi pi-pencil", command: startSubmittedEdit, disabled: busy })
	if (!currentName.value || dirty.value) add("save", "Save", "pi pi-save", () => runWorkspaceAction("save"))
	if (currentName.value && !dirty.value) add("submit", "Submit", "pi pi-check", () => runWorkspaceAction("submit"))
	add("cancel", "Cancel Document", "pi pi-ban", () => runWorkspaceAction("cancel"), true)
	add("amend", "Amend", "pi pi-copy", () => runWorkspaceAction("amend"), true)
	if (currentName.value && workspace.value.permissions?.can_create && !workspace.value.special_source?.active) {
		actions.push({ key: "duplicate", label: "Duplicate", icon: "pi pi-clone", command: duplicateDeliveryChallan, disabled: busy, loading: acting.value === "duplicate", menuOnly: true })
	}
	const primaryKey = capabilities.value.complete_transfer ? "complete_transfer" : actions.some((action) => action.key === "submit") ? "submit" : actions.some((action) => action.key === "save") ? "save" : actions.some((action) => action.key === "amend") ? "amend" : ""
	return actions.map((action) => ({ ...action, primary: action.key === primaryKey }))
})
const hasWorkspace = computed(() => Boolean(Object.keys(workspace.value || {}).length))
const duplicateLabel = computed(() => props.sourceContext?.duplicate_from ? `Duplicate of ${props.sourceContext.duplicate_from}` : "")
const visibleTotals = computed(() => (workspace.value.totals || []).map((total) => {
	if (!canEdit.value) return total
	if (total.fieldname === "total_delivered_qty") return { ...total, value: deliveredQuantity(matrixBlocks.value) }
	if (total.fieldname === "additional_goods_value") return { ...total, value: form.additional_goods_value }
	return total
}).filter((total) => primaryTotals.has(total.fieldname) || totalIsPositive(total)))
const canEditDraft = computed(() => Boolean(
	Number(workspace.value.record?.docstatus || 0) === 0
	&& (currentName.value ? workspace.value.permissions?.can_write : workspace.value.permissions?.can_create),
))
const allowOnSubmitFields = computed(() => new Set(workspace.value.allow_on_submit_fields || []))
const canOfferSubmittedEdit = computed(() => Boolean(
	Number(workspace.value.record?.docstatus || 0) === 1
	&& workspace.value.permissions?.can_update_after_submit
	&& allowOnSubmitFields.value.size
	&& !workspace.value.special_source?.read_only,
))
const canEdit = computed(() => canEditDraft.value || editingSubmitted.value)
const { collapsedStockNotice } = useCollapsedStockGuard({
	enabled: () => canEditDraft.value,
	lot: () => form.lot,
	location: () => form.from_location,
	movement: () => form.cut_panel_movement || workspace.value.record?.cut_panel_movement,
	allowNonBundle: () => form.allow_non_bundle,
	setAllowNonBundle: (value) => setField("allow_non_bundle", value),
	doctypeLabel: "Delivery Challan",
	autoTick: true,
})
function canEditMatrixBlock(kind) {
	if (!canEdit.value || workspace.value.special_source?.read_only) return false
	if (!editingSubmitted.value) return true
	return allowOnSubmitFields.value.has(kind === "items" ? "items" : "correction_items")
}
const visibleFields = computed(() => {
	const result = new Map()
	for (const source of [...(workspace.value.fields || []), ...(workspace.value.dimensions || [])]) {
		if (!source?.fieldname || source.hidden || sourceOwnedFieldnames.has(source.fieldname) || presentationHiddenFieldnames.has(source.fieldname)) continue
		if (source.depends_on && !evaluateCondition(source.depends_on, true)) continue
		if (headerFieldnames.has(source.fieldname)) continue
		if (source.fieldname === "work_order" && currentName.value) continue
		if (result.has(source.fieldname)) continue
		const field = {
			...source,
			reqd: Boolean(source.reqd || source.mandatory || evaluateCondition(source.mandatory_depends_on)),
			read_only: Boolean(source.read_only || source.locked || evaluateCondition(source.read_only_depends_on)),
		}
		field.dependency_locked = Boolean(
			(["from_warehouse", "from_address"].includes(source.fieldname) && !form.from_location)
			|| (["to_warehouse", "supplier_address"].includes(source.fieldname) && !form.supplier),
		)
		field.read_only ||= field.dependency_locked
		if (source.fieldname === "from_warehouse") field.link_filters = { disabled: 0, supplier: form.from_location || "__unselected__" }
		if (source.fieldname === "to_warehouse") field.link_filters = { disabled: 0, supplier: form.supplier || "__unselected__" }
		if (!canEdit.value && !hasDocumentDisplayValue(form[source.fieldname] ?? source.value)) continue
		result.set(source.fieldname, field)
	}
	return [...result.values()].sort((left, right) => fieldOrder(left.fieldname) - fieldOrder(right.fieldname))
})
const fieldGroups = computed(() => {
	const groups = new Map(dcFieldGroups.map((group) => [group.key, { ...group, fields: [] }]))
	for (const field of visibleFields.value) {
		if (afterMatrixFieldnames.has(field.fieldname)) continue
		;(groups.get(fieldGroupKey(field.fieldname)) || groups.get("additional")).fields.push(field)
	}
	return [...groups.values()].filter((group) => group.fields.length)
})
const primaryFieldGroups = computed(() => fieldGroups.value.filter((group) => ["document", "movement"].includes(group.key)))
const secondaryFieldGroups = computed(() => fieldGroups.value.filter((group) => !["document", "movement"].includes(group.key)))
const afterMatrixFields = computed(() => visibleFields.value.filter((field) => afterMatrixFieldnames.has(field.fieldname)))
const overviewDefinitions = [
	{ key: "identity", label: "Document identity", description: "Source and production references", icon: "pi pi-id-card", fields: ["naming_series", "work_order", "purchase_order", "production_detail", "is_rework"] },
	{ key: "movement", label: "Movement", description: "Dispatch route and destination", icon: "pi pi-truck", fields: ["from_location", "from_location_name", "from_warehouse", "from_address", "supplier", "supplier_name", "to_warehouse", "supplier_address"] },
	{ key: "schedule", label: "Logistics", description: "Posting and transport information", icon: "pi pi-calendar", fields: ["posting_date", "posting_time", "actual_date", "vehicle_no", "supplier_document_no"] },
	{ key: "status", label: "Status & notes", description: "Dispatch controls and comments", icon: "pi pi-clipboard", fields: ["status", "includes_packing", "allow_non_bundle", "is_internal_unit", "transfer_complete", "letter_head", "comments"] },
]
const overviewAdditionalDefinition = { key: "additional", label: "Additional details", description: "Other dispatch information", icon: "pi pi-ellipsis-h", wide: true }
const overviewFields = computed(() => {
	const sources = [...(workspace.value.fields || []), ...(workspace.value.dimensions || [])]
	const fields = visibleFields.value.map((field) => ({ ...field, value: form[field.fieldname] ?? field.value }))
	const existing = new Set(fields.map((field) => field.fieldname))
	for (const fieldname of overviewDefinitions.flatMap((definition) => definition.fields)) {
		if (existing.has(fieldname)) continue
		const source = sources.find((field) => field.fieldname === fieldname)
		const value = form[fieldname] ?? source?.value ?? workspace.value.record?.[fieldname]
		if (!source || source.hidden || !hasDocumentDisplayValue(value)) continue
		fields.push({ ...source, value })
		existing.add(fieldname)
	}
	if (!existing.has("status")) fields.push({ fieldname: "status", label: "Status", fieldtype: "Data", value: workspace.value.record?.status || statusLabel(workspace.value.record?.docstatus) })
	return fields
})
const matrixBlocks = computed(() => {
	const blocks = []
	if (itemGroups.value.length) blocks.push({ key: "items", kind: "items", title: "Delivery quantities", groups: itemGroups.value })
	for (const [index, correction] of correctionGroups.value.entries()) {
		blocks.push({
			key: correction.work_order_correction || `correction-${index}`,
			kind: "corrections",
			title: correction.title || correction.work_order_correction || "Correction quantities",
			groups: correction.item_details || [],
		})
	}
	return blocks
})
const headerFacts = computed(() => [
	["Cut Panel Movement", workspace.value.record?.cut_panel_movement || form.cut_panel_movement, "SD YRP Cut Panel Movement"],
	["Source", workspace.value.record?.work_order || form.work_order, "YRP Work Order"],
	["Process", workspace.value.record?.process_name || form.process_name, "YRP Process"],
	["Item", workspace.value.record?.item || form.item, "Item"],
	["Lot", workspace.value.record?.lot || form.lot, "SD YRP Lot"],
].filter(([, value]) => value).map(([label, value, doctype]) => ({ label, value, doctype, name: value })))
const transferPercent = computed(() => Math.max(0, Math.min(100, Number(workspace.value.record?.ste_transferred_percent || (workspace.value.record?.transfer_complete ? 100 : 0)))))

async function load(refresh = false) {
	const sequence = ++loadSequence
	actionSequence += 1
	const requestedName = props.name || currentName.value
	const requestedRouteName = props.name
	const requestedSource = JSON.stringify(props.sourceContext || {})
	const requestedContext = clone(props.sourceContext || {})
	if (refresh) acting.value = "reload"
	else {
		loading.value = true
		clearWorkspaceState(requestedName)
	}
	error.value = ""
	try {
		const nextWorkspace = await getDeliveryChallanWorkspace(requestedName, requestedContext) || {}
		if (loadIsStale(sequence, requestedName, requestedRouteName, requestedSource)) return
		applyWorkspace(nextWorkspace)
	} catch (reason) {
		if (loadIsStale(sequence, requestedName, requestedRouteName, requestedSource)) return
		clearWorkspaceState(requestedName)
		error.value = reason?.message || "Unable to load this Delivery Challan."
	} finally {
		if (!loadIsStale(sequence, requestedName, requestedRouteName, requestedSource)) {
			loading.value = false
			acting.value = ""
		}
	}
}

function loadIsStale(sequence, requestedName, requestedRouteName, requestedSource) {
	return sequence !== loadSequence
		|| requestedRouteName !== props.name
		|| (Boolean(requestedRouteName) && requestedName !== props.name)
		|| requestedSource !== JSON.stringify(props.sourceContext || {})
}

function actionIsStale(sequence, requestedRouteName) {
	return sequence !== actionSequence || requestedRouteName !== props.name
}

function clearWorkspaceState(name = "") {
	workspace.value = {}
	currentName.value = name
	for (const key of Object.keys(form)) delete form[key]
	itemGroups.value = []
	correctionGroups.value = []
	dirty.value = false
	editingSubmitted.value = false
	returnOpen.value = false
	returnError.value = ""
	activeTab.value = "overview"
}

function applyWorkspace(nextWorkspace) {
	workspace.value = nextWorkspace || {}
	currentName.value = workspace.value.record?.name || ""
	for (const key of Object.keys(form)) delete form[key]
	Object.assign(form, clone(workspace.value.values || {}))
	for (const field of workspace.value.fields || []) {
		if (!(field.fieldname in form)) form[field.fieldname] = field.value
	}
	for (const dimension of workspace.value.dimensions || []) {
		if (!(dimension.fieldname in form)) form[dimension.fieldname] = dimension.value
	}
	if (!workspace.value.record?.name) {
		const defaults = currentPostingDefaults()
		if (!form.posting_date) form.posting_date = defaults.date
		if (!form.posting_time) form.posting_time = defaults.time
	}
	if (!form.from_location) {
		form.from_warehouse = ""
		form.from_address = ""
		form.from_address_details = ""
	}
	if (!form.supplier) {
		form.to_warehouse = ""
		form.supplier_address = ""
		form.supplier_address_details = ""
	}
	itemGroups.value = normalizeGroups(workspace.value.matrices?.items || workspace.value.item_groups || [])
	correctionGroups.value = clone(workspace.value.matrices?.correction_items || workspace.value.correction_item_groups || [])
	for (const correction of correctionGroups.value) correction.item_details = normalizeGroups(correction.item_details || [])
	dirty.value = false
	editingSubmitted.value = false
	error.value = ""
	returnOpen.value = false
	returnError.value = ""
	activeTab.value = "overview"
}

async function setField(fieldname, value) {
	if (editingSubmitted.value && !allowOnSubmitFields.value.has(fieldname)) return
	if ((value ?? "") === (form[fieldname] ?? "")) return
	if (fieldname === "work_order" && !currentName.value && value !== form.work_order) {
		if (dirty.value) {
			pendingSourceWorkOrder.value = value
			sourceConfirmVisible.value = true
			return
		}
		await applySourceChange(value)
		return
	}
	form[fieldname] = value
	if (fieldname === "supplier") {
		form.to_warehouse = ""
		form.supplier_address = ""
		form.supplier_address_details = ""
	}
	if (fieldname === "from_location") {
		form.from_warehouse = ""
		form.from_address = ""
		form.from_address_details = ""
	}
	if (["posting_date", "posting_time"].includes(fieldname)) form.edit_posting_date_and_time = 1
	markDirty()
	if (["supplier", "from_location"].includes(fieldname)) {
		const fields = fieldname === "supplier"
			? { addressField: "supplier_address", warehouseField: "to_warehouse" }
			: { addressField: "from_address", warehouseField: "from_warehouse" }
		try { await fillSupplierDefaults(form, { partyField: fieldname, ...fields, preferPrimary: true }) }
		catch (reason) { error.value = reason?.message || "Unable to load location defaults." }
	}
}
async function applySourceChange(value) {
	if (value) {
		await previewSource(value)
		return
	}
	for (const fieldname of [
		"work_order", "production_detail", "process_name", "item", "lot",
		"supplier", "supplier_name", "supplier_address", "supplier_address_details",
		"from_location", "from_location_name", "from_warehouse", "from_address", "from_address_details",
		"to_warehouse",
	]) form[fieldname] = ""
	itemGroups.value = []
	correctionGroups.value = []
	sourceFieldRevision.value += 1
	markDirty()
}
async function previewSource(value) {
	const sequence = ++actionSequence
	const requestedRouteName = props.name
	const request = { ...form, work_order: value }
	acting.value = "preview_source"
	error.value = ""
	try {
		const preview = await previewDeliveryChallanSource(value, request)
		if (actionIsStale(sequence, requestedRouteName)) return
		applyWorkspace(preview || {})
	} catch (reason) {
		if (actionIsStale(sequence, requestedRouteName)) return
		error.value = reason?.message || "Unable to refresh Delivery Challan defaults."
		sourceFieldRevision.value += 1
	} finally {
		if (!actionIsStale(sequence, requestedRouteName)) acting.value = ""
	}
}
async function confirmSourceChange() {
	const value = pendingSourceWorkOrder.value
	pendingSourceWorkOrder.value = null
	sourceConfirmVisible.value = false
	if (value !== null) await applySourceChange(value)
}
function sourceConfirmationVisibilityChanged(visible) {
	sourceConfirmVisible.value = visible
	if (visible || pendingSourceWorkOrder.value === null) return
	pendingSourceWorkOrder.value = null
	sourceFieldRevision.value += 1
}

async function runWorkspaceAction(action) {
	if (action === "save") return save(false)
	if (["submit", "cancel", "amend"].includes(action)) return requestLifecycleAction(action)
}

function startSubmittedEdit() {
	if (!canOfferSubmittedEdit.value) return
	editingSubmitted.value = true
	dirty.value = false
}

function cancelSubmittedEdit() {
	const snapshot = workspace.value
	applyWorkspace(snapshot)
}

function submittedUpdateValues() {
	const values = {}
	for (const fieldname of allowOnSubmitFields.value) {
		if (fieldname in form) values[fieldname] = clone(form[fieldname])
	}
	if (allowOnSubmitFields.value.has("items")) values.item_details = clone(itemGroups.value)
	if (allowOnSubmitFields.value.has("correction_items")) values.correction_item_details = clone(correctionGroups.value)
	return values
}

async function duplicateDeliveryChallan() {
	if (!currentName.value || !workspace.value.permissions?.can_create) return
	if (props.presentation === "page") {
		await router.push({ name: props.duplicateRouteName, query: { duplicate_from: currentName.value } })
		return
	}
	acting.value = "duplicate"
	error.value = ""
	const sequence = ++actionSequence
	const requestedRouteName = props.name
	const duplicateFrom = currentName.value
	try {
		const nextWorkspace = await getDeliveryChallanWorkspace("", { duplicate_from: duplicateFrom }) || {}
		if (actionIsStale(sequence, requestedRouteName)) return
		applyWorkspace(nextWorkspace)
		dirty.value = true
		emit("changed", workspace.value)
	} catch (reason) {
		if (actionIsStale(sequence, requestedRouteName)) return
		error.value = reason?.message || "Unable to duplicate this Delivery Challan."
	} finally {
		if (!actionIsStale(sequence, requestedRouteName)) acting.value = ""
	}
}

async function save(submit) {
	const sequence = ++actionSequence
	const requestedRouteName = props.name
	const requestedName = currentName.value
	acting.value = submit ? "submit" : "save"
	error.value = ""
	try {
		const values = editingSubmitted.value
			? submittedUpdateValues()
			: {
				...clone(form),
				item_details: clone(itemGroups.value),
				correction_item_details: clone(correctionGroups.value),
			}
		const saved = await saveDeliveryChallan(values, {
			name: requestedName,
			submit,
			expectedModified: workspace.value.record?.modified,
		})
		if (actionIsStale(sequence, requestedRouteName)) return
		applyWorkspace(saved || {})
		toast.add({ severity: "success", summary: submit ? "Delivery Challan submitted" : "Delivery Challan saved", detail: workspace.value.record?.name || "Your changes are saved.", life: 3500 })
		emit("changed", workspace.value)
	} catch (reason) {
		if (actionIsStale(sequence, requestedRouteName)) return
		error.value = reason?.message || `Unable to ${submit ? "submit" : "save"} this Delivery Challan.`
	} finally {
		if (!actionIsStale(sequence, requestedRouteName)) acting.value = ""
	}
}

async function runCommand(command, payload = {}, destructive = false) {
	if (!currentName.value) return
	const sequence = ++actionSequence
	const requestedRouteName = props.name
	const requestedName = currentName.value
	acting.value = command
	error.value = ""
	try {
		const result = await executeDeliveryChallanCommand(requestedName, command, payload, workspace.value.record?.modified)
		if (actionIsStale(sequence, requestedRouteName)) return null
		const updated = result?.workspace || result
		if (updated?.record) {
			applyWorkspace(updated)
			emit("changed", workspace.value)
		}
		return result
	} catch (reason) {
		if (actionIsStale(sequence, requestedRouteName)) return null
		error.value = reason?.message || `Unable to ${command.replaceAll("_", " ")} this Delivery Challan.`
		return null
	} finally {
		if (!actionIsStale(sequence, requestedRouteName)) acting.value = ""
	}
}
const lifecycleConfirmTitle = computed(() => pendingLifecycleCommand.value === "submit" ? "Submit Delivery Challan?" : pendingLifecycleCommand.value === "cancel" ? "Cancel Delivery Challan?" : "Amend Delivery Challan?")
const lifecycleConfirmLabel = computed(() => pendingLifecycleCommand.value === "submit" ? "Submit" : pendingLifecycleCommand.value === "cancel" ? "Cancel Delivery Challan" : "Create Amendment")
const completionCancellationMessage = computed(() => (workspace.value?.related?.completion_entries || []).filter(entry => Number(entry.docstatus) === 1).map(entry => ` This also cancels DC Completion ${entry.name}.`).join(""))
const lifecycleConfirmMessage = computed(() => pendingLifecycleCommand.value === "submit" ? `Permanently submit ${currentName.value}?` : pendingLifecycleCommand.value === "cancel" ? `Cancel ${currentName.value}? This keeps the document for audit and reverses its submitted effect.${completionCancellationMessage.value}` : `Create a new draft amendment from ${currentName.value}?`)
function requestLifecycleAction(command) { pendingLifecycleCommand.value = command; lifecycleConfirmVisible.value = true }
async function confirmLifecycleAction() { const command = pendingLifecycleCommand.value; lifecycleConfirmVisible.value = false; pendingLifecycleCommand.value = ""; if (command === "submit") await save(true); else if (command) await runCommand(command) }

async function createReturn(payload) {
	returnError.value = ""
	const result = await runCommand("return", payload)
	if (result?.workspace) {
		returnOpen.value = false
		if (result.created?.doctype === "YRP Goods Received Note" && result.created.name) {
			createdReturnName.value = result.created.name
			createdReturnOpen.value = true
		}
	}
	else if (error.value) returnError.value = error.value
}
function closeReturn() { returnOpen.value = false; returnError.value = "" }
async function completeTransfer() {
	const result = await runCommand("complete_transfer")
	if (result?.created?.doctype === "YRP Stock Entry" && result.created.name) {
		completionEntryName.value = result.created.name
		completionEntryOpen.value = true
	}
}
async function completionEntryChanged() {
	completionEntryOpen.value = false
	await load(true)
	emit("changed", workspace.value)
}
async function createdReturnChanged() {
	await load(true)
	emit("changed", workspace.value)
}
function fieldKey(field) { return `${field.fieldname}-${field.idx || "value"}` }
const dcFieldGroups = [
	{ key: "document", eyebrow: "Document", label: "Document & posting", description: "Series, source and posting controls." },
	{ key: "movement", eyebrow: "Route", label: "Source & receiver", description: "Choose the dispatch source and receiving destination." },
	{ key: "logistics", eyebrow: "Dispatch", label: "Transport details", description: "Capture vehicle and supplier references." },
	{ key: "controls", eyebrow: "Options", label: "Dispatch controls", description: "Additional dispatch handling options." },
	{ key: "transfer", eyebrow: "Status", label: "Internal transfer", description: "Internal transfer completion state." },
	{ key: "additional", eyebrow: "Additional", label: "Additional details", description: "Other permitted Delivery Challan fields." },
]
const dcGroupFields = {
	document: ["naming_series", "work_order", "purchase_order", "posting_date", "posting_time", "edit_posting_date_and_time", "actual_date", "production_detail", "allow_non_bundle"],
	movement: ["from_location", "from_warehouse", "from_address", "from_address_details", "supplier", "to_warehouse", "supplier_address", "supplier_address_details"],
	logistics: ["vehicle_no", "supplier_document_no", "letter_head", "comments"],
	controls: ["includes_packing", "additional_goods_value"],
	transfer: ["is_internal_unit", "transfer_complete", "ste_transferred", "ste_transferred_percent"],
}
const dcFieldOrder = Object.values(dcGroupFields).flat()
function fieldOrder(fieldname) { const index = dcFieldOrder.indexOf(fieldname); return index === -1 ? dcFieldOrder.length + 1 : index }
function fieldGroupKey(fieldname) { return Object.entries(dcGroupFields).find(([, fields]) => fields.includes(fieldname))?.[0] || "additional" }
function addressCreationUrl(status) {
	return `/desk/address/new?${new URLSearchParams({ essdee_supplier: status.party, address_title: status.supplier_name })}`
}
async function refreshAddressStatus() {
	await Promise.all([['from_address', 'from_location'], ['supplier_address', 'supplier']].map(async ([fieldname, partyField]) => {
		const party = form[partyField]
		delete addressStatus[fieldname]
		if (!party) return
		try {
			const status = await getLocationAddressStatus(party)
			if (form[partyField] === party) addressStatus[fieldname] = status
		} catch { /* Address search and save still report permission errors. */ }
	}))
}
watch(() => [form.from_location, form.supplier], refreshAddressStatus)

function linkSearchHandler(field) {
	if (field.fieldname === "from_address") return (text) => searchLinkedDocument("Address", "Supplier", form.from_location, text)
	if (field.fieldname === "supplier_address") return (text) => searchLinkedDocument("Address", "Supplier", form.supplier, text)
	return null
}
function markDirty() { if (!loading.value) dirty.value = true }
function capabilityLabel(name, fallback) { return name === "save" ? fallback : capabilities.value[name]?.label || fallback }
function statusLabel(docstatus) { return Number(docstatus) === 1 ? "Submitted" : Number(docstatus) === 2 ? "Cancelled" : "Draft" }
function evaluateCondition(condition, fallback = false) {
	if (!condition) return fallback
	const expression = String(condition).replace(/^eval:/, "").trim()
	const direct = expression.match(/^(!)?doc\.([A-Za-z0-9_]+)$/)
	if (direct) {
		const value = Boolean(conditionValue(direct[2]))
		return direct[1] ? !value : value
	}
	const comparison = expression.match(/^doc\.([A-Za-z0-9_]+)\s*(===|==|!==|!=)\s*['"]?([^'"]+)['"]?$/)
	if (!comparison) return fallback
	const equal = String(conditionValue(comparison[1]) ?? "") === comparison[3]
	return comparison[2].includes("!") ? !equal : equal
}
function conditionValue(fieldname) {
	return Object.prototype.hasOwnProperty.call(form, fieldname)
		? form[fieldname]
		: workspace.value.record?.[fieldname]
}
function primaryValues(group) { return group.primary_attribute_values?.length ? group.primary_attribute_values : ["default"] }
function hasPrimaryAttribute(group) { return Boolean(group.primary_attribute && primaryValues(group).some((value) => value !== "default")) }
function secondaryUom(row, value) { return String(row.values?.[value]?.secondary_uom || row.secondary_uom || "").trim() }
function hasSecondaryQuantity(group) { return (group.items || []).some((row) => primaryValues(group).some((value) => Boolean(secondaryUom(row, value)))) }
function logicalRowCount(groups) { return (groups || []).reduce((total, group) => total + (group.items?.length || 0), 0) }
function rowKey(row, index) { return [row.item_variant || row.name, row.row_index, row.received_type, row.delivery_challan_item, index].filter((value) => value !== undefined && value !== "").join("-") }
function matrixInputLabel(action, section, row, value, uom = "") {
	const item = section.name || row.item_variant || row.name || "item"
	const context = [...Object.values(row.attributes || {}), value === "default" ? "" : value].filter(Boolean)
	return `${action} ${item}${context.length ? `, ${context.join(", ")}` : ""}${uom ? ` in ${uom}` : ""}`
}
function formatQty(value) { return Number(value || 0).toLocaleString("en-IN", { maximumFractionDigits: 3 }) }
function formatTotal(total) { return Number(total.value || 0).toLocaleString("en-IN", { maximumFractionDigits: total.fieldname?.includes("value") ? 2 : 3 }) }
function totalIsPositive(total) { return Number(total?.value || 0) > 0 }
function formatFieldValue(field) {
	const value = form[field.fieldname] ?? field.value
	if (["Date", "Datetime"].includes(field.fieldtype)) {
		const match = String(value || "").match(/^(\d{4})-(\d{2})-(\d{2})(.*)$/)
		if (match) return `${match[3]}-${match[2]}-${match[1]}${field.fieldtype === "Datetime" ? match[4] : ""}`
	}
	if (field.fieldtype === "Check") return Number(value) ? "Yes" : "No"
	if (["Currency", "Float", "Int", "Percent"].includes(field.fieldtype)) return Number(value || 0).toLocaleString("en-IN", { maximumFractionDigits: 3 })
	return value === null || value === undefined || value === "" ? "—" : plainTextFromHtml(value)
}
function titleCase(value) { return String(value || "").replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase()) }
function clone(value) { return JSON.parse(JSON.stringify(value || {})) }
function normalizeGroups(groups) {
	const normalized = clone(groups || [])
	for (const group of normalized) {
		for (const row of group.items || []) {
			row.values ||= {}
			for (const value of primaryValues(group)) row.values[value] ||= { qty: 0 }
		}
	}
	return normalized
}
function setDisplayQuantity(row, value, quantity) { setAggregatedCellQuantity(row, value, quantity); markDirty() }
function fillTable(section, fill) { setTableQuantities(section.items, primaryValues(section.group), fill, setDisplayQuantity) }
function setDisplaySecondaryQuantity(row, value, quantity) { setAggregatedCellQuantity(row, value, quantity, "secondary_qty"); markDirty() }
function setDisplayComment(row, comment) { setAggregatedItemField(row, "comments", comment); markDirty() }
function itemSections(groups) {
	return groupItemsForDisplay(groups).flatMap((group, groupIndex) => {
		const sections = new Map()
		for (const row of group.items || []) {
			const name = row.name || row.item || row.item_variant || ""
			const lot = row.dimensions?.lot || row.lot || ""
			const key = `${groupIndex}-${name || "item"}-${lot}`
			if (!sections.has(key)) sections.set(key, { group, name, lot, key, items: [] })
			sections.get(key).items.push(row)
		}
		return [...sections.values()]
	})
}
function identityColumns(group) {
	const columns = (group.attributes || []).map((key) => ({ key, label: key, source: "attributes" }))
	const dimensions = []
	for (const row of group.items || []) {
		for (const key of Object.keys(row.dimensions || {})) if (key !== "lot" && !dimensions.includes(key)) dimensions.push(key)
	}
	for (const key of dimensions) columns.push({ key, label: titleCase(key), source: "dimensions" })
	return columns.filter((column, index, values) => values.findIndex((entry) => entry.key === column.key) === index)
}
function identityValue(row, column) {
	const value = column.source === "dimensions" ? row.dimensions?.[column.key] : row.attributes?.[column.key]
	return value === null || value === undefined || value === "" ? "—" : String(value)
}
function currentPostingDefaults() {
	const now = new Date()
	const pad = (value) => String(value).padStart(2, "0")
	return {
		date: `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`,
		time: `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`,
	}
}

onMounted(() => { load(); window.addEventListener("focus", refreshAddressStatus) })
onBeforeUnmount(() => window.removeEventListener("focus", refreshAddressStatus))
watch(() => [props.name, JSON.stringify(props.sourceContext || {})], ([name, source], previous) => {
	if (!previous || name === previous[0] && source === previous[1]) return
	loadSequence += 1
	actionSequence += 1
	clearWorkspaceState(name || "")
	load()
})
function documentDeleted() {
	emit("changed", { deleted: true })
	if (props.presentation === "embedded") emit("closed")
}
</script>

<style scoped>
.delivery-challan-address-message { display: block; margin-top: 6px; color: var(--erp-danger); }
.delivery-challan-address-message a { text-decoration: underline; }
.delivery-challan-workspace { width: 100%; min-width: 0; }
.delivery-challan-tabs :deep(.p-tabpanels) { padding: 12px 0 0; background: transparent; }
.delivery-challan-tabs :deep(.p-tablist-tab-list) { padding-inline: 2px; }
.delivery-challan-tabs :deep(.p-tab span) { margin-left: 5px; padding: 2px 6px; color: var(--erp-text-muted); background: var(--erp-surface-muted); border-radius: var(--erp-pill-radius); font-size: var(--erp-font-size-min); }
.delivery-challan-tab-matrices { display: grid; gap: var(--erp-space-3); }
.delivery-challan-tab-matrix { display: grid; gap: 8px; min-width: 0; }
.delivery-challan-tab-matrix > header { display: flex; align-items: end; justify-content: space-between; gap: 12px; padding: 0 2px; }
.delivery-challan-tab-matrix > header div { display: grid; gap: 2px; }
.delivery-challan-tab-matrix > header span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 750; letter-spacing: .035em; text-transform: uppercase; }
.delivery-challan-tab-matrix > header h2 { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-section); }
.delivery-challan-tab-matrix > header > strong { color: var(--erp-accent); font-size: var(--erp-font-size-min); }
.delivery-challan-after-matrix { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); align-items: end; gap: 10px 14px; padding: 2px; }
.delivery-challan-after-matrix__fact { display: grid; min-width: 0; gap: 3px; padding: 8px 2px; border-bottom: 1px solid var(--erp-border); }
.delivery-challan-after-matrix__fact span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 750; letter-spacing: .035em; text-transform: uppercase; }
.delivery-challan-after-matrix__fact strong { color: var(--erp-text); font-size: var(--erp-font-size-caption); line-height: 1.4; white-space: pre-line; overflow-wrap: anywhere; }
@media (max-width: 1100px) { .delivery-challan-after-matrix { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 700px) { .delivery-challan-after-matrix { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
.delivery-challan-workspace--page { padding-bottom: var(--erp-space-3); }
.delivery-challan-header__identity { display: flex; min-width: 0; align-items: center; gap: 12px; }
.delivery-challan-header__title { display: grid; min-width: 0; gap: 2px; }
.delivery-challan-header__identity h1 { margin: 0; color: var(--erp-text); font-size: 19px; line-height: 1.15; letter-spacing: -.018em; }
.delivery-challan-header__title > span { color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); font-weight: 700; }
.delivery-challan-header__facts { display: flex; min-width: 0; flex: 1; align-items: center; gap: 16px; padding-left: 13px; border-left: 1px solid var(--erp-border); }
.delivery-challan-header__facts > div { display: grid; min-width: 0; gap: 2px; flex: 0 1 auto; }
.delivery-challan-header__facts span, .delivery-challan-total span, .delivery-challan-transfer-progress > span, .delivery-challan-matrix__header span, .delivery-challan-special-context header span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 750; letter-spacing: .035em; text-transform: uppercase; }
.delivery-challan-header__facts strong { overflow: hidden; max-width: 180px; color: var(--erp-text); font-size: var(--erp-font-size-caption); text-overflow: ellipsis; white-space: nowrap; }
.delivery-challan-header__identity--embedded { width: 100%; overflow: hidden; }
.delivery-challan-header__identity--embedded .delivery-challan-header__facts { overflow-x: auto; flex-wrap: nowrap; padding-left: 0; border-left: 0; scrollbar-width: thin; }
.delivery-challan-header__identity--embedded .delivery-challan-header__facts > div { flex: 0 0 auto; }
.delivery-challan-field-fact { display: grid; min-height: 50px; align-content: center; gap: 4px; padding: 7px 10px; border-bottom: 1px solid color-mix(in srgb, var(--erp-border) 76%, var(--erp-surface)); }
.delivery-challan-field-fact span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 750; letter-spacing: .035em; text-transform: uppercase; }
.delivery-challan-field-fact strong { overflow: hidden; color: var(--erp-text); font-size: var(--erp-font-size-caption); text-overflow: ellipsis; white-space: nowrap; }
.delivery-challan-matrix { overflow: hidden; min-width: 0; border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); background: var(--erp-surface); box-shadow: none; }
.delivery-challan-matrix__header { display: flex; min-height: 48px; align-items: center; justify-content: space-between; gap: 12px; padding: 8px 12px; border-bottom: 1px solid var(--erp-border); background: var(--erp-surface-soft); }
.delivery-challan-matrix__header > div { display: grid; gap: 2px; }
.delivery-challan-matrix__header h2 { margin: 0; font-size: var(--erp-font-size-section); }
.delivery-challan-matrix__header > strong { padding: 3px 8px; color: var(--erp-accent); font-size: var(--erp-font-size-min); background: var(--erp-accent-soft); border-radius: var(--erp-pill-radius); }
.delivery-challan-matrix__stack { display: grid; gap: var(--erp-space-3); padding: var(--erp-space-3); background: color-mix(in srgb, var(--erp-surface-soft) 66%, var(--erp-surface)); }
.delivery-challan-matrix__group { overflow: hidden; min-width: 0; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); background: var(--erp-surface); box-shadow: none; }
.delivery-challan-matrix__group > header { display: flex; min-height: 40px; align-items: center; justify-content: space-between; gap: 12px; padding: 7px 10px; border-bottom: 1px solid var(--erp-border); }
.delivery-challan-matrix__group > header div { display: grid; gap: 2px; }
.delivery-challan-matrix__fill { display: inline-flex; align-items: center; gap: 6px; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); font-weight: 700; cursor: pointer; }
.delivery-challan-matrix__group > header strong { color: var(--erp-text); font-size: var(--erp-font-size-caption); }
.delivery-challan-matrix__group > header span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.delivery-challan-matrix__scroll table { min-width: 760px; }
.delivery-challan-matrix__pending-heading, .delivery-challan-matrix__pending { background: var(--erp-attention-soft); }
.delivery-challan-matrix__quantity-heading, .delivery-challan-matrix__quantity { background: var(--erp-accent-soft); }
.delivery-challan-matrix__pending { min-width: 78px; color: var(--erp-attention-text); font-weight: 750; }
.delivery-challan-matrix__quantity, .delivery-challan-matrix__secondary { min-width: 106px; }
.delivery-challan-matrix :deep(.p-inputnumber) { min-width: 94px; }
.delivery-challan-matrix :deep(.p-inputnumber-input) { height: 32px; padding: 5px 8px; text-align: right; }
.delivery-challan-matrix__secondary small { display: block; margin-top: 3px; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.delivery-challan-matrix__primary-cell > small { display: block; margin-top: 3px; color: var(--erp-attention-text); font-size: var(--erp-font-size-min); text-align: right; }
.delivery-challan-matrix__secondary-inline { display: grid; grid-template-columns: minmax(72px, 1fr) auto; align-items: center; gap: 5px; margin-top: 5px; }
.delivery-challan-matrix__secondary-inline span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.delivery-challan-matrix__total { color: var(--erp-accent); font-weight: 800; }
.delivery-challan-matrix__empty { display: grid; min-height: 140px; place-items: center; align-content: center; gap: 6px; color: var(--erp-text-muted); border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); background: var(--erp-surface); }
.delivery-challan-total, .delivery-challan-transfer-progress { display: grid; min-height: 58px; align-content: center; gap: 2px; padding: 9px 12px; border: 0; border-bottom: 1px solid var(--erp-border); border-radius: 0; background: var(--erp-surface); }
.delivery-challan-totals { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1px; background: var(--erp-border); }
.delivery-challan-totals .delivery-challan-total { min-height: 56px; border-bottom: 0; }
.delivery-challan-total:last-child, .delivery-challan-transfer-progress:last-child { border-bottom: 0; }
.delivery-challan-total__hint { color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
.delivery-challan-total strong, .delivery-challan-transfer-progress strong { color: var(--erp-text); font-size: 18px; font-weight: 780; font-variant-numeric: tabular-nums; }
.delivery-challan-total--primary { background: color-mix(in srgb, var(--erp-accent-soft) 76%, var(--erp-surface)); box-shadow: inset 3px 0 0 color-mix(in srgb, var(--erp-accent) 76%, var(--erp-surface)); }
.delivery-challan-total--primary strong { color: var(--erp-accent-hover); font-size: 21px; }
.delivery-challan-transfer-progress > div { overflow: hidden; height: 6px; background: var(--erp-border); border-radius: var(--erp-pill-radius); }
.delivery-challan-transfer-progress > div i { display: block; height: 100%; background: var(--erp-accent); transition: width .2s ease; }
.delivery-challan-transfer-progress small { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.delivery-challan-special-context { display: grid; overflow: hidden; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); background: var(--erp-surface); }
.delivery-challan-special-context header { display: flex; min-height: 42px; align-items: center; justify-content: space-between; gap: 12px; padding: 8px 12px; border-bottom: 1px solid var(--erp-border); background: var(--erp-surface-soft); }
.delivery-challan-special-context header strong { color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
.delivery-challan-special-context > div { display: flex; gap: 7px; padding: var(--erp-space-3); flex-wrap: wrap; }
.delivery-challan-special-context > div span { padding: 5px 9px; color: var(--erp-accent); font-size: var(--erp-font-size-caption); font-weight: 750; border: 1px solid var(--erp-accent-border); border-radius: var(--erp-pill-radius); background: var(--erp-accent-soft); }
@media (max-width: 1100px) { .delivery-challan-header__facts { overflow-x: auto; padding-right: 18px; flex-wrap: nowrap; scrollbar-width: thin; -webkit-mask-image: linear-gradient(to right, #000 0, #000 calc(100% - 18px), transparent 100%); mask-image: linear-gradient(to right, #000 0, #000 calc(100% - 18px), transparent 100%); } .delivery-challan-header__facts:focus-visible { outline: 2px solid var(--erp-accent); outline-offset: 2px; } .delivery-challan-header__facts > div { flex: 0 0 auto; } }
@media (max-width: 760px) { .delivery-challan-header__identity { align-items: flex-start; flex-wrap: wrap; } .delivery-challan-header__facts { width: 100%; flex: 1 0 100%; gap: 8px 14px; padding: 8px 18px 0 0; border-top: 1px solid var(--erp-border); border-left: 0; } .delivery-challan-header__identity--embedded { align-items: center; flex-wrap: nowrap; } .delivery-challan-header__identity--embedded .delivery-challan-header__facts { width: auto; padding-top: 0; border-top: 0; flex: 1 1 auto; } }
@media (max-width: 620px) { .delivery-challan-field-fact { min-height: 46px; padding: 6px 8px; } .delivery-challan-matrix__stack { padding: var(--erp-space-2); } }
:global(.fabric-action-dialog .p-dialog-content) { min-height: 0; }
@media (max-width: 620px) { :global(.fabric-action-dialog) { width: 100vw !important; height: 100dvh !important; max-height: 100dvh !important; margin: 0; border-radius: 0; } :global(.fabric-action-dialog .p-dialog-content) { flex: 1; overflow-y: auto; } }
.collapsed-stock-notice { margin: 0 0 var(--erp-space-3); padding: 8px 10px; color: var(--erp-text); font-size: var(--erp-font-size-caption); border-left: 3px solid var(--erp-warning, #d97706); background: color-mix(in srgb, var(--erp-warning, #d97706) 10%, var(--erp-surface)); }
.collapsed-stock-notice.is-ticked { border-left-color: var(--erp-accent); background: var(--erp-accent-soft); }
</style>
