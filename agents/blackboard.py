# -*- coding: utf-8 -*-
"""
Growth Engine 2.0 - Blackboard Architecture
TRUE SWARM EDITION - Reactive shared memory

The Blackboard is where agents:
- Publish intermediate findings in real-time
- Subscribe to updates from other agents
- Query shared knowledge
- Build collective understanding

This enables TRUE collective intelligence where each agent's
discoveries immediately benefit all other agents.
"""

import asyncio
import logging
import re
from typing import Dict, Any, List, Optional, Callable, Set, Pattern, Union
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import defaultdict
from enum import Enum
import json

logger = logging.getLogger(__name__)


class DataCategory(Enum):
    """Categories of blackboard data"""
    COMPETITOR = "competitor"
    ANALYSIS = "analysis"
    THREAT = "threat"
    OPPORTUNITY = "opportunity"
    SCORE = "score"
    INSIGHT = "insight"
    RECOMMENDATION = "recommendation"
    ACTION = "action"
    META = "meta"


@dataclass
class BlackboardEntry:
    """
    Single entry on the blackboard.
    
    Keys use hierarchical namespace:
    - "scout.competitors.discovered"
    - "analyst.scores.security"
    - "guardian.threats.critical"
    """
    
    key: str
    value: Any
    agent_id: str
    timestamp: datetime = field(default_factory=datetime.now)
    ttl: Optional[int] = None
    tags: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)
    category: Optional[DataCategory] = None
    version: int = 1
    previous_value: Any = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'key': self.key,
            'value': self.value,
            'agent_id': self.agent_id,
            'timestamp': self.timestamp.isoformat(),
            'ttl': self.ttl,
            'tags': list(self.tags),
            'metadata': self.metadata,
            'category': self.category.value if self.category else None,
            'version': self.version
        }
    
    def is_expired(self) -> bool:
        """Check if entry has expired"""
        if self.ttl is None:
            return False
        age = (datetime.now() - self.timestamp).total_seconds()
        return age > self.ttl
    
    def has_changed(self, new_value: Any) -> bool:
        """Check if value has changed significantly"""
        if self.value is None:
            return new_value is not None
        
        # Deep comparison for dicts
        if isinstance(self.value, dict) and isinstance(new_value, dict):
            return json.dumps(self.value, sort_keys=True) != json.dumps(new_value, sort_keys=True)
        
        return self.value != new_value


@dataclass
class Subscription:
    """Blackboard subscription"""
    pattern: str
    agent_id: str
    callback: Callable
    categories: Optional[Set[DataCategory]] = None
    created_at: datetime = field(default_factory=datetime.now)
    trigger_count: int = 0


