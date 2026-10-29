"""Testes da ingestão HTTP sem OCI e sem documentos de pacientes reais."""
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from mediflow.api.app import app
from mediflow.api.uploads import armazenamento, MAX_FILE_BYTES

RAIZ = Path(__file__).resolve().parents[1]
PDF = (RAIZ / "amostras/pdf/DOC-001_laudo_laboratorial_rotina.pdf").read_bytes()
PNG = (RAIZ / "amostras/imagens/DOC-005_receita_ilegivel.png").read_bytes()


class StorageFake:
    def __init__(self, fail=False, invalid_hash=False, fail_manifest=False, invalid_manifest_hash=False):
        self.bucket = "bucket-teste"
        self.documentos = {}
        self.fail = fail
        self.invalid_hash = invalid_hash
        self.fail_manifest = fail_manifest
        self.invalid_manifest_hash = invalid_manifest_hash

    def upload_bytes(self, name, content, content_type="application/octet-stream"):
        import hashlib
        if self.fail or (self.fail_manifest and name.startswith("metadados/")):
            raise RuntimeError("Chave privada de teste (NUNCA EXIBIR)")
        self.documentos[name] = (content, content_type)
        if self.invalid_hash and name.startswith("originais/"):
            return "0" * 64
        if self.invalid_manifest_hash and name.startswith("metadados/"):
            return "0" * 64
        return hashlib.sha256(content).hexdigest()

    def download_bytes(self, name):
        if name not in self.documentos:
            exc = LookupError("Objeto não encontrado")
            exc.status = 404
            raise exc
        return self.documentos[name][0]

    def listar_chaves(self, prefixo, *, inicio=None, limite=20):
        if getattr(self, "fail_listagem", False):
            raise RuntimeError("Chave privada de teste (NUNCA EXIBIR)")
        nomes = sorted(nome for nome in self.documentos if nome.startswith(prefixo))
        if inicio is not None:
            nomes = [nome for nome in nomes if nome >= inicio]
        proximo = nomes[limite] if len(nomes) > limite else None
        return nomes[:limite], proximo


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.setenv("MEDIFLOW_ENV", "development")
    monkeypatch.setenv("MEDIFLOW_ENABLE_LOCAL_UPLOADS", "true")
    store = StorageFake()
    app.dependency_overrides[armazenamento] = lambda: store
    try:
        yield TestClient(app), store
    finally:
        app.dependency_overrides.clear()


def enviar(client, nome="teste.pdf", conteudo=PDF, mime="application/pdf", documento_id="DOC-001", canal="teste_sintetico"):
    return client.post(
        "/v1/triagens/arquivos",
        data={"documento_id": documento_id, "canal_origem": canal},
        files={"arquivo": (nome, conteudo, mime)},
    )


def test_recebe_pdf_valido_e_retorna_recibo_sem_triagem(cliente):
    client, storage = cliente
    res = enviar(client)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["status"] == "recebido"
    assert body["triagem_executada"] is False
    assert body["documento_id"] == "DOC-001"
    assert body["entrada"]["tipo_entrada"] == "pdf"
    assert len(body["entrada"]["sha256"]) == 64
    assert body["armazenamento_original"]["status"] == "confirmado"
    assert body["armazenamento_original"]["bucket"] == "bucket-teste"
    chave = body["armazenamento_original"]["chave_original"]
    assert chave.startswith("originais/DOC-001/") and chave.endswith(".pdf")
    assert storage.documentos[chave] == (PDF, "application/pdf")
    meta = body["registro_metadados"]["chave_metadados"]
    assert meta == f'metadados/DOC-001/{body["arquivo_id"]}.json'
    assert storage.documentos[meta][1] == "application/json"
    assert body["registrado_em_utc"].endswith("Z")
    assert body["entrada"]["nome_arquivo"] == "teste.pdf"
    assert "armazenamento_oci" not in body  # O contrato completo ainda exige resultado e histórico.


def test_envia_png_real_sintetico(cliente):
    client, storage = cliente
    res = enviar(client, "imagem.png", PNG, "image/png")
    assert res.status_code == 201, res.text
    assert res.json()["entrada"]["tipo_entrada"] == "png"
    assert len(storage.documentos) == 2


