<template>
	<div v-if="notes.length" class="quality-calculation-notes">
		<Message v-for="note in notes" :key="note.key" :severity="note.severity" :closable="false" size="small">{{ note.text }}</Message>
	</div>
</template>

<script setup>
import Message from "primevue/message"
defineProps({ notes: { type: Array, default: () => [] } })
</script>
