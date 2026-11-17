# Persistência de resultados e histórico na OCI — B-013 (incremento 1)

**Escopo:** protótipo educacional com documentos sintéticos. Não executa IA, RAG, LangGraph nem decisão médica.

## Serviço e dependências

`mediflow.storage.triage_persistence.persistir_resultado(storage, recibo, resultado)` recebe:

- um `OCIStorage` apontando para o bucket já configurado;
- um `ReciboArquivo` validado e lido do manifesto pela API existente;
- um `ResultadoTriagem` v0.1 **concluído** e com `armazenamento_oci.status="pendente"`.

A aplicação chamadora é responsável por autenticar/autorizar o acesso ao documento e obter o manifesto de modo confiável. Este serviço, isolado, não publica um endpoint, não faz autenticação e não grava na OCI enquanto não for explicitamente invocado.

## Procedimento

1. Verificar IDs, associação entre recibo e resultado e compatibilidade de metadados.
2. Recarregar o original da OCI e conferir tamanho e SHA-256.
3. Gerar um `execucao_id` UUID4 e chaves imutáveis sob `historicos/<documento_id>/<arquivo_id>/<execucao_id>.json` e `resultados/<documento_id>/<arquivo_id>/<execucao_id>.json`.
4. Gravar o histórico primeiro, usando `If-None-Match: *`, e confirmar por download/igualdade de bytes.
5. Gerar uma cópia validada de `ResultadoTriagem`, agora com as três chaves de armazenamento e `status="confirmado"`.
6. Gravar o resultado com a mesma condição de não sobrescrita e confirmar por download.
7. Retornar o resultado confirmado apenas após todas as verificações.

**Falhas:** qualquer exceção no acesso OCI gera `PersistenciaIncompleta`; o serviço não declara sucesso, não apaga objetos e não expõe a mensagem original do provedor. Um histórico parcial pode ficar no bucket para conciliação administrativa. Há possibilidade de o resultado ser gravado e a leitura de confirmação falhar; nesse caso a função também informa persistência não confirmada. Os objetos são imutáveis por `execucao_id`.

**Não é uma transação atômica:** Oracle Object Storage não oferece uma transação envolvendo dois objetos. Uma etapa futura deverá implementar índice de execuções e política de reconciliação/idempotência por operação, além de um endpoint autenticado de consulta. Não existe mecanismo de reprocessamento automático neste incremento.

## Execução local

```powershell
py -3.12 -m pytest -q tests/test_triage_persistence.py
py -3.12 -m compileall -q src tests
```

Os testes utilizam um cliente OCI simulado e não exigem credenciais, rede ou acesso ao bucket real. **Não rodar contra documentos reais.** Para um teste real autorizado no bucket, usar uma chave de execução inédita, arquivos exclusivamente sintéticos e registrar a evidência do comportamento.

## Interfaces preservadas

- `OCIStorage.upload_bytes` permanece com comportamento atual para uploads existentes.
- `OCIStorage.upload_bytes_if_absent` é um método novo: chama `put_object` com `if_none_match="*"`.
- Nenhuma rota FastAPI ou schema canônico foi alterado.
- A próxima tarefa de I1 é criar rota separada de consulta/execução, restrita a ambiente local ou autenticado, sem substituir `extracao-preview`.
