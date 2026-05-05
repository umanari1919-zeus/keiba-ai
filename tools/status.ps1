# 🛠️ NPM Tools Status Check
# 全ツールのバージョン・PATH・設定状態を確認

Write-Host "═══════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  🛠️  NPM Tools Status — うまなり地蔵AI" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# PATH 確認
$npmPath = "C:\Users\uchih\AppData\Roaming\npm"
$pathExists = $env:Path -split ";" | Where-Object { $_ -eq $npmPath }

if ($pathExists) {
    Write-Host "✅ PATH: npm bin ディレクトリが設定済み" -ForegroundColor Green
} else {
    Write-Host "❌ PATH: npm bin ディレクトリが見つかりません" -ForegroundColor Red
    Write-Host "   以下を実行して PATH に追加してください:" -ForegroundColor Yellow
    Write-Host "   `$env:Path += `";$npmPath`"" -ForegroundColor Gray
}

Write-Host ""
Write-Host "─────────────────────────────────────────────" -ForegroundColor Gray

# ツール確認
$tools = @(
    @{ name = "opencode"; cmd = "opencode --version" },
    @{ name = "claude"; cmd = "claude --version" },
    @{ name = "openclaw"; cmd = "openclaw --version" },
    @{ name = "codex"; cmd = "codex --version" }
)

foreach ($tool in $tools) {
    Write-Host ""
    Write-Host "📦 $($tool.name)" -ForegroundColor Cyan

    try {
        $output = & cmd /c $tool.cmd 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "   ✅ インストール済み: $output" -ForegroundColor Green
        } else {
            Write-Host "   ❌ コマンド実行失敗" -ForegroundColor Red
        }
    } catch {
        Write-Host "   ❌ 見つかりません: $_" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "─────────────────────────────────────────────" -ForegroundColor Gray
Write-Host ""

# 設定ファイル確認
Write-Host "📋 Configuration Files" -ForegroundColor Cyan
$configs = @(
    @{ path = ".opencode\config.json"; tool = "opencode" },
    @{ path = ".claude\settings.local.json"; tool = "claude" },
    @{ path = "tools\config.json"; tool = "integration" }
)

foreach ($config in $configs) {
    $fullPath = Join-Path (Get-Location) $config.path
    if (Test-Path $fullPath) {
        Write-Host "   ✅ $($config.tool): $($config.path)" -ForegroundColor Green
    } else {
        Write-Host "   ❌ $($config.tool): $($config.path) (見つかりません)" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "─────────────────────────────────────────────" -ForegroundColor Gray
Write-Host ""

# npm グローバルパッケージ確認
Write-Host "📚 Global npm Packages" -ForegroundColor Cyan
$pkgs = npm list -g --depth=0 2>$null | Select-String "@anthropic-ai|@openai|opencode|openclaw"
if ($pkgs) {
    $pkgs | ForEach-Object {
        Write-Host "   ✅ $_" -ForegroundColor Green
    }
} else {
    Write-Host "   ⚠️  パッケージ情報を取得できません" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "═══════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  📌 次のステップ:" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""
Write-Host "  1. .\tools\init.ps1         → 初期セットアップ実行"
Write-Host "  2. .\tools\test-tools.ps1   → 全ツール動作テスト"
Write-Host "  3. .\tools\integrate.ps1    → パイプラインと統合"
Write-Host ""
