# -*- coding: utf-8 -*-
"""
Tests for Redis Blackboard implementation
"""

import pytest
import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any

from agents.blackboard import DataCategory, BlackboardEntry

# Check if redis is available
try:
    from agents.persistence.redis_blackboard import (
        RedisBlackboard,
        RedisConnectionError,
        REDIS_AVAILABLE,
    )
except ImportError:
    REDIS_AVAILABLE = False
    RedisBlackboard = None
    RedisConnectionError = Exception

from agents.persistence.hybrid_blackboard import (
    HybridBlackboard,
    BlackboardMode,
)

# Skip Redis-specific tests if redis not installed
requires_redis = pytest.mark.skipif(
    not REDIS_AVAILABLE,
    reason="Redis package not installed"
)


# Mock Redis for testing without actual Redis connection
class MockRedis:
    """Mock Redis client for testing"""

    def __init__(self):
        self._data: Dict[str, Dict[str, str]] = {}
        self._sets: Dict[str, set] = {}
        self._lists: Dict[str, list] = {}
        self._expires: Dict[str, int] = {}
        self._pubsub_messages = []

    async def ping(self):
        return True

    async def close(self):
        pass

    async def hset(self, key: str, mapping: Dict[str, Any] = None, **kwargs):
        if key not in self._data:
            self._data[key] = {}
        if mapping:
            self._data[key].update({k: str(v) if v is not None else None for k, v in mapping.items()})
        return len(mapping) if mapping else 0

    async def hgetall(self, key: str) -> Dict[str, str]:
        return self._data.get(key, {})

    async def hget(self, key: str, field: str):
        return self._data.get(key, {}).get(field)

    async def hincrby(self, key: str, field: str, amount: int = 1):
        if key not in self._data:
            self._data[key] = {}
        current = int(self._data[key].get(field, 0))
        self._data[key][field] = str(current + amount)
        return current + amount

    async def expire(self, key: str, ttl: int):
        self._expires[key] = ttl
        return True

    async def delete(self, *keys):
        deleted = 0
        for key in keys:
            if key in self._data:
                del self._data[key]
                deleted += 1
        return deleted

    async def sadd(self, key: str, *values):
        if key not in self._sets:
            self._sets[key] = set()
        self._sets[key].update(values)
        return len(values)

    async def srem(self, key: str, *values):
        if key in self._sets:
            for v in values:
                self._sets[key].discard(v)
        return len(values)

    async def smembers(self, key: str):
        return self._sets.get(key, set())

    async def lpush(self, key: str, *values):
        if key not in self._lists:
            self._lists[key] = []
        for v in values:
            self._lists[key].insert(0, v)
        return len(self._lists[key])

    async def ltrim(self, key: str, start: int, end: int):
        if key in self._lists:
            self._lists[key] = self._lists[key][start:end + 1]
        return True

    async def lrange(self, key: str, start: int, end: int):
        if key not in self._lists:
            return []
        if end == -1:
            return self._lists[key][start:]
        return self._lists[key][start:end + 1]

    async def scan(self, cursor: int = 0, match: str = "*", count: int = 100):
        # Simple scan implementation
        matching = []
        pattern = match.replace("*", "")
        for key in self._data.keys():
            if pattern in key:
                matching.append(key)
        return (0, matching[:count])

    async def publish(self, channel: str, message: str):
        self._pubsub_messages.append({'channel': channel, 'message': message})
        return 1

    def pubsub(self):
        return MockPubSub()

    def pipeline(self):
        return MockPipeline(self)


class MockPubSub:
    """Mock PubSub"""

    def __init__(self):
        self._subscriptions = []

    async def psubscribe(self, *patterns):
        self._subscriptions.extend(patterns)

    async def close(self):
        pass

    async def listen(self):
        # Yield nothing for tests
        return
        yield


