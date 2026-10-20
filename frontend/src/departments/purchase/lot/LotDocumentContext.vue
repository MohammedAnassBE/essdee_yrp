<template>
	<template v-for="(part, index) in parts" :key="index"><template v-if="index"> · </template><DocumentLink v-if="part.name" doctype="Supplier" :name="part.name" :label="part.label" @click="stopLinkClick" /><template v-else>{{ part.label }}</template></template>
</template>

<script setup>
import { computed } from "vue"
import DocumentLink from "../../../components/common/DocumentLink.vue"

const props = defineProps({ doctype: { type: String, required: true }, row: { type: Object, required: true } })
function stopLinkClick(event) {
	if (event.target?.closest?.("a")) event.stopPropagation()
}
const parts = computed(() => [
	{ label: props.doctype === "Purchase Order" ? "" : props.row.process_name },
	{ label: props.row.supplier_name || props.row.supplier, name: props.row.supplier },
	{ label: props.row.is_return ? "Return" : "" },
].filter((part) => part.label))
</script>
