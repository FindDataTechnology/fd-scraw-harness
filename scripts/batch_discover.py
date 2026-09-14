#!/usr/bin/env python3
"""Multi-industry data source discovery pipeline.
For each SW industry, use LLM to search for relevant data sources.
Designed for multi-agent parallel execution.
"""
import subprocess
import sys
from pathlib import Path

def discover_industry(industry_name: str) -> int:
    """Discover data sources for one industry using fd-scraw-harness."""
    
    # Keywords covering different aspects of the industry
    keywords = [
        f"{industry_name} 行业协会",
        f"{industry_name} 交易所 数据",
        f"{industry_name} 统计数据 官网",
        f"{industry_name} 产业信息网",
        f"{industry_name} 市场数据平台",
    ]
    
    from fd_scraw_harness.discovery import discover as run_discover
    session_ids = []
    
    print(f"\n🔍 Searching {industry_name}...")
    for keyword in keywords:
        try:
            sid = run_discover(keyword)
            session_ids.append(sid)
            print(f"  ✓ '{keyword}' → Session #{sid}")
        except Exception as e:
            print(f"  ✗ '{keyword}' → Error: {e}")
    
    return session_ids


def main():
    """Main entry point for industry batch processing."""
    # Define ALL 31 Shenwan Level-1 industries
    industries = [
        ("801010", "农林牧渔"),      # Agriculture, Forestry, Animal Husbandry, Fishery
        ("801030", "基础化工"),     # Basic Chemicals
        ("801040", "钢铁"),          # Steel
        ("801050", "有色金属"),     # Non-ferrous Metals
        ("801080", "电子"),         # Electronics
        ("801110", "家用电器"),     # Home Appliances
        ("801120", "食品饮料"),     # Food & Beverage
        ("801130", "纺织服饰"),     # Textiles & Apparel
        ("801140", "轻工制造"),     # Light Industry Manufacturing
        ("801150", "医药生物"),     # Pharmaceuticals & Biotechnology
        ("801160", "公用事业"),     # Public Utilities
        ("801170", "交通运输"),     # Transportation
        ("801180", "房地产"),       # Real Estate
        ("801200", "商贸零售"),     # Commerce & Retail
        ("801210", "社会服务"),     # Social Services
        ("801230", "综合"),         # Conglomerates
        ("801710", "建筑材料"),     # Building Materials
        ("801720", "建筑装饰"),     # Architectural Decoration
        ("801730", "电力设备"),     # Electrical Equipment
        ("801740", "国防军工"),     # National Defense & Military
        ("801750", "计算机"),       # Computers
        ("801760", "传媒"),         # Media & Entertainment
        ("801770", "通信"),         # Telecommunications
        ("801780", "银行"),         # Banking
        ("801790", "非银金融"),     # Non-Bank Financial Services
        ("801880", "汽车"),         # Automobiles
        ("801890", "机械设备"),     # Machinery & Equipment
        ("801950", "煤炭"),         # Coal Mining
        ("801960", "石油石化"),     # Petroleum & Chemicals
        ("801970", "环保"),         # Environmental Protection
        ("801980", "美容护理"),     # Beauty & Personal Care
    ]
    
    from fd_scraw_harness.db import get_session, init_db
    init_db()
    
    results = {}
    
    for code, name in industries:
        print(f"\n{'='*60}")
        print(f"Processing [{code}] {name}")
        print('='*60)
        
        try:
            session_ids = discover_industry(name)
            results[code] = {
                "name": name,
                "sessions": session_ids,
                "count": len(session_ids),
                "status": "success"
            }
            print(f"✅ Completed with {len(session_ids)} sessions")
        except Exception as e:
            results[code] = {
                "name": name,
                "sessions": [],
                "count": 0,
                "status": "failed",
                "error": str(e)
            }
            print(f"❌ Failed: {e}")
    
    # Print summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print('='*60)
    total_processed = len([r for r in results.values() if r["status"] == "success"])
    total_failed = len([r for r in results.values() if r["status"] == "failed"])
    total_sessions = sum(r["count"] for r in results.values())
    
    print(f"Industries processed: {total_processed}/{len(industries)} successful, {total_failed} failed")
    print(f"Total discovery sessions created: {total_sessions}")
    
    # Show how to access results via CLI
    print(f"\nTo view all results:")
    print(f"  cd ~/finddata/fd-scraw-harness")
    print(f"  uv run fd-scraw-harness list --status discovered")
    print(f"\nTo start dashboard:")
    print(f"  uv run python scripts/dashboard.py 8892")
    print(f"\nThen visit http://127.0.0.1:8892")


if __name__ == "__main__":
    main()
