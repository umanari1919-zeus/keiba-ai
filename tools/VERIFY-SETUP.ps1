# 🔍 OpenCode セットアップ検証スクリプト
# セットアップが正常に完了したかチェック

Write-Host ""
Write-Host "╔════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║  🔍 OpenCode セットアップ検証                 ║" -ForegroundColor Cyan
Write-Host "║     うまなり地蔵AI                           ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

$checks = @()
$passed = 0
$failed = 0

function Test-Check {
    param([string]$Name, [scriptblock]$Test)

    Write-Host "📋 $Name..." -NoNewline
    try {
        $result = & $Test
        if ($result) {
            Write-Host " ✅ OK" -ForegroundColor Green
            return $true
        } else {
            Write-Host " ❌ FAIL" -ForegroundColor Red
            return $false
        }
    } catch {
        Write-Host " ❌ ERROR: $_" -ForegroundColor Red
        return $false
    }
}

# === VERIFICATION CHECKS ===

Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Gray
Write-Host "1️⃣  基本確認" -ForegroundColor Yellow
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Gray
Write-Host ""

if (Test-Check "OpenCode がインストール済み" { opencode --version 2>$null }) { $passed++ } else { $failed++ }
if (Test-Check ".env ファイルが存在" { Test-Path .env }) { $passed++ } else { $failed++ }
if (Test-Check ".opencode/config.json が存在" { Test-Path .opencode/config.json }) { $passed++ } else { $failed++ }
if (Test-Check "ANTHROPIC_API_KEY が設定済み" { (Get-Content .env 2>$null | Select-String "ANTHROPIC_API_KEY") }) { $passed++ } else { $failed++ }

Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Gray
Write-Host "2️⃣  ディレクトリ確認" -ForegroundColor Yellow
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Gray
Write-Host ""

if (Test-Check "generated/ ディレクトリ" { Test-Path generated }) { $passed++ } else { $failed++ }
if (Test-Check ".opencode/logs/ ディレクトリ" { Test-Path .opencode/logs }) { $passed++ } else { $failed++ }
if (Test-Check "tests/ ディレクトリ" { Test-Path tests }) { $passed++ } else { $failed++ }
if (Test-Check "docs/ ディレクトリ" { Test-Path docs }) { $passed++ } else { $failed++ }

Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Gray
Write-Host "3️⃣  ラッパー関数確認" -ForegroundColor Yellow
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Gray
Write-Host ""

# ラッパー関数をロード
. tools\opencode-wrapper.ps1 2>$null

if (Test-Check "new-agent 関数" { Get-Command new-agent -ErrorAction SilentlyContinue }) { $passed++ } else { $failed++ }
if (Test-Check "optimize 関数" { Get-Command optimize -ErrorAction SilentlyContinue }) { $passed++ } else { $failed++ }
if (Test-Check "analyze 関数" { Get-Command analyze -ErrorAction SilentlyContinue }) { $passed++ } else { $failed++ }
if (Test-Check "new-tests 関数" { Get-Command new-tests -ErrorAction SilentlyContinue }) { $passed++ } else { $failed++ }
if (Test-Check "new-docs 関数" { Get-Command new-docs -ErrorAction SilentlyContinue }) { $passed++ } else { $failed++ }

Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Gray
Write-Host "4️⃣  ドキュメント確認" -ForegroundColor Yellow
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Gray
Write-Host ""

if (Test-Check "START-HERE.txt" { Test-Path tools\START-HERE.txt }) { $passed++ } else { $failed++ }
if (Test-Check "AUTO-START.bat" { Test-Path tools\AUTO-START.bat }) { $passed++ } else { $failed++ }
if (Test-Check "AUTOMATED-SETUP-GUIDE.md" { Test-Path tools\AUTOMATED-SETUP-GUIDE.md }) { $passed++ } else { $failed++ }
if (Test-Check "OPENCODE-GUIDE.md" { Test-Path tools\OPENCODE-GUIDE.md }) { $passed++ } else { $failed++ }

Write-Host ""

# === SUMMARY ===
$total = $passed + $failed
$percentage = if ($total -gt 0) { [math]::Round(($passed / $total) * 100) } else { 0 }

Write-Host "╔════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║  ✅ 検証結果                                  ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""
Write-Host "  成功: $passed / $total ($percentage%)" -ForegroundColor Green
Write-Host "  失敗: $failed / $total" -ForegroundColor $(if ($failed -gt 0) { "Red" } else { "Green" })
Write-Host ""

if ($failed -eq 0) {
    Write-Host "✅ セットアップは正常に完了しました！" -ForegroundColor Green
    Write-Host ""
    Write-Host "🎯 次のステップ:" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  1. ラッパー関数をロード（既にロード済み）" -ForegroundColor Gray
    Write-Host "  2. 新しいエージェント生成をテスト:" -ForegroundColor Gray
    Write-Host "     new-agent -AgentName 'test_agent'" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  3. コード分析:" -ForegroundColor Gray
    Write-Host "     analyze -Directory agents/ -Detailed" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  4. パイプライン実行:" -ForegroundColor Gray
    Write-Host "     python run_all.py --v2" -ForegroundColor Cyan
    Write-Host ""
} else {
    Write-Host "❌ 一部のチェックが失敗しました。" -ForegroundColor Red
    Write-Host ""
    Write-Host "🔧 トラブルシューティング:" -ForegroundColor Yellow
    Write-Host "  1. tools\AUTOMATED-SETUP-GUIDE.md を参照" -ForegroundColor Gray
    Write-Host "  2. ログファイルを確認: tools\logs\opencode-automation-*.log" -ForegroundColor Gray
    Write-Host "  3. AUTO-START.bat を再実行" -ForegroundColor Gray
    Write-Host ""
}

Write-Host "╚════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

exit $(if ($failed -eq 0) { 0 } else { 1 })
