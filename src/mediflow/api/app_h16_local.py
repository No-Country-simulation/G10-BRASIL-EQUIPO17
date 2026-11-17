"""H16: composicao HTTP LOCAL de Gemini + RAG/I4 + OCI Object Storage real.

Restrita a documentos sinteticos oficiais, desenvolvimento local e consentimentos
separados. Nada acessa Gemini/OCI no import ou na rota de estado. Nunca publicar.
"""
from __future__ import annotations

import hmac
import os
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from mediflow.api.app_demo_local import _AMOSTRAS, _RAIZ
from mediflow.api.app_gemini_local import ExtratorSomenteAmostras, fornecer_extrator_gemini
from mediflow.api.composicao_i1_i3_i4_i5 import montar_servico_i1_i3_i4_i5
from mediflow.api.triage_processing import obter_servico_triagem, router as router_processamento
from mediflow.api.uploads import (
    MAX_FILE_BYTES,
    ReciboArquivo,
    _ler_manifesto,
    armazenamento,
    receber_documento,
    somente_desenvolvimento_local,
)
from mediflow.extraction.port import ExtratorDocumento
from mediflow.storage.oci_storage import OCIStorage

BUCKET_DEV = "mediflow-docs-dev"
ACK_OCI = "AUTORIZO_OCI_DEV_H16"
ACK_GEMINI = "AUTORIZO_CHAMADAS_GEMINI"
HOSTS_LOCAIS = {"127.0.0.1", "::1", "testclient"}
TIPOS_MIME = {".pdf": "application/pdf", ".png": "image/png"}


def _flags_h16() -> bool:
    """Tudo desabilitado por padrao, inclusive em modo de teste local."""
    return all((
        os.getenv("MEDIFLOW_ENV") == "development",
        os.getenv("MEDIFLOW_ENABLE_LOCAL_UPLOADS") == "true",
        os.getenv("MEDIFLOW_ENABLE_LOCAL_TRIAGE") == "true",
        os.getenv("MEDIFLOW_ENABLE_LOCAL_GEMINI") == "true",
        os.getenv("MEDIFLOW_ENABLE_LOCAL_OCI") == "true",
        os.getenv("MEDIFLOW_GEMINI_REAL_ACK") == ACK_GEMINI,
        os.getenv("MEDIFLOW_OCI_REAL_ACK") == ACK_OCI,
        os.getenv("OCI_BUCKET") == BUCKET_DEV,
    ))


def fornecer_storage_h16() -> OCIStorage:
    """Cria cliente somente durante requisicao autorizada; nunca no import."""
    if not _flags_h16():
        raise HTTPException(403, detail={
            "codigo": "H16_OCI_DESABILITADA",
            "mensagem": "OCI real da H16 nao autorizada para este ambiente.",
        })
    try:
        storage = OCIStorage.from_environment()
        if storage.bucket != BUCKET_DEV:
            raise ValueError("Bucket resolvido divergente")
        return storage
    except Exception as exc:
        raise HTTPException(503, detail={
            "codigo": "H16_OCI_INDISPONIVEL",
            "mensagem": "Nao foi possivel configurar o armazenamento OCI da H16.",
        }) from exc


