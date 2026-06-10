from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import SessionLocal  # noqa: E402
from app.models.creator import CreatorAccount  # noqa: E402


def main() -> int:
    with SessionLocal() as db:
        creators = (
            db.query(CreatorAccount)
            .filter(
                CreatorAccount.platform == "douyin",
                CreatorAccount.monitor_scope == "single_content",
                CreatorAccount.collector_type != "tikhub_douyin",
            )
            .all()
        )
        for creator in creators:
            creator.collector_type = "tikhub_douyin"
            creator.collector_version = "tikhub-douyin-v1"
        db.commit()
        print(f"Switched {len(creators)} single-content Douyin creators to tikhub_douyin.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