def test_arquivo_vazio_rejeitado_sem_upload(cliente):
    client, storage = cliente
    res = enviar(client, conteudo=b"")
    assert res.status_code == 400
    assert not storage.documentos


def test_extensao_invalida(cliente):
    client, storage = cliente
    res = enviar(client, "arquivo.exe", PDF)
    assert res.status_code == 415
    assert not storage.documentos


def test_mime_incompativel(cliente):
    client, storage = cliente
    res = enviar(client, "arquivo.pdf", PDF, "image/png")
    assert res.status_code == 415
    assert not storage.documentos


def test_assinatura_incompativel(cliente):
    client, storage = cliente
    res = enviar(client, "arquivo.pdf", b"documento falso", "application/pdf")
    assert res.status_code == 415
    assert not storage.documentos


def test_pdf_corrompido_rejeitado(cliente):
    client, storage = cliente
    res = enviar(client, conteudo=b"%PDF-arquivo-falso-sem-estrutura")
    assert res.status_code == 422
    assert not storage.documentos


def test_png_corrompido_rejeitado(cliente):
    client, storage = cliente
    res = enviar(client, "imagem.png", b"\x89PNG\r\n\x1a\n" + b"corrupcao", "image/png")
    assert res.status_code == 422
    assert not storage.documentos


def test_pdf_acima_de_dez_paginas(cliente):
    client, storage = cliente
    writer = PdfWriter()
    for _ in range(11):
        writer.add_blank_page(width=100, height=100)
    buf = BytesIO()
    writer.write(buf)
    res = enviar(client, conteudo=buf.getvalue())
    assert res.status_code == 413
    assert not storage.documentos


def test_limite_bytes(cliente):
    client, storage = cliente
    res = enviar(client, "imagem.png", b"\x89PNG\r\n\x1a\n" + b"X" * MAX_FILE_BYTES, "image/png")
    assert res.status_code == 413
    assert not storage.documentos


def test_documento_id_invalido(cliente):
    client, storage = cliente
    res = enviar(client, documento_id="../../segredo")
    assert res.status_code == 422
    assert not storage.documentos


def test_nome_sanitizado_na_resposta(cliente):
    client, storage = cliente
    res = enviar(client, nome="C:\\Uploads\\DOC-001.pdf")
    assert res.status_code == 201, res.text
    assert res.json()["entrada"]["nome_arquivo"] == "DOC-001.pdf"


def test_sem_permissao_local_bloqueia(monkeypatch):
    monkeypatch.delenv("MEDIFLOW_ENABLE_LOCAL_UPLOADS", raising=False)
    monkeypatch.setenv("MEDIFLOW_ENV", "development")
    res = enviar(TestClient(app))
    assert res.status_code == 403
    assert res.json()["detail"]["codigo"] == "UPLOAD_DESABILITADO"


def test_ambiente_nao_desenvolvimento_bloqueia(monkeypatch):
    monkeypatch.setenv("MEDIFLOW_ENABLE_LOCAL_UPLOADS", "true")
    monkeypatch.setenv("MEDIFLOW_ENV", "production")
    res = enviar(TestClient(app))
    assert res.status_code == 403


def test_erro_oci_nao_retorna_segredos(cliente):
    client, _ = cliente
    app.dependency_overrides[armazenamento] = lambda: StorageFake(fail=True)
    res = enviar(client)
    assert res.status_code == 502
    assert "Chave privada" not in res.text
    assert res.json()["detail"]["codigo"] == "FALHA_UPLOAD"


def test_hash_incorreto_nao_retorna_confirmado(cliente):
    client, _ = cliente
    app.dependency_overrides[armazenamento] = lambda: StorageFake(invalid_hash=True)
    res = enviar(client)
    assert res.status_code == 502
    assert res.json()["detail"]["codigo"] == "HASH_INCONSISTENTE"


def test_endpoint_documentado_no_openapi(cliente):
    client, _ = cliente
    doc = client.get("/openapi.json").json()
    assert "/v1/triagens/arquivos" in doc["paths"]
    types = doc["paths"]["/v1/triagens/arquivos"]["post"]["responses"]
    assert "201" in types


def test_entrada_texto_preservada(cliente):
    client, _ = cliente
    res = client.post("/v1/triagens/texto", json={
        "documento_id": "DOC-001", "canal_origem": "teste", "documento_texto": "sintetico"
    })
    assert res.status_code == 501


