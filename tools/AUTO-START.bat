@echo off
REM 🎯 OpenCode 完全自動セットアップ
REM ワンクリック起動スクリプト

setlocal enabledelayedexpansion
chcp 65001 > nul

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_ROOT=%%~fI"
cd /d "%PROJECT_ROOT%"

title 🚀 OpenCode 自動セットアップ - うまなり地蔵AI
color 0A

echo.
echo ████████████████████████████████████████████████████████
echo █                                                      █
echo █  🚀 OpenCode 完全自動セットアップ                  █
echo █     うまなり地蔵AI 競馬予想システム                █
echo █                                                      █
echo ████████████████████████████████████████████████████████
echo.

REM === PRE-CHECK ===
echo 📋 [1/3] 前提条件を確認中...
echo.

if not exist ".env" (
    echo ⚠️  警告: .env ファイルが見つかりません
    echo    → でも大丈夫。セットアップで作成できます
    echo.
)

if not exist "tools\RUN-ALL.ps1" (
    color 0C
    echo ❌ エラー: tools\RUN-ALL.ps1 が見つかりません
    echo    プロジェクトルートを確認してください: %PROJECT_ROOT%
    echo.
    pause
    exit /b 1
)

echo ✅ 全ての前提条件が満たされています
echo.

REM === BACKUP ===
echo 📦 [2/3] 既存ファイルをバックアップ中...
echo.

if exist ".opencode\config.json" (
    for /f "tokens=2-4 delims=/ " %%a in ('date /t') do (set mydate=%%c%%a%%b)
    for /f "tokens=1-2 delims=/:" %%a in ('time /t') do (set mytime=%%a%%b)
    copy ".opencode\config.json" ".opencode\config.json.backup.!mydate!-!mytime!" > nul
    echo   ✅ Backed up: .opencode\config.json
)

if exist ".env" (
    for /f "tokens=2-4 delims=/ " %%a in ('date /t') do (set mydate=%%c%%a%%b)
    for /f "tokens=1-2 delims=/:" %%a in ('time /t') do (set mytime=%%a%%b)
    copy ".env" ".env.backup.!mydate!-!mytime!" > nul
    echo   ✅ Backed up: .env
)

echo.

REM === SETUP ===
echo 🚀 [3/3] OpenCode 完全セットアップを実行中...
echo.
echo ────────────────────────────────────────────────────────
echo.

REM PowerShell で RUN-ALL.ps1 を実行
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "cd '%cd%'; $ProgressPreference='Continue'; & '.\tools\RUN-ALL.ps1' *>&1"

set SETUP_RESULT=%ERRORLEVEL%

echo.
echo ────────────────────────────────────────────────────────
echo.

REM === RESULTS ===
if %SETUP_RESULT% EQU 0 (
    color 0B
    echo ✅ セットアップ完了！
    echo.
    echo ████████████████████████████████████████████████████████
    echo █                                                      █
    echo █  ✨ OpenCode が完全に セットアップされました！    █
    echo █                                                      █
    echo ████████████████████████████████████████████████████████
    echo.
    echo 📝 実行ログ:
    echo    %cd%\tools\logs\opencode-automation-*.log
    echo.
    echo 🎯 次のステップ (PowerShell で):
    echo.
    echo    1️⃣  ラッパー関数をロード:
    echo        . tools\opencode-wrapper.ps1
    echo.
    echo    2️⃣  新しいエージェント生成:
    echo        new-agent -AgentName "my_analyzer"
    echo.
    echo    3️⃣  パイプライン分析:
    echo        analyze -Directory pipeline_v2/ -Detailed
    echo.
    echo    4️⃣  コード最適化:
    echo        optimize -FilePath agents/train_agent.py -ApplyChanges
    echo.
    echo    5️⃣  システム情報:
    echo        oc-info
    echo.
) else (
    color 0C
    echo ❌ セットアップに失敗しました
    echo.
    echo 📝 ログを確認してください:
    echo    %cd%\tools\logs\opencode-automation-*.log
    echo.
    echo 🔧 トラブルシューティング:
    echo.
    echo ① PowerShell のバージョン確認:
    echo    powershell -Version
    echo.
    echo ② OpenCode のインストール確認:
    echo    opencode --version
    echo.
    echo ③ .env ファイルの確認:
    echo    type .env ^| findstr "API_KEY"
    echo.
    echo ④ セットアップスクリプトの手動実行:
    echo    powershell -ExecutionPolicy Bypass -File "tools\opencode-setup.ps1"
    echo.
)

pause
exit /b %SETUP_RESULT%
