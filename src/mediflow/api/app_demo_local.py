"""API HTTP de demonstração LOCAL do MediFlow, sem serviços externos.

ATENCAO: usa extracao por fixture dos tres documentos sinteticos oficiais
(e nao Gemini), e armazenamento VOLATIL em memoria (e nao OCI real).
O app normal mediflow.api.app permanece inalterado e nao inclui /processar.
Iniciar SOMENTE via uvicorn em 127.0.0.1, nunca publicar externamente.
"""
from __future__ import annotations

import os
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse

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
from mediflow.extraction.port import DocumentoParaExtracao
from mediflow.storage.oci_storage import OCIStorage
from mediflow_contracts.models import ExtracaoIA

_RAIZ = Path(__file__).resolve().parents[3]
_AMOSTRAS = {
    "DOC-001": "amostras/pdf/DOC-001_laudo_laboratorial_rotina.pdf",
    "DOC-002": "amostras/pdf/DOC-002_laudo_imagem_alerta.pdf",
    "DOC-005": "amostras/imagens/DOC-005_receita_ilegivel.png",
}
_MODO = "extracao-fixture;armazenamento-fakeoci-memoria"


class ObjetoNaoEncontrado(LookupError):
    status = 404


class ObjectStorageMemoria:
    """Cliente OCI em memória para demonstração local, SEM persistência real."""

    def __init__(self) -> None:
        self.objetos: dict[str, bytes] = {}
        self.falhar_prefixo: str | None = None

    def put_object(self, namespace, bucket, object_name, data, **kwargs):
        if self.falhar_prefixo and object_name.startswith(self.falhar_prefixo):
            raise RuntimeError("ARMAZENAMENTO_DEMO_INDISPONIVEL")
        if kwargs.get("if_none_match") == "*" and object_name in self.objetos:
            raise RuntimeError("OBJETO_JA_EXISTE")
        if not isinstance(data, bytes):
            raise TypeError("Conteudo invalido")
        self.objetos[object_name] = bytes(data)
        return SimpleNamespace()

    def get_object(self, namespace, bucket, object_name):
        if object_name not in self.objetos:
            raise ObjetoNaoEncontrado("Objeto nao encontrado")
        return SimpleNamespace(data=SimpleNamespace(content=self.objetos[object_name]))

    def list_objects(self, namespace, bucket, **kwargs):
        prefixo = kwargs.get("prefix", "")
        inicio = kwargs.get("start")
        limite = kwargs.get("limit", 20)
        nomes = sorted(
            chave for chave in self.objetos
            if chave.startswith(prefixo) and (inicio is None or chave >= inicio)
        )
        proximo = nomes[limite] if len(nomes) > limite else None
        return SimpleNamespace(
            data=SimpleNamespace(
                objects=[SimpleNamespace(name=nome) for nome in nomes[:limite]],
                next_start_with=proximo,
            )
        )


# Uma instancia por processo. Tudo se perde no reinicio; nao executar com workers > 1.
cliente_fakeoci = ObjectStorageMemoria()
storage_demo = OCIStorage(cliente_fakeoci, "namespace-demo", "FAKEOCI-SOMENTE-MEMORIA")


class ExtratorFixtureSintetica:
    """Retorna gabarito SOMENTE quando os bytes forem exatamente da amostra oficial."""

    def extrair(self, documento: DocumentoParaExtracao) -> ExtracaoIA:
        relativo = _AMOSTRAS.get(documento.documento_id)
        if relativo is None:
            raise ValueError("Documento fora dos cenarios sinteticos autorizados")
        caminho = _RAIZ / relativo
        original = caminho.read_bytes()
        if (
            documento.conteudo != original
            or documento.sha256 != sha256(original).hexdigest()
            or documento.nome_original != caminho.name
        ):
            raise ValueError("Documento nao corresponde a amostra oficial")
        resposta = _RAIZ / "exemplos" / f"{documento.documento_id}_extracao_ia.json"
        return ExtracaoIA.model_validate_json(resposta.read_text(encoding="utf-8"))


def fornecer_storage_demo() -> OCIStorage:
    """Injecao apenas neste app isolado; nao modifica a API principal."""
    return storage_demo


def fornecer_servico_demo(
    documento_id: str,
    arquivo_id: str,
    storage: Annotated[OCIStorage, Depends(armazenamento)],
):
    # O recibo e consultado por upload, nunca compartilhado entre arquivos.
    recibo = _ler_manifesto(storage, documento_id, arquivo_id)
    return montar_servico_i1_i3_i4_i5(
        storage=storage,
        recibo=recibo,
        extrator=ExtratorFixtureSintetica(),
    )


app = FastAPI(
    title="MediFlow - API DEMO LOCAL (Fixtures + FakeOCI)",
    version="0.1.0-demo",
    description=(
        "Somente amostras sinteticas DOC-001, DOC-002 e DOC-005. "
        "Extracao por fixtures; armazenamento FakeOCI em memoria; "
        "RAG e LangGraph executados localmente. Proibido uso clinico ou publico."
    ),
)
app.include_router(router_uploads)
app.include_router(router_processamento)
app.dependency_overrides[armazenamento] = fornecer_storage_demo
app.dependency_overrides[obter_servico_triagem] = fornecer_servico_demo


@app.middleware("http")
async def bloquear_fora_do_modo_demo(request, call_next):
    """Falha fechada quando ambiente e flags de demonstração nao sao explicitos."""
    if (
        os.getenv("MEDIFLOW_ENV") != "development"
        or os.getenv("MEDIFLOW_ENABLE_LOCAL_UPLOADS") != "true"
        or os.getenv("MEDIFLOW_ENABLE_LOCAL_TRIAGE") != "true"
        or os.getenv("MEDIFLOW_ENABLE_LOCAL_DEMO") != "true"
    ):
        return JSONResponse(
            status_code=403,
            content={"detail": {"codigo": "DEMO_LOCAL_DESABILITADA", "mensagem": "Demonstração local não autorizada."}},
        )
    resposta = await call_next(request)
    resposta.headers["X-MediFlow-Mode"] = _MODO
    resposta.headers["Cache-Control"] = "no-store"
    return resposta


@app.get("/demo/estado", tags=["demonstracao"])
def estado_demo():
    return {
        "modo": "simulacao_tecnica",
        "extracao": "fixture_sintetica",
        "rag": "local_real",
        "decisao": "langgraph_e_regras_reais",
        "armazenamento": "FakeOCI_volatil_em_memoria",
        "gemini_real": False,
        "oci_real": False,
        "aviso": "O status confirmado refere-se somente ao armazenamento ficticio em memoria.",
    }
