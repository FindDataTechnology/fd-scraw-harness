#!/usr/bin/env python3
"""
自动覆盖分析脚本

定期运行覆盖分析，更新候选数据源的优先级。
可以集成到 crontab 中定期执行。

Usage:
    uv run scripts/analyze_coverage.py [--verbose]
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from fd_scraw_harness.coverage import analyze_all_candidates, print_coverage_report

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="分析候选数据源的覆盖情况")
    parser.add_argument("--verbose", "-v", action="store_true", help="显示详细日志")
    args = parser.parse_args()
    
    # 配置日志
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    
    print("🔍 开始覆盖分析...")
    print("=" * 80)
    
    try:
        # 运行覆盖分析
        results = analyze_all_candidates()
        
        # 打印报告
        print_coverage_report(results)
        
        # 输出摘要
        print("\n" + "=" * 80)
        print("✅ 覆盖分析完成")
        print("=" * 80)
        print(f"总计: {results['total']} 个候选数据源")
        print(f"  已覆盖: {results['covered']}")
        print(f"  部分覆盖: {results['partial']}")
        print(f"  新数据源: {results['new']}")
        print(f"  未知: {results['unknown']}")
        
        # 返回退出码
        if results["new"] > 0:
            print(f"\n💡 发现 {results['new']} 个新数据源值得处理")
            return 0
        else:
            print("\n⚠️  没有发现新数据源")
            return 1
            
    except Exception as e:
        logging.error(f"覆盖分析失败: {e}", exc_info=True)
        return 2


if __name__ == "__main__":
    sys.exit(main())
