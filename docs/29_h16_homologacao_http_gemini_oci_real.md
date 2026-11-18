# MediFlow — H16: Homologação HTTP Gemini + OCI reais

Data: 17/11/2026
Ambiente: desenvolvimento local
Branch: feat/h16-http-gemini-oci-real
Bucket: mediflow-docs-dev
Região: sa-saopaulo-1

## DOC-001 — Rotina

Status: APROVADO — execução real controlada.

### Processamento
- HTTP upload: 201
- HTTP processamento: 200
- Gemini: extração real integrada
- RAG: consultado
- Regra principal: R005
- Destino: prontuario_documental
- Status: processado
- Persistência reportada: confirmado

### Auditoria independente OCI
- Manifesto: OK
- Original: OK
- SHA-256 original: OK
- Resultado Pydantic v0.1: OK
- Histórico e eventos: OK
- Objetos verificados: 4
- Execução e referências cruzadas: consistentes

Resultado final: AUDITORIA_H16_DOC001: APROVADA

## Limitações
- Evidência restrita ao documento sintético DOC-001.
- Não comprova desempenho, custo zero ou precisão clínica.
- Não houve coleta de métricas de tokens ou duração total.
- DOC-005 homologado no escopo tecnico da H16.
- Não publicar a API sem autenticação e controles adicionais.
- Não repetir processamento automaticamente.

## Estado H16
DOC-001: APROVADO
DOC-002: APROVADO
DOC-005: APROVADO

## DOC-002 — Urgência

Status: APROVADO — execução real controlada.

### Processamento
- HTTP upload: 201
- HTTP processamento: 200
- Regras disparadas: R001, R005
- Regra principal: R001
- Prioridade: possivel_urgencia
- Destino: fila_prioritaria_avaliacao_humana
- Revisão humana: obrigatória
- Status: aguardando_auditoria
- RAG: consultado
- Evidências documentais: 11
- Persistência reportada: confirmado

### Auditoria independente OCI
- Manifesto e original: OK
- SHA-256 original: OK
- Marcador explícito confirmado novamente no PDF original
- Precedência R001 sobre R005: OK
- Resultado Pydantic v0.1: OK
- Histórico, eventos e referências cruzadas: OK
- Objetos verificados: 4

Resultado final: AUDITORIA_H16_DOC002: APROVADA

Observação: a confirmação independente foi reproduzida na
auditoria usando os bytes armazenados na OCI. Não foi coletado
um log separado da execução anterior do confirmador I4.


## DOC-005 — Ambiguidade documental

Status: APROVADO — execução real controlada.

### Processamento
- HTTP upload: 201
- HTTP processamento: 200
- Tipo documental: receituario
- Regra principal: R002
- Destino: auditoria_humana
- Prioridade: indeterminada
- Revisão humana: obrigatória
- Status: aguardando_auditoria
- RAG: consultado
- Evidências documentais: 5
- Medicamentos identificados: 1
- dosagem_texto: null
- dosagem_status: ilegivel

### Auditoria independente OCI
- Manifesto: OK
- Original e SHA-256: OK
- Alerta explícito de urgência: ausente
- Resultado Pydantic v0.1: OK
- Regra R002 e revisão humana: OK
- Dosagem não inferida: OK
- Campo ilegível registrado: OK
- Histórico e referências cruzadas: OK
- Objetos verificados: 4

Resultado final: AUDITORIA_H16_DOC005: APROVADA

## Conclusão da H16

Status: HOMOLOGAÇÃO TÉCNICA APROVADA — 3/3 cenários.

- DOC-001: R005 — APROVADO
- DOC-002: R001 — APROVADO
- DOC-005: R002 — APROVADO
- Total: 12 objetos auditados independentemente.

Escopo: FastAPI local, Gemini real, RAG local, confirmação
independente I4, regras/LangGraph e OCI Object Storage real.

Limitações: não constitui validação clínica, avaliação
estatística de precisão, garantia de custo zero, homologação
de segurança para produção ou autorização de uso público.
