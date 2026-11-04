<template>
	<dl class="lot-facts" :aria-label="ariaLabel">
		<div v-for="fact in facts" :key="fact.key" class="lot-edit-fact">
			<dt>{{ fact.label }}</dt>
			<dd><DocumentLink v-if="fact.link" v-bind="fact.link" :label="fact.value" /><template v-else>{{ fact.value }}</template></dd>
		</div>
	</dl>
</template>
<script setup>
import DocumentLink from "../../../components/common/DocumentLink.vue"
defineProps({ facts: { type: Array, required: true }, ariaLabel: { type: String, required: true } })
</script>
