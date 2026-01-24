# -*- coding: utf-8 -*-
"""
Unit tests for Blackboard shared memory system

Tests:
- Publish and get operations
- Subscription patterns
- Category queries
- TTL expiration
- Version tracking
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock
import time

from agents.blackboard import (
    Blackboard,
    BlackboardEntry,
    DataCategory,
    Subscription,
    get_blackboard,
    reset_blackboard
)


# =============================================================================
# PUBLISH AND GET TESTS
# =============================================================================

class TestPublishGet:
    """Tests for basic publish and get operations"""

    @pytest.mark.asyncio
    async def test_publish_basic(self, real_blackboard):
        """Test basic data publication"""
        bb = real_blackboard

        entry = await bb.publish(
            key="scout.industry",
            value="technology",
            agent_id="scout"
        )

        assert entry.key == "scout.industry"
        assert entry.value == "technology"
        assert entry.agent_id == "scout"
        assert entry.version == 1

    @pytest.mark.asyncio
    async def test_get_basic(self, real_blackboard):
        """Test basic data retrieval"""
        bb = real_blackboard

        await bb.publish(
            key="test.key",
            value={"data": "value"},
            agent_id="test"
        )

        value = bb.get("test.key")

        assert value == {"data": "value"}

    @pytest.mark.asyncio
    async def test_get_missing_key(self, real_blackboard):
        """Test getting non-existent key returns None"""
        bb = real_blackboard

        value = bb.get("nonexistent.key")

        assert value is None

    @pytest.mark.asyncio
    async def test_get_with_default(self, real_blackboard):
        """Test getting with default value"""
        bb = real_blackboard

        value = bb.get("nonexistent.key", default="default_value")

        assert value == "default_value"

    @pytest.mark.asyncio
    async def test_get_entry_full(self, real_blackboard):
        """Test getting full entry with metadata"""
        bb = real_blackboard

        await bb.publish(
            key="test.entry",
            value="data",
            agent_id="test",
            tags={"tag1", "tag2"},
            category=DataCategory.ANALYSIS
        )

        entry = bb.get_entry("test.entry")

        assert entry is not None
        assert entry.value == "data"
        assert entry.tags == {"tag1", "tag2"}
        assert entry.category == DataCategory.ANALYSIS

    @pytest.mark.asyncio
    async def test_publish_with_all_options(self, real_blackboard):
        """Test publish with all optional parameters"""
        bb = real_blackboard

        entry = await bb.publish(
            key="full.test",
            value={"complex": "data"},
            agent_id="test",
            ttl=3600,
            tags={"important", "test"},
            metadata={"source": "unit_test"},
            category=DataCategory.INSIGHT
        )

        assert entry.ttl == 3600
        assert entry.tags == {"important", "test"}
        assert entry.metadata == {"source": "unit_test"}
        assert entry.category == DataCategory.INSIGHT

    @pytest.mark.asyncio
    async def test_get_many(self, real_blackboard):
        """Test getting multiple keys at once"""
        bb = real_blackboard

        await bb.publish(key="key1", value="value1", agent_id="test")
        await bb.publish(key="key2", value="value2", agent_id="test")
        await bb.publish(key="key3", value="value3", agent_id="test")

        result = bb.get_many(["key1", "key2", "missing"])

        assert result == {"key1": "value1", "key2": "value2"}


# =============================================================================
# SUBSCRIPTION PATTERN TESTS
# =============================================================================

class TestSubscriptionPattern:
    """Tests for pattern-based subscriptions"""

    @pytest.mark.asyncio
    async def test_subscribe_exact_match(self, real_blackboard):
        """Test subscription with exact key match"""
        bb = real_blackboard
        notifications = []

        def callback(entry):
            notifications.append(entry)

        bb.subscribe(
            pattern="scout.industry",
            agent_id="analyst",
            callback=callback
        )

        await bb.publish(key="scout.industry", value="tech", agent_id="scout")

        assert len(notifications) == 1
        assert notifications[0].value == "tech"

    @pytest.mark.asyncio
    async def test_subscribe_wildcard_prefix(self, real_blackboard):
        """Test subscription with wildcard prefix pattern"""
        bb = real_blackboard
        notifications = []

        def callback(entry):
            notifications.append(entry)

        bb.subscribe(
            pattern="scout.*",
            agent_id="analyst",
            callback=callback
        )

        await bb.publish(key="scout.industry", value="tech", agent_id="scout")
        await bb.publish(key="scout.competitors", value=["a", "b"], agent_id="scout")
        await bb.publish(key="analyst.score", value=85, agent_id="analyst")

        assert len(notifications) == 2

    @pytest.mark.asyncio
    async def test_subscribe_wildcard_suffix(self, real_blackboard):
        """Test subscription with wildcard suffix pattern"""
        bb = real_blackboard
        notifications = []

        def callback(entry):
            notifications.append(entry)

        bb.subscribe(
            pattern="*.critical",
            agent_id="monitor",
            callback=callback
        )

        await bb.publish(key="scout.critical", value="alert1", agent_id="scout")
        await bb.publish(key="guardian.critical", value="alert2", agent_id="guardian")
        await bb.publish(key="scout.normal", value="nothing", agent_id="scout")

        assert len(notifications) == 2

    @pytest.mark.asyncio
    async def test_subscribe_no_self_notification(self, real_blackboard):
        """Test that publisher doesn't receive own notifications"""
        bb = real_blackboard
        notifications = []

        def callback(entry):
            notifications.append(entry)

        bb.subscribe(
            pattern="scout.*",
            agent_id="scout",  # Same as publisher
            callback=callback
        )

        await bb.publish(key="scout.data", value="test", agent_id="scout")

        assert len(notifications) == 0

    @pytest.mark.asyncio
    async def test_subscribe_async_callback(self, real_blackboard):
        """Test subscription with async callback"""
        bb = real_blackboard
        notifications = []

        async def async_callback(entry):
            await asyncio.sleep(0.01)
            notifications.append(entry)

        bb.subscribe(
            pattern="test.*",
            agent_id="receiver",
            callback=async_callback
        )

        await bb.publish(key="test.data", value="async", agent_id="sender")

        assert len(notifications) == 1

    @pytest.mark.asyncio
    async def test_subscribe_with_category_filter(self, real_blackboard):
        """Test subscription with category filter"""
        bb = real_blackboard
        notifications = []

        def callback(entry):
            notifications.append(entry)

        bb.subscribe(
            pattern="*.*",
            agent_id="receiver",
            callback=callback,
            categories={DataCategory.THREAT}
        )

        await bb.publish(
            key="guardian.alert",
            value="threat",
            agent_id="guardian",
            category=DataCategory.THREAT
        )
        await bb.publish(
            key="scout.data",
            value="finding",
            agent_id="scout",
            category=DataCategory.INSIGHT
        )

        assert len(notifications) == 1
        assert notifications[0].category == DataCategory.THREAT

    @pytest.mark.asyncio
    async def test_unsubscribe(self, real_blackboard):
        """Test unsubscribing from pattern"""
        bb = real_blackboard
        notifications = []

        def callback(entry):
            notifications.append(entry)

        bb.subscribe(pattern="test.*", agent_id="receiver", callback=callback)
        bb.unsubscribe(pattern="test.*", agent_id="receiver")

        await bb.publish(key="test.data", value="test", agent_id="sender")

        assert len(notifications) == 0

    @pytest.mark.asyncio
    async def test_unsubscribe_all(self, real_blackboard):
        """Test unsubscribing all patterns for agent"""
        bb = real_blackboard
        notifications = []

        def callback(entry):
            notifications.append(entry)

        bb.subscribe(pattern="test.*", agent_id="receiver", callback=callback)
        bb.subscribe(pattern="other.*", agent_id="receiver", callback=callback)
        bb.unsubscribe_all(agent_id="receiver")

        await bb.publish(key="test.data", value="test", agent_id="sender")
        await bb.publish(key="other.data", value="test", agent_id="sender")

        assert len(notifications) == 0


