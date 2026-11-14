"""
Camada de comunicação com o back-end FastAPI.

- `MediFlowClient` fala com a API via HTTP; não há dados simulados na UI.
- `get_backend()` devolve o cliente apontado para a URL da barra lateral.

Enquanto a API não oferece listagem/consulta de triagens, a UI guarda em
sessão os `ResultadoTriagem` que a própria API devolveu (`_session_results`),
para alimentar a Visão geral e a Fila de auditoria. Nada é inventado na UI.

Todas as falhas de rede/HTTP são convertidas em `APIError`, com uma mensagem
em português pronta a mostrar ao utilizador. As páginas só precisam de
`try/except APIError`. Os pedidos e respostas seguem o contrato v0.1
(`ReciboArquivo` -> `ResultadoTriagem`); a tradução para as páginas fica em
mediflow/ui/models.py.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from pathlib import PurePath
from typing import Any

import requests
import streamlit as st

from mediflow.ui.config import (API_BASE_URL, API_TIMEOUT, CONTRACT_VERSION, ENDPOINTS, SOURCE_CHANNEL,
                               STATUS_ENDPOINTS)
from mediflow.ui.models import compute_stats

# Códigos que significam "a API ainda não oferece esta operação".
NOT_IMPLEMENTED_CODES = (404, 405, 501)


class APIError(Exception):
    """Erro de comunicação com a API, com mensagem amigável para a UI."""

    def __init__(self, message: str, status_code: int | None = None, detail: Any = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.detail = detail

    @property
    def not_implemented(self) -> bool:
        return self.status_code in NOT_IMPLEMENTED_CODES


_SESSION_RESULTS = "_api_results"
_DOC_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{2,63}$")


def new_document_id() -> str:
    """ID gerado pela UI, no formato aceite por `EntradaTexto.documento_id`."""
    return f"UI-{datetime.now():%Y%m%d%H%M%S}-{uuid.uuid4().hex[:6].upper()}"


def document_id_for(filename: str) -> str:
    """ID do documento a partir do nome do arquivo (`DOC-001_laudo.pdf` -> `DOC-001`).

    As composições locais só processam as amostras oficiais, identificadas pelo
    prefixo do nome; sem prefixo válido, gera-se um ID novo.
    """
    prefix = PurePath(filename).stem.split("_", 1)[0]
    return prefix if _DOC_ID.match(prefix) else new_document_id()


def _session_results() -> dict[str, dict]:
    """Resultados devolvidos pela API nesta sessão, por documento_id (mais recente vence)."""
    return st.session_state.setdefault(_SESSION_RESULTS, {})


def _remember(result: dict) -> dict:
    if isinstance(result, dict) and result.get("documento_id"):
        _session_results()[result["documento_id"]] = result
    return result


def _detail_message(detail: Any) -> str | None:
    """Extrai a mensagem dos erros estruturados da API ({"codigo", "mensagem"})."""
    if isinstance(detail, dict):
        return detail.get("mensagem")
    return None


class MediFlowClient:
    """Cliente HTTP fino sobre a API FastAPI do MediFlow (contrato v0.1)."""

    def __init__(self, base_url: str = API_BASE_URL, timeout: float = API_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # ------------------------------------------------------------------ #
    # Infraestrutura
    # ------------------------------------------------------------------ #
    def _url(self, endpoint: str, **params: str) -> str:
        return self.base_url + ENDPOINTS[endpoint].format(**params)

    def _request(self, method: str, endpoint: str, path_params: dict | None = None, **kwargs) -> Any:
        url = self._url(endpoint, **(path_params or {}))
        try:
            response = requests.request(method, url, timeout=self.timeout, **kwargs)
        except requests.exceptions.ConnectionError as exc:
            raise APIError(
                f"Não foi possível conectar à API em {self.base_url}. "
                "Confirme se o servidor FastAPI está rodando "
                "(ex.: `uvicorn mediflow.api.app_demo_local:app --host 127.0.0.1 --port 8000`, na raiz do monorepo)."
            ) from exc
        except requests.exceptions.Timeout as exc:
            raise APIError(
                f"A API não respondeu em {self.timeout:.0f}s. O processamento pode estar lento; tente novamente."
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise APIError(f"Erro inesperado na comunicação com a API: {exc}") from exc

        if not response.ok:
            # FastAPI devolve normalmente {"detail": ...}
            try:
                detail = response.json().get("detail")
            except ValueError:
                detail = response.text[:300]
            messages = {
                400: "A API recusou o pedido",
                403: "A API recusou o acesso (confira as variáveis MEDIFLOW_* do servidor)",
                404: "Recurso não encontrado na API",
                405: "A API ainda não oferece esta operação",
                413: "Arquivo grande demais para a API",
                415: "Formato de arquivo não suportado pela API",
                422: "A API rejeitou os dados enviados (validação do contrato)",
                500: "Erro interno no servidor da API",
                502: "Um serviço usado pela API falhou (IA, armazenamento ou regras)",
                501: "Funcionalidade ainda não implementada na API",
                503: "API temporariamente indisponível",
            }
            base = messages.get(response.status_code, f"A API retornou o erro {response.status_code}")
            extra = _detail_message(detail)
            raise APIError(f"{base}." + (f" {extra}" if extra else ""),
                           status_code=response.status_code, detail=detail)

        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise APIError("A API retornou uma resposta que não é JSON válido.") from exc

    # ------------------------------------------------------------------ #
    # Operações de negócio
    # ------------------------------------------------------------------ #
    def status(self) -> str | None:
        """Nome do modo da API (ex.: "Gemini local"), ou None se nenhuma rota de estado responder."""
        for path, label in STATUS_ENDPOINTS.items():
            try:
                response = requests.get(self.base_url + path, timeout=self.timeout)
            except requests.exceptions.RequestException:
                return None  # servidor inacessível: não adianta testar as outras rotas
            if response.ok:
                return label
        return None

    def health(self) -> bool:
        return self.status() is not None

    def list_documents(self, status: str | None = None) -> list[dict]:
        """Lista de `ResultadoTriagem`. `status` usa os valores do contrato (ex.: aguardando_auditoria)."""
        params = {"status": status} if status else None
        try:
            data = self._request("GET", "triage_list", params=params)
        except APIError as err:
            if not err.not_implemented:
                raise
            docs = list(_session_results().values())
            return [d for d in docs if not status or d.get("status") == status]
        # Aceita tanto uma lista simples como {"items": [...]}
        return data.get("items", []) if isinstance(data, dict) else data

    def get_stats(self) -> dict:
        return compute_stats(self.list_documents())

    def get_document(self, doc_id: str) -> dict:
        try:
            return self._request("GET", "triage", path_params={"doc_id": doc_id})
        except APIError as err:
            if err.not_implemented and doc_id in _session_results():
                return _session_results()[doc_id]
            raise

    def upload_document(self, filename: str, content: bytes, mime_type: str) -> dict:
        """Envia o original e pede o processamento (duas chamadas à API)."""
        data = {"documento_id": document_id_for(filename), "canal_origem": SOURCE_CHANNEL}
        files = {"arquivo": (filename, content, mime_type)}
        receipt = self._request("POST", "upload", data=data, files=files)
        path = {"doc_id": receipt["documento_id"], "file_id": receipt["arquivo_id"]}
        return _remember(self._request("POST", "process", path_params=path))

    def submit_text(self, text: str) -> dict:
        payload = {
            "contrato_versao": CONTRACT_VERSION,
            "documento_id": new_document_id(),
            "canal_origem": SOURCE_CHANNEL,
            "documento_texto": text,
        }
        try:
            return _remember(self._request("POST", "triage_text", json=payload))
        except APIError as err:
            if err.not_implemented:
                raise APIError("A API atual ainda não processa texto colado. Envie o documento como arquivo.",
                               status_code=err.status_code, detail=err.detail) from err
            raise

    def review_queue(self) -> list[dict]:
        docs = self.list_documents(status="aguardando_auditoria")
        return [d for d in docs if not d.get("revisao_humana")]

    def submit_review(self, doc_id: str, action: str, reviewer: str,
                      comment: str = "", corrections: dict | None = None) -> dict:
        """Decisão humana (rota proposta pela UI). `corrections` usa os nomes de campos do contrato."""
        payload = {
            "acao": action,                # "aprovar" | "corrigir" | "rejeitar"
            "revisor": reviewer,
            "comentario": comment,
            "correcoes": corrections or {},
        }
        try:
            return _remember(self._request("POST", "review", path_params={"doc_id": doc_id}, json=payload))
        except APIError as err:
            if err.not_implemented:
                raise APIError("A API ainda não registra revisões humanas. A decisão não foi gravada.",
                               status_code=err.status_code, detail=err.detail) from err
            raise


# ---------------------------------------------------------------------- #
# Seleção do back-end
# ---------------------------------------------------------------------- #
def get_backend() -> MediFlowClient:
    """Devolve o cliente da API configurada na barra lateral."""
    return MediFlowClient(st.session_state.get("api_url", API_BASE_URL))


@st.cache_data(ttl=10, show_spinner=False)
def check_api_health(base_url: str) -> str | None:
    """Modo da API (ou None), em cache para não bater na API a cada rerun."""
    return MediFlowClient(base_url, timeout=3).status()
