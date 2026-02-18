; launch_ps.ahk
; Usage: AutoHotkey.exe scripts\launch_ps.ahk <photoshop_exe> <jsx_path>
;
; Launches Photoshop with the given JSX script via the -r flag.
; Photoshop must not already be running (or must accept a second instance).
; The script exits immediately after launching — the orchestrator polls for
; the output file.

#NoEnv
#SingleInstance Off
SetWorkingDir %A_ScriptDir%\..

; ---------- read CLI arguments ----------
photoshopExe := A_Args[1]
jsxPath      := A_Args[2]

if (photoshopExe = "" or jsxPath = "") {
    MsgBox, 16, launch_ps.ahk, Usage: AutoHotkey.exe launch_ps.ahk <photoshop_exe> <jsx_path>
    ExitApp, 1
}

if !FileExist(photoshopExe) {
    MsgBox, 16, launch_ps.ahk, Photoshop not found:`n%photoshopExe%
    ExitApp, 2
}

if !FileExist(jsxPath) {
    MsgBox, 16, launch_ps.ahk, JSX not found:`n%jsxPath%
    ExitApp, 3
}

; ---------- launch ----------
Run, "%photoshopExe%" -r "%jsxPath%",, Hide, PID
if ErrorLevel {
    MsgBox, 16, launch_ps.ahk, Failed to launch Photoshop.
    ExitApp, 4
}

; Give Photoshop a moment to start accepting the script
Sleep, 2000
ExitApp, 0
