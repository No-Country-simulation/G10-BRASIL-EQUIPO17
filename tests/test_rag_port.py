from mediflow.rag.port import ConsultaRAG, RecuperadorSimulado


def test_simulado_nao_inventa_fontes():
    resultado = RecuperadorSimulado().buscar(ConsultaRAG(texto="qualquer coisa"))
    assert resultado.status == "nao_consultado"
    assert resultado.fontes == []