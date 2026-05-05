"""
zilliz_client.py — Minimal dual-cluster Zilliz client for Nexus OS

Clusters:
  - Serverless: EVENT, FAILURE_PATTERN tracks
  - Town:       TRUST, GOVERNANCE, CAPABILITY tracks

Thread-safe. Graceful degradation when pymilvus is missing or env vars unset.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

# ── Graceful pymilvus import ─────────────────────────────────────────────────
try:
    from pymilvus import (
        Collection,
        CollectionSchema,
        DataType,
        FieldSchema,
        connections,
        utility,
    )

    HAS_MILVUS = True
except ImportError:
    HAS_MILVUS = False

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


# ── Constants ────────────────────────────────────────────────────────────────
class TrackType(str, Enum):
    EVENT = "EVENT"
    FAILURE_PATTERN = "FAILURE_PATTERN"
    TRUST = "TRUST"
    GOVERNANCE = "GOVERNANCE"
    CAPABILITY = "CAPABILITY"


SERVERLESS_TRACKS = {TrackType.EVENT, TrackType.FAILURE_PATTERN}
TOWN_TRACKS = {TrackType.TRUST, TrackType.GOVERNANCE, TrackType.CAPABILITY}

EMBEDDING_DIM = 768  # default; override via env
DIMENSION = int(os.environ.get("ZILLIZ_EMBEDDING_DIM", EMBEDDING_DIM))


# ── Data classes ─────────────────────────────────────────────────────────────
@dataclass
class EmbeddingRecord:
    agent_id: str
    lane: str
    track_type: TrackType
    key: str
    value: str
    embedding: List[float]
    timestamp: float = field(default_factory=time.time)


@dataclass
class SearchResult:
    key: str
    value: str
    agent_id: str
    lane: str
    track_type: str
    score: float


@dataclass
class ClusterStatus:
    name: str
    connected: bool
    uri: str
    error: Optional[str] = None


# ── Main client ──────────────────────────────────────────────────────────────
class ZillizClient:
    """Dual-cluster Zilliz/Milvus client with thread-safe operations."""

    _lock = threading.Lock()
    _connected: Dict[str, bool] = {}

    def __init__(self) -> None:
        self._available = False
        self._serverless_uri = os.environ.get("ZILLIZ_SERVERLESS_URI", "")
        self._serverless_token = os.environ.get("ZILLIZ_SERVERLESS_TOKEN", "")
        self._town_uri = os.environ.get("ZILLIZ_TOWN_URI", "")
        self._town_token = os.environ.get("ZILLIZ_TOWN_TOKEN", "")
        self._collections: Dict[str, Any] = {}

        if not HAS_MILVUS:
            self._init_error = "pymilvus not installed"
            return

        missing = []
        if not self._serverless_uri:
            missing.append("ZILLIZ_SERVERLESS_URI")
        if not self._serverless_token:
            missing.append("ZILLIZ_SERVERLESS_TOKEN")
        if not self._town_uri:
            missing.append("ZILLIZ_TOWN_URI")
        if not self._town_token:
            missing.append("ZILLIZ_TOWN_TOKEN")

        if missing:
            self._init_error = f"Missing env vars: {', '.join(missing)}"
            return

        self._init_error = None
        self._available = True

    # ── Connection management ────────────────────────────────────────────
    def _ensure_connected(self, cluster: str) -> bool:
        """Connect to a cluster if not already connected. Thread-safe."""
        if cluster in self._connected and self._connected[cluster]:
            return True

        with self._lock:
            if cluster in self._connected and self._connected[cluster]:
                return True

            try:
                if cluster == "serverless":
                    uri, token = self._serverless_uri, self._serverless_token
                else:
                    uri, token = self._town_uri, self._town_token

                connections.connect(alias=cluster, uri=uri, token=token)
                self._connected[cluster] = True
                return True
            except Exception as exc:
                self._connected[cluster] = False
                print(f"[zilliz] Failed to connect to {cluster}: {exc}", file=sys.stderr)
                return False

    def _get_collection(self, track_type: TrackType) -> Optional[Collection]:
        """Get or create collection for a track type."""
        name = track_type.value.lower()
        if name in self._collections:
            return self._collections[name]

        cluster = "serverless" if track_type in SERVERLESS_TRACKS else "town"
        if not self._ensure_connected(cluster):
            return None

        with self._lock:
            if name in self._collections:
                return self._collections[name]

            if utility.has_collection(name, using=cluster):
                col = Collection(name, using=cluster)
            else:
                col = self._create_collection(name, cluster)
                if col is None:
                    return None

            col.load()
            self._collections[name] = col
            return col

    def _create_collection(self, name: str, cluster: str) -> Optional[Collection]:
        """Create a collection with the standard schema."""
        try:
            fields = [
                FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
                FieldSchema(name="agent_id", dtype=DataType.VARCHAR, max_length=128),
                FieldSchema(name="lane", dtype=DataType.VARCHAR, max_length=128),
                FieldSchema(name="track_type", dtype=DataType.VARCHAR, max_length=64),
                FieldSchema(name="key", dtype=DataType.VARCHAR, max_length=256),
                FieldSchema(name="value", dtype=DataType.VARCHAR, max_length=4096),
                FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=DIMENSION),
                FieldSchema(name="timestamp", dtype=DataType.DOUBLE),
            ]
            schema = CollectionSchema(fields, description=f"Nexus track: {name}")
            col = Collection(name, schema, using=cluster)
            index_params = {
                "metric_type": "COSINE",
                "index_type": "AUTOINDEX",
                "params": {},
            }
            col.create_index("embedding", index_params)
            return col
        except Exception as exc:
            print(f"[zilliz] Failed to create collection {name}: {exc}", file=sys.stderr)
            return None

    # ── Public API ───────────────────────────────────────────────────────
    def store_embedding(
        self,
        agent_id: str,
        lane: str,
        track_type: TrackType,
        key: str,
        value: str,
        embedding: List[float],
    ) -> bool:
        """Store an embedding. Returns True on success."""
        if not self._available:
            return False

        col = self._get_collection(track_type)
        if col is None:
            return False

        try:
            with self._lock:
                col.insert(
                    [
                        [agent_id],
                        [lane],
                        [track_type.value],
                        [key],
                        [value],
                        [embedding],
                        [time.time()],
                    ]
                )
            return True
        except Exception as exc:
            print(f"[zilliz] store_embedding failed: {exc}", file=sys.stderr)
            return False

    def similar_search(
        self,
        query_embedding: List[float],
        track_type: TrackType,
        top_k: int = 10,
    ) -> List[SearchResult]:
        """Search for similar embeddings. Returns list of SearchResult."""
        if not self._available:
            return []

        col = self._get_collection(track_type)
        if col is None:
            return []

        try:
            with self._lock:
                results = col.search(
                    data=[query_embedding],
                    anns_field="embedding",
                    param={"metric_type": "COSINE", "params": {}},
                    limit=top_k,
                    output_fields=["key", "value", "agent_id", "lane", "track_type"],
                )

            out: List[SearchResult] = []
            for hits in results:
                for hit in hits:
                    out.append(
                        SearchResult(
                            key=hit.entity.get("key", ""),
                            value=hit.entity.get("value", ""),
                            agent_id=hit.entity.get("agent_id", ""),
                            lane=hit.entity.get("lane", ""),
                            track_type=hit.entity.get("track_type", ""),
                            score=hit.score,
                        )
                    )
            return out
        except Exception as exc:
            print(f"[zilliz] similar_search failed: {exc}", file=sys.stderr)
            return []

    def health_check(self) -> Dict[str, Any]:
        """Return health status of both clusters."""
        status: Dict[str, Any] = {
            "pymilvus_installed": HAS_MILVUS,
            "available": self._available,
            "init_error": self._init_error,
            "clusters": {},
        }

        if not self._available:
            return status

        for cluster_name, uri in [
            ("serverless", self._serverless_uri),
            ("town", self._town_uri),
        ]:
            try:
                ok = self._ensure_connected(cluster_name)
                status["clusters"][cluster_name] = ClusterStatus(
                    name=cluster_name,
                    connected=ok,
                    uri=uri[:40] + "..." if len(uri) > 40 else uri,
                ).__dict__
            except Exception as exc:
                status["clusters"][cluster_name] = ClusterStatus(
                    name=cluster_name,
                    connected=False,
                    uri=uri[:40] + "..." if len(uri) > 40 else uri,
                    error=str(exc),
                ).__dict__

        return status


# ── CLI entry point ──────────────────────────────────────────────────────────
def main() -> None:
    client = ZillizClient()
    result = client.health_check()

    print("═══ Zilliz Client Health Check ═══")
    print(f"  pymilvus installed : {result['pymilvus_installed']}")
    print(f"  client available   : {result['available']}")
    if result.get("init_error"):
        print(f"  init error         : {result['init_error']}")

    for name, info in result.get("clusters", {}).items():
        print(f"  cluster [{name}]  : {'connected' if info['connected'] else 'disconnected'}")
        if info.get("error"):
            print(f"    error: {info['error']}")

    if result["available"]:
        print("\n✓ All systems operational")
    else:
        print(f"\n✗ Client not ready — {result.get('init_error', 'unknown reason')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