def test_jpeg_valido(cliente):
    from PIL import Image
    client, storage = cliente
    image = Image.new("RGB", (16, 16), color="white")
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    res = enviar(client, "foto.jpeg", buffer.getvalue(), "image/jpeg")
    assert res.status_code == 201, res.text
    assert res.json()["entrada"]["tipo_entrada"] == "jpeg"
    assert len(storage.documentos) == 2


def test_storage_sem_config_retorna_503_seguro(cliente, monkeypatch):
    from mediflow.api.uploads import armazenamento
    client, _ = cliente
    app.dependency_overrides.pop(armazenamento, None)
    monkeypatch.delenv("OCI_BUCKET", raising=False)
    res = enviar(client)
    assert res.status_code == 503
    assert res.json()["detail"]["codigo"] == "ARMAZENAMENTO_INDISPONIVEL"


def test_associacao_nome_original_e_chave_oci_persistida(cliente):
    import json
    client, storage = cliente
    res = enviar(client, nome=r"C:\Docs\laudo-final.pdf")
    assert res.status_code == 201, res.text
    body = res.json()
    registro = body["registro_metadados"]["chave_metadados"]
    registro_bytes, mime = storage.documentos[registro]
    assert mime == "application/json"
    manifest = json.loads(registro_bytes)
    assert manifest == body
    assert manifest["entrada"]["nome_arquivo"] == "laudo-final.pdf"
    assert manifest["entrada"]["sha256"] == __import__("hashlib").sha256(PDF).hexdigest()
    assert storage.documentos[manifest["armazenamento_original"]["chave_original"]][0] == PDF


def test_consulta_registro_apos_upload_nova_requisicao(cliente):
    client, storage = cliente
    envio = enviar(client)
    assert envio.status_code == 201
    registro = envio.json()
    resultado = client.get(
        f'/v1/triagens/arquivos/{registro["documento_id"]}/{registro["arquivo_id"]}'
    )
    assert resultado.status_code == 200, resultado.text
    assert resultado.json() == registro
    assert len(storage.documentos) == 2


def test_do_is_uploads_mesmo_documento_nao_sobrescrevem(cliente):
    client, storage = cliente
    primeira = enviar(client)
    segunda = enviar(client)
    assert primeira.status_code == segunda.status_code == 201
    a, b = primeira.json(), segunda.json()
    assert a["arquivo_id"] != b["arquivo_id"]
    assert a["armazenamento_original"]["chave_original"] != b["armazenamento_original"]["chave_original"]
    assert a["registro_metadados"]["chave_metadados"] != b["registro_metadados"]["chave_metadados"]
    assert len(storage.documentos) == 4
    for recibo in (a, b):
        resp = client.get(f'/v1/triagens/arquivos/DOC-001/{recibo["arquivo_id"]}')
        assert resp.status_code == 200
        assert resp.json() == recibo


def test_falha_ao_gravar_manifesto_retorna_erro_sem_confirmacao(cliente):
    client, _ = cliente
    storage = StorageFake(fail_manifest=True)
    app.dependency_overrides[armazenamento] = lambda: storage
    res = enviar(client)
    assert res.status_code == 502
    assert res.json()["detail"]["codigo"] == "FALHA_REGISTRO_METADADOS"
    assert "Chave privada" not in res.text
    assert len(storage.documentos) == 1  # Original órfão: requer conciliação, não sucesso falso.
    assert next(iter(storage.documentos)).startswith("originais/")


def test_hash_incorreto_do_manifesto_retorna_erro(cliente):
    client, _ = cliente
    storage = StorageFake(invalid_manifest_hash=True)
    app.dependency_overrides[armazenamento] = lambda: storage
    res = enviar(client)
    assert res.status_code == 502
    assert res.json()["detail"]["codigo"] == "HASH_METADADOS_INCONSISTENTE"


def test_manifesto_inexistente_retorna_404(cliente):
    client, _ = cliente
    res = client.get('/v1/triagens/arquivos/DOC-001/' + 'a'*32)
    assert res.status_code == 404
    assert res.json()["detail"]["codigo"] == "REGISTRO_NAO_ENCONTRADO"


