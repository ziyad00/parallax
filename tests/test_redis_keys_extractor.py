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
