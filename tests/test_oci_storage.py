
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


def test_listar_chaves_usa_prefixo_e_token_de_paginacao():
    from types import SimpleNamespace

    class ClienteListagem:
        def __init__(self):
            self.chamadas = []

        def list_objects(self, namespace, bucket, **kwargs):
            self.chamadas.append((namespace, bucket, kwargs))
            return SimpleNamespace(data=SimpleNamespace(
                objects=[SimpleNamespace(name="metadados/DOC-001/" + "a" * 32 + ".json")],
                next_start_with="metadados/DOC-001/" + "b" * 32 + ".json",
            ))

    client = ClienteListagem()
    storage = OCIStorage(client, "ns", "bucket")
    nomes, seguinte = storage.listar_chaves("metadados/DOC-001/", limite=1)
    assert nomes == ["metadados/DOC-001/" + "a" * 32 + ".json"]
    assert seguinte == "metadados/DOC-001/" + "b" * 32 + ".json"
    nomes2, _ = storage.listar_chaves("metadados/DOC-001/", inicio=seguinte, limite=1)
    assert nomes2 == nomes
    assert client.chamadas == [
        ("ns", "bucket", {"prefix": "metadados/DOC-001/", "limit": 1}),
        ("ns", "bucket", {"prefix": "metadados/DOC-001/", "limit": 1, "start": seguinte}),
    ]
