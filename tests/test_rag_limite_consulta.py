import pytest

from mediflow.rag.port import ConsultaRAG


@pytest.mark.parametrize("invalido", [0, -1, 11, True, 1.5, "3"])
def test_limite_invalido_e_recusado(invalido):
    with pytest.raises(ValueError):
        ConsultaRAG(texto="receituario", limite=invalido)


@pytest.mark.parametrize("valido", [1, 3, 10])
def test_limite_valido_e_aceito(valido):
    assert ConsultaRAG(texto="receituario", limite=valido).limite == valido


def test_limite_padrao_continua_valido():
    assert ConsultaRAG(texto="receituario").limite == 3