# =============================================================================
# CATEGORY QUERY TESTS
# =============================================================================

class TestCategoryQuery:
    """Tests for category-based queries"""

    @pytest.mark.asyncio
    async def test_query_by_pattern(self, real_blackboard):
        """Test querying by pattern"""
        bb = real_blackboard

        await bb.publish(key="scout.comp1", value="c1", agent_id="scout")
        await bb.publish(key="scout.comp2", value="c2", agent_id="scout")
        await bb.publish(key="analyst.score", value=85, agent_id="analyst")

        results = bb.query(pattern="scout.*")

        assert len(results) == 2
        assert all(e.key.startswith("scout.") for e in results)

    @pytest.mark.asyncio
    async def test_query_by_category(self, real_blackboard):
        """Test querying by category"""
        bb = real_blackboard

        await bb.publish(
            key="threat1",
            value="data",
            agent_id="guardian",
            category=DataCategory.THREAT
        )
        await bb.publish(
            key="threat2",
            value="data",
            agent_id="guardian",
            category=DataCategory.THREAT
        )
        await bb.publish(
            key="opportunity1",
            value="data",
            agent_id="prospector",
            category=DataCategory.OPPORTUNITY
        )

        results = bb.query_by_category(DataCategory.THREAT)

        assert len(results) == 2
        assert all(e.category == DataCategory.THREAT for e in results)

    @pytest.mark.asyncio
    async def test_query_with_limit(self, real_blackboard):
        """Test query with result limit"""
        bb = real_blackboard

        for i in range(10):
            await bb.publish(key=f"test.item{i}", value=i, agent_id="test")

        results = bb.query(pattern="test.*", limit=5)

        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_query_with_tags(self, real_blackboard):
        """Test query with tag filter"""
        bb = real_blackboard

        await bb.publish(
            key="tagged1",
            value="data",
            agent_id="test",
            tags={"important", "urgent"}
        )
        await bb.publish(
            key="tagged2",
            value="data",
            agent_id="test",
            tags={"important"}
        )
        await bb.publish(
            key="untagged",
            value="data",
            agent_id="test"
        )

        results = bb.query(pattern="*", tags={"important"})

        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_query_by_agent(self, real_blackboard):
        """Test querying entries by publishing agent"""
        bb = real_blackboard

        await bb.publish(key="scout.data1", value="d1", agent_id="scout")
        await bb.publish(key="scout.data2", value="d2", agent_id="scout")
        await bb.publish(key="analyst.data", value="d3", agent_id="analyst")

        results = bb.query_by_agent(from_agent="scout")

        assert len(results) == 2
        assert all(e.agent_id == "scout" for e in results)


