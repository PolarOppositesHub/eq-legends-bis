/**
 * Watch <EQ folder>/*-Inventory.txt and report a file only after its size
 * has stayed the same for about 400ms.
 *
 * /outputfile inventory rewrites the whole file. A delete-and-recreate
 * drops a file watch, so this watches the folder and re-arms on unlink.
 * Change, add, and unlink all reset the settle timer. A half-written
 * file (size still moving) is never handed to the importer.
 */
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const DEFAULT_SETTLE_MS = 400;

function isInventoryFileName(name) {
  const n = String(name || '');
  if (!/\.txt$/i.test(n)) return false;
  if (/inventory\.exe$/i.test(n)) return false;
  return /inventory\.txt$/i.test(n) || /-inventory\.txt$/i.test(n);
}

function bytesOf(raw) {
  if (Buffer.isBuffer(raw)) return raw;
  return Buffer.from(String(raw), 'utf8');
}

class InventoryFolderWatcher {
  constructor(options = {}) {
    this.folder = options.folder;
    this.settleMs = Number.isFinite(options.settleMs) ? options.settleMs : DEFAULT_SETTLE_MS;
    this.onReady = typeof options.onReady === 'function' ? options.onReady : () => {};
    this.onUnlink = typeof options.onUnlink === 'function' ? options.onUnlink : () => {};
    this.readFile = typeof options.readFile === 'function' ? options.readFile : null;
    this._fsWatch = options.fsWatch || fs.watch.bind(fs);
    this._stat = options.stat || fs.statSync.bind(fs);
    this._exists = options.exists || fs.existsSync.bind(fs);
    this._setTimeout = options.setTimeout || setTimeout;
    this._clearTimeout = options.clearTimeout || clearTimeout;
    this._watcher = null;
    this._armGeneration = 0;
    this._closed = true;
    this._pending = new Map();
    this._lastDelivered = new Map();
    this._missing = new Set();
  }

  start() {
    this._closed = false;
    this._arm();
  }

  stop() {
    this._closed = true;
    this._armGeneration += 1;
    this._closeWatch();
    for (const pending of this._pending.values()) {
      this._clearTimeout(pending.timer);
    }
    this._pending.clear();
  }

  _closeWatch() {
    if (!this._watcher) return;
    try {
      this._watcher.close();
    } catch (_) {
      /* already closed */
    }
    this._watcher = null;
  }

  _arm() {
    if (this._closed || !this.folder) return;
    const generation = this._armGeneration + 1;
    let next;
    try {
      next = this._fsWatch(this.folder, { persistent: true }, (eventType, filename) => {
        if (generation !== this._armGeneration) return;
        this._onRaw(eventType, filename);
      });
    } catch (_) {
      return;
    }
    this._armGeneration = generation;
    const previous = this._watcher;
    this._watcher = next;
    if (previous && previous !== next) {
      try {
        previous.close();
      } catch (_) {
        /* ignore */
      }
    }
    if (next && typeof next.on === 'function') {
      next.on('error', () => {
        if (this._closed || generation !== this._armGeneration) return;
        this._arm();
      });
    }
  }

  _onRaw(eventType, filename) {
    if (this._closed) return;
    if (!filename) {
      this._rescan();
      return;
    }
    const name = path.basename(String(filename));
    if (!isInventoryFileName(name)) return;
    const full = path.join(this.folder, name);
    if (!this._fileExists(full)) {
      this._handleUnlink(full, name);
      return;
    }
    this._missing.delete(full);
    this._schedule(full, name);
  }

  _fileExists(full) {
    try {
      return this._exists(full) && this._stat(full).isFile();
    } catch (_) {
      return false;
    }
  }

  _handleUnlink(full, name) {
    const pending = this._pending.get(full);
    if (pending) {
      this._clearTimeout(pending.timer);
      this._pending.delete(full);
    }
    // Forget the previous import so the recreated file is a new rewrite,
    // even when the new bytes happen to match the deleted file.
    this._lastDelivered.delete(full);
    const firstUnlink = !this._missing.has(full);
    this._missing.add(full);
    // A watch on the file itself dies on delete. Re-arm the folder watch
    // once per unlink so the recreate is observed. Duplicate unlink events
    // must not tear the new watch down again.
    if (firstUnlink) this._arm();
    try {
      this.onUnlink({ path: full, name });
    } catch (_) {
      /* listener errors stay in the listener */
    }
    // The replacement can land before the new watch is attached.
    this._setTimeout(() => {
      if (this._closed) return;
      if (this._fileExists(full)) {
        this._missing.delete(full);
        this._schedule(full, name);
      }
    }, 0);
  }

  _rescan() {
    let names = [];
    try {
      names = fs.readdirSync(this.folder);
    } catch (_) {
      return;
    }
    for (const name of names) {
      if (!isInventoryFileName(name)) continue;
      const full = path.join(this.folder, name);
      if (!this._fileExists(full)) continue;
      this._missing.delete(full);
      this._schedule(full, name);
    }
  }

  _schedule(full, name) {
    if (this._closed) return;
    let st;
    try {
      st = this._stat(full);
    } catch (_) {
      this._handleUnlink(full, name);
      return;
    }
    if (!st.isFile()) return;
    const size = st.size;
    const mtimeMs = st.mtimeMs;
    const prev = this._pending.get(full);
    const last = this._lastDelivered.get(full);
    // Same size and mtime we already imported: a trailing watch echo.
    if (!prev && last && last.size === size && last.mtimeMs === mtimeMs) return;
    if (prev) this._clearTimeout(prev.timer);
    const timer = this._setTimeout(() => {
      const current = this._pending.get(full);
      if (!current || current.size !== size) return;
      this._pending.delete(full);
      this._settle(full, name, size);
    }, this.settleMs);
    this._pending.set(full, { size, mtimeMs, timer });
  }

  _readBytes(full) {
    const raw = this.readFile ? this.readFile(full) : fs.readFileSync(full);
    return bytesOf(raw);
  }

  _settle(full, name, seenSize) {
    if (this._closed) return;
    let st;
    try {
      st = this._stat(full);
    } catch (_) {
      return;
    }
    if (!st.isFile()) return;
    // Size moved during the quiet period. The snapshot was a partial write.
    if (st.size !== seenSize) {
      this._schedule(full, name);
      return;
    }
    if (seenSize === 0) return;
    let buf;
    try {
      buf = this._readBytes(full);
    } catch (_) {
      this._schedule(full, name);
      return;
    }
    if (buf.length !== seenSize) {
      this._schedule(full, name);
      return;
    }
    const hash = crypto.createHash('sha1').update(buf).digest('hex');
    const last = this._lastDelivered.get(full);
    this._lastDelivered.set(full, { size: seenSize, mtimeMs: st.mtimeMs, hash });
    // Identical bytes are the tail of the rewrite we already imported.
    if (last && last.hash === hash) return;
    try {
      this.onReady({
        path: full,
        name,
        size: seenSize,
        mtimeMs: st.mtimeMs,
      });
    } catch (_) {
      /* listener errors stay in the listener */
    }
  }
}

module.exports = {
  DEFAULT_SETTLE_MS,
  InventoryFolderWatcher,
  isInventoryFileName,
};
