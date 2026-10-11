const assert = require('node:assert/strict')
const test = require('node:test')
const {
  CLIENT_ID,
  AUTHORITY,
  SCOPES,
  pkcePair,
  authorizeUrl,
  tokenRequestBody,
  accountFromAccessToken,
  sealRefreshToken,
  openRefreshToken,
  forgetRefreshToken,
} = require('./onedriveAuth')

test('OneDrive authorize URL is the public client, loopback, and PKCE', () => {
  assert.equal(CLIENT_ID, '868f921b-3445-4b09-90bf-13b343145256')
  assert.equal(AUTHORITY, 'https://login.microsoftonline.com/common')
  assert.equal(SCOPES, 'Files.ReadWrite.AppFolder offline_access')
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
  assert.equal(url.searchParams.get('scope'), SCOPES)
  assert.equal(url.searchParams.get('code_challenge_method'), 'S256')
  assert.equal(url.searchParams.get('code_challenge'), pair.challenge)
  assert.equal(url.searchParams.get('response_type'), 'code')
  const body = new URLSearchParams(tokenRequestBody({
    grant: 'authorization_code',
    redirectUri: 'http://localhost:54321',
    code: 'code-1',
    verifier: pair.verifier,
  }))
  assert.equal(body.get('code_verifier'), pair.verifier)
  assert.equal(body.get('client_id'), CLIENT_ID)
  assert.equal(body.get('client_secret'), null)
  const refresh = new URLSearchParams(tokenRequestBody({
    grant: 'refresh_token',
    refreshToken: 'refresh-1',
  }))
  assert.equal(refresh.get('refresh_token'), 'refresh-1')
  assert.equal(refresh.get('grant_type'), 'refresh_token')
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
