import redis

from app.config.app_config import get_app_config

_client: redis.Redis | None = None  # type: ignore[type-arg]


def get_redis() -> redis.Redis:  # type: ignore[type-arg]
    global _client
    if _client is None:
        config = get_app_config()
        if config.app_env == "development":
            import fakeredis
            _client = fakeredis.FakeRedis(decode_responses=True)
        else:
            _client = redis.from_url(config.redis_url, decode_responses=True)
    return _client
