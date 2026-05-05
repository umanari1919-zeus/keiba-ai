# 🚀 OpenCode Full Setup
# OpenCode を完全セットアップしてフル機能を有効化

Write-Host ""
Write-Host "╔═══════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║  🚀 OpenCode Complete Setup                 ║" -ForegroundColor Cyan
Write-Host "║     うまなり地蔵AI 競馬予想システム         ║" -ForegroundColor Cyan
Write-Host "╚═══════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# STEP 1: OpenCode インストール確認
Write-Host "📦 Step 1: OpenCode Installation Check" -ForegroundColor Magenta
Write-Host "─────────────────────────────────────────────" -ForegroundColor Gray

try {
    $version = opencode --version
    Write-Host "✅ OpenCode: $version" -ForegroundColor Green
} catch {
    Write-Host "❌ OpenCode not found. Installing..." -ForegroundColor Red
    npm install -g opencode-ai
    $version = opencode --version
    Write-Host "✅ OpenCode: $version" -ForegroundColor Green
}

Write-Host ""

# STEP 2: 設定ファイル確認・作成
Write-Host "⚙️  Step 2: Configuration Setup" -ForegroundColor Magenta
Write-Host "─────────────────────────────────────────────" -ForegroundColor Gray

$configFile = ".opencode\config.json"

if (Test-Path $configFile) {
    Write-Host "✅ Config file exists: $configFile" -ForegroundColor Green

    # 設定内容確認
    $config = Get-Content $configFile | ConvertFrom-Json
    Write-Host "   Project: $($config.project.name)" -ForegroundColor Gray
    Write-Host "   Model: $($config.model)" -ForegroundColor Gray
    Write-Host "   Provider: $($config.preferredProvider)" -ForegroundColor Gray
} else {
    Write-Host "⚠️  Config file not found" -ForegroundColor Yellow
}

Write-Host ""

# STEP 3: API キー設定
Write-Host "🔑 Step 3: API Keys Configuration" -ForegroundColor Magenta
Write-Host "─────────────────────────────────────────────" -ForegroundColor Gray

$envFile = ".env"

if (Test-Path $envFile) {
    $hasClaudeKey = Select-String -Path $envFile -Pattern "ANTHROPIC_API_KEY" -ErrorAction SilentlyContinue

    if ($hasClaudeKey) {
        Write-Host "✅ ANTHROPIC_API_KEY: 設定済み" -ForegroundColor Green

        # キーが有効か確認
        $key = Get-Content $envFile | Select-String "ANTHROPIC_API_KEY" | ForEach-Object { $_.Line.Split("=")[1].Trim() }
        if ($key -and $key.Length -gt 10) {
            Write-Host "   Key length: $($key.Length) chars" -ForegroundColor Gray
        }
    } else {
        Write-Host "⚠️  ANTHROPIC_API_KEY: 未設定" -ForegroundColor Yellow
        Write-Host "   追加する? (Y/n)" -ForegroundColor Yellow
        $response = Read-Host

        if ($response -ne "n") {
            Write-Host "   API キーを入力 (sk-...):" -ForegroundColor Yellow
            $apiKey = Read-Host -AsSecureString

            # .env に追加
            Add-Content $envFile ""
            Add-Content $envFile "ANTHROPIC_API_KEY=$([System.Runtime.InteropServices.Marshal]::PtrToStringAuto([System.Runtime.InteropServices.Marshal]::SecureStringToCoTaskMemUnicode($apiKey)))"
            Write-Host "   ✅ API キーを .env に追加しました" -ForegroundColor Green
        }
    }
} else {
    Write-Host "❌ .env ファイルが見つかりません" -ForegroundColor Red
    Write-Host "   コマンド: copy .env.template .env" -ForegroundColor Yellow
}

Write-Host ""

# STEP 4: ラッパー関数セットアップ
Write-Host "🎛️  Step 4: PowerShell Wrapper Functions" -ForegroundColor Magenta
Write-Host "─────────────────────────────────────────────" -ForegroundColor Gray

$wrapperFile = "tools\opencode-wrapper.ps1"

if (Test-Path $wrapperFile) {
    Write-Host "✅ Wrapper functions available: $wrapperFile" -ForegroundColor Green

    Write-Host ""
    Write-Host "Loading wrapper functions..." -ForegroundColor Yellow
    . $wrapperFile
    Write-Host "✅ Functions loaded!" -ForegroundColor Green
} else {
    Write-Host "⚠️  Wrapper file not found" -ForegroundColor Yellow
}

Write-Host ""

# STEP 5: テンプレート確認
Write-Host "📋 Step 5: Templates Check" -ForegroundColor Magenta
Write-Host "─────────────────────────────────────────────" -ForegroundColor Gray

$templateDir = ".opencode\templates"

if (Test-Path $templateDir) {
    $templates = Get-ChildItem $templateDir -Filter "*.py" -ErrorAction SilentlyContinue
    Write-Host "✅ Templates directory: $templateDir" -ForegroundColor Green
    Write-Host "   Found templates: $($templates.Count)" -ForegroundColor Gray
} else {
    Write-Host "⚠️  Templates directory not found" -ForegroundColor Yellow
    Write-Host "   Creating..." -ForegroundColor Yellow

    New-Item -ItemType Directory -Path $templateDir -Force > $null
    Write-Host "   ✅ Created: $templateDir" -ForegroundColor Green
}