class Blackboard:
    """
    Shared working memory for agent swarm.
    
    The bulletin board where agents pin notes, read others' findings,
    and get notified in real-time when relevant data appears.
    """
    
    def __init__(self):
        # Storage: key -> BlackboardEntry
        self._data: Dict[str, BlackboardEntry] = {}
        
        # History: all entries ever posted (for replay)
        self._history: List[BlackboardEntry] = []
        
        # Subscriptions: pattern -> [Subscription]
        self._subscriptions: Dict[str, List[Subscription]] = defaultdict(list)
        
        # Compiled regex patterns
        self._compiled_patterns: Dict[str, Pattern] = {}
        
        # Index by category for fast lookup
        self._by_category: Dict[DataCategory, Set[str]] = defaultdict(set)
        
        # Index by agent
        self._by_agent: Dict[str, Set[str]] = defaultdict(set)
        
        # Event callbacks for monitoring
        self._on_publish: Optional[Callable] = None
        self._on_subscribe: Optional[Callable] = None
        
        # Statistics
        self._stats = {
            'total_writes': 0,
            'total_reads': 0,
            'total_notifications': 0,
            'total_subscriptions': 0,
            'by_agent': defaultdict(lambda: {'writes': 0, 'reads': 0}),
            'by_category': defaultdict(int)
        }
        
        # Lock for thread safety
        self._lock = asyncio.Lock()
        
        logger.info("[Blackboard] 📋 Blackboard initialized")
    
    def set_event_callbacks(
        self,
        on_publish: Optional[Callable] = None,
        on_subscribe: Optional[Callable] = None
    ):
        """Set callbacks for blackboard events"""
        self._on_publish = on_publish
        self._on_subscribe = on_subscribe
    
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
        Publish data to blackboard.
        
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
        async with self._lock:
            # Check for existing entry (versioning)
            existing = self._data.get(key)
            version = 1
            previous_value = None
            
            if existing:
                version = existing.version + 1
                previous_value = existing.value
                
                # Skip if value hasn't changed
                if not existing.has_changed(value):
                    logger.debug(f"[Blackboard] Skipping unchanged value for '{key}'")
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
            
            # Store entry
            self._data[key] = entry
            self._history.append(entry)
            
            # Update indexes
            if category:
                self._by_category[category].add(key)
            self._by_agent[agent_id].add(key)
            
            # Update stats
            self._stats['total_writes'] += 1
            self._stats['by_agent'][agent_id]['writes'] += 1
            if category:
                self._stats['by_category'][category.value] += 1
        
        logger.info(
            f"[Blackboard] 📌 {agent_id} published '{key}' "
            f"(v{version}): {str(value)[:80]}..."
        )
        
        # Notify subscribers (outside lock)
        await self._notify_subscribers(entry)
        
        # Fire event callback
        if self._on_publish:
            try:
                if asyncio.iscoroutinefunction(self._on_publish):
                    await self._on_publish(entry)
                else:
                    self._on_publish(entry)
            except Exception as e:
                logger.error(f"[Blackboard] Event callback error: {e}")
        
        return entry
    
    def publish_sync(
        self,
        key: str,
        value: Any,
        agent_id: str,
        **kwargs
    ):
        """Synchronous publish (schedules async)"""
        asyncio.create_task(self.publish(key, value, agent_id, **kwargs))
    
    def get(
        self,
        key: str,
        agent_id: Optional[str] = None,
        default: Any = None
    ) -> Any:
        """
        Get value from blackboard.
        
        Args:
            key: Key to retrieve
            agent_id: Agent requesting (for stats)
            default: Default value if not found
        """
        entry = self._data.get(key)
        
        if entry is None:
            return default
        
        # Check expiration
        if entry.is_expired():
            del self._data[key]
            return default
        
        # Update stats
        self._stats['total_reads'] += 1
        if agent_id:
            self._stats['by_agent'][agent_id]['reads'] += 1
        
        return entry.value
    
    def get_entry(self, key: str) -> Optional[BlackboardEntry]:
        """Get full entry including metadata"""
        entry = self._data.get(key)
        
        if entry and entry.is_expired():
            del self._data[key]
            return None
        
        return entry
    
    def get_many(
        self,
        keys: List[str],
        agent_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get multiple values at once"""
        result = {}
        for key in keys:
            value = self.get(key, agent_id)
            if value is not None:
                result[key] = value
        return result
    
    def query(
        self,
        pattern: str,
        agent_id: Optional[str] = None,
        tags: Optional[Set[str]] = None,
        category: Optional[DataCategory] = None,
        limit: int = 100
    ) -> List[BlackboardEntry]:
        """
        Query blackboard with pattern matching.
        
        Args:
            pattern: Glob pattern (e.g. "scout.*", "*.threat")
            agent_id: Agent querying
            tags: Filter by tags
            category: Filter by category
            limit: Max results
        """
        # Get or compile pattern
        if pattern not in self._compiled_patterns:
            regex_pattern = pattern.replace('.', r'\.').replace('*', '.*')
            self._compiled_patterns[pattern] = re.compile(f'^{regex_pattern}$')
        
        regex = self._compiled_patterns[pattern]
        results = []
        
        # Start with category index if available
        if category:
            keys_to_check = self._by_category.get(category, set())
        else:
            keys_to_check = self._data.keys()
        
        for key in keys_to_check:
            if len(results) >= limit:
                break
            
            entry = self._data.get(key)
            if not entry or entry.is_expired():
                continue
            
            # Pattern match
            if not regex.match(key):
                continue
            
            # Tag filter
            if tags and not tags.issubset(entry.tags):
                continue
            
            results.append(entry)
        
        # Update stats
        if agent_id:
            self._stats['by_agent'][agent_id]['reads'] += len(results)
        
        logger.debug(f"[Blackboard] 🔍 Query '{pattern}' returned {len(results)} entries")
        
        return results
    
    def query_by_category(
        self,
        category: DataCategory,
        agent_id: Optional[str] = None,
        limit: int = 100
    ) -> List[BlackboardEntry]:
        """Query by category (fast indexed lookup)"""
        keys = list(self._by_category.get(category, set()))[:limit]
        entries = []
        
        for key in keys:
            entry = self._data.get(key)
            if entry and not entry.is_expired():
                entries.append(entry)
        
        if agent_id:
            self._stats['by_agent'][agent_id]['reads'] += len(entries)
        
        return entries
    
    def query_by_agent(
        self,
        from_agent: str,
        requester_id: Optional[str] = None,
        limit: int = 100
    ) -> List[BlackboardEntry]:
        """Get all entries published by specific agent"""
        keys = list(self._by_agent.get(from_agent, set()))[:limit]
        entries = []
        
        for key in keys:
            entry = self._data.get(key)
            if entry and not entry.is_expired():
                entries.append(entry)
        
        if requester_id:
            self._stats['by_agent'][requester_id]['reads'] += len(entries)
        
        return entries
    
    def subscribe(
        self,
        pattern: str,
        agent_id: str,
        callback: Callable[[BlackboardEntry], None],
        categories: Optional[Set[DataCategory]] = None
    ):
        """
        Subscribe to blackboard updates.
        
        Args:
            pattern: Glob pattern to match
            agent_id: Agent subscribing
            callback: Function to call on match
            categories: Optional category filter
        """
        subscription = Subscription(
            pattern=pattern,
            agent_id=agent_id,
            callback=callback,
            categories=categories
        )
        
        self._subscriptions[pattern].append(subscription)
        
        # Compile pattern if needed
        if pattern not in self._compiled_patterns:
            regex_pattern = pattern.replace('.', r'\.').replace('*', '.*')
            self._compiled_patterns[pattern] = re.compile(f'^{regex_pattern}$')
        
        self._stats['total_subscriptions'] += 1
        
        logger.info(f"[Blackboard] 📬 {agent_id} subscribed to '{pattern}'")
        
        # Fire callback
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
            
            # Clean up empty patterns
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
    
    async def _notify_subscribers(self, entry: BlackboardEntry):
        """Notify all matching subscribers"""
        notifications = 0
        
        for pattern, subscribers in self._subscriptions.items():
            regex = self._compiled_patterns.get(pattern)
            if not regex:
                continue
            
            if not regex.match(entry.key):
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
                    logger.error(
                        f"[Blackboard] ❌ Callback error for {sub.agent_id}: {e}"
                    )
        
        if notifications > 0:
            self._stats['total_notifications'] += notifications
            logger.debug(
                f"[Blackboard] 🔔 Notified {notifications} subscribers for '{entry.key}'"
            )
    
    def delete(self, key: str):
        """Delete entry"""
        if key in self._data:
            entry = self._data[key]
            
            # Remove from indexes
            if entry.category:
                self._by_category[entry.category].discard(key)
            self._by_agent[entry.agent_id].discard(key)
            
            del self._data[key]
            logger.debug(f"[Blackboard] 🗑️ Deleted '{key}'")
    
    def clear(self, pattern: Optional[str] = None):
        """Clear entries matching pattern (or all)"""
        if pattern is None:
            self._data.clear()
            self._by_category.clear()
            self._by_agent.clear()
            logger.info("[Blackboard] 🗑️ Cleared all entries")
        else:
            regex = re.compile(pattern.replace('.', r'\.').replace('*', '.*'))
            keys_to_delete = [k for k in self._data if regex.match(k)]
            
            for key in keys_to_delete:
                self.delete(key)
            
            logger.info(f"[Blackboard] 🗑️ Cleared {len(keys_to_delete)} entries")
    
    def cleanup_expired(self) -> int:
        """Remove expired entries"""
        expired = [k for k, e in self._data.items() if e.is_expired()]
        
        for key in expired:
            self.delete(key)
        
        if expired:
            logger.info(f"[Blackboard] 🧹 Cleaned {len(expired)} expired entries")
        
        return len(expired)
    
    def get_all_keys(self) -> List[str]:
        """Get all current keys"""
        return list(self._data.keys())
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics"""
        return {
            'total_entries': len(self._data),
            'total_writes': self._stats['total_writes'],
            'total_reads': self._stats['total_reads'],
            'total_notifications': self._stats['total_notifications'],
            'total_subscriptions': self._stats['total_subscriptions'],
            'by_agent': {k: dict(v) for k, v in self._stats['by_agent'].items()},
            'by_category': dict(self._stats['by_category']),
            'active_subscriptions': sum(len(s) for s in self._subscriptions.values()),
            'subscription_patterns': list(self._subscriptions.keys()),
            'history_size': len(self._history)
        }
    
    def get_history(
        self,
        agent_id: Optional[str] = None,
        since: Optional[datetime] = None,
        category: Optional[DataCategory] = None,
        limit: int = 100
    ) -> List[BlackboardEntry]:
        """Get blackboard history"""
        history = self._history
        
        if agent_id:
            history = [e for e in history if e.agent_id == agent_id]
        
        if since:
            history = [e for e in history if e.timestamp >= since]
        
        if category:
            history = [e for e in history if e.category == category]
        
        return history[-limit:]
    
    def get_snapshot(self) -> Dict[str, Any]:
        """Get complete snapshot of current state"""
        return {
            key: entry.to_dict()
            for key, entry in self._data.items()
            if not entry.is_expired()
        }
    
    def reset(self):
        """Full reset"""
        self._data.clear()
        self._history.clear()
        self._subscriptions.clear()
        self._compiled_patterns.clear()
        self._by_category.clear()
        self._by_agent.clear()
        self._stats = {
            'total_writes': 0,
            'total_reads': 0,
            'total_notifications': 0,
            'total_subscriptions': 0,
            'by_agent': defaultdict(lambda: {'writes': 0, 'reads': 0}),
            'by_category': defaultdict(int)
        }
        logger.info("[Blackboard] 🔄 Blackboard reset")


# Global blackboard instance
_blackboard: Optional[Blackboard] = None


def get_blackboard() -> Blackboard:
    """Get or create global blackboard"""
    global _blackboard
    if _blackboard is None:
        _blackboard = Blackboard()
    return _blackboard


def reset_blackboard():
    """Reset global blackboard"""
    global _blackboard
    if _blackboard:
        _blackboard.reset()
    _blackboard = None
