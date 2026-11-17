from mediflow.rag.busca import FonteDocumento, RecuperadorPorPalavras
from mediflow.rag.port import ConsultaRAG

# Fontes de EXEMPLO só para teste. A base real vem da curadoria.
FONTES = [
    FonteDocumento("TESTE-RECEITA", "Ficha de teste: receita",
                   "Receita com paciente medico crm medicamento dosagem", versao="0.1"),
    FonteDocumento("TESTE-LAUDO", "Ficha de teste: laudo",
                   "Laudo com paciente medico crm exame conclusao", versao="0.1"),
]


def test_encontra_fonte_certa_e_cita_a_origem():
    r = RecuperadorPorPalavras(FONTES).buscar(ConsultaRAG("dosagem do medicamento"))
    assert r.status == "consultado"
    assert r.fontes[0].fonte_id == "TESTE-RECEITA"


def test_sem_resultados_nao_inventa_fonte():
    r = RecuperadorPorPalavras(FONTES).buscar(ConsultaRAG("assunto totalmente fora"))
    assert r.status == "sem_resultados"
    assert r.fontes == []


def test_consulta_vazia_nao_quebra():
    r = RecuperadorPorPalavras(FONTES).buscar(ConsultaRAG(""))
    assert r.status == "sem_resultados"


def test_respeita_o_limite():
    r = RecuperadorPorPalavras(FONTES).buscar(ConsultaRAG("paciente medico crm", limite=1))
    assert len(r.fontes) == 1