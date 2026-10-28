"""Recebimento de documentos sintéticos e registro de metadados. Não executa triagem."""

import hashlib
import os
import re
import warnings
import uuid
from datetime import datetime, timezone
from io import BytesIO
from pathlib import PurePath
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, Path, Query
from pydantic import Field, ValidationError
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from PIL import Image, UnidentifiedImageError

from mediflow.storage.oci_storage import OCIStorage
from mediflow_contracts.models import EntradaProcessada, Estrito

router = APIRouter(prefix="/v1/triagens", tags=["ingestao"])

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 10
READ_CHUNK_BYTES = 1024 * 1024
FILE_TYPES = {
    ".pdf": ("pdf", "application/pdf", b"%PDF-"),
    ".png": ("png", "image/png", b"\x89PNG\r\n\x1a\n"),
    ".jpg": ("jpeg", "image/jpeg", b"\xff\xd8\xff"),
    ".jpeg": ("jpeg", "image/jpeg", b"\xff\xd8\xff"),
}


class OriginalArmazenado(Estrito):
    """Prova apenas o armazenamento do original, não dos resultados/histórico."""

    status: Literal["confirmado"] = "confirmado"
    bucket: str
    chave_original: str


class RegistroMetadados(Estrito):
    """Confirma somente o manifesto do upload; não o histórico de triagem."""

    status: Literal["confirmado"] = "confirmado"
    chave_metadados: str


class ReciboArquivo(Estrito):
    contrato_versao: Literal["0.1"] = "0.1"
    documento_id: str
    arquivo_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    registrado_em_utc: str
    status: Literal["recebido"] = "recebido"
    entrada: EntradaProcessada
    armazenamento_original: OriginalArmazenado
    registro_metadados: RegistroMetadados
    triagem_executada: Literal[False] = False
    tamanho_bytes: int = Field(ge=1, le=MAX_FILE_BYTES)



class ResumoArquivo(Estrito):
    arquivo_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    nome_original: str
    tipo_entrada: Literal["pdf", "png", "jpeg"]
    tamanho_bytes: int = Field(ge=1, le=MAX_FILE_BYTES)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    registrado_em_utc: str


class PaginaArquivos(Estrito):
    documento_id: str
    quantidade_pagina: int = Field(ge=0, le=50)
    arquivos: list[ResumoArquivo]
    proximo_cursor: str | None = None

def armazenamento() -> OCIStorage:
    """Dependência substituível por um fake nos testes, sem credenciais."""
    try:
        return OCIStorage.from_environment()
    except Exception as exc:
        # Não divulgar paths de chaves, OCIDs e conteúdo das exceções OCI.
        raise HTTPException(
            status_code=503,
            detail={"codigo": "ARMAZENAMENTO_INDISPONIVEL", "mensagem": "Armazenamento não configurado ou indisponível."},
        ) from exc


def somente_desenvolvimento_local(request: Request) -> None:
    """Portão temporário: endpoint sem autenticação proibido por padrão."""
    habilitado = os.getenv("MEDIFLOW_ENABLE_LOCAL_UPLOADS", "false").lower() == "true"
    ambiente = os.getenv("MEDIFLOW_ENV", "development").lower()
    origem = request.client.host if request.client else ""
    if not habilitado or ambiente != "development" or origem not in {"127.0.0.1", "::1", "testclient"}:
        raise HTTPException(
            status_code=403,
            detail={"codigo": "UPLOAD_DESABILITADO", "mensagem": "Upload disponível somente para testes locais autorizados."},
        )


def verificar_documento(nome: str | None, mime: str | None, dados: bytes) -> tuple[str, str, str]:
    if not nome:
        raise HTTPException(400, detail={"codigo": "NOME_AUSENTE", "mensagem": "Informe o nome do arquivo."})
    # Nome é apenas metadado, nunca é usado para gerar paths em disco/OCI.
    nome_seguro = PurePath(nome.replace("\\", "/")).name
    if not nome_seguro or nome_seguro in {".", ".."} or len(nome_seguro) > 255 or any(ord(c) < 32 for c in nome_seguro):
        raise HTTPException(400, detail={"codigo": "NOME_INVALIDO", "mensagem": "Nome de arquivo inválido."})

    extensao = os.path.splitext(nome_seguro)[1].lower()
    tipo = FILE_TYPES.get(extensao)
    if not tipo:
        raise HTTPException(415, detail={"codigo": "FORMATO_NAO_SUPORTADO", "mensagem": "Somente PDF, PNG e JPEG."})
    tipo_entrada, mime_esperado, assinatura = tipo
    if mime != mime_esperado or not dados.startswith(assinatura):
        raise HTTPException(415, detail={"codigo": "ARQUIVO_INCOMPATIVEL", "mensagem": "Tipo MIME e assinatura do arquivo não conferem."})

    if extensao == ".pdf":
        try:
            reader = PdfReader(BytesIO(dados), strict=False)
            paginas = len(reader.pages)
        except (PdfReadError, ValueError, KeyError, OSError, TypeError) as exc:
            raise HTTPException(422, detail={"codigo": "PDF_INVALIDO", "mensagem": "Estrutura PDF não pôde ser lida."}) from exc
        if paginas == 0:
            raise HTTPException(422, detail={"codigo": "PDF_VAZIO", "mensagem": "PDF não contém páginas."})
        if paginas > MAX_PDF_PAGES:
            raise HTTPException(413, detail={"codigo": "PAGINAS_EXCEDIDAS", "mensagem": "PDF excede o limite inicial de 10 páginas."})
    else:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(BytesIO(dados)) as imagem:
                    formato_esperado = "PNG" if extensao == ".png" else "JPEG"
                    if imagem.format != formato_esperado:
                        raise ValueError("Formato de imagem incompatível")
                    imagem.verify()
                with Image.open(BytesIO(dados)) as imagem:
                    imagem.load()
        except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
            raise HTTPException(422, detail={"codigo": "IMAGEM_INVALIDA", "mensagem": "Imagem não pôde ser decodificada."}) from exc
    return tipo_entrada, mime_esperado, nome_seguro


