"""Per-event-type Pydantic schemas, v1.

Each module owns one event type. Adding a new type is:
  1. New file here with the v1 schema.
  2. Register it in `app/events/registry.py:_REGISTRY`.
  3. Add `payload_summary` extractor in the registry.

The version is part of the schema class name (`WorkoutScheduledV1`),
not a field — bumping a version is a new file so the old shape stays
parseable for retroactive replay.
"""
