/*
 * "Export to Catalog" button on Instance pages.
 *
 * POST /export needs a Keycloak bearer token with the `export` role, so the
 * user logs in on first click. The login is a full-page redirect, so the
 * pending export is stashed in sessionStorage and sent once the user returns.
 * Mirrors sinopia_editor's actionCreators/transfer.js.
 *
 * "keycloak-js" resolves through the import map in _fields.html, which pins
 * the jsDelivr URL and its integrity hash.
 */
import Keycloak from "keycloak-js"

const PENDING_KEY = "bc-export-pending"
const button = document.getElementById("bc-export")
const notice = document.getElementById("bc-export-notice")

const notify = (message, isError = false) => {
  notice.textContent = message
  notice.classList.toggle("bc-notice-error", isError)
  notice.hidden = false
  // The notice sits under the sidebar; the button is near the bottom of the page
  notice.scrollIntoView({ behavior: "smooth", block: "start" })
}

if (button) {
  const {
    instanceUri,
    exportUrl,
    keycloakUrl,
    keycloakRealm,
    keycloakClientId,
  } = button.dataset

  const keycloak = new Keycloak({
    url: keycloakUrl,
    realm: keycloakRealm,
    clientId: keycloakClientId,
  })

  const postExport = async () => {
    await keycloak.updateToken(30)
    const resp = await fetch(exportUrl, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${keycloak.token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ instance_uri: instanceUri }),
    })
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}))
      throw new Error(
        typeof body.detail === "string" ? body.detail : resp.statusText
      )
    }
    notify(
      `Export of ${instanceUri} requested. You will be notified by email once processed.`
    )
  }

  // Disabled while in flight, so a click during the post-login export can't
  // send a duplicate request
  const exportInstance = () => {
    button.disabled = true
    return postExport()
      .catch((err) =>
        notify(`Error requesting export: ${err.message || err}`, true)
      )
      .finally(() => {
        button.disabled = false
      })
  }

  // init() also completes a login redirect when the callback is in the URL
  const ready = keycloak
    .init({ checkLoginIframe: false, pkceMethod: "S256" })
    .then((authenticated) => {
      if (authenticated && sessionStorage.getItem(PENDING_KEY) === instanceUri) {
        sessionStorage.removeItem(PENDING_KEY)
        exportInstance()
      }
    })
    .catch((err) => console.error("Keycloak initialization failed:", err))

  button.addEventListener("click", async () => {
    await ready
    if (keycloak.authenticated) return exportInstance()
    if (!keycloak.didInitialize) {
      return notify("Error requesting export: unable to reach login service", true)
    }
    sessionStorage.setItem(PENDING_KEY, instanceUri)
    keycloak.login()
  })
}