@router.post(
    "/arquivos",
    response_model=ReciboArquivo,
    status_code=201,
    summary="Receber e armazenar original (não executa triagem)",
)
def receber_documento(
    documento_id: Annotated[str, Form(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9-]*$")],
    canal_origem: Annotated[str, Form(min_length=1, max_length=80)],
    arquivo: Annotated[UploadFile, File(description="PDF, PNG ou JPEG sintético; máximo de 10 MiB")],
    _: Annotated[None, Depends(somente_desenvolvimento_local)],
    storage: Annotated[OCIStorage, Depends(armazenamento)],
) -> ReciboArquivo:
    if not canal_origem.strip():
        raise HTTPException(422, detail={"codigo": "CANAL_INVALIDO", "mensagem": "Canal de origem não pode ser vazio."})

    dados = bytearray()
    while bloco := arquivo.file.read(READ_CHUNK_BYTES):
        if len(dados) + len(bloco) > MAX_FILE_BYTES:
            raise HTTPException(413, detail={"codigo": "ARQUIVO_GRANDE", "mensagem": "Limite de 10 MiB excedido."})
        dados.extend(bloco)
    if not dados:
        raise HTTPException(400, detail={"codigo": "ARQUIVO_VAZIO", "mensagem": "Arquivo vazio."})

    tipo_entrada, mime, nome_seguro = verificar_documento(arquivo.filename, arquivo.content_type, bytes(dados))
    extensao = ".jpeg" if nome_seguro.lower().endswith(".jpeg") else os.path.splitext(nome_seguro)[1].lower()
    arquivo_id = uuid.uuid4().hex
    chave = f"originais/{documento_id}/{arquivo_id}{extensao}"
    chave_metadados = f"metadados/{documento_id}/{arquivo_id}.json"
    sha256_local = hashlib.sha256(dados).hexdigest()

    try:
        sha256_enviado = storage.upload_bytes(chave, bytes(dados), content_type=mime)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={"codigo": "FALHA_UPLOAD", "mensagem": "Não foi possível confirmar o armazenamento do original."},
        ) from exc
    if sha256_local != sha256_enviado:
        raise HTTPException(
            status_code=502,
            detail={"codigo": "HASH_INCONSISTENTE", "mensagem": "Integridade do envio não pôde ser confirmada."},
        )

    # O recibo é também o manifesto persistido, com a referência ao nome original.
    # Só é devolvido ao cliente depois da confirmação da gravação do JSON na OCI.
    recibo = ReciboArquivo(
        documento_id=documento_id,
        arquivo_id=arquivo_id,
        registrado_em_utc=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        entrada=EntradaProcessada(
            tipo_entrada=tipo_entrada,
            canal_origem=canal_origem,
            sha256=sha256_local,
            nome_arquivo=nome_seguro,
        ),
        armazenamento_original=OriginalArmazenado(bucket=storage.bucket, chave_original=chave),
        registro_metadados=RegistroMetadados(chave_metadados=chave_metadados),
        tamanho_bytes=len(dados),
    )
    manifesto = recibo.model_dump_json(indent=2).encode("utf-8")
    hash_manifesto = hashlib.sha256(manifesto).hexdigest()
    try:
        enviado = storage.upload_bytes(
            chave_metadados, manifesto, content_type="application/json"
        )
    except Exception as exc:
        # O original já pode existir. Não declarar sucesso nem apagar dados às cegas.
        raise HTTPException(
            502,
            detail={"codigo": "FALHA_REGISTRO_METADADOS", "mensagem": "Original recebido, mas não foi possível registrar seus metadados. Operação incompleta."},
        ) from exc
    if enviado != hash_manifesto:
        raise HTTPException(
            502,
            detail={"codigo": "HASH_METADADOS_INCONSISTENTE", "mensagem": "Integridade do registro de metadados não pôde ser confirmada."},
        )
    return recibo


