"""NoSQL documents: MongoDB, local TinyDB, or an explicit versioned TinyDB seed."""
import asyncio
import gzip
import json
import os
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

from pymongo import MongoClient, ReturnDocument
from tinydb import Query, TinyDB
from tinydb.storages import MemoryStorage


class StorageError(RuntimeError):
    pass


class DocumentStore:
    def __init__(self):
        uri = os.getenv("MONGODB_URI", "")
        self.mode = "mongodb" if uri else "tinydb-local"
        self._lock = threading.RLock()
        self._initialized = False
        self._db = None
        self._runtime_keys = OrderedDict()
        self._seed_keys = set()
        if uri:
            self._client = MongoClient(uri, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000, maxPoolSize=10)
            self._db = self._client[os.getenv("MONGODB_DATABASE", "climate_lens")]
        elif os.getenv("STORAGE_BACKEND") == "tinydb-seeded":
            # Historical documents persist in a versioned TinyDB database asset.
            # Runtime query-cache writes are bounded and local to a warm worker.
            self.mode = "tinydb-seeded"
            seed = Path(os.getenv("SEED_DB_PATH", str(Path(__file__).parent / "data/climate_seed.json.gz")))
            if not seed.exists():
                raise StorageError("The versioned TinyDB dataset is missing. Run scripts/build_seed.py before deploying.")
            with gzip.open(seed, "rt", encoding="utf-8") as stream:
                data = json.load(stream)
            self._db = TinyDB(storage=MemoryStorage)
            self._db.storage.write(data)
            self._seed_keys = {doc["key"] for doc in self._db.all()}
        elif os.getenv("VERCEL"):
            raise StorageError("Configure MONGODB_URI or explicitly set STORAGE_BACKEND=tinydb-seeded in Vercel. Temporary local files are not persistent cloud storage.")
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
                if self.mode == "tinydb-seeded" and key not in self._seed_keys:
                    self._runtime_keys.pop(key, None)
                    self._runtime_keys[key] = True
                    while len(self._runtime_keys) > 32:
                        oldest, _ = self._runtime_keys.popitem(last=False)
                        self._db.remove(Query().key == oldest)

    async def put(self, key, data, ttl):
        try:
            await asyncio.to_thread(self._put, key, data, ttl)
        except Exception as exc:
            raise StorageError("Could not persist the weather analysis to the document database.") from exc

    async def find_weather(self, latitude, longitude, start_date, end_date):
        """Reuse a larger saved weather interval for a narrower year selection."""
        def find():
            with self._lock:
                if self.mode == "mongodb":
                    document = self._db.documents.find_one({
                        "data.request_latitude": latitude,
                        "data.request_longitude": longitude,
                        "data.source.model": "ERA5",
                        "data.source.retrieved_start": {"$lte": start_date},
                        "data.source.retrieved_end": {"$gte": end_date},
                        "expires_epoch": {"$gt": time.time()},
                    })
                    return document["data"] if document else None
                for document in self._db.all():
                    data = document.get("data", {})
                    source = data.get("source", {})
                    if (data.get("request_latitude") == latitude and data.get("request_longitude") == longitude
                            and source.get("model") == "ERA5" and "records" in data
                            and source.get("retrieved_start", "9999") <= start_date
                            and source.get("retrieved_end", "0000") >= end_date
                            and document["expires_epoch"] > time.time()):
                        return data
                return None
        try:
            return await asyncio.to_thread(find)
        except Exception as exc:
            raise StorageError("Could not read the saved weather interval.") from exc

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
