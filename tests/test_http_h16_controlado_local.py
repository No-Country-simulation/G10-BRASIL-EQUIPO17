"""H16 offline: extrator controlado e FakeOCI. PROIBIDO chamar Gemini/OCI reais."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mediflow.api.app import app as app_principal
from mediflow.api.app_demo_local import ExtratorFixtureSintetica, ObjectStorageMemoria
from mediflow.api.app_gemini_local import fornecer_extrator_gemini
from mediflow.api.app_h16_local import app
from mediflow.api.uploads import armazenamento
from mediflow.storage.oci_storage import OCIStorage
from mediflow_contracts.models import ResultadoTriagem

RAIZ = Path(__file__).resolve().parents[1]
ARQUIVOS = {
    "DOC-001": ("amostras/pdf/DOC-001_laudo_laboratorial_rotina.pdf", "application/pdf", "R005", "processado"),
    "DOC-002": ("amostras/pdf/DOC-002_laudo_imagem_alerta.pdf", "application/pdf", "R001", "aguardando_auditoria"),
    "DOC-005": ("amostras/imagens/DOC-005_receita_ilegivel.png", "image/png", "R002", "aguardando_auditoria"),
}


@pytest.fixture
def ambiente(monkeypatch):
    for nome in (
        "MEDIFLOW_ENABLE_LOCAL_UPLOADS", "MEDIFLOW_ENABLE_LOCAL_TRIAGE",
        "MEDIFLOW_ENABLE_LOCAL_GEMINI", "MEDIFLOW_ENABLE_LOCAL_OCI",
    ):
        monkeypatch.setenv(nome, "true")
    monkeypatch.setenv("MEDIFLOW_ENV", "development")
    monkeypatch.setenv("OCI_BUCKET", "mediflow-docs-dev")
    monkeypatch.setenv("MEDIFLOW_OCI_REAL_ACK", "AUTORIZO_OCI_DEV_H16")
    monkeypatch.setenv("MEDIFLOW_GEMINI_REAL_ACK", "AUTORIZO_CHAMADAS_GEMINI")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    fake = ObjectStorageMemoria()
    storage = OCIStorage(fake, "namespace-ficticio", "FAKEOCI-H16-TEST")
    # Overrides garantem zero clientes reais, mesmo com flags/ACK da fixture.
    app.dependency_overrides[armazenamento] = lambda: storage
    app.dependency_overrides[fornecer_extrator_gemini] = lambda: ExtratorFixtureSintetica()
    try:
        with TestClient(app) as cliente:
            yield cliente, fake, storage
    finally:
        app.dependency_overrides.pop(armazenamento, None)
        app.dependency_overrides.pop(fornecer_extrator_gemini, None)
        # A aplicacao pode ser utilizada por outro teste: restaurar o provider H16.
        from mediflow.api.app_h16_local import fornecer_storage_h16
        app.dependency_overrides[armazenamento] = fornecer_storage_h16


def upload(cliente, doc_id, *, conteudo=None, filename=None, mime=None):
    relativo, tipo, *_ = ARQUIVOS[doc_id]
    arquivo = RAIZ / relativo
    return cliente.post(
        "/v1/triagens/arquivos",
        data={"documento_id": doc_id, "canal_origem": "homologacao_h16_offline"},
        files={"arquivo": (filename or arquivo.name, arquivo.read_bytes() if conteudo is None else conteudo,
                            mime or tipo)},
    )


@pytest.mark.parametrize("doc_id", list(ARQUIVOS))
def test_tres_cenarios_http_offline_e_leitura_de_resultado(ambiente, doc_id):
    cliente, fake, _ = ambiente
    resposta = upload(cliente, doc_id)
    assert resposta.status_code == 201, resposta.text
    recibo = resposta.json()
    assert len(fake.objetos) == 2
    resposta = cliente.post(
        f"/v1/triagens/arquivos/{doc_id}/{recibo['arquivo_id']}/processar")
    assert resposta.status_code == 200, resposta.text
    resultado = ResultadoTriagem.model_validate(resposta.json())
    _, _, regra, status = ARQUIVOS[doc_id]
    assert resultado.decisao_roteamento.regra_principal == regra
    assert resultado.status == status
    assert resultado.rag.status == "consultado"
    assert resultado.armazenamento_oci.status == "confirmado"
    assert resultado.armazenamento_oci.bucket == "FAKEOCI-H16-TEST"
    assert resultado.entrada.sha256 == recibo["entrada"]["sha256"]
    assert len(fake.objetos) == 5
    assert any(c.startswith(("processados/", "auditoria_humana/")) for c in fake.objetos)
    assert ResultadoTriagem.model_validate_json(
        fake.objetos[resultado.armazenamento_oci.chave_resultado]) == resultado
    if doc_id == "DOC-005":
        assert resultado.dados_extraidos.medicamentos[0].dosagem_texto is None


def test_upload_outros_bytes_bloqueado_antes_da_primeira_gravacao(ambiente):
    cliente, fake, _ = ambiente
    dados = (RAIZ / ARQUIVOS["DOC-002"][0]).read_bytes()
    r = upload(cliente, "DOC-001", conteudo=dados)
    assert r.status_code == 422
    assert r.json()["detail"]["codigo"] == "H16_AMOSTRA_NAO_AUTORIZADA"
    assert fake.objetos == {}


def test_upload_nome_alterado_bloqueado_antes_da_primeira_gravacao(ambiente):
    cliente, fake, _ = ambiente
    r = upload(cliente, "DOC-001", filename="arquivo.pdf")
    assert r.status_code == 422
    assert fake.objetos == {}


def test_sem_ack_oci_rejeita_sem_chamar_storage(ambiente, monkeypatch):
    cliente, fake, _ = ambiente
    monkeypatch.delenv("MEDIFLOW_OCI_REAL_ACK")
    r = upload(cliente, "DOC-001")
    assert r.status_code == 403
    assert r.json()["detail"]["codigo"] == "H16_LOCAL_DESABILITADA"
    assert fake.objetos == {}


def test_bucket_incorreto_rejeita_sem_gravacao(ambiente, monkeypatch):
    cliente, fake, _ = ambiente
    monkeypatch.setenv("OCI_BUCKET", "bucket-producao")
    r = upload(cliente, "DOC-001")
    assert r.status_code == 403
    assert fake.objetos == {}


def test_sem_chave_gemini_nao_executa_processamento(ambiente):
    cliente, fake, _ = ambiente
    app.dependency_overrides.pop(fornecer_extrator_gemini, None)
    recibo = upload(cliente, "DOC-001").json()
    r = cliente.post(f"/v1/triagens/arquivos/DOC-001/{recibo['arquivo_id']}/processar")
    assert r.status_code == 503
    assert r.json()["detail"]["codigo"] == "GEMINI_REAL_NAO_CONFIGURADO"
    assert len(fake.objetos) == 2


def test_falha_parcial_em_resultado_nao_declara_confirmacao(ambiente):
    cliente, fake, _ = ambiente
    recibo = upload(cliente, "DOC-001").json()
    fake.falhar_prefixo = "resultados/"
    r = cliente.post(f"/v1/triagens/arquivos/DOC-001/{recibo['arquivo_id']}/processar")
    assert r.status_code == 502
    assert r.json()["detail"]["codigo"] == "PERSISTENCIA_INDISPONIVEL"
    assert not any(chave.startswith("resultados/") for chave in fake.objetos)


def test_estado_nao_comprova_integracao_real(ambiente):
    cliente, _, _ = ambiente
    r = cliente.get("/h16/estado")
    assert r.status_code == 200
    assert r.json()["gemini_configurado"] is False
    assert "nao comprova" in r.json()["aviso"]
    assert r.headers["Cache-Control"] == "no-store"


def test_app_principal_nao_publica_processamento():
    assert not any(getattr(r, "path", "").endswith("/processar") for r in app_principal.routes)


# --- Fila e revisao humana na H16 (offline: FakeOCI + extrator por fixture) ---

def processar(cliente, doc_id):
    recibo = upload(cliente, doc_id).json()
    r = cliente.post(f"/v1/triagens/arquivos/{doc_id}/{recibo['arquivo_id']}/processar")
    assert r.status_code == 200, r.text
    return r.json()


def test_fila_lista_resultados_persistidos_no_bucket(ambiente):
    cliente, _, _ = ambiente
    for doc_id in ARQUIVOS:
        processar(cliente, doc_id)
    r = cliente.get("/v1/triagens", params={"status": "aguardando_auditoria"})
    assert r.status_code == 200, r.text
    fila = r.json()
    assert [d["documento_id"] for d in fila] == ["DOC-002", "DOC-005"]
    assert all(d["revisao_humana"] is None and d["recebido_em"] for d in fila)
    assert cliente.get("/v1/triagens/DOC-001").json()["status"] == "processado"


def test_revisao_grava_objeto_imutavel_sem_alterar_resultado(ambiente):
    cliente, fake, _ = ambiente
    resultado = processar(cliente, "DOC-005")
    chave_resultado = resultado["armazenamento_oci"]["chave_resultado"]
    original = fake.objetos[chave_resultado]
    r = cliente.post("/v1/triagens/DOC-005/revisao", json={
        "acao": "corrigir", "revisor": "Auditora Sintetica",
        "comentario": "Dose confirmada com o prescritor (cenario ficticio).",
        "correcoes": {"dados_extraidos": {"medicamentos": [
            {"nome": "Medicamento Alfa (ficticio)", "dosagem_texto": "1 comprimido", "dosagem_status": "legivel"}]}},
    })
    assert r.status_code == 201, r.text
    assert fake.objetos[chave_resultado] == original
    assert [c for c in fake.objetos if c.startswith("revisoes/DOC-005/")]
    consulta = cliente.get("/v1/triagens/DOC-005").json()
    assert consulta["revisao_humana"]["acao"] == "corrigir"
    assert consulta["dados_extraidos"]["medicamentos"][0]["dosagem_texto"] is None
    pendentes = cliente.get("/v1/triagens", params={"status": "aguardando_auditoria"}).json()
    assert all(d["revisao_humana"] for d in pendentes if d["documento_id"] == "DOC-005")


def test_revisao_invalida_e_documento_inexistente(ambiente):
    cliente, fake, _ = ambiente
    processar(cliente, "DOC-002")
    r = cliente.post("/v1/triagens/DOC-002/revisao", json={"acao": "rejeitar", "revisor": "Auditor"})
    assert r.status_code == 422
    r = cliente.post("/v1/triagens/DOC-999/revisao", json={"acao": "aprovar", "revisor": "Auditor"})
    assert r.status_code == 404
    assert not any(c.startswith("revisoes/") for c in fake.objetos)


def test_revisao_h16_bloqueada_sem_autorizacao(ambiente, monkeypatch):
    cliente, fake, _ = ambiente
    monkeypatch.setenv("MEDIFLOW_OCI_REAL_ACK", "nao")
    assert cliente.get("/v1/triagens").status_code == 403
    r = cliente.post("/v1/triagens/DOC-001/revisao", json={"acao": "aprovar", "revisor": "Auditor"})
    assert r.status_code == 403
    assert not fake.objetos


def test_estado_h16_informa_revisao_sem_autenticacao(ambiente):
    cliente, _, _ = ambiente
    assert "sem_autenticacao" in cliente.get("/h16/estado").json()["revisao_humana"]


def test_app_principal_continua_sem_revisao():
    assert not any(getattr(r, "path", "").endswith("/revisao") for r in app_principal.routes)


def test_interface_reconhece_o_modo_h16():
    from mediflow.ui.config import SIMULATED_MODES, STATUS_ENDPOINTS
    assert STATUS_ENDPOINTS["/h16/estado"] == "H16 (Gemini + OCI real)"
    assert STATUS_ENDPOINTS["/h16/estado"] not in SIMULATED_MODES


def test_h16_reprocessamento_nao_herda_revisao(ambiente):
    cliente, fake, _ = ambiente

    primeira = processar(cliente, "DOC-002")
    chave_a = primeira["armazenamento_oci"]["chave_resultado"]

    revisao = cliente.post(
        "/v1/triagens/DOC-002/revisao",
        json={
            "acao": "aprovar",
            "revisor": "Auditor Sintetico",
            "comentario": "Primeira execucao",
        },
    )
    assert revisao.status_code == 201, revisao.text
    assert (
        revisao.json()["revisao_humana"]["chave_resultado"]
        == chave_a
    )

    segunda = processar(cliente, "DOC-002")
    chave_b = segunda["armazenamento_oci"]["chave_resultado"]

    assert chave_a != chave_b

    consulta = cliente.get("/v1/triagens/DOC-002")
    assert consulta.status_code == 200, consulta.text
    assert (
        consulta.json()["armazenamento_oci"]["chave_resultado"]
        == chave_b
    )
    assert consulta.json()["revisao_humana"] is None

    assert len([
        chave for chave in fake.objetos
        if chave.startswith("revisoes/DOC-002/")
    ]) == 1
