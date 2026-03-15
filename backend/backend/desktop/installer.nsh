; Custom NSIS installer script for Bracket Bot
; Creates desktop shortcut for uninstaller

!macro customInstall
  ; Create desktop shortcut for uninstaller
  CreateShortCut "$DESKTOP\Uninstall Bracket Bot.lnk" "$INSTDIR\Uninstall Bracket Bot.exe" "" "$INSTDIR\Uninstall Bracket Bot.exe" 0
  
  ; Create Start Menu shortcut for uninstaller
  CreateShortCut "$SMPROGRAMS\Bracket Bot\Uninstall Bracket Bot.lnk" "$INSTDIR\Uninstall Bracket Bot.exe" "" "$INSTDIR\Uninstall Bracket Bot.exe" 0
!macroend

!macro customUnInstall
  ; Remove desktop uninstall shortcut
  Delete "$DESKTOP\Uninstall Bracket Bot.lnk"
  
  ; Remove Start Menu uninstall shortcut
  Delete "$SMPROGRAMS\Bracket Bot\Uninstall Bracket Bot.lnk"
  
  ; Clean up any leftover data files
  RMDir /r "$LOCALAPPDATA\bracket-bot-desktop"
  RMDir /r "$APPDATA\bracket-bot-desktop"
!macroend
