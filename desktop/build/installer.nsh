# EQ Legends BiS — recreate desktop and Start Menu shortcuts, then refresh
# Explorer's icon cache so they show the current exe icon (dragon-eye seal).
#
# Checked against app-builder-lib 25.1.8 templates and electron-updater 6.8.9:
#
# Fresh install (interactive): installSection's addDesktopLink / addStartMenuLink
# already CreateShortCut. This macro runs after that and writes them again.
#
# Update: electron-updater always passes --updated (NsisUpdater.doInstall).
# quitAndInstall(false, true) is not silent; autoInstallOnAppQuit uses
# /S --updated. Either way isUpdated is set. With allowToChangeInstallationDirectory,
# setIsTryToKeepShortcuts stays true on update, the previous install's
# KeepShortcuts=true registry value is honored, and the old uninstaller is
# launched with --keep-shortcuts. addDesktopLink then does not CreateShortCut
# when the link path is unchanged. createDesktopShortcut "always" only defines
# RECREATE_DESKTOP_SHORTCUT, and that branch is skipped while isUpdated.
# The stock SHChangeNotify at the end of addDesktopLink still runs, but it
# does not replace the .lnk, so Explorer can keep the cached icon for the
# same exe path (the Public Desktop shortcut from the original install).
#
# customInstall is inserted at the end of the install section with no Silent
# or isUpdated guard, so this runs for a fresh install, an interactive update,
# and the silent updater path. The portable target does not include this file.
#
# $appExe, $newDesktopLink, and $newStartMenuLink are set in installSection
# after a per-machine silent update calls setInstallModePerAllUsers, so an
# all-users install refreshes the Public Desktop and common Start Menu links.
#
# The uninstaller is compiled as a separate makensis pass (-DBUILD_UNINSTALLER,
# warnings as errors). Keep this script's variable and macro out of that pass.

!ifndef BUILD_UNINSTALLER

Var eqIconCacheTool

!macro customInstall
  WinShell::UninstShortcut "$newDesktopLink"
  Delete "$newDesktopLink"
  ClearErrors
  CreateShortCut "$newDesktopLink" "$appExe" "" "$appExe" 0 "" "" "${APP_DESCRIPTION}"
  ClearErrors
  WinShell::SetLnkAUMI "$newDesktopLink" "${APP_ID}"

  WinShell::UninstShortcut "$newStartMenuLink"
  Delete "$newStartMenuLink"
  ClearErrors
  CreateShortCut "$newStartMenuLink" "$appExe" "" "$appExe" 0 "" "" "${APP_DESCRIPTION}"
  ClearErrors
  WinShell::SetLnkAUMI "$newStartMenuLink" "${APP_ID}"

  # SHCNE_UPDATEITEM (0x00002000) + SHCNF_PATHW (0x0005) for the exe and both
  # links, then SHCNE_ASSOCCHANGED (0x08000000) so every Explorer window drops
  # the cached association.
  System::Call 'shell32::SHChangeNotify(i 0x00002000, i 0x0005, w "$appExe", i 0)'
  System::Call 'shell32::SHChangeNotify(i 0x00002000, i 0x0005, w "$newDesktopLink", i 0)'
  System::Call 'shell32::SHChangeNotify(i 0x00002000, i 0x0005, w "$newStartMenuLink", i 0)'
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, i 0, i 0)'

  # ie4uinit rebuilds the per-user icon cache. makensis is 32-bit, so on
  # 64-bit Windows Sysnative is the real System32 (System32 would be WOW64).
  ${If} ${RunningX64}
    StrCpy $eqIconCacheTool "$WINDIR\Sysnative\ie4uinit.exe"
  ${Else}
    StrCpy $eqIconCacheTool "$WINDIR\System32\ie4uinit.exe"
  ${EndIf}
  ${If} ${FileExists} "$eqIconCacheTool"
    ExecWait '"$eqIconCacheTool" -show'
    ExecWait '"$eqIconCacheTool" -ClearIconCache'
  ${EndIf}
  ClearErrors
!macroend

!endif
