"""Triagem por texto (EntradaTexto) na demonstração local: fixture + FakeOCI.

Os três cenários oficiais em texto devem chegar às mesmas regras da versão em
arquivo. Texto arbitrário é recusado com erro sanitizado, sem chamar serviços.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mediflow.api.app import app as app_principal
from mediflow.api.app_demo_local import app, cliente_fakeoci
from mediflow.api.app_gemini_local import ExtratorSomenteAmostras
from mediflow.extraction.port import DocumentoParaExtracao
from mediflow.rules.confirmador_alerta import ConfirmadorAlertaOriginal
from mediflow_contracts.models import ResultadoTriagem

RAIZ = Path(__file__).resolve().parents[1]
TEXTOS = {
    "DOC-001": "amostras/texto/DOC-001_laudo_laboratorial_rotina.txt",
    "DOC-002": "amostras/texto/DOC-002_laudo_imagem_alerta.txt",
    "DOC-005": "amostras/texto/DOC-005_receita_ilegivel.txt",
}


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.setenv("MEDIFLOW_ENV", "development")
    monkeypatch.setenv("MEDIFLOW_ENABLE_LOCAL_UPLOADS", "true")
    monkeypatch.setenv("MEDIFLOW_ENABLE_LOCAL_TRIAGE", "true")
    monkeypatch.setenv("MEDIFLOW_ENABLE_LOCAL_DEMO", "true")
    cliente_fakeoci.objetos.clear()
    cliente_fakeoci.falhar_prefixo = None
    with TestClient(app) as c:
        yield c
    cliente_fakeoci.objetos.clear()
    cliente_fakeoci.falhar_prefixo = None


def texto(cenario: str) -> str:
    return (RAIZ / TEXTOS[cenario]).read_text(encoding="utf-8")


def enviar(c, documento_id: str, conteudo: str, canal: str = "texto_demo"):
    return c.post("/v1/triagens/texto", json={
        "contrato_versao": "0.1",
        "documento_id": documento_id,
        "canal_origem": canal,
        "documento_texto": conteudo,
    })


@pytest.mark.parametrize("cenario,regra,destino,status", [
    ("DOC-001", "R005", "prontuario_documental", "processado"),
    ("DOC-002", "R001", "fila_prioritaria_avaliacao_humana", "aguardando_auditoria"),
    ("DOC-005", "R002", "auditoria_humana", "aguardando_auditoria"),
])
def test_tres_cenarios_por_texto(cliente, cenario, regra, destino, status):
    doc_id = f"TXT-{cenario}"
    r = enviar(cliente, doc_id, texto(cenario))
    assert r.status_code == 200, r.text
    resultado = ResultadoTriagem.model_validate(r.json())
    assert resultado.documento_id == doc_id
    assert resultado.entrada.tipo_entrada == "texto"
    assert resultado.entrada.nome_arquivo == f"{doc_id}.txt"
    assert resultado.decisao_roteamento.regra_principal == regra
    assert resultado.decisao_roteamento.destino_principal == destino
    assert resultado.status == status
    assert resultado.armazenamento_oci.status == "confirmado"
    assert resultado.armazenamento_oci.chave_original.startswith(f"originais/{doc_id}/")
    assert resultado.armazenamento_oci.chave_original.endswith(".txt")

    chaves = set(cliente_fakeoci.objetos)
    original = cliente_fakeoci.objetos[resultado.armazenamento_oci.chave_original]
    assert original.decode("utf-8").strip() == texto(cenario).strip()
    assert any(c.startswith(f"metadados/{doc_id}/") for c in chaves)
    assert any(c.startswith(f"resultados/{doc_id}/") for c in chaves)


def test_alerta_confirmado_no_texto_original_independente_da_llm():
    dados = texto("DOC-002").encode("utf-8")
    from hashlib import sha256
    doc = DocumentoParaExtracao("TXT-1", "a" * 32, "TXT-1.txt", "text/plain", dados, sha256(dados).hexdigest())
    assert ConfirmadorAlertaOriginal().confirmar(doc) is True
    dados = texto("DOC-001").encode("utf-8")
    doc = DocumentoParaExtracao("TXT-2", "a" * 32, "TXT-2.txt", "text/plain", dados, sha256(dados).hexdigest())
    assert ConfirmadorAlertaOriginal().confirmar(doc) is False


def test_quebras_de_linha_windows_sao_aceitas(cliente):
    r = enviar(cliente, "TXT-CRLF", texto("DOC-001").replace("\n", "\r\n"))
    assert r.status_code == 200, r.text
    assert r.json()["decisao_roteamento"]["regra_principal"] == "R005"


def test_texto_fora_das_amostras_e_recusado_sem_resultado(cliente):
    r = enviar(cliente, "TXT-LIVRE", "Paciente ficticio. Exame qualquer. Texto nao oficial.")
    assert r.status_code == 422
    assert r.json()["detail"]["codigo"] == "TEXTO_NAO_AUTORIZADO"
    assert "Paciente" not in r.text
    assert cliente_fakeoci.objetos == {}


def test_resultado_aparece_na_listagem_de_triagens(cliente):
    assert enviar(cliente, "TXT-LISTA", texto("DOC-005")).status_code == 200
    r = cliente.get("/v1/triagens")
    assert r.status_code == 200
    assert "TXT-LISTA" in json.dumps(r.json())


def test_rota_texto_bloqueada_sem_flags(monkeypatch):
    monkeypatch.setenv("MEDIFLOW_ENV", "development")
    monkeypatch.setenv("MEDIFLOW_ENABLE_LOCAL_DEMO", "false")
    with TestClient(app) as c:
        r = enviar(c, "TXT-BLOQ", texto("DOC-001"))
    assert r.status_code == 403


def test_entrada_invalida_retorna_422(cliente):
    r = enviar(cliente, "x", texto("DOC-001"))
    assert r.status_code == 422
    r = enviar(cliente, "TXT-VAZIO", "")
    assert r.status_code == 422


def test_api_principal_continua_sem_processamento():
    with TestClient(app_principal) as c:
        r = enviar(c, "TXT-PRINC", texto("DOC-001"))
    assert r.status_code == 501


class _ExtratorQueNaoDeveSerChamado:
    def extrair(self, documento):
        raise AssertionError("Gemini nao pode receber texto fora das amostras")


def test_gemini_local_so_recebe_texto_oficial():
    from hashlib import sha256
    guarda = ExtratorSomenteAmostras(_ExtratorQueNaoDeveSerChamado())
    dados = "Texto arbitrario de teste".encode("utf-8")
    doc = DocumentoParaExtracao("TXT-G", "a" * 32, "TXT-G.txt", "text/plain", dados, sha256(dados).hexdigest())
    with pytest.raises(ValueError, match="amostras"):
        guarda.extrair(doc)


@pytest.mark.parametrize(
    "cenario",
    ["DOC-001", "DOC-002", "DOC-005"],
)
def test_texto_modificado_nao_grava_objetos(cliente, cenario):
    conteudo = texto(cenario) + "\nALTERACAO_FICTICIA"
    resposta = enviar(
        cliente,
        f"TXT-ALTERADO-{cenario}",
        conteudo,
    )

    assert resposta.status_code == 422
    assert resposta.json()["detail"]["codigo"] == "TEXTO_NAO_AUTORIZADO"
    assert cliente_fakeoci.objetos == {}


def test_sem_validador_texto_falha_fechado(cliente):
    from mediflow.api.triage_text import obter_validador_texto

    original = app.dependency_overrides.pop(
        obter_validador_texto,
        None,
    )

    try:
        resposta = enviar(
            cliente,
            "TXT-SEM-VALIDADOR",
            texto("DOC-001"),
        )

        assert resposta.status_code == 503
        assert (
            resposta.json()["detail"]["codigo"]
            == "VALIDACAO_TEXTO_NAO_CONFIGURADA"
        )
        assert cliente_fakeoci.objetos == {}
    finally:
        if original is not None:
            app.dependency_overrides[obter_validador_texto] = original


def test_gemini_local_rejeita_texto_sem_gravar(monkeypatch):
    from mediflow.api.app_gemini_local import (
        app as gemini_app,
        fornecer_extrator_gemini,
    )

    monkeypatch.setenv("MEDIFLOW_ENV", "development")
    monkeypatch.setenv("MEDIFLOW_ENABLE_LOCAL_UPLOADS", "true")
    monkeypatch.setenv("MEDIFLOW_ENABLE_LOCAL_TRIAGE", "true")
    monkeypatch.setenv("MEDIFLOW_ENABLE_LOCAL_GEMINI", "true")

    cliente_fakeoci.objetos.clear()

    anterior = gemini_app.dependency_overrides.get(
        fornecer_extrator_gemini
    )
    gemini_app.dependency_overrides[
        fornecer_extrator_gemini
    ] = lambda: _ExtratorQueNaoDeveSerChamado()

    try:
        with TestClient(gemini_app) as c:
            resposta = enviar(
                c,
                "TXT-GEMINI-REJEITADO",
                "Texto ficticio fora das tres amostras.",
            )

        assert resposta.status_code == 422
        assert resposta.json()["detail"]["codigo"] == "TEXTO_NAO_AUTORIZADO"
        assert cliente_fakeoci.objetos == {}
    finally:
        if anterior is None:
            gemini_app.dependency_overrides.pop(
                fornecer_extrator_gemini,
                None,
            )
        else:
            gemini_app.dependency_overrides[
                fornecer_extrator_gemini
            ] = anterior
        cliente_fakeoci.objetos.clear()
