<template>
	<LotMainTab :sections="sections" :expanded="expanded" :scroll-to="scrollTo" @update:expanded="emit('update:expanded', $event)">
		<template #header>
			<DocumentOverview v-if="headerGroups.length" :fields="fields" :definitions="LOT_HEADER_GROUPS" id-prefix="lot-header" aria-label="Lot details" :include-empty="includeEmpty" />
		</template>
		<template #quantities>
			<slot name="quantities-actions" />
			<LotOrderItemsTab v-if="workspace.order_items" :order-items="workspace.order_items" :pieces="workspace.order_pieces" />
			<LotEmptyState v-else title="No order quantities" reason="Choose an Item Production Detail to load box quantities." />
		</template>
		<template #order-details>
			<div class="lot-tab-stack">
				<slot name="order-details-actions" />
				<LotFacts :facts="workspaceFacts(fields, LOT_ORDER_DETAIL_FIELDS, includeEmpty)" aria-label="Order detail facts" />
				<LotOrderDetailsTab :order-details="workspace.order_details" />
			</div>
		</template>
		<template #transfer><LotFacts :facts="workspaceFacts(fields, LOT_TRANSFER_FIELDS, true)" aria-label="Transfer facts" /></template>
		<template #process-flow><LotProcessFlow :lot="workspace.name" :item="workspaceValues(fields).item || ''" :fabrics="workspace.fabrics || []" /></template>
	</LotMainTab>
</template>
<script setup>
import { computed } from "vue"
import DocumentOverview from "../../../components/documents/DocumentOverview.vue"
import { buildDocumentOverviewGroups } from "../../../utils/documentOverview.js"
import LotEmptyState from "./LotEmptyState.vue"
import LotFacts from "./LotFacts.vue"
import LotMainTab from "./LotMainTab.vue"
import LotOrderDetailsTab from "./LotOrderDetailsTab.vue"
import LotOrderItemsTab from "./LotOrderItemsTab.vue"
import LotProcessFlow from "./flow/LotProcessFlow.vue"
import {
	LOT_HEADER_GROUPS, LOT_ORDER_DETAIL_FIELDS, LOT_TRANSFER_FIELDS,
	hasLotTransfer, lotSections, orderDetailRowCount, workspaceFacts, workspaceValues,
} from "./lotLayout.js"
/** Read-only Summary tab. */
const props = defineProps({
	workspace: { type: Object, required: true },
	expanded: { type: Array, default: () => [] },
	scrollTo: { type: String, default: "" },
	includeEmpty: Boolean,
})
const emit = defineEmits(["update:expanded"])
const fields = computed(() => [...(props.workspace.header || []), ...(props.workspace.details || []), ...(props.workspace.ipd_facts || [])])
const headerGroups = computed(() => buildDocumentOverviewGroups(fields.value, LOT_HEADER_GROUPS, { includeEmpty: props.includeEmpty }))
const sections = computed(() => {
	const workspace = props.workspace
	const orderGroups = workspace.order_details?.groups || []
	return lotSections({
		"order-details": Boolean(workspace.order_details),
		transfer: hasLotTransfer(workspaceValues(fields.value)),
		"process-flow": Boolean(workspace.name),
	}, {
		"order-details": orderDetailRowCount(orderGroups),
	})
})
</script>
