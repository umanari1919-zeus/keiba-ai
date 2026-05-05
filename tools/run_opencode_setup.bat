@echo off
REM 🚀 OpenCode 完全自動セットアップ
REM うまなり地蔵AI 競馬予想システム
REM ダブルクリックで自動実行

setlocal enabledelayedexpansion

REM タイトル設定
title OpenCode Complete Setup - うまなり地蔵AI

REM カラー表示
color 0A

echo.
echo ╔═══════════════════════════════════════════════════════╗
echo ║  🚀 OpenCode Complete Setup                          ║
echo ║     うまなり地蔵AI 競馬予想システム                  ║
echo ║     Automated Full Setup                             ║
echo ╚═══════════════════════════════════════════════════════╝
echo.

REM ディレクトリ確認
if not exist "tools\RUN-ALL.ps1" (
    color 0C
    echo ❌ エラー: tools\RUN-ALL.ps1 が見つかりません
    echo    カレントディレクトリ: %cd%
    echo.
    pause
    exit /b 1
)

REM PowerShell 実行
echo ⏳ PowerShell スクリプトを実行中...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "cd '%cd%'; & '.\tools\RUN-ALL.ps1'"

if %ERRORLEVEL% EQU 0 (
    color 0B
    echo.
    echo ╔═══════════════════════════════════════════════════════╗
    echo ║  ✅ セットアップ成功！                               ║
    echo ╚═══════════════════════════════════════════════════════╝
    echo.
    echo 📝 ログ確認:
    echo    for /f "delims=" %%f in ('dir /b /od tools\logs\opencode-automation-*.log') do set LATEST=%%f
    echo.
    echo 🎯 次のステップ:
    echo    1. PowerShell を開く (Win + X → Terminal)
    echo    2. cd D:\keiba_ai
    echo    3. . tools\opencode-wrapper.ps1
    echo    4. new-agent -AgentName "my_agent"
    echo.
) else (
    color 0C
    echo.
    echo ❌ セットアップに失敗しました
    echo    ログを確認してください: tools\logs\
    echo.
)

pause
