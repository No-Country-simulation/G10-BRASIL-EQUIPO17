# Composição I1/I3/I4/I5 — validação controlada com FakeOCI

## Objetivo

Integrar os componentes reais já aprovados **I1 (orquestração)**, **I3 (RAG local)**,
**I4 (confirmador independente, motor determinístico e LangGraph)** e **I5
(adaptador de persistência)** sem ligar credenciais de serviços externos.

A extração **I2 é injetada**. Nos testes, usa a fixture oficial `ExtracaoIA`
para os três documentos sintéticos `DOC-001`, `DOC-002` e `DOC-005`. Não é
uma homologação Gemini real nem um deploy público.

## Arquivos

- `src/mediflow/api/composicao_i1_i3_i4_i5.py`: fábrica por upload que
  reutiliza `montar_servico_i1_i3_i4` e `montar_servico_triagem_com_oci`.
- `tests/test_integracao_i1_i3_i4_i5_fake_oci.py`: valida os documentos oficiais,
  RAG real, encaminhamento I4, recibo OCI simulado, persistência e falhas.

## Garantias verificadas nos testes

1. Construir o serviço não grava objetos nem faz chamadas de rede.
2. Regra/destino/status para `DOC-001` (`R005`), `DOC-002` (`R001`) e
   `DOC-005` (`R002`) permanecem coerentes com os originais.
3. A consulta RAG utiliza as fichas locais reais e não determina a prioridade.
4. Os bytes e metadados originais permanecem intactos e vinculados ao
   `documento_id`, `arquivo_id`, canal e SHA-256.
5. A FakeOCI armazena separadamente histórico e resultado com chaves por execução;
   a confirmação só ocorre depois de leitura de integridade.
6. Falhas de RAG não rebaixam R001; falhas de persistência não declaram sucesso.
7. Divergências de upload são rejeitadas antes de gravar.

## Execução

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_integracao_i1_i3_i4_i5_fake_oci.py -rx
.\.venv\Scripts\python.exe -m pytest -q -k "not fluxo_api_com_gemini_real"
.\.venv\Scripts\python.exe -m compileall -q src scripts tests
```

## Limitações e próximas atividades

- **Gemini real**: depende da homologação I2 com os três documentos sintéticos;
  os testes deste incremento usam fixtures de extração.
- **OCI real**: os testes usam FakeOCI. Executar homologação com bucket dev e
  credenciais isoladas em etapa separada, sem expor segredos.
- **HTTP**: não registrar rota de processamento automaticamente em `app.py`.
  O protótipo permanece restrito ao desenvolvimento local, sem autorização para
  deploy público. Autenticação, autorização, TLS, logs seguros e hardening serão
  necessários antes de qualquer exposição.
- Uso exclusivamente educacional e administrativo; não tomar decisões clínicas.
