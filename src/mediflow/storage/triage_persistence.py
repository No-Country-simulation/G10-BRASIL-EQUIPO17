"""Persistência imutável de resultados sintéticos do MediFlow na OCI.

Não executa IA, roteamento, autenticação nem dispara triagem.
O retorno é confirmado apenas após verificar original, histórico e resultado.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import uuid4

from mediflow.storage.oci_storage import OCIStorage
from mediflow_contracts.models import ArmazenamentoOCI, ResultadoTriagem

if TYPE_CHECKING:
    from mediflow.api.uploads import ReciboArquivo

_DOCUMENTO_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{2,63}$")
_ARQUIVO_ID = re.compile(r"^[a-f0-9]{32}$")
_EXECUCAO_ID = re.compile(r"^[a-f0-9]{32}$")


class PersistenciaIncompleta(RuntimeError):
    """O processo pode ter gravado um objeto isolado; não houve confirmação completa."""


def _json_bytes(objeto: dict) -> bytes:
    return json.dumps(objeto, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _ler_integridade(storage: OCIStorage, chave: str, esperado: bytes) -> None:
    recebido = storage.download_bytes(chave)
    if not isinstance(recebido, bytes) or recebido != esperado:
        raise PersistenciaIncompleta("Não foi possível confirmar a integridade do objeto.")


def persistir_resultado(
    storage: OCIStorage,
    recibo: ReciboArquivo,
    resultado: ResultadoTriagem,
    *,
    execucao_id: str | None = None,
) -> ResultadoTriagem:
    """Persiste histórico, depois resultado, sem alterar original nem manifesto.

    Em falhas, não realiza limpeza destrutiva; chaves de execução são imutáveis.
    A operação deve ser invocada somente após a triagem ter sido concluída.
    """
    if not isinstance(resultado, ResultadoTriagem):
        raise TypeError("ResultadoTriagem válido é obrigatório.")
    doc = recibo.documento_id
    arq = recibo.arquivo_id
    if not _DOCUMENTO_ID.fullmatch(doc) or not _ARQUIVO_ID.fullmatch(arq):
        raise ValueError("Identificadores inválidos.")
    if resultado.documento_id != doc:
        raise ValueError("Documento do resultado não corresponde ao recibo.")
    if resultado.status not in {"processado", "aguardando_auditoria"}:
        raise ValueError("Resultado ainda não está concluído.")
    if resultado.armazenamento_oci.status != "pendente":
        raise ValueError("O resultado já contém um estado de persistência.")
    if (
        resultado.entrada.tipo_entrada != recibo.entrada.tipo_entrada
        or resultado.entrada.canal_origem != recibo.entrada.canal_origem
        or resultado.entrada.sha256 != recibo.entrada.sha256
        or resultado.entrada.nome_arquivo != recibo.entrada.nome_arquivo
        or recibo.armazenamento_original.bucket != storage.bucket
        or not recibo.armazenamento_original.chave_original.startswith(f"originais/{doc}/{arq}.")
    ):
        raise ValueError("Metadados de entrada inconsistentes com o recibo.")
    identificador = execucao_id or uuid4().hex
    if not _EXECUCAO_ID.fullmatch(identificador):
        raise ValueError("Identificador de execução inválido.")

    chave_original = recibo.armazenamento_original.chave_original
    chave_historico = f"historicos/{doc}/{arq}/{identificador}.json"
    chave_resultado = f"resultados/{doc}/{arq}/{identificador}.json"

    try:
        original = storage.download_bytes(chave_original)
        if (
            not isinstance(original, bytes)
            or len(original) != recibo.tamanho_bytes
            or hashlib.sha256(original).hexdigest() != recibo.entrada.sha256
        ):
            raise PersistenciaIncompleta("Integridade do original não confirmada.")

        historico = _json_bytes({
            "contrato_versao": "0.1",
            "documento_id": doc,
            "arquivo_id": arq,
            "execucao_id": identificador,
            "registrado_em_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "status_resultado": resultado.status,
            "eventos": [evento.model_dump(mode="json") for evento in resultado.eventos],
        })
        hash_historico = storage.upload_bytes_if_absent(
            chave_historico, historico, content_type="application/json"
        )
        if hash_historico != hashlib.sha256(historico).hexdigest():
            raise PersistenciaIncompleta("Hash de upload do histórico divergente.")
        _ler_integridade(storage, chave_historico, historico)

        dados_finais = resultado.model_dump(mode="json")
        dados_finais["armazenamento_oci"] = ArmazenamentoOCI(
            status="confirmado",
            bucket=storage.bucket,
            chave_original=chave_original,
            chave_resultado=chave_resultado,
            chave_historico=chave_historico,
        ).model_dump(mode="json")
        resultado_confirmado = ResultadoTriagem.model_validate(dados_finais)
        blob = _json_bytes(resultado_confirmado.model_dump(mode="json"))
        hash_resultado = storage.upload_bytes_if_absent(
            chave_resultado, blob, content_type="application/json"
        )
        if hash_resultado != hashlib.sha256(blob).hexdigest():
            raise PersistenciaIncompleta("Hash de upload do resultado divergente.")
        _ler_integridade(storage, chave_resultado, blob)
        return resultado_confirmado
    except Exception as exc:
        # Não expor mensagens OCI que contenham nomes, paths ou credenciais.
        raise PersistenciaIncompleta(
            "Persistência não confirmada. Verifique objetos parciais pela execução."
        ) from exc
