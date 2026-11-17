"""Triagem de documento enviado como TEXTO (JSON `EntradaTexto`).

Grava o texto como original `.txt` (UTF-8) e manifesto, como um upload, e
executa o mesmo pipeline do arquivo: extração, confirmação independente do
alerta no texto original, RAG, regras/LangGraph e persistência.

Não registrar na API principal. Apps locais fornecem a fábrica de serviço via
`dependency_overrides`; sem ela, a rota falha fechada com HTTP 503.
"""
from __future__ import annotations

from typing import Annotated, Callable

from fastapi import APIRouter, Depends, HTTPException

from mediflow.api.triage_processing import executar_servico, somente_processamento_local
from mediflow.api.triage_service import ServicoTriagem
from mediflow.api.uploads import (
    MAX_FILE_BYTES,
    ReciboArquivo,
    armazenamento,
    registrar_original,
)
from mediflow.extraction.port import DocumentoParaExtracao
from mediflow.storage.oci_storage import OCIStorage
from mediflow_contracts.models import EntradaTexto, ResultadoTriagem

router = APIRouter(prefix="/v1/triagens", tags=["processamento-documental"])

FabricaServicoTexto = Callable[[OCIStorage, ReciboArquivo], ServicoTriagem]


def obter_fabrica_servico_texto() -> FabricaServicoTexto:
    """Falha fechada até que um app local injete a composição."""
    raise HTTPException(
        status_code=503,
        detail={
            "codigo": "TRIAGEM_NAO_CONFIGURADA",
            "mensagem": "Adaptadores de processamento ainda nao configurados.",
        },
    )


def normalizar_texto(texto: str) -> str:
    """Forma canônica do original: quebras LF e sem espaços nas pontas."""
    return texto.replace("\r\n", "\n").replace("\r", "\n").strip() + "\n"


@router.post(
    "/texto",
    response_model=ResultadoTriagem,
    summary="Triar documento enviado como texto (somente demonstração local)",
    description=(
        "Recebe `EntradaTexto`, grava o texto como original `.txt` e executa a "
        "triagem completa. Somente dados sintéticos; restrito a ambiente local."
    ),
)
def triar_texto(
    entrada: EntradaTexto,
    _: Annotated[None, Depends(somente_processamento_local)],
    storage: Annotated[OCIStorage, Depends(armazenamento)],
    fabrica: Annotated[FabricaServicoTexto, Depends(obter_fabrica_servico_texto)],
) -> ResultadoTriagem:
    if not entrada.canal_origem.strip() or not entrada.documento_texto.strip():
        raise HTTPException(
            422, detail={"codigo": "TEXTO_INVALIDO", "mensagem": "Texto e canal de origem são obrigatórios."}
        )
    dados = normalizar_texto(entrada.documento_texto).encode("utf-8")
    if len(dados) > MAX_FILE_BYTES:
        raise HTTPException(413, detail={"codigo": "TEXTO_GRANDE", "mensagem": "Limite de 10 MiB excedido."})

    nome = f"{entrada.documento_id}.txt"
    recibo = registrar_original(
        storage,
        documento_id=entrada.documento_id,
        canal_origem=entrada.canal_origem,
        dados=dados,
        nome_seguro=nome,
        tipo_entrada="texto",
        mime="text/plain",
        extensao=".txt",
    )
    documento = DocumentoParaExtracao(
        documento_id=recibo.documento_id,
        arquivo_id=recibo.arquivo_id,
        nome_original=nome,
        mime_type="text/plain",
        conteudo=dados,
        sha256=recibo.entrada.sha256 or "",
    )
    return executar_servico(fabrica(storage, recibo), documento, entrada.canal_origem)
