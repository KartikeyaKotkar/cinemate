# cache.py — Redis-compatible interface, in-memory for now
_cache: dict = {}

def get(key: str):
    return _cache.get(key)

def set(key: str, value, ttl: int = 86400):
    # TTL ignored by in-memory impl — Redis will honor it
    _cache[key] = value

def delete(key: str):
    _cache.pop(key, None)
