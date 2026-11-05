<template>
	<p class="pf-tone-legend">
		<span v-for="[tone, label] in TONE_LEGEND" :key="tone"><i :class="`pf-tone-${tone}`" />{{ label }}</span>
		<span class="pf-tone-legend__sep" />
		<span><b>Difference</b></span>
		<span v-for="[tone, label] in DIFFERENCE_LEGEND" :key="tone"><i :class="`pf-tone-${tone}`" />{{ label }}</span>
	</p>
</template>
<script setup>
import { DIFFERENCE_LEGEND, TONE_LEGEND } from "../../../../utils/lotProcessFlow.js"
</script>
