<template>
	<TemporalFieldBase v-bind="$attrs" mode="datetime" />
</template>

<script setup>
import TemporalFieldBase from "./TemporalFieldBase.vue"

defineOptions({ inheritAttrs: false })
</script>
