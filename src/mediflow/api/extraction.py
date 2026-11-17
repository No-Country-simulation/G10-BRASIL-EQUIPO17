"""Integração real com o extrator Gemini."""

import hashlib
import logging

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import ValidationError

from mediflow.api.uploads import (
    MAX_FILE_BYTES,
    _ler_manifesto,
    armazenamento,
    somente_desenvolvimento_local,
)
from mediflow.extraction.port import DocumentoParaExtracao, ExtratorDocumento
from mediflow.storage.oci_storage import OCIStorage
from mediflow_contracts.models import ExtracaoIA

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/triagens", tags=["integracao-ia"])

MIME_ENTRADA = {
    "pdf": "application/pdf",
    "png": "image/png",
    "jpeg": "image/jpeg",
}

def extrator_gemini() -> ExtratorDocumento:
    """Cria o extrator real somente durante a requisição."""
    try:
        from mediflow.extraction.gemini_extractor import ExtratorGemini

        return ExtratorGemini()
    except ValueError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "codigo": "EXTRATOR_NAO_CONFIGURADO",
                "mensagem": "Serviço de extração não está configurado.",
            },
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "codigo": "EXTRATOR_INDISPONIVEL",
                "mensagem": "Não foi possível inicializar o serviço de extração.",
            },
        ) from exc


@router.post(
    "/arquivos/{documento_id}/{arquivo_id}/extracao",
    response_model=ExtracaoIA,
    summary="Extrair informações documentais com Gemini",
)
def extrair_documento(
    documento_id: Annotated[
        str,
        Path(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9-]*$"),
    ],
    arquivo_id: Annotated[str, Path(pattern=r"^[a-f0-9]{32}$")],
    _: Annotated[None, Depends(somente_desenvolvimento_local)],
    storage: Annotated[OCIStorage, Depends(armazenamento)],
    extrator: Annotated[ExtratorDocumento, Depends(extrator_gemini)],
) -> ExtracaoIA:
    """Recupera o original, valida sua integridade e executa a extração."""

    recibo = _ler_manifesto(storage, documento_id, arquivo_id)

    nome = recibo.entrada.nome_arquivo
    sha = recibo.entrada.sha256
    chave = recibo.armazenamento_original.chave_original
    mime = MIME_ENTRADA.get(recibo.entrada.tipo_entrada)

    if not mime or not nome or not sha:
        raise HTTPException(
            status_code=502,
            detail={
                "codigo": "REGISTRO_INCOMPLETO",
                "mensagem": "Metadados incompletos para extração.",
            },
        )

    try:
        conteudo = storage.download_bytes(chave)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "codigo": "ORIGINAL_INDISPONIVEL",
                "mensagem": "Não foi possível recuperar o arquivo original.",
            },
        ) from exc

    if (
        not isinstance(conteudo, bytes)
        or not conteudo
        or len(conteudo) > MAX_FILE_BYTES
        or len(conteudo) != recibo.tamanho_bytes
        or hashlib.sha256(conteudo).hexdigest() != sha
    ):
        raise HTTPException(
            status_code=502,
            detail={
                "codigo": "INTEGRIDADE_ORIGINAL_INVALIDA",
                "mensagem": "Arquivo original não corresponde aos metadados armazenados.",
            },
        )

    documento = DocumentoParaExtracao(
        documento_id=documento_id,
        arquivo_id=arquivo_id,
        nome_original=nome,
        mime_type=mime,
        conteudo=conteudo,
        sha256=sha,
    )

    try:
        resultado_bruto = extrator.extrair(documento)
        resultado = ExtracaoIA.model_validate(resultado_bruto)
    except (ValidationError, ValueError, TypeError) as exc:
        if isinstance(exc, ValidationError):
            erros = [
                {
                    "campo": ".".join(str(item) for item in erro["loc"]),
                    "tipo": erro["type"],
                }
                for erro in exc.errors()
            ]
            logger.warning(
                "Falha de validação na extração: documento_id=%s erros=%s",
                documento_id,
                erros,
            )
        else:
            logger.warning(
                "Falha na extração: documento_id=%s tipo=%s",
                documento_id,
                type(exc).__name__,
            )
        raise HTTPException(
            status_code=502,
            detail={
            "codigo": "EXTRACAO_CONTRATO_INVALIDO",
            "mensagem": "Módulo de extração retornou dados incompatíveis com o contrato.",
            },
        ) from exc

    except Exception as exc:
        raise HTTPException(
        status_code=502,
        detail={
                "codigo": "EXTRATOR_INDISPONIVEL",
                "mensagem": "Falha na execução da extração documental.",
        },
        ) from exc

    if resultado.documento_id != documento_id:
        raise HTTPException(
            status_code=502,
            detail={
                "codigo": "EXTRACAO_DOCUMENTO_DIVERGENTE",
                "mensagem": "O identificador retornado pelo extrator não corresponde ao solicitado.",
            },
        )

    return resultado
