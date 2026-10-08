<template>
	<DepartmentPage
		v-if="presentation === 'page'"
		title="Goods Received Note"
		accent="#0a7f5a"
		:back-to="backTo"
		:back-label="backLabel"
		:show-title="false"
		flat
		full-width
		:inline-navigation="Boolean(documentName)"
		data-domain-root="goods-received-note-workspace"
	>
		<section class="fabric-goods-received-note-frame">
			<GoodsReceivedNoteWorkspace
				:name="documentName"
				:source-context="resolvedSourceContext"
				:duplicate-route-name="duplicateRouteName"
				@changed="workspaceChanged"
				@closed="emit('closed')"
			/>
		</section>
	</DepartmentPage>
	<GoodsReceivedNoteWorkspace
		v-else
		presentation="embedded"
		:name="documentName"
		:source-context="resolvedSourceContext"
		:duplicate-route-name="duplicateRouteName"
		@changed="workspaceChanged"
		@closed="emit('closed')"
	/>
</template>

<script setup>
import { computed } from "vue"
import { useRoute, useRouter } from "vue-router"

import DepartmentPage from "../components/DepartmentPage.vue"
import GoodsReceivedNoteWorkspace from "./fabric-store/GoodsReceivedNoteWorkspace.vue"

const props = defineProps({
	presentation: { type: String, default: "page" },
	name: { type: String, default: "" },
	sourceContext: { type: Object, default: () => ({}) },
	backTo: { type: String, default: "/fabric-store/work-orders" },
	backLabel: { type: String, default: "Work Orders" },
	viewRouteName: { type: String, default: "fabric-goods-received-note" },
	duplicateRouteName: { type: String, default: "fabric-goods-received-note-new" },
})
const emit = defineEmits(["changed", "closed"])
const route = useRoute()
const router = useRouter()

const documentName = computed(() => props.name || String(route.params.goodsReceivedNoteId || ""))
const resolvedSourceContext = computed(() => Object.keys(props.sourceContext || {}).length
	? props.sourceContext
	: compactSource(route.query))

async function workspaceChanged(workspace) {
	emit("changed", workspace)
	const name = workspace?.record?.name
	if (props.presentation === "page" && name && name !== route.params.goodsReceivedNoteId) {
		await router.replace({ name: props.viewRouteName, params: { goodsReceivedNoteId: name } })
	}
}
function compactSource(source) {
	return Object.fromEntries(
		["work_order", "purchase_order", "delivery_challan", "against", "against_id", "duplicate_from"]
			.filter((key) => source?.[key])
			.map((key) => [key, String(source[key])]),
	)
}
</script>

<style scoped>
.fabric-goods-received-note-frame { width: 100%; max-width: 1840px; min-width: 0; margin: 0 auto var(--erp-space-3); }
@media (max-width: 650px) { .fabric-goods-received-note-frame { margin-bottom: 0; } }
</style>
