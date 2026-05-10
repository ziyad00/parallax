from pathlib import Path

from parallax.core import group_by_resource_set
from parallax.extractors import RedisKeysExtractor


def write(tmp: Path, rel: str, content: str) -> None:
    p = tmp / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def test_clusters_python_and_node_touching_same_namespace(tmp_path):
    write(tmp_path, "py/cache.py", '''
async def get_profile(user_id):
    return await r.get(f"user:{user_id}:profile")

async def cache_session(token):
    await r.setex("session:abc", 3600, token)
''')
    write(tmp_path, "ts/cache.ts", '''
async function profile(id: string) {
  return redis.get(`user:${id}:profile`);
}
async function session(t: string) {
  await redis.set("session:xyz", t);
}
''')

    units = list(RedisKeysExtractor().extract(tmp_path))
    clusters = group_by_resource_set(units, min_resources=2)
    matching = [c for c in clusters if c.resources == frozenset({"user", "session"})]
    assert matching
    files = {u.location for u in matching[0].units}
    assert files == {"py/cache.py", "ts/cache.ts"}


def test_strict_key_mode_keeps_full_path(tmp_path):
    write(tmp_path, "a.py", 'r.get("user:42:profile")')
    write(tmp_path, "b.py", 'r.set("user:99:profile", v)')
    units = list(RedisKeysExtractor(prefix_only=False).extract(tmp_path))
    # Both keys normalise to "user:{id}:profile"
    resources = set().union(*(u.resources for u in units))
    assert "user:{id}:profile" in resources


def test_dict_get_is_not_a_redis_op(tmp_path):
    """``dict.get`` / ``params.get`` / ``config.set`` must not be matched
    as Redis ops; receiver gating is what enforces this."""
    write(tmp_path, "handlers.py", '''
def handler(params, config, my_dict):
    a = params.get("user_id")
    config.set("debug", True)
    b = my_dict.get("foo")
    c = some_set.add("xyz")
    return a, b, c
''')
    units = list(RedisKeysExtractor().extract(tmp_path))
    assert units == []


def test_self_dot_redis_attribute_chain_matches(tmp_path):
    write(tmp_path, "service.py", '''
class CacheService:
    def write_session(self, token):
        self.redis.set("session:abc", token)

    def read_user(self, uid):
        return self.cache.get(f"user:{uid}")
''')
    units = list(RedisKeysExtractor().extract(tmp_path))
    resources = set().union(*(u.resources for u in units))
    assert "session" in resources
    assert "user" in resources


def test_custom_receiver_allow_list(tmp_path):
    write(tmp_path, "custom.py", '''
my_kv.get("user:42")
weird_name.set("x:y", 1)   # not in allow-list, must NOT match
''')
    units = list(RedisKeysExtractor(receivers=frozenset({"my_kv"})).extract(tmp_path))
    resources = set().union(*(u.resources for u in units))
    assert "user" in resources
    assert "x" not in resources
