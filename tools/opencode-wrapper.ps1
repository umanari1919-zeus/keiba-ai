# 🎯 OpenCode Wrapper Functions
# OpenCode を簡単に使うための PowerShell ラッパー関数集

Write-Host "📦 OpenCode Wrapper Functions Loading..." -ForegroundColor Cyan

# ============================================================================
# FUNCTION 1: エージェント生成
# ============================================================================
function New-Agent {
    param(
        [Parameter(Mandatory=$true)]
        [string]$AgentName,

        [Parameter(Mandatory=$false)]
        [string]$Description = "新しいエージェント",

        [Parameter(Mandatory=$false)]
        [string]$Template = "agent_pattern_v2",

        [Parameter(Mandatory=$false)]
        [string]$OutputDir = "agents"
    )

    Write-Host ""
    Write-Host "🤖 Creating Agent: $AgentName" -ForegroundColor Cyan
    Write-Host "─────────────────────────────────────────" -ForegroundColor Gray

    $agentFile = "$OutputDir\${AgentName}_agent.py"

    try {
        # OpenCode で生成
        Write-Host "⏳ Generating with OpenCode..." -ForegroundColor Yellow
        opencode generate `
            --type "agent" `
            --name "$AgentName" `
            --template "$Template" `
            --description "$Description" `
            --output "$agentFile"

        if ($LASTEXITCODE -eq 0) {
            Write-Host "✅ Agent created: $agentFile" -ForegroundColor Green

            # ファイル確認
            if (Test-Path $agentFile) {
                $size = (Get-Item $agentFile).Length
                Write-Host "   Size: $size bytes" -ForegroundColor Gray
                Write-Host ""
                Write-Host "📝 Preview:" -ForegroundColor Cyan
                Get-Content $agentFile | Select-Object -First 20
                Write-Host "..."
            }

            return $agentFile
        } else {
            Write-Host "❌ Generation failed" -ForegroundColor Red
            return $null
        }
    } catch {
        Write-Host "❌ Error: $_" -ForegroundColor Red
        return $null
    }
}

# ============================================================================
# FUNCTION 2: パイプラインステップ生成
# ============================================================================
function New-PipelineStep {
    param(
        [Parameter(Mandatory=$true)]
        [string]$StepName,

        [Parameter(Mandatory=$false)]
        [string]$Description = "",

        [Parameter(Mandatory=$false)]
        [string]$Phase = "processing"
    )

    Write-Host ""
    Write-Host "🔧 Creating Pipeline Step: $StepName" -ForegroundColor Cyan
    Write-Host "─────────────────────────────────────────" -ForegroundColor Gray

    try {
        opencode generate `
            --type "pipeline_step" `
            --name "$StepName" `
            --phase "$Phase" `
            --description "$Description"

        Write-Host "✅ Pipeline step created" -ForegroundColor Green
    } catch {
        Write-Host "❌ Error: $_" -ForegroundColor Red
    }
}

# ============================================================================
# FUNCTION 3: コード最適化
# ============================================================================
function Optimize-Code {
    param(
        [Parameter(Mandatory=$true)]
        [string]$FilePath,

        [Parameter(Mandatory=$false)]
        [ValidateSet("performance", "readability", "maintainability", "security")]
        [string]$Strategy = "performance",

        [Parameter(Mandatory=$false)]
        [switch]$ApplyChanges
    )

    Write-Host ""
    Write-Host "⚡ Optimizing Code: $FilePath" -ForegroundColor Cyan
    Write-Host "─────────────────────────────────────────" -ForegroundColor Gray
    Write-Host "Strategy: $Strategy" -ForegroundColor Gray

    if (-not (Test-Path $FilePath)) {
        Write-Host "❌ File not found: $FilePath" -ForegroundColor Red
        return
    }

    try {
        Write-Host "⏳ Analyzing..." -ForegroundColor Yellow
        opencode optimize `
            --input "$FilePath" `
            --strategy "$Strategy" `
            $(if ($ApplyChanges) { "--apply" })

        Write-Host "✅ Optimization complete" -ForegroundColor Green
    } catch {
        Write-Host "❌ Error: $_" -ForegroundColor Red
    }
}

