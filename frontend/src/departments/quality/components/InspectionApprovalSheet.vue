<template>
	<figure v-if="src" class="quality-approval-sheet">
		<button type="button" class="quality-approval-sheet__thumbnail" aria-label="Zoom approval sheet" @click="visible = true">
			<img :src="src" alt="Quality approval sheet" />
		</button>
		<figcaption>Approval sheet</figcaption>
	</figure>
	<Dialog v-if="src" v-model:visible="visible" modal header="Approval sheet" class="quality-approval-dialog" :draggable="false">
		<img class="quality-approval-dialog__image" :src="src" alt="Quality approval sheet, full image" />
		<template #footer><a :href="src" target="_blank" rel="noopener">Open original <i class="pi pi-external-link" aria-hidden="true" /></a></template>
	</Dialog>
</template>

<script setup>
import Dialog from "primevue/dialog"
import { ref, watch } from "vue"
const props = defineProps({ src: { type: String, default: "" } })
const visible = ref(false)
watch(() => props.src, () => { visible.value = false })
</script>
