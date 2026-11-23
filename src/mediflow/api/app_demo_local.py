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

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse

from mediflow.api.composicao_i1_i3_i4_i5 import montar_servico_i1_i3_i4_i5
from mediflow.api.triage_processing import (
    obter_servico_triagem,
    router as router_processamento,
)
from mediflow.api.triage_review import router as router_revisao
from mediflow.api.triage_text import (
    normalizar_texto,
    obter_fabrica_servico_texto,
    obter_validador_texto,
    router as router_texto,
)
from mediflow.api.uploads import (
    _ler_manifesto,
    armazenamento,
    fornecer_validador_upload,
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
# Versões em texto das mesmas amostras (texto extraído dos originais).
_AMOSTRAS_TEXTO = {
    "DOC-001": "amostras/texto/DOC-001_laudo_laboratorial_rotina.txt",
    "DOC-002": "amostras/texto/DOC-002_laudo_imagem_alerta.txt",
    "DOC-005": "amostras/texto/DOC-005_receita_ilegivel.txt",
}
_MODO = "extracao-fixture;armazenamento-fakeoci-memoria"


def _cenario_texto_oficial(dados: bytes) -> str | None:
    """Reconhece bytes sinteticos, sem OCI nem Gemini."""
    try:
        enviado = normalizar_texto(dados.decode("utf-8"))
    except UnicodeDecodeError:
        return None

    for cenario, relativo in _AMOSTRAS_TEXTO.items():
        oficial = normalizar_texto(
            (_RAIZ / relativo).read_text(encoding="utf-8")
        )
        if enviado == oficial:
            return cenario

    return None


def amostra_texto_oficial(
    documento: DocumentoParaExtracao,
) -> str | None:
    if documento.mime_type != "text/plain":
        return None
    return _cenario_texto_oficial(documento.conteudo)


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
        if documento.mime_type == "text/plain":
            cenario = amostra_texto_oficial(documento)
            if cenario is None:
                raise ValueError("Texto fora dos cenarios sinteticos autorizados")
            resposta = _RAIZ / "exemplos" / f"{cenario}_extracao_ia.json"
            extracao = ExtracaoIA.model_validate_json(resposta.read_text(encoding="utf-8"))
            return extracao.model_copy(update={"documento_id": documento.documento_id})
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


def validar_arquivo_demo(documento_id: str, nome: str, dados: bytes, mime: str) -> None:
    """Rejeita arquivos fora do catalogo sintetico ANTES da persistencia FakeOCI."""
    relativo = _AMOSTRAS.get(documento_id)
    caminho = _RAIZ / relativo if relativo else None
    mime_esperado = "application/pdf" if documento_id in {"DOC-001", "DOC-002"} else "image/png"
    if (
        caminho is None
        or nome != caminho.name
        or mime != mime_esperado
        or dados != caminho.read_bytes()
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "codigo": "AMOSTRA_NAO_AUTORIZADA",
                "mensagem": (
                    "Nesta demonstracao so sao aceitos os arquivos originais sinteticos "
                    "DOC-001 (PDF), DOC-002 (PDF) e DOC-005 (PNG). "
                    "Use uma das amostras oficiais do projeto. "
                    "O arquivo enviado nao foi armazenado nem processado."
                ),
            },
        )


def fornecer_validador_arquivo_demo():
    return validar_arquivo_demo


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


def fornecer_validador_texto_demo():
    return lambda dados: _cenario_texto_oficial(dados) is not None


def fornecer_fabrica_texto_demo():
    return lambda storage, recibo: montar_servico_i1_i3_i4_i5(
        storage=storage, recibo=recibo, extrator=ExtratorFixtureSintetica(),
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
app.include_router(router_revisao)
app.include_router(router_texto)
app.dependency_overrides[armazenamento] = fornecer_storage_demo
app.dependency_overrides[fornecer_validador_upload] = fornecer_validador_arquivo_demo
app.dependency_overrides[obter_servico_triagem] = fornecer_servico_demo
app.dependency_overrides[obter_fabrica_servico_texto] = fornecer_fabrica_texto_demo
app.dependency_overrides[obter_validador_texto] = fornecer_validador_texto_demo


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
