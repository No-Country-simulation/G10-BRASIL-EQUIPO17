"""Consulta de triagens e registro de revisao humana (somente composicoes locais).

Nao registra este router em app.py. As rotas leem os resultados ja persistidos
por `persistir_resultado` e gravam cada decisao humana como objeto imutavel em
`revisoes/{documento_id}/{revisao_id}.json`. O `ResultadoTriagem` original nunca
e alterado: correcoes do revisor ficam somente no registro da revisao.

As respostas sao o `ResultadoTriagem` v0.1 acrescido de dois campos aditivos,
`recebido_em` e `revisao_humana` (null ate a primeira decisao). Nao ha
autenticacao: o nome do revisor e declarativo. Exclusivo para dados sinteticos.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator

from mediflow.api.triage_processing import somente_processamento_local
from mediflow.api.uploads import armazenamento
from mediflow.storage.oci_storage import OCIStorage
from mediflow_contracts.models import ResultadoTriagem

router = APIRouter(
    prefix="/v1/triagens",
    tags=["revisao-humana"],
    dependencies=[Depends(somente_processamento_local)],
)

_DOCUMENTO_ID = r"^[A-Za-z0-9][A-Za-z0-9-]{2,63}$"
_CHAVE_RESULTADO = re.compile(r"^resultados/([A-Za-z0-9][A-Za-z0-9-]{2,63})/([a-f0-9]{32})/([a-f0-9]{32})\.json$")
_CHAVE_REVISAO = re.compile(r"^revisoes/[A-Za-z0-9][A-Za-z0-9-]{2,63}/[0-9TZ]{22}-[a-f0-9]{32}\.json$")
_LIMITE_PAGINA = 100
_STATUS = Literal["recebido", "processando", "processado", "aguardando_auditoria", "falha"]


class Revisao(BaseModel):
    """Decisao enviada pelo auditor. Correcoes usam os nomes de campos do contrato v0.1."""

    model_config = ConfigDict(extra="forbid")
    acao: Literal["aprovar", "corrigir", "rejeitar"]
    revisor: str = Field(min_length=1, max_length=120)
    comentario: str = Field(default="", max_length=2000)
    correcoes: dict[Literal["classificacao", "decisao_roteamento", "dados_extraidos"], dict] = Field(
        default_factory=dict
    )

    @model_validator(mode="after")
    def coerencia(self):
        self.revisor = self.revisor.strip()
        self.comentario = self.comentario.strip()
        if not self.revisor:
            raise ValueError("revisor obrigatorio")
        if self.acao == "rejeitar" and not self.comentario:
            raise ValueError("rejeitar exige comentario com o motivo")
        if self.acao == "corrigir" and not self.correcoes:
            raise ValueError("corrigir exige ao menos uma correcao")
        if self.acao != "corrigir" and self.correcoes:
            raise ValueError("correcoes so sao aceitas com acao corrigir")
        return self


def _erro(status: int, codigo: str, mensagem: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"codigo": codigo, "mensagem": mensagem})


def _listar(storage: OCIStorage, prefixo: str) -> list[str]:
    chaves: list[str] = []
    inicio = None
    while True:
        pagina, inicio = storage.listar_chaves(prefixo, inicio=inicio, limite=_LIMITE_PAGINA)
        chaves.extend(pagina)
        if inicio is None:
            return chaves


def _ler_json(storage: OCIStorage, chave: str) -> dict:
    return json.loads(storage.download_bytes(chave).decode("utf-8"))


def _recebido_em(storage: OCIStorage, chave_historico: str | None) -> str | None:
    if not chave_historico:
        return None
    try:
        return _ler_json(storage, chave_historico).get("registrado_em_utc")
    except Exception:
        return None


def _ultima_revisao(
    storage: OCIStorage,
    documento_id: str,
    chave_resultado: str,
) -> dict | None:
    """Busca a revisao mais recente da execucao solicitada."""
    chaves = sorted(
        (
            chave
            for chave in _listar(storage, f"revisoes/{documento_id}/")
            if _CHAVE_REVISAO.fullmatch(chave)
        ),
        reverse=True,
    )

    for chave in chaves:
        revisao = _ler_json(storage, chave)
        if (
            isinstance(revisao, dict)
            and revisao.get("documento_id") == documento_id
            and revisao.get("chave_resultado") == chave_resultado
        ):
            return revisao

    return None


def _resultados_mais_recentes(storage: OCIStorage, documento_id: str | None = None) -> dict[str, dict]:
    """Ultimo ResultadoTriagem valido de cada documento, com `recebido_em` aditivo."""
    prefixo = f"resultados/{documento_id}/" if documento_id else "resultados/"
    try:
        chaves = _listar(storage, prefixo)
    except Exception as exc:
        raise _erro(502, "ARMAZENAMENTO_INDISPONIVEL", "Nao foi possivel listar as triagens.") from exc

    escolhidos: dict[str, dict] = {}
    for chave in chaves:
        if not _CHAVE_RESULTADO.fullmatch(chave):
            continue
        try:
            resultado = ResultadoTriagem.model_validate(_ler_json(storage, chave)).model_dump(mode="json")
        except Exception:
            continue  # objeto parcial ou fora do contrato: nao entra na listagem
        resultado["recebido_em"] = _recebido_em(storage, resultado["armazenamento_oci"].get("chave_historico"))
        atual = escolhidos.get(resultado["documento_id"])
        if atual is None or (resultado["recebido_em"] or "") > (atual["recebido_em"] or ""):
            escolhidos[resultado["documento_id"]] = resultado
    return escolhidos


def _com_revisao(storage: OCIStorage, resultado: dict) -> dict:
    try:
        resultado["revisao_humana"] = _ultima_revisao(
            storage,
            resultado["documento_id"],
            resultado["armazenamento_oci"]["chave_resultado"],
        )
    except Exception as exc:
        raise _erro(502, "ARMAZENAMENTO_INDISPONIVEL", "Nao foi possivel ler as revisoes.") from exc
    return resultado


def _obter(storage: OCIStorage, documento_id: str) -> dict:
    resultado = _resultados_mais_recentes(storage, documento_id).get(documento_id)
    if resultado is None:
        raise _erro(404, "TRIAGEM_NAO_ENCONTRADA", "Nenhum resultado processado para este documento.")
    return _com_revisao(storage, resultado)


@router.get("", summary="Listar triagens processadas (ultimo resultado por documento)")
def listar_triagens(
    storage: Annotated[OCIStorage, Depends(armazenamento)],
    status: Annotated[_STATUS | None, Query()] = None,
) -> list[dict]:
    resultados = _resultados_mais_recentes(storage).values()
    filtrados = [r for r in resultados if status is None or r["status"] == status]
    return [_com_revisao(storage, r) for r in sorted(filtrados, key=lambda r: r["documento_id"])]


@router.get("/{documento_id}", summary="Consultar o ultimo resultado de um documento")
def obter_triagem(
    documento_id: Annotated[str, Path(pattern=_DOCUMENTO_ID)],
    storage: Annotated[OCIStorage, Depends(armazenamento)],
) -> dict:
    return _obter(storage, documento_id)


@router.post("/{documento_id}/revisao", status_code=201, summary="Registrar decisao humana")
def registrar_revisao(
    documento_id: Annotated[str, Path(pattern=_DOCUMENTO_ID)],
    revisao: Revisao,
    storage: Annotated[OCIStorage, Depends(armazenamento)],
) -> dict:
    resultado = _obter(storage, documento_id)
    if not resultado["decisao_roteamento"]["requer_revisao_humana"]:
        raise _erro(409, "REVISAO_NAO_REQUERIDA", "Este documento nao aguarda revisao humana.")

    agora = datetime.now(timezone.utc)
    revisao_id = uuid4().hex
    registro = {
        "contrato_versao": "0.1",
        "revisao_id": revisao_id,
        "documento_id": documento_id,
        "chave_resultado": resultado["armazenamento_oci"]["chave_resultado"],
        "revisado_em": agora.isoformat().replace("+00:00", "Z"),
        **revisao.model_dump(mode="json"),
    }
    chave = f"revisoes/{documento_id}/{agora.strftime('%Y%m%dT%H%M%S%fZ')}-{revisao_id}.json"
    corpo = json.dumps(registro, ensure_ascii=False, sort_keys=True).encode("utf-8")
    try:
        storage.upload_bytes_if_absent(chave, corpo, content_type="application/json")
    except Exception as exc:
        raise _erro(502, "REVISAO_NAO_PERSISTIDA", "Nao foi possivel registrar a revisao.") from exc

    resultado["revisao_humana"] = registro
    return resultado