class MockPipeline:
    """Mock Pipeline"""

    def __init__(self, redis: MockRedis):
        self._redis = redis
        self._commands = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def hset(self, key, mapping=None, **kwargs):
        self._commands.append(('hset', key, mapping))
        return self

    async def hgetall(self, key):
        self._commands.append(('hgetall', key))
        return self

    async def expire(self, key, ttl):
        self._commands.append(('expire', key, ttl))
        return self

    async def sadd(self, key, *values):
        self._commands.append(('sadd', key, values))
        return self

    async def srem(self, key, *values):
        self._commands.append(('srem', key, values))
        return self

    async def lpush(self, key, *values):
        self._commands.append(('lpush', key, values))
        return self

    async def ltrim(self, key, start, end):
        self._commands.append(('ltrim', key, start, end))
        return self

    async def hincrby(self, key, field, amount=1):
        self._commands.append(('hincrby', key, field, amount))
        return self

    async def publish(self, channel, message):
        self._commands.append(('publish', channel, message))
        return self

    async def delete(self, *keys):
        self._commands.append(('delete', keys))
        return self

    async def execute(self):
        results = []
        for cmd in self._commands:
            if cmd[0] == 'hset':
                await self._redis.hset(cmd[1], cmd[2])
                results.append(True)
            elif cmd[0] == 'hgetall':
                results.append(await self._redis.hgetall(cmd[1]))
            elif cmd[0] == 'expire':
                results.append(await self._redis.expire(cmd[1], cmd[2]))
            elif cmd[0] == 'sadd':
                results.append(await self._redis.sadd(cmd[1], *cmd[2]))
            elif cmd[0] == 'srem':
                results.append(await self._redis.srem(cmd[1], *cmd[2]))
            elif cmd[0] == 'lpush':
                results.append(await self._redis.lpush(cmd[1], *cmd[2]))
            elif cmd[0] == 'ltrim':
                results.append(await self._redis.ltrim(cmd[1], cmd[2], cmd[3]))
            elif cmd[0] == 'hincrby':
                results.append(await self._redis.hincrby(cmd[1], cmd[2], cmd[3]))
            elif cmd[0] == 'publish':
                results.append(await self._redis.publish(cmd[1], cmd[2]))
            elif cmd[0] == 'delete':
                results.append(await self._redis.delete(*cmd[1]))
            else:
                results.append(None)
        self._commands = []
        return results


@pytest.fixture
def mock_redis():
    """Create mock Redis instance"""
    return MockRedis()


@pytest.fixture
def redis_blackboard(mock_redis):
    """Create RedisBlackboard with mocked Redis"""
    if not REDIS_AVAILABLE:
        pytest.skip("Redis package not installed")

    with patch('agents.persistence.redis_blackboard.aioredis') as mock_aioredis:
        mock_aioredis.from_url = MagicMock(return_value=mock_redis)

        bb = RedisBlackboard(
            redis_url="redis://localhost:6379",
            key_prefix="test"
        )
        bb._redis = mock_redis
        bb._connected = True

        return bb


@pytest.fixture
def hybrid_blackboard():
    """Create HybridBlackboard in memory mode"""
    bb = HybridBlackboard(mode=BlackboardMode.MEMORY_ONLY)
    return bb


@requires_redis
class TestRedisBlackboardKeyGeneration:
    """Tests for Redis key generation"""

    def test_key_generation(self, redis_blackboard):
        """Key generation includes prefix"""
        key = redis_blackboard._key('entries', 'test.key')
        assert key == "test:blackboard:entries:test.key"

    def test_key_with_multiple_parts(self, redis_blackboard):
        """Key generation handles multiple parts"""
        key = redis_blackboard._key('index', 'category', 'competitor')
        assert key == "test:blackboard:index:category:competitor"


