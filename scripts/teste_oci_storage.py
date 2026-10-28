
import hashlib
from uuid import uuid4

from mediflow.storage.oci_storage import OCIStorage


def main():
    storage = OCIStorage.from_environment()

    documento = (
        b"MediFlow - teste sintetico de Object Storage\n"
        b"Documento ficticio, sem dados pessoais.\n"
    )

    object_name = f"testes/{uuid4().hex}.txt"

    hash_original = storage.upload_bytes(
        object_name,
        documento,
        content_type="text/plain",
    )

    recuperado = storage.download_bytes(object_name)

    hash_recuperado = hashlib.sha256(recuperado).hexdigest()

    if hash_original != hash_recuperado:
        raise RuntimeError("Falha na verificacao de integridade")

    print("UPLOAD: OK")
    print("DOWNLOAD: OK")
    print("INTEGRIDADE SHA-256: OK")
    print(f"BUCKET: {storage.bucket}")
    print(f"OBJETO: {object_name}")
    print(f"SHA-256: {hash_original}")


if __name__ == "__main__":
    main()
