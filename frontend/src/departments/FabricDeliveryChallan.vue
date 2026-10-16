<template>
	<DepartmentPage
		v-if="presentation === 'page'"
		title="Delivery Challan"
		:back-to="backTo"
		:back-label="backLabel"
		:show-title="false"
		flat
		full-width
		:inline-navigation="Boolean(documentName)"
		data-domain-root="delivery-challan-workspace"
	>
		<section class="fabric-delivery-challan-frame">
			<DeliveryChallanWorkspace
				:name="documentName"
				:source-context="resolvedSourceContext"
				:duplicate-route-name="duplicateRouteName"
				@changed="workspaceChanged"
				@closed="emit('closed')"
			/>
		</section>
	</DepartmentPage>
	<DeliveryChallanWorkspace
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
import { preserveListNavigationState } from "../router/listDocumentNavigation.js"
import DeliveryChallanWorkspace from "./fabric-store/DeliveryChallanWorkspace.vue"

const props = defineProps({
	presentation: { type: String, default: "page" },
	name: { type: String, default: "" },
	sourceContext: { type: Object, default: () => ({}) },
	backTo: { type: String, default: "/fabric-store/work-orders" },
	backLabel: { type: String, default: "Work Orders" },
	viewRouteName: { type: String, default: "fabric-delivery-challan" },
	duplicateRouteName: { type: String, default: "fabric-delivery-challan-new" },
})
const emit = defineEmits(["changed", "closed"])
const route = useRoute()
const router = useRouter()

const documentName = computed(() => props.name || String(route.params.deliveryChallanId || ""))
const resolvedSourceContext = computed(() => Object.keys(props.sourceContext || {}).length
	? props.sourceContext
	: compactSource(route.query))

async function workspaceChanged(workspace) {
	emit("changed", workspace)
	const name = workspace?.record?.name
	if (props.presentation === "page" && name && name !== route.params.deliveryChallanId) {
		await router.replace({ name: props.viewRouteName, params: { deliveryChallanId: name }, state: preserveListNavigationState(name) })
	}
}
function compactSource(source) {
	return Object.fromEntries(
		["work_order", "purchase_order", "delivery_challan", "duplicate_from"]
			.filter((key) => source?.[key])
			.map((key) => [key, String(source[key])]),
	)
}
</script>

<style scoped>
.fabric-delivery-challan-frame { width: 100%; min-width: 0; margin: 0 0 var(--erp-space-3); }
@media (max-width: 650px) { .fabric-delivery-challan-frame { margin-bottom: 0; } }
</style>
