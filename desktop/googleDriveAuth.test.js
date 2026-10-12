const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')
const {
  GOOGLE_DRIVE_CLIENT_ID,
  AUTHORIZE,
  SCOPES,
  SIGN_IN_TEXT,
  UPDATE_SIGN_IN_TEXT,
  pkcePair,
  authorizeUrl,
  tokenRequestBody,
  accountFromToken,
  sealRefreshToken,
  openRefreshToken,
  forgetRefreshToken,
  refreshAccessToken,
} = require('./googleDriveAuth')

test('Google Drive authorize URL is the public client, loopback, and PKCE', () => {
  assert.equal(GOOGLE_DRIVE_CLIENT_ID, '122260219418-2rhjatugpadqi99ofecm8quruernbb0d.apps.googleusercontent.com')
  assert.equal(GOOGLE_DRIVE_CLIENT_ID.includes('.apps.googleusercontent.com'), true)
  assert.equal(AUTHORIZE, 'https://accounts.google.com/o/oauth2/v2/auth')
  assert.equal(SCOPES, 'https://www.googleapis.com/auth/drive.appdata')
  const pair = pkcePair((n) => Buffer.alloc(n, 7))
  assert.notEqual(pair.verifier, pair.challenge)
  const url = new URL(authorizeUrl({
    redirectUri: 'http://localhost:54321',
    state: 'state-1',
    challenge: pair.challenge,
  }))
  assert.equal(url.origin + url.pathname, 'https://accounts.google.com/o/oauth2/v2/auth')
  assert.equal(url.searchParams.get('client_id'), GOOGLE_DRIVE_CLIENT_ID)
  assert.equal(url.searchParams.get('redirect_uri'), 'http://localhost:54321')
  assert.equal(url.searchParams.get('scope'), SCOPES)
  assert.equal(url.searchParams.get('code_challenge_method'), 'S256')
  assert.equal(url.searchParams.get('code_challenge'), pair.challenge)
  assert.equal(url.searchParams.get('response_type'), 'code')
  assert.equal(url.searchParams.get('access_type'), 'offline')
  assert.equal(url.searchParams.get('prompt'), 'consent')
  const body = new URLSearchParams(tokenRequestBody({
    grant: 'authorization_code',
    redirectUri: 'http://localhost:54321',
    code: 'code-1',
    verifier: pair.verifier,
  }))
  assert.equal(body.get('code_verifier'), pair.verifier)
  assert.equal(body.get('client_id'), GOOGLE_DRIVE_CLIENT_ID)
  assert.equal(body.get('client_secret'), null)
  assert.equal(body.get('scope'), null)
  const refresh = new URLSearchParams(tokenRequestBody({
    grant: 'refresh_token',
    refreshToken: 'refresh-1',
  }))
  assert.equal(refresh.get('refresh_token'), 'refresh-1')
  assert.equal(refresh.get('grant_type'), 'refresh_token')
  assert.equal(refresh.get('client_secret'), null)
})

test('the account falls back to Google Drive when the token has no email', () => {
  const payload = Buffer.from(JSON.stringify({ email: 'josh@example.com' })).toString('base64url')
  assert.equal(accountFromToken({ id_token: `header.${payload}.sig` }), 'josh@example.com')
  assert.equal(accountFromToken({ access_token: 'ya29.opaque' }), 'Google Drive')
})

test('refresh tokens are sealed with safeStorage', () => {
  const files = new Map()
  const deps = {
    tokenPath: 'google-drive-refresh.bin',
    isEncryptionAvailable: () => true,
    encryptString: (value) => Buffer.from(`sealed:${value}`),
    decryptString: (buf) => String(buf).replace('sealed:', ''),
    writeFile: (file, buf) => files.set(file, buf),
    readFile: (file) => files.get(file),
    exists: (file) => files.has(file),
    removeFile: (file) => files.delete(file),
  }
  assert.equal(sealRefreshToken('refresh-1', deps).ok, true)
  assert.equal(openRefreshToken(deps), 'refresh-1')
  forgetRefreshToken(deps)
  assert.equal(openRefreshToken(deps), '')
  const blocked = sealRefreshToken('refresh-1', { ...deps, isEncryptionAvailable: () => false })
  assert.equal(blocked.ok, false)
})

test('no stored refresh token says Sign in to Google Drive', async () => {
  const result = await refreshAccessToken({
    tokenPath: 'google-drive-refresh.bin',
    isEncryptionAvailable: () => true,
    exists: () => false,
    readFile: () => Buffer.from(''),
    decryptString: () => '',
  })
  assert.equal(result.ok, false)
  assert.equal(result.signedOut, true)
  assert.equal(result.error, SIGN_IN_TEXT)
})

test('a saved sign-in without the appdata scope asks to sign in again', async () => {
  const files = new Map()
  const deps = {
    tokenPath: 'google-drive-refresh.bin',
    isEncryptionAvailable: () => true,
    encryptString: (value) => Buffer.from(`sealed:${value}`),
    decryptString: (buf) => String(buf).replace('sealed:', ''),
    writeFile: (file, buf) => files.set(file, buf),
    readFile: (file) => files.get(file),
    exists: (file) => files.has(file),
    removeFile: (file) => files.delete(file),
    request: async () => { throw new Error('should not refresh') },
  }
  sealRefreshToken('refresh-1', deps)
  const result = await refreshAccessToken(deps)
  assert.equal(result.needsUpdate, true)
  assert.equal(result.error, UPDATE_SIGN_IN_TEXT)
})

test('a rejected refresh surfaces Google error text and does not log the token', async () => {
  const logs = []
  const files = new Map()
  const deps = {
    tokenPath: 'google-drive-refresh.bin',
    isEncryptionAvailable: () => true,
    encryptString: (value) => Buffer.from(`sealed:${value}`),
    decryptString: (buf) => String(buf).replace('sealed:', ''),
    writeFile: (file, buf) => files.set(file, buf),
    readFile: (file) => files.get(file),
    exists: (file) => files.has(file),
    removeFile: (file) => files.delete(file),
    log: (message) => logs.push(message),
    request: async () => ({ error: 'invalid_grant', error_description: 'Token has been expired or revoked.' }),
  }
  sealRefreshToken('refresh-1', deps)
  files.set(deps.tokenPath.replace('google-drive-refresh.bin', 'google-drive-scopes.txt'), Buffer.from(SCOPES))
  const result = await refreshAccessToken(deps)
  assert.equal(result.ok, false)
  assert.equal(result.authExpired, true)
  assert.match(result.error, /invalid_grant/)
  assert.match(result.error, /expired or revoked/)
  assert.equal(logs.join('\n').includes('refresh-1'), false)
})

test('the desktop shell signs in to Google Drive without giving the page the refresh token', () => {
  const main = fs.readFileSync(path.join(__dirname, 'main.js'), 'utf8')
  const preload = fs.readFileSync(path.join(__dirname, 'preload.js'), 'utf8')
  const pkg = require('./package.json')
  assert.match(main, /eq:google-drive-sign-in/)
  assert.match(main, /eq:google-drive-sign-out/)
  assert.match(main, /google-drive-refresh\.bin/)
  assert.match(main, /safeStorage/)
  assert.match(preload, /signInGoogleDrive/)
  assert.match(preload, /signOutGoogleDrive/)
  assert.equal(preload.includes('refresh_token'), false)
  assert.equal(main.includes('refresh_token'), false)
  assert.ok(pkg.build.files.includes('googleDriveAuth.js'))
})
