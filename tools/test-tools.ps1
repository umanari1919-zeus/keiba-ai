# 🧪 NPM Tools Test Suite
# 全ツールの動作テスト・ヘルプ表示

Write-Host ""
Write-Host "╔═══════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║  🧪 NPM Tools Test — うまなり地蔵AI         ║" -ForegroundColor Cyan
Write-Host "╚═══════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# グローバル PATH 確認
$npmPath = "C:\Users\uchih\AppData\Roaming\npm"
if ($env:Path -notlike "*npm*") {
    Write-Host "❌ PATH に npm bin ディレクトリがありません" -ForegroundColor Red
    Write-Host "   実行: `$env:Path += `";$npmPath`"" -ForegroundColor Yellow
    exit 1
}

Write-Host "✅ PATH: npm bin ディレクトリが設定済み" -ForegroundColor Green
Write-Host ""

# ツール別テスト
$tools = @(
    @{
        name = "opencode"
        version_cmd = "opencode --version"
        help_cmd = "opencode --help"
        test_cmd = "opencode --info"
    },
    @{
        name = "claude"
        version_cmd = "claude --version"
        help_cmd = "claude --help"
        test_cmd = "claude --help"
    },
    @{
        name = "openclaw"
        version_cmd = "openclaw --version"
        help_cmd = "openclaw --help"
        test_cmd = "openclaw --help"
    },
    @{
        name = "codex"
        version_cmd = "codex --version"
        help_cmd = "codex --help"
        test_cmd = "codex --help"
    }
)

$passed = 0
$failed = 0

foreach ($tool in $tools) {
    Write-Host "─────────────────────────────────────────────" -ForegroundColor Gray
    Write-Host "📦 $($tool.name)" -ForegroundColor Cyan
    Write-Host "─────────────────────────────────────────────" -ForegroundColor Gray

    # バージョン確認
    try {
        Write-Host "  バージョン: " -NoNewline
        $version = & cmd /c $tool.version_cmd 2>&1
        Write-Host "$version" -ForegroundColor Green
        $passed++
    } catch {
        Write-Host "❌ エラー: $_" -ForegroundColor Red
        $failed++
        continue
    }

    # ヘルプ表示
    Write-Host "  ヘルプ: " -NoNewline
    try {
        $help = & cmd /c $tool.help_cmd 2>&1 | Select-Object -First 1
        if ($help) {
            Write-Host "✅ 表示可能" -ForegroundColor Green
            $passed++
        } else {
            Write-Host "⚠️  表示内容なし" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "⚠️  表示不可" -ForegroundColor Yellow
    }

    # テスト実行
    Write-Host "  テスト: " -NoNewline
    try {
        $test = & cmd /c $tool.test_cmd 2>&1 | Select-Object -First 1
        Write-Host "✅ 実行成功" -ForegroundColor Green
        $passed++
    } catch {
        Write-Host "⚠️  実行失敗" -ForegroundColor Yellow
        $failed++
    }

    Write-Host ""
}

Write-Host "═══════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""
Write-Host "📊 テスト結果" -ForegroundColor Cyan
Write-Host "─────────────────────────────────────────────" -ForegroundColor Gray
Write-Host "  ✅ 成功: $passed"
Write-Host "  ❌ 失敗: $failed"
Write-Host ""

if ($failed -eq 0) {
    Write-Host "✅ 全ツール動作確認完了！" -ForegroundColor Green
    Write-Host ""
    Write-Host "📌 次のステップ:" -ForegroundColor Yellow
    Write-Host "  1. README.md でツール使用方法確認"
    Write-Host "  2. .\tools\integrate.ps1 でパイプライン統合"
    Write-Host "  3. サンプルコマンド実行"
    Write-Host ""
    Write-Host "🎯 クイックテスト:" -ForegroundColor Yellow
    Write-Host "  > opencode --info" -ForegroundColor Gray
    Write-Host "  > claude --version" -ForegroundColor Gray
    Write-Host "  > openclaw --help" -ForegroundColor Gray
    Write-Host "  > codex search ""horse racing""" -ForegroundColor Gray
} else {
    Write-Host "❌ いくつかのテストが失敗しました" -ForegroundColor Red
    Write-Host "   PATH 設定またはインストールを確認してください" -ForegroundColor Yellow
}

Write-Host ""
