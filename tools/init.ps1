# 🚀 NPM Tools Initialization
# 全ツールの初期セットアップ・PATH 設定・環境変数設定

Write-Host ""
Write-Host "╔═══════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║  🚀 NPM Tools Initialize — うまなり地蔵AI    ║" -ForegroundColor Cyan
Write-Host "╚═══════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# STEP 1: PATH 設定
Write-Host "📍 Step 1: PATH 環境変数設定" -ForegroundColor Magenta
Write-Host "─────────────────────────────────────────────" -ForegroundColor Gray

$npmPath = "C:\Users\uchih\AppData\Roaming\npm"
$currentPath = [System.Environment]::GetEnvironmentVariable("Path", "User")

if ($currentPath -like "*npm*") {
    Write-Host "✅ PATH に npm bin ディレクトリが既に設定されています" -ForegroundColor Green
} else {
    Write-Host "⏳ PATH に npm bin ディレクトリを追加中..." -ForegroundColor Yellow

    try {
        [System.Environment]::SetEnvironmentVariable(
            "Path",
            $currentPath + ";$npmPath",
            "User"
        )
        Write-Host "✅ PATH 設定完了: $npmPath" -ForegroundColor Green
        Write-Host "⚠️  PowerShell を再起動してください" -ForegroundColor Yellow
    } catch {
        Write-Host "❌ PATH 設定失敗: $_" -ForegroundColor Red
        exit 1
    }
}

Write-Host ""

# STEP 2: 環境変数テンプレートチェック
Write-Host "🔑 Step 2: 環境変数設定確認" -ForegroundColor Magenta
Write-Host "─────────────────────────────────────────────" -ForegroundColor Gray

$envFile = ".env"
$envExists = Test-Path $envFile

if ($envExists) {
    Write-Host "✅ $envFile が存在します" -ForegroundColor Green
    $content = Get-Content $envFile

    $hasClaudeKey = $content | Select-String "CLAUDE_API_KEY"
    $hasOpenCodeKey = $content | Select-String "OPENCODE_API_KEY"
    $hasCodexKey = $content | Select-String "CODEX_API_KEY"

    if ($hasClaudeKey) {
        Write-Host "   ✅ CLAUDE_API_KEY: 設定済み" -ForegroundColor Green
    } else {
        Write-Host "   ⚠️  CLAUDE_API_KEY: 未設定（Anthropic API キーが必要）" -ForegroundColor Yellow
    }

    if ($hasCodexKey) {
        Write-Host "   ✅ CODEX_API_KEY: 設定済み" -ForegroundColor Green
    } else {
        Write-Host "   ⚠️  CODEX_API_KEY: 未設定（OpenAI API キーが必要）" -ForegroundColor Yellow
    }
} else {
    Write-Host "⚠️  .env ファイルが見つかりません" -ForegroundColor Yellow
    Write-Host "   作成コマンド: copy .env.template .env" -ForegroundColor Gray
}

Write-Host ""

# STEP 3: ツールディレクトリ作成
Write-Host "📁 Step 3: ツールディレクトリ確保" -ForegroundColor Magenta
Write-Host "─────────────────────────────────────────────" -ForegroundColor Gray

$dirs = @("tools\logs", "docs", "tools\scripts")

foreach ($dir in $dirs) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force > $null
        Write-Host "✅ 作成: $dir" -ForegroundColor Green
    } else {
        Write-Host "✅ 存在: $dir" -ForegroundColor Green
    }
}

Write-Host ""

# STEP 4: ツール動作確認
Write-Host "🧪 Step 4: ツール動作確認" -ForegroundColor Magenta
Write-Host "─────────────────────────────────────────────" -ForegroundColor Gray

$tools = @("opencode", "claude", "openclaw", "codex")
$allOk = $true

foreach ($tool in $tools) {
    try {
        $output = & cmd /c "$tool --version" 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✅ $tool: $output" -ForegroundColor Green
        } else {
            Write-Host "⚠️  $tool: 応答がありません" -ForegroundColor Yellow
            $allOk = $false
        }
    } catch {
        Write-Host "❌ $tool: 見つかりません" -ForegroundColor Red
        $allOk = $false
    }
}

Write-Host ""

# STEP 5: 設定ファイル確認
Write-Host "⚙️  Step 5: 設定ファイル確認" -ForegroundColor Magenta
Write-Host "─────────────────────────────────────────────" -ForegroundColor Gray

if (Test-Path "tools\config.json") {
    Write-Host "✅ tools\config.json: 存在" -ForegroundColor Green
} else {
    Write-Host "⚠️  tools\config.json: 未作成" -ForegroundColor Yellow
}

if (Test-Path ".opencode\config.json") {
    Write-Host "✅ .opencode\config.json: 存在" -ForegroundColor Green
} else {
    Write-Host "ℹ️  .opencode\config.json: opencode の初回実行時に自動作成" -ForegroundColor Cyan
}

if (Test-Path ".claude\settings.local.json") {
    Write-Host "✅ .claude\settings.local.json: 存在" -ForegroundColor Green
} else {
    Write-Host "ℹ️  .claude\settings.local.json: claude の初回実行時に自動作成" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "╔═══════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║  ✅ セットアップ完了！" -ForegroundColor Cyan
Write-Host "╚═══════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

Write-Host "📌 次のステップ:" -ForegroundColor Yellow
Write-Host ""
Write-Host "  1️⃣  PowerShell を再起動（新しいウィンドウで）"
Write-Host "  2️⃣  .\tools\test-tools.ps1 で全ツール動作テスト"
Write-Host "  3️⃣  .\tools\integrate.ps1 でパイプライン統合"
Write-Host "  4️⃣  README.md でツール使用方法確認"
Write-Host ""

if (-not $allOk) {
    Write-Host "⚠️  いくつかのツールが見つかりません。PATH 設定後、PowerShell を再起動してください。" -ForegroundColor Yellow
}

Write-Host ""
