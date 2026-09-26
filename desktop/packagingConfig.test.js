const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const fs = require('fs');
const path = require('path');
const test = require('node:test');

const desktopDir = __dirname;
const repoRoot = path.resolve(desktopDir, '..');

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, 'utf8'));
}

function showMainPackageJson() {
  return execFileSync('git', ['show', 'origin/main:desktop/package.json'], {
    cwd: repoRoot,
    encoding: 'utf8',
  });
}

test('nsis shortcuts, seal icon, include script, and appId stay stable', () => {
  const pkg = readJson(path.join(desktopDir, 'package.json'));
  const build = pkg.build;
  const mainPkg = JSON.parse(showMainPackageJson());
  const nsis = build.nsis;

  assert.equal(build.appId, 'com.eqlegends.bis');
  assert.equal(build.appId, mainPkg.build.appId);
  assert.equal(pkg.productName, mainPkg.productName);
  assert.equal(build.productName, mainPkg.build.productName);
  assert.equal(build.productName, 'EQ Legends BiS');
  assert.equal(nsis.shortcutName, mainPkg.build.nsis.shortcutName);
  assert.equal(nsis.shortcutName, 'EQ Legends BiS');
  assert.equal(nsis.oneClick, false);
  assert.equal(nsis.allowToChangeInstallationDirectory, true);
  assert.equal(Object.prototype.hasOwnProperty.call(nsis, 'guid'), false);
  assert.equal(Object.prototype.hasOwnProperty.call(mainPkg.build.nsis, 'guid'), false);

  assert.equal(nsis.createDesktopShortcut, 'always');
  assert.equal(nsis.createStartMenuShortcut, true);

  const sealIco = path.join(repoRoot, 'packaging', 'icons', 'eq-legends-bis.ico');
  const buildIco = path.join(desktopDir, 'build', 'icon.ico');
  assert.equal(fs.existsSync(sealIco), true);
  assert.equal(fs.readFileSync(buildIco).equals(fs.readFileSync(sealIco)), true);

  assert.equal(build.icon, 'build/icon.ico');
  assert.equal(build.win.icon, 'build/icon.ico');
  assert.equal(fs.existsSync(path.join(desktopDir, build.win.icon)), true);
  // false skips rcedit, so win.icon never becomes the exe's embedded icon.
  assert.equal(build.win.signAndEditExecutable, true);

  for (const key of ['installerIcon', 'uninstallerIcon', 'installerHeaderIcon']) {
    assert.equal(nsis[key], 'icon.ico');
    assert.equal(fs.existsSync(path.join(desktopDir, 'build', nsis[key])), true);
  }

  assert.equal(nsis.include, 'installer.nsh');
  const includePath = path.join(desktopDir, 'build', nsis.include);
  assert.equal(fs.existsSync(includePath), true);
  const nsh = fs.readFileSync(includePath, 'utf8');
  assert.match(nsh, /!macro customInstall\b/);
  assert.match(nsh, /CreateShortCut "\$newDesktopLink"/);
  assert.match(nsh, /CreateShortCut "\$newStartMenuLink"/);
  assert.match(nsh, /"\$appExe" 0/);
  assert.match(nsh, /shell32::SHChangeNotify\(i 0x08000000, i 0, i 0, i 0\)/);
  assert.match(nsh, /ie4uinit\.exe/);
  assert.match(nsh, /ExecWait '"\$eqIconCacheTool" -show'/);
  assert.equal(/\$\{IfNot\} \$\{Silent\}/.test(nsh), false);
  assert.equal(/!macro customInstall[\s\S]*\$\{isUpdated\}/.test(nsh), false);

  let ignored = false;
  try {
    execFileSync('git', ['check-ignore', '-q', 'desktop/build/installer.nsh'], { cwd: repoRoot });
    ignored = true;
  } catch (err) {
    assert.equal(err.status, 1);
  }
  assert.equal(ignored, false);

  const mainJs = fs.readFileSync(path.join(desktopDir, 'main.js'), 'utf8');
  const idMatch = mainJs.match(/const APP_USER_MODEL_ID = '([^']+)'/);
  assert.ok(idMatch);
  assert.equal(idMatch[1], build.appId);
  assert.match(mainJs, /app\.setAppUserModelId\(APP_USER_MODEL_ID\)/);
});
