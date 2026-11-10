# MediFlow — Integração controlada I1 + I3 + I4

**Objetivo:** conectar a orquestração I1, o recuperador definitivo I3 e a confirmação independente/motor LangGraph I4, sem antecipar a homologação externa da I2.

## Dependências de PR

- PR #16 (I3) integrado à `develop`.
- PR #33 (I4) ainda em revisão na elaboração deste incremento: **seu código precisa estar presente na branch de testes**; não modificar o PR #33.
- PR #34 (I2, Gemini Flash Lite) integrado, mas não utilizado nos novos testes.

## Arquivos

- `src/mediflow/api/composicao_i1_i3_i4.py`: fábrica de composição sem endpoint, OCI ou chamadas externas; carrega as 14 fichas Markdown do I3 e injeta o `GrafoDocumentalI4` e o `ConfirmadorAlertaOriginal`.
- `tests/test_integracao_i1_i3_i4_real_local.py`: três documentos oficiais sintéticos, RAG real, confirmação no documento original e execução efetiva do LangGraph, com extrator de fixture para substituir somente o I2.

## O que os testes comprovam

1. DOC-001 → R005 / `prontuario_documental` / `processado`.
2. DOC-002 → R001 / `fila_prioritaria_avaliacao_humana` / `aguardando_auditoria`.
3. DOC-005 → R002 / `auditoria_humana` / `aguardando_auditoria`; dosagem permanece nula/ilegível.
4. Fontes da base RAG retornam `fonte_id`, `versao` e `titulo`, sem usar nomes e identificadores de pacientes como consulta.
5. Uma alegação de urgência apenas na extração simulada não altera a decisão sem confirmação no original.
6. Uma falha do RAG não rebaixa alerta confirmado no original.
7. Original com SHA-256 adulterado é rejeitado antes de invocar extração.
8. A persistência OCI permanece `pendente` neste incremento.

## Como executar (PowerShell)

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,ai]"
.\.venv\Scripts\python.exe -m pytest -q tests/test_integracao_i1_i3_i4_real_local.py -rx
.\.venv\Scripts\python.exe -m pytest -q -k "not fluxo_api_com_gemini_real"
.\.venv\Scripts\python.exe -m compileall -q src scripts tests
git diff --check
```

## Restrições

- **I2:** `ExtratorDeFixtureOficial` carrega resultados sintéticos versionados, sem invocar Gemini; a homologação H03/H04 permanece com a Júlia.
- **I3:** recuperador real local com fichas Markdown; nenhuma API de embeddings ou modelos de rede é utilizada.
- **I4:** confirmação real lê os PDFs/PNG oficiais; o grafo LangGraph executa os seis caminhos possíveis, mas os três cenários exercitam R005, R001 e R002.
- **I5:** sem persistidor nem escrita na OCI; sem falso `confirmado`.
- **API:** não se habilita o endpoint `/processar`; não há autenticação/autorização para acesso público.
- **Segurança:** o sistema é protótipo educacional e documental com dados sintéticos. Não realiza triagem ou decisão clínica para pacientes reais.

## Próximos portões

1. Integrar o PR #33 e rebasear/sincronizar a branch sobre `develop` após CI verde e revisão.
2. Conectar o I2 real ao mesmo serviço apenas após homologação dos três documentos com Gemini.
3. Acoplar o adaptador OCI I5 e validar a persistência completa.
4. Corrigir a defesa conhecida do I1 que permite um par regra/destino inconsistente quando recebe um decisor externo defeituoso, sem duplicar regras no I1.
5. Testar idempotência e endpoint local protegido antes do MVP demonstrável.
