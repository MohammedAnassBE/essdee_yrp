/**
 * Authentication helpers for the Frappe backend.
 */

import { callMethod } from './client'

/**
 * Log in with username and password.
 * On success, reloads the page to pick up the new CSRF token set by Frappe.
 */
export async function login(usr, pwd) {
  const response = await fetch('/api/method/login', {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    credentials: 'include',
    body: JSON.stringify({ usr, pwd }),
  })

  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.message || 'Login failed')
  }

  // Reload so the server-rendered template injects a fresh csrf_token
  window.location.reload()
}

/**
 * Log out the current user and redirect to the login page.
 */
export async function logout() {
  await callMethod('logout')
  window.location.href = '/login'
}

/**
 * Get the currently logged-in user's email / username.
 * @returns {string} e.g. "administrator" or "user@example.com"
 */
export async function getLoggedUser() {
  const user = await callMethod('frappe.auth.get_logged_user')
  return user
}

/**
 * Retrieve basic session info.
 * Prefers the boot data Frappe injects into the page; falls back to an API call.
 * @returns {{ user: string, full_name: string }}
 */
export async function getSessionInfo() {
  // Frappe injects boot data into the page on first load
  const boot = window.frappe?.boot
  if (boot?.user?.name) {
    return {
      user: boot.user.name,
      full_name: boot.user.full_name || boot.user.name,
    }
  }

  const user = await getLoggedUser()
  return { user, full_name: user }
}
