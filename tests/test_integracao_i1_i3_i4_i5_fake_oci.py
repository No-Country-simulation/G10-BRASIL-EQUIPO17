"""Integração I1/I3/I4/I5 com RAG e LangGraph reais, mas FakeOCI.

Usa arquivos sintéticos oficiais e fixtures I2. Não acessa rede, Gemini,
credenciais OCI ou endpoints HTTP. Testa o vínculo e os efeitos de persistência.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from mediflow.api.composicao_i1_i3_i4_i5 import montar_servico_i1_i3_i4_i5
from mediflow.api.triage_persistence_adapter import VinculoArquivoInvalido
from mediflow.api.triage_service import FalhaOrquestracao
from mediflow.api.uploads import ReciboArquivo
from mediflow.storage.oci_storage import OCIStorage
from mediflow_contracts.models import ResultadoTriagem
from test_integracao_i1_i3_i4_real_local import ExtratorDeFixtureOficial, documento_oficial
from test_triage_persistence_adapter import FakeOCI


_TIPO = {"application/pdf": "pdf", "image/png": "png", "image/jpeg": "jpeg"}


def preparar_original(doc_id="DOC-001", *, arquivo_id="a" * 32, cliente=None):
    """Registra original e manifesto reais de teste no armazenamento fictício."""
    original = replace(documento_oficial(doc_id), arquivo_id=arquivo_id)
    fake = cliente if cliente is not None else FakeOCI()
    storage = OCIStorage(fake, "namespace-ficticio", "bucket-ficticio")
    extensao = original.nome_original.rsplit(".", 1)[-1].lower()
    chave_original = f"originais/{doc_id}/{arquivo_id}.{extensao}"
    chave_metadados = f"metadados/{doc_id}/{arquivo_id}.json"
    recibo = ReciboArquivo.model_validate(
        {
            "documento_id": doc_id,
            "arquivo_id": arquivo_id,
            "registrado_em_utc": "2026-11-10T00:00:00Z",
            "entrada": {
                "tipo_entrada": _TIPO[original.mime_type],
                "canal_origem": "teste_sintetico",
                "sha256": original.sha256,
                "nome_arquivo": original.nome_original,
            },
            "armazenamento_original": {
                "bucket": storage.bucket,
                "chave_original": chave_original,
            },
            "registro_metadados": {"chave_metadados": chave_metadados},
            "tamanho_bytes": len(original.conteudo),
        }
    )
    fake.objetos[chave_original] = original.conteudo
    fake.objetos[chave_metadados] = recibo.model_dump_json().encode("utf-8")
    return fake, storage, recibo, original


def montar(storage, recibo, *, recuperador_referencias=None):
    return montar_servico_i1_i3_i4_i5(
        storage=storage,
        recibo=recibo,
        extrator=ExtratorDeFixtureOficial(),
        recuperador_referencias=recuperador_referencias,
    )


@pytest.mark.parametrize(
    "doc_id,regra,destino,status",
    [
        ("DOC-001", "R005", "prontuario_documental", "processado"),
        ("DOC-002", "R001", "fila_prioritaria_avaliacao_humana", "aguardando_auditoria"),
        ("DOC-005", "R002", "auditoria_humana", "aguardando_auditoria"),
    ],
)
def test_documentos_oficiais_com_rag_grafo_e_persistencia_ficticia(doc_id, regra, destino, status):
    fake, storage, recibo, original = preparar_original(doc_id)
    snapshot = dict(fake.objetos)
    servico = montar(storage, recibo)
    assert not fake.gravacoes  # Construir a composição não realiza escrita.

    resultado = servico.executar(original, canal_origem=recibo.entrada.canal_origem)

    assert resultado.documento_id == doc_id
    assert resultado.entrada.sha256 == original.sha256
    assert resultado.status == status
    assert resultado.decisao_roteamento.regra_principal == regra
    assert resultado.decisao_roteamento.destino_principal == destino
    assert resultado.rag.status == "consultado"
    assert 1 <= len(resultado.rag.fontes) <= 3
    assert resultado.armazenamento_oci.status == "confirmado"
    assert len(fake.gravacoes) == 2
    chave_historico, chave_resultado = fake.gravacoes
    assert chave_historico.startswith(f"historicos/{doc_id}/{original.arquivo_id}/")
    assert chave_resultado.startswith(f"resultados/{doc_id}/{original.arquivo_id}/")
    assert resultado.armazenamento_oci.chave_historico == chave_historico
    assert resultado.armazenamento_oci.chave_resultado == chave_resultado
    persistido = ResultadoTriagem.model_validate_json(fake.objetos[chave_resultado])
    assert persistido == resultado
    assert all(fake.objetos[chave] == blob for chave, blob in snapshot.items())
    if doc_id == "DOC-005":
        assert resultado.dados_extraidos.medicamentos[0].dosagem_texto is None
        assert resultado.dados_extraidos.medicamentos[0].dosagem_status == "ilegivel"


def test_falha_rag_nao_rebaixa_alerta_e_oci_guarda_estado_de_falha():
    class RecuperadorIndisponivel:
        def buscar(self, consulta):
            raise RuntimeError("SEGREDO_RAG_SINTETICO")

    fake, storage, recibo, original = preparar_original("DOC-002")
    resultado = montar(
        storage, recibo, recuperador_referencias=RecuperadorIndisponivel()
    ).executar(original, canal_origem=recibo.entrada.canal_origem)
    assert resultado.rag.status == "falha"
    assert resultado.decisao_roteamento.regra_principal == "R001"
    assert resultado.decisao_roteamento.requer_revisao_humana
    assert resultado.armazenamento_oci.status == "confirmado"
    assert "SEGREDO_RAG_SINTETICO" not in str(resultado.model_dump())
    persistido = ResultadoTriagem.model_validate_json(
        fake.objetos[resultado.armazenamento_oci.chave_resultado]
    )
    assert persistido == resultado


@pytest.mark.parametrize(
    "prefixo,quantidade_gravacoes",
    [("historicos/", 0), ("resultados/", 1)],
)
def test_falha_oci_nao_declara_persistencia_confirmada(prefixo, quantidade_gravacoes):
    fake, storage, recibo, original = preparar_original("DOC-001")
    fake.falhar_prefixo = prefixo
    with pytest.raises(FalhaOrquestracao, match="PERSISTENCIA_INDISPONIVEL") as erro:
        montar(storage, recibo).executar(
            original, canal_origem=recibo.entrada.canal_origem
        )
    assert len(fake.gravacoes) == quantidade_gravacoes
    assert "SEGREDO_OCI_SIMULADO" not in str(erro.value)
    assert not any(chave.startswith("resultados/") for chave in fake.objetos)


@pytest.mark.parametrize("adulteracao", ["arquivo_id", "sha256"])
def test_vinculo_arquivo_incorreto_impede_persistencia(adulteracao):
    fake, storage, recibo, original = preparar_original("DOC-001")
    alteracoes = {"arquivo_id": "b" * 32} if adulteracao == "arquivo_id" else {"sha256": "0" * 64}
    adulterado = replace(original, **alteracoes)
    with pytest.raises(VinculoArquivoInvalido):
        montar(storage, recibo).executar(
            adulterado, canal_origem=recibo.entrada.canal_origem
        )
    assert not fake.gravacoes


def test_dois_uploads_do_mesmo_documento_nao_misturam_chaves():
    fake, storage_a, recibo_a, original_a = preparar_original("DOC-001")
    _, storage_b, recibo_b, original_b = preparar_original(
        "DOC-001", arquivo_id="b" * 32, cliente=fake
    )
    a = montar(storage_a, recibo_a).executar(
        original_a, canal_origem=recibo_a.entrada.canal_origem
    )
    b = montar(storage_b, recibo_b).executar(
        original_b, canal_origem=recibo_b.entrada.canal_origem
    )
    assert a.armazenamento_oci.status == b.armazenamento_oci.status == "confirmado"
    assert a.armazenamento_oci.chave_resultado != b.armazenamento_oci.chave_resultado
    assert a.armazenamento_oci.chave_historico != b.armazenamento_oci.chave_historico
    assert len(fake.gravacoes) == 4
