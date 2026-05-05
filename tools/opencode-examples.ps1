# 🎓 OpenCode Practical Examples
# 実践的な使用例と サンプルワークフロー

Write-Host ""
Write-Host "╔═══════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║  🎓 OpenCode Practical Examples              ║" -ForegroundColor Cyan
Write-Host "║     うまなり地蔵AI ワークフロー集          ║" -ForegroundColor Cyan
Write-Host "╚═══════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# ============================================================================
# 例 1: 新しい指標エージェント開発
# ============================================================================
function Example-NewIndicatorAgent {
    Write-Host ""
    Write-Host "📋 例1: 新しい指標エージェント開発" -ForegroundColor Cyan
    Write-Host "─────────────────────────────────────────────" -ForegroundColor Gray
    Write-Host ""
    Write-Host "シナリオ: モメンタム指標を分析するエージェントを開発" -ForegroundColor Yellow
    Write-Host ""

    Write-Host "1️⃣  エージェント骨組み生成:" -ForegroundColor Cyan
    Write-Host "   > opencode generate --type agent --name 'momentum_analyzer' --description '価格モメンタム分析'" -ForegroundColor Gray
    Write-Host ""

    Write-Host "2️⃣  テストコード自動生成:" -ForegroundColor Cyan
    Write-Host "   > opencode generate --type tests --input agents/momentum_analyzer_agent.py --framework pytest" -ForegroundColor Gray
    Write-Host ""

    Write-Host "3️⃣  パフォーマンス最適化:" -ForegroundColor Cyan
    Write-Host "   > opencode optimize --input agents/momentum_analyzer_agent.py --strategy performance --preview" -ForegroundColor Gray
    Write-Host ""

    Write-Host "4️⃣  ドキュメント自動生成:" -ForegroundColor Cyan
    Write-Host "   > opencode generate --type documentation --input agents/momentum_analyzer_agent.py --format markdown" -ForegroundColor Gray
    Write-Host ""

    Write-Host "5️⃣  可読性向上:" -ForegroundColor Cyan
    Write-Host "   > opencode optimize --input agents/momentum_analyzer_agent.py --strategy readability --apply" -ForegroundColor Gray
    Write-Host ""

    Write-Host "✅ 完成! agents/momentum_analyzer_agent.py が完全に開発されました" -ForegroundColor Green
    Write-Host ""
}

# ============================================================================
# 例 2: パイプラインステップ追加
# ============================================================================
function Example-AddPipelineStep {
    Write-Host ""
    Write-Host "📋 例2: パイプラインステップ追加" -ForegroundColor Cyan
    Write-Host "─────────────────────────────────────────────" -ForegroundColor Gray
    Write-Host ""
    Write-Host "シナリオ: pipeline_v2 に新しい'ボラティリティ計算'ステップを追加" -ForegroundColor Yellow
    Write-Host ""

    Write-Host "1️⃣  分析 — 既存ステップの構造を理解:" -ForegroundColor Cyan
    Write-Host "   > opencode analyze --dir pipeline_v2/ --detailed" -ForegroundColor Gray
    Write-Host ""

    Write-Host "2️⃣  生成 — 新しいステップを作成:" -ForegroundColor Cyan
    Write-Host "   > opencode generate --type pipeline_step --name 'volatility_calculation' --phase 'feature_engineering'" -ForegroundColor Gray
    Write-Host ""

    Write-Host "3️⃣  最適化 — パフォーマンス改善:" -ForegroundColor Cyan
    Write-Host "   > opencode optimize --input pipeline_v2/volatility_calculation.py --strategy performance" -ForegroundColor Gray
    Write-Host ""

    Write-Host "4️⃣  テスト生成:" -ForegroundColor Cyan
    Write-Host "   > opencode generate --type tests --input pipeline_v2/volatility_calculation.py" -ForegroundColor Gray
    Write-Host ""

    Write-Host "✅ 新しいステップ pipeline_v2/volatility_calculation.py が追加されました" -ForegroundColor Green
    Write-Host ""
}

