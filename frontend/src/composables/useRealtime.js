/**
 * useRealtime — a single shared socket.io connection to Frappe's realtime server
 * for live document/list updates in the /web SPA.
 *
 * Design (mirrors Frappe Desk's socketio_client.js):
 *  - ONE module-singleton socket per browser tab (not per component).
 *  - Lazy connect on first subscription; degrades silently if the realtime
 *    server is unreachable — realtime is strictly ADDITIVE, the app works
 *    without it and the server-side stale-write guard still protects data.
 *  - Ref-counted room subscriptions so overlapping subscribers share one
 *    server-side join, and re-emitted on (re)connect so reconnects recover.
 *
 * Events consumed (emitted by Frappe core on every save — no backend code):
 *  - `doc_update`  { modified, doctype, name }  on room doc:<doctype>/<name>
 *  - `list_update` { doctype, name, user }       on room doctype:<doctype>
 *
 * Protocol (from apps/frappe/realtime/*, read-only reference):
 *  - URL: <protocol>//<hostname>:<socketio_port>/<site_name> — the namespace IS
 *    the site name (multitenancy); boot.socketio_port comes from web.py.
 *  - Auth: the `sid` session cookie rides along (withCredentials; cookies are
 *    port-agnostic). The node server validates it via
 *    /api/method/frappe.realtime.get_user_info.
 *  - Rooms: emitting `doctype_subscribe`(doctype) joins `doctype:<DocType>`
 *    AFTER a server-side frappe.realtime.has_permission check — no read
 *    permission means the join silently never happens (arrangement never
 *    grants capability).
 */
import { ref, readonly } from 'vue'
import { io } from 'socket.io-client'

let socket = null
let connectFailed = false

// Reactive connection state, exported (read-only) so shells/pages can render a
// "Live" indicator. False until the socket's first successful connect; tracks
// disconnect/reconnect cycles after that.
const connected = ref(false)

// Ref-counted rooms. Key is `<doctype>::<name>` for docs, `<doctype>` for lists.
const docRooms = new Map() // key -> { doctype, name, count }
const listRooms = new Map() // doctype -> { count }

function boot() {
  return (typeof window !== 'undefined' && window.frappe && window.frappe.boot) || {}
}

// A subscriber callback must NEVER throw into the socket.io event loop (it
// would break sibling listeners on the same event). Realtime is best-effort.
function safeCall(cb, data) {
  try {
    cb(data)
  } catch (err) {
    // eslint-disable-next-line no-console
    console.warn('[realtime] subscriber callback failed', err)
  }
}

// Re-emit every active subscription. Runs on first connect AND every reconnect,
// so a dropped connection recovers its rooms without the components re-subscribing.
function rejoinAll() {
  if (!socket) return
  for (const { doctype, name } of docRooms.values()) socket.emit('doc_subscribe', doctype, name)
  for (const [doctype] of listRooms) socket.emit('doctype_subscribe', doctype)
}

function ensureSocket() {
  if (socket || connectFailed) return socket
  if (typeof window === 'undefined') return null
  const b = boot()
  const site = b.site_name
  const port = b.socketio_port || 9000
  if (!site) {
    connectFailed = true
    return null
  }
  try {
    // Build host-only (NOT location.origin — origin already carries :8003 and
    // would double-port to :8003:9000). The namespace is the site name.
    const url = `${window.location.protocol}//${window.location.hostname}:${port}/${site}`
    socket = io(url, {
      withCredentials: true, // send the `sid` session cookie for auth
      // Keep retrying forever (default backoff, capped at 30s) so a bench/
      // realtime-server restart recovers without a page reload. All failures
      // stay silent — the app works identically with realtime down.
      reconnectionDelayMax: 30000,
      secure: window.location.protocol === 'https:',
    })
    socket.on('connect', () => {
      connected.value = true
      rejoinAll()
    })
    socket.on('disconnect', () => {
      connected.value = false
    })
    // Silent: realtime is additive; never surface a socket failure to the user.
    socket.on('connect_error', () => {})
  } catch (_) {
    socket = null
    connectFailed = true
  }
  return socket
}

