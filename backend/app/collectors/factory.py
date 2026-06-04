from app.collectors.base import CollectorConfigurationError, CreatorCollector
from app.collectors.douyin_public_web import DouyinPublicWebCollector
from app.collectors.mock import MockCollector
from app.models.creator import CreatorAccount


def get_collector(creator: CreatorAccount) -> CreatorCollector:
    if creator.collector_type == "mock":
        return MockCollector()
    if creator.collector_type == "douyin_public_web":
        return DouyinPublicWebCollector()
    raise CollectorConfigurationError(f"不支持的采集器类型：{creator.collector_type}")
