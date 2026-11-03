"""Rota HTTP preparatória I1 para acionar ServicoTriagem a partir da OCI.

Nao registra este router em app.py. Por padrao o processamento esta desativado,
e nao ha um adaptador real configurado. Exclusivo para testes com dados sinteticos.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import PurePath
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request

from mediflow.api.triage_service import FalhaOrquestracao, ServicoTriagem
from mediflow.api.uploads import (
    MAX_FILE_BYTES,
    _ler_manifesto,
    armazenamento,
    somente_desenvolvimento_local,
)
from mediflow.extraction.port import DocumentoParaExtracao
from mediflow.storage.oci_storage import OCIStorage
from mediflow_contracts.models import ResultadoTriagem

router = APIRouter(prefix="/v1/triagens", tags=["processamento-documental"])

_MIME = {"pdf": "application/pdf", "png": "image/png", "jpeg": "image/jpeg"}
_EXTENSOES = {"pdf": {".pdf"}, "png": {".png"}, "jpeg": {".jpg", ".jpeg"}}


def somente_processamento_local(request: Request) -> None:
    """Portao adicional; nao e autenticacao para ambiente publico."""
    somente_desenvolvimento_local(request)
    if os.getenv("MEDIFLOW_ENABLE_LOCAL_TRIAGE", "false").lower() != "true":
        raise HTTPException(
            status_code=403,
            detail={
                "codigo": "PROCESSAMENTO_DESABILITADO",
                "mensagem": "Processamento disponivel somente em ambiente local autorizado.",
            },
        )


def obter_servico_triagem() -> ServicoTriagem:
    """Falha fechada ate que os adaptadores I2/I3/I4/I5 sejam homologados.

    Nos testes, substitua esta dependencia via app.dependency_overrides.
    Nao ligar automaticamente ExtratorSimulado, decisor demonstrativo ou Gemini.
    """
    raise HTTPException(
        status_code=503,
        detail={
            "codigo": "TRIAGEM_NAO_CONFIGURADA",
            "mensagem": "Adaptadores de processamento ainda nao configurados.",
        },
    )


def _erro_oci(codigo: str, mensagem: str) -> HTTPException:
    return HTTPException(status_code=502, detail={"codigo": codigo, "mensagem": mensagem})


def _documento_verificado(
    storage: OCIStorage, documento_id: str, arquivo_id: str
) -> tuple[DocumentoParaExtracao, str]:
    """Le manifesto do OCI e so devolve bytes cuja integridade foi conferida."""
    recibo = _ler_manifesto(storage, documento_id, arquivo_id)
    entrada = recibo.entrada
    nome = entrada.nome_arquivo
    sha = entrada.sha256
    mime = _MIME.get(entrada.tipo_entrada)
    if not nome or not sha or not mime:
        raise _erro_oci("REGISTRO_INCOMPLETO", "Metadados insuficientes para processamento.")

    # A chave deve ser a chave exata que o upload original teria produzido.
    # A validacao nao depende de nomes fornecidos na requisicao HTTP.
    extensao = PurePath(nome.replace("\\", "/")).suffix.lower()
    if (
        PurePath(nome.replace("\\", "/")).name != nome
        or extensao not in _EXTENSOES[entrada.tipo_entrada]
        or recibo.armazenamento_original.chave_original
        != f"originais/{documento_id}/{arquivo_id}{extensao}"
    ):
        raise _erro_oci("REGISTRO_INCONSISTENTE", "Metadados de arquivo inconsistentes.")

    try:
        conteudo = storage.download_bytes(recibo.armazenamento_original.chave_original)
    except Exception as exc:
        raise _erro_oci("ORIGINAL_INDISPONIVEL", "Arquivo original indisponivel.") from exc

    if (
        not isinstance(conteudo, bytes)
        or not conteudo
        or len(conteudo) > MAX_FILE_BYTES
        or len(conteudo) != recibo.tamanho_bytes
        or hashlib.sha256(conteudo).hexdigest() != sha
    ):
        raise _erro_oci("INTEGRIDADE_ORIGINAL_INVALIDA", "Integridade do arquivo original invalida.")

    return (
        DocumentoParaExtracao(
            documento_id=documento_id,
            arquivo_id=arquivo_id,
            nome_original=nome,
            mime_type=mime,
            conteudo=conteudo,
            sha256=sha,
        ),
        entrada.canal_origem,
    )


@router.post(
    "/arquivos/{documento_id}/{arquivo_id}/processar",
    response_model=ResultadoTriagem,
    summary="Processar documento existente (preparacao I1; desabilitado por padrao)",
    description=(
        "Somente demonstracao local com documentos sinteticos. "
        "Sem adaptadores homologados retorna HTTP 503. "
        "Nao disponibilizar publicamente sem autenticacao e controles adicionais."
    ),
)
def processar_documento_armazenado(
    documento_id: Annotated[str, Path(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9-]*$")],
    arquivo_id: Annotated[str, Path(pattern=r"^[a-f0-9]{32}$")],
    _: Annotated[None, Depends(somente_processamento_local)],
    storage: Annotated[OCIStorage, Depends(armazenamento)],
    servico: Annotated[ServicoTriagem, Depends(obter_servico_triagem)],
) -> ResultadoTriagem:
    """Aciona o servico apenas depois de validar o manifesto e o original."""
    documento, canal_origem = _documento_verificado(storage, documento_id, arquivo_id)
    try:
        resultado = ResultadoTriagem.model_validate(
            servico.executar(documento, canal_origem=canal_origem)
        )
    except FalhaOrquestracao as exc:
        codigos = {
            "entrada": "ENTRADA_PROCESSAMENTO_INVALIDA",
            "extracao": "EXTRACAO_INDISPONIVEL",
            "alerta": "CONFIRMACAO_INDISPONIVEL",
            "decisao": "DECISAO_INDISPONIVEL",
            "persistencia": "PERSISTENCIA_INDISPONIVEL",
        }
        raise HTTPException(
            status_code=502,
            detail={
                "codigo": codigos.get(exc.etapa, "PROCESSAMENTO_INDISPONIVEL"),
                "mensagem": "Nao foi possivel concluir o processamento documental.",
            },
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "codigo": "PROCESSAMENTO_INDISPONIVEL",
                "mensagem": "Nao foi possivel concluir o processamento documental.",
            },
        ) from exc

    if (
        resultado.documento_id != documento_id
        or resultado.entrada.tipo_entrada != _tipo_entrada(documento.mime_type)
        or resultado.entrada.nome_arquivo != documento.nome_original
        or resultado.entrada.sha256 != documento.sha256
        or resultado.entrada.canal_origem != canal_origem
        or resultado.status not in {"processado", "aguardando_auditoria"}
    ):
        raise _erro_oci("RESULTADO_INCONSISTENTE", "Resultado nao corresponde ao arquivo solicitado.")

    return resultado


def _tipo_entrada(mime_type: str) -> str:
    return {v: k for k, v in _MIME.items()}[mime_type]
