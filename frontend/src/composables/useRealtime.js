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
 */
import { io } from 'socket.io-client'

let socket = null
let connectFailed = false

// Ref-counted rooms. Key is `<doctype>::<name>` for docs, `<doctype>` for lists.
const docRooms = new Map() // key -> { doctype, name, count }
const listRooms = new Map() // doctype -> { count }

function boot() {
  return (typeof window !== 'undefined' && window.frappe && window.frappe.boot) || {}
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
      reconnectionAttempts: 5,
      secure: window.location.protocol === 'https:',
    })
    socket.on('connect', rejoinAll)
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
    if (data && data.doctype === doctype && data.name === name) cb(data)
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
    if (data && data.doctype === doctype) cb(data)
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

export function useRealtime() {
  return { onDocUpdate, onListUpdate }
}
