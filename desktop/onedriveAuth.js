/**
 * OneDrive sign-in for the public client.
 * System browser, loopback http://localhost:<port>, PKCE. The refresh token
 * stays in Electron safeStorage. Tests pass the crypto and file helpers in.
 */
const crypto = require('crypto')
const http = require('http')

const CLIENT_ID = '868f921b-3445-4b09-90bf-13b343145256'
// /common covers work and personal accounts. /consumers would reject work accounts.
// The scope must be the fully qualified Graph resource. A bare Files.ReadWrite.AppFolder
// on /common makes a personal Microsoft account get an opaque access token that Graph 401s.
// offline_access stays unqualified. Graph calls send Authorization: Bearer <token>.
const AUTHORITY = 'https://login.microsoftonline.com/common'
const SCOPES = 'https://graph.microsoft.com/Files.ReadWrite.AppFolder offline_access'
const REQUIRED_SCOPE = 'https://graph.microsoft.com/Files.ReadWrite.AppFolder'
const SIGN_IN_TEXT = 'Sign in to OneDrive'
const UPDATE_SIGN_IN_TEXT = 'Sign in to OneDrive again to finish the update'
const AUTH_EXPIRED_TEXT = 'OneDrive sign-in expired. Sign in again.'

function pkcePair(randomBytes = (n) => crypto.randomBytes(n)) {
  const verifier = randomBytes(32).toString('base64url')
  const challenge = crypto.createHash('sha256').update(verifier).digest('base64url')
  return { verifier, challenge }
}

function authorizeUrl({ redirectUri, state, challenge }) {
  const params = new URLSearchParams({
    client_id: CLIENT_ID,
    response_type: 'code',
    redirect_uri: redirectUri,
    response_mode: 'query',
    scope: SCOPES,
    state,
    code_challenge: challenge,
    code_challenge_method: 'S256',
  })
  return `${AUTHORITY}/oauth2/v2.0/authorize?${params.toString()}`
}

function tokenUrl() {
  return `${AUTHORITY}/oauth2/v2.0/token`
}

/** Display name from the access token Microsoft already issued. Empty if it has none. */
function accountFromAccessToken(accessToken) {
  const parts = String(accessToken || '').split('.')
  if (parts.length < 2) return ''
  try {
    const json = JSON.parse(Buffer.from(parts[1], 'base64url').toString('utf8'))
    return String(json.preferred_username || json.upn || json.unique_name || json.name || '')
  } catch (_) {
    return ''
  }
}

function tokenRequestBody({ grant, redirectUri, code, verifier, refreshToken }) {
  const body = new URLSearchParams({
    client_id: CLIENT_ID,
    scope: SCOPES,
    grant_type: grant,
  })
  if (grant === 'authorization_code') {
    body.set('code', code || '')
    body.set('redirect_uri', redirectUri || '')
    body.set('code_verifier', verifier || '')
  } else {
    body.set('refresh_token', refreshToken || '')
  }
  return body.toString()
}

function sealRefreshToken(token, deps) {
  if (!deps.isEncryptionAvailable()) {
    return { ok: false, error: 'This PC cannot store the OneDrive sign-in safely.' }
  }
  deps.writeFile(deps.tokenPath, deps.encryptString(token))
  return { ok: true }
}

function openRefreshToken(deps) {
  if (!deps.exists(deps.tokenPath) || !deps.isEncryptionAvailable()) return ''
  return deps.decryptString(deps.readFile(deps.tokenPath))
}

function forgetRefreshToken(deps) {
  if (deps.exists(deps.tokenPath)) deps.removeFile(deps.tokenPath)
  const scopes = scopesFile(deps)
  if (scopes && deps.exists(scopes)) deps.removeFile(scopes)
  return { ok: true }
}

function scopesFile(deps) {
  if (deps && deps.scopesPath) return deps.scopesPath
  const tokenPath = String((deps && deps.tokenPath) || '')
  if (!tokenPath) return ''
  if (tokenPath.endsWith('onedrive-refresh.bin')) {
    return tokenPath.replace(/onedrive-refresh\.bin$/, 'onedrive-scopes.txt')
  }
  return `${tokenPath}.scopes`
}

function readScopes(deps) {
  const file = scopesFile(deps)
  if (!file || !deps.exists(file)) return ''
  const raw = deps.readFile(file)
  if (Buffer.isBuffer(raw)) return raw.toString('utf8')
  return String(raw || '')
}

function scopesAreCurrent(text) {
  return String(text || '').includes(REQUIRED_SCOPE)
}

function writeScopes(deps) {
  const file = scopesFile(deps)
  if (!file || typeof deps.writeFile !== 'function') return
  deps.writeFile(file, Buffer.from(SCOPES, 'utf8'))
}

function formatTokenError(token) {
  if (!token || typeof token !== 'object') return ''
  const code = typeof token.error === 'string' ? token.error.trim() : ''
  const description = typeof token.error_description === 'string' ? token.error_description.trim() : ''
  if (code && description) return `${code}: ${description}`
  return description || code
}

