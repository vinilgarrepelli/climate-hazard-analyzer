"""NoSQL document cache: MongoDB in production, TinyDB for local development."""
import asyncio
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from pymongo import MongoClient, ReturnDocument
from tinydb import Query, TinyDB


class StorageError(RuntimeError):
    pass


class DocumentStore:
    def __init__(self):
        uri = os.getenv("MONGODB_URI", "")
        self.mode = "mongodb" if uri else "tinydb-local"
        self._lock = threading.RLock()
        self._initialized = False
        self._db = None
        if uri:
            self._client = MongoClient(uri, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000, maxPoolSize=10)
            self._db = self._client[os.getenv("MONGODB_DATABASE", "climate_lens")]
        elif os.getenv("VERCEL"):
            raise StorageError("Configure MONGODB_URI in Vercel to enable the production database. Local files are not a persistent cloud database.")
        else:
            path = Path(os.getenv("LOCAL_DB_PATH", ".data/climate.json"))
            path.parent.mkdir(parents=True, exist_ok=True)
            self._db = TinyDB(path)

    def _indexes(self):
        if self.mode == "mongodb" and not self._initialized:
            self._db.documents.create_index("expires_at", expireAfterSeconds=0)
            self._db.rate_limits.create_index("expires_at", expireAfterSeconds=0)
            self._initialized = True

    def _get(self, key):
        with self._lock:
            self._indexes()
            if self.mode == "mongodb":
                document = self._db.documents.find_one({"_id": key})
            else:
                document = self._db.get(Query().key == key)
            return document["data"] if document and document["expires_epoch"] > time.time() else None

    async def get(self, key):
        try:
            return await asyncio.to_thread(self._get, key)
        except Exception as exc:
            raise StorageError("The document database is unavailable. Check connectivity and the database account permissions.") from exc

    def _put(self, key, data, ttl):
        now = time.time()
        with self._lock:
            self._indexes()
            document = {"key": key, "data": data, "expires_epoch": now + ttl, "created_epoch": now}
            if self.mode == "mongodb":
                document["expires_at"] = datetime.fromtimestamp(now + ttl, timezone.utc)
                self._db.documents.replace_one({"_id": key}, document, upsert=True)
            else:
                self._db.upsert(document, Query().key == key)

    async def put(self, key, data, ttl):
        try:
            await asyncio.to_thread(self._put, key, data, ttl)
        except Exception as exc:
            raise StorageError("Could not persist the weather analysis to the document database.") from exc

    async def allow_request(self, identity: str, limit: int) -> bool:
        """Mongo's atomic increment gives a distributed fixed-minute rate limit."""
        if self.mode != "mongodb":
            return True  # The API supplies an in-process local limiter.

        def increment():
            self._indexes()
            bucket = int(time.time()) // 60
            document = self._db.rate_limits.find_one_and_update(
                {"_id": f"{identity}:{bucket}"},
                {"$inc": {"count": 1}, "$setOnInsert": {"expires_at": datetime.fromtimestamp((bucket + 2) * 60, timezone.utc)}},
                upsert=True, return_document=ReturnDocument.AFTER,
            )
            return document["count"] <= limit

        try:
            return await asyncio.to_thread(increment)
        except Exception as exc:
            raise StorageError("The database rate limiter is unavailable; retry later.") from exc


_store = None


def get_store() -> DocumentStore:
    global _store
    if _store is None:
        _store = DocumentStore()
    return _store