# ============================================================================
# FUNCTION 4: コード分析
# ============================================================================
function Analyze-Codebase {
    param(
        [Parameter(Mandatory=$false)]
        [string]$Directory = "pipeline_v2",

        [Parameter(Mandatory=$false)]
        [switch]$Detailed,

        [Parameter(Mandatory=$false)]
        [switch]$GenerateReport
    )

    Write-Host ""
    Write-Host "🔍 Analyzing Codebase: $Directory" -ForegroundColor Cyan
    Write-Host "─────────────────────────────────────────" -ForegroundColor Gray

    if (-not (Test-Path $Directory)) {
        Write-Host "❌ Directory not found: $Directory" -ForegroundColor Red
        return
    }

    try {
        Write-Host "⏳ Analyzing..." -ForegroundColor Yellow
        opencode analyze `
            --dir "$Directory" `
            $(if ($Detailed) { "--detailed" }) `
            $(if ($GenerateReport) { "--report" })

        Write-Host "✅ Analysis complete" -ForegroundColor Green
    } catch {
        Write-Host "❌ Error: $_" -ForegroundColor Red
    }
}

# ============================================================================
# FUNCTION 5: テストコード生成
# ============================================================================
function New-Tests {
    param(
        [Parameter(Mandatory=$true)]
        [string]$SourceFile,

        [Parameter(Mandatory=$false)]
        [string]$TestDir = "tests",

        [Parameter(Mandatory=$false)]
        [ValidateSet("unittest", "pytest")]
        [string]$Framework = "pytest"
    )

    Write-Host ""
    Write-Host "🧪 Generating Tests: $SourceFile" -ForegroundColor Cyan
    Write-Host "─────────────────────────────────────────" -ForegroundColor Gray

    if (-not (Test-Path $SourceFile)) {
        Write-Host "❌ File not found: $SourceFile" -ForegroundColor Red
        return
    }

    $fileName = (Get-Item $SourceFile).BaseName
    $testFile = "$TestDir\test_${fileName}.py"

    try {
        Write-Host "⏳ Generating tests..." -ForegroundColor Yellow
        opencode generate `
            --type "tests" `
            --input "$SourceFile" `
            --framework "$Framework" `
            --output "$testFile"

        Write-Host "✅ Tests created: $testFile" -ForegroundColor Green
    } catch {
        Write-Host "❌ Error: $_" -ForegroundColor Red
    }
}

# ============================================================================
# FUNCTION 6: ドキュメント生成
# ============================================================================
function New-Documentation {
    param(
        [Parameter(Mandatory=$true)]
        [string]$SourceFile,

        [Parameter(Mandatory=$false)]
        [string]$OutputDir = "docs",

        [Parameter(Mandatory=$false)]
        [ValidateSet("markdown", "rst", "html")]
        [string]$Format = "markdown"
    )

    Write-Host ""
    Write-Host "📚 Generating Documentation: $SourceFile" -ForegroundColor Cyan
    Write-Host "─────────────────────────────────────────" -ForegroundColor Gray

    if (-not (Test-Path $SourceFile)) {
        Write-Host "❌ File not found: $SourceFile" -ForegroundColor Red
        return
    }

    $fileName = (Get-Item $SourceFile).BaseName
    $docFile = "$OutputDir\${fileName}.$(if ($Format -eq 'markdown') { 'md' } elseif ($Format -eq 'rst') { 'rst' } else { 'html' })"

    try {
        Write-Host "⏳ Generating documentation..." -ForegroundColor Yellow
        opencode generate `
            --type "documentation" `
            --input "$SourceFile" `
            --format "$Format" `
            --output "$docFile"

        Write-Host "✅ Documentation created: $docFile" -ForegroundColor Green
    } catch {
        Write-Host "❌ Error: $_" -ForegroundColor Red
    }
}

# ============================================================================
# FUNCTION 7: 機能別コード検索・生成
# ============================================================================
function Find-Pattern {
    param(
        [Parameter(Mandatory=$true)]
        [string]$Pattern,

        [Parameter(Mandatory=$false)]
        [string]$SearchDir = ".",

        [Parameter(Mandatory=$false)]
        [switch]$Generate
    )

    Write-Host ""
    Write-Host "🔎 Searching for pattern: $Pattern" -ForegroundColor Cyan
    Write-Host "─────────────────────────────────────────" -ForegroundColor Gray

    try {
        opencode search --pattern "$Pattern" --dir "$SearchDir"

        if ($Generate) {
            Write-Host ""
            Write-Host "Would you like to generate an implementation? (Y/n)" -ForegroundColor Yellow
            $response = Read-Host

            if ($response -ne "n") {
                opencode generate --pattern "$Pattern" --type "implementation"
            }
        }
    } catch {
        Write-Host "❌ Error: $_" -ForegroundColor Red
    }
}

# ============================================================================
# FUNCTION 8: 一括最適化
# ============================================================================
function Optimize-All {
    param(
        [Parameter(Mandatory=$false)]
        [string]$RootDir = ".",

        [Parameter(Mandatory=$false)]
        [ValidateSet("performance", "readability", "maintainability")]
        [string]$Strategy = "performance",

        [Parameter(Mandatory=$false)]
        [switch]$Apply
    )

    Write-Host ""
    Write-Host "🚀 Optimizing all code in: $RootDir" -ForegroundColor Cyan
    Write-Host "─────────────────────────────────────────" -ForegroundColor Gray
    Write-Host "Strategy: $Strategy" -ForegroundColor Gray

    try {
        Write-Host "⏳ Starting optimization..." -ForegroundColor Yellow
        opencode analyze --dir "$RootDir" --detailed
        opencode apply-suggestions `
            --strategy "$Strategy" `
            $(if ($Apply) { "--auto" })

        Write-Host "✅ Optimization complete" -ForegroundColor Green
    } catch {
        Write-Host "❌ Error: $_" -ForegroundColor Red
    }
}

# ============================================================================
# FUNCTION 9: 情報取得
# ============================================================================
function Show-OpenCodeInfo {
    Write-Host ""
    Write-Host "╔═══════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "║  ℹ️  OpenCode Information                 ║" -ForegroundColor Cyan
    Write-Host "╚═══════════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""

    Write-Host "📦 Version:" -ForegroundColor Cyan
    opencode --version

    Write-Host ""
    Write-Host "⚙️  Configuration:" -ForegroundColor Cyan
    Write-Host "   Config: .opencode/config.json" -ForegroundColor Gray
    Write-Host "   Model: $(opencode config --get model)" -ForegroundColor Gray
    Write-Host "   Provider: $(opencode config --get preferredProvider)" -ForegroundColor Gray

    Write-Host ""
    Write-Host "📊 Available Templates:" -ForegroundColor Cyan
    opencode list --templates

    Write-Host ""
}

# ============================================================================
# ALIAS ショートカット
# ============================================================================
Set-Alias -Name new-agent -Value New-Agent -Force
Set-Alias -Name new-pipeline -Value New-PipelineStep -Force
Set-Alias -Name optimize -Value Optimize-Code -Force
Set-Alias -Name analyze -Value Analyze-Codebase -Force
Set-Alias -Name new-tests -Value New-Tests -Force
Set-Alias -Name new-docs -Value New-Documentation -Force
Set-Alias -Name find-pattern -Value Find-Pattern -Force
Set-Alias -Name optimize-all -Value Optimize-All -Force
Set-Alias -Name oc-info -Value Show-OpenCodeInfo -Force

Write-Host ""
Write-Host "✅ OpenCode Wrapper Functions loaded!" -ForegroundColor Green
Write-Host ""
Write-Host "📌 利用可能なコマンド:" -ForegroundColor Yellow
Write-Host "   new-agent -AgentName 'analyzer'         # エージェント生成"
Write-Host "   optimize -FilePath 'agents/train.py'    # コード最適化"
Write-Host "   analyze -Directory 'pipeline_v2'        # 分析"
Write-Host "   new-tests -SourceFile 'agents/test.py'  # テスト生成"
Write-Host "   new-docs -SourceFile 'agents/train.py'  # ドキュメント生成"
Write-Host "   optimize-all -Apply                     # 全体最適化"
Write-Host "   oc-info                                 # 情報表示"
Write-Host ""
