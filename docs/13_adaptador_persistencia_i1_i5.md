# MediFlow — Adaptador de persistência I1 ↔ I5 (incremento isolado)

**Escopo:** MVP administrativo educacional, **somente documentos sintéticos**. Este incremento prepara a conexão entre `ServicoTriagem` (#18), a rota preparatória (#19) e `persistir_resultado()` (#15) **sem habilitar a API de processamento nem executar OCI real**. Não produz decisões clínicas.

## Arquivos

| Arquivo | Finalidade |
|---|---|
| `src/mediflow/api/triage_persistence_adapter.py` | Porta `PersistidorResultadoOCI`, vinculação por upload e fábrica `montar_servico_triagem_com_oci` |
| `tests/test_triage_persistence_adapter.py` | Integração com FakeOCI, I2/I4 simulados e testes negativos |
| `docs/13_adaptador_persistencia_i1_i5.md` | Arquitetura, limites e execução |

**Não foram modificados:** `app.py`, `triage_processing.py`, `triage_service.py`, contratos `models.py`, implementações I2/I3/I4 ou o módulo de persistência I5.

## Fluxo e restrições

```text
Requisição local autorizada (integração HTTP FUTURA)
  -> manifesto confiável (_ler_manifesto por documento_id + arquivo_id)
  -> original íntegro (triage_processing._documento_verificado)
  -> montar_servico_triagem_com_oci(storage, recibo, I2, I4, RAG opcional)
  -> ServicoTriagemComOCI.executar(documento, canal_origem=recibo.entrada.canal_origem)
     -> CONFERE documento_id, arquivo_id, MIME, nome, bytes, tamanho, SHA-256 e canal
     -> ServicoTriagem (extração, confirmação independente, RAG, decisão)
        -> PersistidorResultadoOCI.persistir(resultado)
           -> persistir_resultado(storage, recibo, resultado)
              -> HISTÓRICO e RESULTADO: upload-if-absent, download, integridade
              -> armazenamento_oci.status = confirmado SOMENTE depois de tudo OK
```

**Vínculo por execução:** `ResultadoTriagem v0.1` não contém `arquivo_id`. Por isso, o adaptador de persistência armazena uma cópia defensiva do `ReciboArquivo`, e a fachada `ServicoTriagemComOCI` confere o `arquivo_id` e os bytes do `DocumentoParaExtracao` antes de executar qualquer I2/I4/I5. É proibido manter a fachada como singleton ou reutilizá-la entre requisições. O recibo deve vir do manifesto OCI validado e autorizado, nunca ser recebido diretamente do cliente.

**Falhas:** o serviço I1 transforma falhas do I5 em `FalhaOrquestracao` (`PERSISTENCIA_INDISPONIVEL`) sem expor credenciais, e **não** informa sucesso em caso de confirmação incompleta. Uma escrita parcial do histórico é possível e exige reconciliação administrativa futura. Não há transação entre os dois objetos.

**Reprocessamentos:** `persistir_resultado` gera um novo `execucao_id` a cada chamada, portanto novas execuções são escritas em novas chaves; não existe idempotência de requisições, índice de execuções ou mecanismo de reconciliação automática. A rota HTTP pública não deve ser habilitada sem essas medidas, autenticação e controle de custos.

## Utilização no futuro (não executar com adaptadores simulados em produção)

```python
from mediflow.api.triage_persistence_adapter import montar_servico_triagem_com_oci

# Dentro de uma requisição devidamente autorizada, após carregar manifesto
# confiável, verificar original/bytes e configurar os adaptadores reais:
servico = montar_servico_triagem_com_oci(
    storage=storage,
    recibo=recibo,
    extrator=extrator_i2,
    confirmador=confirmador_i4,
    decisor=decisor_i4,
    recuperador=recuperador_i3,  # opcional
)
resultado = servico.executar(documento, canal_origem=recibo.entrada.canal_origem)
```

**Atenção:** este exemplo é ilustrativo. Os objetos `extrator_i2`, `confirmador_i4`, `decisor_i4`, `recuperador_i3`, `storage`, `recibo` e `documento` não são criados automaticamente neste incremento. A função `obter_servico_triagem()` da rota #19 continua retornando 503, e o router ainda não está montado no `app.py`.

## Testes

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_triage_persistence_adapter.py
.\.venv\Scripts\python.exe -m pytest -q -k "not fluxo_api_com_gemini_real"
.\.venv\Scripts\python.exe -m compileall -q src scripts tests
```

O novo arquivo possui 16 testes, incluindo os três cenários DOC-001/002/005 com fakes, original e manifesto preservados, alteração de `arquivo_id` mesmo com bytes idênticos, alteração de `documento_id`, canal, tamanho/hash, referência OCI inconsistente, snapshot imutável do recibo, falha no histórico/resultado, verificação de leitura, reprocessamento e rejeição de colisão. Todos usam `FakeOCI`, sem SDK/credenciais nem rede; os fakes I2/I4 não executam OCR/Gemini ou LangGraph.

## Critério de aceite

- 16 testes novos aprovados; suíte geral estável e CI em Python 3.12/3.13.
- Somente três arquivos neste PR; base `develop`.
- Nenhum endpoint novo ou serviço real habilitado por padrão.
- Verificações de integridade e de escopo de execução demonstradas.
- A integração final da rota e dos adaptadores I3/I4, autenticação, observabilidade e idempotência ficam para a etapa de MVP ponta a ponta.
