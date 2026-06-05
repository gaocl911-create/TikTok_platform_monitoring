from dataclasses import dataclass
from uuid import uuid4

from redis import Redis

from app.core.config import settings

_RELEASE_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
end
return 0
"""


@dataclass(slots=True)
class CreatorCollectionLock:
    client: Redis
    key: str
    token: str

    def release(self) -> None:
        try:
            self.client.eval(_RELEASE_SCRIPT, 1, self.key, self.token)
        finally:
            self.client.close()


def acquire_creator_collection_lock(creator_id: int) -> CreatorCollectionLock | None:
    client = Redis.from_url(settings.redis_url, decode_responses=True)
    key = f"creator-monitor:collection-lock:{creator_id}"
    token = uuid4().hex
    acquired = client.set(key, token, nx=True, ex=settings.collection_lock_ttl_seconds)
    if not acquired:
        client.close()
        return None
    return CreatorCollectionLock(client=client, key=key, token=token)