function redactSecrets(text, secrets) {
  let safe = String(text || '')
  for (const secret of secrets || []) {
    if (secret) safe = safe.split(String(secret)).join('[redacted]')
  }
  return safe.replace(/Bearer\s+\S+/gi, 'Bearer [redacted]')
}

function logTokenProblem(deps, message, secrets) {
  const safe = redactSecrets(message, secrets)
  if (deps && typeof deps.log === 'function') deps.log(safe)
}

function listenLoopback(httpLib = http) {
  return new Promise((resolve, reject) => {
    const server = httpLib.createServer()
    server.once('error', reject)
    server.listen(0, '127.0.0.1', () => {
      const port = server.address().port
      resolve({ server, port, redirectUri: `http://localhost:${port}` })
    })
  })
}

function waitForCode(server, state) {
  return new Promise((resolve, reject) => {
    const onRequest = (req, res) => {
      const host = (req.headers && req.headers.host) || 'localhost'
      let parsed
      try {
        parsed = new URL(req.url || '/', `http://${host}`)
      } catch (err) {
        res.writeHead(400)
        res.end('Bad redirect')
        return
      }
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' })
      res.end('<p>You can close this window and return to EQ Legends BiS.</p>')
      server.close()
      if (parsed.searchParams.get('state') !== state) {
        reject(new Error('OneDrive sign-in did not match this app.'))
        return
      }
      const error = parsed.searchParams.get('error')
      if (error) {
        reject(new Error(parsed.searchParams.get('error_description') || error))
        return
      }
      resolve(parsed.searchParams.get('code') || '')
    }
    server.on('request', onRequest)
  })
}

async function signInOneDrive(deps) {
  const { verifier, challenge } = pkcePair(deps.randomBytes)
  const state = (deps.randomBytes || crypto.randomBytes)(16).toString('hex')
  const { server, redirectUri } = await listenLoopback(deps.http || http)
  const codePromise = waitForCode(server, state)
  const timer = setTimeout(() => {
    server.close()
  }, deps.timeoutMs || 180000)
  try {
    await deps.openExternal(authorizeUrl({ redirectUri, state, challenge }))
    const code = await codePromise
    if (!code) return { ok: false, error: 'OneDrive did not return a code.' }
    const token = await deps.request(tokenUrl(), {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: tokenRequestBody({
        grant: 'authorization_code',
        redirectUri,
        code,
        verifier,
      }),
    })
    const microsoft = formatTokenError(token)
    if (microsoft && !(token && token.access_token)) {
      logTokenProblem(deps, microsoft, [])
      return { ok: false, error: microsoft }
    }
    const access = token && token.access_token
    const refresh = token && token.refresh_token
    if (!access || !refresh) return { ok: false, error: microsoft || 'OneDrive did not return a refresh token.' }
    const sealed = sealRefreshToken(refresh, deps)
    if (!sealed.ok) return sealed
    writeScopes(deps)
    const account = token.account || accountFromAccessToken(access) || 'OneDrive'
    return { ok: true, access_token: access, account }
  } catch (err) {
    return { ok: false, error: String(err && err.message ? err.message : err) }
  } finally {
    clearTimeout(timer)
    try { server.close() } catch (_) { /* already closed */ }
  }
}

async function refreshAccessToken(deps) {
  const refresh = openRefreshToken(deps)
  if (!refresh) return { ok: false, signedOut: true, error: SIGN_IN_TEXT }
  if (!scopesAreCurrent(readScopes(deps))) {
    return { ok: false, needsUpdate: true, error: UPDATE_SIGN_IN_TEXT }
  }
  let token
  try {
    token = await deps.request(tokenUrl(), {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: tokenRequestBody({ grant: 'refresh_token', refreshToken: refresh }),
    })
  } catch (err) {
    const message = redactSecrets(String(err && err.message ? err.message : err), [refresh])
    logTokenProblem(deps, message, [refresh])
    return { ok: false, error: message, authExpired: false }
  }
  const microsoft = formatTokenError(token)
  if (!token || !token.access_token) {
    const message = redactSecrets(microsoft || AUTH_EXPIRED_TEXT, [refresh])
    logTokenProblem(deps, message, [refresh])
    return { ok: false, error: message, authExpired: true }
  }
  if (token.refresh_token) sealRefreshToken(token.refresh_token, deps)
  writeScopes(deps)
  const account = token.account || accountFromAccessToken(token.access_token) || 'OneDrive'
  return { ok: true, access_token: token.access_token, account }
}

module.exports = {
  CLIENT_ID,
  AUTHORITY,
  SCOPES,
  REQUIRED_SCOPE,
  SIGN_IN_TEXT,
  UPDATE_SIGN_IN_TEXT,
  AUTH_EXPIRED_TEXT,
  pkcePair,
  authorizeUrl,
  tokenUrl,
  tokenRequestBody,
  accountFromAccessToken,
  sealRefreshToken,
  openRefreshToken,
  forgetRefreshToken,
  scopesFile,
  scopesAreCurrent,
  listenLoopback,
  signInOneDrive,
  refreshAccessToken,
}
