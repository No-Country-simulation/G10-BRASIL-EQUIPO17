"""Testes isolados de persistência, sem acesso à Oracle Cloud."""
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest

from mediflow.storage.oci_storage import OCIStorage
from mediflow.storage.triage_persistence import PersistenciaIncompleta, persistir_resultado
from mediflow_contracts.models import ResultadoTriagem

RAIZ = Path(__file__).resolve().parents[1]
DADOS_ORIGINAIS = b"Documento sintetico PDF de teste"
ARQ = "a" * 32
EXECUCAO = "b" * 32
CHAVE_ORIGINAL = f"originais/DOC-001/{ARQ}.pdf"


class FakeOCI:
    def __init__(self):
        self.objetos = {CHAVE_ORIGINAL: DADOS_ORIGINAIS}
        self.falhar_prefixo = None
        self.corromper_prefixo = None
        self.gravacoes = []

    def get_object(self, namespace, bucket, name):
        valor = self.objetos[name]
        if self.corromper_prefixo and name.startswith(self.corromper_prefixo):
            valor = b"objeto corrompido"
        return SimpleNamespace(data=SimpleNamespace(content=valor))

    def put_object(self, namespace, bucket, name, content, **kwargs):
        assert kwargs["if_none_match"] == "*"
        if self.falhar_prefixo and name.startswith(self.falhar_prefixo):
            raise RuntimeError("Segredo OCI simulado")
        if name in self.objetos:
            raise RuntimeError("precondition failed")
        self.objetos[name] = content
        self.gravacoes.append(name)


def dados():
    origem = SimpleNamespace(
        documento_id="DOC-001", arquivo_id=ARQ,
        tamanho_bytes=len(DADOS_ORIGINAIS),
        entrada=SimpleNamespace(
            tipo_entrada="pdf", canal_origem="teste_sintetico",
            sha256=sha256(DADOS_ORIGINAIS).hexdigest(),
            nome_arquivo="arquivo.pdf",
        ),
        armazenamento_original=SimpleNamespace(bucket="bucket-dev", chave_original=CHAVE_ORIGINAL),
    )
    resultado = ResultadoTriagem.model_validate_json(
        (RAIZ / "exemplos/DOC-001_resultado.json").read_text(encoding="utf-8")
    )
    resultado.entrada.sha256 = origem.entrada.sha256
    resultado.entrada.nome_arquivo = origem.entrada.nome_arquivo
    return origem, resultado


def test_persiste_historico_e_resultado_com_confirmacao():
    fake = FakeOCI()
    storage = OCIStorage(fake, namespace="ns", bucket="bucket-dev")
    recibo, resultado = dados()
    retorno = persistir_resultado(storage, recibo, resultado, execucao_id=EXECUCAO)
    assert retorno.armazenamento_oci.status == "confirmado"
    assert resultado.armazenamento_oci.status == "pendente"
    assert len(fake.gravacoes) == 2
    assert fake.gravacoes[0].startswith("historicos/")
    assert fake.gravacoes[1].startswith("resultados/")
    assert ResultadoTriagem.model_validate_json(fake.objetos[fake.gravacoes[1]]) == retorno


def test_original_corrompido_impede_qualquer_gravacao():
    fake = FakeOCI()
    fake.objetos[CHAVE_ORIGINAL] = b"conteudo incorreto"
    storage = OCIStorage(fake, "ns", "bucket-dev")
    recibo, resultado = dados()
    with pytest.raises(PersistenciaIncompleta):
        persistir_resultado(storage, recibo, resultado, execucao_id=EXECUCAO)
    assert not fake.gravacoes


def test_falha_historico_impede_gravacao_resultado():
    fake = FakeOCI()
    fake.falhar_prefixo = "historicos/"
    storage = OCIStorage(fake, "ns", "bucket-dev")
    recibo, resultado = dados()
    with pytest.raises(PersistenciaIncompleta):
        persistir_resultado(storage, recibo, resultado, execucao_id=EXECUCAO)
    assert not fake.gravacoes


def test_falha_resultado_mantem_historico_parcial_sem_sucesso():
    fake = FakeOCI()
    fake.falhar_prefixo = "resultados/"
    storage = OCIStorage(fake, "ns", "bucket-dev")
    recibo, resultado = dados()
    with pytest.raises(PersistenciaIncompleta):
        persistir_resultado(storage, recibo, resultado, execucao_id=EXECUCAO)
    assert len(fake.gravacoes) == 1
    assert fake.gravacoes[0].startswith("historicos/")


def test_repeticao_mesmo_id_nao_sobrescreve():
    fake = FakeOCI()
    storage = OCIStorage(fake, "ns", "bucket-dev")
    recibo, resultado = dados()
    persistir_resultado(storage, recibo, resultado, execucao_id=EXECUCAO)
    conteudo = dict(fake.objetos)
    with pytest.raises(PersistenciaIncompleta):
        persistir_resultado(storage, recibo, resultado, execucao_id=EXECUCAO)
    assert fake.objetos == conteudo


def test_id_documento_divergente_rejeitado_antes_de_gravar():
    fake = FakeOCI()
    storage = OCIStorage(fake, "ns", "bucket-dev")
    recibo, resultado = dados()
    resultado.documento_id = "DOC-002"
    with pytest.raises(ValueError, match="não corresponde"):
        persistir_resultado(storage, recibo, resultado, execucao_id=EXECUCAO)
    assert not fake.gravacoes


def test_nao_persiste_resultado_em_processamento():
    fake = FakeOCI()
    storage = OCIStorage(fake, "ns", "bucket-dev")
    recibo, resultado = dados()
    resultado.status = "processando"
    with pytest.raises(ValueError, match="concluído"):
        persistir_resultado(storage, recibo, resultado, execucao_id=EXECUCAO)
    assert not fake.gravacoes


def test_integridade_do_historico_precisa_ser_verificada():
    fake = FakeOCI()
    fake.corromper_prefixo = "historicos/"
    storage = OCIStorage(fake, "ns", "bucket-dev")
    recibo, resultado = dados()
    with pytest.raises(PersistenciaIncompleta):
        persistir_resultado(storage, recibo, resultado, execucao_id=EXECUCAO)
    assert len(fake.gravacoes) == 1
