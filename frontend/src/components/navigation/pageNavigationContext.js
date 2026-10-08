import { inject } from "vue"

export const pageNavigationKey = Symbol("essdee-page-navigation")

export function usePageNavigation() {
	return inject(pageNavigationKey, null)
}
