
from types import SimpleNamespace

from mediflow.storage.oci_storage import OCIStorage


class FakeOCIClient:
    def __init__(self):
        self.objects = {}

    def put_object(
        self, namespace, bucket, name, content, **kwargs
    ):
        self.objects[(namespace, bucket, name)] = content

    def get_object(self, namespace, bucket, name):
        content = self.objects[(namespace, bucket, name)]
        return SimpleNamespace(
            data=SimpleNamespace(content=content)
        )


def test_upload_e_download():
    client = FakeOCIClient()
    storage = OCIStorage(
        client,
        namespace="namespace-teste",
        bucket="bucket-teste",
    )

    original = b"documento sintetico"

    hash_original = storage.upload_bytes(
        "testes/exemplo.txt",
        original,
    )

    recuperado = storage.download_bytes(
        "testes/exemplo.txt"
    )

    assert recuperado == original
    assert len(hash_original) == 64
