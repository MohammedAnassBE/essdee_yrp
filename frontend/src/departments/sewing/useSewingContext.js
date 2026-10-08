import { computed, inject, onUnmounted, provide, readonly, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"

const sewingContextKey = Symbol("sewing-context")

export function useSewingContext() {
	const inherited = inject(sewingContextKey, null)
	if (inherited) return inherited

	const route = useRoute()
	const router = useRouter()
	const supplier = computed(() => typeof route.query.supplier === "string" ? route.query.supplier : "")
	const requestGeneration = ref(0)
	let mounted = true

	function beginRequest() {
		return ++requestGeneration.value
	}

	function isCurrent(generation) {
		return mounted && generation === requestGeneration.value
	}

	function setSupplier(value) {
		const nextSupplier = typeof value === "string" ? value : ""
		if (supplier.value === nextSupplier) return Promise.resolve()
		// Invalidate immediately, including while router navigation is pending.
		beginRequest()
		return router.replace({
			path: route.path,
			query: { ...route.query, supplier: nextSupplier || undefined },
			hash: route.hash,
		})
	}

	watch(supplier, beginRequest, { flush: "sync" })
	onUnmounted(() => {
		mounted = false
		beginRequest()
	})
	const context = { supplier, setSupplier, requestGeneration: readonly(requestGeneration), beginRequest, isCurrent }
	provide(sewingContextKey, context)
	return context
}