def test_consulta_manifesto_desabilitada_fora_do_dev(cliente, monkeypatch):
    client, _ = cliente
    monkeypatch.setenv('MEDIFLOW_ENABLE_LOCAL_UPLOADS', 'false')
    res = client.get('/v1/triagens/arquivos/DOC-001/' + 'a'*32)
    assert res.status_code == 403


def test_manifesto_corrompido_retorna_502_sem_vazar_conteudo(cliente):
    client, storage = cliente
    envio = enviar(client)
    assert envio.status_code == 201
    registro = envio.json()
    chave = registro['registro_metadados']['chave_metadados']
    storage.documentos[chave] = (b'{"segredo": "NAO_EXIBIR"}', 'application/json')
    res = client.get(f'/v1/triagens/arquivos/DOC-001/{registro["arquivo_id"]}')
    assert res.status_code == 502
    assert res.json()['detail']['codigo'] == 'REGISTRO_INVALIDO'
    assert 'NAO_EXIBIR' not in res.text


def test_manifesto_com_documento_trocado_retorna_502(cliente):
    import json
    client, storage = cliente
    envio = enviar(client)
    assert envio.status_code == 201
    registro = envio.json()
    chave = registro['registro_metadados']['chave_metadados']
    persistido = json.loads(storage.documentos[chave][0])
    persistido['documento_id'] = 'DOC-OUTRO'
    storage.documentos[chave] = (json.dumps(persistido).encode(), 'application/json')
    res = client.get(f'/v1/triagens/arquivos/DOC-001/{registro["arquivo_id"]}')
    assert res.status_code == 502
    assert res.json()['detail']['codigo'] == 'REGISTRO_INCONSISTENTE'


def test_consulta_id_invalido_nao_aciona_storage(cliente):
    client, storage = cliente
    res = client.get('/v1/triagens/arquivos/DOC-001/../../abc')
    assert res.status_code in (404, 422)
    assert storage.documentos == {}
    res = client.get('/v1/triagens/arquivos/DOC-001/nao-e-uuid')
    assert res.status_code == 422


def test_manifesto_dados_de_resposta_nao_afirmam_triagem(cliente):
    client, _ = cliente
    res = enviar(client)
    assert res.status_code == 201
    registro = res.json()
    assert registro['triagem_executada'] is False
    assert registro['status'] == 'recebido'
    assert 'armazenamento_oci' not in registro
    assert 'decisao_roteamento' not in registro


# Listagem de manifestos por documento_id — sem banco de dados e sem OCI real.
def test_listagem_vazia_retorna_pagina_vazia(cliente):
    client, _ = cliente
    res = client.get("/v1/triagens/arquivos/DOC-001")
    assert res.status_code == 200, res.text
    assert res.json() == {
        "documento_id": "DOC-001", "quantidade_pagina": 0,
        "arquivos": [], "proximo_cursor": None,
    }


def test_lista_varios_arquivos_do_documento_sem_misturar_outros(cliente):
    client, storage = cliente
    a = enviar(client, nome="laudo.pdf").json()
    b = enviar(client, nome="receita.png", conteudo=PNG, mime="image/png").json()
    c = enviar(client, nome="outro.pdf", documento_id="DOC-002").json()
    res = client.get("/v1/triagens/arquivos/DOC-001")
    assert res.status_code == 200, res.text
    d = res.json()
    assert d["documento_id"] == "DOC-001"
    assert d["quantidade_pagina"] == 2
    assert d["proximo_cursor"] is None
    assert {x["arquivo_id"] for x in d["arquivos"]} == {a["arquivo_id"], b["arquivo_id"]}
    assert {x["nome_original"] for x in d["arquivos"]} == {"laudo.pdf", "receita.png"}
    assert c["arquivo_id"] not in {x["arquivo_id"] for x in d["arquivos"]}
    assert all(x["sha256"] and x["tamanho_bytes"] > 0 for x in d["arquivos"])
    assert len(storage.documentos) == 6


def test_paginar_sem_perder_arquivos_ou_duplicar(cliente):
    client, _ = cliente
    ids = {enviar(client).json()["arquivo_id"] for _ in range(5)}
    cursor = None
    coletados = []
    for pagina in range(3):
        params = {"limite": 2}
        if cursor:
            params["cursor"] = cursor
        res = client.get("/v1/triagens/arquivos/DOC-001", params=params)
        assert res.status_code == 200, res.text
        dados = res.json()
        assert dados["quantidade_pagina"] == (1 if pagina == 2 else 2)
        coletados += [x["arquivo_id"] for x in dados["arquivos"]]
        cursor = dados["proximo_cursor"]
        assert bool(cursor) == (pagina != 2)
    assert len(set(coletados)) == 5
    assert set(coletados) == ids


