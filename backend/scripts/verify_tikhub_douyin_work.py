from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.collectors.tikhub import TikHubDouyinWorkResolver  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify TikHub Douyin single work field mapping without writing DB."
    )
    parser.add_argument("share_text", help="Douyin work URL or full share text.")
    args = parser.parse_args()

    started = time.perf_counter()
    resolver = TikHubDouyinWorkResolver()
    resolved = resolver.resolve(args.share_text)
    elapsed_ms = round((time.perf_counter() - started) * 1000)

    report = {
        "elapsed_ms": elapsed_ms,
        "source_url": resolved.source_url,
        "creator": {
            "platform_account_id": resolved.creator.platform_account_id,
            "platform_display_id": resolved.creator.platform_display_id,
            "nickname": resolved.creator.nickname,
            "follower_count": resolved.creator.follower_count,
            "total_like_count": resolved.creator.total_like_count,
            "content_count": resolved.creator.content_count,
        },
        "content": {
            "platform_content_id": resolved.content.platform_content_id,
            "title": resolved.content.title,
            "published_at": (
                resolved.content.published_at.isoformat()
                if resolved.content.published_at
                else None
            ),
            "like_count": resolved.content.like_count,
            "comment_count": resolved.content.comment_count,
            "collect_count": resolved.content.collect_count,
            "share_count": resolved.content.share_count,
            "metrics_status": resolved.content.metrics_status,
            "missing_metrics": (resolved.content.raw_data or {}).get("missing_metrics", []),
        },
        "usage": resolver.usage_summary(),
        "warnings": resolver.warnings,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
