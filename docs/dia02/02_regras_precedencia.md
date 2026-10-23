# Dia 2 — Catálogo formal de regras documentais `v0.1`

Os arquivos `rules/roteamento.yaml` e `rules/validacao.yaml` são **regras locais fictícias para testes**, não protocolos clínicos. Mantemos os IDs R001–R006 do kit e do Dia 1.

| ID | Condição verificável | Ação principal |
|---|---|---|
| R001 | Marcador de alerta **confirmado no próprio documento** | Priorizar avaliação humana |
| R002 | Ausência, ilegibilidade ou contradição crítica | Auditoria humana |
| R003 | Solicitação de exame/procedimento documentalmente suficiente | Auditoria administrativa de autorizações |
| R004 | Receituário completo para fins documentais | Farmácia documental (sem dispensação) |
| R005 | Laudo, alta ou atestado documentalmente suficiente | Prontuário documental simulado |
| R006 | Qualquer outro caso | Auditoria humana |

**Precedência:** `R001 > R002 > R003 > R004 > R005 > R006`.

A decisão registra a regra principal e todas as disparadas. Quando urgência e ambiguidade coexistem, o alerta prioritário permanece, bem como as observações de ambiguidade. Não há inferência diagnóstica.

### Origem do alerta
A extração por LLM pode indicar um possível marcador, mas o **flag que aciona R001 deverá ser confirmado por verificação independente do conteúdo original**. O protótipo de teste recebe esse sinal explicitamente como entrada confiável; a etapa de verificação sobre texto bruto será implementada futuramente. Se RAG falhar, R001 não depende do RAG.

### Validação por classe
- `receituario`: paciente, pelo menos um medicamento, nome e dosagem legível; em falha, revisão humana.
- `laudo_laboratorial`: paciente, nome do exame, conclusão e resultados. Falta de valores retorna auditoria, não interpretação clínica.
- `laudo_imagem`: paciente, nome do exame e conclusão. Conclusão faltante encaminha à auditoria.
- `solicitacao_exame`: paciente e procedimentos; ausência leva à auditoria.
- `relatorio_alta`: paciente, resumo, datas de admissão e alta.
- `atestado`: paciente, emissão e afastamento.
- `outro_desconhecido`: auditoria humana.

O nome de profissional ausente (`V003`) gera advertência, mas não é automaticamente tratado como urgência clínica. A equipe poderá ampliar critérios após testes com corpus sintético e revisão especializada.

### Falhas externas
LLM ausente, retorno inválido, PDF corrompido, OCI indisponível ou tratamento incompleto **não devem ser convertidos em sucesso**. O grafo deve registrar falha técnica e bloquear roteamento de rotina; sinal explícito de prioridade já detectado deve ser preservado para avaliação humana. Definir procedimento de contingência operacional na implementação.
