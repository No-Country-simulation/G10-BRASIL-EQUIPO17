# Integração I1/I2 — interface de extração (simulação técnica)

## Objetivo e limites

O MediFlow já recebe e armazena documentos sintéticos na OCI. Esta etapa confirma o **contrato de passagem dos bytes recuperados do Object Storage para um extrator**, desacoplado da FastAPI e do SDK Oracle.

**Nenhum modelo Gemini é invocado aqui. Não existe classificação semântica, extração real nem decisão de roteamento.** O resultado estruturado é neutro, exclusivamente para verificar a comunicação técnica. A rota não persiste extrações e não altera manifestos nem originais.

## Interface fornecida ao I2

Arquivo `src/mediflow/extraction/port.py`:

- `DocumentoParaExtracao(documento_id, arquivo_id, nome_original, mime_type, conteudo: bytes, sha256)`: os bytes vêm da OCI e seu SHA-256 é verificado antes da invocação.
- `ExtratorDocumento.extrair(documento: DocumentoParaExtracao) -> ExtracaoIA`: interface (`Protocol`) para o extrator real do I2.
- `ExtratorSimulado`: retorna `tipo_documento='outro_desconhecido'` e campos vazios, **sem analisar o conteúdo**. Não tomar esse valor como classificação verdadeira.

O retorno real do I2 deverá respeitar `mediflow_contracts.models.ExtracaoIA` (v0.1), inclusive `documento_id` correspondente. Não modificar schemas gerados manualmente.

## Endpoint de teste (APENAS local)

`GET /v1/triagens/arquivos/{documento_id}/{arquivo_id}/extracao-preview`

Pré-requisitos: `MEDIFLOW_ENV=development`, `MEDIFLOW_ENABLE_LOCAL_UPLOADS=true`, servidor escutando `127.0.0.1` e perfil OCI configurado. A rota usa a **mesma proteção local** das rotas de upload e consulta. Não a publique: falta autenticação e autorização por usuário.

Sequência:

1. Localiza o manifesto em `metadados/{documento_id}/{arquivo_id}.json` e valida a associação.
2. Recupera o objeto original `originais/...` na OCI.
3. Verifica tamanho e SHA-256 conforme o manifesto; recusa inconsistências.
4. Monta `DocumentoParaExtracao` com bytes, MIME e identificadores.
5. Invoca **somente** `ExtratorSimulado` (padrão) e valida o retorno com Pydantic `ExtracaoIA`.
6. Responde `modo=simulacao_tecnica`, `integridade_original=confirmada`, `triagem_executada=false` e aviso explícito de que não há IA real.

Erros esperados: 403 fora do ambiente local; 404 se o manifesto não existir; 502 em falha de OCI, divergência de integridade, extração inválida ou indisponibilidade do extrator. Detalhes de chaves OCI não são retornados.

## Teste no Swagger

1. Atualize a `develop` e instale `.[dev,cloud]`.
2. Configure as variáveis locais de OCI e execute o Uvicorn com `--host 127.0.0.1`.
3. Use POST `/v1/triagens/arquivos` para enviar um documento sintético (ou use um `arquivo_id` já registrado).
4. Copie `documento_id` e `arquivo_id` do recibo.
5. Execute o novo GET `.../extracao-preview`.
6. Verifique HTTP 200, `integridade_original=confirmada`, `modo=simulacao_tecnica` e `triagem_executada=false`.
7. Confirme que **nenhum novo objeto** foi criado na OCI pelo preview (operação somente leitura).

## Integração futura com o módulo de IA

O I2 deve implementar um extrator com a assinatura `extrair(documento) -> ExtracaoIA`, utilizando dados sintéticos e sem inventar valores ausentes. A comunicação com Gemini e seus segredos devem ficar no adaptador do I2, e não dentro do `port.py` ou da FastAPI.

Antes de integrar um extrator real, será necessária uma rota distinta ou uma política de execução explícita, com autenticação, tratamento de falhas e identificação inequívoca de que os dados são derivados de IA. **A rota de preview continuará rotulada como simulação e não deve começar a executar Gemini silenciosamente.**

## Testes automatizados

O arquivo `tests/test_api_extraction_preview.py` testa PDF, PNG, integridade, ausência de registro, restrição local, erro da OCI, incompatibilidade do contrato e troca de `documento_id`, tudo com armazenamento falso. A CI não requer credenciais OCI/Gemini.
