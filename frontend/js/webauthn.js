/* ============================================================================
   VECTOR · webauthn.js — passkey (fingerprint / Windows Hello / Face ID) login.

   Talks to core/api/routers/webauthn_auth.py. Replaces having to paste
   VECTOR_API_KEY into a URL or config file for interactive browser use — the
   private key never leaves the device; only a signed challenge crosses the
   wire, and a short-lived session token (12h) comes back on success.

   Usage:
     VECTORAuth.isEnrolled()       -> Promise<boolean>   (GET /auth/webauthn/status)
     VECTORAuth.register()         -> Promise<{status,name}>  (localhost only)
     VECTORAuth.login()            -> Promise<string>    resolves with the session token
     VECTORAuth.getSessionToken()  -> string | null      cached token, if still unexpired
     VECTORAuth.clearSession()     -> void

   On a successful login(), the token is (a) cached in sessionStorage under
   'vector_webauthn_token' and (b) written into window.VECTOR_CONFIG.apiKey
   so VECTOR.html's existing autoConnect() picks it up exactly like a
   pasted static key, with zero changes needed to vector-core.js's auth path.

   Browser constraint (not fixable client-side): WebAuthn only runs in a
   "secure context" — https://, or the special-cased http://localhost. It will
   NOT work from a phone hitting the LAN-IP HUD URL over plain HTTP; that path
   still needs the static VECTOR_API_KEY until VECTOR serves over TLS.

   NOT YET LIVE-TESTED in an actual browser (see KNOWN_ISSUES.md) — the
   backend ceremony logic has a full cryptographic round-trip test
   (tests/backend/test_webauthn_auth.py) using a simulated authenticator, but
   this file's own navigator.credentials.create()/get() calls need a real
   fingerprint/Windows Hello prompt to confirm end-to-end.
   ========================================================================== */
(function () {
  'use strict';

  const BASE = (window.VECTOR_CONFIG && window.VECTOR_CONFIG.base) || '';
  const TOKEN_KEY = 'vector_webauthn_token';
  const TOKEN_EXP_KEY = 'vector_webauthn_token_exp';

  function b64urlToBuffer(b64url) {
    const pad = '='.repeat((4 - (b64url.length % 4)) % 4);
    const base64 = (b64url + pad).replace(/-/g, '+').replace(/_/g, '/');
    const raw = atob(base64);
    const buf = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i++) buf[i] = raw.charCodeAt(i);
    return buf.buffer;
  }

  function bufferToB64url(buf) {
    const bytes = new Uint8Array(buf);
    let str = '';
    for (let i = 0; i < bytes.length; i++) str += String.fromCharCode(bytes[i]);
    return btoa(str).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  }

  async function api(path, opts) {
    const res = await fetch(BASE + path, Object.assign({
      headers: { 'Content-Type': 'application/json' }
    }, opts || {}));
    if (!res.ok) {
      let detail = res.statusText;
      try { detail = (await res.json()).detail || detail; } catch (e) {}
      throw new Error(`${path} -> ${res.status}: ${detail}`);
    }
    return res.json();
  }

  async function isEnrolled() {
    const status = await api('/auth/webauthn/status');
    return !!status.enrolled;
  }

  async function register() {
    if (!window.PublicKeyCredential) {
      throw new Error('This browser does not support WebAuthn/passkeys.');
    }
    const options = await api('/auth/webauthn/register/options', { method: 'POST' });

    const publicKey = Object.assign({}, options, {
      challenge: b64urlToBuffer(options.challenge),
      user: Object.assign({}, options.user, { id: b64urlToBuffer(options.user.id) }),
      excludeCredentials: (options.excludeCredentials || []).map(c =>
        Object.assign({}, c, { id: b64urlToBuffer(c.id) })
      )
    });

    const credential = await navigator.credentials.create({ publicKey });
    if (!credential) throw new Error('Passkey creation was cancelled.');

    const body = {
      id: credential.id,
      rawId: bufferToB64url(credential.rawId),
      type: credential.type,
      response: {
        clientDataJSON: bufferToB64url(credential.response.clientDataJSON),
        attestationObject: bufferToB64url(credential.response.attestationObject)
      }
    };

    return api('/auth/webauthn/register/verify', {
      method: 'POST',
      body: JSON.stringify(body)
    });
  }

  async function login() {
    if (!window.PublicKeyCredential) {
      throw new Error('This browser does not support WebAuthn/passkeys.');
    }
    const options = await api('/auth/webauthn/login/options', { method: 'POST' });

    const publicKey = Object.assign({}, options, {
      challenge: b64urlToBuffer(options.challenge),
      allowCredentials: (options.allowCredentials || []).map(c =>
        Object.assign({}, c, { id: b64urlToBuffer(c.id) })
      )
    });

    const assertion = await navigator.credentials.get({ publicKey });
    if (!assertion) throw new Error('Passkey login was cancelled.');

    const body = {
      id: assertion.id,
      rawId: bufferToB64url(assertion.rawId),
      type: assertion.type,
      response: {
        clientDataJSON: bufferToB64url(assertion.response.clientDataJSON),
        authenticatorData: bufferToB64url(assertion.response.authenticatorData),
        signature: bufferToB64url(assertion.response.signature),
        userHandle: assertion.response.userHandle ? bufferToB64url(assertion.response.userHandle) : null
      }
    };

    const result = await api('/auth/webauthn/login/verify', {
      method: 'POST',
      body: JSON.stringify(body)
    });

    const expiresAt = Date.now() + (result.expires_in || 0) * 1000;
    sessionStorage.setItem(TOKEN_KEY, result.token);
    sessionStorage.setItem(TOKEN_EXP_KEY, String(expiresAt));

    window.VECTOR_CONFIG = window.VECTOR_CONFIG || {};
    window.VECTOR_CONFIG.apiKey = result.token;

    return result.token;
  }

  function getSessionToken() {
    const token = sessionStorage.getItem(TOKEN_KEY);
    const exp = parseInt(sessionStorage.getItem(TOKEN_EXP_KEY) || '0', 10);
    if (!token || !exp || Date.now() >= exp) return null;
    return token;
  }

  function clearSession() {
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(TOKEN_EXP_KEY);
  }

  // If a still-valid session exists from an earlier page load this tab,
  // make it available immediately (before autoConnect() runs) without
  // requiring another fingerprint prompt.
  const existing = getSessionToken();
  if (existing) {
    window.VECTOR_CONFIG = window.VECTOR_CONFIG || {};
    if (!window.VECTOR_CONFIG.apiKey) window.VECTOR_CONFIG.apiKey = existing;
  }

  window.VECTORAuth = { isEnrolled, register, login, getSessionToken, clearSession };
})();
