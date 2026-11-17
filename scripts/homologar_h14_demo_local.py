"""H14: gera evidencia sanitizada dos 3 cenarios da API demo, sem Gemini/OCI reais.

Uso na raiz do repo:
    python scripts/homologar_h14_demo_local.py
    python scripts/homologar_h14_demo_local.py --output docs/evidencias/h14_demonstracao_local.json

O cliente HTTP e interno (FastAPI TestClient). Nenhum servidor publico e iniciado.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from mediflow.api.app_demo_local import app, cliente_fakeoci
from mediflow_contracts.models import ResultadoTriagem

RAIZ = Path(__file__).resolve().parents[1]
SAIDA_PADRAO = Path("docs/evidencias/h14_demonstracao_local.json")
FLAGS_DEMO = {
    "MEDIFLOW_ENV": "development",
    "MEDIFLOW_ENABLE_LOCAL_UPLOADS": "true",
    "MEDIFLOW_ENABLE_LOCAL_TRIAGE": "true",
    "MEDIFLOW_ENABLE_LOCAL_DEMO": "true",
}
CENARIOS = {
    "DOC-001": {
        "arquivo": "amostras/pdf/DOC-001_laudo_laboratorial_rotina.pdf",
        "mime": "application/pdf",
        "categoria": "laudo_laboratorial",
        "regra": "R005",
        "destino": "prontuario_documental",
        "revisao": False,
        "status": "processado",
    },
    "DOC-002": {
        "arquivo": "amostras/pdf/DOC-002_laudo_imagem_alerta.pdf",
        "mime": "application/pdf",
        "categoria": "laudo_imagem",
        "regra": "R001",
        "destino": "fila_prioritaria_avaliacao_humana",
        "revisao": True,
        "status": "aguardando_auditoria",
    },
    "DOC-005": {
        "arquivo": "amostras/imagens/DOC-005_receita_ilegivel.png",
        "mime": "image/png",
        "categoria": "receituario",
        "regra": "R002",
        "destino": "auditoria_humana",
        "revisao": True,
        "status": "aguardando_auditoria",
    },
}


def _exigir(condicao: bool, codigo: str) -> None:
    if not condicao:
        raise RuntimeError(codigo)


def _git_commit() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    commit = proc.stdout.strip()
    _exigir(len(commit) == 40 and all(c in "0123456789abcdef" for c in commit), "GIT_COMMIT_INVALIDO")
    return commit


def executar_h14() -> dict:
    """Executa upload+processamento dos tres originais sintéticos; nao grava arquivo.

    Preserva o FakeOCI global preexistente para nao contaminar testes subsequentes.
    Apenas resumo seguro, sem payload de paciente, evidencias ou chaves de storage.
    """
    anterior = dict(cliente_fakeoci.objetos)
    falhar_anterior = cliente_fakeoci.falhar_prefixo
    cliente_fakeoci.objetos.clear()
    cliente_fakeoci.falhar_prefixo = None
    agora = datetime.now(timezone.utc)
    identificador = uuid4().hex
    cenarios_registrados = []

    try:
        # O modo demo nao consulta GEMINI_API_KEY nem configura o cliente da OCI.
        with patch.dict(os.environ, FLAGS_DEMO, clear=False):
            with TestClient(app) as cliente:
                modo = cliente.get("/demo/estado")
                _exigir(modo.status_code == 200, "H14_ESTADO_HTTP_INVALIDO")
                estado = modo.json()
                _exigir(
                    estado.get("modo") == "simulacao_tecnica"
                    and estado.get("gemini_real") is False
                    and estado.get("oci_real") is False
                    and estado.get("extracao") == "fixture_sintetica",
                    "H14_MODO_NAO_ISOLADO",
                )

                for documento_id, esperado in CENARIOS.items():
                    arquivo = RAIZ / esperado["arquivo"]
                    bytes_originais = arquivo.read_bytes()
                    mime = esperado["mime"]
                    resposta_upload = cliente.post(
                        "/v1/triagens/arquivos",
                        data={"documento_id": documento_id, "canal_origem": "h14_demo_local"},
                        files={"arquivo": (arquivo.name, bytes_originais, mime)},
                    )
                    _exigir(resposta_upload.status_code == 201, f"{documento_id}_UPLOAD_NAO_CONFIRMADO")
                    recibo = resposta_upload.json()
                    _exigir(recibo.get("documento_id") == documento_id, f"{documento_id}_RECIBO_DIVERGENTE")
                    _exigir(recibo.get("entrada", {}).get("sha256") == sha256(bytes_originais).hexdigest(), f"{documento_id}_HASH_DIVERGENTE")
                    arquivo_id = recibo.get("arquivo_id")
                    _exigir(isinstance(arquivo_id, str) and len(arquivo_id) == 32, f"{documento_id}_ARQUIVO_ID_INVALIDO")

                    resposta = cliente.post(
                        f"/v1/triagens/arquivos/{documento_id}/{arquivo_id}/processar"
                    )
                    _exigir(resposta.status_code == 200, f"{documento_id}_PROCESSAMENTO_NAO_CONFIRMADO")
                    _exigir("fakeoci" in resposta.headers.get("X-MediFlow-Mode", "").lower(), f"{documento_id}_MODO_HTTP_INVALIDO")
                    resultado = ResultadoTriagem.model_validate(resposta.json())
                    decisao = resultado.decisao_roteamento
                    _exigir(resultado.documento_id == documento_id, f"{documento_id}_DOCUMENTO_DIVERGENTE")
                    _exigir(resultado.entrada.sha256 == recibo["entrada"]["sha256"], f"{documento_id}_ENTRADA_DIVERGENTE")
                    _exigir(resultado.entrada.nome_arquivo == arquivo.name, f"{documento_id}_NOME_DIVERGENTE")
                    _exigir(resultado.classificacao.tipo_documento == esperado["categoria"], f"{documento_id}_CLASSIFICACAO_DIVERGENTE")
                    _exigir(decisao.regra_principal == esperado["regra"], f"{documento_id}_REGRA_DIVERGENTE")
                    _exigir(decisao.destino_principal == esperado["destino"], f"{documento_id}_DESTINO_DIVERGENTE")
                    _exigir(decisao.requer_revisao_humana is esperado["revisao"], f"{documento_id}_REVISAO_DIVERGENTE")
                    _exigir(resultado.status == esperado["status"], f"{documento_id}_STATUS_DIVERGENTE")
                    _exigir(resultado.rag.status == "consultado", f"{documento_id}_RAG_NAO_CONSULTADO")
                    _exigir(resultado.classificacao.indicador_qualidade.calibrado is False, f"{documento_id}_CONFIANCA_INDEVIDA")
                    storage = resultado.armazenamento_oci
                    _exigir(storage.status == "confirmado" and storage.bucket == "FAKEOCI-SOMENTE-MEMORIA", f"{documento_id}_FAKEOCI_NAO_CONFIRMADO")
                    _exigir(storage.chave_resultado in cliente_fakeoci.objetos, f"{documento_id}_RESULTADO_NAO_PERSISTIDO")
                    salvo = ResultadoTriagem.model_validate_json(cliente_fakeoci.objetos[storage.chave_resultado])
                    _exigir(salvo == resultado, f"{documento_id}_RESULTADO_NAO_CONSISTENTE")
                    if documento_id == "DOC-005":
                        _exigir(
                            bool(resultado.dados_extraidos.medicamentos)
                            and resultado.dados_extraidos.medicamentos[0].dosagem_texto is None
                            and resultado.dados_extraidos.medicamentos[0].dosagem_status == "ilegivel",
                            "DOC-005_DOSAGEM_INFERIDA",
                        )

                    # Lista explícita de campos; nunca serializar o JSON clínico inteiro.
                    cenarios_registrados.append({
                        "teste_id": f"H14-{documento_id}",
                        "documento_id": documento_id,
                        "status_h14": "aprovado_com_simulacao",
                        "http_upload": resposta_upload.status_code,
                        "http_processamento": resposta.status_code,
                        "sha256_amostra_sintetica": sha256(bytes_originais).hexdigest(),
                        "categoria": resultado.classificacao.tipo_documento,
                        "regra": decisao.regra_principal,
                        "destino": decisao.destino_principal,
                        "revisao_humana": decisao.requer_revisao_humana,
                        "status_resultado": resultado.status,
                        "rag_status": resultado.rag.status,
                        "numero_fontes_rag": len(resultado.rag.fontes),
                        "numero_evidencias_documentais": len(resultado.evidencias),
                        "persistencia": "fakeoci_memoria_verificada",
                    })
    finally:
        cliente_fakeoci.objetos.clear()
        cliente_fakeoci.objetos.update(anterior)
        cliente_fakeoci.falhar_prefixo = falhar_anterior

    return {
        "criterio": "H14",
        "status_h14": "aprovado_com_simulacao",
        "execucao_id": identificador,
        "timestamp_utc": agora.isoformat().replace("+00:00", "Z"),
        "timestamp_brt": agora.astimezone(timezone(timedelta(hours=-3))).isoformat(),
        "git_commit_base": _git_commit(),
        "ambiente": "local_testclient_sem_rede",
        "componentes": {
            "api": "fastapi_real_local",
            "extracao": "fixtures_sinteticas_nao_gemini",
            "rag": "recuperador_local_real",
            "regras_langgraph": "implementacoes_locais_reais",
            "persistencia": "fakeoci_volatil_em_memoria",
            "gemini_real": False,
            "oci_real": False,
            "streamlit_executado": False,
        },
        "cenarios": cenarios_registrados,
        "limitacao": (
            "Evidencia H14 tecnica local: nao homologa Gemini real, OCI real, "
            "Streamlit nem uso clinico. Chaves e conteudo integral nao sao registrados."
        ),
    }


def salvar_relatorio(relatorio: dict, destino: Path) -> Path:
    arquivo = destino if destino.is_absolute() else RAIZ / destino
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(json.dumps(relatorio, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return arquivo


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=SAIDA_PADRAO,
                        help="Caminho da evidencia JSON (padrao: docs/evidencias/h14_demonstracao_local.json)")
    argumentos = parser.parse_args()
    try:
        relatorio = executar_h14()
        destino = salvar_relatorio(relatorio, argumentos.output)
    except Exception as exc:
        # Nao exibir resposta HTTP, documentos ou rastros de provedor.
        print(f"H14: NAO CONFIRMADO ({type(exc).__name__})")
        return 1
    print(f"H14: {len(relatorio['cenarios'])}/3 cenarios aprovados com simulacao")
    for c in relatorio["cenarios"]:
        print(f"  {c['documento_id']}: {c['regra']} -> {c['destino']} ({c['status_resultado']})")
    print(f"Evidencia local: {destino}")
    print("Gemini/OCI reais: NAO executados. Streamlit: NAO executado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
