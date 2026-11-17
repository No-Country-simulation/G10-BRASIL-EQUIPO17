"""H10: falhas parciais OCI (simuladas) devem impedir sucesso no I1.

Usa exclusivamente FakeOCI e fixtures sinteticas ja presentes no projeto.
Nenhuma credencial e lida, nenhum objeto real e criado ou apagado.
"""

from types import SimpleNamespace

import pytest

from mediflow.api.triage_service import FalhaOrquestracao
from test_triage_persistence_adapter import criar_servico, preparar

SEGREDO_SIMULADO = "CREDENCIAL_OCI_NAO_EXIBIR_H10"
EXECUCAO_FIXA = "e" * 32


def _executar_com_falha(storage, recibo, documento):
    """Confere que a excecao publica e sanitizada, sem retorno de sucesso."""
    with pytest.raises(FalhaOrquestracao) as capturada:
        criar_servico(storage, recibo).executar(
            documento, canal_origem=recibo.entrada.canal_origem
        )
    assert capturada.value.codigo == "PERSISTENCIA_INDISPONIVEL"
    assert capturada.value.etapa == "persistencia"
    assert SEGREDO_SIMULADO not in str(capturada.value)


def _originais_preservados(fake, snapshot):
    """Falhas nao podem alterar nem excluir original ou manifesto existentes."""
    for chave, conteudo in snapshot.items():
        assert fake.objetos[chave] == conteudo


@pytest.mark.parametrize(
    "prefixo,quantidade",
    [("historicos/", 1), ("resultados/", 2)],
    ids=["ack-perdido-historico", "ack-perdido-resultado"],
)
def test_h10_timeout_apos_gravacao_nao_confirma(monkeypatch, prefixo, quantidade):
    """OCI pode gravar o objeto e a resposta ao cliente se perder."""
    fake, storage, recibo, documento = preparar()
    snapshot = dict(fake.objetos)
    gravar_original = fake.put_object

    def gravar_e_perder_resposta(namespace, bucket, nome, conteudo, **kwargs):
        gravar_original(namespace, bucket, nome, conteudo, **kwargs)
        if nome.startswith(prefixo):
            raise TimeoutError(SEGREDO_SIMULADO)

    monkeypatch.setattr(fake, "put_object", gravar_e_perder_resposta)
    _executar_com_falha(storage, recibo, documento)
    assert len(fake.gravacoes) == quantidade
    assert fake.gravacoes[0].startswith("historicos/")
    if quantidade == 2:
        assert fake.gravacoes[1].startswith("resultados/")
    _originais_preservados(fake, snapshot)


@pytest.mark.parametrize(
    "prefixo,quantidade",
    [("historicos/", 1), ("resultados/", 2)],
    ids=["falha-leitura-historico", "falha-leitura-resultado"],
)
def test_h10_erro_leitura_confirmacao_nao_confirma(monkeypatch, prefixo, quantidade):
    """Um upload aceito nao basta: leitura e integridade sao obrigatorias."""
    fake, storage, recibo, documento = preparar()
    snapshot = dict(fake.objetos)
    leitura_original = fake.get_object

    def falha_na_leitura(namespace, bucket, nome):
        if nome.startswith(prefixo):
            raise TimeoutError(SEGREDO_SIMULADO)
        return leitura_original(namespace, bucket, nome)

    monkeypatch.setattr(fake, "get_object", falha_na_leitura)
    _executar_com_falha(storage, recibo, documento)
    assert len(fake.gravacoes) == quantidade
    _originais_preservados(fake, snapshot)


@pytest.mark.parametrize(
    "prefixo,quantidade",
    [("historicos/", 1), ("resultados/", 2)],
    ids=["hash-historico-divergente", "hash-resultado-divergente"],
)
def test_h10_hash_upload_divergente_nao_confirma(monkeypatch, prefixo, quantidade):
    """Mesmo com conteudo gravado, um hash inesperado impede confirmacao."""
    fake, storage, recibo, documento = preparar()
    snapshot = dict(fake.objetos)
    upload_original = storage.upload_bytes_if_absent

    def upload_com_hash_errado(nome, conteudo, content_type="application/octet-stream"):
        digest = upload_original(nome, conteudo, content_type=content_type)
        return "0" * 64 if nome.startswith(prefixo) else digest

    monkeypatch.setattr(storage, "upload_bytes_if_absent", upload_com_hash_errado)
    _executar_com_falha(storage, recibo, documento)
    assert len(fake.gravacoes) == quantidade
    _originais_preservados(fake, snapshot)


@pytest.mark.parametrize(
    "prefixo,quantidade",
    [("historicos/", 1), ("resultados/", 2)],
    ids=["historico-corrompido", "resultado-corrompido"],
)
def test_h10_leitura_corrompida_nao_confirma(prefixo, quantidade):
    """Bytes divergentes no download nao podem ser aceitos como gravacao valida."""
    fake, storage, recibo, documento = preparar()
    snapshot = dict(fake.objetos)
    fake.corromper_prefixo = prefixo
    _executar_com_falha(storage, recibo, documento)
    assert len(fake.gravacoes) == quantidade
    _originais_preservados(fake, snapshot)


def test_h10_original_indisponivel_nao_produz_escritas(monkeypatch):
    """Sem verificar o original, nem historico nem resultado devem ser criados."""
    fake, storage, recibo, documento = preparar()
    snapshot = dict(fake.objetos)
    leitura_original = fake.get_object

    def erro_original(namespace, bucket, nome):
        if nome.startswith("originais/"):
            raise TimeoutError(SEGREDO_SIMULADO)
        return leitura_original(namespace, bucket, nome)

    monkeypatch.setattr(fake, "get_object", erro_original)
    _executar_com_falha(storage, recibo, documento)
    assert fake.gravacoes == []
    assert fake.objetos == snapshot


def test_h10_repeticao_mesma_execucao_parcial_nao_repara_nem_sobrescreve(monkeypatch):
    """Reprocessamento com mesma ID nao e reconciliacao nem transacao atomica."""
    fake, storage, recibo, documento = preparar()
    monkeypatch.setattr(
        "mediflow.storage.triage_persistence.uuid4",
        lambda: SimpleNamespace(hex=EXECUCAO_FIXA),
    )
    fake.falhar_prefixo = "resultados/"
    _executar_com_falha(storage, recibo, documento)
    assert len(fake.gravacoes) == 1
    assert fake.gravacoes[0].endswith(f"/{EXECUCAO_FIXA}.json")
    snapshot = dict(fake.objetos)

    fake.falhar_prefixo = None
    _executar_com_falha(storage, recibo, documento)
    assert len(fake.gravacoes) == 1
    assert fake.objetos == snapshot