# ============================================================================
# 例 3: 既存パイプラインの改善
# ============================================================================
function Example-OptimizeExistingPipeline {
    Write-Host ""
    Write-Host "📋 例3: 既存パイプラインの改善" -ForegroundColor Cyan
    Write-Host "─────────────────────────────────────────────" -ForegroundColor Gray
    Write-Host ""
    Write-Host "シナリオ: model_train_03.py をパフォーマンス最適化" -ForegroundColor Yellow
    Write-Host ""

    Write-Host "1️⃣  詳細分析:" -ForegroundColor Cyan
    Write-Host "   > opencode analyze --file pipeline/model_train_03.py --detailed" -ForegroundColor Gray
    Write-Host ""

    Write-Host "   結果:")
    Write-Host "   • Cyclomatic Complexity: 6.2 (高い)" -ForegroundColor Gray
    Write-Host "   • 改善提案: ループの最適化、メモリ効率化" -ForegroundColor Gray
    Write-Host ""

    Write-Host "2️⃣  最適化提案確認:" -ForegroundColor Cyan
    Write-Host "   > opencode optimize --input pipeline/model_train_03.py --strategy performance --preview" -ForegroundColor Gray
    Write-Host ""

    Write-Host "3️⃣  確認して適用:" -ForegroundColor Cyan
    Write-Host "   > opencode optimize --input pipeline/model_train_03.py --apply" -ForegroundColor Gray
    Write-Host ""

    Write-Host "4️⃣  テスト実行:" -ForegroundColor Cyan
    Write-Host "   > python canary_run.py" -ForegroundColor Gray
    Write-Host ""

    Write-Host "✅ パイプラインが最適化されました" -ForegroundColor Green
    Write-Host ""
}

# ============================================================================
# 例 4: バッチドキュメント生成
# ============================================================================
function Example-BatchDocumentation {
    Write-Host ""
    Write-Host "📋 例4: バッチドキュメント生成" -ForegroundColor Cyan
    Write-Host "─────────────────────────────────────────────" -ForegroundColor Gray
    Write-Host ""
    Write-Host "シナリオ: agents/ 全体のドキュメントを自動生成" -ForegroundColor Yellow
    Write-Host ""

    Write-Host "1️⃣  単一ファイル生成テスト:" -ForegroundColor Cyan
    Write-Host "   > opencode generate --type documentation --input agents/base_agent.py --format markdown" -ForegroundColor Gray
    Write-Host ""

    Write-Host "2️⃣  バッチ生成 — 全エージェント:" -ForegroundColor Cyan
    Write-Host "   > for (`$file in (ls agents/*_agent.py)) { opencode generate --type documentation --input `$file.FullName }" -ForegroundColor Gray
    Write-Host ""

    Write-Host "3️⃣  または OpenCode のバッチ機能:" -ForegroundColor Cyan
    Write-Host "   > opencode batch --type documentation --input-dir agents/ --output-dir docs/agents/" -ForegroundColor Gray
    Write-Host ""

    Write-Host "4️⃣  生成確認:" -ForegroundColor Cyan
    Write-Host "   > ls docs/agents/" -ForegroundColor Gray
    Write-Host ""

    Write-Host "✅ docs/agents/*.md にドキュメントが生成されました" -ForegroundColor Green
    Write-Host ""
}

# ============================================================================
# 例 5: Kelly 基準ロジック最適化
# ============================================================================
function Example-OptimizeKelly {
    Write-Host ""
    Write-Host "📋 例5: Kelly 基準ロジック最適化" -ForegroundColor Cyan
    Write-Host "─────────────────────────────────────────────" -ForegroundColor Gray
    Write-Host ""
    Write-Host "シナリオ: Kelly 基準ベットサイジングを最速化" -ForegroundColor Yellow
    Write-Host ""

    Write-Host "1️⃣  Kelly 関連コード検索:" -ForegroundColor Cyan
    Write-Host "   > opencode search --pattern 'kelly.*fraction|kelly_bankroll' --dir pipeline/" -ForegroundColor Gray
    Write-Host ""

    Write-Host "2️⃣  見つかったファイル: pipeline/kelly_bankroll_09.py" -ForegroundColor Gray
    Write-Host ""

    Write-Host "3️⃣  メトリクス分析:" -ForegroundColor Cyan
    Write-Host "   > opencode analyze --file pipeline/kelly_bankroll_09.py --metrics" -ForegroundColor Gray
    Write-Host ""

    Write-Host "   予想される結果:")
    Write-Host "   • 実行時間: 10ms → 2ms (5倍高速化可能)" -ForegroundColor Gray
    Write-Host "   • メモリ: 改善提案あり" -ForegroundColor Gray
    Write-Host ""

    Write-Host "4️⃣  パフォーマンス最適化:" -ForegroundColor Cyan
    Write-Host "   > opencode optimize --input pipeline/kelly_bankroll_09.py --strategy performance --detailed" -ForegroundColor Gray
    Write-Host ""

    Write-Host "5️⃣  提案適用:" -ForegroundColor Cyan
    Write-Host "   > opencode optimize --input pipeline/kelly_bankroll_09.py --apply" -ForegroundColor Gray
    Write-Host ""

    Write-Host "6️⃣  ベンチマーク検証:" -ForegroundColor Cyan
    Write-Host "   > python -m timeit -n 1000 'from pipeline.kelly_bankroll_09 import kelly_fraction'" -ForegroundColor Gray
    Write-Host ""

    Write-Host "✅ Kelly 基準計算が最適化されました (最大 5 倍高速化)" -ForegroundColor Green
    Write-Host ""
}

