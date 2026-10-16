<template>
	<div class="ordered-processes">
		<LinkField v-model="candidate" doctype="YRP Process" label="Add process" :show-open-button="false" show-clear />
		<ol v-if="modelValue.length" aria-label="Selected processes">
			<li v-for="(process, index) in modelValue" :key="process">
				<span>{{ process }}</span>
				<Button v-if="index > 0" icon="pi pi-arrow-up" text :aria-label="'Move ' + process + ' earlier'" @click="move(index, -1)" />
				<Button v-if="index < modelValue.length - 1" icon="pi pi-arrow-down" text :aria-label="'Move ' + process + ' later'" @click="move(index, 1)" />
				<Button icon="pi pi-times" text :aria-label="'Remove ' + process" @click="update(modelValue.filter((value) => value !== process))" />
			</li>
		</ol>
	</div>
</template>

<script setup>
import Button from "primevue/button"
import { ref, watch } from "vue"
import LinkField from "../../../components/common/LinkField.vue"
import { addProcess, moveProcess } from "./productionReportFilters.js"

const props = defineProps({ modelValue: { type: Array, default: () => [] } })
const emit = defineEmits(["update:modelValue"])
const candidate = ref("")
function update(values) { emit("update:modelValue", values) }
function move(index, direction) { update(moveProcess(props.modelValue, index, direction)) }
watch(candidate, (value) => {
	if (!value) return
	update(addProcess(props.modelValue, value))
	candidate.value = ""
})
</script>

<style scoped>
.ordered-processes { min-width: 0; }
ol { display: flex; flex-wrap: wrap; gap: var(--erp-space-2); list-style: none; padding: 0; margin: var(--erp-space-2) 0 0; }
li { display: inline-flex; align-items: center; gap: var(--erp-space-1); padding: 2px var(--erp-space-2); border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); background: var(--erp-surface); color: var(--erp-text); }
</style>
