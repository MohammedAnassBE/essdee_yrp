<template>
	<div class="lot-tab-stack">
		<slot name="actions" />
		<section class="lot-section">
			<header><div><span>BOM</span><h2>Last BOM calculation</h2></div></header>
			<LotFacts :facts="workspaceFacts(fields, LOT_BOM_FIELDS, true)" aria-label="BOM facts" />
		</section>
		<slot><LotBomTab :bom="workspace.bom || {}" /></slot>
	</div>
</template>
<script setup>
import { computed } from "vue"
import LotBomTab from "./LotBomTab.vue"
import LotFacts from "./LotFacts.vue"
import { LOT_BOM_FIELDS, workspaceFacts } from "./lotLayout.js"
/** BOM tab: last calculation facts, then the BOM Summary and Additional Items (default slot overrides). */
const props = defineProps({ workspace: { type: Object, required: true } })
const fields = computed(() => [...(props.workspace.header || []), ...(props.workspace.details || [])])
</script>
