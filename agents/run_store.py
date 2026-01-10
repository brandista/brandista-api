# -*- coding: utf-8 -*-
"""
Growth Engine 2.0 - RunStore
Abstraction for persistent run state storage.

Supports:
- InMemoryRunStore: For development/testing
- RedisRunStore: For production multi-worker deployments

Redis keys:
- run:{run_id}:meta    (JSON - created_at, user_id, url, etc)
- run:{run_id}:status  (string - pending/running/completed/failed/cancelled)
- run:{run_id}:result  (JSON - final result, optional)
- run:{run_id}:trace   (LIST - trace events)
- run:{run_id}:cancelled (string "1", short TTL)
- runs:index           (ZSET - timestamp -> run_id for listing)
- runs:status:{status} (SET - run_ids by status for filtering)
"""

import asyncio
import json
import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict
from enum import Enum

logger = logging.getLogger(__name__)


# TTL settings (seconds)
RUN_DATA_TTL = 7 * 24 * 3600     # 7 days for meta/status/result/trace
CANCELLED_TTL = 6 * 3600         # 6 hours for cancel flag
EVENT_STREAM_TTL = 24 * 3600     # 24 hours for event stream


@dataclass
class RunMeta:
    """Metadata for a run"""
    run_id: str
    user_id: Optional[str] = None
    url: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RunMeta':
        return cls(**data)


@dataclass
class RunEvent:
    """A single event in the run stream"""
    event_id: Optional[str] = None  # Redis stream ID
    event_type: str = "unknown"
    agent_id: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RunEvent':
        return cls(**data)