# =============================================================================
# TTL EXPIRATION TESTS
# =============================================================================

class TestTTLExpiration:
    """Tests for TTL-based entry expiration"""

    @pytest.mark.asyncio
    async def test_entry_expires_after_ttl(self, real_blackboard):
        """Test that entry expires after TTL"""
        bb = real_blackboard

        await bb.publish(
            key="expiring",
            value="temporary",
            agent_id="test",
            ttl=1  # 1 second TTL
        )

        # Should exist immediately
        assert bb.get("expiring") == "temporary"

        # Wait for expiration
        time.sleep(1.1)

        # Should be expired now
        assert bb.get("expiring") is None

    @pytest.mark.asyncio
    async def test_entry_without_ttl_persists(self, real_blackboard):
        """Test that entry without TTL doesn't expire"""
        bb = real_blackboard

        await bb.publish(
            key="persistent",
            value="forever",
            agent_id="test"
            # No TTL
        )

        # Should exist
        assert bb.get("persistent") == "forever"

    @pytest.mark.asyncio
    async def test_is_expired_method(self, real_blackboard):
        """Test BlackboardEntry.is_expired() method"""
        entry = BlackboardEntry(
            key="test",
            value="data",
            agent_id="test",
            ttl=1
        )

        assert entry.is_expired() is False

        time.sleep(1.1)

        assert entry.is_expired() is True

    @pytest.mark.asyncio
    async def test_cleanup_expired(self, real_blackboard):
        """Test cleanup of expired entries"""
        bb = real_blackboard

        await bb.publish(key="exp1", value="v1", agent_id="test", ttl=1)
        await bb.publish(key="exp2", value="v2", agent_id="test", ttl=1)
        await bb.publish(key="persist", value="v3", agent_id="test")

        time.sleep(1.1)

        count = bb.cleanup_expired()

        assert count == 2
        assert bb.get("exp1") is None
        assert bb.get("exp2") is None
        assert bb.get("persist") == "v3"

    @pytest.mark.asyncio
    async def test_expired_entries_excluded_from_query(self, real_blackboard):
        """Test that expired entries are excluded from queries"""
        bb = real_blackboard

        await bb.publish(key="test.expired", value="old", agent_id="test", ttl=1)
        await bb.publish(key="test.valid", value="new", agent_id="test")

        time.sleep(1.1)

        results = bb.query(pattern="test.*")

        assert len(results) == 1
        assert results[0].key == "test.valid"


