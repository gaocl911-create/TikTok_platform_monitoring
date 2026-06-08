from app.collectors.base import CollectorConfigurationError, CreatorCollector
from app.collectors.douyin_public_web import DouyinPublicWebCollector
from app.collectors.mock import MockCollector
from app.collectors.tikomni import TikOmniDouyinCollector
from app.models.creator import CreatorAccount


def get_collector(creator: CreatorAccount) -> CreatorCollector:
    if creator.collector_type == "mock":
        return MockCollector()
    if creator.collector_type == "douyin_public_web":
        return DouyinPublicWebCollector()
    if creator.collector_type == "tikomni_douyin":
        if creator.platform != "douyin":
            raise CollectorConfigurationError(
                "TikOmni Douyin collector only supports Douyin accounts"
            )
        return TikOmniDouyinCollector(
            spent_today_cny=getattr(creator, "tikomni_spent_today_cny", 0),
        )
    raise CollectorConfigurationError(f"不支持的采集器类型：{creator.collector_type}")