class RunStore(ABC):
    """
    Abstract base class for run state storage.

    All methods are async to support Redis operations.
    """

    @abstractmethod
    async def create_run(self, run_id: str, meta: RunMeta) -> bool:
        """Create a new run entry"""
        pass

    @abstractmethod
    async def set_status(self, run_id: str, status: str) -> bool:
        """Set run status (pending/running/completed/failed/cancelled)"""
        pass

    @abstractmethod
    async def get_status(self, run_id: str) -> Optional[str]:
        """Get current run status"""
        pass

    @abstractmethod
    async def set_result(self, run_id: str, result: Dict[str, Any]) -> bool:
        """Store final run result"""
        pass

    @abstractmethod
    async def get_result(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Get run result"""
        pass

    @abstractmethod
    async def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Get full run state (meta + status + result)"""
        pass

    @abstractmethod
    async def list_runs(
        self,
        limit: int = 50,
        offset: int = 0,
        status: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List runs with filtering"""
        pass

    @abstractmethod
    async def cancel(self, run_id: str) -> bool:
        """Mark run as cancelled"""
        pass

    @abstractmethod
    async def is_cancelled(self, run_id: str) -> bool:
        """Check if run is cancelled (fast check for polling)"""
        pass

    @abstractmethod
    async def append_trace(self, run_id: str, event: RunEvent) -> bool:
        """Append event to trace"""
        pass

    @abstractmethod
    async def get_trace(self, run_id: str, limit: int = 100) -> List[RunEvent]:
        """Get trace events"""
        pass

    # Event streaming methods
    @abstractmethod
    async def emit_event(self, run_id: str, event: RunEvent) -> str:
        """Emit event to stream, returns event_id"""
        pass

    @abstractmethod
    async def read_events(
        self,
        run_id: str,
        last_id: str = "0",
        count: int = 100,
        block_ms: int = 0
    ) -> List[RunEvent]:
        """Read events from stream (for WS forwarding)"""
        pass


class InMemoryRunStore(RunStore):
    """
    In-memory implementation for development/testing.
    NOT suitable for multi-worker production!
    """

    def __init__(self):
        self._runs: Dict[str, Dict[str, Any]] = {}
        self._cancelled: set = set()
        self._events: Dict[str, List[RunEvent]] = {}
        self._event_counter: Dict[str, int] = {}
        logger.info("[InMemoryRunStore] Initialized (dev mode only)")

    async def create_run(self, run_id: str, meta: RunMeta) -> bool:
        self._runs[run_id] = {
            'meta': meta.to_dict(),
            'status': 'pending',
            'result': None,
            'trace': []
        }
        self._events[run_id] = []
        self._event_counter[run_id] = 0
        return True

    async def set_status(self, run_id: str, status: str) -> bool:
        if run_id in self._runs:
            self._runs[run_id]['status'] = status
            return True
        return False

    async def get_status(self, run_id: str) -> Optional[str]:
        if run_id in self._runs:
            return self._runs[run_id]['status']
        return None

    async def set_result(self, run_id: str, result: Dict[str, Any]) -> bool:
        if run_id in self._runs:
            self._runs[run_id]['result'] = result
            return True
        return False

    async def get_result(self, run_id: str) -> Optional[Dict[str, Any]]:
        if run_id in self._runs:
            return self._runs[run_id].get('result')
        return None

    async def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        return self._runs.get(run_id)

    async def list_runs(
        self,
        limit: int = 50,
        offset: int = 0,
        status: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        runs = list(self._runs.values())

        # Filter by status
        if status:
            runs = [r for r in runs if r['status'] == status]

        # Filter by user_id
        if user_id:
            runs = [r for r in runs if r['meta'].get('user_id') == user_id]

        # Sort by created_at descending
        runs.sort(key=lambda r: r['meta'].get('created_at', ''), reverse=True)

        # Paginate
        return runs[offset:offset + limit]

    async def cancel(self, run_id: str) -> bool:
        self._cancelled.add(run_id)
        await self.set_status(run_id, 'cancelled')
        return True

    async def is_cancelled(self, run_id: str) -> bool:
        return run_id in self._cancelled

    async def append_trace(self, run_id: str, event: RunEvent) -> bool:
        if run_id in self._runs:
            self._runs[run_id]['trace'].append(event.to_dict())
            return True
        return False

    async def get_trace(self, run_id: str, limit: int = 100) -> List[RunEvent]:
        if run_id in self._runs:
            trace_data = self._runs[run_id].get('trace', [])[-limit:]
            return [RunEvent.from_dict(e) for e in trace_data]
        return []

    async def emit_event(self, run_id: str, event: RunEvent) -> str:
        if run_id not in self._events:
            self._events[run_id] = []
            self._event_counter[run_id] = 0

        self._event_counter[run_id] += 1
        event.event_id = f"{self._event_counter[run_id]}"
        self._events[run_id].append(event)
        return event.event_id

    async def read_events(
        self,
        run_id: str,
        last_id: str = "0",
        count: int = 100,
        block_ms: int = 0
    ) -> List[RunEvent]:
        if run_id not in self._events:
            return []

        last_idx = int(last_id) if last_id != "0" else 0
        events = self._events[run_id][last_idx:last_idx + count]

        # Simulate blocking if no events (for long polling)
        if not events and block_ms > 0:
            await asyncio.sleep(block_ms / 1000.0)
            events = self._events[run_id][last_idx:last_idx + count]

        return events


class RedisRunStore(RunStore):
    """
    Redis-backed implementation for production multi-worker deployments.

    Requires redis-py[async] (aioredis integrated in redis-py>=4.2)
    """

    def __init__(self, redis_client=None, redis_url: str = None):
        """
        Initialize with either a redis client or URL.

        Args:
            redis_client: Existing async Redis client
            redis_url: Redis URL (e.g., redis://localhost:6379)
        """
        self._redis = redis_client
        self._redis_url = redis_url or os.environ.get('REDIS_URL', 'redis://localhost:6379')
        self._connected = False
        logger.info(f"[RedisRunStore] Initialized (url={self._redis_url[:30]}...)")

    async def _ensure_connected(self):
        """Ensure Redis connection is established"""
        if self._connected and self._redis:
            return

        try:
            import redis.asyncio as redis
            self._redis = await redis.from_url(
                self._redis_url,
                encoding="utf-8",
                decode_responses=True
            )
            self._connected = True
            logger.info("[RedisRunStore] Connected to Redis")
        except ImportError:
            raise RuntimeError("redis[async] package required for RedisRunStore. pip install redis[async]")

    def _key(self, run_id: str, suffix: str) -> str:
        """Generate Redis key"""
        return f"run:{run_id}:{suffix}"

    async def create_run(self, run_id: str, meta: RunMeta) -> bool:
        await self._ensure_connected()

        pipe = self._redis.pipeline()

        # Store meta
        pipe.set(self._key(run_id, 'meta'), json.dumps(meta.to_dict()), ex=RUN_DATA_TTL)

        # Set initial status
        pipe.set(self._key(run_id, 'status'), 'pending', ex=RUN_DATA_TTL)

        # Add to index (ZSET with timestamp as score)
        timestamp = datetime.now().timestamp()
        pipe.zadd('runs:index', {run_id: timestamp})

        # Add to status set
        pipe.sadd('runs:status:pending', run_id)

        await pipe.execute()
        logger.debug(f"[RedisRunStore] Created run {run_id}")
        return True

    async def set_status(self, run_id: str, status: str) -> bool:
        await self._ensure_connected()

        # Get old status to update sets
        old_status = await self.get_status(run_id)

        pipe = self._redis.pipeline()

        # Update status
        pipe.set(self._key(run_id, 'status'), status, ex=RUN_DATA_TTL)

        # Update status sets
        if old_status:
            pipe.srem(f'runs:status:{old_status}', run_id)
        pipe.sadd(f'runs:status:{status}', run_id)

        # Update meta timestamps
        meta_key = self._key(run_id, 'meta')
        meta_json = await self._redis.get(meta_key)
        if meta_json:
            meta = json.loads(meta_json)
            if status == 'running' and not meta.get('started_at'):
                meta['started_at'] = datetime.now().isoformat()
            elif status in ('completed', 'failed', 'cancelled'):
                meta['completed_at'] = datetime.now().isoformat()
            pipe.set(meta_key, json.dumps(meta), ex=RUN_DATA_TTL)

        await pipe.execute()
        logger.debug(f"[RedisRunStore] Run {run_id} status: {old_status} -> {status}")
        return True

    async def get_status(self, run_id: str) -> Optional[str]:
        await self._ensure_connected()
        return await self._redis.get(self._key(run_id, 'status'))

    async def set_result(self, run_id: str, result: Dict[str, Any]) -> bool:
        await self._ensure_connected()
        await self._redis.set(
            self._key(run_id, 'result'),
            json.dumps(result, default=str),
            ex=RUN_DATA_TTL
        )
        return True

    async def get_result(self, run_id: str) -> Optional[Dict[str, Any]]:
        await self._ensure_connected()
        result_json = await self._redis.get(self._key(run_id, 'result'))
        if result_json:
            return json.loads(result_json)
        return None

    async def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        await self._ensure_connected()

        pipe = self._redis.pipeline()
        pipe.get(self._key(run_id, 'meta'))
        pipe.get(self._key(run_id, 'status'))
        pipe.get(self._key(run_id, 'result'))

        meta_json, status, result_json = await pipe.execute()

        if not meta_json:
            return None

        return {
            'meta': json.loads(meta_json),
            'status': status or 'unknown',
            'result': json.loads(result_json) if result_json else None
        }

    async def list_runs(
        self,
        limit: int = 50,
        offset: int = 0,
        status: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        await self._ensure_connected()

        # Get run IDs
        if status:
            # Get from status set, then sort by timestamp
            run_ids = list(await self._redis.smembers(f'runs:status:{status}'))
            # Get scores for sorting
            if run_ids:
                scores = await self._redis.zmscore('runs:index', run_ids)
                run_ids = [rid for rid, score in sorted(
                    zip(run_ids, scores),
                    key=lambda x: x[1] or 0,
                    reverse=True
                ) if score is not None]
        else:
            # Get from index (sorted by timestamp, newest first)
            run_ids = await self._redis.zrevrange('runs:index', offset, offset + limit - 1)

        if not run_ids:
            return []

        # Fetch runs
        runs = []
        for run_id in run_ids[offset:offset + limit]:
            run = await self.get_run(run_id)
            if run:
                # Filter by user_id if specified
                if user_id and run['meta'].get('user_id') != user_id:
                    continue
                run['run_id'] = run_id
                runs.append(run)

        return runs

    async def cancel(self, run_id: str) -> bool:
        await self._ensure_connected()

        pipe = self._redis.pipeline()

        # Set cancel flag with short TTL
        pipe.set(self._key(run_id, 'cancelled'), '1', ex=CANCELLED_TTL)

        # Update status
        await pipe.execute()
        await self.set_status(run_id, 'cancelled')

        logger.info(f"[RedisRunStore] Run {run_id} cancelled")
        return True

    async def is_cancelled(self, run_id: str) -> bool:
        """Fast cancel check - agents poll this"""
        await self._ensure_connected()
        result = await self._redis.get(self._key(run_id, 'cancelled'))
        return result == '1'

    async def append_trace(self, run_id: str, event: RunEvent) -> bool:
        await self._ensure_connected()
        await self._redis.rpush(
            self._key(run_id, 'trace'),
            json.dumps(event.to_dict())
        )
        await self._redis.expire(self._key(run_id, 'trace'), RUN_DATA_TTL)
        return True

    async def get_trace(self, run_id: str, limit: int = 100) -> List[RunEvent]:
        await self._ensure_connected()
        events_json = await self._redis.lrange(
            self._key(run_id, 'trace'),
            -limit,
            -1
        )
        return [RunEvent.from_dict(json.loads(e)) for e in events_json]

    async def emit_event(self, run_id: str, event: RunEvent) -> str:
        """Emit event to Redis Stream"""
        await self._ensure_connected()

        stream_key = self._key(run_id, 'events')

        # Add to stream
        event_id = await self._redis.xadd(
            stream_key,
            {
                'type': event.event_type,
                'agent_id': event.agent_id or '',
                'timestamp': event.timestamp,
                'data': json.dumps(event.data)
            },
            maxlen=1000  # Keep last 1000 events
        )

        # Set TTL on stream
        await self._redis.expire(stream_key, EVENT_STREAM_TTL)

        return event_id

    async def read_events(
        self,
        run_id: str,
        last_id: str = "0",
        count: int = 100,
        block_ms: int = 0
    ) -> List[RunEvent]:
        """Read events from Redis Stream (for WS forwarding)"""
        await self._ensure_connected()

        stream_key = self._key(run_id, 'events')

        try:
            # XREAD with optional blocking
            if block_ms > 0:
                result = await self._redis.xread(
                    {stream_key: last_id},
                    count=count,
                    block=block_ms
                )
            else:
                result = await self._redis.xread(
                    {stream_key: last_id},
                    count=count
                )

            if not result:
                return []

            # Parse stream entries
            events = []
            for stream_name, entries in result:
                for entry_id, entry_data in entries:
                    events.append(RunEvent(
                        event_id=entry_id,
                        event_type=entry_data.get('type', 'unknown'),
                        agent_id=entry_data.get('agent_id') or None,
                        timestamp=entry_data.get('timestamp', ''),
                        data=json.loads(entry_data.get('data', '{}'))
                    ))

            return events

        except Exception as e:
            logger.error(f"[RedisRunStore] Error reading events: {e}")
            return []


# Factory function

def get_run_store(redis_url: str = None, force_memory: bool = False) -> RunStore:
    """
    Factory to create appropriate RunStore.

    Uses Redis if REDIS_URL is set and redis package available.
    Falls back to InMemory for development.
    """
    redis_url = redis_url or os.environ.get('REDIS_URL')

    if force_memory:
        logger.info("[RunStore] Using InMemoryRunStore (forced)")
        return InMemoryRunStore()

    if redis_url:
        try:
            return RedisRunStore(redis_url=redis_url)
        except Exception as e:
            logger.warning(f"[RunStore] Redis unavailable ({e}), falling back to InMemory")

    logger.info("[RunStore] Using InMemoryRunStore (no REDIS_URL)")
    return InMemoryRunStore()
