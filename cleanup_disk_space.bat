@echo off
REM ================================================================
REM うまなり地蔵AI — ディスク容量クリーンアップ（推定 ~8.7GB 解放）
REM
REM 削除対象:
REM   archive\model_v2.pkl             7.2 GB  (廃止モデル)
REM   archive\model_v8.pkl           458 MB  (ルートの model_v8.pkl が本体)
REM   archive\keiba_data_features.csv  536 MB  (旧コピー)
REM   archive\keiba_data.csv           146 MB  (旧コピー)
REM   model_v3〜v7.pkl (ルート)         251 MB  (廃止モデル)
REM   __pycache__ 全体                  ~70 MB  (自動再生成)
REM
REM 保持するもの:
REM   model_v8.pkl (ルート, 111MB) — 現役モデル
REM   archive\secret_envs\           — 認証情報
REM   data\ / logs\ / reports\       — 運用データ
REM ================================================================

cd /d "%~dp0"

echo.
echo ┌──────────────────────────────────────────────┐
echo │  うまなり地蔵AI  ディスク容量クリーンアップ  │
echo └──────────────────────────────────────────────┘
echo.
echo 削除予定ファイル（合計 ~8.7GB）:
echo.

set total_mb=0

REM archive 配下チェック
if exist "archive\model_v2.pkl"            echo   [D] archive\model_v2.pkl             ^(7200 MB^)
if exist "archive\model_v8.pkl"            echo   [D] archive\model_v8.pkl              ^( 458 MB^)
if exist "archive\keiba_data_features.csv" echo   [D] archive\keiba_data_features.csv   ^( 536 MB^)
if exist "archive\keiba_data.csv"          echo   [D] archive\keiba_data.csv            ^( 146 MB^)
REM ルート廃止モデル
if exist "model_v2.pkl" echo   [D] model_v2.pkl                      ^(7200 MB^)
if exist "model_v3.pkl" echo   [D] model_v3.pkl                      ^(  42 MB^)
if exist "model_v4.pkl" echo   [D] model_v4.pkl                      ^(  41 MB^)
if exist "model_v5.pkl" echo   [D] model_v5.pkl                      ^(  43 MB^)
if exist "model_v6.pkl" echo   [D] model_v6.pkl                      ^(  40 MB^)
if exist "model_v7.pkl" echo   [D] model_v7.pkl                      ^(  85 MB^)
echo   [D] __pycache__ ディレクトリ (全体)         ^( ~70 MB^)
echo.
echo 保持するもの:
echo   [K] model_v8.pkl (現役モデル, 111MB)
echo   [K] archive\secret_envs\ (認証情報)
echo   [K] data\, logs\, reports\ (運用データ)
echo.

set /p confirm=上記を削除してよいですか？ [y/N]:
if /i not "%confirm%"=="y" (
    echo キャンセルしました。
    pause
    exit /b 0
)

echo.
echo === archive\ クリーンアップ ===

if exist "archive\model_v2.pkl" (
    del /f "archive\model_v2.pkl" && echo   OK  archive\model_v2.pkl (7.2GB) 削除完了
) else (
    echo   --  archive\model_v2.pkl なし（スキップ）
)

if exist "archive\model_v8.pkl" (
    del /f "archive\model_v8.pkl" && echo   OK  archive\model_v8.pkl (458MB) 削除完了
) else (
    echo   --  archive\model_v8.pkl なし（スキップ）
)

if exist "archive\keiba_data_features.csv" (
    del /f "archive\keiba_data_features.csv" && echo   OK  archive\keiba_data_features.csv (536MB) 削除完了
) else (
    echo   --  archive\keiba_data_features.csv なし（スキップ）
)

if exist "archive\keiba_data.csv" (
    del /f "archive\keiba_data.csv" && echo   OK  archive\keiba_data.csv (146MB) 削除完了
) else (
    echo   --  archive\keiba_data.csv なし（スキップ）
)

echo.
echo === ルート廃止モデル クリーンアップ ===

for %%v in (2 3 4 5 6 7) do (
    if exist "model_v%%v.pkl" (
        del /f "model_v%%v.pkl" && echo   OK  model_v%%v.pkl 削除完了
    )
)

echo.
echo === __pycache__ クリーンアップ ===

for /d /r . %%d in (__pycache__) do (
    if exist "%%d" rd /s /q "%%d" 2>nul
)
echo   OK  __pycache__ 全体を削除しました（Python 実行時に自動再生成されます）

echo.
echo === .pytest_cache クリーンアップ ===

for /d /r . %%d in (.pytest_cache) do (
    if exist "%%d" rd /s /q "%%d" 2>nul
)
echo   OK  .pytest_cache 削除しました

echo.
echo ┌──────────────────────────────────────────────┐
echo │  クリーンアップ完了！                         │
echo │  model_v8.pkl (現役) は保持されています       │
echo │  archive\secret_envs\ は保持されています      │
echo └──────────────────────────────────────────────┘
echo.
echo 現在のルートモデルファイル:
dir /b model_v*.pkl 2>nul
echo.
pause
