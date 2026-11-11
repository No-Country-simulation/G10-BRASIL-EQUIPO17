# MediFlow — H12: tratamento seguro de erros da API I1

**Estado:** aprovado com simulação local; validação CI pendente. Homologação real ponta a ponta ainda não realizada.

**Escopo:** testes de contrato HTTP e sanitização do router de processamento documental I1 com `FakeOCI` e `ServicoSimulado`. Documentos e marcadores de credenciais são **sintéticos**. Não há chamadas à OCI, Gemini, RAG ou LangGraph reais, nem mudança no motor I4. O endpoint `/processar` permanece **não registrado** no `app.py` principal.

## Objetivo

Ampliar a evidência do critério H12 de `docs/16_criterios_homologacao_mvp.md`: falhas de armazenamento, entradas/manifestos indisponíveis, erros de orquestração e resultados incompatíveis devem produzir códigos HTTP previsíveis, mensagem sanitizada e nenhuma triagem aparentemente bem-sucedida.

## Arquivos deste incremento

| Arquivo | Finalidade |
|---|---|
| `tests/test_h12_erros_api_i1.py` | 21 casos parametrizados e isolados de falha HTTP, sem acesso à rede |
| `docs/20_h12_tratamento_seguro_erros_api_i1.md` | Matriz, limites e evidências |

**Não modificar nesta entrega:** `src/mediflow/api/app.py`, `src/mediflow/api/triage_processing.py`, contratos v0.1 e implementações I2/I3/I4/I5. O PR #31 (H11) altera `triage_processing.py` separadamente e está em revisão.

## Matriz de cenários H12

| Cenários | Quantidade | Retorno esperado |
|---|---:|---|
| Falha de `FalhaOrquestracao` em entrada, extração, alerta, decisão, persistência ou etapa não mapeada | 6 | HTTP 502, código público conforme etapa, sem mensagem interna |
| Exceções imprevistas do adaptador (`RuntimeError`, `OSError`, `ValueError`) | 3 | HTTP 502 `PROCESSAMENTO_INDISPONIVEL` |
| Resultado incompatível com documento, tipo, canal, nome, SHA-256 ou estado terminal | 6 | HTTP 502 `RESULTADO_INCONSISTENTE` |
| Falha de consulta do manifesto | 1 | HTTP 502 `FALHA_CONSULTA_METADADOS` |
| Manifesto inexistente | 1 | HTTP 404 `REGISTRO_NAO_ENCONTRADO` |
| Original indisponível | 1 | HTTP 502 `ORIGINAL_INDISPONIVEL` |
| Adaptadores não configurados | 1 | HTTP 503 `TRIAGEM_NAO_CONFIGURADA`, sem consultar OCI |
| Resposta do serviço que viola contrato canônico | 1 | HTTP 502 `PROCESSAMENTO_INDISPONIVEL` |
| Ausência de `/processar` na aplicação principal | 1 | Rota não publicada no OpenAPI normal |
| **Total** | **21** | |

**Observações:** as rotas e componentes são montados somente no aplicativo de teste com substituição explícita de dependências. Os exemplos de erros e chaves são strings fictícias. Os testes não reclassificam erros de infraestrutura como sucesso nem comprovam o comportamento de serviços reais sob indisponibilidade.

## Execução local

A partir da raiz do projeto, na branch `test/h12-erros-api-i1` baseada na `develop`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_h12_erros_api_i1.py -rx
.\.venv\Scripts\python.exe -m pytest -q tests/test_api_triage_processing.py tests/test_h12_erros_api_i1.py -rx
.\.venv\Scripts\python.exe -m pytest -q -k "not fluxo_api_com_gemini_real"
.\.venv\Scripts\python.exe -m compileall -q src scripts tests
git diff --check
git status --short
```

## Critérios de aceite

1. Os 21 testes H12 aprovados, sem `xfail` novo nem marcações para contornar falhas.
2. Testes preexistentes da API e suíte geral sem regressões; o `xfail` conhecido do I4 permanece documentado e fora do escopo.
3. Nenhum dado clínico real, credencial ou chamada externa, nem alteração de contratos.
4. PR direcionado a `develop`; CI Python 3.12/3.13 aprovada e revisão de outra área.
5. A matriz H12 permanece classificada como **parcial / ampliada com simulação**, pois a homologação real ponta a ponta e os controles públicos ainda não existem.

## Evidência de execução

**Execução local — 09/11/2026 (BRT)**

- Branch: `test/h12-erros-api-i1`.
- Base inicial: `develop` (`fcb5449`).
- Testes H12: 21 aprovados.
- Testes combinados da API: 47 aprovados.
- Suíte geral: 301 aprovados, 1 excluído e 1 xfailed conhecido (I4).
- `compileall`: concluído sem erros.
- `git diff --check`: sem erros.
- CI Python 3.12/3.13: pendente de execução no PR.
- OCI, Gemini e RAG reais: não utilizados.
- Endpoint `/processar`: permanece não registrado no aplicativo principal.

**A preencher após executar no ambiente local:** data/hora BRT, SHA de base, branch, contagem dos testes H12, contagem da suíte, resultado de `compileall` e links dos checks da CI. Não registrar valores de variáveis de ambiente nem conteúdo de objetos armazenados.

## Limitações e dependências

- O PR #31/H11 trata da habilitação **explícita** em ambiente de desenvolvimento. Este H12 não modifica aquela alteração nem precisa aguardar o merge para iniciar os testes.
- O router `/processar` não é publicado pela aplicação principal; o sucesso HTTP 200 nos testes antigos utiliza um **serviço simulado**, não integra os componentes definitivos.
- AuthN/AuthZ, rate limiting, idempotência, retries e auditoria de acesso deverão ser definidos antes de qualquer serviço público.
- H09 (OCI real) e H10 (falhas simuladas) são evidências separadas. H12 não deve ser descrito como validação real de OCI ou Gemini.
