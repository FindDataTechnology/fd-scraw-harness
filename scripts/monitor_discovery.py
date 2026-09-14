#!/usr/bin/env python3
"""Monitor discovery harness for new data sources every 5 minutes."""
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fd_scraw_harness.db import init_db, get_session
from fd_scraw_harness.models import Manifest


def get_all_sources():
    """Get all sources from database."""
    with get_session() as sess:
        manifests = sess.query(Manifest).all()
        return [{
            'id': m.id,
            'status': m.status,
            'source_name': m.source_name,
            'model_used': m.model_used,
            'created_at': m.created_at,
        } for m in manifests]


def format_summary(sources):
    """Format a summary of new sources."""
    lines = []
    for s in sources:
        marker = "🆕" if s['status'] == 'discovered' else "✅"
        source_name = s.get('source') or s.get('source_name', 'N/A')
        model_name = s.get('model') or s.get('model_used', 'N/A')
        lines.append(f"{marker} ID:{s['id']} {source_name} ({model_name}) - {s['created_at']}")
    return "\n".join(lines)


def main():
    """Main monitoring loop."""
    init_db()
    
    print("=" * 70)
    print("Harness Discovery Monitor")
    print("Checking for new data sources every 5 minutes...")
    print("=" * 70)
    
    # Track seen source IDs to avoid duplicates
    seen_ids = set()
    
    while True:
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n[{now}] Checking for new sources...")
            
            # Get all sources
            all_sources = get_all_sources()
            
            # Find new ones (not seen before)
            new_sources = [s for s in all_sources if s['id'] not in seen_ids]
            
            if new_sources:
                seen_ids.update(s['id'] for s in new_sources)
                print(f"\n✅ Found {len(new_sources)} new source(s):")
                print(format_summary(new_sources))
                
                # Check if we can evaluate
                if os.environ.get("LINJIE_API_KEY"):
                    print("\n🤖 LLM evaluation enabled - ready to evaluate new sources")
                    print("   (Evaluation logic would go here)")
                else:
                    print("\n💡 Tip: Set LINJIE_API_KEY to enable auto-evaluation:")
                    print("   export LINJIE_API_KEY='your-key-here'")
            else:
                print("  No new sources since last check.")
                
        except KeyboardInterrupt:
            print("\n\nStopping monitor...")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
        
        # Wait 5 minutes (300 seconds)
        print("\n⏰ Next check in 5 minutes...")
        time.sleep(300)


if __name__ == "__main__":
    main()
