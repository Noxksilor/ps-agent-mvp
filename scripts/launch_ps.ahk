; launch_ps.ahk  (AutoHotkey v2)
; Usage: AutoHotkey64.exe scripts\launch_ps.ahk <photoshop_exe> <jsx_path>
;
; Launches Photoshop with the given JSX script via the -r flag.
; The script exits after handing off to Photoshop — the orchestrator polls
; for the output file.

#Requires AutoHotkey v2.0
#SingleInstance Off

; ---------- read CLI arguments ----------
photoshopExe := A_Args.Length >= 1 ? A_Args[1] : ""
jsxPath      := A_Args.Length >= 2 ? A_Args[2] : ""

if (photoshopExe = "" or jsxPath = "") {
    MsgBox "Usage: AutoHotkey64.exe launch_ps.ahk <photoshop_exe> <jsx_path>", "launch_ps.ahk", 16
    ExitApp 1
}

if !FileExist(photoshopExe) {
    MsgBox "Photoshop not found:`n" photoshopExe, "launch_ps.ahk", 16
    ExitApp 2
}

if !FileExist(jsxPath) {
    MsgBox "JSX not found:`n" jsxPath, "launch_ps.ahk", 16
    ExitApp 3
}

; ---------- launch ----------
; Use Run with full quoted paths; Hide keeps the window hidden.
try {
    Run '"' photoshopExe '" -r "' jsxPath '"',, "Hide"
} catch as e {
    MsgBox "Failed to launch Photoshop: " e.Message, "launch_ps.ahk", 16
    ExitApp 4
}

; Give Photoshop a moment to start accepting the script
Sleep 2000
ExitApp 0
