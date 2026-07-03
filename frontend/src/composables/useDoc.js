import { ref, readonly } from 'vue'
import {
  getDoc, createDoc, updateDoc, deleteDoc, submitDoc, cancelDoc, amendDoc, duplicateDoc,
  getMeta, getLinkedDocs, getDocInfo,
} from '@/api/client'

export function useDoc(doctype) {
  const doc = ref(null)
  const meta = ref(null)          // parent DocType meta (fields, title_field…)
  const metaBundle = ref(null)    // full getdoctype bundle: [parentMeta, ...childMetas]
  const linked = ref(null)        // { <LinkedDocType>: [rows] }
  const docInfo = ref(null)       // { comments, versions, communications… }
  const loading = ref(false)
  const metaLoading = ref(false)
  const linkedLoading = ref(false)
  const activityLoading = ref(false)
  const saving = ref(false)
  const error = ref(null)

  async function load(name) {
    loading.value = true
    error.value = null
    try {
      doc.value = await getDoc(doctype, name)
    } catch (e) {
      error.value = e.message || 'Failed to load'
    } finally {
      loading.value = false
    }
  }

  // Meta is cached per composable instance — fetched once per doctype. The
  // in-flight promise is shared (`metaPromise`) so concurrent callers — e.g.
  // DocDetail's loadMeta() + loadChildMetas() — collapse to ONE getdoctype
  // request. `metaBundle` keeps the FULL bundle ([parentMeta, ...childMetas]) so
  // a child-meta consumer can reuse it instead of refetching the same endpoint.
  let metaPromise = null
  async function loadMeta() {
    if (meta.value) return meta.value
    if (metaPromise) return metaPromise
    metaLoading.value = true
    metaPromise = (async () => {
      try {
        const bundle = await getMeta(doctype)
        metaBundle.value = bundle || []
        meta.value = bundle[0] || null
        return meta.value
      } catch (_) {
        meta.value = null
        return null
      } finally {
        metaLoading.value = false
        metaPromise = null
      }
    })()
    return metaPromise
  }

  async function loadLinked(name) {
    linkedLoading.value = true
    try {
      linked.value = await getLinkedDocs(doctype, name || doc.value?.name)
    } catch (_) {
      linked.value = {}
    } finally {
      linkedLoading.value = false
    }
  }

  async function loadActivity(name) {
    activityLoading.value = true
    try {
      docInfo.value = await getDocInfo(doctype, name || doc.value?.name)
    } catch (_) {
      docInfo.value = null
    } finally {
      activityLoading.value = false
    }
  }

  async function save(data, name = null) {
    saving.value = true
    error.value = null
    try {
      if (name || doc.value?.name) {
        const result = await updateDoc(doctype, name || doc.value.name, data)
        doc.value = result
        return result
      } else {
        const result = await createDoc(doctype, data)
        doc.value = result
        return result
      }
    } catch (e) {
      error.value = e.message || 'Failed to save'
      throw e
    } finally {
      saving.value = false
    }
  }

  async function remove(name = null) {
    saving.value = true
    error.value = null
    try {
      await deleteDoc(doctype, name || doc.value?.name)
      doc.value = null
    } catch (e) {
      error.value = e.message || 'Failed to delete'
      throw e
    } finally {
      saving.value = false
    }
  }

  async function submit(name = null) {
    saving.value = true
    error.value = null
    try {
      const result = await submitDoc(doctype, name || doc.value?.name, doc.value?.modified)
      doc.value = result
      return result
    } catch (e) {
      error.value = e.message || 'Failed to submit'
      throw e
    } finally {
      saving.value = false
    }
  }

  async function cancel(name = null) {
    saving.value = true
    error.value = null
    try {
      const result = await cancelDoc(doctype, name || doc.value?.name, doc.value?.modified)
      doc.value = result
      return result
    } catch (e) {
      error.value = e.message || 'Failed to cancel'
      throw e
    } finally {
      saving.value = false
    }
  }

  async function amend(name = null) {
    saving.value = true
    error.value = null
    try {
      const result = await amendDoc(doctype, name || doc.value?.name)
      return result
    } catch (e) {
      error.value = e.message || 'Failed to amend'
      throw e
    } finally {
      saving.value = false
    }
  }

  async function duplicate(name = null) {
    saving.value = true
    error.value = null
    try {
      const result = await duplicateDoc(doctype, name || doc.value?.name)
      return result
    } catch (e) {
      error.value = e.message || 'Failed to duplicate'
      throw e
    } finally {
      saving.value = false
    }
  }

  function reset() {
    doc.value = null
    error.value = null
  }

  return {
    doc,
    meta,
    metaBundle,
    linked,
    docInfo,
    loading: readonly(loading),
    metaLoading: readonly(metaLoading),
    linkedLoading: readonly(linkedLoading),
    activityLoading: readonly(activityLoading),
    saving: readonly(saving),
    error,
    load,
    loadMeta,
    loadLinked,
    loadActivity,
    save,
    remove,
    submit,
    cancel,
    amend,
    duplicate,
    reset
  }
}
