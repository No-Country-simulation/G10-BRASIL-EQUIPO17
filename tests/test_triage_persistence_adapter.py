"""Integra I1 + I5 via FakeOCI: nunca acessa rede, Gemini ou LangGraph."""
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest

from mediflow.api.triage_persistence_adapter import (
    PersistidorResultadoOCI,
    VinculoArquivoInvalido,
    montar_servico_triagem_com_oci,
)
from mediflow.api.triage_service import FalhaOrquestracao
from mediflow.api.uploads import ReciboArquivo
from mediflow.extraction.port import DocumentoParaExtracao
from mediflow.storage.oci_storage import OCIStorage
from mediflow_contracts.models import ExtracaoIA, ResultadoTriagem
from mediflow_contracts.routing import gerar_exemplo_de_contrato

RAIZ = Path(__file__).resolve().parents[1]
ID_ARQ = "a" * 32


class FakeOCI:
    def __init__(self):
        self.objetos = {}
        self.gravacoes = []
        self.falhar_prefixo = None
        self.corromper_prefixo = None

    def get_object(self, namespace, bucket, object_name):
        dados = self.objetos[object_name]
        if self.corromper_prefixo and object_name.startswith(self.corromper_prefixo):
            dados = b"conteudo corrompido"
        return SimpleNamespace(data=SimpleNamespace(content=dados))

    def put_object(self, namespace, bucket, object_name, data, **kwargs):
        assert kwargs["if_none_match"] == "*"
        if self.falhar_prefixo and object_name.startswith(self.falhar_prefixo):
            raise RuntimeError("SEGREDO_OCI_SIMULADO")
        if object_name in self.objetos:
            raise RuntimeError("precondition failed")
        self.objetos[object_name] = data
        self.gravacoes.append(object_name)


class ExtratorDeFixture:
    def extrair(self, documento):
        return ExtracaoIA.model_validate_json(
            (RAIZ / f"exemplos/{documento.documento_id}_extracao_ia.json").read_text("utf-8")
        )


class ConfirmadorPorBytesDeTeste:
    def confirmar(self, documento):
        return b"MARCADOR_EXPLICITO_TESTE" in documento.conteudo


class DecisorDeFixture:
    def decidir(self, extracao, *, entrada, rag, alerta_textual_confirmado):
        # Gerador historico apenas para testes, NAO substituir o I4.
        resultado = gerar_exemplo_de_contrato(
            extracao,
            formato=entrada.tipo_entrada,
            alerta_textual_confirmado=alerta_textual_confirmado,
            canal_origem=entrada.canal_origem,
        )
        resultado.entrada = entrada
        resultado.rag = rag
        return resultado


def preparar(doc_id="DOC-001", *, arquivo_id=ID_ARQ, canal="teste-sintetico"):
    fake = FakeOCI()
    storage = OCIStorage(fake, "namespace-ficticio", "bucket-ficticio")
    tipo = "png" if doc_id == "DOC-005" else "pdf"
    mime = "image/png" if tipo == "png" else "application/pdf"
    nome = f"amostra.{tipo}"
    dados = f"DOCUMENTO_FICTICIO_{doc_id}".encode("ascii")
    if doc_id == "DOC-002":
        dados += b" MARCADOR_EXPLICITO_TESTE"
    chave_original = f"originais/{doc_id}/{arquivo_id}.{tipo}"
    chave_metadados = f"metadados/{doc_id}/{arquivo_id}.json"
    recibo = ReciboArquivo.model_validate({
        "documento_id": doc_id,
        "arquivo_id": arquivo_id,
        "registrado_em_utc": "2026-11-04T00:00:00Z",
        "entrada": {
            "tipo_entrada": tipo,
            "canal_origem": canal,
            "sha256": sha256(dados).hexdigest(),
            "nome_arquivo": nome,
        },
        "armazenamento_original": {"bucket": storage.bucket, "chave_original": chave_original},
        "registro_metadados": {"chave_metadados": chave_metadados},
        "tamanho_bytes": len(dados),
    })
    fake.objetos[chave_original] = dados
    fake.objetos[chave_metadados] = recibo.model_dump_json().encode("utf-8")
    documento = DocumentoParaExtracao(
        documento_id=doc_id, arquivo_id=arquivo_id, nome_original=nome,
        mime_type=mime, conteudo=dados, sha256=sha256(dados).hexdigest(),
    )
    return fake, storage, recibo, documento


