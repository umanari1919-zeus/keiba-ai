@echo off
REM 廃止済みモデルファイル削除スクリプト（約7.5GB解放）
REM model_v8.pkl は削除しません

echo === 廃止モデル削除 ===
echo 削除対象:
echo   model_v2.pkl  (7.2GB)
echo   model_v3.pkl  (42MB)
echo   model_v4.pkl  (41MB)
echo   model_v5.pkl  (43MB)
echo   model_v6.pkl  (40MB)
echo   model_v7.pkl  (85MB)
echo.

set /p confirm=削除してよいですか？ [y/N]:
if /i not "%confirm%"=="y" (
    echo キャンセルしました
    pause
    exit /b
)

cd /d "%~dp0"
del /f model_v2.pkl 2>nul && echo   model_v2.pkl 削除完了 || echo   model_v2.pkl スキップ
del /f model_v3.pkl 2>nul && echo   model_v3.pkl 削除完了 || echo   model_v3.pkl スキップ
del /f model_v4.pkl 2>nul && echo   model_v4.pkl 削除完了 || echo   model_v4.pkl スキップ
del /f model_v5.pkl 2>nul && echo   model_v5.pkl 削除完了 || echo   model_v5.pkl スキップ
del /f model_v6.pkl 2>nul && echo   model_v6.pkl 削除完了 || echo   model_v6.pkl スキップ
del /f model_v7.pkl 2>nul && echo   model_v7.pkl 削除完了 || echo   model_v7.pkl スキップ

echo.
echo === 残ファイル確認 ===
dir model_v*.pkl 2>nul
echo.
echo model_v8.pkl は保持されています
pause
