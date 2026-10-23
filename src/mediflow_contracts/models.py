"""Contratos MediFlow v0.1. Sem integrações externas; não realiza triagem clínica."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Categoria = Literal[
    'receituario','laudo_laboratorial','laudo_imagem','solicitacao_exame',
    'relatorio_alta','atestado','outro_desconhecido'
]
Destino = Literal[
    'fila_prioritaria_avaliacao_humana','auditoria_humana',
    'auditoria_autorizacoes','fila_farmacia_documental',
    'prontuario_documental','fila_erros_tecnicos'
]
Prioridade = Literal['rotina','possivel_urgencia','indeterminada']
StatusCampo = Literal['legivel','ausente','ilegivel','conflitante']

class Estrito(BaseModel):
    model_config = ConfigDict(extra='forbid', validate_assignment=True)

class EntradaTexto(Estrito):
    contrato_versao: Literal['0.1'] = '0.1'
    documento_id: str = Field(min_length=3, max_length=64, pattern=r'^[A-Za-z0-9][A-Za-z0-9-]*$')
    canal_origem: str = Field(min_length=1, max_length=80)
    documento_texto: str = Field(min_length=1, max_length=100_000)

class Paciente(Estrito):
    nome: str | None = None
    nome_status: StatusCampo = 'ausente'
    identificador: str | None = None
    idade: int | None = Field(default=None, ge=0, le=130)

    @model_validator(mode='after')
    def nome_coerente(self):
        if self.nome_status != 'legivel' and self.nome is not None:
            raise ValueError('nome nao pode ser confirmado em status diferente de legivel')
        if self.nome_status == 'legivel' and not self.nome:
            raise ValueError('nome legivel requer valor')
        return self

class Profissional(Estrito):
    nome: str | None = None
    crm_texto: str | None = None  # apenas transcricao, sem validacao externa

class Medicamento(Estrito):
    nome: str | None = None
    dosagem_texto: str | None = None
    dosagem_status: StatusCampo = 'ausente'

    @model_validator(mode='after')
    def dose_coerente(self):
        if self.dosagem_status != 'legivel' and self.dosagem_texto is not None:
            raise ValueError('dosagem nao pode ser preenchida se nao for legivel')
        if self.dosagem_status == 'legivel' and not self.dosagem_texto:
            raise ValueError('dosagem legivel requer texto')
        return self

class ResultadoLaboratorial(Estrito):
    parametro: str
    valor_texto: str
    unidade: str | None = None

class Exame(Estrito):
    nome: str | None = None
    achados: str | None = None
    conclusao: str | None = None
    resultados: list[ResultadoLaboratorial] = Field(default_factory=list)

class DadosExtraidos(Estrito):
    paciente: Paciente = Field(default_factory=Paciente)
    profissional: Profissional = Field(default_factory=Profissional)
    exame: Exame = Field(default_factory=Exame)
    medicamentos: list[Medicamento] = Field(default_factory=list)
    procedimentos: list[str] = Field(default_factory=list)
    identificacao_guia: str | None = None
    cid_documentado: str | None = None  # apenas se explicitamente presente
    data_emissao: str | None = Field(default=None, pattern=r'^\d{4}-\d{2}-\d{2}$')
    data_solicitacao: str | None = Field(default=None, pattern=r'^\d{4}-\d{2}-\d{2}$')
    data_admissao: str | None = Field(default=None, pattern=r'^\d{4}-\d{2}-\d{2}$')
    data_alta: str | None = Field(default=None, pattern=r'^\d{4}-\d{2}-\d{2}$')
    afastamento_periodo: str | None = None
    resumo: str | None = None
    descricao_documento: str | None = None

class Evidencia(Estrito):
    campo: str
    trecho_documento: str = Field(min_length=1)
    pagina: int | None = Field(default=None, ge=1)
    origem: Literal['documento'] = 'documento'

class SinaisDocumentais(Estrito):
    marcador_urgencia_explicito: bool = False
    transcricao_marcador_urgencia: str | None = None

    @model_validator(mode='after')
    def marcador_coerente(self):
        if self.marcador_urgencia_explicito != bool(self.transcricao_marcador_urgencia):
            raise ValueError('marcador explicito exige transcricao e vice-versa')
        return self

class ExtracaoIA(Estrito):
    contrato_versao: Literal['0.1'] = '0.1'
    documento_id: str
    tipo_documento: Categoria
    especialidade_texto: str | None = None
    dados_extraidos: DadosExtraidos
    evidencias: list[Evidencia] = Field(default_factory=list)
    sinais_documentais: SinaisDocumentais = Field(default_factory=SinaisDocumentais)

class IndicadorQualidade(Estrito):
    valor: float | None = Field(default=None, ge=0, le=1)
    metodo: Literal['nao_calculado','heuristica_completude_consistencia_v0'] = 'nao_calculado'
    calibrado: Literal[False] = False
    criterios: list[str] = Field(default_factory=list)

    @model_validator(mode='after')
    def criterio_metrica(self):
        if self.metodo == 'nao_calculado' and self.valor is not None:
            raise ValueError('nao_calculado exige valor null')
        if self.metodo != 'nao_calculado' and self.valor is None:
            raise ValueError('metrica calculada exige valor')
        return self

class Classificacao(Estrito):
    tipo_documento: Categoria
    nivel_prioridade_documental: Prioridade
    especialidade_texto: str | None = None
    indicador_qualidade: IndicadorQualidade = Field(default_factory=IndicadorQualidade)

class Validacao(Estrito):
    integridade_documental: Literal['suficiente','insuficiente','indeterminada']
    campos_ausentes: list[str] = Field(default_factory=list)
    campos_ilegiveis: list[str] = Field(default_factory=list)
    conflitos: list[str] = Field(default_factory=list)
    observacoes: list[str] = Field(default_factory=list)

class FonteRAG(Estrito):
    fonte_id: str
    titulo: str
    url: str | None = None
    versao: str | None = None
    trecho_relevante: str | None = None

class RecuperacaoRAG(Estrito):
    status: Literal['nao_consultado','consultado','sem_resultados','falha'] = 'nao_consultado'
    fontes: list[FonteRAG] = Field(default_factory=list)
    erro_codigo: str | None = None

    @model_validator(mode='after')
    def fontes_consistentes(self):
        if self.status != 'consultado' and self.fontes:
            raise ValueError('fontes somente quando consulta realizada')
        if self.status == 'consultado' and not self.fontes:
            raise ValueError('consulta com fontes exige pelo menos uma')
        return self

class Alerta(Estrito):
    codigo: str
    mensagem: str

class DecisaoRoteamento(Estrito):
    destino_principal: Destino
    requer_revisao_humana: bool
    regra_principal: Literal['R001','R002','R003','R004','R005','R006','R900']
    regras_disparadas: list[str] = Field(min_length=1)
    justificativa: str = Field(min_length=1)
    versao_regras: Literal['0.1'] = '0.1'
    alertas: list[Alerta] = Field(default_factory=list)

class EntradaProcessada(Estrito):
    tipo_entrada: Literal['texto','pdf','png','jpeg']
    canal_origem: str
    sha256: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    nome_arquivo: str | None = None

class ArmazenamentoOCI(Estrito):
    status: Literal['pendente','confirmado','falha'] = 'pendente'
    bucket: str | None = None
    chave_original: str | None = None
    chave_resultado: str | None = None
    chave_historico: str | None = None

    @model_validator(mode='after')
    def status_real(self):
        if self.status == 'confirmado' and not (self.bucket and self.chave_original and self.chave_resultado and self.chave_historico):
            raise ValueError('status confirmado requer bucket e 3 chaves')
        if self.status != 'confirmado' and any([self.bucket,self.chave_original,self.chave_resultado,self.chave_historico]):
            raise ValueError('nao declarar enderecos OCI como sucesso sem confirmacao')
        return self

class Evento(Estrito):
    codigo: str
    descricao: str
    timestamp_utc: str | None = None

class ResultadoTriagem(Estrito):
    contrato_versao: Literal['0.1'] = '0.1'
    documento_id: str
    status: Literal['recebido','processando','processado','aguardando_auditoria','falha']
    entrada: EntradaProcessada
    classificacao: Classificacao
    dados_extraidos: DadosExtraidos
    validacao: Validacao
    evidencias: list[Evidencia] = Field(default_factory=list)
    rag: RecuperacaoRAG = Field(default_factory=RecuperacaoRAG)
    decisao_roteamento: DecisaoRoteamento
    armazenamento_oci: ArmazenamentoOCI = Field(default_factory=ArmazenamentoOCI)
    eventos: list[Evento] = Field(default_factory=list)

    @model_validator(mode='after')
    def coerencia_encaminhamento(self):
        d = self.decisao_roteamento
        if self.classificacao.nivel_prioridade_documental == 'possivel_urgencia':
            if d.destino_principal != 'fila_prioritaria_avaliacao_humana' or not d.requer_revisao_humana:
                raise ValueError('possivel urgencia exige fila prioritaria e revisao humana')
        if d.destino_principal in ('fila_prioritaria_avaliacao_humana','auditoria_humana','fila_erros_tecnicos') and not d.requer_revisao_humana:
            raise ValueError('destino de excecao exige revisao humana')
        if d.requer_revisao_humana and self.status == 'processado':
            raise ValueError('status processado nao representa pendencia de revisao humana')
        if self.status == 'aguardando_auditoria' and not d.requer_revisao_humana:
            raise ValueError('aguardando_auditoria exige revisao humana')
        if self.status == 'falha' and d.destino_principal != 'fila_erros_tecnicos':
            raise ValueError('falha tecnica exige fila_erros_tecnicos')
        return self
