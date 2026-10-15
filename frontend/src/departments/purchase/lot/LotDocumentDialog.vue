<template>
	<Dialog
		:visible="visible"
		modal
		dismissable-mask
		maximizable
		:header="title"
		class="lot-document-dialog erp-entity-dialog erp-dialog--lg"
		@update:visible="emit('update:visible', $event)"
		@hide="emit('hide')"
	>
		<div class="lot-document-dialog__content">
			<div v-if="loading" class="lot-document-dialog__loading">
				<Skeleton v-for="index in 5" :key="index" height="3rem" />
			</div>
			<div
				v-else-if="error"
				class="lot-document-dialog__state lot-document-dialog__state--error"
				role="alert"
			>
				<i class="pi pi-exclamation-circle" aria-hidden="true" />
				<strong>{{ error }}</strong>
				<Button
					label="Retry"
					icon="pi pi-refresh"
					severity="secondary"
					outlined
					@click="load"
				/>
			</div>
			<template v-else-if="payload.record">
				<div class="lot-document-dialog__status-row">
					<div>
						<DocumentStatusBadge
							:docstatus="payload.record.docstatus"
							:label="payload.record.status"
						/>
						<strong>
							{{ payload.record.supplier_name || payload.record.supplier || "—" }}
						</strong>
					</div>
					<small>Updated {{ formatLotDate(payload.record.modified, true) }}</small>
				</div>
				<section class="lot-document-summary-strip" aria-label="Document totals">
					<div
						v-for="field in payload.summary"
						:key="field.fieldname"
						class="lot-document-summary-metric"
					>
						<span>{{ field.label }}</span>
						<strong>{{ formatLotSummaryValue(field, payload.record.currency) }}</strong>
					</div>
				</section>
				<section v-if="details.length" class="lot-document-detail-grid">
					<div
						v-for="field in details"
						:key="field.fieldname"
						:class="{ 'lot-document-detail-wide': field.fieldname === 'comments' }"
					>
						<span>{{ field.label }}</span>
						<DocumentStatusBadge
							v-if="['status', 'open_status'].includes(field.fieldname)"
							:label="field.value"
							:docstatus="payload.record.docstatus"
						/>
						<strong
							v-else
							:class="{ 'lot-document-detail-link': field.fieldtype === 'Link' }"
							:title="field.fieldtype === 'Link' ? field.value : formatField(field)"
						>
							{{ formatField(field) }}
						</strong>
					</div>
				</section>
				<section v-if="doctype === 'YRP Work Order'" class="lot-section">
					<header>
						<div>
							<span>Inputs</span>
							<h2>Deliverables</h2>
						</div>
						<span class="lot-count">
							{{ countLabel(payload.item_row_count, "row") }}
						</span>
					</header>
					<div v-if="payload.deliverables?.length" class="lot-section__body">
						<WorkOrderItemMatrix :groups="payload.deliverables" />
					</div>
					<LotEmptyState
						v-else
						title="No deliverables"
						reason="No deliverable quantities are recorded for this Work Order."
					/>
				</section>
				<StockItemMatrix
					v-else-if="doctype === 'Purchase Order' && payload.item_groups?.length"
					:groups="payload.item_groups"
					:doctype="doctype"
					:physical-row-count="payload.item_row_count"
					:currency="payload.record.currency || ''"
					group-by-item
					show-lot-column
					show-pricing
					show-fulfillment
					:show-received="false"
					:show-amount="false"
					pricing-before-fulfillment
				/>
				<StockItemMatrix
					v-else-if="payload.item_groups?.length"
					:groups="payload.item_groups"
					:doctype="doctype"
					:physical-row-count="payload.item_row_count"
					group-by-item
				/>
				<LotEmptyState
					v-else
					title="No items"
					reason="No item quantities are recorded for this document."
				/>
			</template>
		</div>
		<template #footer>
			<div class="lot-document-dialog__footer">
				<Button
					label="Close"
					severity="secondary"
					text
					@click="emit('update:visible', false)"
				/>
				<Button
					label="Open full document"
					icon="pi pi-external-link"
					severity="secondary"
					outlined
					@click="openFullDocument"
				/>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import Skeleton from "primevue/skeleton"
import { computed, ref, watch } from "vue"
import { useRouter } from "vue-router"
import { getLotDocument } from "../../../api/purchase.js"
import DocumentStatusBadge from "../../../components/documents/DocumentStatusBadge.vue"
import StockItemMatrix from "../../../components/stock/StockItemMatrix.vue"
import { webDocumentPath } from "../../../router/webDocumentRoutes.js"
import { formatDocumentOverviewValue } from "../../../utils/documentOverview.js"
import WorkOrderItemMatrix from "../../fabric-store/WorkOrderItemMatrix.vue"
import LotEmptyState from "./LotEmptyState.vue"
import {
	LOT_DOCUMENT_SECTIONS,
	countLabel,
	formatLotDate,
	formatLotSummaryValue,
	formatLotTime,
} from "./lotViews.js"

const props = defineProps({
	visible: Boolean,
	lot: { type: String, required: true },
	doctype: { type: String, default: "" },
	name: { type: String, default: "" },
})
const emit = defineEmits(["update:visible", "hide"])
const router = useRouter()
const loading = ref(false)
const error = ref("")
const payload = ref({})
let loadSequence = 0
const title = computed(
	() =>
		`${LOT_DOCUMENT_SECTIONS.find((section) => section.doctype === props.doctype)?.title || "Document"} · ${props.name}`,
)
const details = computed(() =>
	(payload.value.details || []).filter(
		(field) => field.value !== null && field.value !== undefined && field.value !== "",
	),
)
function formatField(field) {
	if (field.fieldtype === "Datetime") return formatLotDate(field.value, true)
	if (field.fieldtype === "Time") return formatLotTime(field.value)
	return field.display_value || formatDocumentOverviewValue(field)
}

async function load() {
	if (!props.visible || !props.name) return
	const sequence = ++loadSequence
	loading.value = true
	error.value = ""
	payload.value = {}
	try {
		const result = await getLotDocument(props.lot, props.doctype, props.name)
		if (sequence === loadSequence) payload.value = result
	} catch (reason) {
		if (sequence === loadSequence)
			error.value = reason?.message || "Unable to load this linked document."
	} finally {
		if (sequence === loadSequence) loading.value = false
	}
}
function openFullDocument() {
	router.push(webDocumentPath(props.doctype, props.name).replace(/^\/web(?=\/)/, ""))
	emit("update:visible", false)
}
watch(
	() => [props.visible, props.lot, props.doctype, props.name],
	([visible]) => {
		if (visible) load()
		else loadSequence += 1
	},
	{ immediate: true },
)
</script>