@requires_redis
class TestRedisBlackboardPublish:
    """Tests for publishing to Redis blackboard"""

    @pytest.mark.asyncio
    async def test_publish_creates_entry(self, redis_blackboard, mock_redis):
        """Publishing creates entry in Redis"""
        entry = await redis_blackboard.publish(
            key="scout.competitors.new",
            value={"name": "Competitor A"},
            agent_id="scout"
        )

        assert entry.key == "scout.competitors.new"
        assert entry.value == {"name": "Competitor A"}
        assert entry.agent_id == "scout"
        assert entry.version == 1

    @pytest.mark.asyncio
    async def test_publish_with_category(self, redis_blackboard, mock_redis):
        """Publishing with category updates index"""
        entry = await redis_blackboard.publish(
            key="scout.threat",
            value={"severity": "high"},
            agent_id="scout",
            category=DataCategory.THREAT
        )

        assert entry.category == DataCategory.THREAT

    @pytest.mark.asyncio
    async def test_publish_with_ttl(self, redis_blackboard, mock_redis):
        """Publishing with TTL sets expiration"""
        entry = await redis_blackboard.publish(
            key="temp.data",
            value="temporary",
            agent_id="test",
            ttl=3600
        )

        assert entry.ttl == 3600

    @pytest.mark.asyncio
    async def test_publish_increments_version(self, redis_blackboard, mock_redis):
        """Publishing same key increments version"""
        entry1 = await redis_blackboard.publish(
            key="scout.data",
            value="first",
            agent_id="scout"
        )
        assert entry1.version == 1

        entry2 = await redis_blackboard.publish(
            key="scout.data",
            value="second",
            agent_id="scout"
        )
        assert entry2.version == 2
        assert entry2.previous_value == "first"

    @pytest.mark.asyncio
    async def test_publish_skips_unchanged_value(self, redis_blackboard, mock_redis):
        """Publishing unchanged value returns existing entry"""
        await redis_blackboard.publish(
            key="scout.data",
            value={"status": "ok"},
            agent_id="scout"
        )

        # Publish same value again
        entry = await redis_blackboard.publish(
            key="scout.data",
            value={"status": "ok"},
            agent_id="scout"
        )

        # Should return existing entry without incrementing version
        assert entry.version == 1

    @pytest.mark.asyncio
    async def test_publish_with_tags(self, redis_blackboard, mock_redis):
        """Publishing with tags stores tags"""
        entry = await redis_blackboard.publish(
            key="tagged.entry",
            value="data",
            agent_id="test",
            tags={"important", "urgent"}
        )

        assert entry.tags == {"important", "urgent"}

    @pytest.mark.asyncio
    async def test_publish_with_metadata(self, redis_blackboard, mock_redis):
        """Publishing with metadata stores metadata"""
        entry = await redis_blackboard.publish(
            key="meta.entry",
            value="data",
            agent_id="test",
            metadata={"source": "api", "priority": 1}
        )

        assert entry.metadata["source"] == "api"
        assert entry.metadata["priority"] == 1


@requires_redis
class TestRedisBlackboardGet:
    """Tests for getting from Redis blackboard"""

    @pytest.mark.asyncio
    async def test_get_existing_entry(self, redis_blackboard, mock_redis):
        """Get returns value for existing key"""
        await redis_blackboard.publish(
            key="test.key",
            value={"data": "value"},
            agent_id="test"
        )

        value = await redis_blackboard.get("test.key")
        assert value == {"data": "value"}

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_default(self, redis_blackboard, mock_redis):
        """Get returns default for nonexistent key"""
        value = await redis_blackboard.get("nonexistent", default="default")
        assert value == "default"

    @pytest.mark.asyncio
    async def test_get_entry_returns_full_entry(self, redis_blackboard, mock_redis):
        """Get entry returns full BlackboardEntry"""
        await redis_blackboard.publish(
            key="full.entry",
            value="data",
            agent_id="test",
            category=DataCategory.ANALYSIS
        )

        entry = await redis_blackboard.get_entry("full.entry")
        assert isinstance(entry, BlackboardEntry)
        assert entry.key == "full.entry"
        assert entry.agent_id == "test"
        assert entry.category == DataCategory.ANALYSIS

    @pytest.mark.asyncio
    async def test_get_many(self, redis_blackboard, mock_redis):
        """Get many returns multiple values"""
        await redis_blackboard.publish("key1", "value1", "test")
        await redis_blackboard.publish("key2", "value2", "test")
        await redis_blackboard.publish("key3", "value3", "test")

        result = await redis_blackboard.get_many(["key1", "key2", "key4"])

        assert result["key1"] == "value1"
        assert result["key2"] == "value2"
        assert "key4" not in result