@pytest.mark.parametrize("params", [{"limite": 0}, {"limite": 51}, {"limite": -1}, {"limite": "abc"}])
def test_listagem_rejeita_limite_invalido(cliente, params):
    client, _ = cliente
    assert client.get("/v1/triagens/arquivos/DOC-001", params=params).status_code == 422


@pytest.mark.parametrize("cursor", ["metadados/DOC-002/" + "a" * 32 + ".json", "../../outro", "metadados/DOC-001/errado.json"])
def test_listagem_rejeita_cursor_de_outro_documento_ou_malformado(cliente, cursor):
    client, _ = cliente
    res = client.get("/v1/triagens/arquivos/DOC-001", params={"cursor": cursor})
    assert res.status_code == 422
    assert res.json()["detail"]["codigo"] == "CURSOR_INVALIDO"


def test_listagem_protegida_pelo_portao_local(cliente, monkeypatch):
    client, _ = cliente
    monkeypatch.setenv("MEDIFLOW_ENABLE_LOCAL_UPLOADS", "false")
    res = client.get("/v1/triagens/arquivos/DOC-001")
    assert res.status_code == 403


def test_listagem_falha_oci_nao_expoe_segredos(cliente):
    client, storage = cliente
    storage.fail_listagem = True
    res = client.get("/v1/triagens/arquivos/DOC-001")
    assert res.status_code == 502
    assert res.json()["detail"]["codigo"] == "FALHA_LISTAGEM_METADADOS"
    assert "Chave privada" not in res.text


def test_manifesto_corrompido_falha_a_pagina_inteira(cliente):
    client, storage = cliente
    envio = enviar(client).json()
    chave = envio["registro_metadados"]["chave_metadados"]
    storage.documentos[chave] = (b"not json", "application/json")
    res = client.get("/v1/triagens/arquivos/DOC-001")
    assert res.status_code == 502
    assert res.json()["detail"]["codigo"] == "REGISTRO_INVALIDO"
    assert "not json" not in res.text


def test_listagem_registro_com_id_incorreto_retorna_erro(cliente):
    client, storage = cliente
    envio = enviar(client).json()
    chave = envio["registro_metadados"]["chave_metadados"]
    import json
    doc = json.loads(storage.documentos[chave][0])
    doc["arquivo_id"] = "0" * 32
    storage.documentos[chave] = (json.dumps(doc).encode(), "application/json")
    res = client.get("/v1/triagens/arquivos/DOC-001")
    assert res.status_code == 502
    assert res.json()["detail"]["codigo"] == "REGISTRO_INCONSISTENTE"


def test_listagem_chave_fora_do_padrao_retorna_502(cliente):
    client, storage = cliente
    storage.documentos["metadados/DOC-001/arquivo-indevido.txt"] = (b"{}", "application/json")
    res = client.get("/v1/triagens/arquivos/DOC-001")
    assert res.status_code == 502
    assert res.json()["detail"]["codigo"] == "LISTAGEM_INCONSISTENTE"


def test_listagem_eh_exibida_no_swagger(cliente):
    client, _ = cliente
    urls = client.get("/openapi.json").json()["paths"]
    assert "/v1/triagens/arquivos/{documento_id}" in urls
    assert "get" in urls["/v1/triagens/arquivos/{documento_id}"]


def test_manifesto_removido_entre_listagem_e_leitura(cliente):
    client, storage = cliente
    enviado = enviar(client).json()
    chave = enviado["registro_metadados"]["chave_metadados"]
    original = storage.download_bytes

    def simular_remocao(nome):
        if nome == chave:
            exc = LookupError("Manifesto sumiu durante listagem")
            exc.status = 404
            raise exc
        return original(nome)

    storage.download_bytes = simular_remocao
    resposta = client.get("/v1/triagens/arquivos/DOC-001")
    assert resposta.status_code == 502
    assert resposta.json()["detail"]["codigo"] == "LISTAGEM_INCONSISTENTE"
