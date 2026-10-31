<template>
	<section :id="`lot-section-${sectionKey}`" class="lot-section lot-collapsible" :class="{ 'is-open': expanded }" :data-section="sectionKey">
		<header>
			<button type="button" class="lot-collapsible__toggle" :aria-expanded="expanded" :aria-controls="bodyId" @click="emit('toggle')">
				<i :class="expanded ? 'pi pi-chevron-down' : 'pi pi-chevron-right'" aria-hidden="true" />
				<div><span>{{ eyebrow }}</span><h2>{{ label }}</h2></div>
			</button>
			<span v-if="count !== null" class="lot-count">{{ count }}</span>
		</header>
		<div v-if="expanded" :id="bodyId" class="lot-collapsible__body"><slot /></div>
	</section>
</template>
<script setup>
import { computed } from "vue"
const props = defineProps({
	sectionKey: { type: String, required: true },
	eyebrow: { type: String, default: "" },
	label: { type: String, required: true },
	count: { type: [Number, String], default: null },
	expanded: Boolean,
})
const emit = defineEmits(["toggle"])
const bodyId = computed(() => `lot-section-${props.sectionKey}-body`)
</script>
