const assert = require('node:assert/strict')
const test = require('node:test')
const {
  CLIENT_ID,
  AUTHORITY,
  SCOPES,
  SIGN_IN_TEXT,
  UPDATE_SIGN_IN_TEXT,
  pkcePair,
  authorizeUrl,
  tokenRequestBody,
  accountFromAccessToken,
  sealRefreshToken,
  openRefreshToken,
  forgetRefreshToken,
  scopesFile,
  refreshAccessToken,
} = require('./onedriveAuth')

test('OneDrive authorize URL is the public client, loopback, and PKCE', () => {
  assert.equal(CLIENT_ID, '868f921b-3445-4b09-90bf-13b343145256')
  assert.equal(AUTHORITY, 'https://login.microsoftonline.com/common')
  assert.equal(SCOPES, 'https://graph.microsoft.com/Files.ReadWrite.AppFolder offline_access')
  const pair = pkcePair((n) => Buffer.alloc(n, 7))
  assert.notEqual(pair.verifier, pair.challenge)
  const url = new URL(authorizeUrl({
    redirectUri: 'http://localhost:54321',
    state: 'state-1',
    challenge: pair.challenge,
  }))
  assert.equal(url.origin + url.pathname, 'https://login.microsoftonline.com/common/oauth2/v2.0/authorize')
  assert.equal(url.searchParams.get('client_id'), CLIENT_ID)
  assert.equal(url.searchParams.get('redirect_uri'), 'http://localhost:54321')
  assert.equal(url.searchParams.get('scope'), 'https://graph.microsoft.com/Files.ReadWrite.AppFolder offline_access')
  assert.equal(url.searchParams.get('code_challenge_method'), 'S256')
  assert.equal(url.searchParams.get('code_challenge'), pair.challenge)
  assert.equal(url.searchParams.get('response_type'), 'code')
  const body = new URLSearchParams(tokenRequestBody({
    grant: 'authorization_code',
    redirectUri: 'http://localhost:54321',
    code: 'code-1',
    verifier: pair.verifier,
  }))
  assert.equal(body.get('scope'), SCOPES)
  assert.equal(body.get('code_verifier'), pair.verifier)
  assert.equal(body.get('client_id'), CLIENT_ID)
  assert.equal(body.get('client_secret'), null)
  const refresh = new URLSearchParams(tokenRequestBody({
    grant: 'refresh_token',
    refreshToken: 'refresh-1',
  }))
  assert.equal(refresh.get('refresh_token'), 'refresh-1')
  assert.equal(refresh.get('grant_type'), 'refresh_token')
  assert.equal(refresh.get('scope'), SCOPES)
})

test('the signed-in account comes from the access token when the token response has none', () => {
  const payload = Buffer.from(JSON.stringify({ preferred_username: 'josh@example.com' })).toString('base64url')
  assert.equal(accountFromAccessToken(`header.${payload}.sig`), 'josh@example.com')
  assert.equal(accountFromAccessToken('not-a-jwt'), '')
})

test('refresh tokens are sealed with safeStorage and refused when it is unavailable', () => {
  const files = new Map()
  const deps = {
    tokenPath: 'onedrive-refresh.bin',
    isEncryptionAvailable: () => true,
    encryptString: (value) => Buffer.from(`sealed:${value}`),
    decryptString: (buf) => String(buf).replace('sealed:', ''),
    writeFile: (path, buf) => files.set(path, buf),
    readFile: (path) => files.get(path),
    exists: (path) => files.has(path),
    removeFile: (path) => files.delete(path),
  }
  const sealed = sealRefreshToken('refresh-1', deps)
  assert.equal(sealed.ok, true)
  assert.equal(openRefreshToken(deps), 'refresh-1')
  forgetRefreshToken(deps)
  assert.equal(openRefreshToken(deps), '')
  const blocked = sealRefreshToken('refresh-1', { ...deps, isEncryptionAvailable: () => false })
  assert.equal(blocked.ok, false)
  assert.equal(files.has(deps.tokenPath), false)
})

function fileDeps(files = new Map()) {
  return {
    tokenPath: 'onedrive-refresh.bin',
    isEncryptionAvailable: () => true,
    encryptString: (value) => Buffer.from(`sealed:${value}`),
    decryptString: (buf) => String(buf).replace('sealed:', ''),
    writeFile: (path, buf) => files.set(path, buf),
    readFile: (path) => files.get(path),
    exists: (path) => files.has(path),
    removeFile: (path) => files.delete(path),
  }
}

test('no stored refresh token says Sign in to OneDrive', async () => {
  const result = await refreshAccessToken({
    ...fileDeps(),
    request: async () => {
      throw new Error('should not request a token')
    },
  })
  assert.equal(result.ok, false)
  assert.equal(result.signedOut, true)
  assert.equal(result.error, SIGN_IN_TEXT)
  assert.equal(result.error.includes('expired'), false)
})

test('a token saved for the old scopes asks the user to sign in again', async () => {
  const files = new Map()
  const deps = fileDeps(files)
  sealRefreshToken('refresh-1', deps)
  let requested = false
  const missing = await refreshAccessToken({
    ...deps,
    request: async () => {
      requested = true
      return { access_token: 'nope' }
    },
  })
  assert.equal(requested, false)
  assert.equal(missing.needsUpdate, true)
  assert.equal(missing.error, UPDATE_SIGN_IN_TEXT)
  deps.writeFile(scopesFile(deps), Buffer.from('Files.ReadWrite.AppFolder offline_access', 'utf8'))
  const old = await refreshAccessToken({
    ...deps,
    request: async () => {
      requested = true
      return { access_token: 'nope' }
    },
  })
  assert.equal(requested, false)
  assert.equal(old.error, UPDATE_SIGN_IN_TEXT)
})

test('a current refresh sends the Graph scope and a Microsoft error is shown and logged', async () => {
  const files = new Map()
  const deps = fileDeps(files)
  sealRefreshToken('refresh-1', deps)
  deps.writeFile(scopesFile(deps), Buffer.from(SCOPES, 'utf8'))
  const logs = []
  const failed = await refreshAccessToken({
    ...deps,
    log: (line) => logs.push(line),
    request: async () => ({
      error: 'invalid_grant',
      error_description: 'AADSTS70008: The refresh token refresh-1 has expired due to inactivity.',
    }),
  })
  assert.equal(failed.ok, false)
  assert.equal(failed.authExpired, true)
  assert.match(failed.error, /^invalid_grant: AADSTS70008:/)
  assert.equal(failed.error.includes('OneDrive sign-in expired'), false)
  assert.match(logs.join('\n'), /invalid_grant/)
  assert.equal(logs.join('\n').includes('refresh-1'), false)

  let scope = ''
  const ok = await refreshAccessToken({
    ...deps,
    request: async (_url, options) => {
      scope = new URLSearchParams(options.body).get('scope')
      return { access_token: 'opaque-access', refresh_token: 'refresh-2' }
    },
  })
  assert.equal(ok.ok, true)
  assert.equal(scope, SCOPES)
  assert.equal(openRefreshToken(deps), 'refresh-2')
  assert.match(String(deps.readFile(scopesFile(deps))), /https:\/\/graph\.microsoft\.com\/Files\.ReadWrite\.AppFolder/)
  forgetRefreshToken(deps)
  assert.equal(deps.exists(scopesFile(deps)), false)
})