# ============================================================================
# 例 6: エージェント品質向上パイプライン
# ============================================================================
function Example-QualityImprovement {
    Write-Host ""
    Write-Host "📋 例6: エージェント品質向上パイプライン" -ForegroundColor Cyan
    Write-Host "─────────────────────────────────────────────" -ForegroundColor Gray
    Write-Host ""
    Write-Host "シナリオ: agents/base_agent.py を品質基準に合わせて改善" -ForegroundColor Yellow
    Write-Host ""

    Write-Host "1️⃣  現状分析:" -ForegroundColor Cyan
    Write-Host "   > opencode analyze --file agents/base_agent.py --detailed" -ForegroundColor Gray
    Write-Host ""

    Write-Host "2️⃣  スコア確認:" -ForegroundColor Cyan
    Write-Host "   > opencode analyze --file agents/base_agent.py --metrics" -ForegroundColor Gray
    Write-Host ""

    Write-Host "3️⃣  可読性改善:" -ForegroundColor Cyan
    Write-Host "   > opencode optimize --input agents/base_agent.py --strategy readability --preview" -ForegroundColor Gray
    Write-Host "   > opencode optimize --input agents/base_agent.py --strategy readability --apply" -ForegroundColor Gray
    Write-Host ""

    Write-Host "4️⃣  保守性改善:" -ForegroundColor Cyan
    Write-Host "   > opencode optimize --input agents/base_agent.py --strategy maintainability --apply" -ForegroundColor Gray
    Write-Host ""

    Write-Host "5️⃣  セキュリティ改善:" -ForegroundColor Cyan
    Write-Host "   > opencode optimize --input agents/base_agent.py --strategy security --apply" -ForegroundColor Gray
    Write-Host ""

    Write-Host "6️⃣  改善後の確認:" -ForegroundColor Cyan
    Write-Host "   > opencode analyze --file agents/base_agent.py --metrics" -ForegroundColor Gray
    Write-Host ""

    Write-Host "✅ エージェントの品質が大幅に向上しました" -ForegroundColor Green
    Write-Host ""
}

# ============================================================================
# 例 7: ラッパー関数を使った高速ワークフロー
# ============================================================================
function Example-WrapperFunctions {
    Write-Host ""
    Write-Host "📋 例7: ラッパー関数を使った高速ワークフロー" -ForegroundColor Cyan
    Write-Host "─────────────────────────────────────────────" -ForegroundColor Gray
    Write-Host ""
    Write-Host "シナリオ: PowerShell ラッパー関数で素早く開発" -ForegroundColor Yellow
    Write-Host ""

    Write-Host "事前準備:" -ForegroundColor Yellow
    Write-Host ". tools\opencode-wrapper.ps1" -ForegroundColor Gray
    Write-Host ""

    Write-Host "1️⃣  エージェント生成 (new-agent):" -ForegroundColor Cyan
    Write-Host "   > new-agent -AgentName 'volatility_analyzer' -Description 'ボラティリティ分析'" -ForegroundColor Gray
    Write-Host ""

    Write-Host "2️⃣  コード最適化 (optimize):" -ForegroundColor Cyan
    Write-Host "   > optimize -FilePath agents/volatility_analyzer_agent.py -ApplyChanges" -ForegroundColor Gray
    Write-Host ""

    Write-Host "3️⃣  テスト生成 (new-tests):" -ForegroundColor Cyan
    Write-Host "   > new-tests -SourceFile agents/volatility_analyzer_agent.py -Framework pytest" -ForegroundColor Gray
    Write-Host ""

    Write-Host "4️⃣  ドキュメント生成 (new-docs):" -ForegroundColor Cyan
    Write-Host "   > new-docs -SourceFile agents/volatility_analyzer_agent.py -Format markdown" -ForegroundColor Gray
    Write-Host ""

    Write-Host "5️⃣  分析結果確認 (analyze):" -ForegroundColor Cyan
    Write-Host "   > analyze -Directory agents/ -Detailed" -ForegroundColor Gray
    Write-Host ""

    Write-Host "✅ わずか 5 コマンドで完全なエージェント開発フローが完了!" -ForegroundColor Green
    Write-Host ""
}

