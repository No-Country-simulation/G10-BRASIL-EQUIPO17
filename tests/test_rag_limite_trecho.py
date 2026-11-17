import pytest

from mediflow.rag.busca import FonteDocumento, RecuperadorPorPalavras
from mediflow.rag.port import ConsultaRAG


@pytest.mark.parametrize("limite", [0, -1])
def test_limite_invalido_e_recusado(limite):
    with pytest.raises(ValueError):
        ConsultaRAG(texto="receituario", limite=limite)


def test_trecho_vem_da_linha_com_os_termos():
    fonte = FonteDocumento(
        fonte_id="X-1",
        titulo="Ficha",
        texto=(
            "Linha inicial sem relacao alguma.\n"
            "O receituario exige dosagem legivel do medicamento.\n"
            "Fim."
        ),
        versao="0.1",
    )
    resultado = RecuperadorPorPalavras([fonte]).buscar(
        ConsultaRAG(texto="dosagem do medicamento")
    )
    assert resultado.status == "consultado"
    trecho = resultado.fontes[0].trecho_relevante
    assert "dosagem" in trecho
    assert "Linha inicial" not in trecho
