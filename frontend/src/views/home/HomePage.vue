<!-- HomePage — thin ScreenRenderer shell (spec §7.2).

     The 589-line home was decomposed into the registered blocks
     (src/blocks/: home-greeting, home-queues, home-recent, home-quick-create);
     this shell only picks WHICH home screen to render:
       store.homeScreen (the active layout's screens.home)
       → compiled-in Default home (§12.3) when the config's home is empty
       → and the same fallback if ScreenRenderer itself ever throws
         (onErrorCaptured; per-block failures are already contained by
         BlockBoundary — this guards the renderer level only, §14 row 11). -->
<template>
	<div class="home">
		<ScreenRenderer :screen="screen" />
	</div>
</template>

<script setup>
import { computed, onErrorCaptured, ref } from "vue"
import { ScreenRenderer, useUiConfigStore } from "@yrp/web-engine"
import { fallbackConfig } from "@/config/defaultConfig"

const ui = useUiConfigStore()
const renderFailed = ref(false)

const screen = computed(() => {
	const home = renderFailed.value ? null : ui.homeScreen
	return home?.blocks?.length ? home : fallbackConfig.screens.home
})

onErrorCaptured((err) => {
	console.error("[essdee home] screen render failed — falling back to Default home:", err)
	if (renderFailed.value) return false // fallback failed too: stop, don't loop
	renderFailed.value = true
	return false
})
</script>

<style scoped>
.home {
	max-width: 1180px;
	margin: 0 auto;
	width: 100%;
}
/* Today's home rhythm: 18px between hero, queues and recent (was the blocks'
   own margins). The engine grid defaults to --space-4 (16px); pin it to the
   transcribed 18px so the decomposition stays pixel-identical. */
.home :deep(.yrp-screen-grid) {
	gap: 18px;
}
</style>
