# -*- coding: utf-8 -*-
"""
Growth Engine 2.0 - Redis Blackboard
Persistent, scalable blackboard implementation using Redis

Version: 3.0.0

This provides the same interface as the in-memory Blackboard but stores
data in Redis for:
- Persistence across restarts
- Horizontal scaling (multiple workers share state)
- Pub/Sub for real-time notifications
"""

import asyncio
import json
import logging
import re
from typing import Dict, Any, List, Optional, Callable, Set, Union
from datetime import datetime
from dataclasses import dataclass, field
from collections import defaultdict
from contextlib import asynccontextmanager

try:
    import redis.asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    aioredis = None

from agents.blackboard import (
    BlackboardEntry,
    DataCategory,
    Subscription,
)

logger = logging.getLogger(__name__)


class RedisConnectionError(Exception):
    """Redis connection failed"""
    pass


class RedisBlackboard:
    """
    Redis-backed blackboard implementation.

    Stores entries in Redis hashes with automatic TTL support.
    Uses Pub/Sub for real-time subscriber notifications.

    Key schema:
    - blackboard:entries:<key> - Hash containing entry data
    - blackboard:index:category:<category> - Set of keys in category
    - blackboard:index:agent:<agent_id> - Set of keys by agent
    - blackboard:history - List of all published keys (capped)
    - blackboard:stats - Hash of statistics

    Pub/Sub channels:
    - blackboard:updates - All entry updates
    - blackboard:updates:<pattern> - Pattern-specific updates
    """

    PREFIX = "blackboard"
    HISTORY_MAX_SIZE = 10000

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        key_prefix: str = "growth_engine",
        max_connections: int = 10,
    ):
        """
        Initialize Redis blackboard.

        Args:
            redis_url: Redis connection URL
            key_prefix: Prefix for all Redis keys (namespacing)
            max_connections: Maximum connections in pool
        """
        if not REDIS_AVAILABLE:
            raise ImportError(
                "redis package not installed. Install with: pip install redis[hiredis]"
            )

        self._redis_url = redis_url
        self._key_prefix = key_prefix
        self._max_connections = max_connections

        # Redis clients (lazy initialization)
        self._redis: Optional[aioredis.Redis] = None
        self._pubsub: Optional[aioredis.client.PubSub] = None
        self._pubsub_task: Optional[asyncio.Task] = None

        # Local subscription tracking
        self._subscriptions: Dict[str, List[Subscription]] = defaultdict(list)
        self._compiled_patterns: Dict[str, re.Pattern] = {}

        # Event callbacks
        self._on_publish: Optional[Callable] = None
        self._on_subscribe: Optional[Callable] = None

        # Connection state
        self._connected = False
        self._lock = asyncio.Lock()

        logger.info(f"[RedisBlackboard] Initialized with prefix '{key_prefix}'")

    def _key(self, *parts: str) -> str:
        """Build Redis key with prefix"""
        return f"{self._key_prefix}:{self.PREFIX}:{':'.join(parts)}"

    async def connect(self) -> bool:
        """
        Connect to Redis.

        Returns:
            True if connected successfully
        """
        if self._connected:
            return True

        async with self._lock:
            if self._connected:
                return True

            try:
                self._redis = aioredis.from_url(
                    self._redis_url,
                    max_connections=self._max_connections,
                    decode_responses=True,
                )

                # Test connection
                await self._redis.ping()

                self._connected = True
                logger.info("[RedisBlackboard] Connected to Redis")

                # Start Pub/Sub listener
                await self._start_pubsub()

                return True

            except Exception as e:
                logger.error(f"[RedisBlackboard] Connection failed: {e}")
                self._connected = False
                raise RedisConnectionError(f"Failed to connect to Redis: {e}")

    async def disconnect(self):
        """Disconnect from Redis"""
        if self._pubsub_task:
            self._pubsub_task.cancel()
            try:
                await self._pubsub_task
            except asyncio.CancelledError:
                pass

        if self._pubsub:
            await self._pubsub.close()

        if self._redis:
            await self._redis.close()

        self._connected = False
        logger.info("[RedisBlackboard] Disconnected from Redis")

    async def _ensure_connected(self):
        """Ensure Redis connection is active"""
        if not self._connected:
            await self.connect()

    async def _start_pubsub(self):
        """Start Pub/Sub listener for notifications"""
        self._pubsub = self._redis.pubsub()

        # Subscribe to main updates channel
        await self._pubsub.psubscribe(f"{self._key('updates')}:*")

        # Start listener task
        self._pubsub_task = asyncio.create_task(self._pubsub_listener())
        logger.info("[RedisBlackboard] Pub/Sub listener started")

    async def _pubsub_listener(self):
        """Listen for Pub/Sub messages and notify subscribers"""
        try:
            async for message in self._pubsub.listen():
                if message['type'] != 'pmessage':
                    continue

                try:
                    # Parse the entry from message
                    data = json.loads(message['data'])
                    entry = self._dict_to_entry(data)

                    # Notify local subscribers
                    await self._notify_local_subscribers(entry)

                except Exception as e:
                    logger.error(f"[RedisBlackboard] Pub/Sub message error: {e}")

        except asyncio.CancelledError:
            logger.debug("[RedisBlackboard] Pub/Sub listener cancelled")
        except Exception as e:
            logger.error(f"[RedisBlackboard] Pub/Sub listener error: {e}")

    def set_event_callbacks(
        self,
        on_publish: Optional[Callable] = None,
        on_subscribe: Optional[Callable] = None
    ):
        """Set callbacks for blackboard events"""
        self._on_publish = on_publish
        self._on_subscribe = on_subscribe

    def _entry_to_dict(self, entry: BlackboardEntry) -> Dict[str, Any]:
        """Convert entry to dictionary for Redis storage"""
        return {
            'key': entry.key,
            'value': json.dumps(entry.value),
            'agent_id': entry.agent_id,
            'timestamp': entry.timestamp.isoformat(),
            'ttl': entry.ttl,
            'tags': json.dumps(list(entry.tags)),
            'metadata': json.dumps(entry.metadata),
            'category': entry.category.value if entry.category else None,
            'version': entry.version,
            'previous_value': json.dumps(entry.previous_value) if entry.previous_value else None,
        }

    def _dict_to_entry(self, data: Dict[str, Any]) -> BlackboardEntry:
        """Convert dictionary from Redis to BlackboardEntry"""
        return BlackboardEntry(
            key=data['key'],
            value=json.loads(data['value']) if isinstance(data['value'], str) else data['value'],
            agent_id=data['agent_id'],
            timestamp=datetime.fromisoformat(data['timestamp']),
            ttl=int(data['ttl']) if data.get('ttl') else None,
            tags=set(json.loads(data['tags'])) if isinstance(data.get('tags'), str) else set(data.get('tags', [])),
            metadata=json.loads(data['metadata']) if isinstance(data.get('metadata'), str) else data.get('metadata', {}),
            category=DataCategory(data['category']) if data.get('category') else None,
            version=int(data.get('version', 1)),
            previous_value=json.loads(data['previous_value']) if data.get('previous_value') else None,
        )

    async def publish(
        self,
        key: str,
        value: Any,
        agent_id: str,
        ttl: Optional[int] = None,
        tags: Optional[Set[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        category: Optional[DataCategory] = None
    ) -> BlackboardEntry:
        """
        Publish data to Redis blackboard.

        Args:
            key: Hierarchical key (e.g. "scout.competitors.new")
            value: Data to publish
            agent_id: Agent publishing
            ttl: Time-to-live in seconds
            tags: Tags for categorization
            metadata: Additional metadata
            category: Data category for indexing

        Returns:
            The created BlackboardEntry
        """
        await self._ensure_connected()

        redis_key = self._key('entries', key)

        # Check for existing entry
        existing_data = await self._redis.hgetall(redis_key)
        version = 1
        previous_value = None

        if existing_data:
            existing = self._dict_to_entry(existing_data)
            version = existing.version + 1
            previous_value = existing.value

            # Skip if value hasn't changed
            if not existing.has_changed(value):
                logger.debug(f"[RedisBlackboard] Skipping unchanged value for '{key}'")
                return existing

        # Create entry
        entry = BlackboardEntry(
            key=key,
            value=value,
            agent_id=agent_id,
            ttl=ttl,
            tags=tags or set(),
            metadata=metadata or {},
            category=category,
            version=version,
            previous_value=previous_value
        )

        # Store in Redis
        entry_dict = self._entry_to_dict(entry)

        async with self._redis.pipeline() as pipe:
            # Store entry
            await pipe.hset(redis_key, mapping=entry_dict)

            # Set TTL if specified
            if ttl:
                await pipe.expire(redis_key, ttl)

            # Update indexes
            if category:
                await pipe.sadd(self._key('index', 'category', category.value), key)
            await pipe.sadd(self._key('index', 'agent', agent_id), key)

            # Add to history (capped list)
            await pipe.lpush(self._key('history'), json.dumps({
                'key': key,
                'agent_id': agent_id,
                'timestamp': entry.timestamp.isoformat(),
                'category': category.value if category else None,
            }))
            await pipe.ltrim(self._key('history'), 0, self.HISTORY_MAX_SIZE - 1)

            # Update stats
            await pipe.hincrby(self._key('stats'), 'total_writes', 1)
            await pipe.hincrby(self._key('stats'), f'agent:{agent_id}:writes', 1)
            if category:
                await pipe.hincrby(self._key('stats'), f'category:{category.value}', 1)

            # Publish update notification
            await pipe.publish(
                self._key('updates', key.split('.')[0]),  # Use first part as channel
                json.dumps(entry_dict)
            )

            await pipe.execute()

        logger.info(
            f"[RedisBlackboard] Published '{key}' (v{version}): {str(value)[:80]}..."
        )

        # Fire event callback
        if self._on_publish:
            try:
                if asyncio.iscoroutinefunction(self._on_publish):
                    await self._on_publish(entry)
                else:
                    self._on_publish(entry)
            except Exception as e:
                logger.error(f"[RedisBlackboard] Event callback error: {e}")

        return entry

    async def get(
        self,
        key: str,
        agent_id: Optional[str] = None,
        default: Any = None
    ) -> Any:
        """Get value from Redis blackboard"""
        await self._ensure_connected()

        redis_key = self._key('entries', key)
        data = await self._redis.hgetall(redis_key)

        if not data:
            return default

        entry = self._dict_to_entry(data)

        # Update read stats
        if agent_id:
            await self._redis.hincrby(self._key('stats'), f'agent:{agent_id}:reads', 1)
        await self._redis.hincrby(self._key('stats'), 'total_reads', 1)

        return entry.value

    async def get_entry(self, key: str) -> Optional[BlackboardEntry]:
        """Get full entry including metadata"""
        await self._ensure_connected()

        redis_key = self._key('entries', key)
        data = await self._redis.hgetall(redis_key)

        if not data:
            return None

        return self._dict_to_entry(data)

    async def get_many(
        self,
        keys: List[str],
        agent_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get multiple values at once"""
        await self._ensure_connected()

        result = {}

        async with self._redis.pipeline() as pipe:
            for key in keys:
                await pipe.hgetall(self._key('entries', key))

            results = await pipe.execute()

        for key, data in zip(keys, results):
            if data:
                entry = self._dict_to_entry(data)
                result[key] = entry.value

        return result

    async def query(
        self,
        pattern: str,
        agent_id: Optional[str] = None,
        tags: Optional[Set[str]] = None,
        category: Optional[DataCategory] = None,
        limit: int = 100
    ) -> List[BlackboardEntry]:
        """Query blackboard with pattern matching"""
        await self._ensure_connected()

        # Use Redis SCAN for pattern matching
        redis_pattern = self._key('entries', pattern.replace('*', '*'))

        entries = []

        # If category specified, use index
        if category:
            keys = await self._redis.smembers(self._key('index', 'category', category.value))
            keys = [k for k in keys if self._pattern_matches(pattern, k)]
        else:
            # Scan for matching keys
            keys = []
            cursor = 0
            while True:
                cursor, batch = await self._redis.scan(
                    cursor=cursor,
                    match=redis_pattern,
                    count=100
                )

                for redis_key in batch:
                    # Extract original key from Redis key
                    key = redis_key.replace(f"{self._key('entries')}:", "")
                    keys.append(key)

                if cursor == 0 or len(keys) >= limit:
                    break

        # Fetch entries
        async with self._redis.pipeline() as pipe:
            for key in keys[:limit]:
                await pipe.hgetall(self._key('entries', key))

            results = await pipe.execute()

        for data in results:
            if data:
                entry = self._dict_to_entry(data)

                # Tag filter
                if tags and not tags.issubset(entry.tags):
                    continue

                entries.append(entry)

        logger.debug(f"[RedisBlackboard] Query '{pattern}' returned {len(entries)} entries")

        return entries

    def _pattern_matches(self, pattern: str, key: str) -> bool:
        """Check if key matches glob pattern"""
        if pattern not in self._compiled_patterns:
            regex_pattern = pattern.replace('.', r'\.').replace('*', '.*')
            self._compiled_patterns[pattern] = re.compile(f'^{regex_pattern}$')

        return self._compiled_patterns[pattern].match(key) is not None

    async def query_by_category(
        self,
        category: DataCategory,
        agent_id: Optional[str] = None,
        limit: int = 100
    ) -> List[BlackboardEntry]:
        """Query by category (fast indexed lookup)"""
        await self._ensure_connected()

        keys = await self._redis.smembers(self._key('index', 'category', category.value))
        keys = list(keys)[:limit]

        entries = []

        if keys:
            async with self._redis.pipeline() as pipe:
                for key in keys:
                    await pipe.hgetall(self._key('entries', key))

                results = await pipe.execute()

            for data in results:
                if data:
                    entries.append(self._dict_to_entry(data))

        return entries

    async def query_by_agent(
        self,
        from_agent: str,
        requester_id: Optional[str] = None,
        limit: int = 100
    ) -> List[BlackboardEntry]:
        """Get all entries published by specific agent"""
        await self._ensure_connected()

        keys = await self._redis.smembers(self._key('index', 'agent', from_agent))
        keys = list(keys)[:limit]

        entries = []

        if keys:
            async with self._redis.pipeline() as pipe:
                for key in keys:
                    await pipe.hgetall(self._key('entries', key))

                results = await pipe.execute()

            for data in results:
                if data:
                    entries.append(self._dict_to_entry(data))

        return entries

    def subscribe(
        self,
        pattern: str,
        agent_id: str,
        callback: Callable[[BlackboardEntry], None],
        categories: Optional[Set[DataCategory]] = None
    ):
        """Subscribe to blackboard updates (local tracking)"""
        subscription = Subscription(
            pattern=pattern,
            agent_id=agent_id,
            callback=callback,
            categories=categories
        )

        self._subscriptions[pattern].append(subscription)

        # Compile pattern
        if pattern not in self._compiled_patterns:
            regex_pattern = pattern.replace('.', r'\.').replace('*', '.*')
            self._compiled_patterns[pattern] = re.compile(f'^{regex_pattern}$')

        logger.info(f"[RedisBlackboard] {agent_id} subscribed to '{pattern}'")

        if self._on_subscribe:
            try:
                self._on_subscribe(subscription)
            except Exception:
                pass

    def unsubscribe(self, pattern: str, agent_id: str):
        """Unsubscribe from pattern"""
        if pattern in self._subscriptions:
            self._subscriptions[pattern] = [
                sub for sub in self._subscriptions[pattern]
                if sub.agent_id != agent_id
            ]

            if not self._subscriptions[pattern]:
                del self._subscriptions[pattern]

    def unsubscribe_all(self, agent_id: str):
        """Remove all subscriptions for an agent"""
        for pattern in list(self._subscriptions.keys()):
            self._subscriptions[pattern] = [
                sub for sub in self._subscriptions[pattern]
                if sub.agent_id != agent_id
            ]
            if not self._subscriptions[pattern]:
                del self._subscriptions[pattern]

    async def _notify_local_subscribers(self, entry: BlackboardEntry):
        """Notify local subscribers of an update"""
        notifications = 0

        for pattern, subscribers in self._subscriptions.items():
            regex = self._compiled_patterns.get(pattern)
            if not regex or not regex.match(entry.key):
                continue

            for sub in subscribers:
                # Skip self-notifications
                if sub.agent_id == entry.agent_id:
                    continue

                # Category filter
                if sub.categories and entry.category not in sub.categories:
                    continue

                try:
                    if asyncio.iscoroutinefunction(sub.callback):
                        await sub.callback(entry)
                    else:
                        sub.callback(entry)

                    sub.trigger_count += 1
                    notifications += 1

                except Exception as e:
                    logger.error(f"[RedisBlackboard] Callback error for {sub.agent_id}: {e}")

        if notifications > 0:
            logger.debug(f"[RedisBlackboard] Notified {notifications} subscribers for '{entry.key}'")

    async def delete(self, key: str):
        """Delete entry"""
        await self._ensure_connected()

        redis_key = self._key('entries', key)

        # Get entry first to update indexes
        data = await self._redis.hgetall(redis_key)

        if data:
            entry = self._dict_to_entry(data)

            async with self._redis.pipeline() as pipe:
                # Delete entry
                await pipe.delete(redis_key)

                # Update indexes
                if entry.category:
                    await pipe.srem(self._key('index', 'category', entry.category.value), key)
                await pipe.srem(self._key('index', 'agent', entry.agent_id), key)

                await pipe.execute()

            logger.debug(f"[RedisBlackboard] Deleted '{key}'")

    async def clear(self, pattern: Optional[str] = None):
        """Clear entries matching pattern (or all)"""
        await self._ensure_connected()

        if pattern is None:
            # Clear all blackboard keys
            cursor = 0
            while True:
                cursor, keys = await self._redis.scan(
                    cursor=cursor,
                    match=f"{self._key_prefix}:{self.PREFIX}:*",
                    count=100
                )

                if keys:
                    await self._redis.delete(*keys)

                if cursor == 0:
                    break

            logger.info("[RedisBlackboard] Cleared all entries")
        else:
            # Clear matching entries
            entries = await self.query(pattern, limit=10000)

            for entry in entries:
                await self.delete(entry.key)

            logger.info(f"[RedisBlackboard] Cleared {len(entries)} entries")

    async def get_all_keys(self) -> List[str]:
        """Get all current keys"""
        await self._ensure_connected()

        keys = []
        cursor = 0

        while True:
            cursor, batch = await self._redis.scan(
                cursor=cursor,
                match=self._key('entries', '*'),
                count=100
            )

            for redis_key in batch:
                key = redis_key.replace(f"{self._key('entries')}:", "")
                keys.append(key)

            if cursor == 0:
                break

        return keys

    async def get_stats(self) -> Dict[str, Any]:
        """Get statistics"""
        await self._ensure_connected()

        stats_data = await self._redis.hgetall(self._key('stats'))

        # Parse stats
        by_agent = defaultdict(lambda: {'writes': 0, 'reads': 0})
        by_category = defaultdict(int)

        total_writes = int(stats_data.get('total_writes', 0))
        total_reads = int(stats_data.get('total_reads', 0))

        for key, value in stats_data.items():
            if key.startswith('agent:') and ':writes' in key:
                agent_id = key.replace('agent:', '').replace(':writes', '')
                by_agent[agent_id]['writes'] = int(value)
            elif key.startswith('agent:') and ':reads' in key:
                agent_id = key.replace('agent:', '').replace(':reads', '')
                by_agent[agent_id]['reads'] = int(value)
            elif key.startswith('category:'):
                cat = key.replace('category:', '')
                by_category[cat] = int(value)

        # Count entries
        total_entries = len(await self.get_all_keys())

        return {
            'total_entries': total_entries,
            'total_writes': total_writes,
            'total_reads': total_reads,
            'total_notifications': 0,  # Would need separate tracking
            'total_subscriptions': sum(len(s) for s in self._subscriptions.values()),
            'by_agent': dict(by_agent),
            'by_category': dict(by_category),
            'active_subscriptions': sum(len(s) for s in self._subscriptions.values()),
            'subscription_patterns': list(self._subscriptions.keys()),
            'backend': 'redis',
            'connected': self._connected,
        }

    async def get_history(
        self,
        agent_id: Optional[str] = None,
        since: Optional[datetime] = None,
        category: Optional[DataCategory] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get blackboard history"""
        await self._ensure_connected()

        # Get history from Redis list
        history_data = await self._redis.lrange(self._key('history'), 0, limit * 2)

        history = []
        for item in history_data:
            entry_meta = json.loads(item)

            # Filter by agent
            if agent_id and entry_meta.get('agent_id') != agent_id:
                continue

            # Filter by time
            if since:
                entry_time = datetime.fromisoformat(entry_meta['timestamp'])
                if entry_time < since:
                    continue

            # Filter by category
            if category and entry_meta.get('category') != category.value:
                continue

            history.append(entry_meta)

            if len(history) >= limit:
                break

        return history

    async def get_snapshot(self) -> Dict[str, Any]:
        """Get complete snapshot of current state"""
        await self._ensure_connected()

        keys = await self.get_all_keys()
        snapshot = {}

        if keys:
            async with self._redis.pipeline() as pipe:
                for key in keys:
                    await pipe.hgetall(self._key('entries', key))

                results = await pipe.execute()

            for key, data in zip(keys, results):
                if data:
                    entry = self._dict_to_entry(data)
                    snapshot[key] = entry.to_dict()

        return snapshot

    async def reset(self):
        """Full reset"""
        await self.clear()
        self._subscriptions.clear()
        self._compiled_patterns.clear()
        logger.info("[RedisBlackboard] Reset complete")

    async def health_check(self) -> Dict[str, Any]:
        """Check Redis connection health"""
        try:
            await self._ensure_connected()
            latency_start = asyncio.get_event_loop().time()
            await self._redis.ping()
            latency = (asyncio.get_event_loop().time() - latency_start) * 1000

            return {
                'healthy': True,
                'latency_ms': round(latency, 2),
                'connected': self._connected,
            }
        except Exception as e:
            return {
                'healthy': False,
                'error': str(e),
                'connected': False,
            }


# Global instance
_redis_blackboard: Optional[RedisBlackboard] = None


def get_redis_blackboard(
    redis_url: str = "redis://localhost:6379",
    key_prefix: str = "growth_engine"
) -> RedisBlackboard:
    """Get or create global Redis blackboard"""
    global _redis_blackboard
    if _redis_blackboard is None:
        _redis_blackboard = RedisBlackboard(redis_url, key_prefix)
    return _redis_blackboard


async def reset_redis_blackboard():
    """Reset global Redis blackboard"""
    global _redis_blackboard
    if _redis_blackboard:
        await _redis_blackboard.reset()
    _redis_blackboard = None