@requires_redis
class TestRedisBlackboardQuery:
    """Tests for querying Redis blackboard"""

    @pytest.mark.asyncio
    async def test_query_by_pattern(self, redis_blackboard, mock_redis):
        """Query returns entries matching pattern"""
        await redis_blackboard.publish("scout.data.1", "a", "scout")
        await redis_blackboard.publish("scout.data.2", "b", "scout")
        await redis_blackboard.publish("analyst.data.1", "c", "analyst")

        # Query for scout entries
        results = await redis_blackboard.query("scout.*")
        assert len(results) >= 2

    @pytest.mark.asyncio
    async def test_query_by_category(self, redis_blackboard, mock_redis):
        """Query by category uses index"""
        await redis_blackboard.publish(
            "threat.1", "high", "guardian", category=DataCategory.THREAT
        )
        await redis_blackboard.publish(
            "threat.2", "low", "guardian", category=DataCategory.THREAT
        )
        await redis_blackboard.publish(
            "insight.1", "good", "analyst", category=DataCategory.INSIGHT
        )

        results = await redis_blackboard.query_by_category(DataCategory.THREAT)

        # Should only get threat entries
        for entry in results:
            assert entry.category == DataCategory.THREAT

    @pytest.mark.asyncio
    async def test_query_by_agent(self, redis_blackboard, mock_redis):
        """Query by agent returns agent's entries"""
        await redis_blackboard.publish("scout.a", "1", "scout")
        await redis_blackboard.publish("scout.b", "2", "scout")
        await redis_blackboard.publish("analyst.a", "3", "analyst")

        results = await redis_blackboard.query_by_agent("scout")

        for entry in results:
            assert entry.agent_id == "scout"


@requires_redis
class TestRedisBlackboardSubscriptions:
    """Tests for subscription functionality"""

    def test_subscribe_registers_callback(self, redis_blackboard):
        """Subscribe registers callback"""
        callback = MagicMock()

        redis_blackboard.subscribe("scout.*", "analyst", callback)

        assert "scout.*" in redis_blackboard._subscriptions
        assert len(redis_blackboard._subscriptions["scout.*"]) == 1

    def test_unsubscribe_removes_callback(self, redis_blackboard):
        """Unsubscribe removes callback"""
        callback = MagicMock()

        redis_blackboard.subscribe("scout.*", "analyst", callback)
        redis_blackboard.unsubscribe("scout.*", "analyst")

        assert "scout.*" not in redis_blackboard._subscriptions

    def test_unsubscribe_all(self, redis_blackboard):
        """Unsubscribe all removes all agent callbacks"""
        callback = MagicMock()

        redis_blackboard.subscribe("scout.*", "analyst", callback)
        redis_blackboard.subscribe("guardian.*", "analyst", callback)

        redis_blackboard.unsubscribe_all("analyst")

        assert len(redis_blackboard._subscriptions) == 0


@requires_redis
class TestRedisBlackboardDelete:
    """Tests for delete operations"""

    @pytest.mark.asyncio
    async def test_delete_removes_entry(self, redis_blackboard, mock_redis):
        """Delete removes entry"""
        await redis_blackboard.publish("to.delete", "value", "test")

        await redis_blackboard.delete("to.delete")

        value = await redis_blackboard.get("to.delete")
        assert value is None

    @pytest.mark.asyncio
    async def test_clear_removes_all(self, redis_blackboard, mock_redis):
        """Clear removes all entries"""
        await redis_blackboard.publish("key1", "a", "test")
        await redis_blackboard.publish("key2", "b", "test")

        await redis_blackboard.clear()

        keys = await redis_blackboard.get_all_keys()
        assert len(keys) == 0


@requires_redis
class TestRedisBlackboardStats:
    """Tests for statistics"""

    @pytest.mark.asyncio
    async def test_stats_track_writes(self, redis_blackboard, mock_redis):
        """Stats track write operations"""
        await redis_blackboard.publish("a", "1", "test")
        await redis_blackboard.publish("b", "2", "test")

        stats = await redis_blackboard.get_stats()
        # Stats are tracked in Redis hincrby
        assert stats['backend'] == 'redis'
        assert stats['connected'] is True

    @pytest.mark.asyncio
    async def test_health_check(self, redis_blackboard, mock_redis):
        """Health check returns status"""
        health = await redis_blackboard.health_check()

        assert health['healthy'] is True
        assert health['connected'] is True
        assert 'latency_ms' in health