def criar_servico(storage, recibo):
    return montar_servico_triagem_com_oci(
        storage=storage, recibo=recibo,
        extrator=ExtratorDeFixture(),
        confirmador=ConfirmadorPorBytesDeTeste(),
        decisor=DecisorDeFixture(),
    )


@pytest.mark.parametrize("doc,regra,esperado", [
    ("DOC-001", "R005", "processado"),
    ("DOC-002", "R001", "aguardando_auditoria"),
    ("DOC-005", "R002", "aguardando_auditoria"),
])
def test_pipeline_i1_i5_persiste_dois_objetos(doc, regra, esperado):
    fake, storage, recibo, documento = preparar(doc)
    originais = dict(fake.objetos)
    servico = criar_servico(storage, recibo)
    assert len(fake.objetos) == 2  # montar nao escreve
    resultado = servico.executar(documento, canal_origem=recibo.entrada.canal_origem)
    assert resultado.status == esperado
    assert resultado.decisao_roteamento.regra_principal == regra
    assert resultado.armazenamento_oci.status == "confirmado"
    assert len(fake.gravacoes) == 2
    assert fake.gravacoes[0].startswith(f"historicos/{doc}/{documento.arquivo_id}/")
    assert fake.gravacoes[1].startswith(f"resultados/{doc}/{documento.arquivo_id}/")
    assert all(fake.objetos[k] == v for k,v in originais.items())
    assert ResultadoTriagem.model_validate_json(fake.objetos[fake.gravacoes[1]]) == resultado
    assert resultado.armazenamento_oci.chave_historico == fake.gravacoes[0]
    assert resultado.armazenamento_oci.chave_resultado == fake.gravacoes[1]


def test_recibo_diferente_documento_id_rejeitado_antes_da_gravacao():
    fake, storage, recibo, documento = preparar()
    servico = criar_servico(storage, recibo)
    outro = DocumentoParaExtracao("DOC-OUTRO", documento.arquivo_id, documento.nome_original,
                                   documento.mime_type, documento.conteudo, documento.sha256)
    with pytest.raises(VinculoArquivoInvalido):
        servico.executar(outro, canal_origem=recibo.entrada.canal_origem)
    assert fake.gravacoes == []


def test_arquivo_id_diferente_mesmos_bytes_rejeitado():
    fake, storage, recibo, documento = preparar()
    servico = criar_servico(storage, recibo)
    outro = DocumentoParaExtracao(documento.documento_id, "b"*32, documento.nome_original,
                                   documento.mime_type, documento.conteudo, documento.sha256)
    with pytest.raises(VinculoArquivoInvalido):
        servico.executar(outro, canal_origem=recibo.entrada.canal_origem)
    assert fake.gravacoes == []


def test_canal_diferente_rejeitado():
    fake, storage, recibo, documento = preparar()
    with pytest.raises(VinculoArquivoInvalido):
        criar_servico(storage, recibo).executar(documento, canal_origem="outro-canal")
    assert not fake.gravacoes


def test_bytes_adulterados_rejeitados_antes_de_gravar():
    fake, storage, recibo, documento = preparar()
    outro = DocumentoParaExtracao(documento.documento_id, documento.arquivo_id,
             documento.nome_original, documento.mime_type, b"adulterado", documento.sha256)
    with pytest.raises(VinculoArquivoInvalido):
        criar_servico(storage, recibo).executar(outro, canal_origem=recibo.entrada.canal_origem)
    assert not fake.gravacoes


def test_bucket_ou_chave_do_original_inconsistentes_rejeitados():
    fake, storage, recibo, _ = preparar()
    recibo.armazenamento_original.bucket = "outro-bucket"
    with pytest.raises(VinculoArquivoInvalido):
        criar_servico(storage, recibo)
    recibo.armazenamento_original.bucket = storage.bucket
    recibo.armazenamento_original.chave_original = "originais/DOC-001/outro.pdf"
    with pytest.raises(VinculoArquivoInvalido):
        criar_servico(storage, recibo)
    assert not fake.gravacoes


