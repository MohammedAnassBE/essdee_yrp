import { onBeforeUnmount, shallowRef, toValue, watch } from "vue"
import { useRoute } from "vue-router"

/** The title the mounted page reports for its path; App.vue writes it to document.title. */
export const reportedPageTitle = shallowRef(null)

/** Report the tab title as Desk does: the title field when set, else the name. No name (unsaved or loading) keeps the route title. */
export function usePageTitle(name, title = null) {
	const route = useRoute()
	const owner = {}
	watch(
		() => [toValue(name), toValue(title)],
		([nameValue, titleValue]) => {
			const text = nameValue ? String(titleValue || nameValue).trim() : ""
			reportedPageTitle.value = text ? { owner, path: route.path, title: text } : null
		},
		{ immediate: true },
	)
	onBeforeUnmount(() => {
		if (reportedPageTitle.value?.owner === owner) reportedPageTitle.value = null
	})
}