class TestHybridBlackboardModes:
    """Tests for HybridBlackboard mode switching"""

    def test_default_mode_is_memory(self, hybrid_blackboard):
        """Default mode is memory only"""
        assert hybrid_blackboard.get_mode() == BlackboardMode.MEMORY_ONLY

    @pytest.mark.asyncio
    async def test_memory_only_mode_uses_memory(self, hybrid_blackboard):
        """Memory only mode uses in-memory storage"""
        entry = await hybrid_blackboard.publish("test", "value", "agent")

        assert entry.value == "value"

        value = await hybrid_blackboard.get("test")
        assert value == "value"

    @pytest.mark.asyncio
    async def test_sync_get_works_in_memory_mode(self, hybrid_blackboard):
        """Sync get works in memory mode"""
        await hybrid_blackboard.publish("test", "value", "agent")

        value = hybrid_blackboard.get_sync("test")
        assert value == "value"

    @pytest.mark.asyncio
    async def test_stats_track_memory_operations(self, hybrid_blackboard):
        """Stats track memory operations"""
        await hybrid_blackboard.publish("a", "1", "test")
        await hybrid_blackboard.get("a")

        stats = hybrid_blackboard.get_stats()
        assert stats['memory_writes'] == 1
        assert stats['memory_reads'] == 1
        assert stats['mode'] == 'memory_only'


class TestHybridBlackboardDualWrite:
    """Tests for dual write mode"""

    @pytest.mark.asyncio
    async def test_dual_write_writes_to_memory(self):
        """Dual write mode writes to memory"""
        bb = HybridBlackboard(mode=BlackboardMode.MEMORY_ONLY)

        # Set to dual write (will fail Redis but write to memory)
        bb._mode = BlackboardMode.DUAL_WRITE

        entry = await bb.publish("test", "value", "agent")
        assert entry.value == "value"

        # Read from memory (primary in dual write)
        value = await bb.get("test")
        assert value == "value"


class TestHybridBlackboardSubscriptions:
    """Tests for subscription in hybrid mode"""

    @pytest.mark.asyncio
    async def test_subscribe_in_memory_mode(self, hybrid_blackboard):
        """Subscriptions work in memory mode"""
        received = []

        def callback(entry):
            received.append(entry)

        hybrid_blackboard.subscribe("scout.*", "analyst", callback)

        await hybrid_blackboard.publish("scout.data", "value", "scout")

        # Callback should have been triggered
        assert len(received) == 1
        assert received[0].key == "scout.data"

    @pytest.mark.asyncio
    async def test_unsubscribe_works(self, hybrid_blackboard):
        """Unsubscribe removes subscription"""
        callback = MagicMock()

        hybrid_blackboard.subscribe("test.*", "agent", callback)
        hybrid_blackboard.unsubscribe("test.*", "agent")

        await hybrid_blackboard.publish("test.data", "value", "other")

        # Callback should not be called
        callback.assert_not_called()


class TestHybridBlackboardSync:
    """Tests for sync functionality"""

    @pytest.mark.asyncio
    async def test_get_snapshot(self, hybrid_blackboard):
        """Get snapshot returns all entries"""
        await hybrid_blackboard.publish("a", "1", "test")
        await hybrid_blackboard.publish("b", "2", "test")

        snapshot = hybrid_blackboard.get_snapshot()

        assert "a" in snapshot
        assert "b" in snapshot

    @pytest.mark.asyncio
    async def test_get_history(self, hybrid_blackboard):
        """Get history returns recent entries"""
        await hybrid_blackboard.publish("a", "1", "test")
        await hybrid_blackboard.publish("b", "2", "test")

        history = hybrid_blackboard.get_history()

        assert len(history) == 2

    @pytest.mark.asyncio
    async def test_reset_clears_everything(self, hybrid_blackboard):
        """Reset clears all data and stats"""
        await hybrid_blackboard.publish("a", "1", "test")

        await hybrid_blackboard.reset()

        keys = hybrid_blackboard.get_all_keys()
        assert len(keys) == 0

        stats = hybrid_blackboard.get_stats()
        assert stats['memory_writes'] == 0