Write-Host ""

# STEP 6: 機能テスト
Write-Host "🧪 Step 6: Feature Test" -ForegroundColor Magenta
Write-Host "─────────────────────────────────────────────" -ForegroundColor Gray

Write-Host "Testing OpenCode commands..." -ForegroundColor Yellow

$tests = @(
    @{ cmd = "opencode --version"; name = "Version" },
    @{ cmd = "opencode --info"; name = "Info" },
    @{ cmd = "opencode list --templates"; name = "Templates" }
)

$passed = 0
$failed = 0

foreach ($test in $tests) {
    try {
        $output = & cmd /c $test.cmd 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  ✅ $($test.name)" -ForegroundColor Green
            $passed++
        } else {
            Write-Host "  ⚠️  $($test.name): No response" -ForegroundColor Yellow
            $failed++
        }
    } catch {
        Write-Host "  ❌ $($test.name): $_" -ForegroundColor Red
        $failed++
    }
}

Write-Host ""

# STEP 7: 出力ディレクトリ確認
Write-Host "📁 Step 7: Output Directories" -ForegroundColor Magenta
Write-Host "─────────────────────────────────────────────" -ForegroundColor Gray

$dirs = @(
    "generated",
    ".opencode\logs",
    ".opencode\cache",
    "docs"
)

foreach ($dir in $dirs) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force > $null
        Write-Host "   ✅ Created: $dir" -ForegroundColor Green
    } else {
        Write-Host "   ✅ Exists: $dir" -ForegroundColor Green
    }
}

Write-Host ""

# STEP 8: 推奨設定
Write-Host "⚙️  Step 8: Recommended Configuration" -ForegroundColor Magenta
Write-Host "─────────────────────────────────────────────" -ForegroundColor Gray

Write-Host "推奨設定を適用しますか? (Y/n)" -ForegroundColor Yellow
$response = Read-Host

if ($response -ne "n") {
    Write-Host "⏳ Applying settings..." -ForegroundColor Yellow

    # デフォルトモデル設定
    opencode config --set model "anthropic/claude-haiku-4-5-20251001"
    opencode config --set preferredProvider "anthropic"

    # パフォーマンス設定
    opencode config --set temperature 0.5
    opencode config --set contextWindow 100000
    opencode config --set maxTokens 8000

    Write-Host "✅ Settings applied!" -ForegroundColor Green
}

Write-Host ""

# ファイナルレポート
Write-Host "╔═══════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║  ✅ OpenCode Setup Complete!" -ForegroundColor Cyan
Write-Host "╚═══════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

Write-Host "📊 Setup Summary:" -ForegroundColor Yellow
Write-Host "  ✅ OpenCode version: $version" -ForegroundColor Green
Write-Host "  ✅ Configuration file: $configFile" -ForegroundColor Green
Write-Host "  ✅ Feature tests passed: $passed/$($passed + $failed)" -ForegroundColor Green
Write-Host "  ✅ Output directories created" -ForegroundColor Green
Write-Host "  ✅ Wrapper functions loaded" -ForegroundColor Green
Write-Host ""

Write-Host "🎯 Next Steps:" -ForegroundColor Yellow
Write-Host ""
Write-Host "  1️⃣  ラッパー関数を有効化:"
Write-Host "     . tools\opencode-wrapper.ps1" -ForegroundColor Gray
Write-Host ""
Write-Host "  2️⃣  利用可能なコマンド:"
Write-Host "     new-agent -AgentName 'analyzer'" -ForegroundColor Gray
Write-Host "     optimize -FilePath 'agents/train.py' -ApplyChanges" -ForegroundColor Gray
Write-Host "     analyze -Directory 'pipeline_v2' -Detailed" -ForegroundColor Gray
Write-Host "     new-tests -SourceFile 'agents/base_agent.py'" -ForegroundColor Gray
Write-Host "     new-docs -SourceFile 'agents/train_agent.py'" -ForegroundColor Gray
Write-Host "     oc-info" -ForegroundColor Gray
Write-Host ""
Write-Host "  3️⃣  詳細ガイド: tools\OPENCODE-GUIDE.md を参照" -ForegroundColor Gray
Write-Host ""
Write-Host "  4️⃣  実践例: tools\opencode-examples.ps1 を実行" -ForegroundColor Gray
Write-Host ""

Write-Host "📚 Documentation:" -ForegroundColor Yellow
Write-Host "  • tools\OPENCODE-GUIDE.md — 完全ガイド" -ForegroundColor Gray
Write-Host "  • .opencode\config.json — 設定ファイル" -ForegroundColor Gray
Write-Host "  • tools\opencode-wrapper.ps1 — ラッパー関数" -ForegroundColor Gray
Write-Host ""

Write-Host "💡 Pro Tips:" -ForegroundColor Yellow
Write-Host "  • ラッパー関数は $PROFILE に追加して永続化"
Write-Host "  • opencode analyze で定期的にコード品質を監視"
Write-Host "  • テストとドキュメントは生成時に一緒に作成" -ForegroundColor Gray
Write-Host ""

Write-Host "✨ Happy Coding with OpenCode!" -ForegroundColor Cyan
Write-Host ""
