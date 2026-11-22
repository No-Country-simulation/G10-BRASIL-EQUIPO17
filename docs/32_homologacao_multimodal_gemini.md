# MediFlow — Homologação multimodal com Gemini real e FakeOCI

## Escopo e implementação

Em 21/11/2026 (BRT), foram executados os três cenários sintéticos oficiais em ambiente local controlado, com FastAPI TestClient, Gemini real (`gemini-3.5-flash-lite`, SDK `google-genai` 2.34.0), RAG local, confirmação independente de alertas, motor determinístico e LangGraph. O armazenamento foi exclusivamente FakeOCI, em memória, com escrita e releitura verificadas. Nenhuma gravação Oracle Cloud real ou execução Streamlit fez parte deste ensaio.

A configuração optativa `MEDIFLOW_ENABLE_GEMINI_MULTIMODAL=true` envia os bytes originais de PDF, PNG ou JPEG, junto com a referência textual independente (leitura/PyMuPDF ou Tesseract OCR) e o schema JSON. A variável ausente ou diferente de `true` mantém o modo textual; entradas textuais continuam textuais. A validação de trechos literais e páginas é preservada. Sem texto verificável, a extração multimodal é bloqueada; não há fallback textual silencioso. Caminhos válidos de evidência com prefixo `dados_extraidos.` são normalizados após a validação, somente no modo multimodal. O motor e seu limiar de 0,75 permanecem inalterados.

## Resultados observados

| Cenário | Formato | Regra | Destino | Revisão | Qualidade documental | Evidências | Duração da chamada SDK |
|---|---|---|---|---|---:|---:|---:|
| DOC-001 | PDF | R005 | prontuario_documental | Não | 1,00 | 14 | 3,359 s |
| DOC-002 | PDF | R001 | fila_prioritaria_avaliacao_humana | Sim | 1,00 | 10 | 2,328 s |
| DOC-005 | PNG | R002 | auditoria_humana | Sim | 0,73 | 7 | 3,259 s |

Cada aprovação registrou HTTP 201 no upload e HTTP 200 no processamento, uma chamada lógica ao SDK, correspondência dos bytes e MIME da amostra, resposta do SDK, consulta RAG e releitura do resultado e original. Foram cinco objetos voláteis por execução aprovada (15 ao somar as três execuções independentes, não objetos simultâneos). O DOC-002 manteve R001 como principal apesar de R005 também disparar. No DOC-005, `dosagem_texto=null` e `dosagem_status=ilegivel` foram verificados. O indicador é heurístico e não calibrado.

## Histórico transparente das divergências

- A primeira tentativa de preparação foi bloqueada antes de chamada ao Gemini por ausência do SDK OCI, dispensável para FakeOCI. O homologador foi corrigido e o diagnóstico offline alcançou a montagem do payload sem enviar ao provedor.
- Duas chamadas do DOC-001 no patch inicial retornaram R006. Na segunda, a instrumentação identificou quatro campos mínimos completos mas zero ancorados pelo motor: as 11 evidências tinham prefixo `dados_extraidos.`. Indicador 0,70. Após orientar e normalizar caminhos válidos no adaptador multimodal, a nova execução retornou R005, quatro campos mínimos ancorados e qualidade 1,00.
- A primeira tentativa do DOC-002 no patch corrigido retornou HTTP 502, `EXTRACAO_INDISPONIVEL`, após resposta do SDK. A causa específica não foi capturada nessa execução. Uma nova execução instrumentada, sem mudança do código funcional, foi aprovada; não se afirma que a variabilidade foi eliminada.
- DOC-005 aprovado na primeira execução real registrada deste cenário.

São seis chamadas lógicas reais registradas (três aprovadas e três divergentes), sem contagem das retentativas internas do SDK. Aprovação dos três cenários não equivale a 100% de sucesso por tentativa.

## Rastreabilidade e regressão

- Commit-base: `dbea56c67952e3cff54e6a4a38eb0817c40c542a`.
- SHA-256 do patch funcional corrigido sobre a base: `736f828aba217de0279ea5ebfd9568e3b2d48cb5fde47a8c232495dee5e9ef7a`.
- Regressão local em Python 3.13.7: 624 aprovados, 3 deselecionados; 40 testes do adaptador, compilação e formatação aprovadas. São 23 novos casos em relação à base de 601 testes. A CI desta alteração será aferida no PR.
- [Registros sanitizados consolidados](evidencias/multimodal_gemini_fakeoci.json), com hashes dos seis registros originais, métricas e resultados de cada execução. Não contêm payload bruto, valores de paciente, chaves de objetos ou credenciais.

## Reprodução controlada

Usar apenas `app_gemini_local` e as três amostras oficiais, seguindo [a preparação e os controles](25_homologacao_gemini_local_fakeoci.md). Acrescentar `MEDIFLOW_ENABLE_GEMINI_MULTIMODAL=true` ao ambiente do processo, com consentimento e credencial Gemini já configurados de modo seguro; manter OCI real desabilitada. Executar upload e processamento conforme [README](../README.md#executar-a-demonstração-local), agora na aplicação Gemini local, sem publicar a API. A configuração por si só não comprova chamada real. O ensaio registrado usou instrumentação externa ao repositório para verificar o payload e a releitura. A regressão offline não exige credenciais.

## Limites

JPEG foi coberto por testes offline, não por ensaio Gemini real. O modo híbrido ainda depende de texto independente: informação exclusivamente visual sem evidência textual verificável não é homologada. Não foram medidos contribuição visual isolada, custo, tokens, precisão, desempenho típico, confiabilidade estatística ou validade clínica. A homologação multimodal com OCI real e interface Streamlit não foi realizada; as validações anteriores de armazenamento e interface são distintas. Uso estritamente educacional com arquivos sintéticos, sem publicação ou dados reais de pacientes.
