# MediFlow — Critérios de homologação ponta a ponta do MVP

**Escopo:** protótipo educacional de triagem **documental e administrativa** com arquivos exclusivamente sintéticos. Não realiza diagnóstico, prescrição ou decisão médica.

**Estado das validações — 21/11/2026**

| Validação | Evidência comprovada |
|---|---|
| Demonstração local | 3/3 cenários, com extração de referência e armazenamento simulado em memória (FakeOCI). |
| Extração com Gemini real | 3/3 cenários em fluxo HTTP com armazenamento simulado. |
| Integração com Gemini e OCI reais | 3/3 cenários em fluxo HTTP, com 12 objetos auditados. |
| Persistência e revisão humana na OCI real | Dois cenários textuais, três execuções e uma revisão humana; 14 novos objetos íntegros, 29 históricos preservados e 43 objetos auditados. Extração de referência, sem Gemini real. |
| Extração multimodal híbrida | 3/3 cenários aprovados com Gemini real e FakeOCI; dois PDFs e um PNG, sem OCI real; [relatório](32_homologacao_multimodal_gemini.md). |
| Interface e testes automatizados | Regressão de 24/11/2026: **651 passed, 3 skipped**; CI Python 3.12/3.13 aprovada após o [PR #74](https://github.com/No-Country-simulation/G10-BRASIL-EQUIPO17/pull/74) ([execução](https://github.com/No-Country-simulation/G10-BRASIL-EQUIPO17/actions/runs/45509887206)). O marco anterior de 21/11/2026 teve 624 aprovados e 3 deselecionados. |

**Interpretação:** os três cenários foram comprovados com serviços reais no escopo indicado. A validação de persistência e revisão humana é uma execução distinta. Os controles negativos de falhas externas foram testados com simulação; não se atribui a eles comprovação de falhas reais de provedores. Não há validação clínica. Consulte os [relatórios da integração real](29_h16_homologacao_http_gemini_oci_real.md) e da [persistência e revisão humana](31_h17_homologacao_persistencia_oci_real.md).

**Rastreabilidade:** os códigos H01–H17 identificam critérios e etapas das validações técnicas. Os registros históricos da seção 7 conservam as referências das respectivas execuções. As responsabilidades são descritas pelas frentes técnicas, não por códigos de integrantes.

## 1. Objetivo e fontes de verdade

Comprovar que a integração entre API e orquestração, extração OCR/Gemini, recuperação de referências (RAG), confirmação independente, regras de roteamento, armazenamento OCI, interface e testes processa os três documentos sintéticos oficiais sem inventar dados, sem rebaixar alertas e sem declarar persistência inexistente.

Fontes de referência do repositório:

- `baseline_dia1/cenarios.json` e `baseline_dia1/gabarito_tres_cenarios.json`: cenários e resultados esperados.
- `amostras/pdf/` e `amostras/imagens/`: originais sintéticos presentes no projeto.
- `rules/roteamento.yaml` e `rules/validacao.yaml`: precedência, destinos e validações.
- `src/mediflow_contracts/models.py`: contratos canônicos `ExtracaoIA` e `ResultadoTriagem` v0.1.
- `docs/11_integracao_mvp.md`, `docs/12_api_processamento_triagem.md`, `docs/13_adaptador_persistencia_i1_i5.md`, `docs/14_adaptador_rag_i1_i3.md`, `docs/15_homologacao_extracao_i1_i2.md`: arquitetura e testes parciais.

> Os gabaritos e as regras versionadas constituem a referência dos testes. Divergências devem ser tratadas como defeitos, não como resultados aprovados.

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
- **DOC-002:** paciente `Carlos Almeida Exemplo`, exame `Angiotomografia de tórax`, conclusão textual correspondente a `Achados descritos como compatíveis com tromboembolismo pulmonar agudo`; **a confirmação da R001 deve ocorrer no documento original pelo confirmador independente, nunca apenas pela LLM ou pelo RAG**.
- **DOC-005:** paciente `Fernanda Oliveira Exemplo`, medicamento fictício `Medicamento Alfa (fictício)` e **dosagem não inferida**: `dosagem_texto=null`, com estado compatível com ausência/ilegibilidade; jamais completar dose por suposição.

Para todos: `documento_id` consistente, evidências referentes a texto efetivamente existente (e à página correta quando preenchida), regra/justificativa presentes, prioridades/estados coerentes com os contratos e nenhuma fabricação de confiança calibrada, CID ou dados ausentes.

## 4. Matriz técnica por etapa

| Código | Critério de aceite verificável | Frente técnica | Método de evidência | Situação verificada |
|---|---|---|---|---|
| H01 | Upload de PDF/PNG sintético retorna recibo vinculando `documento_id`, `arquivo_id`, nome, MIME, tamanho e SHA-256 | API e orquestração; Armazenamento OCI | API + inspeção de recibo | Aprovado no fluxo HTTP local com FakeOCI (H14 e H15) e com OCI real (H16, 3/3) |
| H02 | Documento recuperado corresponde byte a byte ao original; adulteração bloqueia processamento | API e orquestração; Armazenamento OCI | Teste negativo SHA-256 e auditoria de integridade | Adulteração testada com simulação; integridade dos 29 objetos históricos e 14 novos verificada por SHA-256 na auditoria OCI real (H17) |
| H03 | A extração classifica e extrai campos no contrato `ExtracaoIA v0.1`, preservando valores ausentes ou ilegíveis | Extração documental | Teste automatizado + chamada Gemini controlada | Aprovado real controlado: Gemini real nos 3 cenários (H15 e H16); custo e tokens não medidos |
| H04 | Evidências possuem trecho real e referência de página válida (ou página nula com trecho verificável) | Extração documental | Teste de integridade textual | Aprovado com simulação; no H15 há evidências nos 3 resultados (14/10/5), sem conferência literal registrada |
| H05 | O recuperador retorna `RecuperacaoRAG` com `fonte_id`, versão e URL verificável quando houver referência; não decide roteamento | Recuperação de referências (RAG); API e orquestração | Testes do recuperador e integração com a API | RAG real local consultado nos 3 cenários do fluxo HTTP (H14 e H15) |
| H06 | O confirmador verifica o alerta do DOC-002 diretamente no original, de modo independente da LLM; R001 tem precedência | Confirmação e regras | Testes com alerta confirmado/não confirmado e ambiguidades concomitantes | Testado localmente; no H15 e na H16 (Gemini real) R001 permaneceu principal no DOC-002; na H16 o marcador foi reconfirmado na auditoria a partir dos bytes gravados na OCI, sem log separado da execução do confirmador |
| H07 | DOC-001/DOC-002/DOC-005 apresentam os destinos, regras, revisão e status previstos na seção 3 | Confirmação e regras; API e orquestração | Testes parametrizados + execução final | Aprovado com simulação (H14), real controlado com Gemini + FakeOCI (H15) e com Gemini + OCI reais (H16), 3/3 |
| H08 | Falha do RAG é registrada como `falha` e não altera a prioridade/decisão do motor de regras | API e orquestração; Recuperação de referências (RAG); Confirmação e regras | Teste negativo com erro injetado | Aprovado com falha RAG simulada e motor deterministico real |
| H09 | OCI grava resultado e histórico da mesma execução; leitura posterior confirma integridade e associação ao arquivo | API e orquestração; Armazenamento OCI | Testes com fake + bucket de desenvolvimento autorizado | Aprovado real controlado: isolado em DOC-001 com fixture (H09, 08/11/2026) e no fluxo HTTP completo nos 3 cenários (H16, 17/11/2026, 12 objetos auditados) |
| H10 | Falha parcial OCI não retorna sucesso nem `armazenamento_oci.status=confirmado` | API e orquestração; Armazenamento OCI | Teste de falha entre gravações | Aprovado com FakeOCI e testes ampliados; falhas na OCI real pendentes |
| H11 | Endpoint `/processar` funciona **somente** em ambiente local autorizado; não publica rota sem composição/configuração segura | API e orquestração | Testes HTTP, flags e Swagger local | Aprovado em aplicacao HTTP local; API principal sem rota de processamento; rotas de revisão humana também restritas às apps locais |
| H12 | Entrada inválida, documento inexistente, falha externa e contrato inconsistente resultam em erro sanitizado e HTTP apropriado | API e orquestração; Extração documental; Armazenamento OCI | Testes 403/404/422/502/503, conforme caso | Testes HTTP locais aprovados; falhas externas reais pendentes |
| H13 | CI Python 3.12/3.13, regressão offline e `compileall` aprovados; controle de exposição de segredos e dados reais | Todas as frentes | Checks GitHub + revisão de diff | Regressão posterior: 651 aprovados e 3 ignorados (24/11/2026), CI pós-merge do PR #74 aprovada em Python 3.12/3.13. Marco histórico: 624 aprovados e 3 deselecionados (21/11/2026). As verificações não substituem auditoria de segurança. |
| H14 | Demonstração documentada dos três cenários, com JSON sanitizado, timestamp, commit e identificador do teste | API e orquestração; Interface e qualidade | Registro de execução e vídeo/roteiro se necessário | Aprovado com simulação (12/11/2026): [`docs/evidencias/h14_demonstracao_local.json`](evidencias/h14_demonstracao_local.json) |
| H15 | Fluxo HTTP com Gemini real produz os resultados da seção 3, sem inventar dados | API e orquestração; Extração documental | Execução local controlada + evidência sanitizada | Aprovado real controlado local 3/3 (13/11/2026), com FakeOCI: [relatório](27_h15_homologacao_http_gemini_real.md) |
| H16 | Fluxo HTTP com Gemini e OCI reais produz os resultados da seção 3, com objetos auditados de forma independente no bucket | API e orquestração; Extração documental; Armazenamento OCI | Execução local controlada + auditoria independente dos objetos OCI | Aprovado real controlado local 3/3 (17/11/2026), bucket `mediflow-docs-dev`, 12 objetos auditados: [relatório](29_h16_homologacao_http_gemini_oci_real.md). Revisão humana validada separadamente no critério seguinte. |
| H17 | Índices por status, gravação e recuperação de revisão humana associada à execução, preservação dos resultados e não herança após reprocessamento | API, armazenamento OCI e testes | Auditoria independente por SHA-256, consulta e reprocessamento | Aprovado real controlado (20/11/2026): 2 cenários textuais, 3 execuções, 3 índices, 1 revisão e 43 objetos íntegros (14 novos e 29 históricos preservados); sem Gemini real. [Relatório](31_h17_homologacao_persistencia_oci_real.md) |

### Complemento de integridade — PR #74 (24/11/2026)

- **Revisão humana:** correções inválidas são rejeitadas com HTTP 422, `CORRECOES_INVALIDAS`, antes da persistência; resultado original preservado.
- **Concorrência:** `RLock` protege o registro concorrente de revisões no mesmo processo; não fornece controle distribuído entre processos ou instâncias.
- **Extração Gemini:** normalização de caminhos de evidências válidos nos modos textual e multimodal, sem modificar valores, trechos ou páginas.
- **Cobertura:** regressão offline de 651 testes aprovados e 3 ignorados, complementada por CI Python 3.12/3.13 aprovada. Não houve nova homologação real de Gemini ou OCI neste PR.

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

## 6. Escopo e interpretação das aprovações

| Área | Evidência registrada |
|---|---|
| Integração de código | API, extração, RAG, confirmação independente, regras, LangGraph, persistência e interface integrados e testados. |
| Serviços reais | Os três cenários foram validados com Gemini e OCI reais. A revisão humana e os índices foram comprovados em validação posterior específica com OCI real e extração de referência. |
| Tratamento de falhas | Os testes de falhas externas utilizam simulações controladas; não comprovam todas as falhas possíveis em provedores reais. |
| Qualidade automatizada | Regressão posterior com 651 testes aprovados e 3 ignorados (24/11/2026); CI Python 3.12/3.13 aprovada após o [PR #74](https://github.com/No-Country-simulation/G10-BRASIL-EQUIPO17/pull/74). A regressão anterior, de 624 aprovados e 3 deselecionados, permanece registrada historicamente. |

**Limite das evidências:** a aprovação nos cenários sintéticos não equivale a certificação clínica ou homologação irrestrita de todos os controles operacionais. Latência foi registrada em ensaios específicos; custo e tokens do Gemini não foram medidos. A interface permanece restrita ao escopo educacional e controlado, com revisor sem autenticação. Os resultados simulados e os resultados com serviços externos devem ser interpretados separadamente.

## 7. Registros de execução

Registros técnicos das execuções controladas, sem dados reais de pacientes ou informações secretas:

| Data/hora (BRT) | Commit | Cenário/caso | Ambiente | Componentes reais/simulados | Esperado | Obtido | Status | Evidência/observação | Frente técnica |
|---|---|---|---|---|---|---|---|---|---|
| 12/11/2026 20:47 | `b178477` | DOC-001 (H14) | Local, TestClient sem rede | Reais: API, RAG, regras, LangGraph. Simulados: extração (fixture), FakeOCI | R005, prontuario_documental, processado | R005, prontuario_documental, processado | Aprovado com simulação | `docs/evidencias/h14_demonstracao_local.json` | API e orquestração; Interface e qualidade |
| 12/11/2026 20:47 | `b178477` | DOC-002 (H14) | Local, TestClient sem rede | Idem | R001, fila_prioritaria_avaliacao_humana, aguardando_auditoria | R001, fila_prioritaria_avaliacao_humana, aguardando_auditoria | Aprovado com simulação | Idem | API e orquestração; Interface e qualidade |
| 12/11/2026 20:47 | `b178477` | DOC-005 (H14) | Local, TestClient sem rede | Idem | R002, auditoria_humana, aguardando_auditoria | R002, auditoria_humana, aguardando_auditoria | Aprovado com simulação | Idem | API e orquestração; Interface e qualidade |
| 13/11/2026 (hora não capturada) | `d9510da` | DOC-001 (H15) | Local, HTTP `127.0.0.1:8001` | Reais: API, Gemini, RAG, regras, LangGraph. Simulado: FakeOCI | R005, prontuario_documental, processado | R005, prontuario_documental, processado (9,36 s) | Aprovado real controlado | `docs/27_h15_homologacao_http_gemini_real.md` | API e orquestração; Extração documental |
| 13/11/2026 (hora não capturada) | `d9510da` | DOC-002 (H15) | Local, HTTP `127.0.0.1:8001` | Idem | R001, fila_prioritaria_avaliacao_humana, aguardando_auditoria | R001 (com R005 disparada), fila_prioritaria_avaliacao_humana, aguardando_auditoria (66,06 s) | Aprovado real controlado | Idem | API e orquestração; Extração documental |
| 13/11/2026 (hora não capturada) | `d9510da` | DOC-005 (H15) | Local, HTTP `127.0.0.1:8001` | Idem | R002, auditoria_humana, aguardando_auditoria | R002, auditoria_humana, aguardando_auditoria; `dosagem_texto=null` (6,34 s) | Aprovado real controlado | Idem | API e orquestração; Extração documental |
| 17/11/2026 14:00 | `b6427d1` + alterações integradas em `e8255fc` | DOC-001/002/005 pela interface Streamlit | Local, `app_demo_local` + Streamlit | Reais: API, RAG, regras, LangGraph, UI. Simulados: extração (fixture), FakeOCI | Resultados da seção 3; revisão humana registrada sem alterar o resultado | 3/3 conforme a seção 3; revisão `corrigir` gravada com `dosagem_texto` original mantido `null` | Aprovado com simulação | QA visual; correções de UI no PR #46 | Equipe |
| 17/11/2026 | `97517b9` → `main` `b303b96` | Suíte completa (H13) | Local Python 3.12.10 + GitHub Actions 3.12/3.13 | Reais: API, RAG, regras, LangGraph. Simulados: extração (fixture), FakeOCI; testes de Gemini real desmarcados | Suíte e CI verdes | 483 passed, 3 deselected; CI verde no PR #12 e no push para `main` | Aprovado | PR #12 | Equipe |
| 17/11/2026 (hora não capturada) | branch `feat/h16-http-gemini-oci-real` (commit não registrado) | DOC-001/002/005 (H16) | Local, `app_h16_local` + bucket `mediflow-docs-dev` (`sa-saopaulo-1`) | Reais: API, Gemini, RAG, confirmador, regras, LangGraph, OCI Object Storage | Resultados da seção 3 | R005/processado, R001/aguardando_auditoria, R002/aguardando_auditoria com `dosagem_texto=null`; 12 objetos auditados | Aprovado real controlado | `docs/29_h16_homologacao_http_gemini_oci_real.md` | Equipe |
| 20/11/2026 | `6a1f74f8ad000fcd01b6640f67c9d8019e34134a` | Índices e revisão humana (H17) | Local + OCI Object Storage real | Reais: API, regras, RAG, LangGraph, OCI. Simulada: extração de referência | Integridade, revisão vinculada e isolamento entre execuções | 43 objetos auditados, 29 históricos preservados, 14 novos; 3 resultados válidos e revisão da primeira execução não herdada | Aprovado real controlado | `docs/31_h17_homologacao_persistencia_oci_real.md` | API, armazenamento e testes |
| 20/11/2026 | PR #67 | Regressão consolidada da interface e API | Local + CI Python 3.12/3.13 | Sem chamadas Gemini reais ou gravações OCI reais | Regressão e compilação aprovadas | 601 passed, 3 deselected; CI verde | Aprovado offline | PR #67 | Equipe |

## 8. Reprodução dos testes sem serviços reais

A partir da raiz do projeto, com dependências já instaladas:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -k "not fluxo_api_com_gemini_real"
.\.venv\Scripts\python.exe -m compileall -q src scripts tests
git diff --check
```

**A regressão offline não requer credenciais Gemini ou OCI.** Os testes utilizam adaptadores controlados quando necessário. As validações reais possuem procedimentos e evidências próprios.

**Última regressão consolidada registrada:** 24/11/2026 — **651 passed, 3 skipped**, sem acionamento real de Gemini ou OCI. CI pós-merge do [PR #74](https://github.com/No-Country-simulation/G10-BRASIL-EQUIPO17/pull/74) aprovada em Python 3.12 e 3.13 ([execução](https://github.com/No-Country-simulation/G10-BRASIL-EQUIPO17/actions/runs/45509887206)). A regressão de 21/11/2026 (**624 passed, 3 deselected**) e a CI do PR #71 permanecem como evidências históricas. [Homologação multimodal e evidências](32_homologacao_multimodal_gemini.md).
