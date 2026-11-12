"""Homologação H09: persistência real OCI com dados sintéticos do DOC-001.

Uso dentro do repositório MediFlow, copiado para scripts/:
  python scripts/homologar_h09_oci_real.py           # planejamento sem gravação
  python scripts/homologar_h09_oci_real.py --execute # grava 4 objetos novos

Não executa Gemini, RAG, motor I4 ou FastAPI. A decisão é uma fixture de exemplo.
Não exclui objetos, não sobrescreve chaves e não divulga credenciais.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

BUCKET_PERMITIDO = "mediflow-docs-dev"
DOCUMENTO_ID = "DOC-001"
CANAL = "homologacao_h09"
ARQUIVO_RELATIVO = Path("amostras/pdf/DOC-001_laudo_laboratorial_rotina.pdf")
EXEMPLO_RELATIVO = Path("exemplos/DOC-001_resultado.json")


def _validar(condicao: bool, codigo: str) -> None:
    if not condicao:
        raise RuntimeError(codigo)


def _conferir_bytes(storage, chave: str, esperado: bytes) -> None:
    recebido = storage.download_bytes(chave)
    _validar(isinstance(recebido, bytes) and recebido == esperado,
             "LEITURA_DIVERGENTE")


def homologar(executar: bool) -> None:
    # Identificadores imprevisíveis: uma execução nunca reutiliza chaves anteriores.
    arquivo_id = uuid4().hex
    execucao_id = uuid4().hex
    raiz = Path(__file__).resolve().parents[1]
    arquivo = raiz / ARQUIVO_RELATIVO
    exemplo = raiz / EXEMPLO_RELATIVO
    original_key = f"originais/{DOCUMENTO_ID}/{arquivo_id}.pdf"
    manifesto_key = f"metadados/{DOCUMENTO_ID}/{arquivo_id}.json"
    historico_key = f"historicos/{DOCUMENTO_ID}/{arquivo_id}/{execucao_id}.json"
    resultado_key = f"resultados/{DOCUMENTO_ID}/{arquivo_id}/{execucao_id}.json"

    print("H09 - Homologacao de persistencia OCI com fixture sintetica")
    print(f"Bucket autorizado: {BUCKET_PERMITIDO}")
    print(f"Documento: {DOCUMENTO_ID} | arquivo_id: {arquivo_id} | execucao_id: {execucao_id}")
    print("Objetos novos previstos (nunca sobrescritos):")
    for chave in (original_key, manifesto_key, historico_key, resultado_key):
        print(f"  {chave}")

    if not executar:
        print("MODO PLANEJAMENTO: nenhuma credencial consultada e nenhuma escrita efetuada.")
        print("Para realizar a homologacao com as credenciais OCI locais, use --execute.")
        return

    _validar(os.environ.get("OCI_BUCKET") == BUCKET_PERMITIDO,
             "BUCKET_NAO_AUTORIZADO: configure OCI_BUCKET=mediflow-docs-dev")
    _validar(os.environ.get("MEDIFLOW_ENV") == "development",
             "AMBIENTE_NAO_AUTORIZADO")

    # Importar somente na execução. Modo planejamento funciona sem SDK Oracle.
    from mediflow.api.uploads import ReciboArquivo, OriginalArmazenado, RegistroMetadados
    from mediflow.storage.oci_storage import OCIStorage
    from mediflow.storage.triage_persistence import persistir_resultado
    from mediflow_contracts.models import EntradaProcessada, ResultadoTriagem

    # Validar todos os insumos antes de conectar ou gravar na OCI.
    _validar(arquivo.is_file() and exemplo.is_file(), "AMOSTRAS_NAO_ENCONTRADAS")
    conteudo = arquivo.read_bytes()
    _validar(conteudo.startswith(b"%PDF-") and 0 < len(conteudo) <= 10 * 1024 * 1024,
             "DOCUMENTO_SINTETICO_INVALIDO")
    sha = hashlib.sha256(conteudo).hexdigest()

    entrada = EntradaProcessada(
        tipo_entrada="pdf",
        canal_origem=CANAL,
        sha256=sha,
        nome_arquivo=arquivo.name,
    )
    resultado = ResultadoTriagem.model_validate_json(exemplo.read_bytes())
    _validar(resultado.documento_id == DOCUMENTO_ID, "FIXTURE_DOCUMENTO_DIVERGENTE")
    _validar(resultado.status == "processado" and
             resultado.decisao_roteamento.regra_principal == "R005" and
             resultado.armazenamento_oci.status == "pendente",
             "FIXTURE_NAO_E_A_ESPERADA")
    resultado.entrada = entrada.model_copy(deep=True)

    recibo = ReciboArquivo(
        documento_id=DOCUMENTO_ID,
        arquivo_id=arquivo_id,
        registrado_em_utc=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        entrada=entrada.model_copy(deep=True),
        armazenamento_original=OriginalArmazenado(
            bucket=BUCKET_PERMITIDO,
            chave_original=original_key,
        ),
        registro_metadados=RegistroMetadados(chave_metadados=manifesto_key),
        tamanho_bytes=len(conteudo),
    )
    manifesto = recibo.model_dump_json(indent=2).encode("utf-8")

    # Confirmação explícita de bucket antes de realizar a primeira escrita.
    storage = OCIStorage.from_environment()
    _validar(storage.bucket == BUCKET_PERMITIDO, "BUCKET_RESOLVIDO_DIVERGENTE")

    print("[1/4] Gravando e conferindo original...")
    hash_gravado = storage.upload_bytes_if_absent(
        original_key, conteudo, content_type="application/pdf")
    _validar(hash_gravado == sha, "HASH_ORIGINAL_DIVERGENTE")
    _conferir_bytes(storage, original_key, conteudo)

    print("[2/4] Gravando e conferindo manifesto...")
    hash_manifesto = storage.upload_bytes_if_absent(
        manifesto_key, manifesto, content_type="application/json")
    _validar(hash_manifesto == hashlib.sha256(manifesto).hexdigest(),
             "HASH_MANIFESTO_DIVERGENTE")
    _conferir_bytes(storage, manifesto_key, manifesto)
    recebido = ReciboArquivo.model_validate_json(storage.download_bytes(manifesto_key))
    _validar(recebido == recibo, "MANIFESTO_INCONSISTENTE")

    print("[3/4] Persistindo historico e resultado via codigo real I1/OCI...")
    confirmado = persistir_resultado(
        storage, recebido, resultado, execucao_id=execucao_id)
    _validar(confirmado.armazenamento_oci.status == "confirmado", "SEM_CONFIRMACAO")
    _validar(confirmado.armazenamento_oci.chave_original == original_key and
             confirmado.armazenamento_oci.chave_historico == historico_key and
             confirmado.armazenamento_oci.chave_resultado == resultado_key,
             "CHAVES_INCONSISTENTES")

    print("[4/4] Validando as leituras e as associacoes...")
    import json
    resultado_gravado = ResultadoTriagem.model_validate_json(
        storage.download_bytes(resultado_key))
    historico_gravado = json.loads(storage.download_bytes(historico_key))
    _validar(resultado_gravado == confirmado, "RESULTADO_GRAVADO_DIVERGENTE")
    _validar(historico_gravado.get("documento_id") == DOCUMENTO_ID and
             historico_gravado.get("arquivo_id") == arquivo_id and
             historico_gravado.get("execucao_id") == execucao_id and
             historico_gravado.get("status_resultado") == "processado",
             "HISTORICO_GRAVADO_DIVERGENTE")

    print("H09: APROVADO REAL CONTROLADO - Object Storage (4 objetos verificados)")
    print("Decisao R005: FIXTURE SINTETICA; nao houve execucao do motor I4.")
    print("Sem delecao automatica: registrar as 4 chaves para retencao/limpeza futura.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true",
                        help="Autoriza gravar 4 objetos sintéticos novos no bucket dev")
    argumentos = parser.parse_args()
    try:
        homologar(argumentos.execute)
        return 0
    except Exception as exc:
        # Erros do SDK podem conter identificadores e caminhos de credenciais.
        print(f"H09: NAO CONFIRMADO - {type(exc).__name__}", file=sys.stderr)
        print("Pode haver objetos parciais. Conferir as chaves impressas acima.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
