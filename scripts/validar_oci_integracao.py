
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from oci.exceptions import ServiceError
from mediflow.storage.oci_storage import OCIStorage


def main():
    storage = OCIStorage.from_environment()
    pasta = Path("amostras")

    formatos = {
        ".pdf": "application/pdf",
        ".png": "image/png",
    }

    for extensao, mime in formatos.items():
        arquivo = next(
            (
                p for p in pasta.rglob("*")
                if p.is_file()
                and p.suffix.lower() == extensao
            ),
            None,
        )

        if arquivo is None:
            print(f"{extensao}: SEM AMOSTRA - teste pendente")
            continue

        original = arquivo.read_bytes()
        nome = f"testes/validacao/{uuid4().hex}{extensao}"

        hash_envio = storage.upload_bytes(
            nome,
            original,
            content_type=mime,
        )

        recuperado = storage.download_bytes(nome)

        metadados = storage.client.head_object(
            storage.namespace,
            storage.bucket,
            nome,
        )

        assert original == recuperado
        assert hash_envio == sha256(recuperado).hexdigest()
        assert len(original) == int(
            metadados.headers["content-length"]
        )

        print(f"{extensao}: UPLOAD OK")
        print(f"{extensao}: DOWNLOAD OK")
        print(f"{extensao}: INTEGRIDADE OK")

    # Documento inexistente deve produzir um erro,
    # nunca retornar conteúdo fictício.
    inexistente = f"testes/inexistente-{uuid4().hex}.txt"

    try:
        storage.download_bytes(inexistente)
    except ServiceError as erro:
        if erro.status != 404:
            raise
        print("OBJETO INEXISTENTE: ERRO 404 CORRETO")
    else:
        raise AssertionError(
            "Documento inexistente foi tratado como existente"
        )

    print("VALIDACAO CONCLUIDA")


if __name__ == "__main__":
    main()
