# MediFlow — H16: composição HTTP local Gemini + OCI

**Status documental:** homologação real aprovada em 17/11/2026, com os três cenários sintéticos (DOC-001, DOC-002 e DOC-005).

**Evidência:** [`docs/29_h16_homologacao_http_gemini_oci_real.md`](29_h16_homologacao_http_gemini_oci_real.md).

**Status da revisão humana H16:** implementação validada com FakeOCI e testes offline; gravação e leitura de uma revisão real na OCI ainda não homologadas.

## Objetivo

Disponibilizar uma aplicação FastAPI local e isolada que integra recepção documental, `ServicoTriagem`, extração Gemini, RAG local, confirmação independente de alertas, motor determinístico/LangGraph e persistência OCI Object Storage. A rota de processamento não é publicada na API principal, e os contratos Pydantic v0.1 são preservados.

## Controles de segurança

- Aceita **somente** bytes, nome e MIME das amostras oficiais `DOC-001`, `DOC-002` e `DOC-005` **antes** de instanciar o storage de upload e antes de escrever.
- Extrator usa `ExtratorSomenteAmostras` da H15, para uma segunda verificação de integridade antes de invocar o Gemini.
- Exige `127.0.0.1`, `::1` ou `testclient`, `MEDIFLOW_ENV=development`, flags explícitas, bucket `mediflow-docs-dev` e `MEDIFLOW_OCI_REAL_ACK=AUTORIZO_OCI_DEV_H16`.
- Para uma chamada Gemini real, o extrator Gemini também exige `MEDIFLOW_GEMINI_REAL_ACK=AUTORIZO_CHAMADAS_GEMINI` e `GEMINI_API_KEY` configurada.
- O endpoint `GET /h16/estado` não acessa serviços externos e **não comprova** execução real.
- Não iniciar em `0.0.0.0`, não usar `--reload` ou múltiplos workers; não processar dados de pacientes reais. A flag de localidade **não é autenticação**.
- Cada upload novo cria original e manifesto; cada processamento novo cria histórico e resultado. A API ainda não implementa idempotência: repetir POST pode gerar custos e objetos adicionais. Não repetir chamadas reais automaticamente.
- Tratamento de falhas e integridade reutiliza os serviços de API e persistência OCI. Não há transação atômica de objetos nem limpeza destrutiva.

## Fila e revisão humana no bucket dev

A H16 também registra as rotas de `triage_review.py`, sobre o **mesmo bucket** `mediflow-docs-dev`:

- `GET /v1/triagens?status=` e `GET /v1/triagens/{documento_id}` listam/consultam os resultados persistidos, com `recebido_em` e `revisao_humana`.
- `POST /v1/triagens/{documento_id}/revisao` grava a decisão (`aprovar`, `corrigir`, `rejeitar`) como objeto **imutável** em `revisoes/{documento_id}/…json`. O `ResultadoTriagem` original nunca é alterado; correções ficam só no registro da revisão.
- Mesmas travas da H16 (localhost, flags, consentimentos e bucket dev). **Sem autenticação:** o nome do revisor é declarativo; cada decisão é uma gravação real no bucket.
- A interface Streamlit reconhece o modo pela rota `/h16/estado` ("H16 (Gemini + OCI real)") e habilita a fila de auditoria com revisão.

A associação das revisões utiliza a `chave_resultado` da execução. Uma nova execução não herda uma revisão anterior do mesmo documento.

**Pendente:** em uma homologação real controlada e autorizada, registrar uma revisão sintética do DOC-005, conferir o objeto imutável em `revisoes/` e verificar a leitura via `GET /v1/triagens/DOC-005`. Nenhuma gravação real de revisão foi comprovada nesta etapa.

## Componentes e documentos

- `src/mediflow/api/app_h16_local.py` — composição isolada H16.
- `tests/test_http_h16_controlado_local.py` — testes com Gemini por fixture e OCI em memória, **sem acessos externos**.
- `docs/28_h16_preparacao_http_gemini_oci.md` — esta documentação.
- `docs/29_h16_homologacao_http_gemini_oci_real.md` — evidência da homologação real dos três cenários.

## Execução offline (sem serviços externos)

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_http_h16_controlado_local.py -rx
.\.venv\Scripts\python.exe -m pytest -q -k "not fluxo_api_com_gemini_real"
.\.venv\Scripts\python.exe -m compileall -q src scripts tests
git diff --check
git status -sb
```

Os testes injetam explicitamente `ObjectStorageMemoria` e `ExtratorFixtureSintetica`; nunca constroem um cliente OCI nem chamam o Gemini. As flags e o consentimento **nos testes** não autorizam operações reais.

## Homologação documental concluída

Em 17/11/2026, a H16 executou os três documentos sintéticos oficiais com Gemini e OCI Object Storage reais, em ambiente de desenvolvimento local e com autorização explícita.

| Documento | Regra principal | Resultado |
|---|---|---|
| DOC-001 | R005 | APROVADO |
| DOC-002 | R001 | APROVADO |
| DOC-005 | R002 | APROVADO |

Foram verificados independentemente **12 objetos OCI**, quatro por cenário: original, manifesto, histórico e resultado. A homologação ocorreu antes da introdução dos índices segregados por status.

O relatório completo está em [`docs/29_h16_homologacao_http_gemini_oci_real.md`](29_h16_homologacao_http_gemini_oci_real.md).

A evidência não comprova precisão clínica, desempenho estatístico, custo zero ou segurança para produção.

## Evoluções posteriores

- O motor determinístico recebeu um indicador heurístico de qualidade não calibrado.
- A persistência passou a gravar um quinto objeto por execução concluída: o índice segregado por status e destino.
- A API de consulta passou a verificar esse índice para novas execuções, preservando a compatibilidade com as execuções H16 anteriores.
- A revisão humana foi integrada à composição H16 e validada offline com FakeOCI.
- Revisões são vinculadas à execução por sua `chave_resultado`; o resultado original permanece imutável.

**Essas evoluções não fazem parte da homologação OCI real histórica de 12 objetos.** A nova persistência e a revisão humana ainda exigem suas próprias verificações reais controladas.

## Próximas validações

1. Homologar leitura e registro de revisão humana na OCI real, somente com autorização explícita e dados sintéticos.
2. Verificar a persistência real dos novos índices segregados por status, sem modificar objetos históricos.
3. Registrar custos, latência e consumo de tokens em uma execução controlada, quando pertinente.
4. Manter autenticação, autorização, idempotência, retenção e segurança de produção fora do escopo de uma publicação até serem implementadas e validadas.

Não repetir chamadas Gemini ou gravações OCI automaticamente. Esta documentação não autoriza uma nova execução real.