def somente_amostra_oficial(
    documento_id: Annotated[str, Form(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9-]*$")],
    arquivo: Annotated[UploadFile, File()],
) -> None:
    """Bloqueia arquivos arbitrarios ANTES da dependência OCI e de qualquer escrita.

    Reposiciona o ponteiro para que a rota de upload original valide os bytes.
    """
    relativo = _AMOSTRAS.get(documento_id)
    if relativo is None:
        raise HTTPException(422, detail={
            "codigo": "H16_AMOSTRA_NAO_AUTORIZADA",
            "mensagem": "Somente DOC-001, DOC-002 e DOC-005 sinteticos oficiais.",
        })
    caminho = _RAIZ / relativo
    mime = TIPOS_MIME.get(caminho.suffix.lower())
    if arquivo.filename != caminho.name or arquivo.content_type != mime:
        raise HTTPException(422, detail={
            "codigo": "H16_AMOSTRA_NAO_AUTORIZADA",
            "mensagem": "Nome ou MIME diferentes da amostra oficial.",
        })
    dados = arquivo.file.read(MAX_FILE_BYTES + 1)
    arquivo.file.seek(0)
    if len(dados) > MAX_FILE_BYTES:
        raise HTTPException(413, detail={
            "codigo": "ARQUIVO_GRANDE", "mensagem": "Limite de 10 MiB excedido.",
        })
    if not hmac.compare_digest(dados, caminho.read_bytes()):
        raise HTTPException(422, detail={
            "codigo": "H16_AMOSTRA_NAO_AUTORIZADA",
            "mensagem": "Conteudo diferente da amostra sintetica oficial.",
        })


def fornecer_servico_h16(
    documento_id: str,
    arquivo_id: str,
    storage: Annotated[OCIStorage, Depends(armazenamento)],
    extrator: Annotated[ExtratorDocumento, Depends(fornecer_extrator_gemini)],
):
    """Compoe o servico por recibo; a validacao do original ocorre no router.

    ExtratorSomenteAmostras faz uma segunda validacao de bytes antes do Gemini.
    """
    recibo = _ler_manifesto(storage, documento_id, arquivo_id)
    return montar_servico_i1_i3_i4_i5(
        storage=storage,
        recibo=recibo,
        extrator=ExtratorSomenteAmostras(extrator),
    )


app = FastAPI(
    title="MediFlow H16 - Gemini + OCI DEV (somente localhost)",
    version="0.1.0-h16-local",
    description=("H16 educacional: somente tres documentos sinteticos oficiais, "
                 "consentimento explicito e bucket OCI de desenvolvimento."),
)
app.include_router(router_processamento)
app.dependency_overrides[armazenamento] = fornecer_storage_h16
app.dependency_overrides[obter_servico_triagem] = fornecer_servico_h16


@app.middleware("http")
async def restringir_h16(request: Request, call_next):
    host = request.client.host if request.client else ""
    if host not in HOSTS_LOCAIS or not _flags_h16():
        return JSONResponse(status_code=403, content={"detail": {
            "codigo": "H16_LOCAL_DESABILITADA",
            "mensagem": "H16 somente em desenvolvimento local autorizado e bucket de teste.",
        }})
    resposta = await call_next(request)
    resposta.headers["X-MediFlow-Mode"] = "h16-local-gemini-oci-dev"
    resposta.headers["Cache-Control"] = "no-store"
    return resposta


@app.post("/v1/triagens/arquivos", response_model=ReciboArquivo, status_code=201,
          tags=["h16-local"], summary="Upload oficial sintetico no bucket OCI dev")
def receber_amostra_h16(
    documento_id: Annotated[str, Form(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9-]*$")],
    canal_origem: Annotated[str, Form(min_length=1, max_length=80)],
    arquivo: Annotated[UploadFile, File()],
    _: Annotated[None, Depends(somente_amostra_oficial)],
    storage: Annotated[OCIStorage, Depends(armazenamento)],
    __: Annotated[None, Depends(somente_desenvolvimento_local)],
) -> ReciboArquivo:
    # Reaproveita validacoes, UUID, recibo e escrita de original/manifesto do I1.
    # A unica diferenca da H16 e o bloqueio PREVIO de qualquer arquivo nao oficial.
    return receber_documento(
        documento_id=documento_id,
        canal_origem=canal_origem,
        arquivo=arquivo,
        _=None,
        storage=storage,
    )


@app.get("/h16/estado", tags=["h16-local"])
def estado_h16():
    """Nao faz rede e nao prova gravacao, leitura ou chamada Gemini bem-sucedida."""
    return {
        "modo": "h16_local_controlada",
        "gemini_configurado": (
            os.getenv("MEDIFLOW_GEMINI_REAL_ACK") == ACK_GEMINI
            and bool(os.getenv("GEMINI_API_KEY"))
        ),
        "oci_configurada_para_bucket_dev": _flags_h16(),
        "rag": "local_real",
        "decisao": "langgraph_e_regras_reais",
        "aviso": "A configuracao nao comprova chamadas reais; verificar execucao e leituras.",
    }