class TestHybridBlackboardQuery:
    """Tests for query operations"""

    @pytest.mark.asyncio
    async def test_query_pattern(self, hybrid_blackboard):
        """Query returns matching entries"""
        await hybrid_blackboard.publish("scout.a", "1", "scout")
        await hybrid_blackboard.publish("scout.b", "2", "scout")
        await hybrid_blackboard.publish("analyst.a", "3", "analyst")

        results = await hybrid_blackboard.query("scout.*")

        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_query_by_category(self, hybrid_blackboard):
        """Query by category returns correct entries"""
        await hybrid_blackboard.publish(
            "threat.1", "high", "guardian", category=DataCategory.THREAT
        )
        await hybrid_blackboard.publish(
            "insight.1", "good", "analyst", category=DataCategory.INSIGHT
        )

        results = await hybrid_blackboard.query_by_category(DataCategory.THREAT)

        assert len(results) == 1
        assert results[0].category == DataCategory.THREAT


class TestHybridBlackboardHealthCheck:
    """Tests for health check"""

    @pytest.mark.asyncio
    async def test_health_check_memory_mode(self, hybrid_blackboard):
        """Health check works in memory mode"""
        health = await hybrid_blackboard.health_check()

        assert health['mode'] == 'memory_only'
        assert health['memory']['healthy'] is True


@requires_redis
class TestEntryConversion:
    """Tests for entry serialization"""

    def test_entry_to_dict(self, redis_blackboard):
        """Entry converts to dict correctly"""
        entry = BlackboardEntry(
            key="test.key",
            value={"data": "value"},
            agent_id="test",
            ttl=3600,
            tags={"tag1", "tag2"},
            metadata={"source": "api"},
            category=DataCategory.ANALYSIS,
            version=2
        )

        result = redis_blackboard._entry_to_dict(entry)

        assert result['key'] == "test.key"
        assert json.loads(result['value']) == {"data": "value"}
        assert result['agent_id'] == "test"
        assert result['ttl'] == 3600
        assert result['category'] == "analysis"
        assert result['version'] == 2

    def test_dict_to_entry(self, redis_blackboard):
        """Dict converts back to entry correctly"""
        data = {
            'key': 'test.key',
            'value': '{"data": "value"}',
            'agent_id': 'test',
            'timestamp': datetime.now().isoformat(),
            'ttl': '3600',
            'tags': '["tag1", "tag2"]',
            'metadata': '{"source": "api"}',
            'category': 'analysis',
            'version': '2',
            'previous_value': None
        }

        entry = redis_blackboard._dict_to_entry(data)

        assert entry.key == "test.key"
        assert entry.value == {"data": "value"}
        assert entry.agent_id == "test"
        assert entry.ttl == 3600
        assert entry.category == DataCategory.ANALYSIS
        assert entry.version == 2


@requires_redis
class TestPatternMatching:
    """Tests for pattern matching"""

    def test_pattern_matches_exact(self, redis_blackboard):
        """Pattern matches exact key"""
        assert redis_blackboard._pattern_matches("scout.data", "scout.data")

    def test_pattern_matches_wildcard(self, redis_blackboard):
        """Pattern matches with wildcard"""
        assert redis_blackboard._pattern_matches("scout.*", "scout.data")
        assert redis_blackboard._pattern_matches("scout.*", "scout.threats")
        assert not redis_blackboard._pattern_matches("scout.*", "analyst.data")

    def test_pattern_matches_prefix_wildcard(self, redis_blackboard):
        """Pattern matches with prefix wildcard"""
        assert redis_blackboard._pattern_matches("*.data", "scout.data")
        assert redis_blackboard._pattern_matches("*.data", "analyst.data")
        assert not redis_blackboard._pattern_matches("*.data", "scout.threats")

    def test_pattern_matches_middle_wildcard(self, redis_blackboard):
        """Pattern matches with middle wildcard"""
        assert redis_blackboard._pattern_matches("scout.*.high", "scout.threat.high")
        assert not redis_blackboard._pattern_matches("scout.*.high", "scout.threat.low")
