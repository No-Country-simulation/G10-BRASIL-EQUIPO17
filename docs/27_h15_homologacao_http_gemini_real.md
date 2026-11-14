# MediFlow — H15: homologação HTTP integrada com Gemini real e FakeOCI

## 1. Objetivo

Registrar a homologação funcional **controlada e local** dos três cenários sintéticos oficiais do MediFlow, passando por **HTTP FastAPI → Gemini real (I2) → confirmação independente no original (I4) → RAG local (I3) → regras determinísticas e LangGraph (I4) → FakeOCI em memória (I5)**, com orquestração I1.

**Escopo da aprovação:** fluxos funcionais observados nas três execuções reais da extração, não homologação final do MVP. A execução não usou Oracle Object Storage real, nem envolveu a interface Streamlit, dados reais de pacientes ou implantação pública.

## 2. Referência da execução

| Item | Valor |
|---|---|
| Data local informada pelo contexto da sessão | 13/11/2026 (BRT) |
| Horário exato da execução | Não capturado nos logs apresentados |
| Branch local | `test/h15-gemini-http-integrado` |
| Commit-base local conhecido | `d9510da` (PR #41 já integrado à `develop`) |
| Modelo Gemini configurado | `gemini-3.1-flash-lite` |
| Ambiente | PowerShell / Windows / servidor HTTP restrito a `127.0.0.1:8001` |
| Aplicação | `mediflow.api.app_gemini_local:app` |
| Armazenamento | `FAKEOCI-SOMENTE-MEMORIA` |
| OCI real / Streamlit | Não executados |
| Credencial | Configurada somente no ambiente local; valor não coletado |

**Observação sobre rastreabilidade:** o commit-base é o último HEAD explicitamente informado anteriormente (`d9510da`), e a branch foi criada a partir dele. Após as execuções, `git rev-parse --short HEAD` confirmou `d9510da` antes do PR. Nenhuma hora precisa de execução, versão do SDK, região, consumo de tokens ou custo foi coletada; não atribuir valores presumidos.

## 3. Pré-condições e regressão

- `develop` local sincronizada com `origin/develop`, commit `d9510da`.
- Suíte offline antes da criação da branch H15: **467 passed, 3 deselected** (15,09 s).
- `compileall` e `git diff --check` executados sem saída de erro.
- Na branch H15, teste específico `tests/test_http_gemini_controlado_local.py`: **13 passed** (1,81 s). Esses 13 testes usam extrator injetado e **não** chamam Gemini nem OCI reais.
- SDK `google.genai` importado com sucesso.
- Endpoint `GET /gemini/estado` informou `gemini_real_habilitado=True`, `rag=local_real`, `decisao=langgraph_e_regras_reais`, `armazenamento=FakeOCI_volatil_em_memoria` e `oci_real=False`.

## 4. Resultados funcionais observados

| Critério | DOC-001 — Rotina | DOC-002 — Urgência | DOC-005 — Ambiguidade |
|---|---|---|---|
| Tipo documental | `laudo_laboratorial` | `laudo_imagem` | `receituario` |
| Status do resultado | `processado` | `aguardando_auditoria` | `aguardando_auditoria` |
| Regra principal | `R005` | `R001` | `R002` |
| Destino principal | `prontuario_documental` | `fila_prioritaria_avaliacao_humana` | `auditoria_humana` |
| Revisão humana | `False` | `True` | `True` |
| RAG | `consultado` | `consultado` | `consultado` |
| Armazenamento reportado | `FAKEOCI-SOMENTE-MEMORIA` | `FAKEOCI-SOMENTE-MEMORIA` | `FAKEOCI-SOMENTE-MEMORIA` |
| Duração observada | **9,36 s** | **66,06 s** | **6,34 s** |
| Número de evidências no resultado | **14** | **10** | **5** |
| SHA-256 resultado × recibo | Igual | Igual | Igual |
| Confiança indicada como calibrada | `False` | `False` | `False` |
| Avaliação funcional | Resultado esperado | Resultado esperado | Resultado esperado |

### 4.1. DOC-001 — Rotina

- Resultado `processado` com regra `R005`, destino `prontuario_documental` e sem revisão humana.
- **14 evidências** documentais presentes no objeto retornado.
- `armazenamento_oci.status=confirmado` na **FakeOCI**.
- Campo `chave_historico` presente, segundo a conferência complementar.
- O SHA-256 do resultado correspondeu ao recibo de upload.

### 4.2. DOC-002 — Urgência

- Resultado `aguardando_auditoria`, regra principal `R001`, destino `fila_prioritaria_avaliacao_humana` e revisão humana `True`.
- Lista observada de regras disparadas: `R001, R005`. **R001 permaneceu principal**, como esperado.
- **10 evidências** documentais no objeto de resultado.
- `armazenamento_oci.status=confirmado` na **FakeOCI**; campos `chave_resultado` e `chave_historico` presentes.
- O SHA-256 do resultado correspondeu ao recibo de upload.
- Duração observada de **66,06 s**. Uma execução isolada não permite concluir causa, número de retries ou latência típica; investigar somente se necessário.
- O código da orquestração possui a verificação de alerta independente no documento original. A saída enviada confirma R001 e sua precedência, mas **não contém um log separado do confirmador**.

### 4.3. DOC-005 — Receita ambígua

- Resultado `aguardando_auditoria`, regra `R002`, destino `auditoria_humana` e revisão humana `True`.
- A primeira dosagem retornou `dosagem_texto = null` (verificação `DosagemNaoInferida=True`) e `dosagem_status = ilegivel`.
- **5 evidências** documentais no objeto retornado.
- `armazenamento_oci.status=confirmado` na **FakeOCI**.
- O SHA-256 do resultado correspondeu ao recibo de upload.

### 4.4. Observações sobre HTTP e persistência

- Os recibos de upload foram retornados e as solicitações `Invoke-RestMethod` de processamento terminaram com sucesso, gerando os objetos de resultado.
- Os **códigos HTTP numéricos** de cada requisição não foram capturados no terminal apresentado. Portanto, o relatório não os preenche retroativamente como `201` ou `200`, mesmo que esses sejam os valores esperados nos testes locais.
- O status `confirmado` refere-se apenas à **FakeOCI em memória**. A leitura independente do resultado armazenado não foi realizada nesta sessão de homologação real; foi coberta anteriormente por testes controlados. O reinício do servidor remove os objetos voláteis.

## 5. Classificação da homologação

**H15 — cenários funcionais HTTP reais: `aprovado_real_controlado_local` (3/3 cenários).**

A aprovação é restrita ao comportamento observado: três documentos sintéticos, Gemini real, RAG local, regras/roteamento e FakeOCI. Não equivale a avaliação estatística de precisão, confiabilidade clínica, desempenho, custo, persistência OCI real ou deploy completo.

## 6. Verificações pendentes antes do PR

1. Confirmar `git rev-parse HEAD` e `git status -sb`; preservar os dois arquivos não rastreados históricos, sem incluí-los no commit.
2. Revisar este relatório e `docs/evidencias/h15_gemini_http_real.json` quanto a identificação de pacientes (mesmo fictícios), segredos, tokens e conteúdo integral dos documentos.
3. Validar a estrutura JSON e executar `git diff --check`.
4. Reexecutar a suíte offline `pytest -q -k "not fluxo_api_com_gemini_real"` e `compileall`; registrar a contagem observada após inclusão da documentação.
5. Criar commit **somente** dos dois arquivos H15; abrir PR para `develop` com CI verde e revisão.
6. Planejar homologação OCI real ponta a ponta separadamente, com orçamento e credenciais próprios, e controles adicionais de segurança.

## 7. Limitações e segurança

- Ambiente de desenvolvimento local, sem autenticação para produção; **não publicar** `app_gemini_local:app` em rede ou internet, não usar `--reload` ou múltiplos workers.
- Não processar dados reais de pacientes. O MediFlow é um protótipo educacional de triagem documental, não uma ferramenta de decisão clínica.
- O uso de Gemini real pode consumir quota e causar custos; as três execuções registradas não quantificam o consumo.
- Não atualizar gabaritos para esconder divergências; registrar falhas e solicitar revisão da equipe.
- Nenhuma chave API, payload clínico integral, resultado JSON integral ou endereço de objeto é persistido no relatório público.
- O relatório é baseado exclusivamente nas saídas fornecidas na sessão; não afirma observabilidade que não foi instrumentada.
