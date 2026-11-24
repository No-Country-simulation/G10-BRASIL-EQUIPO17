
import pytest
from unittest.mock import MagicMock, patch

from mediflow.extraction.gemini_extractor import ExtratorGemini
from mediflow_contracts.models import EntradaTexto


def criar_entrada():
    return EntradaTexto(
        documento_id="doc-123",
        canal_origem="teste",
        documento_texto="Documento fictício para teste.",
    )


def test_extrator_rejeita_api_key_ausente(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        ExtratorGemini()

def test_extrator_configura_timeout_e_retry(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "chave-ficticia")

    with patch(
        "mediflow.extraction.gemini_extractor.genai.Client"
    ) as cliente_mock:
        ExtratorGemini()

    cliente_mock.assert_called_once()

    configuracao = cliente_mock.call_args.kwargs["http_options"]

    assert configuracao.timeout == 60000

    retry = configuracao.retry_options

    assert retry.attempts == 5
    assert retry.initial_delay == 2
    assert retry.max_delay == 30
    assert retry.exp_base == 2
    assert retry.http_status_codes == [408, 429, 500, 502, 503, 504]


def test_extrator_envia_texto_e_valida_resposta(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "chave-ficticia")

    resposta_json = {
        "contrato_versao": "0.1",
        "documento_id": "doc-123",
        "tipo_documento": "outro_desconhecido",
        "dados_extraidos": {},
    }

    resposta = MagicMock()
    resposta.text = __import__("json").dumps(resposta_json)

    cliente_mock = MagicMock()
    cliente_mock.models.generate_content.return_value = resposta

    with patch(
        "mediflow.extraction.gemini_extractor.genai.Client",
        return_value=cliente_mock,
    ):
        extrator = ExtratorGemini()
        resultado = extrator.extrair_texto(criar_entrada())

    assert resultado.documento_id == "doc-123"
    cliente_mock.models.generate_content.assert_called_once()


def test_extrator_rejeita_resposta_sem_texto(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "chave-ficticia")

    resposta = MagicMock()
    resposta.text = None

    cliente_mock = MagicMock()
    cliente_mock.models.generate_content.return_value = resposta

    with patch(
        "mediflow.extraction.gemini_extractor.genai.Client",
        return_value=cliente_mock,
    ):
        extrator = ExtratorGemini()

        with pytest.raises(ValueError, match="resposta vazia"):
            extrator.extrair_texto(criar_entrada())



from mediflow.extraction.port import DocumentoParaExtracao, ExtratorDocumento


def criar_documento(mime_type="text/plain", conteudo=b"Documento ficticio"):
    return DocumentoParaExtracao(
        documento_id="doc-123",
        arquivo_id="arquivo-123",
        nome_original="documento.txt",
        mime_type=mime_type,
        conteudo=conteudo,
        sha256="hash-ficticio",
    )



def test_extrator_gemini_implementa_interface(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "chave-ficticia")

    with patch(
        "mediflow.extraction.gemini_extractor.genai.Client"
    ):
        extrator = ExtratorGemini()

    assert callable(getattr(extrator, "extrair", None))



def test_extrator_rejeita_tipo_nao_suportado(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "chave-ficticia")

    with patch(
        "mediflow.extraction.gemini_extractor.genai.Client"
    ):
        extrator = ExtratorGemini()

    with pytest.raises(ValueError, match="Tipo de arquivo não suportado"):
        extrator.extrair(
            criar_documento(mime_type="application/octet-stream", conteudo=b"%PDF")
        )


def test_extrator_rejeita_texto_utf8_invalido(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "chave-ficticia")

    with patch(
        "mediflow.extraction.gemini_extractor.genai.Client"
    ):
        extrator = ExtratorGemini()

    with pytest.raises(ValueError, match="UTF-8"):
        extrator.extrair(
            criar_documento(conteudo=b"\xff\xfe")
        )



def test_extrator_processa_pdf_e_encaminha_texto_ao_gemini(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "chave-ficticia")

    with patch(
        "mediflow.extraction.gemini_extractor.genai.Client"
    ):
        extrator = ExtratorGemini()

    resultado_esperado = MagicMock()

    with (
        patch(
            "mediflow.extraction.gemini_extractor.extrair_texto_pdf",
            return_value="Texto fictício extraído do PDF.",
        ) as mock_pdf,
        patch.object(
            extrator,
            "extrair_texto",
            return_value=resultado_esperado,
        ) as mock_gemini,
    ):
        resultado = extrator.extrair(
            criar_documento(
                mime_type="application/pdf",
                conteudo=b"conteudo-pdf-ficticio",
            )
        )

    mock_pdf.assert_called_once_with(b"conteudo-pdf-ficticio")
    mock_gemini.assert_called_once()

    entrada = mock_gemini.call_args.args[0]
    assert entrada.documento_texto == "Texto fictício extraído do PDF."
    assert resultado is resultado_esperado


@pytest.mark.parametrize("mime_type", ["image/png", "image/jpeg"])
def test_extrator_processa_imagem_e_encaminha_texto_ao_gemini(
    monkeypatch, mime_type
):
    monkeypatch.setenv("GEMINI_API_KEY", "chave-ficticia")

    with patch(
        "mediflow.extraction.gemini_extractor.genai.Client"
    ):
        extrator = ExtratorGemini()

    resultado_esperado = MagicMock()

    with (
        patch(
            "mediflow.extraction.gemini_extractor.extrair_texto_imagem",
            return_value="[Página 1]\nTexto fictício extraído da imagem.",
        ) as mock_imagem,
        patch.object(
            extrator,
            "extrair_texto",
            return_value=resultado_esperado,
        ) as mock_gemini,
    ):
        resultado = extrator.extrair(
            criar_documento(
                mime_type=mime_type,
                conteudo=b"imagem-ficticia",
            )
        )

    mock_imagem.assert_called_once_with(b"imagem-ficticia")
    mock_gemini.assert_called_once()

    entrada = mock_gemini.call_args.args[0]
    assert entrada.documento_texto == "[Página 1]\nTexto fictício extraído da imagem."
    assert resultado is resultado_esperado

def test_extrator_propaga_falha_de_comunicacao_com_gemini(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "chave-ficticia")

    cliente_mock = MagicMock()
    cliente_mock.models.generate_content.side_effect = RuntimeError(
        "Serviço Gemini indisponível"
    )

    with patch(
        "mediflow.extraction.gemini_extractor.genai.Client",
        return_value=cliente_mock,
    ):
        extrator = ExtratorGemini()

    with pytest.raises(RuntimeError, match="Serviço Gemini indisponível"):
        extrator.extrair_texto(criar_entrada())

def test_extrator_usa_modelo_padrao(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "chave-ficticia")
    monkeypatch.delenv("GEMINI_MODEL", raising=False)

    with patch("mediflow.extraction.gemini_extractor.genai.Client"):
        extrator = ExtratorGemini()

    assert extrator.modelo == "gemini-3.5-flash-lite"


def test_extrator_usa_modelo_da_variavel_ambiente(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "chave-ficticia")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.1-flash-lite")

    with patch("mediflow.extraction.gemini_extractor.genai.Client"):
        extrator = ExtratorGemini()

    assert extrator.modelo == "gemini-3.1-flash-lite"


def test_extrator_prioriza_modelo_informado_no_construtor(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "chave-ficticia")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.1-flash-lite")

    with patch("mediflow.extraction.gemini_extractor.genai.Client"):
        extrator = ExtratorGemini(modelo="gemini-3.8-flash")

    assert extrator.modelo == "gemini-3.8-flash"

def test_extrator_usa_modelo_padrao_quando_variavel_vazia(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "chave-ficticia")
    monkeypatch.setenv("GEMINI_MODEL", "")

    with patch("mediflow.extraction.gemini_extractor.genai.Client"):
        extrator = ExtratorGemini()

    assert extrator.modelo == "gemini-3.5-flash-lite"


def test_extrator_usa_modelo_padrao_quando_variavel_tem_apenas_espacos(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "chave-ficticia")
    monkeypatch.setenv("GEMINI_MODEL", "   ")

    with patch("mediflow.extraction.gemini_extractor.genai.Client"):
        extrator = ExtratorGemini()

    assert extrator.modelo == "gemini-3.5-flash-lite"



def test_extrator_envia_modelo_configurado_para_gemini(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "chave-ficticia")

    resposta_json = {
        "contrato_versao": "0.1",
        "documento_id": "doc-123",
        "tipo_documento": "outro_desconhecido",
        "dados_extraidos": {},
    }

    resposta = MagicMock()
    resposta.text = __import__("json").dumps(resposta_json)

    cliente_mock = MagicMock()
    cliente_mock.models.generate_content.return_value = resposta

    modelo_esperado = "gemini-3.1-flash-lite"

    with patch(
        "mediflow.extraction.gemini_extractor.genai.Client",
        return_value=cliente_mock,
    ):
        extrator = ExtratorGemini(modelo=modelo_esperado)
        extrator.extrair_texto(criar_entrada())

    argumentos = cliente_mock.models.generate_content.call_args.kwargs

    assert argumentos["model"] == modelo_esperado

# A entrada binaria e o texto independente coexistem no modo multimodal.
@pytest.fixture
def cliente_multimodal(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "chave-ficticia")
    cliente = MagicMock()
    cliente.models.generate_content.return_value.text = __import__("json").dumps({
        "contrato_versao": "0.1",
        "documento_id": "doc-123",
        "tipo_documento": "outro_desconhecido",
        "dados_extraidos": {},
    })
    with patch("mediflow.extraction.gemini_extractor.genai.Client", return_value=cliente):
        yield cliente


@pytest.mark.parametrize("mime,funcao", [
    ("application/pdf", "extrair_texto_pdf"),
    ("image/png", "extrair_texto_imagem"),
    ("image/jpeg", "extrair_texto_imagem"),
])
def test_multimodal_envia_bytes_originais_e_texto(monkeypatch, cliente_multimodal, mime, funcao):
    monkeypatch.setenv("MEDIFLOW_ENABLE_GEMINI_MULTIMODAL", "true")
    original = b"bytes-ficticios-do-documento"
    referencia = "[Página 1]\nDocumento fictício para teste."
    with patch("mediflow.extraction.gemini_extractor." + funcao, return_value=referencia) as ocr:
        resultado = ExtratorGemini().extrair(criar_documento(mime_type=mime, conteudo=original))
    ocr.assert_called_once_with(original)
    cliente_multimodal.models.generate_content.assert_called_once()
    kwargs = cliente_multimodal.models.generate_content.call_args.kwargs
    assert kwargs["config"] == {"response_mime_type": "application/json"}
    partes = kwargs["contents"]
    assert isinstance(partes, list) and len(partes) == 2
    assert partes[0].inline_data.data == original
    assert partes[0].inline_data.mime_type == mime
    assert referencia in partes[1]
    assert "Schema JSON obrigatório:" in partes[1]
    assert resultado.documento_id == "doc-123"


@pytest.mark.parametrize("flag", [None, "false", "1"])
def test_multimodal_nao_ativado_preserva_prompt_textual(monkeypatch, cliente_multimodal, flag):
    if flag is None:
        monkeypatch.delenv("MEDIFLOW_ENABLE_GEMINI_MULTIMODAL", raising=False)
    else:
        monkeypatch.setenv("MEDIFLOW_ENABLE_GEMINI_MULTIMODAL", flag)
    with patch("mediflow.extraction.gemini_extractor.extrair_texto_pdf", return_value="Texto de referência"):
        ExtratorGemini().extrair(criar_documento(mime_type="application/pdf", conteudo=b"pdf-ficticio"))
    kwargs = cliente_multimodal.models.generate_content.call_args.kwargs
    assert isinstance(kwargs["contents"], str)
    assert "Texto de referência" in kwargs["contents"]


def test_multimodal_mantem_texto_livre(monkeypatch, cliente_multimodal):
    monkeypatch.setenv("MEDIFLOW_ENABLE_GEMINI_MULTIMODAL", "true")
    extrator = ExtratorGemini()
    extrator.extrair(criar_documento())
    assert isinstance(cliente_multimodal.models.generate_content.call_args.kwargs["contents"], str)
    extrator.extrair_texto(criar_entrada())
    assert isinstance(cliente_multimodal.models.generate_content.call_args.kwargs["contents"], str)


@pytest.mark.parametrize("pagina,trecho,erro", [
    (1, "Documento fictício", None),
    (2, "Documento fictício", "página inexistente"),
    (1, "Informação inventada", "trecho da evidência"),
    (None, "Informação inventada", "trecho da evidência"),
])
def test_multimodal_valida_evidencias_no_texto_independente(monkeypatch, cliente_multimodal, pagina, trecho, erro):
    monkeypatch.setenv("MEDIFLOW_ENABLE_GEMINI_MULTIMODAL", "true")
    cliente_multimodal.models.generate_content.return_value.text = __import__("json").dumps({
        "contrato_versao": "0.1", "documento_id": "doc-123",
        "tipo_documento": "outro_desconhecido", "dados_extraidos": {},
        "evidencias": [{"campo": "descricao_documento", "trecho_documento": trecho,
                        "pagina": pagina, "origem": "documento"}],
    })
    documento = criar_documento(mime_type="image/png", conteudo=b"imagem-ficticia")
    with patch("mediflow.extraction.gemini_extractor.extrair_texto_imagem", return_value="[Página 1]\nDocumento fictício"):
        if erro:
            with pytest.raises(ValueError, match=erro):
                ExtratorGemini().extrair(documento)
        else:
            resultado = ExtratorGemini().extrair(documento)
            assert resultado.evidencias[0].pagina == 1
    cliente_multimodal.models.generate_content.assert_called_once()


@pytest.mark.parametrize("mime,funcao,referencia", [
    ("image/png", "extrair_texto_imagem", ""),
    ("application/pdf", "extrair_texto_pdf", "[Página 1]\n\n[Página 2]"),
])
def test_multimodal_sem_texto_independente_nao_chama_modelo(monkeypatch, cliente_multimodal, mime, funcao, referencia):
    monkeypatch.setenv("MEDIFLOW_ENABLE_GEMINI_MULTIMODAL", "true")
    with patch("mediflow.extraction.gemini_extractor." + funcao, return_value=referencia):
        with pytest.raises(ValueError, match="extrair texto"):
            ExtratorGemini().extrair(criar_documento(mime_type=mime, conteudo=b"documento-ficticio"))
    cliente_multimodal.models.generate_content.assert_not_called()


def test_multimodal_falha_gemini_sem_fallback_silencioso(monkeypatch, cliente_multimodal):
    monkeypatch.setenv("MEDIFLOW_ENABLE_GEMINI_MULTIMODAL", "true")
    cliente_multimodal.models.generate_content.side_effect = RuntimeError("falha simulada")
    with patch("mediflow.extraction.gemini_extractor.extrair_texto_pdf", return_value="Texto de referência"):
        with pytest.raises(RuntimeError, match="falha simulada"):
            ExtratorGemini().extrair(criar_documento(mime_type="application/pdf", conteudo=b"pdf-ficticio"))
    cliente_multimodal.models.generate_content.assert_called_once()

@pytest.mark.parametrize("flag,regra,nota", [("true", "R005", 1.0), ("false", "R005", 1.0)])
def test_multimodal_corrige_caminhos_e_preserva_motor(monkeypatch, cliente_multimodal, flag, regra, nota):
    from mediflow.rules.motor_deterministico import MotorRegrasDeterministico
    from mediflow_contracts.models import EntradaProcessada, RecuperacaoRAG

    monkeypatch.setenv("MEDIFLOW_ENABLE_GEMINI_MULTIMODAL", flag)
    pares = [
        ("paciente.nome", "Paciente Ficticio"),
        ("exame.nome", "Hemograma"),
        ("exame.conclusao", "Rotina"),
        ("exame.resultados[0].valor_texto", "13,4"),
        ("profissional.nome", "Profissional Ficticio"),
    ]
    evidencias = [{"campo": "dados_extraidos." + campo, "trecho_documento": trecho,
                   "pagina": 1, "origem": "documento"} for campo, trecho in pares]
    payload = {
        "documento_id": "doc-123", "tipo_documento": "laudo_laboratorial",
        "dados_extraidos": {
            "paciente": {"nome": "Paciente Ficticio", "nome_status": "legivel"},
            "profissional": {"nome": "Profissional Ficticio"},
            "exame": {"nome": "Hemograma", "conclusao": "Rotina",
                      "resultados": [{"parametro": "Hemoglobina", "valor_texto": "13,4"}]},
        }, "evidencias": evidencias,
    }
    cliente_multimodal.models.generate_content.return_value.text = __import__("json").dumps(payload)
    referencia = "[Página 1]\n" + "\n".join(trecho for _, trecho in pares)
    with patch("mediflow.extraction.gemini_extractor.extrair_texto_pdf", return_value=referencia):
        extracao = ExtratorGemini().extrair(criar_documento(mime_type="application/pdf", conteudo=b"pdf-ficticio"))
    esperado = [dict(e, campo=e["campo"].removeprefix("dados_extraidos.")) for e in evidencias]
    assert [e.model_dump() for e in extracao.evidencias] == esperado
    if flag == "true":
        prompt = cliente_multimodal.models.generate_content.call_args.kwargs["contents"][1]
        assert "caminhos relativos sem" in prompt
    resultado = MotorRegrasDeterministico().decidir(
        extracao, entrada=EntradaProcessada(tipo_entrada="pdf", canal_origem="teste"),
        rag=RecuperacaoRAG(), alerta_textual_confirmado=False,
    )
    assert resultado.classificacao.indicador_qualidade.valor == nota
    assert resultado.decisao_roteamento.regra_principal == regra
    assert resultado.decisao_roteamento.requer_revisao_humana is False


def test_multimodal_normaliza_medicamento_sem_alterar_sinal_ou_caminho_canonico():
    from mediflow_contracts.models import ExtracaoIA
    from mediflow.extraction.gemini_extractor import _normalizar_caminhos_multimodais
    campos = ["dados_extraidos.medicamentos[0].nome", "sinais_documentais.marcador_urgencia_explicito", "paciente.nome"]
    extracao = ExtracaoIA.model_validate({
        "documento_id": "doc-123", "tipo_documento": "receituario",
        "dados_extraidos": {"medicamentos": [{"nome": "Ficticio", "dosagem_status": "ilegivel"}]},
        "evidencias": [{"campo": c, "trecho_documento": "Ficticio", "pagina": 1} for c in campos],
    })
    normalizada = _normalizar_caminhos_multimodais(extracao)
    assert [e.campo for e in normalizada.evidencias] == ["medicamentos[0].nome", *campos[1:]]
    assert [e.campo for e in extracao.evidencias] == campos
    assert normalizada.dados_extraidos == extracao.dados_extraidos
    assert normalizada.sinais_documentais == extracao.sinais_documentais
    assert normalizada.dados_extraidos.medicamentos[0].dosagem_texto is None
    assert _normalizar_caminhos_multimodais(normalizada) == normalizada


@pytest.mark.parametrize("campo", [
    "dados_extraidos.exame.nome.inexistente",
    "dados_extraidos.exame.resultados[99].valor_texto",
    "dados_extraidos.dados_extraidos.paciente.nome",
    "dados_extraidos.exame.resultados[].valor_texto",
])
def test_multimodal_nao_normaliza_caminho_invalido(campo):
    from mediflow_contracts.models import ExtracaoIA
    from mediflow.extraction.gemini_extractor import _normalizar_caminhos_multimodais
    extracao = ExtracaoIA.model_validate({
        "documento_id": "doc-123", "tipo_documento": "laudo_laboratorial",
        "dados_extraidos": {}, "evidencias": [{"campo": campo, "trecho_documento": "Ficticio", "pagina": 1}],
    })
    assert _normalizar_caminhos_multimodais(extracao) == extracao


@pytest.mark.parametrize("pagina,trecho,erro", [(2, "Ficticio", "página inexistente"), (1, "Inventado", "trecho da evidência")])
def test_multimodal_prefixo_nao_contorna_validacao(monkeypatch, cliente_multimodal, pagina, trecho, erro):
    monkeypatch.setenv("MEDIFLOW_ENABLE_GEMINI_MULTIMODAL", "true")
    cliente_multimodal.models.generate_content.return_value.text = __import__("json").dumps({
        "documento_id": "doc-123", "tipo_documento": "laudo_laboratorial",
        "dados_extraidos": {"exame": {"nome": "Ficticio"}},
        "evidencias": [{"campo": "dados_extraidos.exame.nome", "pagina": pagina, "trecho_documento": trecho}],
    })
    with patch("mediflow.extraction.gemini_extractor.extrair_texto_pdf", return_value="[Página 1]\nFicticio"):
        with pytest.raises(ValueError, match=erro):
            ExtratorGemini().extrair(criar_documento(mime_type="application/pdf", conteudo=b"pdf-ficticio"))


# REGRESSAO_CAMINHOS_TEXTUAIS_V1
@pytest.mark.parametrize(
    "via_pdf",
    [False, True],
    ids=["entrada_textual_direta", "pdf_sem_multimodal"],
)
def test_regressao_caminhos_textuais_normalizados(
    monkeypatch, cliente_multimodal, via_pdf
):
    import json
    from mediflow.rules.motor_deterministico import MotorRegrasDeterministico
    from mediflow_contracts.models import EntradaProcessada, RecuperacaoRAG

    monkeypatch.setenv("MEDIFLOW_ENABLE_GEMINI_MULTIMODAL", "false")

    pares = [
        ("paciente.nome", "Paciente Ficticio"),
        ("exame.nome", "Hemograma"),
        ("exame.conclusao", "Rotina"),
        ("exame.resultados[0].valor_texto", "13,4"),
        ("profissional.nome", "Profissional Ficticio"),
    ]

    payload = {
        "documento_id": "doc-123",
        "tipo_documento": "laudo_laboratorial",
        "dados_extraidos": {
            "paciente": {
                "nome": "Paciente Ficticio",
                "nome_status": "legivel",
            },
            "profissional": {"nome": "Profissional Ficticio"},
            "exame": {
                "nome": "Hemograma",
                "conclusao": "Rotina",
                "resultados": [
                    {"parametro": "Hemoglobina", "valor_texto": "13,4"}
                ],
            },
        },
        "evidencias": [
            {
                "campo": "dados_extraidos." + campo,
                "trecho_documento": trecho,
                "pagina": 1,
                "origem": "documento",
            }
            for campo, trecho in pares
        ],
    }

    cliente_multimodal.models.generate_content.return_value.text = (
        json.dumps(payload)
    )

    texto = "[Página 1]\n" + "\n".join(
        trecho for _, trecho in pares
    )

    extrator = ExtratorGemini()

    if via_pdf:
        with patch(
            "mediflow.extraction.gemini_extractor.extrair_texto_pdf",
            return_value=texto,
        ):
            extracao = extrator.extrair(
                criar_documento(
                    mime_type="application/pdf",
                    conteudo=b"pdf-ficticio",
                )
            )
    else:
        entrada = EntradaTexto(
            documento_id="doc-123",
            canal_origem="teste",
            documento_texto=texto,
        )
        extracao = extrator.extrair_texto(entrada)

    cliente_multimodal.models.generate_content.assert_called_once()

    chamada = cliente_multimodal.models.generate_content.call_args.kwargs
    assert isinstance(chamada["contents"], str)

    assert [e.campo for e in extracao.evidencias] == [
        campo for campo, _ in pares
    ]

    resultado = MotorRegrasDeterministico().decidir(
        extracao,
        entrada=EntradaProcessada(
            tipo_entrada="pdf" if via_pdf else "texto",
            canal_origem="teste",
        ),
        rag=RecuperacaoRAG(),
        alerta_textual_confirmado=False,
    )

    assert resultado.classificacao.indicador_qualidade.valor == 1.0
    assert resultado.decisao_roteamento.regra_principal == "R005"
    assert resultado.decisao_roteamento.requer_revisao_humana is False


@pytest.mark.parametrize(
    "campo",
    [
        "dados_extraidos.exame.nome.inexistente",
        "dados_extraidos.exame.resultados[99].valor_texto",
        "dados_extraidos.dados_extraidos.paciente.nome",
    ],
)
def test_textual_nao_normaliza_caminho_invalido(
    cliente_multimodal, campo
):
    import json

    payload = {
        "documento_id": "doc-123",
        "tipo_documento": "laudo_laboratorial",
        "dados_extraidos": {
            "exame": {"nome": "Hemograma"}
        },
        "evidencias": [
            {
                "campo": campo,
                "trecho_documento": "Hemograma",
                "pagina": 1,
                "origem": "documento",
            }
        ],
    }

    cliente_multimodal.models.generate_content.return_value.text = (
        json.dumps(payload)
    )

    entrada = EntradaTexto(
        documento_id="doc-123",
        canal_origem="teste",
        documento_texto="[Página 1]\nHemograma",
    )

    extracao = ExtratorGemini().extrair_texto(entrada)

    assert extracao.evidencias[0].campo == campo


@pytest.mark.parametrize(
    "pagina,trecho,erro",
    [
        (2, "Hemograma", "página inexistente"),
        (1, "Inventado", "trecho da evidência"),
    ],
)
def test_textual_prefixo_nao_contorna_validacao(
    cliente_multimodal, pagina, trecho, erro
):
    import json

    payload = {
        "documento_id": "doc-123",
        "tipo_documento": "laudo_laboratorial",
        "dados_extraidos": {
            "exame": {"nome": "Hemograma"}
        },
        "evidencias": [
            {
                "campo": "dados_extraidos.exame.nome",
                "trecho_documento": trecho,
                "pagina": pagina,
                "origem": "documento",
            }
        ],
    }

    cliente_multimodal.models.generate_content.return_value.text = (
        json.dumps(payload)
    )

    entrada = EntradaTexto(
        documento_id="doc-123",
        canal_origem="teste",
        documento_texto="[Página 1]\nHemograma",
    )

    with pytest.raises(ValueError, match=erro):
        ExtratorGemini().extrair_texto(entrada)