/**
 * Subscribe to changes of a single document. `cb({ modified, doctype, name })`
 * fires only for the matching doctype+name. Returns a disposer (call onUnmounted).
 */
function onDocUpdate(doctype, name, cb) {
  const s = ensureSocket()
  if (!s || !doctype || !name) return () => {}
  const key = `${doctype}::${name}`
  const entry = docRooms.get(key)
  if (entry) {
    entry.count++
  } else {
    docRooms.set(key, { doctype, name, count: 1 })
    s.emit('doc_subscribe', doctype, name)
  }
  const handler = (data) => {
    if (data && data.doctype === doctype && data.name === name) safeCall(cb, data)
  }
  s.on('doc_update', handler)
  return () => {
    s.off('doc_update', handler)
    const e = docRooms.get(key)
    if (!e) return
    e.count--
    if (e.count <= 0) {
      docRooms.delete(key)
      s.emit('doc_unsubscribe', doctype, name)
    }
  }
}

/**
 * Subscribe to any change within a doctype (list view). `cb({ doctype, name,
 * user })` fires for any matching-doctype save. Returns a disposer.
 */
function onListUpdate(doctype, cb) {
  const s = ensureSocket()
  if (!s || !doctype) return () => {}
  const entry = listRooms.get(doctype)
  if (entry) {
    entry.count++
  } else {
    listRooms.set(doctype, { count: 1 })
    s.emit('doctype_subscribe', doctype)
  }
  const handler = (data) => {
    if (data && data.doctype === doctype) safeCall(cb, data)
  }
  s.on('list_update', handler)
  return () => {
    s.off('list_update', handler)
    const e = listRooms.get(doctype)
    if (!e) return
    e.count--
    if (e.count <= 0) {
      listRooms.delete(doctype)
      s.emit('doctype_unsubscribe', doctype)
    }
  }
}

/**
 * Subscribe to list changes of a doctype with a built-in trailing debounce
 * (minimum 500ms) so bursts of saves (bulk imports, cascades) collapse into a
 * single callback carrying the LATEST `{ doctype, name, user }` payload.
 *
 * Preferred entry point for shells/blocks; `onListUpdate` stays available for
 * callers that manage their own coalescing (DynamicListPage does).
 *
 * Returns the unsubscribe helper: calling it cancels any pending debounced
 * fire, detaches the listener, and (ref-counted) leaves the server room.
 */
function subscribeList(doctype, cb, { debounceMs = 500 } = {}) {
  const wait = Math.max(500, Number(debounceMs) || 0)
  let timer = null
  let lastData = null
  const dispose = onListUpdate(doctype, (data) => {
    lastData = data
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => {
      timer = null
      safeCall(cb, lastData)
    }, wait)
  })
  return () => {
    if (timer) {
      clearTimeout(timer)
      timer = null
    }
    dispose()
  }
}

/**
 * Kick off the shared socket connection WITHOUT subscribing to anything.
 * Used by shells that render a Live indicator (ChromeBar) so `connected` is
 * truthful even before the first room subscription. Idempotent and as silent
 * as every other entry point — a failed connect just leaves connected=false.
 */
function ensureConnected() {
  ensureSocket()
}

const connectedReadonly = readonly(connected)

export function useRealtime() {
  return {
    /** Reactive read-only ref — true while the socket is connected. */
    connected: connectedReadonly,
    /** Connect the shared socket eagerly (no subscription). Idempotent. */
    ensureConnected,
    /** Debounced (>=500ms) list subscription; returns its unsubscribe fn. */
    subscribeList,
    onDocUpdate,
    onListUpdate,
  }
}

// Introspection handle for headless verification (playwright drives) and quick
// console debugging. Inert: it exposes only what useRealtime() already returns,
// and every room join is still permission-checked server-side.
if (typeof window !== 'undefined') {
  window.__essdeeRealtime = {
    get connected() {
      return connected.value
    },
    ensureConnected,
    subscribeList,
    onDocUpdate,
    onListUpdate,
  }
}
