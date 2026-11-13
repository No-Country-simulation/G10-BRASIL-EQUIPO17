"""
Configuração central da interface MediFlow.

Tudo o que depende do back-end (URL, endpoints, timeouts, vocabulário do
contrato) está concentrado aqui, para que a equipa de API possa ajustar o
contrato sem mexer nas páginas. Os valores podem ser sobrepostos por
variáveis de ambiente.

O vocabulário segue o contrato v0.1 (`src/mediflow_contracts/models.py`,
fonte canónica) e os ficheiros `config/destinos.json`, `rules/roteamento.yaml`
e `baseline_dia1/categorias.json` do monorepo.
"""

import os

# --------------------------------------------------------------------------- #
# Ligação à API FastAPI
# --------------------------------------------------------------------------- #
API_BASE_URL: str = os.getenv("MEDIFLOW_API_URL", "http://127.0.0.1:8000").rstrip("/")
API_TIMEOUT: float = float(os.getenv("MEDIFLOW_API_TIMEOUT", "120"))

CONTRACT_VERSION = "0.1"
# Valor de `canal_origem` enviado pela interface em cada triagem.
SOURCE_CHANNEL = "interface_streamlit"

# Endpoints. Se o back-end usar outros caminhos, basta alterar aqui.
ENDPOINTS = {
    # Envio em duas etapas (src/mediflow/api/uploads.py e triage_processing.py):
    # 1) POST multipart documento_id, canal_origem, arquivo -> ReciboArquivo (201)
    # 2) POST .../processar -> ResultadoTriagem
    "upload": "/v1/triagens/arquivos",
    "process": "/v1/triagens/arquivos/{doc_id}/{file_id}/processar",
    # Contrato v0.1; a API principal ainda responde 501 e as composições locais não a expõem.
    "triage_text": "/v1/triagens/texto",
    # Ainda inexistentes na API (a UI usa o histórico da sessão enquanto isso).
    "triage": "/v1/triagens/{doc_id}",              # GET ResultadoTriagem
    "triage_list": "/v1/triagens",                  # GET ?status= -> lista de ResultadoTriagem
    "review": "/v1/triagens/{doc_id}/revisao",      # POST decisão do auditor
}

# Rotas de estado, testadas por ordem: a API principal expõe /health; as
# composições locais (app_demo_local, app_gemini_local) expõem só o seu estado.
STATUS_ENDPOINTS = {
    "/gemini/estado": "Gemini local",
    "/demo/estado": "Demonstração (fixtures)",
    "/health": "API principal",
}

# --------------------------------------------------------------------------- #
# Ingestão
# --------------------------------------------------------------------------- #
ACCEPTED_FILE_TYPES = ["pdf", "png", "jpg", "jpeg"]
MAX_UPLOAD_MB = 10  # limite proposto no contrato v0.1 (10 MiB)
MAX_PDF_PAGES = 10  # idem: PDFs de até 10 páginas
# Assinatura binária esperada no início de cada formato (o contrato pede validar MIME, assinatura e tamanho).
FILE_SIGNATURES = {"pdf": (b"%PDF-",), "png": (b"\x89PNG\r\n\x1a\n",), "jpg": (b"\xff\xd8\xff",), "jpeg": (b"\xff\xd8\xff",)}

# --------------------------------------------------------------------------- #
# Vocabulário de domínio (rótulos e cores usados em toda a UI)
# --------------------------------------------------------------------------- #
# As páginas usam chaves internas curtas; `contract` é o valor equivalente no
# contrato v0.1 (a tradução é feita só em ui/models.py).
# "badge" é a cor nativa do Streamlit (st.badge / :cor-badge[]); "color" é o hex
# usado em gráficos e tabelas.
# A prioridade usa as cores de semáforo (verde/âmbar/vermelho); os estados usam
# tons frios, para que as duas colunas nunca partilhem a mesma cor na tabela.
PRIORITIES = {
    "rotina": {"label": "Rotina", "contract": "rotina",
               "badge": "green", "color": "#15803d", "icon": ":material/check_circle:"},
    "urgente": {"label": "Possível urgência", "contract": "possivel_urgencia",
                "badge": "red", "color": "#dc2626", "icon": ":material/emergency:"},
    "ambiguidade": {"label": "Indeterminada", "contract": "indeterminada",
                    "badge": "orange", "color": "#d97706", "icon": ":material/help:"},
}

