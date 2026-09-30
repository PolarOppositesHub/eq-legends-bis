/** Drop validation, freshness, and which character file auto-import follows. */

const LOCATION_COLUMNS = ['location', 'name', 'id', 'count', 'slots'];
const KEYRING_COLUMNS = ['keyring', 'name', 'id'];

export const INVENTORY_EXE_MESSAGE =
  'Pick Inventory.txt from in-game /outputfile inventory — not inventory.exe or other binaries.';

export const INVENTORY_NOT_DUMP_MESSAGE =
  'That file is not an inventory dump. Drop the Inventory.txt from /outputfile inventory.';

export function classifyInventoryHeader(line) {
  const names = new Set();
  for (const part of String(line || '').split('\t')) {
    const key = part.trim().toLowerCase();
    if (key) names.add(key);
  }
  if (LOCATION_COLUMNS.every((key) => names.has(key))) return 'location';
  if (KEYRING_COLUMNS.every((key) => names.has(key)) && !names.has('location')) return 'keyring';
  return null;
}

export function inventoryTextHasRecognisedHeader(text) {
  const lines = String(text || '').replace(/^\uFEFF/, '').split(/\r?\n/);
  for (const line of lines) {
    if (!line.trim()) continue;
    if (classifyInventoryHeader(line)) return true;
  }
  return false;
}

export function looksLikeBinaryInventory(text) {
  if (text == null) return false;
  const sample = String(text).slice(0, 4096);
  if (sample.includes('\u0000')) return true;
  if (sample.startsWith('MZ') || sample.startsWith('\u007fELF')) return true;
  return false;
}

export function rejectionForInventoryDrop({ name, text }) {
  const lower = String(name || '').toLowerCase();
  if (lower.endsWith('.exe') || lower.endsWith('.dll') || lower.endsWith('.bin')) {
    return INVENTORY_EXE_MESSAGE;
  }
  if (looksLikeBinaryInventory(text)) return INVENTORY_NOT_DUMP_MESSAGE;
  if (!inventoryTextHasRecognisedHeader(text)) return INVENTORY_NOT_DUMP_MESSAGE;
  return null;
}

export async function acceptInventoryDrop(file) {
  if (!file) return { ok: false, message: 'No file dropped.' };
  const name = String(file.name || '');
  let text = '';
  try {
    text = typeof file.text === 'function' ? await file.text() : String(file.text || '');
  } catch (_) {
    return { ok: false, message: 'Could not read the dropped file.' };
  }
  const message = rejectionForInventoryDrop({ name, text });
  if (message) return { ok: false, message };
  return { ok: true, name, text };
}

export function formatImportedAgo(importedAt, now = Date.now()) {
  const at = Number(importedAt);
  if (!Number.isFinite(at)) return '';
  const elapsed = Math.max(0, Number(now) - at);
  const seconds = Math.floor(elapsed / 1000);
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return hours === 1 ? '1 hr ago' : `${hours} hr ago`;
  const days = Math.floor(hours / 24);
  return days === 1 ? '1 day ago' : `${days} days ago`;
}

export function freshnessLine(name, importedAt, now) {
  if (!name || importedAt == null || importedAt === '') return '';
  const ago = formatImportedAgo(importedAt, now);
  if (!ago) return '';
  return `Imported ${name} · ${ago}`;
}

export function defaultInventorySelection(files, preferredName) {
  const list = Array.isArray(files) ? files : [];
  if (preferredName && list.some((file) => file && file.name === preferredName)) {
    return preferredName;
  }
  if (list.length) return list[0].name || '';
  return '';
}

export const NO_INVENTORY_YET =
  'No inventory imported yet — use Update from EQ folder or Import Inventory.txt.';

export function occupiedInventoryRows(items) {
  return (Array.isArray(items) ? items : []).filter((row) => {
    const name = String(row?.base_name || row?.name || '').trim();
    return name && name.toLowerCase() !== 'empty';
  });
}

/**
 * The freshness line, the character selector, and the bag list have to name
 * one import. A filename remembered in settings is not an import until its
 * rows are loaded. With no pin, the default character is that import, which
 * is the newest dump.
 */
export function inventoryPanelState({
  files,
  selectedName,
  importedName,
  importedAt,
  items,
  now,
}) {
  const list = Array.isArray(files) ? files : [];
  const name = String(importedName || '').trim();
  const rows = Array.isArray(items) ? items : [];
  const occupied = occupiedInventoryRows(rows);
  const hasImport = Boolean(name) && rows.length > 0;
  const pinned = selectedName && list.some((file) => file && file.name === selectedName)
    ? selectedName
    : '';
  // A filename in settings is not an import until its rows are loaded.
  // Once they are, the line, the selector, and the slots all name that file
  // (the one just imported, which is the newest dump when nothing is pinned).
  if (!hasImport) {
    return {
      character: pinned,
      freshness: '',
      occupied: [],
      showEmpty: true,
    };
  }
  return {
    character: name,
    freshness: freshnessLine(name, importedAt, now),
    occupied,
    showEmpty: false,
  };
}

export function withChangedFile(files, info) {
  const list = Array.isArray(files) ? files.slice() : [];
  if (!info || !info.name) return list;
  const index = list.findIndex((file) => file && file.name === info.name);
  const previous = index >= 0 ? list[index] : null;
  const row = {
    name: info.name,
    path: info.path || previous?.path || '',
    mtimeMs: Math.max(Number(previous?.mtimeMs) || 0, Number(info.mtimeMs) || 0),
    size: info.size ?? previous?.size,
  };
  if (index >= 0) list[index] = { ...previous, ...row };
  else list.push(row);
  list.sort((a, b) => (Number(b.mtimeMs) || 0) - (Number(a.mtimeMs) || 0));
  return list;
}

export function shouldAutoImport({ enabled, selectedName, changedName, files }) {
  if (!enabled || !changedName) return false;
  // A pinned character follows that file. An empty pin follows the newest
  // mtime, which the caller passes already sorted.
  if (selectedName) return selectedName === changedName;
  const list = Array.isArray(files) ? files : [];
  if (!list.length) return true;
  const newest = list[0];
  return Boolean(newest && newest.name === changedName);
}
