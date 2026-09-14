#!/usr/bin/env python3
"""
完整使用示例：从发现到覆盖分析的端到端流程

演示如何使用 fd-scraw-harness 的完整功能：
1. 发现候选数据源
2. 分析页面结构
3. 生成 manifest
4. 运行覆盖分析
5. 查看优先级调整结果
"""
from __future__ import annotations

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from fd_scraw_harness.db import get_session, init_db
from fd_scraw_harness.models import Candidate, Discovery


def example_discover_and_analyze():
    """示例：发现并分析数据源"""
    print("=" * 80)
    print("📋 示例 1: 发现新数据源")
    print("=" * 80)
    
    from fd_scraw_harness.discovery import discover as run_discover
    
    # 发现数据源
    print("\n🔍 搜索关键词：'有色金属 交易所'")
    session_id = run_discover("有色金属 交易所")
    print(f"✅ 创建发现会话 #{session_id}")
    
    # 查看发现的候选源
    init_db()
    with get_session() as sess:
        candidates = sess.query(Candidate).filter_by(discovery_id=session_id).all()
        print(f"\n📊 找到 {len(candidates)} 个候选数据源:")
        
        for i, c in enumerate(candidates[:5], 1):
            print(f"\n{i}. {c.title or 'N/A'}")
            print(f"   URL: {c.url}")
            print(f"   原始分数: {c.score}")
            if c.description:
                print(f"   描述: {c.description[:100]}...")


def example_coverage_analysis():
    """示例：运行覆盖分析"""
    print("\n" + "=" * 80)
    print("📋 示例 2: 运行覆盖分析")
    print("=" * 80)
    
    from fd_scraw_harness.coverage import analyze_all_candidates, print_coverage_report
    
    print("\n🔍 分析所有候选数据源的覆盖情况...")
    results = analyze_all_candidates()
    
    print("\n📊 覆盖分析结果:")
    print(f"  总计: {results['total']} 个候选数据源")
    print(f"  ✅ 已覆盖: {results['covered']}")
    print(f"  ⚠️  部分覆盖: {results['partial']}")
    print(f"  🆕 新数据源: {results['new']}")
    
    # 打印详细报告
    print_coverage_report(results)


def example_priority_adjustment():
    """示例：查看优先级调整"""
    print("\n" + "=" * 80)
    print("📋 示例 3: 查看优先级调整")
    print("=" * 80)
    
    init_db()
    
    with get_session() as sess:
        # 查询已分析的候选源
        candidates = (
            sess.query(Candidate)
            .filter(Candidate.coverage_status != "unknown")
            .order_by(Candidate.adjusted_score.desc())
            .limit(10)
            .all()
        )
        
        print("\n📊 Top 10 候选数据源 (按调整后分数排序):")
        
        for i, c in enumerate(candidates, 1):
            score_change = (c.adjusted_score or 0) - (c.score or 0)
            status_icon = {
                "covered": "✅",
                "partial": "⚠️ ",
                "new": "🆕",
            }.get(c.coverage_status, "❓")
            
            print(f"\n{i}. {status_icon} {c.title or 'N/A'}")
            print(f"   URL: {c.url}")
            print(f"   原始分数: {c.score}")
            print(f"   调整后分数: {c.adjusted_score}")
            if score_change < 0:
                print(f"   ⬇️  分数变化: {score_change:+d}")
            elif score_change > 0:
                print(f"   ⬆️  分数变化: {score_change:+d}")
            else:
                print(f"   ➡️  分数不变")


def example_filter_by_coverage():
    """示例：按覆盖状态过滤"""
    print("\n" + "=" * 80)
    print("📋 示例 4: 按覆盖状态过滤")
    print("=" * 80)
    
    init_db()
    
    with get_session() as sess:
        # 查询新数据源（未覆盖）
        new_sources = (
            sess.query(Candidate)
            .filter_by(coverage_status="new")
            .order_by(Candidate.adjusted_score.desc())
            .limit(10)
            .all()
        )
        
        print(f"\n🆕 发现 {len(new_sources)} 个新数据源 (未覆盖):")
        
        for i, c in enumerate(new_sources, 1):
            print(f"\n{i}. {c.title or 'N/A'}")
            print(f"   URL: {c.url}")
            print(f"   调整后分数: {c.adjusted_score}")
        
        # 查询已覆盖的数据源
        covered_sources = (
            sess.query(Candidate)
            .filter_by(coverage_status="covered")
            .all()
        )
        
        print(f"\n✅ 发现 {len(covered_sources)} 个已覆盖的数据源:")
        
        for i, c in enumerate(covered_sources[:5], 1):
            print(f"\n{i}. {c.title or 'N/A'}")
            print(f"   URL: {c.url}")
            print(f"   原始分数: {c.score} → 调整后: {c.adjusted_score}")


def main():
    """主函数"""
    print("\n" + "=" * 80)
    print("🚀 fd-scraw-harness 完整使用示例")
    print("=" * 80)
    
    try:
        # 示例 1: 发现数据源
        example_discover_and_analyze()
        
        # 示例 2: 覆盖分析
        example_coverage_analysis()
        
        # 示例 3: 优先级调整
        example_priority_adjustment()
        
        # 示例 4: 按覆盖状态过滤
        example_filter_by_coverage()
        
        print("\n" + "=" * 80)
        print("✅ 所有示例执行完成")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ 示例执行失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