def _ler_manifesto(storage: OCIStorage, documento_id: str, arquivo_id: str) -> ReciboArquivo:
    """Reutilizado na consulta individual e na listagem; valida referências OCI."""
    chave = f"metadados/{documento_id}/{arquivo_id}.json"
    try:
        dados = storage.download_bytes(chave)
    except Exception as exc:
        # Oracle costuma responder com ServiceError.status; compatível com fakes.
        if getattr(exc, "status", None) == 404:
            raise HTTPException(
                404, detail={"codigo": "REGISTRO_NAO_ENCONTRADO", "mensagem": "Registro não encontrado."}
            ) from exc
        raise HTTPException(
            502, detail={"codigo": "FALHA_CONSULTA_METADADOS", "mensagem": "Não foi possível consultar os metadados."}
        ) from exc
    try:
        recibo = ReciboArquivo.model_validate_json(dados)
    except (ValidationError, ValueError, TypeError) as exc:
        raise HTTPException(
            502, detail={"codigo": "REGISTRO_INVALIDO", "mensagem": "Registro armazenado está inválido."}
        ) from exc
    if (
        recibo.documento_id != documento_id
        or recibo.arquivo_id != arquivo_id
        or recibo.registro_metadados.chave_metadados != chave
        or recibo.armazenamento_original.bucket != storage.bucket
        or not recibo.armazenamento_original.chave_original.startswith(f"originais/{documento_id}/{arquivo_id}.")
    ):
        raise HTTPException(
            502, detail={"codigo": "REGISTRO_INCONSISTENTE", "mensagem": "Registro e identificadores não conferem."}
        )
    return recibo


@router.get(
    "/arquivos/{documento_id}/{arquivo_id}",
    response_model=ReciboArquivo,
    summary="Consultar o manifesto de um upload (não consulta triagem)",
)
def consultar_registro_arquivo(
    documento_id: Annotated[str, Path(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9-]*$")],
    arquivo_id: Annotated[str, Path(pattern=r"^[a-f0-9]{32}$")],
    _: Annotated[None, Depends(somente_desenvolvimento_local)],
    storage: Annotated[OCIStorage, Depends(armazenamento)],
) -> ReciboArquivo:
    return _ler_manifesto(storage, documento_id, arquivo_id)


@router.get(
    "/arquivos/{documento_id}",
    response_model=PaginaArquivos,
    summary="Listar uploads de um documento (não consulta triagem)",
)
def listar_arquivos_documento(
    documento_id: Annotated[str, Path(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9-]*$")],
    _: Annotated[None, Depends(somente_desenvolvimento_local)],
    storage: Annotated[OCIStorage, Depends(armazenamento)],
    limite: Annotated[int, Query(ge=1, le=50)] = 20,
    cursor: Annotated[str | None, Query(max_length=256)] = None,
) -> PaginaArquivos:
    prefixo = f"metadados/{documento_id}/"
    padrao = rf"{re.escape(prefixo)}[a-f0-9]{{32}}\.json"

    # Token OCI é um nome de objeto; não aceitar cursor de outro documento.
    if cursor is not None and re.fullmatch(padrao, cursor) is None:
        raise HTTPException(422, detail={
            "codigo": "CURSOR_INVALIDO", "mensagem": "Cursor não pertence ao documento solicitado."
        })

    try:
        chaves, proximo = storage.listar_chaves(prefixo, inicio=cursor, limite=limite)
    except Exception as exc:
        raise HTTPException(502, detail={
            "codigo": "FALHA_LISTAGEM_METADADOS", "mensagem": "Não foi possível listar os metadados."
        }) from exc

    if (
        len(chaves) > limite
        or any(re.fullmatch(padrao, chave) is None for chave in chaves)
        or (proximo is not None and re.fullmatch(padrao, proximo) is None)
        or (proximo is not None and (not chaves or proximo <= chaves[-1]))
    ):
        raise HTTPException(502, detail={
            "codigo": "LISTAGEM_INCONSISTENTE", "mensagem": "Índice de metadados inconsistente."
        })

    arquivos = []
    for chave in chaves:
        arquivo_id = chave[len(prefixo):-5]  # Remove prefixo e '.json'.
        try:
            recibo = _ler_manifesto(storage, documento_id, arquivo_id)
        except HTTPException as exc:
            if exc.status_code == 404:
                # OCI listou uma chave que deixou de existir durante a consulta.
                raise HTTPException(502, detail={
                    "codigo": "LISTAGEM_INCONSISTENTE",
                    "mensagem": "Índice de metadados inconsistente.",
                }) from exc
            raise
        arquivos.append(ResumoArquivo(
            arquivo_id=recibo.arquivo_id,
            nome_original=recibo.entrada.nome_arquivo or "",
            tipo_entrada=recibo.entrada.tipo_entrada,
            tamanho_bytes=recibo.tamanho_bytes,
            sha256=recibo.entrada.sha256 or "",
            registrado_em_utc=recibo.registrado_em_utc,
        ))
    return PaginaArquivos(
        documento_id=documento_id,
        quantidade_pagina=len(arquivos),
        arquivos=arquivos,
        proximo_cursor=proximo,
    )
