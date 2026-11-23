"""Consulta de triagens e revisao humana na demonstracao local (fixture + FakeOCI)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mediflow.api.app import app as app_principal
from mediflow.api.app_demo_local import app, cliente_fakeoci
from mediflow_contracts.models import ResultadoTriagem

RAIZ = Path(__file__).resolve().parents[1]
ARQUIVOS = {
    "DOC-001": ("amostras/pdf/DOC-001_laudo_laboratorial_rotina.pdf", "application/pdf"),
    "DOC-002": ("amostras/pdf/DOC-002_laudo_imagem_alerta.pdf", "application/pdf"),
    "DOC-005": ("amostras/imagens/DOC-005_receita_ilegivel.png", "image/png"),
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


def processar(c, doc_id):
    relativo, mime = ARQUIVOS[doc_id]
    arquivo = RAIZ / relativo
    r = c.post(
        "/v1/triagens/arquivos",
        data={"documento_id": doc_id, "canal_origem": "demo_local"},
        files={"arquivo": (arquivo.name, arquivo.read_bytes(), mime)},
    )
    assert r.status_code == 201, r.text
    recibo = r.json()
    r = c.post(f"/v1/triagens/arquivos/{doc_id}/{recibo['arquivo_id']}/processar")
    assert r.status_code == 200, r.text
    return r.json()


def revisar(c, doc_id, **payload):
    corpo = {"acao": "aprovar", "revisor": "Auditora Sintetica", **payload}
    return c.post(f"/v1/triagens/{doc_id}/revisao", json=corpo)


def test_listagem_vazia(cliente):
    r = cliente.get("/v1/triagens")
    assert r.status_code == 200
    assert r.json() == []


def test_lista_e_filtra_triagens_processadas(cliente):
    for doc_id in ARQUIVOS:
        processar(cliente, doc_id)

    todos = cliente.get("/v1/triagens").json()
    assert [d["documento_id"] for d in todos] == ["DOC-001", "DOC-002", "DOC-005"]
    for d in todos:
        assert d["revisao_humana"] is None
        assert d["recebido_em"]
        ResultadoTriagem.model_validate({k: v for k, v in d.items() if k not in {"revisao_humana", "recebido_em"}})

    fila = cliente.get("/v1/triagens", params={"status": "aguardando_auditoria"}).json()
    assert {d["documento_id"] for d in fila} == {"DOC-002", "DOC-005"}

    assert cliente.get("/v1/triagens", params={"status": "invalido"}).status_code == 422


def test_consulta_documento(cliente):
    processar(cliente, "DOC-005")
    r = cliente.get("/v1/triagens/DOC-005")
    assert r.status_code == 200
    assert r.json()["decisao_roteamento"]["regra_principal"] == "R002"
    assert cliente.get("/v1/triagens/DOC-999").status_code == 404
    assert cliente.get("/v1/triagens/..%2Foriginais").status_code in {404, 422}


def test_aprovacao_registrada_sem_alterar_resultado(cliente):
    resultado = processar(cliente, "DOC-005")
    chave_resultado = resultado["armazenamento_oci"]["chave_resultado"]
    original = cliente_fakeoci.objetos[chave_resultado]

    r = revisar(cliente, "DOC-005", comentario="  conferido  ")
    assert r.status_code == 201, r.text
    revisao = r.json()["revisao_humana"]
    assert revisao["acao"] == "aprovar"
    assert revisao["revisor"] == "Auditora Sintetica"
    assert revisao["comentario"] == "conferido"
    assert revisao["chave_resultado"] == chave_resultado
    assert revisao["revisado_em"].endswith("Z")

    assert cliente_fakeoci.objetos[chave_resultado] == original
    chaves = [c for c in cliente_fakeoci.objetos if c.startswith("revisoes/DOC-005/")]
    assert len(chaves) == 1
    assert json.loads(cliente_fakeoci.objetos[chaves[0]])["revisao_id"] == revisao["revisao_id"]

    assert cliente.get("/v1/triagens/DOC-005").json()["revisao_humana"]["revisao_id"] == revisao["revisao_id"]


def test_ultima_revisao_prevalece(cliente):
    processar(cliente, "DOC-002")
    revisar(cliente, "DOC-002")
    correcao = {"decisao_roteamento": {"destino_principal": "auditoria_humana"}}
    r = revisar(cliente, "DOC-002", acao="corrigir", correcoes=correcao)
    assert r.status_code == 201, r.text

    atual = cliente.get("/v1/triagens/DOC-002").json()
    assert atual["revisao_humana"]["acao"] == "corrigir"
    assert atual["revisao_humana"]["correcoes"] == correcao
    assert atual["decisao_roteamento"]["destino_principal"] == "fila_prioritaria_avaliacao_humana"
    assert len([c for c in cliente_fakeoci.objetos if c.startswith("revisoes/DOC-002/")]) == 2


def test_ultima_revisao_prevalece_com_relogio_parado(cliente, monkeypatch):
    """No Windows o relogio repete valores; revisoes no mesmo instante nao podem empatar."""
    from datetime import datetime, timezone

    import mediflow.api.triage_review as modulo

    instante = datetime(2026, 11, 18, 12, 0, 0, tzinfo=timezone.utc)

    class RelogioParado(datetime):
        @classmethod
        def now(cls, tz=None):
            return instante

    processar(cliente, "DOC-002")
    monkeypatch.setattr(modulo, "datetime", RelogioParado)
    for acao in ("aprovar", "rejeitar", "aprovar", "rejeitar", "aprovar"):
        extra = {"comentario": "motivo sintetico"} if acao == "rejeitar" else {}
        assert revisar(cliente, "DOC-002", acao=acao, **extra).status_code == 201
        assert cliente.get("/v1/triagens/DOC-002").json()["revisao_humana"]["acao"] == acao

    chaves = sorted(c for c in cliente_fakeoci.objetos if c.startswith("revisoes/DOC-002/"))
    assert len({c.rsplit("/", 1)[1][:22] for c in chaves}) == 5


@pytest.mark.parametrize(
    "payload",
    [
        {"acao": "rejeitar"},
        {"acao": "corrigir"},
        {"acao": "aprovar", "correcoes": {"classificacao": {"tipo_documento": "receita"}}},
        {"acao": "corrigir", "correcoes": {"armazenamento_oci": {"status": "confirmado"}}},
        {"acao": "apagar"},
        {"revisor": "   "},
        {"campo_extra": True},
    ],
)
def test_revisao_invalida_rejeitada(cliente, payload):
    processar(cliente, "DOC-005")
    assert revisar(cliente, "DOC-005", **payload).status_code == 422
    assert not [c for c in cliente_fakeoci.objetos if c.startswith("revisoes/")]


def test_revisao_exige_documento_processado_e_pendente(cliente):
    assert revisar(cliente, "DOC-005").status_code == 404
    processar(cliente, "DOC-001")
    r = revisar(cliente, "DOC-001")
    assert r.status_code == 409
    assert r.json()["detail"]["codigo"] == "REVISAO_NAO_REQUERIDA"


def test_falha_de_armazenamento_nao_vaza_detalhes(cliente):
    processar(cliente, "DOC-005")
    cliente_fakeoci.falhar_prefixo = "revisoes/"
    r = revisar(cliente, "DOC-005")
    assert r.status_code == 502
    assert r.json()["detail"]["codigo"] == "REVISAO_NAO_PERSISTIDA"
    assert "FAKEOCI" not in r.text


def test_rotas_bloqueadas_sem_flags(cliente, monkeypatch):
    monkeypatch.setenv("MEDIFLOW_ENABLE_LOCAL_TRIAGE", "false")
    assert cliente.get("/v1/triagens").status_code == 403
    assert revisar(cliente, "DOC-005").status_code == 403


def test_api_principal_nao_expoe_revisao():
    with TestClient(app_principal) as c:
        assert c.get("/v1/triagens").status_code in {404, 405}
        assert c.post("/v1/triagens/DOC-005/revisao", json={}).status_code in {404, 405}


@pytest.mark.parametrize(
    ("doc_id", "prefixo"),
    [
        ("DOC-001", "processados/"),
        ("DOC-005", "auditoria_humana/"),
    ],
)
def test_resultado_sem_indice_nao_e_consultavel(
    cliente, doc_id, prefixo
):
    relativo, mime = ARQUIVOS[doc_id]
    arquivo = RAIZ / relativo

    upload = cliente.post(
        "/v1/triagens/arquivos",
        data={
            "documento_id": doc_id,
            "canal_origem": "demo_local",
        },
        files={
            "arquivo": (
                arquivo.name,
                arquivo.read_bytes(),
                mime,
            )
        },
    )

    assert upload.status_code == 201
    recibo = upload.json()

    cliente_fakeoci.falhar_prefixo = prefixo

    resposta = cliente.post(
        f"/v1/triagens/arquivos/{doc_id}/"
        f"{recibo['arquivo_id']}/processar"
    )

    assert resposta.status_code == 502
    assert any(
        k.startswith("resultados/")
        for k in cliente_fakeoci.objetos
    )
    assert not any(
        k.startswith(prefixo)
        for k in cliente_fakeoci.objetos
    )

    assert cliente.get("/v1/triagens").json() == []
    assert cliente.get(
        f"/v1/triagens/{doc_id}"
    ).status_code == 404

    if doc_id == "DOC-005":
        assert revisar(
            cliente, doc_id
        ).status_code == 404


def test_indice_incoerente_bloqueia_consulta(cliente):
    processar(cliente, "DOC-005")

    chave = next(
        k for k in cliente_fakeoci.objetos
        if k.startswith("auditoria_humana/")
    )

    indice = json.loads(cliente_fakeoci.objetos[chave])
    indice["chave_resultado"] = "resultado-inexistente"
    cliente_fakeoci.objetos[chave] = json.dumps(
        indice
    ).encode("utf-8")

    assert cliente.get("/v1/triagens").json() == []
    assert cliente.get(
        "/v1/triagens/DOC-005"
    ).status_code == 404


def test_resultado_h16_legado_continua_consultavel(cliente):
    resultado = processar(cliente, "DOC-001")
    chave_historico = (
        resultado["armazenamento_oci"]["chave_historico"]
    )

    historico = json.loads(
        cliente_fakeoci.objetos[chave_historico]
    )
    assert "chave_indice_status" in historico

    # Reconstroi exclusivamente em memoria o formato
    # utilizado antes da introducao dos indices.
    historico.pop("chave_indice_status")
    cliente_fakeoci.objetos[chave_historico] = json.dumps(
        historico
    ).encode("utf-8")

    chave_indice = next(
        k for k in cliente_fakeoci.objetos
        if k.startswith("processados/")
    )
    del cliente_fakeoci.objetos[chave_indice]

    consulta = cliente.get("/v1/triagens/DOC-001")

    assert consulta.status_code == 200
    assert consulta.json()["status"] == "processado"


@pytest.mark.parametrize(
    "prefixo",
    ["historicos/", "processados/"],
)
def test_falha_leitura_persistencia_retorna_502(
    cliente, monkeypatch, prefixo
):
    processar(cliente, "DOC-001")

    leitura_original = cliente_fakeoci.get_object

    def leitura_com_falha(namespace, bucket, nome):
        if nome.startswith(prefixo):
            raise TimeoutError("SEGREDO_OCI_SIMULADO")
        return leitura_original(namespace, bucket, nome)

    monkeypatch.setattr(
        cliente_fakeoci,
        "get_object",
        leitura_com_falha,
    )

    for endpoint in (
        "/v1/triagens",
        "/v1/triagens/DOC-001",
    ):
        resposta = cliente.get(endpoint)

        assert resposta.status_code == 502
        assert (
            resposta.json()["detail"]["codigo"]
            == "ARMAZENAMENTO_INDISPONIVEL"
        )
        assert "SEGREDO_OCI_SIMULADO" not in resposta.text


def test_reprocessamento_nao_herda_revisao_anterior(cliente):
    primeira = processar(cliente, "DOC-005")
    chave_a = primeira["armazenamento_oci"]["chave_resultado"]

    revisao_a = revisar(
        cliente,
        "DOC-005",
        comentario="Revisao sintetica da execucao A",
    )
    assert revisao_a.status_code == 201, revisao_a.text

    registro_a = revisao_a.json()["revisao_humana"]
    assert registro_a["chave_resultado"] == chave_a

    chave_revisao_a = next(
        chave
        for chave in cliente_fakeoci.objetos
        if chave.startswith("revisoes/DOC-005/")
    )
    bytes_revisao_a = cliente_fakeoci.objetos[chave_revisao_a]

    segunda = processar(cliente, "DOC-005")
    chave_b = segunda["armazenamento_oci"]["chave_resultado"]

    assert chave_a != chave_b

    consulta = cliente.get("/v1/triagens/DOC-005")
    assert consulta.status_code == 200, consulta.text

    resultado_atual = consulta.json()
    assert (
        resultado_atual["armazenamento_oci"]["chave_resultado"]
        == chave_b
    )
    assert resultado_atual["revisao_humana"] is None

    fila = cliente.get(
        "/v1/triagens",
        params={"status": "aguardando_auditoria"},
    )
    assert fila.status_code == 200

    item = next(
        doc for doc in fila.json()
        if doc["documento_id"] == "DOC-005"
    )
    assert item["revisao_humana"] is None

    revisao_b = revisar(
        cliente,
        "DOC-005",
        comentario="Revisao sintetica da execucao B",
    )
    assert revisao_b.status_code == 201, revisao_b.text
    assert (
        revisao_b.json()["revisao_humana"]["chave_resultado"]
        == chave_b
    )

    consulta_final = cliente.get("/v1/triagens/DOC-005")
    assert consulta_final.status_code == 200
    assert (
        consulta_final.json()["revisao_humana"]["chave_resultado"]
        == chave_b
    )

    assert cliente_fakeoci.objetos[chave_revisao_a] == bytes_revisao_a

    chaves_revisao = [
        chave for chave in cliente_fakeoci.objetos
        if chave.startswith("revisoes/DOC-005/")
    ]
    assert len(chaves_revisao) == 2


@pytest.mark.parametrize(
    "defeito",
    ["objeto_ausente", "objeto_corrompido", "leitura_indisponivel"],
)
def test_revisao_exige_confirmacao_apos_upload(
    cliente, monkeypatch, defeito
):
    """Nunca confirma uma revisao sem leitura integra do objeto."""
    resultado = processar(cliente, "DOC-005")
    chave_resultado = resultado["armazenamento_oci"]["chave_resultado"]
    bytes_resultado = cliente_fakeoci.objetos[chave_resultado]

    gravar_original = cliente_fakeoci.put_object
    ler_original = cliente_fakeoci.get_object

    def gravar_com_defeito(namespace, bucket, nome, dados, **kwargs):
        if nome.startswith("revisoes/"):
            if defeito == "objeto_ausente":
                # Simula sucesso sem escrita.
                return None
            if defeito == "objeto_corrompido":
                return gravar_original(
                    namespace, bucket, nome, b"{}", **kwargs
                )
        return gravar_original(
            namespace, bucket, nome, dados, **kwargs
        )

    def ler_com_defeito(namespace, bucket, nome):
        if nome.startswith("revisoes/"):
            raise TimeoutError("SEGREDO_OCI_SIMULADO")
        return ler_original(namespace, bucket, nome)

    with monkeypatch.context() as m:
        if defeito == "leitura_indisponivel":
            m.setattr(
                cliente_fakeoci, "get_object", ler_com_defeito
            )
        else:
            m.setattr(
                cliente_fakeoci, "put_object", gravar_com_defeito
            )

        resposta = revisar(cliente, "DOC-005")

    assert resposta.status_code == 502
    assert (
        resposta.json()["detail"]["codigo"]
        == "REVISAO_NAO_PERSISTIDA"
    )
    assert "SEGREDO_OCI_SIMULADO" not in resposta.text
    assert cliente_fakeoci.objetos[chave_resultado] == bytes_resultado

    revisoes = [
        chave for chave in cliente_fakeoci.objetos
        if chave.startswith("revisoes/DOC-005/")
    ]

    if defeito == "objeto_ausente":
        assert revisoes == []
        assert (
            cliente.get("/v1/triagens/DOC-005")
            .json()["revisao_humana"] is None
        )

    elif defeito == "objeto_corrompido":
        assert len(revisoes) == 1
        assert cliente_fakeoci.objetos[revisoes[0]] == b"{}"
        assert (
            cliente.get("/v1/triagens/DOC-005")
            .json()["revisao_humana"] is None
        )

    else:
        # A gravacao pode ter ocorrido, mas nao foi confirmada
        # durante a falha de leitura. Nao repetir automaticamente.
        assert len(revisoes) == 1
        consulta = cliente.get("/v1/triagens/DOC-005")
        assert consulta.status_code == 200
        assert consulta.json()["revisao_humana"]["acao"] == "aprovar"



def test_ajuste8b_rejeicao_com_alteracoes_persistidas(cliente):
    resultado = processar(cliente, "DOC-005")
    chave_resultado = resultado["armazenamento_oci"]["chave_resultado"]
    original = cliente_fakeoci.objetos[chave_resultado]
    correcoes = {
        "classificacao": {"tipo_documento": "solicitacao_exame"},
        "dados_extraidos": {"paciente": {"nome": "Paciente Sintetico Rejeitado"}},
    }

    r = revisar(
        cliente, "DOC-005", acao="rejeitar",
        comentario="Exame descartado no caso sintetico",
        correcoes=correcoes,
    )
    assert r.status_code == 201, r.text
    registro = r.json()["revisao_humana"]
    assert registro["acao"] == "rejeitar"
    assert registro["correcoes"] == correcoes
    assert cliente_fakeoci.objetos[chave_resultado] == original

    consulta = cliente.get("/v1/triagens/DOC-005")
    assert consulta.status_code == 200
    assert consulta.json()["revisao_humana"]["correcoes"] == correcoes
    assert consulta.json()["dados_extraidos"] == resultado["dados_extraidos"]
    pendentes = cliente.get("/v1/triagens", params={"status": "aguardando_auditoria"}).json()
    assert not any(d["documento_id"] == "DOC-005" and
                   d["revisao_humana"] is None for d in pendentes)