# =============================================================================
# VERSION TRACKING TESTS
# =============================================================================

class TestVersionTracking:
    """Tests for entry version tracking"""

    @pytest.mark.asyncio
    async def test_initial_version_is_one(self, real_blackboard):
        """Test that initial version is 1"""
        bb = real_blackboard

        entry = await bb.publish(key="test", value="v1", agent_id="test")

        assert entry.version == 1

    @pytest.mark.asyncio
    async def test_version_increments_on_update(self, real_blackboard):
        """Test that version increments on update"""
        bb = real_blackboard

        entry1 = await bb.publish(key="test", value="v1", agent_id="test")
        entry2 = await bb.publish(key="test", value="v2", agent_id="test")

        assert entry1.version == 1
        assert entry2.version == 2

    @pytest.mark.asyncio
    async def test_version_tracks_history(self, real_blackboard):
        """Test that version history is maintained"""
        bb = real_blackboard

        await bb.publish(key="test", value="original", agent_id="test")
        entry = await bb.publish(key="test", value="updated", agent_id="test")

        assert entry.previous_value == "original"
        assert entry.value == "updated"

    @pytest.mark.asyncio
    async def test_no_update_if_value_unchanged(self, real_blackboard):
        """Test that unchanged values don't create new versions"""
        bb = real_blackboard

        entry1 = await bb.publish(key="test", value="same", agent_id="test")
        entry2 = await bb.publish(key="test", value="same", agent_id="test")

        # Should return same entry
        assert entry1.version == 1
        assert entry2.version == 1

    @pytest.mark.asyncio
    async def test_has_changed_method(self, real_blackboard):
        """Test BlackboardEntry.has_changed() method"""
        entry = BlackboardEntry(
            key="test",
            value={"a": 1, "b": 2},
            agent_id="test"
        )

        assert entry.has_changed({"a": 1, "b": 2}) is False
        assert entry.has_changed({"a": 1, "b": 3}) is True
        assert entry.has_changed({"a": 1}) is True


# =============================================================================
# STATISTICS AND HISTORY TESTS
# =============================================================================