# ============================================================================
# 例 8: 定期的なコード監視
# ============================================================================
function Example-ContinuousMonitoring {
    Write-Host ""
    Write-Host "📋 例8: 定期的なコード品質監視" -ForegroundColor Cyan
    Write-Host "─────────────────────────────────────────────" -ForegroundColor Gray
    Write-Host ""
    Write-Host "シナリオ: 日次でコード品質をチェック" -ForegroundColor Yellow
    Write-Host ""

    Write-Host "📅 日次スクリプト (daily-check.ps1):" -ForegroundColor Cyan
    Write-Host ""
    Write-Host '
# agents/ の品質スコアを確認
opencode analyze --dir agents/ --metrics

# 改善候補を特定
opencode analyze --dir agents/ --optimization-candidates

# ログに記録
Get-Date | Out-File -Append logs/code-quality.log
opencode analyze --dir agents/ --metrics | Out-File -Append logs/code-quality.log
' -ForegroundColor Gray
    Write-Host ""

    Write-Host "📅 週次スクリプト (weekly-report.ps1):" -ForegroundColor Cyan
    Write-Host ""
    Write-Host '
# 全体分析レポート生成
opencode analyze --dir . --detailed --report

# 過去1週間の改善度合いを確認
$lastWeek = (Get-Date).AddDays(-7)
Get-Content logs/code-quality.log | Select-String -After $lastWeek

# 改善が必要な箇所を表示
opencode analyze --dir . --optimization-candidates | Export-Csv reports/candidates_$(Get-Date -Format yyyyMMdd).csv
' -ForegroundColor Gray
    Write-Host ""

    Write-Host "✅ コード品質を継続的に監視できます" -ForegroundColor Green
    Write-Host ""
}

# ============================================================================
# メニュー表示
# ============================================================================
function Show-Menu {
    Write-Host ""
    Write-Host "═══════════════════════════════════════════════" -ForegroundColor Cyan
    Write-Host "  どの例を実行しますか?" -ForegroundColor Cyan
    Write-Host "═══════════════════════════════════════════════" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  1. 新しい指標エージェント開発" -ForegroundColor Cyan
    Write-Host "  2. パイプラインステップ追加" -ForegroundColor Cyan
    Write-Host "  3. 既存パイプラインの改善" -ForegroundColor Cyan
    Write-Host "  4. バッチドキュメント生成" -ForegroundColor Cyan
    Write-Host "  5. Kelly 基準ロジック最適化" -ForegroundColor Cyan
    Write-Host "  6. エージェント品質向上" -ForegroundColor Cyan
    Write-Host "  7. ラッパー関数ワークフロー" -ForegroundColor Cyan
    Write-Host "  8. コード品質監視" -ForegroundColor Cyan
    Write-Host "  9. すべての例を表示" -ForegroundColor Cyan
    Write-Host "  0. 終了" -ForegroundColor Cyan
    Write-Host ""
}

# ============================================================================
# メイン実行
# ============================================================================
$running = $true

while ($running) {
    Show-Menu
    $choice = Read-Host "選択 (0-9)"

    switch ($choice) {
        "1" { Example-NewIndicatorAgent }
        "2" { Example-AddPipelineStep }
        "3" { Example-OptimizeExistingPipeline }
        "4" { Example-BatchDocumentation }
        "5" { Example-OptimizeKelly }
        "6" { Example-QualityImprovement }
        "7" { Example-WrapperFunctions }
        "8" { Example-ContinuousMonitoring }
        "9" {
            Example-NewIndicatorAgent
            Example-AddPipelineStep
            Example-OptimizeExistingPipeline
            Example-BatchDocumentation
            Example-OptimizeKelly
            Example-QualityImprovement
            Example-WrapperFunctions
            Example-ContinuousMonitoring
        }
        "0" {
            Write-Host ""
            Write-Host "さようなら! Happy Coding with OpenCode! 🚀" -ForegroundColor Cyan
            Write-Host ""
            $running = $false
        }
        default {
            Write-Host "❌ 無効な選択です" -ForegroundColor Red
        }
    }
}
