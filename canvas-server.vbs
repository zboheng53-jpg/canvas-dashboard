' Canvas Dashboard - Silent background server wrapper
' Runs serve.py via pythonw.exe (no console window)
' Auto-restarts on crash (exit code 1), stops on clean exit or port conflict

Option Explicit

Dim WshShell, fso, strDir, pythonExe, scriptPath, logPath, logFile
Dim exitCode, restartCount, delayMs

Const EXIT_OK = 0
Const EXIT_CRASH = 1
Const EXIT_PORT_CONFLICT = 2

Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

strDir = fso.GetParentFolderName(WScript.ScriptFullName)
pythonExe = strDir & "\.venv\Scripts\pythonw.exe"
scriptPath = strDir & "\serve.py"
logPath = strDir & "\data\vbs_wrapper.log"
restartCount = 0

If Not fso.FileExists(pythonExe) Then
    WScript.Quit 3
End If

Sub WriteLog(msg)
    On Error Resume Next
    Set logFile = fso.OpenTextFile(logPath, 8, True)
    If Err.Number = 0 Then
        logFile.WriteLine Now() & " " & msg
        logFile.Close
    End If
    On Error GoTo 0
End Sub

WriteLog "[INFO] VBS wrapper started. Project: " & strDir

Do
    exitCode = WshShell.Run("""" & pythonExe & """ """ & scriptPath & """", 0, True)

    WriteLog "[INFO] serve.py exited with code " & exitCode

    Select Case exitCode
        Case EXIT_OK
            WriteLog "[INFO] Clean shutdown — exiting wrapper."
            Exit Do
        Case EXIT_PORT_CONFLICT
            WriteLog "[INFO] Port conflict — another instance is running."
            Exit Do
        Case Else
            restartCount = restartCount + 1
            If restartCount <= 10 Then
                delayMs = 2000
            ElseIf restartCount <= 30 Then
                delayMs = 10000
            Else
                delayMs = 60000
            End If
            WriteLog "[INFO] Restarting in " & delayMs & "ms (attempt #" & restartCount & ")"
            WScript.Sleep delayMs
    End Select
Loop