class TestStatisticsHistory:
    """Tests for statistics and history tracking"""

    @pytest.mark.asyncio
    async def test_stats_structure(self, real_blackboard):
        """Test stats have correct structure"""
        bb = real_blackboard

        stats = bb.get_stats()

        assert 'total_entries' in stats
        assert 'total_writes' in stats
        assert 'total_reads' in stats
        assert 'total_notifications' in stats
        assert 'total_subscriptions' in stats
        assert 'by_agent' in stats
        assert 'by_category' in stats

    @pytest.mark.asyncio
    async def test_stats_track_writes(self, real_blackboard):
        """Test that stats track writes"""
        bb = real_blackboard

        await bb.publish(key="test1", value="v1", agent_id="test")
        await bb.publish(key="test2", value="v2", agent_id="test")

        stats = bb.get_stats()

        assert stats['total_writes'] == 2

    @pytest.mark.asyncio
    async def test_stats_track_reads(self, real_blackboard):
        """Test that stats track reads"""
        bb = real_blackboard

        await bb.publish(key="test", value="v", agent_id="test")
        bb.get("test", agent_id="reader")
        bb.get("test", agent_id="reader")

        stats = bb.get_stats()

        assert stats['by_agent']['reader']['reads'] == 2

    @pytest.mark.asyncio
    async def test_get_history(self, real_blackboard):
        """Test getting publication history"""
        bb = real_blackboard

        await bb.publish(key="test1", value="v1", agent_id="scout")
        await bb.publish(key="test2", value="v2", agent_id="scout")
        await bb.publish(key="test3", value="v3", agent_id="analyst")

        history = bb.get_history()
        scout_history = bb.get_history(agent_id="scout")

        assert len(history) == 3
        assert len(scout_history) == 2

    @pytest.mark.asyncio
    async def test_get_snapshot(self, real_blackboard):
        """Test getting complete snapshot"""
        bb = real_blackboard

        await bb.publish(key="key1", value="v1", agent_id="test")
        await bb.publish(key="key2", value="v2", agent_id="test")

        snapshot = bb.get_snapshot()

        assert "key1" in snapshot
        assert "key2" in snapshot
        assert snapshot["key1"]["value"] == "v1"


# =============================================================================
# RESET AND CLEAR TESTS
# =============================================================================

class TestResetClear:
    """Tests for reset and clear operations"""

    @pytest.mark.asyncio
    async def test_clear_all(self, real_blackboard):
        """Test clearing all entries"""
        bb = real_blackboard

        await bb.publish(key="key1", value="v1", agent_id="test")
        await bb.publish(key="key2", value="v2", agent_id="test")

        bb.clear()

        assert len(bb.get_all_keys()) == 0

    @pytest.mark.asyncio
    async def test_clear_by_pattern(self, real_blackboard):
        """Test clearing entries by pattern"""
        bb = real_blackboard

        await bb.publish(key="scout.data1", value="v1", agent_id="scout")
        await bb.publish(key="scout.data2", value="v2", agent_id="scout")
        await bb.publish(key="analyst.score", value="v3", agent_id="analyst")

        bb.clear(pattern="scout.*")

        keys = bb.get_all_keys()
        assert "analyst.score" in keys
        assert "scout.data1" not in keys

    @pytest.mark.asyncio
    async def test_delete_single(self, real_blackboard):
        """Test deleting single entry"""
        bb = real_blackboard

        await bb.publish(key="to_delete", value="v", agent_id="test")
        await bb.publish(key="to_keep", value="v", agent_id="test")

        bb.delete("to_delete")

        assert bb.get("to_delete") is None
        assert bb.get("to_keep") == "v"

    @pytest.mark.asyncio
    async def test_reset_clears_everything(self, real_blackboard):
        """Test that reset clears all state"""
        bb = real_blackboard

        await bb.publish(key="test", value="v", agent_id="test")
        bb.subscribe(pattern="*", agent_id="sub", callback=lambda x: None)

        bb.reset()

        assert len(bb._data) == 0
        assert len(bb._subscriptions) == 0
        assert len(bb._history) == 0
        assert bb._stats['total_writes'] == 0