def test_chave_manifesto_incorreta_rejeitada():
    fake, storage, recibo, _ = preparar()
    recibo.registro_metadados.chave_metadados = "metadados/DOC-001/errado.json"
    with pytest.raises(VinculoArquivoInvalido):
        criar_servico(storage, recibo)
    assert not fake.gravacoes


def test_recibo_mutado_pelo_chamador_nao_altera_vinculo():
    fake, storage, recibo, documento = preparar()
    servico = criar_servico(storage, recibo)
    recibo.entrada.canal_origem = "canal-externo-mutado"
    resultado = servico.executar(documento, canal_origem="teste-sintetico")
    assert resultado.entrada.canal_origem == "teste-sintetico"
    assert resultado.armazenamento_oci.status == "confirmado"


def test_falha_historico_impede_sucesso_e_resultado():
    fake, storage, recibo, documento = preparar()
    fake.falhar_prefixo = "historicos/"
    with pytest.raises(FalhaOrquestracao) as e:
        criar_servico(storage, recibo).executar(documento, canal_origem=recibo.entrada.canal_origem)
    assert e.value.codigo == "PERSISTENCIA_INDISPONIVEL"
    assert "SEGREDO_OCI_SIMULADO" not in str(e.value)
    assert not fake.gravacoes


def test_falha_resultado_mantem_historico_parcial_sem_sucesso():
    fake, storage, recibo, documento = preparar()
    fake.falhar_prefixo = "resultados/"
    with pytest.raises(FalhaOrquestracao) as e:
        criar_servico(storage, recibo).executar(documento, canal_origem=recibo.entrada.canal_origem)
    assert e.value.codigo == "PERSISTENCIA_INDISPONIVEL"
    assert len(fake.gravacoes) == 1
    assert fake.gravacoes[0].startswith("historicos/")
    assert "SEGREDO_OCI_SIMULADO" not in str(e.value)


def test_resultado_corrompido_apos_upload_nao_e_confirmado():
    fake, storage, recibo, documento = preparar()
    fake.corromper_prefixo = "resultados/"
    with pytest.raises(FalhaOrquestracao) as e:
        criar_servico(storage, recibo).executar(documento, canal_origem=recibo.entrada.canal_origem)
    assert e.value.codigo == "PERSISTENCIA_INDISPONIVEL"
    assert len(fake.gravacoes) == 2


def test_reprocessamento_gera_outra_execucao_sem_sobrescrever():
    fake, storage, recibo, documento = preparar()
    servico = criar_servico(storage, recibo)
    r1 = servico.executar(documento, canal_origem=recibo.entrada.canal_origem)
    r2 = servico.executar(documento, canal_origem=recibo.entrada.canal_origem)
    assert r1.armazenamento_oci.chave_resultado != r2.armazenamento_oci.chave_resultado
    assert len(fake.gravacoes) == 4


def test_colisao_execucao_id_rejeitada_preservando_objetos(monkeypatch):
    fake, storage, recibo, documento = preparar()
    monkeypatch.setattr("mediflow.storage.triage_persistence.uuid4", lambda: SimpleNamespace(hex="b"*32))
    servico = criar_servico(storage, recibo)
    servico.executar(documento, canal_origem=recibo.entrada.canal_origem)
    snapshot = dict(fake.objetos)
    with pytest.raises(FalhaOrquestracao) as e:
        servico.executar(documento, canal_origem=recibo.entrada.canal_origem)
    assert e.value.codigo == "PERSISTENCIA_INDISPONIVEL"
    assert fake.objetos == snapshot


def test_persistidor_implementa_porta_e_rejeita_resultado_de_outro_documento():
    fake, storage, recibo, _ = preparar()
    persistidor = PersistidorResultadoOCI(storage, recibo)
    outro = ResultadoTriagem.model_validate_json(
        (RAIZ / "exemplos/DOC-002_resultado.json").read_text("utf-8")
    )
    with pytest.raises(ValueError, match="nao corresponde|não corresponde"):
        persistidor.persistir(outro)
    assert not fake.gravacoes
