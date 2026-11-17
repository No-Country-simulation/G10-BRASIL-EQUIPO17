# MediFlow — Critérios de homologação ponta a ponta do MVP

**Escopo:** protótipo educacional de triagem **documental e administrativa** com arquivos exclusivamente sintéticos. Não é sistema clínico, não realiza diagnóstico, prescrição ou decisão médica. **Situação inicial:** critérios definidos; homologação completa ainda não executada.

> **Situação em 17/11/2026 (`develop` em `3968418`):** três cenários aprovados com simulação (H14) e com Gemini real + FakeOCI (H15); interface Streamlit validada visualmente; suíte local com 483 testes aprovados. **Pendente:** Gemini e OCI reais no mesmo fluxo, falhas reproduzidas nos serviços reais, custo/tokens do Gemini e aprovação formal da equipe. O MVP **não** recebe o status *homologado ponta a ponta* (ver regra de bloqueio na seção 6).

**Referência da integração ao criar este documento:** `develop` no commit `cebdf4d` (PR #23 integrado). Revalidar o commit quando os testes forem executados.

## 1. Objetivo e fontes de verdade

Comprovar que a execução integrada I1 (API/orquestração), I2 (extração OCR/Gemini), I3 (RAG de referências), I4 (confirmação independente e regras), I5 (OCI) e apresentação/QA I6 processa os três documentos sintéticos oficiais sem inventar dados, sem rebaixar alertas e sem declarar persistência inexistente.

Fontes de referência do repositório:

- `baseline_dia1/cenarios.json` e `baseline_dia1/gabarito_tres_cenarios.json`: cenários e resultados esperados.
- `amostras/pdf/` e `amostras/imagens/`: originais sintéticos presentes no projeto.
- `rules/roteamento.yaml` e `rules/validacao.yaml`: precedência, destinos e validações.
- `src/mediflow_contracts/models.py`: contratos canônicos `ExtracaoIA` e `ResultadoTriagem` v0.1.
- `docs/11_integracao_mvp.md`, `docs/12_api_processamento_triagem.md`, `docs/13_adaptador_persistencia_i1_i5.md`, `docs/14_adaptador_rag_i1_i3.md`, `docs/15_homologacao_extracao_i1_i2.md`: arquitetura e testes parciais.

> Não alterar gabaritos nem regras para fazer testes passarem. Em caso de divergência, registrar defeito e obter aprovação da equipe para eventual alteração de escopo.

## 2. Estados de aprovação

- **Pendente:** não executado ou dependência indisponível.
- **Aprovado com simulação:** teste automatizado executado com fakes/mocks explicitamente identificados.
- **Aprovado real controlado:** componente verdadeiro executado em ambiente de desenvolvimento restrito, com evidência sanitizada.
- **Reprovado:** divergência contra o gabarito, contrato ou invariante de segurança.
- **Bloqueado:** não é possível executar porque falta integração, credencial autorizada ou implementação.

Uma etapa **aprovada com simulação** não substitui a homologação **real controlada**. A CI verde por si só não comprova Gemini/OCI reais.

## 3. Critérios obrigatórios dos três cenários

| ID | Entrada sintética | Classificação | Regra principal | Destino | Revisão humana | Resultado esperado |
|---|---|---|---|---|---|---|
| DOC-001 | `amostras/pdf/DOC-001_laudo_laboratorial_rotina.pdf` | `laudo_laboratorial` | `R005` | `prontuario_documental` | `false` | `processado` |
| DOC-002 | `amostras/pdf/DOC-002_laudo_imagem_alerta.pdf` | `laudo_imagem` | `R001` | `fila_prioritaria_avaliacao_humana` | `true` | `aguardando_auditoria` |
| DOC-005 | `amostras/imagens/DOC-005_receita_ilegivel.png` | `receituario` | `R002` | `auditoria_humana` | `true` | `aguardando_auditoria` |

Verificar também os campos literais do gabarito:

- **DOC-001:** paciente `Marina Lacerda Fictícia`, exame `Hemograma completo`, data documental `18/10/2026` (representação de API pode ser normalizada conforme o contrato, sem mudar o valor factual).
- **DOC-002:** paciente `Carlos Almeida Exemplo`, exame `Angiotomografia de tórax`, conclusão textual correspondente a `Achados descritos como compatíveis com tromboembolismo pulmonar agudo`; **a confirmação da R001 deve ocorrer no documento original por I4, nunca apenas pela LLM ou pelo RAG**.
- **DOC-005:** paciente `Fernanda Oliveira Exemplo`, medicamento fictício `Medicamento Alfa (fictício)` e **dosagem não inferida**: `dosagem_texto=null`, com estado compatível com ausência/ilegibilidade; jamais completar dose por suposição.

Para todos: `documento_id` consistente, evidências referentes a texto efetivamente existente (e à página correta quando preenchida), regra/justificativa presentes, prioridades/estados coerentes com os contratos e nenhuma fabricação de confiança calibrada, CID ou dados ausentes.

## 4. Matriz técnica por etapa

| Código | Critério de aceite verificável | Dono | Método de evidência | Situação registrada |
|---|---|---|---|---|
| H01 | Upload de PDF/PNG sintético retorna recibo vinculando `documento_id`, `arquivo_id`, nome, MIME, tamanho e SHA-256 | I1/I5 | API + inspeção de recibo | Aprovado no fluxo HTTP local com FakeOCI (H14 e H15); com OCI real, apenas isolado (H09) |
| H02 | Documento recuperado corresponde byte a byte ao original; adulteração bloqueia processamento | I1/I5 | Teste negativo SHA-256 | Aprovado com simulação em testes anteriores; revalidar integração |
| H03 | I2 classifica e extrai campos no contrato `ExtracaoIA v0.1`, sem valores inventados | I2 | Teste automatizado + chamada Gemini controlada | Aprovado real controlado: Gemini real nos 3 cenários (H15); custo e tokens não medidos |
| H04 | Evidências possuem trecho real e referência de página válida (ou página nula com trecho verificável) | I2 | Teste de integridade textual | Aprovado com simulação; no H15 há evidências nos 3 resultados (14/10/5), sem conferência literal registrada |
| H05 | I3 retorna `RecuperacaoRAG` com `fonte_id`, versão e URL verificável quando houver referência; não decide roteamento | I3/I1 | Testes do recuperador definitivo + I1 | RAG real local consultado nos 3 cenários do fluxo HTTP (H14 e H15) |
| H06 | I4 confirma alerta do DOC-002 diretamente no original, de modo independente da LLM; R001 tem precedência | I4 | Testes com alerta confirmado/não confirmado e ambiguidades concomitantes | Testado localmente; no H15 (Gemini real) R001 permaneceu principal no DOC-002, sem log separado do confirmador |
| H07 | DOC-001/DOC-002/DOC-005 apresentam os destinos, regras, revisão e status previstos na seção 3 | I4/I1 | Testes parametrizados + execução final | Aprovado com simulação (H14) e real controlado com Gemini + FakeOCI (H15), 3/3 |
| H08 | Falha do RAG é registrada como `falha` e não altera a prioridade/decisão do I4 | I1/I3/I4 | Teste negativo com erro injetado | Aprovado com falha RAG simulada e motor deterministico real |
| H09 | OCI grava resultado e histórico da mesma execução; leitura posterior confirma integridade e associação ao arquivo | I1/I5 | Testes com fake + bucket de desenvolvimento autorizado | Aprovado real controlado em DOC-001 com fixture (08/11/2026); nao ponta a ponta |
| H10 | Falha parcial OCI não retorna sucesso nem `armazenamento_oci.status=confirmado` | I1/I5 | Teste de falha entre gravações | Aprovado com FakeOCI e testes ampliados; falhas na OCI real pendentes |
| H11 | Endpoint `/processar` funciona **somente** em ambiente local autorizado; não publica rota sem composição/configuração segura | I1 | Testes HTTP, flags e Swagger local | Aprovado em aplicacao HTTP local; API principal sem rota de processamento; rotas de revisão humana também restritas às apps locais |
| H12 | Entrada inválida, documento inexistente, falha externa e contrato inconsistente resultam em erro sanitizado e HTTP apropriado | I1/I2/I5 | Testes 403/404/422/502/503, conforme caso | Testes HTTP locais aprovados; falhas externas reais pendentes |
| H13 | CI Python 3.12/3.13, suíte completa e `compileall` aprovados, sem segredos ou arquivos reais no Git | Todos | Checks GitHub + revisão de diff | Suíte local: 483 aprovados em `3968418` (17/11/2026); CI do commit final a confirmar |
| H14 | Demonstração documentada dos três cenários, com JSON sanitizado, timestamp, commit e identificador do teste | I1/I6 | Registro de execução e vídeo/roteiro se necessário | Aprovado com simulação (12/11/2026): [`docs/evidencias/h14_demonstracao_local.json`](evidencias/h14_demonstracao_local.json) |
| H15 | Fluxo HTTP com Gemini real produz os resultados da seção 3, sem inventar dados | I1/I2 | Execução local controlada + evidência sanitizada | Aprovado real controlado local 3/3 (13/11/2026), com FakeOCI: [relatório](27_h15_homologacao_http_gemini_real.md) |

## 5. Testes de falha e segurança (obrigatórios)

- SHA-256/tamanho/identificador ou associação de `arquivo_id` adulterados: recusar antes de invocar extração e persistência.
- LLM menciona urgência, mas documento original não contém confirmação independente: **não acionar R001**.
- Documento original possui alerta confirmado e há ambiguidade: **R001 permanece principal** e a ambiguidade é preservada.
- RAG indisponível: registrar falha sem inventar fonte nem rebaixar decisão.
- OCR/Gemini indisponíveis, resposta inválida ou evidência inventada: não responder com triagem processada; retornar erro seguro.
- OCI falha entre histórico e resultado: não retornar armazenamento confirmado; identificar necessidade de reconciliação operacional.
- Dois `arquivo_id` no mesmo `documento_id`: impedir mistura de metadados, RAG, histórico e resultados.
- Verificar comportamento para repetição da chamada: registrar a política de idempotência/reprocessamento antes de habilitar acesso público.
- Nunca imprimir documentos completos, chaves, tokens ou credenciais nos logs, PRs ou evidências.

## 6. Portões de aprovação

### P0 — Critérios definidos (agora)

- [ ] Matriz de cenários validada pelos responsáveis I1, I2, I3, I4, I5 e I6.
- [ ] Dependências bloqueantes e responsáveis identificados; nenhuma etapa real marcada como executada.
- [x] Documento versionado por PR para `develop`, com checks verdes.

### P1 — Integração de código

- [x] Recuperador RAG real integrado e testado localmente (PR #16).
- [x] Confirmador independente, motor de regras e LangGraph integrados (PR #33).
- [x] Orquestracao integrada com extracao por fixture, RAG, LangGraph e FakeOCI (PR #37).
- [x] Rota de processamento registrada na aplicacao demonstrativa local (PRs #31 e #42).
- [ ] Integrar Gemini e persistencia OCI reais ao processamento completo. *(Gemini real integrado e homologado no H15; OCI real ainda fora do fluxo completo.)*
- [x] Interface Streamlit e revisão humana integradas às APIs locais (PR #46).

### P2 — Execução controlada de serviços reais

- [ ] Gemini real homologado com documentos sintéticos, custo/latência anotados e sem segredos. *(Homologado no H15 com latência por cenário e sem segredos; custo e tokens não medidos.)*
- [x] Persistencia OCI real homologada com fixture DOC-001 (H09); fluxo completo pendente.
- [x] DOC-001, DOC-002 e DOC-005 passaram nos resultados da seção 3 sem correção manual oculta (H14 e H15).
- [ ] Falhas obrigatórias da seção 5 reproduzidas e registradas. *(Cobertas com fakes em H08, H10 e H12; não reproduzidas nos serviços reais.)*

### P3 — Liberação do MVP demonstrável

- [ ] Suíte automatizada e CI 3.12/3.13 verdes no commit candidato. *(Suíte local verde em `3968418`; confirmar a CI no commit promovido para `main`.)*
- [x] Evidências anexadas ao PR/relatório: commit, ambiente, execução, resultado, limitações (H09, H14, H15).
- [x] README e procedimento de execução atualizados, sem segredos.
- [ ] Equipe aprova explicitamente o **protótipo educacional**; nenhuma divulgação como uso clínico ou deploy público.

**Regra de bloqueio:** o MVP só recebe status *homologado ponta a ponta* quando todos os três cenários e os controles essenciais forem comprovados com os componentes reais aplicáveis. Os fakes não podem ser apresentados como integração real.

## 7. Modelo de registro de execução

Copiar uma linha por execução, sem incluir dados clínicos não sintéticos ou informações secretas:

| Data/hora (BRT) | Commit | Cenário/caso | Ambiente | Componentes reais/simulados | Esperado | Obtido | Status | Evidência/observação | Responsável |
|---|---|---|---|---|---|---|---|---|---|
| 12/11/2026 20:47 | `b178477` | DOC-001 (H14) | Local, TestClient sem rede | Reais: API, RAG, regras, LangGraph. Simulados: extração (fixture), FakeOCI | R005, prontuario_documental, processado | R005, prontuario_documental, processado | Aprovado com simulação | `docs/evidencias/h14_demonstracao_local.json` | I1/I6 |
| 12/11/2026 20:47 | `b178477` | DOC-002 (H14) | Local, TestClient sem rede | Idem | R001, fila_prioritaria_avaliacao_humana, aguardando_auditoria | R001, fila_prioritaria_avaliacao_humana, aguardando_auditoria | Aprovado com simulação | Idem | I1/I6 |
| 12/11/2026 20:47 | `b178477` | DOC-005 (H14) | Local, TestClient sem rede | Idem | R002, auditoria_humana, aguardando_auditoria | R002, auditoria_humana, aguardando_auditoria | Aprovado com simulação | Idem | I1/I6 |
| 13/11/2026 (hora não capturada) | `d9510da` | DOC-001 (H15) | Local, HTTP `127.0.0.1:8001` | Reais: API, Gemini, RAG, regras, LangGraph. Simulado: FakeOCI | R005, prontuario_documental, processado | R005, prontuario_documental, processado (9,36 s) | Aprovado real controlado | `docs/27_h15_homologacao_http_gemini_real.md` | I1/I2 |
| 13/11/2026 (hora não capturada) | `d9510da` | DOC-002 (H15) | Local, HTTP `127.0.0.1:8001` | Idem | R001, fila_prioritaria_avaliacao_humana, aguardando_auditoria | R001 (com R005 disparada), fila_prioritaria_avaliacao_humana, aguardando_auditoria (66,06 s) | Aprovado real controlado | Idem | I1/I2 |
| 13/11/2026 (hora não capturada) | `d9510da` | DOC-005 (H15) | Local, HTTP `127.0.0.1:8001` | Idem | R002, auditoria_humana, aguardando_auditoria | R002, auditoria_humana, aguardando_auditoria; `dosagem_texto=null` (6,34 s) | Aprovado real controlado | Idem | I1/I2 |
| 17/11/2026 14:00 | `b6427d1` + alterações integradas em `e8255fc` | DOC-001/002/005 pela interface Streamlit | Local, `app_demo_local` + Streamlit | Reais: API, RAG, regras, LangGraph, UI. Simulados: extração (fixture), FakeOCI | Resultados da seção 3; revisão humana registrada sem alterar o resultado | 3/3 conforme a seção 3; revisão `corrigir` gravada com `dosagem_texto` original mantido `null` | Aprovado com simulação | QA visual; correções de UI no PR #46 | Equipe |

## 8. Execução preliminar sem serviços reais

A partir da raiz do projeto, com dependências já instaladas:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -k "not fluxo_api_com_gemini_real"
.\.venv\Scripts\python.exe -m compileall -q src scripts tests
git diff --check
```

**Não** configurar chaves/ativar serviços externos para concluir P0. Testes de Gemini e OCI reais ocorrerão separadamente, com autorização e controle de custos. O resultado local deve ser marcado como **baseline simulada**, não como homologação final.

**Última baseline registrada:** 17/11/2026, `develop` em `3968418`: **483 passed, 3 deselected**; `compileall` e `git diff --check` sem erros.
