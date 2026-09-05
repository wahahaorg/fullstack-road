from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Protocol

from minio import Minio


class ObjectStore(Protocol):
    async def put(self, key: str, data: bytes) -> None: ...

    async def get(self, key: str) -> bytes: ...

    async def delete(self, key: str) -> None: ...


class FileObjectStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    async def put(self, key: str, data: bytes) -> None:
        path = self._root / key

        def write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

        await asyncio.to_thread(write)

    async def get(self, key: str) -> bytes:
        return await asyncio.to_thread((self._root / key).read_bytes)

    async def delete(self, key: str) -> None:
        path = self._root / key
        if path.exists():
            await asyncio.to_thread(path.unlink)


class MinioObjectStore:
    def __init__(
        self, endpoint: str, access_key: str, secret_key: str, bucket: str
    ) -> None:
        self._client = Minio(endpoint, access_key=access_key, secret_key=secret_key)
        self._bucket = bucket

    async def put(self, key: str, data: bytes) -> None:
        import io

        def write() -> None:
            if not self._client.bucket_exists(self._bucket):
                self._client.make_bucket(self._bucket)
            self._client.put_object(self._bucket, key, io.BytesIO(data), len(data))

        await asyncio.to_thread(write)

    async def get(self, key: str) -> bytes:
        def read() -> bytes:
            response = self._client.get_object(self._bucket, key)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()

        return await asyncio.to_thread(read)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._client.remove_object, self._bucket, key)
