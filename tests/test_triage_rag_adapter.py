"""Contrato I1/I3 isolado: somente fakes, sem I3 Draft, rede, OCI ou Gemini."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from mediflow.api.triage_rag_adapter import AdaptadorRAGI3, construir_texto_consulta
from mediflow_contracts.models import ExtracaoIA, RecuperacaoRAG, FonteRAG, SinaisDocumentais, Paciente

RAIZ = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, slots=True)
class ConsultaDeTeste:
    texto: str
    limite: int = 3


class RecuperadorFake:
    def __init__(self, retorno=None):
        self.consultas = []
        self.retorno = retorno if retorno is not None else RecuperacaoRAG(status="sem_resultados")

    def buscar(self, consulta):
        assert isinstance(consulta, ConsultaDeTeste)
        self.consultas.append(consulta)
        return self.retorno


def extracao(doc="DOC-005"):
    return ExtracaoIA.model_validate_json(
        (RAIZ / f"exemplos/{doc}_extracao_ia.json").read_text(encoding="utf-8")
    )


@pytest.mark.parametrize("doc,palavras", [
    ("DOC-001", ("laudo", "laboratorial", "exame")),
    ("DOC-002", ("laudo", "imagem", "achados")),
    ("DOC-005", ("receituario", "dosagem", "ilegivel")),
])
def test_consulta_utiliza_categoria_e_estado_sintetico(doc, palavras):
    consulta = construir_texto_consulta(extracao(doc))
    assert all(palavra in consulta for palavra in palavras)
    assert "campos minimos" in consulta


@pytest.mark.parametrize("categoria", [
    "receituario", "laudo_laboratorial", "laudo_imagem", "solicitacao_exame",
    "relatorio_alta", "atestado", "outro_desconhecido",
])
def test_todas_as_categorias_podem_gerar_consulta(categoria):
    entrada = extracao()
    entrada.tipo_documento = categoria
    assert construir_texto_consulta(entrada).strip()


def test_consulta_nao_expoe_identificadores_nem_textos_livres():
    entrada = extracao("DOC-005")
    entrada.documento_id = "SEGREDO-ID-900"
    entrada.dados_extraidos.paciente.nome = "PACIENTE-SIGILOSO"
    entrada.dados_extraidos.paciente.identificador = "CPF-SIGILOSO"
    entrada.dados_extraidos.profissional.nome = "MEDICO-SIGILOSO"
    entrada.dados_extraidos.medicamentos[0].nome = "MEDICAMENTO-SIGILOSO"
    entrada.dados_extraidos.cid_documentado = "CID-SIGILOSO"
    entrada.dados_extraidos.resumo = "RESUMO-SIGILOSO"
    entrada.evidencias = []
    entrada.sinais_documentais = SinaisDocumentais(
        marcador_urgencia_explicito=True,
        transcricao_marcador_urgencia="MARCADOR-SIGILOSO",
    )
    texto = construir_texto_consulta(entrada)
    assert "SIGILOSO" not in texto
    assert "SEGREDO" not in texto
    assert "DOC-005" not in texto
    assert "MARCADOR" not in texto.upper()


def test_consulta_nao_altera_objeto_de_extracao():
    entrada = extracao("DOC-005")
    antes = entrada.model_dump(mode="json")
    construir_texto_consulta(entrada)
    assert entrada.model_dump(mode="json") == antes


def test_estados_problema_sem_conteudo_livre():
    entrada = extracao("DOC-005")
    entrada.dados_extraidos.paciente = Paciente(nome=None, nome_status="ilegivel")
    entrada.dados_extraidos.medicamentos[0].dosagem_status = "conflitante"
    consulta = construir_texto_consulta(entrada)
    assert "nome ilegivel" in consulta
    assert "dosagem conflitante" in consulta
    assert "dosagem ilegivel" not in consulta


def test_nao_inventa_dosagem_ausente_se_lista_esta_vazia():
    entrada = extracao("DOC-001")
    consulta = construir_texto_consulta(entrada)
    assert "dosagem ausente" not in consulta


def test_adaptador_repassa_texto_e_limite_para_consulta_estrutural():
    fake = RecuperadorFake()
    adaptador = AdaptadorRAGI3(recuperador=fake, fabrica_consulta=ConsultaDeTeste, limite=2)
    resultado = adaptador.buscar(extracao("DOC-005"))
    assert isinstance(resultado, RecuperacaoRAG)
    assert resultado.status == "sem_resultados"
    assert len(fake.consultas) == 1
    assert fake.consultas[0].limite == 2
    assert "dosagem ilegivel" in fake.consultas[0].texto


def test_devolve_fontes_link_e_versao_sem_alterar_entrada():
    fonte = FonteRAG(
        fonte_id="REGRA-R002", titulo="Documento de teste", versao="0.1",
        url="https://example.org/fonte", trecho_relevante="Trecho fictício relevante",
    )
    upstream = RecuperacaoRAG(status="consultado", fontes=[fonte])
    fake = RecuperadorFake(upstream)
    resultado = AdaptadorRAGI3(fake, ConsultaDeTeste).buscar(extracao())
    assert resultado.status == "consultado"
    assert resultado.fontes[0].url == fonte.url
    assert resultado.fontes[0].versao == "0.1"
    assert resultado.fontes[0].trecho_relevante == "Trecho fictício relevante"
    assert resultado is not upstream
    resultado.fontes[0].titulo = "ALTERADO"
    assert upstream.fontes[0].titulo == "Documento de teste"


@pytest.mark.parametrize("status", ["falha", "nao_consultado", "sem_resultados"])
def test_estados_sem_fontes_preservados(status):
    retorno = RecuperacaoRAG(status=status, erro_codigo="RAG_FALHA_SIMULADA" if status == "falha" else None)
    resultado = AdaptadorRAGI3(RecuperadorFake(retorno), ConsultaDeTeste).buscar(extracao())
    assert resultado.status == status
    assert not resultado.fontes


@pytest.mark.parametrize("limite", [0, -1, 11, 1.5, True, "3"])
def test_limite_invalido_rejeitado(limite):
    with pytest.raises(ValueError):
        AdaptadorRAGI3(RecuperadorFake(), ConsultaDeTeste, limite=limite)


def test_recuperador_e_fabrica_ausentes_rejeitados():
    with pytest.raises(TypeError):
        AdaptadorRAGI3(object(), ConsultaDeTeste)
    with pytest.raises(TypeError):
        AdaptadorRAGI3(RecuperadorFake(), None)


def test_tipo_de_extracao_invalido_rejeitado_antes_da_busca():
    fake = RecuperadorFake()
    with pytest.raises(TypeError):
        AdaptadorRAGI3(fake, ConsultaDeTeste).buscar({"texto": "nao validado"})
    assert not fake.consultas


def test_fabrica_que_altera_parametros_nao_aciona_recuperador():
    fake = RecuperadorFake()
    def fabrica(*, texto, limite):
        return ConsultaDeTeste(texto=texto, limite=limite + 1)
    with pytest.raises(ValueError, match="inconsistentes"):
        AdaptadorRAGI3(fake, fabrica).buscar(extracao())
    assert fake.consultas == []


def test_erro_de_busca_propaga_para_que_i1_registre_falha():
    class RecuperadorComFalha:
        def buscar(self, consulta):
            raise RuntimeError("ERRO_PRIVADO_SIMULADO")
    with pytest.raises(RuntimeError):
        AdaptadorRAGI3(RecuperadorComFalha(), ConsultaDeTeste).buscar(extracao())


def test_retorno_invalido_rejeitado_pelo_contrato():
    fake = RecuperadorFake({"status": "consultado", "fontes": []})
    with pytest.raises(Exception):
        AdaptadorRAGI3(fake, ConsultaDeTeste).buscar(extracao())


@pytest.mark.parametrize("doc_id,mime,marcador,regra", [
    ("DOC-001", "application/pdf", False, "R005"),
    ("DOC-002", "application/pdf", True, "R001"),
    ("DOC-005", "image/png", False, "R002"),
])
def test_fluxo_i1_com_adaptador_preserva_decisao_independente(doc_id, mime, marcador, regra):
    """Prova a conexão ao I1, nunca substitui o motor de regras do I4."""
    from hashlib import sha256
    from mediflow.api.triage_service import ServicoTriagem
    from mediflow.extraction.port import DocumentoParaExtracao
    from mediflow_contracts.routing import gerar_exemplo_de_contrato

    class ExtratorDeFixture:
        def extrair(self, documento):
            return extracao(doc_id)

    class ConfirmadorPorBytes:
        def confirmar(self, documento):
            return b"MARCADOR_EXPLICITO_TESTE" in documento.conteudo

    class DecisorDeFixture:
        def decidir(self, extracao_ia, *, entrada, rag, alerta_textual_confirmado):
            resultado = gerar_exemplo_de_contrato(
                extracao_ia, formato=entrada.tipo_entrada,
                alerta_textual_confirmado=alerta_textual_confirmado,
                canal_origem=entrada.canal_origem,
            )
            resultado.entrada = entrada
            resultado.rag = rag
            return resultado

    conteudo = f"AMOSTRA_FICTICIA_{doc_id}".encode("ascii")
    if marcador:
        conteudo += b" MARCADOR_EXPLICITO_TESTE"
    documento = DocumentoParaExtracao(
        documento_id=doc_id, arquivo_id="a" * 32,
        nome_original="amostra.pdf" if mime == "application/pdf" else "amostra.png",
        mime_type=mime, conteudo=conteudo, sha256=sha256(conteudo).hexdigest(),
    )
    fonte = FonteRAG(fonte_id="REGRA-SINTETICA", titulo="Ficha de teste", versao="0.1")
    fake_i3 = RecuperadorFake(RecuperacaoRAG(status="consultado", fontes=[fonte]))
    servico_i1 = ServicoTriagem(
        extrator=ExtratorDeFixture(),
        confirmador=ConfirmadorPorBytes(),
        decisor=DecisorDeFixture(),
        recuperador=AdaptadorRAGI3(fake_i3, ConsultaDeTeste),
    )
    resultado = servico_i1.executar(documento, canal_origem="teste_sintetico")
    assert resultado.decisao_roteamento.regra_principal == regra
    assert resultado.rag.status == "consultado"
    assert resultado.rag.fontes[0].fonte_id == "REGRA-SINTETICA"
    assert len(fake_i3.consultas) == 1
    assert documento.documento_id not in fake_i3.consultas[0].texto


def test_falha_do_recuperador_e_isolada_pelo_i1_sem_interromper_triagem():
    """Comprova fallback real do I1, sem rede, Gemini ou I4 real."""
    from hashlib import sha256
    from mediflow.api.triage_service import ServicoTriagem
    from mediflow.extraction.port import DocumentoParaExtracao
    from mediflow_contracts.routing import gerar_exemplo_de_contrato

    class Extrator:
        def extrair(self, documento):
            return extracao("DOC-001")

    class Confirmador:
        def confirmar(self, documento):
            return False

    class Decisor:
        def decidir(self, e, *, entrada, rag, alerta_textual_confirmado):
            res = gerar_exemplo_de_contrato(
                e, formato=entrada.tipo_entrada,
                alerta_textual_confirmado=alerta_textual_confirmado,
                canal_origem=entrada.canal_origem,
            )
            res.entrada = entrada
            res.rag = rag
            return res

    class RAGQueFalha:
        def buscar(self, consulta):
            raise RuntimeError("CHAVE_FICTICIA_NAO_EXIBIR")

    dados = b"AMOSTRA_FICTICIA_DOC-001"
    documento = DocumentoParaExtracao(
        "DOC-001", "a" * 32, "amostra.pdf", "application/pdf", dados, sha256(dados).hexdigest(),
    )
    servico = ServicoTriagem(
        Extrator(), Confirmador(), Decisor(),
        recuperador=AdaptadorRAGI3(RAGQueFalha(), ConsultaDeTeste),
    )
    res = servico.executar(documento, canal_origem="teste_sintetico")
    assert res.decisao_roteamento.regra_principal == "R005"
    assert res.rag.status == "falha"
    assert res.rag.erro_codigo == "RAG_ERRO_INTEGRACAO"
    assert "CHAVE_FICTICIA_NAO_EXIBIR" not in str(res.model_dump())
