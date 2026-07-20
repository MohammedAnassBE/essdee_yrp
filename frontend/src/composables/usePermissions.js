import { ref, computed } from 'vue'
import { noWebCreate } from '@/config/doctypes'

// Singleton reactive state (shared across all components)
const _canRead = ref([])
const _canCreate = ref([])
const _canWrite = ref([])
const _canDelete = ref([])
const _canSubmit = ref([])
const _canCancel = ref([])
const _isAdmin = ref(false)
const _roles = ref([])
const _loaded = ref(false)

function loadPermissions() {
  const bootUser = window.frappe?.boot?.user
  if (!bootUser) return

  _canRead.value = bootUser.can_read || []
  _canCreate.value = bootUser.can_create || []
  _canWrite.value = bootUser.can_write || []
  _canDelete.value = bootUser.can_delete || []
  _canSubmit.value = bootUser.can_submit || []
  _canCancel.value = bootUser.can_cancel || []
  _roles.value = Array.isArray(bootUser.roles) ? bootUser.roles : []
  _isAdmin.value =
    window.frappe?.session?.user === 'Administrator' ||
    _roles.value.includes('Administrator')
  _loaded.value = true
}

// Run eagerly — boot data is available synchronously before Vue mounts
loadPermissions()

export function usePermissions() {

  function canRead(dt) {
    if (_isAdmin.value) return true
    return _canRead.value.includes(dt)
  }

  function canCreate(dt) {
    // Catalog-level create block (spine_consumer_config-synced doctypes: Lot,
    // Item, Terms and Condition). Checked BEFORE the admin bypass so no /web
    // create surface — list New, home CTA, palette, Duplicate — ever appears
    // for these, for ANY user. See config/doctypes.js noWebCreate().
    if (noWebCreate(dt)) return false
    if (_isAdmin.value) return true
    return _canCreate.value.includes(dt)
  }

  function canWrite(dt) {
    if (_isAdmin.value) return true
    return _canWrite.value.includes(dt)
  }

  function canDelete(dt) {
    if (_isAdmin.value) return true
    return _canDelete.value.includes(dt)
  }

  function canSubmit(dt) {
    if (_isAdmin.value) return true
    return _canSubmit.value.includes(dt)
  }

  function canCancel(dt) {
    if (_isAdmin.value) return true
    return _canCancel.value.includes(dt)
  }

  function canAmend(dt) {
    return canCreate(dt)
  }

  // Role helpers (e.g. to gate "Open in Desk" to admins / System Managers).
  function hasRole(role) {
    return _roles.value.includes(role)
  }
  const isAdmin = computed(() => _isAdmin.value)

  const accessLabel = computed(() => {
    if (!_loaded.value) return ''
    if (_isAdmin.value) return 'Administrator'
    const hasCreate = _canCreate.value.length > 0
    const hasWrite = _canWrite.value.length > 0
    if (hasCreate && hasWrite) return 'Full access'
    if (_canRead.value.length > 0 && !hasCreate && !hasWrite) return 'Read only'
    return 'Limited access'
  })

  return {
    loadPermissions,
    canRead,
    canCreate,
    canWrite,
    canDelete,
    canSubmit,
    canCancel,
    canAmend,
    hasRole,
    isAdmin,
    accessLabel,
  }
}
