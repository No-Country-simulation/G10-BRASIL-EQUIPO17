# MediFlow — H10: falhas parciais de persistência OCI (I1/I5)

**Estado:** aprovado com simulação na execução local; validação da CI pendente.
**Ambiente:** simulado com `FakeOCI`, sem rede, credenciais ou gravações na OCI real.
**Escopo:** protótipo educacional de triagem documental e administrativa, somente dados sintéticos. Não realiza decisões clínicas.

## Objetivo

Reforçar o critério H10 de `docs/16_criterios_homologacao_mvp.md`: a falha em qualquer etapa do armazenamento não pode produzir um `ResultadoTriagem` retornado com `armazenamento_oci.status="confirmado"`.

O serviço I1 encapsula falhas do persistidor no código público `PERSISTENCIA_INDISPONIVEL` e não divulga mensagens internas da OCI. A persistência exige verificar o documento original, registrar o histórico e confirmar sua leitura, registrar o resultado e confirmar sua leitura.

## Arquivo de teste

- `tests/test_h10_falhas_parciais_i1.py`: **10 casos de teste** (quatro cenários parametrizados em duas variações e dois casos individuais). Exercita a integração I1↔persistidor com componentes simulados definidos em `tests/test_triage_persistence_adapter.py`.

### Cenários cobertos

| Falha injetada | Estado parcial possível | Comportamento obrigatório |
|---|---|---|
| Timeout depois de gravar histórico | Histórico isolado | Sem confirmação de sucesso |
| Timeout depois de gravar resultado | Histórico e resultado presentes, confirmação incerta | Sem confirmação de sucesso |
| Falha ao ler histórico | Histórico isolado | Sem confirmação de sucesso |
| Falha ao ler resultado | Ambos presentes | Sem confirmação de sucesso |
| Hash retornado divergente para histórico | Histórico isolado | Sem confirmação de sucesso |
| Hash retornado divergente para resultado | Ambos presentes | Sem confirmação de sucesso |
| Leitura com bytes corrompidos do histórico | Histórico isolado | Sem confirmação de sucesso |
| Leitura com bytes corrompidos do resultado | Ambos presentes | Sem confirmação de sucesso |
| Original indisponível | Nenhuma nova gravação | Sem confirmação de sucesso |
| Repetição da mesma ID após gravação parcial | Histórico antigo permanece | Sem sobrescrita e sem reparação automática |

O arquivo de teste verifica também a preservação do original e do manifesto e a sanitização da exceção pública `FalhaOrquestracao`. Não busca certificar credenciais, permissões ou comportamento de indisponibilidade do serviço OCI real.

## Como executar

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_h10_falhas_parciais_i1.py -rx
.\.venv\Scripts\python.exe -m pytest -q -k "not fluxo_api_com_gemini_real"
.\.venv\Scripts\python.exe -m compileall -q src scripts tests
git diff --check
```

**Evidência da execução local — 09/11/2026 (BRT)**

- Branch: `test/h10-falhas-parciais-oci`.
- Commit-base da `develop`: `fcb5449`.
- Testes H10: 10 aprovados.
- Testes combinados de persistência: 34 aprovados.
- Suíte geral: 290 aprovados, 1 excluído, 1 xfailed conhecido (I4).
- `compileall`: concluído sem erros.
- `git diff --check`: sem erros.
- CI Python 3.12/3.13: pendente de execução no PR H10.
- OCI real: não utilizada neste incremento.

## Limites e pendências

- **Somente simulação:** falhas controladas por `FakeOCI`; não injetar falhas no bucket real `mediflow-docs-dev` nesta etapa.
- O OCI Object Storage não fornece transação atômica entre histórico e resultado. Um objeto pode estar gravado mesmo se a operação for reportada como falha.
- A simples presença de ambos os objetos após timeout **não comprova confirmação pela aplicação**; é necessário verificar as leituras e integridade.
- Não há reconciliação automática de execuções parciais, índice de execuções nem idempotência por requisição. Recuperação administrativa será tratada em incremento separado, com coordenação I1/I5.
- Não altera `triage_service.py`, `triage_persistence.py`, `app.py`, contratos, infraestrutura OCI ou motor I4. Nenhuma rota HTTP é habilitada.
- A homologação H09 em OCI real é separada e não deve ser reexecutada para validar este incremento.

**Critério para atualizar H10 na matriz:** após a execução bem-sucedida, registrar "Aprovado com simulação — cobertura ampliada de falhas parciais", sem confundir com "Aprovado real controlado".
