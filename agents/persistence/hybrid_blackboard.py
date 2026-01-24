# -*- coding: utf-8 -*-
"""
Growth Engine 2.0 - Hybrid Blackboard
Seamless migration between in-memory and Redis storage

Version: 3.0.0

The HybridBlackboard enables zero-downtime migration:
1. MEMORY_ONLY: Original behavior (default)
2. DUAL_WRITE: Write to both, read from memory (migration phase)
3. DUAL_WRITE_READ_REDIS: Write to both, read from Redis (validation phase)
4. REDIS_ONLY: Full Redis mode (target state)

This allows gradual migration with rollback capability at each step.
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional, Callable, Set
from datetime import datetime
from enum import Enum

from agents.blackboard import (
    Blackboard,
    BlackboardEntry,
    DataCategory,
    get_blackboard,
)
from agents.persistence.redis_blackboard import (
    RedisBlackboard,
    get_redis_blackboard,
    RedisConnectionError,
)

logger = logging.getLogger(__name__)


class BlackboardMode(Enum):
    """Operating mode for hybrid blackboard"""
    MEMORY_ONLY = "memory_only"           # Default: in-memory only
    DUAL_WRITE = "dual_write"             # Write both, read memory
    DUAL_WRITE_READ_REDIS = "dual_read"   # Write both, read Redis
    REDIS_ONLY = "redis_only"             # Redis only


class HybridBlackboard:
    """
    Hybrid blackboard that can operate in multiple modes.

    Provides seamless migration path from in-memory to Redis storage.
    """

    def __init__(
        self,
        mode: BlackboardMode = BlackboardMode.MEMORY_ONLY,
        redis_url: str = "redis://localhost:6379",
        key_prefix: str = "growth_engine",
        fallback_on_redis_error: bool = True,
    ):
        """
        Initialize hybrid blackboard.

        Args:
            mode: Operating mode
            redis_url: Redis connection URL
            key_prefix: Redis key prefix
            fallback_on_redis_error: Fall back to memory on Redis errors
        """
        self._mode = mode
        self._redis_url = redis_url
        self._key_prefix = key_prefix
        self._fallback_on_error = fallback_on_redis_error

        # Storage backends
        self._memory: Blackboard = get_blackboard()
        self._redis: Optional[RedisBlackboard] = None

        # Redis connection state
        self._redis_connected = False
        self._redis_errors = 0
        self._max_redis_errors = 5  # Circuit breaker threshold

        # Callbacks
        self._on_publish: Optional[Callable] = None
        self._on_subscribe: Optional[Callable] = None

        # Statistics
        self._stats = {
            'memory_writes': 0,
            'redis_writes': 0,
            'memory_reads': 0,
            'redis_reads': 0,
            'redis_fallbacks': 0,
            'mode_changes': 0,
        }

        logger.info(f"[HybridBlackboard] Initialized in {mode.value} mode")

    async def initialize(self):
        """Initialize connections based on mode"""
        if self._mode != BlackboardMode.MEMORY_ONLY:
            try:
                self._redis = get_redis_blackboard(self._redis_url, self._key_prefix)
                await self._redis.connect()
                self._redis_connected = True
                logger.info("[HybridBlackboard] Redis connected")
            except Exception as e:
                logger.error(f"[HybridBlackboard] Redis connection failed: {e}")
                if not self._fallback_on_error:
                    raise
                logger.warning("[HybridBlackboard] Falling back to memory-only mode")
                self._mode = BlackboardMode.MEMORY_ONLY

    async def set_mode(self, mode: BlackboardMode):
        """
        Change operating mode.

        Args:
            mode: New operating mode
        """
        old_mode = self._mode

        # Initialize Redis if needed
        if mode != BlackboardMode.MEMORY_ONLY and not self._redis_connected:
            await self.initialize()

        self._mode = mode
        self._stats['mode_changes'] += 1

        logger.info(f"[HybridBlackboard] Mode changed: {old_mode.value} -> {mode.value}")

    def get_mode(self) -> BlackboardMode:
        """Get current operating mode"""
        return self._mode

    def set_event_callbacks(
        self,
        on_publish: Optional[Callable] = None,
        on_subscribe: Optional[Callable] = None
    ):
        """Set callbacks for events"""
        self._on_publish = on_publish
        self._on_subscribe = on_subscribe

        # Propagate to backends
        self._memory.set_event_callbacks(on_publish, on_subscribe)
        if self._redis:
            self._redis.set_event_callbacks(on_publish, on_subscribe)

    async def _write_to_redis(
        self,
        key: str,
        value: Any,
        agent_id: str,
        **kwargs
    ) -> Optional[BlackboardEntry]:
        """Write to Redis with error handling"""
        if not self._redis or not self._redis_connected:
            return None

        try:
            entry = await self._redis.publish(key, value, agent_id, **kwargs)
            self._stats['redis_writes'] += 1
            self._redis_errors = 0  # Reset error counter
            return entry
        except Exception as e:
            self._redis_errors += 1
            logger.error(f"[HybridBlackboard] Redis write error: {e}")

            # Circuit breaker
            if self._redis_errors >= self._max_redis_errors:
                logger.warning("[HybridBlackboard] Too many Redis errors, disabling Redis writes")
                self._redis_connected = False

            return None

    async def _read_from_redis(
        self,
        key: str,
        agent_id: Optional[str] = None,
        default: Any = None
    ) -> Any:
        """Read from Redis with error handling"""
        if not self._redis or not self._redis_connected:
            return None

        try:
            value = await self._redis.get(key, agent_id, default)
            self._stats['redis_reads'] += 1
            return value
        except Exception as e:
            self._redis_errors += 1
            logger.error(f"[HybridBlackboard] Redis read error: {e}")

            if self._redis_errors >= self._max_redis_errors:
                self._redis_connected = False

            return None

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
        Publish data based on current mode.

        Args:
            key: Hierarchical key
            value: Data to publish
            agent_id: Agent publishing
            ttl: Time-to-live in seconds
            tags: Tags for categorization
            metadata: Additional metadata
            category: Data category

        Returns:
            BlackboardEntry from primary storage
        """
        kwargs = {
            'ttl': ttl,
            'tags': tags,
            'metadata': metadata,
            'category': category,
        }

        if self._mode == BlackboardMode.MEMORY_ONLY:
            # Memory only
            entry = await self._memory.publish(key, value, agent_id, **kwargs)
            self._stats['memory_writes'] += 1
            return entry

        elif self._mode == BlackboardMode.DUAL_WRITE:
            # Write to both, return from memory
            entry = await self._memory.publish(key, value, agent_id, **kwargs)
            self._stats['memory_writes'] += 1

            # Async write to Redis (don't wait)
            asyncio.create_task(self._write_to_redis(key, value, agent_id, **kwargs))
            return entry

        elif self._mode == BlackboardMode.DUAL_WRITE_READ_REDIS:
            # Write to both, return from Redis
            await self._memory.publish(key, value, agent_id, **kwargs)
            self._stats['memory_writes'] += 1

            redis_entry = await self._write_to_redis(key, value, agent_id, **kwargs)

            if redis_entry:
                return redis_entry
            else:
                # Fallback to memory on Redis error
                self._stats['redis_fallbacks'] += 1
                return await self._memory.publish(key, value, agent_id, **kwargs)

        else:  # REDIS_ONLY
            redis_entry = await self._write_to_redis(key, value, agent_id, **kwargs)

            if redis_entry:
                return redis_entry
            elif self._fallback_on_error:
                # Fallback to memory
                self._stats['redis_fallbacks'] += 1
                entry = await self._memory.publish(key, value, agent_id, **kwargs)
                self._stats['memory_writes'] += 1
                return entry
            else:
                raise RedisConnectionError("Redis write failed and fallback disabled")

    def publish_sync(self, key: str, value: Any, agent_id: str, **kwargs):
        """Synchronous publish"""
        asyncio.create_task(self.publish(key, value, agent_id, **kwargs))

    async def get(
        self,
        key: str,
        agent_id: Optional[str] = None,
        default: Any = None
    ) -> Any:
        """Get value based on current mode"""
        if self._mode == BlackboardMode.MEMORY_ONLY:
            self._stats['memory_reads'] += 1
            return self._memory.get(key, agent_id, default)

        elif self._mode == BlackboardMode.DUAL_WRITE:
            # Read from memory (primary during migration)
            self._stats['memory_reads'] += 1
            return self._memory.get(key, agent_id, default)

        elif self._mode in (BlackboardMode.DUAL_WRITE_READ_REDIS, BlackboardMode.REDIS_ONLY):
            # Read from Redis
            value = await self._read_from_redis(key, agent_id, None)

            if value is not None:
                return value
            elif self._mode == BlackboardMode.DUAL_WRITE_READ_REDIS or self._fallback_on_error:
                # Fallback to memory
                self._stats['redis_fallbacks'] += 1
                self._stats['memory_reads'] += 1
                return self._memory.get(key, agent_id, default)
            else:
                return default

    def get_sync(self, key: str, agent_id: Optional[str] = None, default: Any = None) -> Any:
        """Synchronous get - only works for memory mode"""
        if self._mode in (BlackboardMode.MEMORY_ONLY, BlackboardMode.DUAL_WRITE):
            return self._memory.get(key, agent_id, default)
        else:
            raise RuntimeError("Sync get not available in Redis mode - use async get()")

    async def get_entry(self, key: str) -> Optional[BlackboardEntry]:
        """Get full entry"""
        if self._mode in (BlackboardMode.MEMORY_ONLY, BlackboardMode.DUAL_WRITE):
            return self._memory.get_entry(key)
        else:
            if self._redis and self._redis_connected:
                entry = await self._redis.get_entry(key)
                if entry:
                    return entry

            # Fallback
            return self._memory.get_entry(key)

    async def query(
        self,
        pattern: str,
        agent_id: Optional[str] = None,
        tags: Optional[Set[str]] = None,
        category: Optional[DataCategory] = None,
        limit: int = 100
    ) -> List[BlackboardEntry]:
        """Query based on current mode"""
        if self._mode in (BlackboardMode.MEMORY_ONLY, BlackboardMode.DUAL_WRITE):
            return self._memory.query(pattern, agent_id, tags, category, limit)
        else:
            if self._redis and self._redis_connected:
                try:
                    return await self._redis.query(pattern, agent_id, tags, category, limit)
                except Exception as e:
                    logger.error(f"[HybridBlackboard] Redis query error: {e}")

            return self._memory.query(pattern, agent_id, tags, category, limit)

    async def query_by_category(
        self,
        category: DataCategory,
        agent_id: Optional[str] = None,
        limit: int = 100
    ) -> List[BlackboardEntry]:
        """Query by category"""
        if self._mode in (BlackboardMode.MEMORY_ONLY, BlackboardMode.DUAL_WRITE):
            return self._memory.query_by_category(category, agent_id, limit)
        else:
            if self._redis and self._redis_connected:
                try:
                    return await self._redis.query_by_category(category, agent_id, limit)
                except Exception:
                    pass

            return self._memory.query_by_category(category, agent_id, limit)

    def subscribe(
        self,
        pattern: str,
        agent_id: str,
        callback: Callable[[BlackboardEntry], None],
        categories: Optional[Set[DataCategory]] = None
    ):
        """Subscribe to updates"""
        # Always subscribe to memory (for local notifications)
        self._memory.subscribe(pattern, agent_id, callback, categories)

        # Also subscribe to Redis if available
        if self._redis and self._redis_connected:
            self._redis.subscribe(pattern, agent_id, callback, categories)

    def unsubscribe(self, pattern: str, agent_id: str):
        """Unsubscribe from pattern"""
        self._memory.unsubscribe(pattern, agent_id)
        if self._redis:
            self._redis.unsubscribe(pattern, agent_id)

    def unsubscribe_all(self, agent_id: str):
        """Remove all subscriptions"""
        self._memory.unsubscribe_all(agent_id)
        if self._redis:
            self._redis.unsubscribe_all(agent_id)

    async def delete(self, key: str):
        """Delete entry"""
        self._memory.delete(key)

        if self._redis and self._redis_connected:
            try:
                await self._redis.delete(key)
            except Exception as e:
                logger.error(f"[HybridBlackboard] Redis delete error: {e}")

    async def clear(self, pattern: Optional[str] = None):
        """Clear entries"""
        self._memory.clear(pattern)

        if self._redis and self._redis_connected:
            try:
                await self._redis.clear(pattern)
            except Exception as e:
                logger.error(f"[HybridBlackboard] Redis clear error: {e}")

    def get_all_keys(self) -> List[str]:
        """Get all keys from primary storage"""
        return self._memory.get_all_keys()

    async def get_all_keys_async(self) -> List[str]:
        """Get all keys (async for Redis mode)"""
        if self._mode in (BlackboardMode.MEMORY_ONLY, BlackboardMode.DUAL_WRITE):
            return self._memory.get_all_keys()
        else:
            if self._redis and self._redis_connected:
                try:
                    return await self._redis.get_all_keys()
                except Exception:
                    pass
            return self._memory.get_all_keys()

    def get_stats(self) -> Dict[str, Any]:
        """Get combined statistics"""
        memory_stats = self._memory.get_stats()

        stats = {
            **self._stats,
            'mode': self._mode.value,
            'redis_connected': self._redis_connected,
            'redis_errors': self._redis_errors,
            'memory': memory_stats,
        }

        return stats

    async def get_full_stats(self) -> Dict[str, Any]:
        """Get full statistics including Redis"""
        stats = self.get_stats()

        if self._redis and self._redis_connected:
            try:
                stats['redis'] = await self._redis.get_stats()
            except Exception:
                pass

        return stats

    def get_history(
        self,
        agent_id: Optional[str] = None,
        since: Optional[datetime] = None,
        category: Optional[DataCategory] = None,
        limit: int = 100
    ) -> List[BlackboardEntry]:
        """Get history from memory"""
        return self._memory.get_history(agent_id, since, category, limit)

    def get_snapshot(self) -> Dict[str, Any]:
        """Get snapshot from memory"""
        return self._memory.get_snapshot()

    async def reset(self):
        """Full reset"""
        self._memory.reset()

        if self._redis:
            try:
                await self._redis.reset()
            except Exception:
                pass

        self._stats = {
            'memory_writes': 0,
            'redis_writes': 0,
            'memory_reads': 0,
            'redis_reads': 0,
            'redis_fallbacks': 0,
            'mode_changes': 0,
        }

        logger.info("[HybridBlackboard] Reset complete")

    async def sync_memory_to_redis(self) -> int:
        """
        Sync all memory entries to Redis.

        Use during migration to populate Redis from memory.

        Returns:
            Number of entries synced
        """
        if not self._redis or not self._redis_connected:
            raise RuntimeError("Redis not connected")

        snapshot = self._memory.get_snapshot()
        synced = 0

        for key, entry_dict in snapshot.items():
            try:
                # Recreate entry
                category = DataCategory(entry_dict['category']) if entry_dict.get('category') else None

                await self._redis.publish(
                    key=entry_dict['key'],
                    value=entry_dict['value'],
                    agent_id=entry_dict['agent_id'],
                    ttl=entry_dict.get('ttl'),
                    tags=set(entry_dict.get('tags', [])),
                    metadata=entry_dict.get('metadata', {}),
                    category=category,
                )
                synced += 1
            except Exception as e:
                logger.error(f"[HybridBlackboard] Sync error for {key}: {e}")

        logger.info(f"[HybridBlackboard] Synced {synced} entries to Redis")
        return synced

    async def verify_sync(self) -> Dict[str, Any]:
        """
        Verify memory and Redis are in sync.

        Returns:
            Verification report
        """
        if not self._redis or not self._redis_connected:
            return {'error': 'Redis not connected'}

        memory_keys = set(self._memory.get_all_keys())
        redis_keys = set(await self._redis.get_all_keys())

        only_in_memory = memory_keys - redis_keys
        only_in_redis = redis_keys - memory_keys
        in_both = memory_keys & redis_keys

        # Check values for keys in both
        mismatched = []
        for key in in_both:
            mem_value = self._memory.get(key)
            redis_value = await self._redis.get(key)

            if mem_value != redis_value:
                mismatched.append(key)

        return {
            'in_sync': len(only_in_memory) == 0 and len(only_in_redis) == 0 and len(mismatched) == 0,
            'memory_count': len(memory_keys),
            'redis_count': len(redis_keys),
            'only_in_memory': list(only_in_memory),
            'only_in_redis': list(only_in_redis),
            'value_mismatches': mismatched,
        }

    async def health_check(self) -> Dict[str, Any]:
        """Health check for both backends"""
        health = {
            'mode': self._mode.value,
            'memory': {'healthy': True},
        }

        if self._redis:
            health['redis'] = await self._redis.health_check()

        return health


# Global instance
_hybrid_blackboard: Optional[HybridBlackboard] = None


def get_hybrid_blackboard(
    mode: BlackboardMode = BlackboardMode.MEMORY_ONLY,
    redis_url: str = "redis://localhost:6379",
    key_prefix: str = "growth_engine"
) -> HybridBlackboard:
    """Get or create global hybrid blackboard"""
    global _hybrid_blackboard
    if _hybrid_blackboard is None:
        _hybrid_blackboard = HybridBlackboard(mode, redis_url, key_prefix)
    return _hybrid_blackboard


async def reset_hybrid_blackboard():
    """Reset global hybrid blackboard"""
    global _hybrid_blackboard
    if _hybrid_blackboard:
        await _hybrid_blackboard.reset()
    _hybrid_blackboard = None
