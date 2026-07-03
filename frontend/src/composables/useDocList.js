import { ref, reactive } from 'vue'
import { getList, getListView, getCount } from '@/api/client'

export function useDocList(doctype, options = {}) {
  const {
    fields = ['name'],
    defaultFilters = {},
    orderBy = 'creation desc',
    pageSize = 20,
    immediate = true
  } = options

  const data = ref([])
  const totalCount = ref(0)
  const loading = ref(false)
  const error = ref(null)
  const page = ref(1)
  const filters = reactive({ ...defaultFilters })
  const orFilters = ref(null)
  // Interactive filter-popover filters: Frappe 4-tuples [doctype, field, op, value],
  // where doctype may be a CHILD table. ANDed with the object filters above.
  const advancedFilters = ref([])
  const currentOrderBy = ref(orderBy)

  // Convert the {field: value} / {field: [op, val]} object form to Frappe tuples,
  // so it can be concatenated with advancedFilters into one list-form filter set.
  function objectFiltersToTuples(obj) {
    const out = []
    for (const [field, val] of Object.entries(obj)) {
      if (Array.isArray(val)) out.push([field, val[0], val[1]])
      else out.push([field, '=', val])
    }
    return out
  }

  // The exact filter param + order this list queries with: tuples when advanced
  // filters are present (so a filter's own doctype reaches get_list), else the
  // simpler object form. Exposed so callers (e.g. the detail page's prev/next
  // navigation) can step through the SAME set. or_filters (search) is excluded —
  // Frappe's get_next ignores it too, keeping stepping faithful to the Desk.
  function resolvedQuery() {
    const filters_ = advancedFilters.value.length
      ? [...objectFiltersToTuples(filters), ...advancedFilters.value]
      : { ...filters }
    return { filters: filters_, orderBy: currentOrderBy.value }
  }

  async function fetch() {
    loading.value = true
    error.value = null
    try {
      // When advanced filters are present, send Frappe list-form filters (tuples)
      // so a filter's own doctype (parent OR child table) reaches get_list, which
      // adds the child-table JOIN itself. With none, keep the simpler object form.
      const filterParam = resolvedQuery().filters
      // A child-table filter (tuple doctype !== this list's doctype) makes the
      // server LEFT JOIN the child table, emitting one row per matching child — so
      // de-duplicate parents with `distinct` on BOTH the list and the count.
      const needsDistinct = advancedFilters.value.some(
        (t) => Array.isArray(t) && t.length >= 4 && t[0] !== doctype
      )
      const params = {
        fields,
        filters: filterParam,
        order_by: currentOrderBy.value,
        limit_start: (page.value - 1) * pageSize,
        limit_page_length: pageSize
      }
      if (orFilters.value) params.or_filters = orFilters.value
      // Child-table filters need reportview.get (it honors `distinct`); the REST
      // list path silently ignores distinct and would return duplicated parents.
      const listResult = needsDistinct
        ? await getListView(doctype, params)
        : await getList(doctype, params)
      data.value = listResult.data || []
      // The REST list endpoint returns no total_count, so the count call provides
      // it (distinct- and or_filters-aware). If that throws, probe-fall-back from the
      // rows we DID get so the paginator still works instead of collapsing to 0 and
      // hiding pages that exist.
      let total = listResult.total_count
      try {
        total = await getCount(doctype, filterParam, orFilters.value, needsDistinct)
      } catch (_) {
        if (total === undefined || total === null) {
          const n = data.value.length
          total = (page.value - 1) * pageSize + n + (n === pageSize ? 1 : 0)
        }
      }
      totalCount.value = total ?? 0
    } catch (e) {
      error.value = e.message || 'Failed to fetch'
    } finally {
      loading.value = false
    }
  }

  function setFilter(key, value) {
    if (value === null || value === undefined || value === '') {
      delete filters[key]
    } else {
      filters[key] = value
    }
    page.value = 1
  }

  function removeFilter(key) {
    delete filters[key]
    page.value = 1
  }

  function clearFilters(preserveKeys = []) {
    for (const key of Object.keys(filters)) {
      if (!preserveKeys.includes(key)) delete filters[key]
    }
    page.value = 1
  }

  function setOrFilters(val) {
    orFilters.value = val
    page.value = 1
  }

  function clearOrFilters() {
    orFilters.value = null
  }

  function setAdvancedFilters(arr) {
    advancedFilters.value = Array.isArray(arr) ? arr : []
    page.value = 1
  }

  function clearAdvancedFilters() {
    advancedFilters.value = []
    page.value = 1
  }

  function setPage(p) {
    page.value = p
    fetch()
  }

  function setOrderBy(val) {
    currentOrderBy.value = val
    page.value = 1
    fetch()
  }

  function refresh() {
    fetch()
  }

  if (immediate) {
    fetch()
  }

  return {
    data,
    totalCount,
    loading,
    error,
    page,
    pageSize,
    filters,
    orFilters,
    advancedFilters,
    currentOrderBy,
    fetch,
    setFilter,
    removeFilter,
    clearFilters,
    setOrFilters,
    clearOrFilters,
    setAdvancedFilters,
    clearAdvancedFilters,
    setPage,
    setOrderBy,
    refresh,
    resolvedQuery
  }
}
