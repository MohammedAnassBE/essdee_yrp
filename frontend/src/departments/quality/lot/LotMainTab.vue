<template>
	<div ref="root" class="lot-tab-stack lot-main">
		<slot name="header" />
		<slot name="quantities" />
		<LotCollapsibleSection
			v-for="section in sections"
			:key="section.key"
			:section-key="section.key"
			:eyebrow="section.eyebrow"
			:label="section.label"
			:count="section.count"
			:expanded="expanded.includes(section.key)"
			@toggle="emit('update:expanded', toggleSection(expanded, section.key))"
		>
			<slot :name="section.key" />
		</LotCollapsibleSection>
	</div>
</template>
<script setup>
import { nextTick, onMounted, ref, watch } from "vue"
import LotCollapsibleSection from "./LotCollapsibleSection.vue"
import { toggleSection } from "./lotLayout.js"
/** Lot tab layout: header, always-open Order Quantities, then collapsible sections that render on expand. */
const props = defineProps({
	sections: { type: Array, required: true },
	expanded: { type: Array, default: () => [] },
	scrollTo: { type: String, default: "" },
})
const emit = defineEmits(["update:expanded"])
const root = ref(null)
async function scrollToSection(key) {
	if (!key) return
	await nextTick()
	root.value?.querySelector(`[data-section="${key}"]`)?.scrollIntoView?.({ block: "start" })
}
onMounted(() => scrollToSection(props.scrollTo))
watch(() => props.scrollTo, scrollToSection)
</script>
