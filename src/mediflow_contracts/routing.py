"""Protótipo puro de decisão documental para TESTES DE CONTRATO do Dia 2.

NAO interpreta imagem/PDF, NAO chama LLM/RAG, NAO consulta OCI.
A evidência de marcador de urgência deve ser confirmada no texto de origem
por módulo determinístico futuro, sem confiar só no texto gerado pela LLM.
"""
import json
from pathlib import Path
import yaml
from .models import (
    ExtracaoIA, ResultadoTriagem, EntradaProcessada, Classificacao, Validacao,
    DecisaoRoteamento, Alerta,
)

RAIZ = Path(__file__).resolve().parents[2]
REGRAS = RAIZ / 'rules' / 'roteamento.yaml'


def contexto_documental(extracao: ExtracaoIA, *, alerta_textual_confirmado: bool) -> tuple[dict, list[str], list[str], list[str]]:
    d = extracao.dados_extraidos
    t = extracao.tipo_documento
    ausentes, ilegiveis, conflitos = [], [], []
    if d.paciente.nome_status != 'legivel':
        campo = 'paciente.nome'
        if d.paciente.nome_status == 'conflitante': conflitos.append(campo)
        elif d.paciente.nome_status == 'ilegivel': ilegiveis.append(campo)
        else: ausentes.append(campo)

    if t == 'receituario':
        if not d.medicamentos:
            ausentes.append('medicamentos[]')
        for i, m in enumerate(d.medicamentos):
            if not m.nome: ausentes.append(f'medicamentos[{i}].nome')
            if m.dosagem_status != 'legivel':
                campo = f'medicamentos[{i}].dosagem_texto'
                if m.dosagem_status == 'conflitante': conflitos.append(campo)
                elif m.dosagem_status == 'ilegivel': ilegiveis.append(campo)
                else: ausentes.append(campo)
    if t in ('laudo_laboratorial','laudo_imagem'):
        if not d.exame.nome: ausentes.append('exame.nome')
        if not d.exame.conclusao: ausentes.append('exame.conclusao')
    if t == 'laudo_laboratorial' and not d.exame.resultados:
        ausentes.append('exame.resultados[]')
    if t == 'solicitacao_exame' and not d.procedimentos:
        ausentes.append('procedimentos[]')
    if t == 'relatorio_alta':
        for k in ['resumo','data_admissao','data_alta']:
            if getattr(d,k) is None: ausentes.append(k)
    if t == 'atestado':
        for k in ['data_emissao','afastamento_periodo']:
            if getattr(d,k) is None: ausentes.append(k)

    critico = bool(ausentes or ilegiveis or conflitos)
    suficiente = not critico and t != 'outro_desconhecido'
    sinais = {
        'marcador_urgencia_explicito_confirmado': alerta_textual_confirmado,
        'ambiguidade_critica': critico,
        'solicitacao_exame_completa': t == 'solicitacao_exame' and suficiente,
        'receituario_completo': t == 'receituario' and suficiente,
        'documento_rotina_completo': t in ('laudo_laboratorial','laudo_imagem','relatorio_alta','atestado') and suficiente,
        'fallback': True
    }
    return sinais, ausentes, ilegiveis, conflitos


def escolher_regra(extracao: ExtracaoIA, *, alerta_textual_confirmado: bool, arquivo_regras: Path = REGRAS):
    configuracao = yaml.safe_load(arquivo_regras.read_text(encoding='utf-8'))
    sinais, ausentes, ilegiveis, conflitos = contexto_documental(extracao, alerta_textual_confirmado=alerta_textual_confirmado)
    regras_por_id = {r['id']: r for r in configuracao['regras']}
    disparadas = [rid for rid in configuracao['precedencia'] if sinais[regras_por_id[rid]['condicao']] and rid != 'R006']
    principal_id = disparadas[0] if disparadas else 'R006'
    if not disparadas: disparadas = ['R006']
    return regras_por_id[principal_id], disparadas, ausentes, ilegiveis, conflitos


def gerar_exemplo_de_contrato(extracao: ExtracaoIA, *, formato: str, alerta_textual_confirmado: bool = False, canal_origem: str = 'teste_sintetico') -> ResultadoTriagem:
    """Produz saída de EXEMPLO. Não é processamento real nem grava na OCI."""
    r, regras, ausentes, ilegiveis, conflitos = escolher_regra(extracao, alerta_textual_confirmado=alerta_textual_confirmado)
    urgencia = r['id'] == 'R001'
    avisos = []
    if urgencia and (ausentes or ilegiveis or conflitos):
        avisos.append('Ambiguidade concomitante preservada; nao reduzir prioridade do alerta.')
    # Explicitamente nao usa sinais da LLM sozinhos para urgencia
    alertas = [Alerta(codigo='ALERTA_DOCUMENTAL', mensagem='Possivel urgencia textual: revisao humana prioritaria.') ] if urgencia else []
    resultado = ResultadoTriagem(
        documento_id=extracao.documento_id,
        status='aguardando_auditoria' if r['requer_revisao_humana'] else 'processado',
        entrada=EntradaProcessada(tipo_entrada=formato, canal_origem=canal_origem),
        classificacao=Classificacao(
            tipo_documento=extracao.tipo_documento,
            nivel_prioridade_documental=r['prioridade'],
            especialidade_texto=extracao.especialidade_texto,
        ),
        dados_extraidos=extracao.dados_extraidos,
        validacao=Validacao(
            integridade_documental='insuficiente' if ausentes or ilegiveis or conflitos else 'suficiente',
            campos_ausentes=ausentes, campos_ilegiveis=ilegiveis, conflitos=conflitos, observacoes=avisos,
        ),
        evidencias=extracao.evidencias,
        decisao_roteamento=DecisaoRoteamento(
            destino_principal=r['destino'],requer_revisao_humana=r['requer_revisao_humana'],
            regra_principal=r['id'],regras_disparadas=regras,
            justificativa=r['justificativa'],alertas=alertas,
        ),
    )
    return resultado
