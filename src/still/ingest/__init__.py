"""INGEST stage (spec §7): per-source adapters fetching raw entries.

Each adapter takes its Source config and returns normalized Items.
One adapter per ingestion method (spec §5.1).
"""
