# 🔗 NPM Tools Pipeline Integration
# パイプライン・エージェントとツール統合

Write-Host ""
Write-Host "╔═══════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║  🔗 Pipeline Integration Setup               ║" -ForegroundColor Cyan
Write-Host "╚═══════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# 設定確認
Write-Host "📋 Step 1: 統合設定確認" -ForegroundColor Magenta
Write-Host "─────────────────────────────────────────────" -ForegroundColor Gray

$config_json = "tools\config.json"
if (Test-Path $config_json) {
    Write-Host "✅ tools\config.json: 存在" -ForegroundColor Green
    $config = Get-Content $config_json | ConvertFrom-Json
    Write-Host "   プロジェクトルート: $($config.integration.keiba_ai_project.root)" -ForegroundColor Gray
    Write-Host "   パイプライン: $($config.integration.keiba_ai_project.pipeline_dir)" -ForegroundColor Gray
    Write-Host "   エージェント: $($config.integration.keiba_ai_project.agents_dir)" -ForegroundColor Gray
} else {
    Write-Host "❌ tools\config.json が見つかりません" -ForegroundColor Red
    exit 1
}

Write-Host ""

# 統合スクリプト生成
Write-Host "🔧 Step 2: 統合スクリプト生成" -ForegroundColor Magenta
Write-Host "─────────────────────────────────────────────" -ForegroundColor Gray

# Python 統合モジュール
$python_integration = @"
# tools/opencode_integration.py
# opencode との統合 - コード自動生成

import json
import subprocess
import os
from pathlib import Path

class CodeGenerator:
    def __init__(self):
        self.npm_bin = r'C:\Users\uchih\AppData\Roaming\npm'
        self.opencode_cmd = os.path.join(self.npm_bin, 'opencode.cmd')

    def generate(self, step_id: str, template: str = "default", **kwargs):
        '''opencode でコード生成'''
        cmd = [self.opencode_cmd, 'generate', '--type', step_id]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.stdout

    def optimize(self, file_path: str):
        '''ファイルを opencode で最適化'''
        cmd = [self.opencode_cmd, 'optimize', '--input', file_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.stdout

    def analyze(self, dir_path: str):
        '''ディレクトリを analyze'''
        cmd = [self.opencode_cmd, 'analyze', '--dir', dir_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.stdout

# 使用例
# gen = CodeGenerator()
# code = gen.generate('anomaly_detection', template='agent_pattern')
"@

$python_integration | Out-File -Encoding UTF8 "tools\opencode_integration.py"
Write-Host "✅ tools\opencode_integration.py: 生成完了" -ForegroundColor Green

# Claude 統合スクリプト
$claude_integration = @"
# tools/claude_integration.py
# Claude Code との統合 - エージェント開発・テスト

import subprocess
import os
from pathlib import Path

class ClaudeCodeHelper:
    def __init__(self):
        self.npm_bin = r'C:\Users\uchih\AppData\Roaming\npm'
        self.claude_cmd = os.path.join(self.npm_bin, 'claude.cmd')

    def test_agent(self, agent_file: str):
        '''エージェント自動テスト'''
        cmd = [self.claude_cmd, 'test', agent_file]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.stdout, result.returncode

    def develop(self, agent_file: str):
        '''エージェント開発環境起動'''
        cmd = [self.claude_cmd, 'dev', agent_file]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.stdout, result.returncode

    def run(self, script_file: str):
        '''スクリプト実行'''
        cmd = [self.claude_cmd, 'run', script_file]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.stdout, result.returncode

# 使用例
# helper = ClaudeCodeHelper()
# stdout, rc = helper.test_agent('agents/train_agent.py')
"@

$claude_integration | Out-File -Encoding UTF8 "tools\claude_integration.py"
Write-Host "✅ tools\claude_integration.py: 生成完了" -ForegroundColor Green

Write-Host ""

# パイプライン統合ポイント
Write-Host "🔌 Step 3: パイプライン統合ポイント" -ForegroundColor Magenta
Write-Host "─────────────────────────────────────────────" -ForegroundColor Gray

Write-Host "以下のファイルにツール統合を追加してください:" -ForegroundColor Yellow
Write-Host ""

Write-Host "  1️⃣  pipeline_v2/00_orchestrator.py" -ForegroundColor Cyan
Write-Host "      → from tools.opencode_integration import CodeGenerator" -ForegroundColor Gray
Write-Host ""

Write-Host "  2️⃣  agents/test_agent.py" -ForegroundColor Cyan
Write-Host "      → from tools.claude_integration import ClaudeCodeHelper" -ForegroundColor Gray
Write-Host ""

Write-Host "  3️⃣  pipeline/model_train_03.py" -ForegroundColor Cyan
Write-Host "      → claude で自動最適化可能" -ForegroundColor Gray
Write-Host ""

Write-Host "  4️⃣  docs/ ジェネレーション" -ForegroundColor Cyan
Write-Host "      → openclaw で自動ドキュメント化" -ForegroundColor Gray
Write-Host ""

# サンプル実行コマンド
Write-Host "🎯 Step 4: サンプルコマンド" -ForegroundColor Magenta
Write-Host "─────────────────────────────────────────────" -ForegroundColor Gray

Write-Host ""
Write-Host "📝 opencode で新しいエージェント生成:" -ForegroundColor Yellow
Write-Host '  > opencode generate --type "agent" --name "new_analyzer"' -ForegroundColor Gray
Write-Host ""

Write-Host "🧪 claude で既存エージェントテスト:" -ForegroundColor Yellow
Write-Host "  > cd agents && claude test base_agent.py" -ForegroundColor Gray
Write-Host ""

Write-Host "📚 openclaw でドキュメント生成:" -ForegroundColor Yellow
Write-Host "  > openclaw generate --input agents/base_agent.py --output docs/base_agent.md" -ForegroundColor Gray
Write-Host ""

Write-Host "🔍 codex でコード検索:" -ForegroundColor Yellow
Write-Host '  > codex search "kelly fraction"' -ForegroundColor Gray
Write-Host ""

# 動作確認
Write-Host "✅ Step 5: 動作確認" -ForegroundColor Magenta
Write-Host "─────────────────────────────────────────────" -ForegroundColor Gray

Write-Host ""
Write-Host "Python 統合モジュール テスト:" -ForegroundColor Yellow

if (Test-Path "tools\opencode_integration.py") {
    Write-Host "  ✅ tools\opencode_integration.py 作成済み" -ForegroundColor Green

    # Python テスト
    $pythonTest = @"
import sys
sys.path.insert(0, 'tools')
from opencode_integration import CodeGenerator

try:
    gen = CodeGenerator()
    print("✅ CodeGenerator 初期化成功")
except Exception as e:
    print(f"❌ エラー: {e}")
"@

    $pythonTest | python -c "import sys; exec(sys.stdin.read())" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ✅ Python 統合テスト: OK" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "╔═══════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║  ✅ 統合セットアップ完了！" -ForegroundColor Cyan
Write-Host "╚═══════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

Write-Host "📌 次のステップ:" -ForegroundColor Yellow
Write-Host "  1. tools/opencode_integration.py を pipeline_v2/ から import"
Write-Host "  2. tools/claude_integration.py を agents/test 用スクリプトで import"
Write-Host "  3. .\tools\usage-examples.ps1 で実例確認"
Write-Host ""