# Estados do contrato (`ResultadoTriagem.status`) e, a seguir, os estados de
# decisão humana, que o contrato v0.1 ainda não modela (extensão da UI).
STATUSES = {
    "received": {"label": "Recebido", "contract": "recebido",
                 "badge": "gray", "color": "#94a3b8", "icon": ":material/inbox:"},
    "processing": {"label": "Processando", "contract": "processando",
                   "badge": "gray", "color": "#64748b", "icon": ":material/hourglass_top:"},
    "processed": {"label": "Processado", "contract": "processado",
                  "badge": "primary", "color": "#0f766e", "icon": ":material/task_alt:"},
    "pending_review": {"label": "Aguardando auditoria", "contract": "aguardando_auditoria",
                       "badge": "violet", "color": "#7c3aed", "icon": ":material/pending:"},
    "error": {"label": "Falha técnica", "contract": "falha",
              "badge": "red", "color": "#9f1239", "icon": ":material/error:"},
    "approved": {"label": "Aprovado", "badge": "blue", "color": "#2563eb", "icon": ":material/verified:"},
    "corrected": {"label": "Corrigido", "badge": "blue", "color": "#0891b2", "icon": ":material/edit_note:"},
    "rejected": {"label": "Rejeitado", "badge": "gray", "color": "#64748b", "icon": ":material/block:"},
}

# Ação da revisão humana -> estado mostrado na UI.
REVIEW_STATUSES = {"aprovar": "approved", "corrigir": "corrected", "rejeitar": "rejected"}

# Filas de destino (`decisao_roteamento.destino_principal`, config/destinos.json).
DESTINATIONS = {
    "fila_prioritaria_avaliacao_humana": "Fila prioritária",
    "auditoria_humana": "Auditoria humana",
    "auditoria_autorizacoes": "Auditoria de autorizações",
    "fila_farmacia_documental": "Farmácia documental",
    "prontuario_documental": "Prontuário",
    "fila_erros_tecnicos": "Erros técnicos",
}

# Categorias estáveis (`classificacao.tipo_documento`, baseline_dia1/categorias.json).
DOCUMENT_TYPES = {
    "receituario": "Receituário médico",
    "laudo_laboratorial": "Laudo laboratorial",
    "laudo_imagem": "Laudo de imagem",
    "solicitacao_exame": "Solicitação de exame",
    "relatorio_alta": "Relatório de alta",
    "atestado": "Atestado médico",
    "outro_desconhecido": "Outro/desconhecido",
}

# Catálogo de regras (rules/roteamento.yaml). R900 está reservada no contrato
# para falhas técnicas.
RULES = {
    "R001": {"name": "Marcador de urgência no documento", "severity": "critical",
             "description": "Marcador explícito de alerta no documento. Exige avaliação humana prioritária.",
             "effect": "Fila prioritária · revisão humana"},
    "R002": {"name": "Ambiguidade crítica", "severity": "high",
             "description": "Campo essencial ausente, ilegível ou conflitante; requer conferência humana.",
             "effect": "Auditoria humana · prioridade indeterminada"},
    "R003": {"name": "Solicitação de exame completa", "severity": "info",
             "description": "Solicitação documental com campos essenciais presentes.",
             "effect": "Auditoria de autorizações"},
    "R004": {"name": "Receituário completo", "severity": "info",
             "description": "Receituário completo para fila documental, sem dispensação automática.",
             "effect": "Farmácia documental"},
    "R005": {"name": "Documento de rotina completo", "severity": "info",
             "description": "Documento de rotina com integridade administrativa suficiente.",
             "effect": "Prontuário"},
    "R006": {"name": "Sem condições de roteamento automático", "severity": "medium",
             "description": "Documento sem condições para roteamento documental automático.",
             "effect": "Auditoria humana"},
    "R900": {"name": "Falha técnica", "severity": "critical",
             "description": "O processamento falhou e não pode ser tratado como rotina.",
             "effect": "Erros técnicos"},
}

# Estado de um campo extraído (`StatusCampo`) quando não é legível.
FIELD_STATUS_LABELS = {"ausente": "(ausente)", "ilegivel": "(ilegível)", "conflitante": "(conflitante)"}

# Sinalizações derivadas da validação e da decisão -> texto legível.
FLAG_LABELS = {
    "alerta_critico": "Marcador de urgência no documento",
    "dosagem_ilegivel": "Dosagem ilegível",
    "campo_ilegivel": "Campo ilegível",
    "campo_em_falta": "Campo obrigatório ausente",
    "campo_conflitante": "Campo conflitante",
    "integridade_insuficiente": "Integridade documental insuficiente",
    "sem_roteamento_automatico": "Sem roteamento automático",
    "falha_tecnica": "Falha técnica no processamento",
    "baixa_confianca": "Indicador de qualidade baixo",
}

# Estados finais de um documento tratado com sucesso (KPI "Concluídos").
DONE_STATUSES = ("processed", "approved", "corrected")

# Intervalo de atualização automática da Visão geral.
DASHBOARD_REFRESH = "30s"

# Abaixo deste valor do indicador de qualidade o documento é destacado.
# No contrato v0.1 o indicador vem `null` (não calculado) e não é calibrado.
LOW_CONFIDENCE_THRESHOLD = 0.70
