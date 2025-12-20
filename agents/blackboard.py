# -*- coding: utf-8 -*-
"""
Growth Engine 2.0 - Blackboard Architecture
TRUE SWARM AGENTS - Shared working memory

The Blackboard is where agents:
- Publish intermediate findings
- Subscribe to updates from other agents
- Query shared knowledge
- Coordinate through shared state

This enables collective intelligence.
"""

import asyncio
import logging
import re
from typing import Dict, Any, List, Optional, Callable, Set, Pattern
from datetime import datetime
from dataclasses import dataclass, field
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class BlackboardEntry:
    """
    Single entry on the blackboard.
    
    Entries are organized by key (hierarchical namespace).
    Example keys:
    - "scout.competitors.high_threat"
    - "analyst.scores.trend"
    - "guardian.threats.critical"
    """
    
    key: str
    value: Any
    agent_id: str
    timestamp: datetime = field(default_factory=datetime.now)
    ttl: Optional[int] = None  # Time to live in seconds
    tags: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'key': self.key,
            'value': self.value,
            'agent_id': self.agent_id,
            'timestamp': self.timestamp.isoformat(),
            'ttl': self.ttl,
            'tags': list(self.tags),
            'metadata': self.metadata
        }
    
    def is_expired(self) -> bool:
        """Check if entry has expired"""
        if self.ttl is None:
            return False
        
        age = (datetime.now() - self.timestamp).total_seconds()
        return age > self.ttl


