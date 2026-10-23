import json
from pathlib import Path
import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from mediflow_contracts.models import EntradaTexto, ExtracaoIA, ResultadoTriagem, Medicamento, ArmazenamentoOCI, Classificacao, DecisaoRoteamento
from mediflow_contracts.routing import gerar_exemplo_de_contrato

ROOT=Path(__file__).resolve().parents[1]

def ler(rel):
    return json.loads((ROOT/rel).read_text(encoding='utf-8'))

@pytest.mark.parametrize('fname,model',[
 ('entrada_texto.schema.json', EntradaTexto),
 ('extracao_ia.schema.json', ExtracaoIA),
 ('resultado_triagem.schema.json', ResultadoTriagem)
])
def test_schema_e_fonte_canonica(fname, model):
    schema=ler('schemas/'+fname)
    Draft202012Validator.check_schema(schema)
    assert schema == model.model_json_schema()

@pytest.mark.parametrize('doc_id', ['DOC-001','DOC-002','DOC-005'])
def test_extracao_e_resultado_validos(doc_id):
    extracao=ler(f'exemplos/{doc_id}_extracao_ia.json')
    resultado=ler(f'exemplos/{doc_id}_resultado.json')
    Draft202012Validator(ler('schemas/extracao_ia.schema.json')).validate(extracao)
    Draft202012Validator(ler('schemas/resultado_triagem.schema.json')).validate(resultado)
    assert ExtracaoIA.model_validate(extracao).documento_id == doc_id
    assert ResultadoTriagem.model_validate(resultado).documento_id == doc_id
    assert resultado['armazenamento_oci']['status'] == 'pendente'
    assert resultado['classificacao']['indicador_qualidade']['valor'] is None
    assert resultado['classificacao']['indicador_qualidade']['calibrado'] is False


def test_entrada_texto_valida():
    dado=ler('exemplos/entrada_texto.json')
    Draft202012Validator(ler('schemas/entrada_texto.schema.json')).validate(dado)
    EntradaTexto.model_validate(dado)


def test_tres_cenarios_compativeis_com_baseline_dia1():
    baseline=ler('baseline_dia1/gabarito_tres_cenarios.json')
    assert len(baseline)==3
    for caso in baseline:
        saida=ler(f"exemplos/{caso['documento_id']}_resultado.json")
        exp=caso['esperado']
        assert saida['documento_id']==caso['documento_id']
        assert saida['classificacao']['tipo_documento']==exp['tipo_documento']
        assert saida['decisao_roteamento']['destino_principal']==exp['destino_principal']
        assert saida['decisao_roteamento']['requer_revisao_humana']==exp['requer_revisao_humana']
        assert saida['decisao_roteamento']['regra_principal']==exp['regra_roteamento']


def test_dosagem_ilegivel_nao_pode_conter_valor():
    with pytest.raises(ValidationError):
        Medicamento(nome='Medicamento Alfa',dosagem_status='ilegivel',dosagem_texto='10 mg')
    m=Medicamento(nome='Medicamento Alfa',dosagem_status='ilegivel',dosagem_texto=None)
    assert m.dosagem_texto is None


def test_oci_nao_declarar_sucesso_sem_evidencia():
    with pytest.raises(ValidationError):
        ArmazenamentoOCI(status='confirmado',bucket='mediflow')
    assert ArmazenamentoOCI().status == 'pendente'


def test_urgencia_e_ambiguidade_coexistem():
    raw=ler('exemplos/DOC-002_extracao_ia.json')
    raw['dados_extraidos']['paciente']={'nome':None,'nome_status':'conflitante'}
    extracao=ExtracaoIA.model_validate(raw)
    res=gerar_exemplo_de_contrato(extracao,formato='pdf',alerta_textual_confirmado=True)
    assert res.decisao_roteamento.regra_principal=='R001'
    assert 'R002' in res.decisao_roteamento.regras_disparadas
    assert res.decisao_roteamento.destino_principal=='fila_prioritaria_avaliacao_humana'
    assert res.validacao.conflitos==['paciente.nome']
    assert res.decisao_roteamento.requer_revisao_humana


def test_urgencia_nao_depende_rag():
    raw=ler('exemplos/DOC-002_extracao_ia.json')
    extra=ExtracaoIA.model_validate(raw)
    res=gerar_exemplo_de_contrato(extra,formato='pdf',alerta_textual_confirmado=True)
    res.rag.status='falha'
    assert res.decisao_roteamento.regra_principal=='R001'
    ResultadoTriagem.model_validate(res.model_dump())


def test_llm_sozinha_nao_pode_acionar_urgencia():
    raw=ler('exemplos/DOC-002_extracao_ia.json')
    # Campo gerado pela LLM nao e evidencia independente.
    assert raw['sinais_documentais']['marcador_urgencia_explicito']
    extra=ExtracaoIA.model_validate(raw)
    res=gerar_exemplo_de_contrato(extra,formato='pdf',alerta_textual_confirmado=False)
    assert res.decisao_roteamento.regra_principal!='R001'


def test_urgencia_exige_revisao():
    out=ler('exemplos/DOC-002_resultado.json')
    out['decisao_roteamento']['requer_revisao_humana']=False
    with pytest.raises(ValidationError):
        ResultadoTriagem.model_validate(out)


def test_status_falha_exige_rota_tecnica():
    out=ler('exemplos/DOC-001_resultado.json')
    out['status']='falha'
    with pytest.raises(ValidationError):
        ResultadoTriagem.model_validate(out)


def test_campos_extra_rejeitados():
    out=ler('exemplos/DOC-001_resultado.json')
    out['diagnostico_inventado']='Nao pode'
    with pytest.raises(ValidationError):
        ResultadoTriagem.model_validate(out)


def test_catalogo_e_destinos_sem_divergencias():
    cats=ler('baseline_dia1/categorias.json')['categorias']
    dest=ler('config/destinos.json')
    assert {c['id'] for c in cats}==set(dest['por_categoria_sem_excecao'])
    assert {c['destino_normal'] for c in cats}==set(dest['por_categoria_sem_excecao'].values())
    assert {c['id']: c['destino_normal'] for c in cats} == dest['por_categoria_sem_excecao']


def test_amostras_aprovadas_presentes():
    casos=ler('baseline_dia1/cenarios.json')['cenarios']
    for c in casos:
        file=ROOT/c['arquivo'].replace('amostras/','amostras/')
        assert file.exists() and file.stat().st_size>100
