"""Composicao HTTP local: Gemini opcional + RAG/decisao reais + FakeOCI.

Nao substitui a API principal nem a demonstracao por fixtures. Nao usa OCI real.
O acesso ao Gemini exige consentimento explicito por variavel de ambiente,
chave configurada e documento exatamente igual a uma amostra sintetica oficial.
Nao iniciar em interface publica nem com varios processos/--reload.
"""
from __future__ import annotations

import os
from hashlib import sha256
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from mediflow.api.app_demo_local import (
    _AMOSTRAS,
    _RAIZ,
    cliente_fakeoci,
    storage_demo,
)
from mediflow.api.composicao_i1_i3_i4_i5 import montar_servico_i1_i3_i4_i5
from mediflow.api.triage_processing import (
    obter_servico_triagem,
    router as router_processamento,
)
from mediflow.api.uploads import (
    _ler_manifesto,
    armazenamento,
    router as router_uploads,
)
from mediflow.extraction.port import DocumentoParaExtracao, ExtratorDocumento
from mediflow.storage.oci_storage import OCIStorage
from mediflow_contracts.models import ExtracaoIA

_MODO = "extracao-gemini-controlada;armazenamento-fakeoci-memoria"
_CONSENTIMENTO = "AUTORIZO_CHAMADAS_GEMINI"
_HOSTS = {"127.0.0.1", "::1", "testclient"}


def _flags_de_ambiente() -> bool:
    return (
        os.getenv("MEDIFLOW_ENV") == "development"
        and os.getenv("MEDIFLOW_ENABLE_LOCAL_UPLOADS") == "true"
        and os.getenv("MEDIFLOW_ENABLE_LOCAL_TRIAGE") == "true"
        and os.getenv("MEDIFLOW_ENABLE_LOCAL_GEMINI") == "true"
    )


def _gemini_autorizado() -> bool:
    return os.getenv("MEDIFLOW_GEMINI_REAL_ACK") == _CONSENTIMENTO


def fornecer_storage_fakeoci() -> OCIStorage:
    """Mesmo fake volátil da demonstração, nunca OCI real."""
    return storage_demo


def fornecer_extrator_gemini() -> ExtratorDocumento:
    """Unico ponto que instancia cliente Gemini real, sem chamada remota aqui.

    Os testes substituem esta dependência por extrator controlado.
    """
    if not _gemini_autorizado():
        raise HTTPException(
            503,
            detail={
                "codigo": "GEMINI_REAL_NAO_AUTORIZADO",
                "mensagem": "Chamadas Gemini reais nao foram autorizadas para este ambiente.",
            },
        )
    if not os.getenv("GEMINI_API_KEY"):
        raise HTTPException(
            503,
            detail={
                "codigo": "GEMINI_REAL_NAO_CONFIGURADO",
                "mensagem": "Credencial Gemini nao configurada.",
            },
        )
    try:
        from mediflow.extraction.gemini_extractor import ExtratorGemini

        return ExtratorGemini()
    except Exception as exc:
        raise HTTPException(
            503,
            detail={
                "codigo": "GEMINI_REAL_INDISPONIVEL",
                "mensagem": "Nao foi possivel preparar a extracao documental.",
            },
        ) from exc


class ExtratorSomenteAmostras:
    """Impede enviar arquivos arbitrarios ou alterados ao provedor externo."""

    def __init__(self, base: ExtratorDocumento) -> None:
        self.base = base

    def extrair(self, documento: DocumentoParaExtracao) -> ExtracaoIA:
        relativo = _AMOSTRAS.get(documento.documento_id)
        if relativo is None:
            raise ValueError("Cenario sintetico nao autorizado")
        caminho = _RAIZ / relativo
        original = caminho.read_bytes()
        if (
            documento.conteudo != original
            or documento.sha256 != sha256(original).hexdigest()
            or documento.nome_original != caminho.name
        ):
            raise ValueError("Documento diferente da amostra sintetica oficial")
        return self.base.extrair(documento)


def fornecer_servico_gemini(
    documento_id: str,
    arquivo_id: str,
    storage: Annotated[OCIStorage, Depends(armazenamento)],
    extrator: Annotated[ExtratorDocumento, Depends(fornecer_extrator_gemini)],
):
    """Composicao por recibo: integridade, extracao, RAG, regras, FakeOCI."""
    recibo = _ler_manifesto(storage, documento_id, arquivo_id)
    return montar_servico_i1_i3_i4_i5(
        storage=storage,
        recibo=recibo,
        extrator=ExtratorSomenteAmostras(extrator),
    )


app = FastAPI(
    title="MediFlow - HOMOLOGACAO GEMINI LOCAL (FakeOCI)",
    version="0.1.0-gemini-local",
    description=(
        "Somente DOC-001, DOC-002 e DOC-005 sinteticos oficiais. "
        "Gemini real exige autorizacao explicita; FakeOCI em memoria. "
        "RAG, motor deterministico e LangGraph locais reais. "
        "Nao publicar nem utilizar dados clinicos reais."
    ),
)
app.include_router(router_uploads)
app.include_router(router_processamento)
app.dependency_overrides[armazenamento] = fornecer_storage_fakeoci
app.dependency_overrides[obter_servico_triagem] = fornecer_servico_gemini


@app.middleware("http")
async def exigir_modo_gemini_local(request: Request, call_next):
    host = request.client.host if request.client else ""
    if not _flags_de_ambiente() or host not in _HOSTS:
        return JSONResponse(
            status_code=403,
            content={
                "detail": {
                    "codigo": "GEMINI_LOCAL_DESABILITADO",
                    "mensagem": "Homologacao Gemini restrita a desenvolvimento local autorizado.",
                }
            },
        )
    resposta = await call_next(request)
    resposta.headers["X-MediFlow-Mode"] = _MODO
    resposta.headers["Cache-Control"] = "no-store"
    return resposta


@app.get("/gemini/estado", tags=["homologacao-gemini"])
def estado_gemini():
    return {
        "modo": "homologacao_gemini_local",
        "extracao": "gemini_real_se_explicitamente_autorizado",
        "gemini_real_habilitado": _gemini_autorizado() and bool(os.getenv("GEMINI_API_KEY")),
        "rag": "local_real",
        "decisao": "langgraph_e_regras_reais",
        "armazenamento": "FakeOCI_volatil_em_memoria",
        "oci_real": False,
        "aviso": (
            "Habilitacao nao comprova chamada real bem-sucedida. "
            "O status confirmado refere-se apenas a FakeOCI em memoria."
        ),
    }
