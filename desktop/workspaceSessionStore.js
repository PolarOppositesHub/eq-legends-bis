/**
 * Working session on disk, next to settings.json, under Electron userData.
 *
 * userData follows the app product name (EQ Legends BiS), not the version
 * and not the API port. NSIS upgrades and electron-updater replace the
 * install directory and leave this folder in place, so the file survives
 * an app update. localStorage cannot: the window origin is
 * http://127.0.0.1:<port>/ and the port changes every launch.
 *
 * A corrupt or partial file reads back as null so the UI can start from
 * defaults. Writes are atomic (temp file + rename) so a crash mid-save
 * does not leave a truncated JSON document in place of the last good one.
 */
const fs = require('fs');
const path = require('path');

const FILE_NAME = 'workspace-session.json';
const MAX_BYTES = 8_000_000;

function sessionFilePath(userDataDir) {
  return path.join(userDataDir, FILE_NAME);
}

function readWorkspaceSession(userDataDir) {
  try {
    const filePath = sessionFilePath(userDataDir);
    if (!fs.existsSync(filePath)) return null;
    const raw = fs.readFileSync(filePath, 'utf8');
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return null;
    return parsed;
  } catch (_) {
    return null;
  }
}

function writeWorkspaceSession(userDataDir, session) {
  if (!session || typeof session !== 'object' || Array.isArray(session)) {
    throw new Error('workspace session must be a plain object');
  }
  const body = JSON.stringify(session);
  if (Buffer.byteLength(body, 'utf8') > MAX_BYTES) {
    throw new Error('workspace session is too large');
  }
  const filePath = sessionFilePath(userDataDir);
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  const tmp = `${filePath}.${process.pid}.tmp`;
  fs.writeFileSync(tmp, body, 'utf8');
  fs.renameSync(tmp, filePath);
  return session;
}

function clearWorkspaceSession(userDataDir) {
  const filePath = sessionFilePath(userDataDir);
  try {
    if (fs.existsSync(filePath)) fs.unlinkSync(filePath);
  } catch (_) {
    /* already gone */
  }
  return { ok: true };
}

module.exports = {
  FILE_NAME,
  MAX_BYTES,
  sessionFilePath,
  readWorkspaceSession,
  writeWorkspaceSession,
  clearWorkspaceSession,
};