class Blackboard:
    """
    Shared working memory for agent swarm.
    
    Think of this as a bulletin board where agents can:
    - Pin notes (publish)
    - Read notes (query)
    - Get notified when new notes appear (subscribe)
    
    This enables agents to:
    1. See each other's thought process
    2. React to findings in real-time
    3. Build collective understanding
    """
    
    def __init__(self):
        # Storage: key -> BlackboardEntry
        self._data: Dict[str, BlackboardEntry] = {}
        
        # History: all entries ever posted
        self._history: List[BlackboardEntry] = []
        
        # Subscriptions: pattern -> [(agent_id, callback)]
        self._subscriptions: Dict[str, List[tuple[str, Callable]]] = defaultdict(list)
        
        # Compiled regex patterns for subscriptions
        self._subscription_patterns: Dict[str, Pattern] = {}
        
        # Statistics
        self._stats = {
            'total_writes': 0,
            'total_reads': 0,
            'total_notifications': 0,
            'by_agent': defaultdict(lambda: {'writes': 0, 'reads': 0}),
            'by_key_prefix': defaultdict(int)
        }
        
        logger.info("[Blackboard] 📋 Blackboard initialized")
    
    def publish(
        self,
        key: str,
        value: Any,
        agent_id: str,
        ttl: Optional[int] = None,
        tags: Optional[Set[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Publish data to blackboard.
        
        Args:
            key: Hierarchical key (e.g. "scout.competitors.new")
            value: Data to publish (any type)
            agent_id: Agent publishing
            ttl: Optional time-to-live in seconds
            tags: Optional tags for categorization
            metadata: Optional metadata
        
        Example:
            blackboard.publish(
                key="scout.competitors.high_threat",
                value={"url": "example.com", "score": 95},
                agent_id="scout",
                tags={"threat", "immediate"}
            )
        """
        entry = BlackboardEntry(
            key=key,
            value=value,
            agent_id=agent_id,
            ttl=ttl,
            tags=tags or set(),
            metadata=metadata or {}
        )
        
        # Store entry
        self._data[key] = entry
        self._history.append(entry)
        
        # Update stats
        self._stats['total_writes'] += 1
        self._stats['by_agent'][agent_id]['writes'] += 1
        
        key_prefix = key.split('.')[0] if '.' in key else key
        self._stats['by_key_prefix'][key_prefix] += 1
        
        logger.info(
            f"[Blackboard] 📌 {agent_id} published to '{key}': "
            f"{str(value)[:100]}"
        )
        
        # Notify subscribers
        self._notify_subscribers(entry)
    
    def get(
        self,
        key: str,
        agent_id: Optional[str] = None
    ) -> Optional[Any]:
        """
        Get value from blackboard.
        
        Args:
            key: Key to retrieve
            agent_id: Optional agent requesting (for stats)
            
        Returns:
            Value or None if not found
        """
        entry = self._data.get(key)
        
        if entry is None:
            return None
        
        # Check if expired
        if entry.is_expired():
            del self._data[key]
            return None
        
        # Update stats
        self._stats['total_reads'] += 1
        if agent_id:
            self._stats['by_agent'][agent_id]['reads'] += 1
        
        return entry.value
    
    def get_entry(self, key: str) -> Optional[BlackboardEntry]:
        """Get full entry (including metadata)"""
        entry = self._data.get(key)
        
        if entry and entry.is_expired():
            del self._data[key]
            return None
        
        return entry
    
    def query(
        self,
        pattern: str,
        agent_id: Optional[str] = None,
        tags: Optional[Set[str]] = None
    ) -> List[BlackboardEntry]:
        """
        Query blackboard with pattern matching.
        
        Args:
            pattern: Glob pattern (e.g. "scout.*", "*.high_threat")
            agent_id: Optional agent querying (for stats)
            tags: Optional filter by tags
            
        Returns:
            List of matching entries
        
        Example:
            # Get all scout findings
            entries = blackboard.query("scout.*")
            
            # Get all high threat items
            entries = blackboard.query("*.high_threat")
            
            # Get by tags
            entries = blackboard.query("*", tags={"critical"})
        """
        # Convert glob to regex
        regex_pattern = pattern.replace('.', r'\.').replace('*', '.*')
        regex = re.compile(f'^{regex_pattern}$')
        
        results = []
        
        for key, entry in self._data.items():
            # Check expiration
            if entry.is_expired():
                continue
            
            # Match pattern
            if not regex.match(key):
                continue
            
            # Match tags if specified
            if tags and not tags.issubset(entry.tags):
                continue
            
            results.append(entry)
        
        # Update stats
        if agent_id:
            self._stats['by_agent'][agent_id]['reads'] += len(results)
        
        logger.info(
            f"[Blackboard] 🔍 Query '{pattern}' returned {len(results)} entries"
        )
        
        return results
    
    def subscribe(
        self,
        pattern: str,
        agent_id: str,
        callback: Callable[[BlackboardEntry], None]
    ):
        """
        Subscribe to blackboard updates matching pattern.
        
        Callback will be called whenever a matching entry is published.
        
        Args:
            pattern: Glob pattern to match
            agent_id: Agent subscribing
            callback: Function to call on match
        
        Example:
            def on_threat_found(entry: BlackboardEntry):
                print(f"Threat found: {entry.value}")
            
            blackboard.subscribe(
                pattern="*.high_threat",
                agent_id="guardian",
                callback=on_threat_found
            )
        """
        # Store subscription
        self._subscriptions[pattern].append((agent_id, callback))
        
        # Compile regex pattern if not already done
        if pattern not in self._subscription_patterns:
            regex_pattern = pattern.replace('.', r'\.').replace('*', '.*')
            self._subscription_patterns[pattern] = re.compile(f'^{regex_pattern}$')
        
        logger.info(
            f"[Blackboard] 📬 {agent_id} subscribed to pattern '{pattern}'"
        )
    
    def unsubscribe(
        self,
        pattern: str,
        agent_id: str
    ):
        """Unsubscribe from pattern"""
        if pattern in self._subscriptions:
            self._subscriptions[pattern] = [
                (aid, cb) for aid, cb in self._subscriptions[pattern]
                if aid != agent_id
            ]
            
            # Clean up if no subscribers left
            if not self._subscriptions[pattern]:
                del self._subscriptions[pattern]
                if pattern in self._subscription_patterns:
                    del self._subscription_patterns[pattern]
    
    def _notify_subscribers(self, entry: BlackboardEntry):
        """Notify all subscribers matching the entry's key"""
        notifications = 0
        
        for pattern, subscribers in self._subscriptions.items():
            regex = self._subscription_patterns[pattern]
            
            if regex.match(entry.key):
                for agent_id, callback in subscribers:
                    try:
                        # Call callback (can be async)
                        if asyncio.iscoroutinefunction(callback):
                            # Schedule async callback
                            asyncio.create_task(callback(entry))
                        else:
                            callback(entry)
                        
                        notifications += 1
                        
                    except Exception as e:
                        logger.error(
                            f"[Blackboard] ❌ Callback error for {agent_id}: {e}",
                            exc_info=True
                        )
        
        if notifications > 0:
            self._stats['total_notifications'] += notifications
            logger.info(
                f"[Blackboard] 🔔 Notified {notifications} subscribers "
                f"for key '{entry.key}'"
            )
    
    def delete(self, key: str):
        """Delete entry from blackboard"""
        if key in self._data:
            del self._data[key]
            logger.info(f"[Blackboard] 🗑️ Deleted '{key}'")
    
    def clear(self, pattern: Optional[str] = None):
        """
        Clear blackboard entries.
        
        Args:
            pattern: Optional glob pattern (None = clear all)
        """
        if pattern is None:
            # Clear everything
            self._data.clear()
            logger.info("[Blackboard] 🗑️ Cleared all entries")
        else:
            # Clear matching pattern
            regex_pattern = pattern.replace('.', r'\.').replace('*', '.*')
            regex = re.compile(f'^{regex_pattern}$')
            
            keys_to_delete = [
                key for key in self._data.keys()
                if regex.match(key)
            ]
            
            for key in keys_to_delete:
                del self._data[key]
            
            logger.info(
                f"[Blackboard] 🗑️ Cleared {len(keys_to_delete)} entries "
                f"matching '{pattern}'"
            )
    
    def get_all_keys(self) -> List[str]:
        """Get all current keys"""
        return list(self._data.keys())
    
    def get_stats(self) -> Dict[str, Any]:
        """Get blackboard statistics"""
        return {
            'total_entries': len(self._data),
            'total_writes': self._stats['total_writes'],
            'total_reads': self._stats['total_reads'],
            'total_notifications': self._stats['total_notifications'],
            'by_agent': dict(self._stats['by_agent']),
            'by_key_prefix': dict(self._stats['by_key_prefix']),
            'active_subscriptions': sum(
                len(subs) for subs in self._subscriptions.values()
            ),
            'subscription_patterns': list(self._subscriptions.keys())
        }
    
    def get_history(
        self,
        agent_id: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100
    ) -> List[BlackboardEntry]:
        """
        Get blackboard history.
        
        Args:
            agent_id: Optional filter by agent
            since: Optional filter by timestamp
            limit: Maximum entries to return
        """
        history = self._history
        
        # Filter by agent
        if agent_id:
            history = [e for e in history if e.agent_id == agent_id]
        
        # Filter by time
        if since:
            history = [e for e in history if e.timestamp >= since]
        
        # Limit results
        return history[-limit:]
    
    def cleanup_expired(self):
        """Remove expired entries"""
        expired = [
            key for key, entry in self._data.items()
            if entry.is_expired()
        ]
        
        for key in expired:
            del self._data[key]
        
        if expired:
            logger.info(
                f"[Blackboard] 🧹 Cleaned up {len(expired)} expired entries"
            )


# Global blackboard instance
_blackboard: Optional[Blackboard] = None


def get_blackboard() -> Blackboard:
    """Get or create global blackboard"""
    global _blackboard
    if _blackboard is None:
        _blackboard = Blackboard()
    return _blackboard


def reset_blackboard():
    """Reset global blackboard (for testing)"""
    global _blackboard
    _blackboard = None
