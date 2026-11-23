# MediFlow — Validação de persistência e revisão humana na OCI (H17)

**Data:** 20/11/2026
**Situação:** HOMOLOGAÇÃO TÉCNICA APROVADA — dentro do escopo sintético e controlado
**Ambiente:** desenvolvimento local; Oracle Cloud Infrastructure (OCI) Object Storage real
**Região OCI:** `sa-saopaulo-1` (configuração previamente validada)
**Bucket:** `mediflow-docs-dev`
**Branch e commit-base:** `develop` — `6a1f74f8ad000fcd01b6640f67c9d8019e34134a`
**Contrato:** `ResultadoTriagem` v0.1
**Escopo:** persistência de índices por status, revisão humana e isolamento da revisão entre execuções, sem Gemini real.

## 1. Objetivo e delimitação

Validar, **na OCI real**, as funcionalidades de persistência introduzidas depois da H16: índices segregados em `processados/` e `auditoria_humana/`, gravação e recuperação de revisão humana independente do resultado original e reprocessamento sem herança indevida de revisões. Reutilizar os módulos existentes de ingestão, orquestração, regras e armazenamento, com **fixtures sintéticas** em lugar do Gemini.

A H17 **não substitui a H16**. A H16 homologou os três cenários oficiais com Gemini e OCI reais; a H17 concentra-se nas funcionalidades posteriores de persistência. A H17 utiliza as versões **textuais** sintéticas de DOC-001 e DOC-005 e não constitui repetição dos fluxos multimodais de H16.

Foi concedida autorização explícita para até **14 novos objetos sintéticos** no bucket de desenvolvimento, sem Gemini real, sem exclusão e sem alteração intencional dos objetos históricos. O limite foi integralmente utilizado, sem excedê-lo.

## 2. Preparação e baseline

Antes da primeira gravação real, foram confirmados:

- Commit local `6a1f74f8ad000fcd01b6640f67c9d8019e34134a`, na branch `develop`, sem alterações rastreadas.
- **65 testes direcionados aprovados**, em 21,80 s, abrangendo persistência, revisão, triagem textual e HTTP de demonstração.
- Ensaio com FakeOCI aprovado, com **14 objetos simulados** e confirmação da não herança de revisão após reprocessamento.
- Inventário inicial OCI com **29 objetos**, total de **571.072 bytes** e nenhuma chave H17 preexistente.
- Baseline individual de tamanho e SHA-256 dos 29 objetos salva em `%USERPROFILE%\mediflow-h17-evidencias\baseline_pre_h17.json`.
- Fingerprint SHA-256 do inventário de referência:

```text
58db1a6489fd89eefb60a90bf8387b6aff7667bdb603406955c5e1ff8cda96ef
```

O preflight H17-01 comparou o conjunto completo de 29 chaves e os SHA-256 dos respectivos conteúdos na OCI real com a baseline antes de autorizar a primeira operação de escrita. Resultado: `PREFLIGHT_H17: APROVADO`, sem gravações e sem chamadas Gemini.

## 3. Execuções homologadas

| Etapa | Cenário | Regra principal | Status | Novos objetos | Total do bucket após a etapa | Resultado |
|---|---|---|---|---:|---:|---|
| H17-02 | `H17-DOC-001` (rotina) | R005 | `processado` | 5 | 34 | APROVADO |
| H17-03 | `H17-DOC-005`, execução A (ambiguidade) | R002 | `aguardando_auditoria` | 5 | 39 | APROVADO |
| H17-04 | Revisão humana da execução A | — | HTTP 201 após confirmação | 1 | 40 | APROVADO |
| H17-05 | `H17-DOC-005`, execução B (reprocessamento) | R002 | `aguardando_auditoria` | 3 | 43 | APROVADO |
| **Total** | | | | **14** | **43** | **APROVADO** |

Todos os quatro lotes terminaram com **código de saída 0**, conforme os logs apresentados.

### 3.1. H17-02 — Rotina, DOC-001

- Entrada: fixture textual oficial do DOC-001, sob identificador `H17-DOC-001`.
- Regra principal: **R005**.
- Destino: `prontuario_documental`.
- Índice de status criado sob `processados/prontuario_documental/`.
- Cinco gravações confirmadas: original, manifesto, histórico, resultado e índice.

Identificadores de execução:

```text
arquivo_id: 5f60c107c19f402baa8dd6791fd2b3b4
execucao_id: 143b5322a93c4604884dc84e603ada7c
```

### 3.2. H17-03 — Ambiguidade, DOC-005, execução A

- Entrada: fixture textual oficial do DOC-005, sob identificador `H17-DOC-005`.
- Regra principal: **R002**.
- Status: `aguardando_auditoria`.
- Destino: `auditoria_humana`.
- Índice criado sob `auditoria_humana/auditoria_humana/`.
- Cinco gravações confirmadas: original, manifesto, histórico, resultado e índice.

Identificadores de execução:

```text
arquivo_id: aaae08ee24ee4ea3af1385ea1c4ac50f
execucao_id: 9af2826f6da04832baada70213759473
```

O resultado preservou a ambiguidade documental: `dosagem_status = ilegivel` e `dosagem_texto = null`, conforme verificação independente da auditoria final.

### 3.3. H17-04 — Revisão humana da execução A

- Registrada uma revisão sintética, com ação `aprovar`, por meio da rota existente de revisão humana.
- HTTP **201** retornado após confirmação de upload e leitura posterior.
- Objeto armazenado sob `revisoes/H17-DOC-005/`, com associação à **chave exata do resultado da execução A**.
- Consulta individual e fila de auditoria recuperaram a revisão.
- O resultado original da execução A não foi alterado.

Chave da revisão:

```text
revisoes/H17-DOC-005/20261120T173407861059Z-7b5a062a7aa343d1a76c66721bd4ebcd.json
```

### 3.4. H17-05 — Reprocessamento, DOC-005, execução B

- Reutilizou o mesmo `arquivo_id` e o mesmo objeto original/manifesto da execução A; **não houve novo upload da entrada**.
- Nova execução recebeu `execucao_id` diferente: `bced523db04f45d69daa958d329b4f8d`.
- Criados **apenas três objetos**: histórico B, resultado B e índice B em `auditoria_humana/auditoria_humana/`.
- Regra principal permaneceu **R002**.
- Consulta individual e fila retornaram a execução B com `revisao_humana = null`.
- O resultado e a revisão da execução A permaneceram íntegros.

Portanto, a revisão vinculada à execução A **não foi herdada** pela execução B.

## 4. Auditoria final independente — H17-06

A H17-06 foi executada em 20/11/2026, com **somente leituras OCI** e consultas HTTP locais GET. A única escrita do script foi um arquivo **local**, fora do repositório e fora da OCI.

Saída observada:

```text
EVIDENCIAS_LOCAIS: 4/4 VALIDADAS
BASELINE: 29 OBJETOS, FINGERPRINT CONFIRMADO
INVENTARIO_OCI: 43 CHAVES EXATAS
DISTRIBUICAO: COMPATIVEL
SHA256_HISTORICOS: 29/29 OK
SHA256_OBJETOS_H17: 14/14 OK
AMOSTRAS_SINTETICAS: 2/2 CONFIRMADAS
RESULTADOS_H17: DOC001 R005, DOC005_A R002, DOC005_B R002 - OK
INDICES_STATUS: 3/3 CONSISTENTES
CONTRATO_RESULTADOTRIAGEM_V01: 3/3 VALIDOS
REVISAO_A: OBJETO INTEGRO E VINCULO_EXATO CONFIRMADO
REVISAO_B: AUSENTE (NAO HERDADA)
CONSULTA_E_FILA: EXECUCAO_B SEM REVISAO - OK
INVENTARIO_FINAL: 43 OBJETOS RECONFIRMADOS
GRAVACOES_OCI: 0
CHAMADAS_GEMINI_REAL: 0
AUDITORIA_FINAL_H17: APROVADA
CODIGO_SAIDA: 0
```

A validação incluiu igualdade de chaves esperadas, tamanhos, hashes SHA-256, consistência de manifestos, originais, históricos e índices, validade dos três objetos `ResultadoTriagem` v0.1 e associação estrita da revisão à execução A. A consulta da execução B foi testada em aplicação FastAPI em processo, com armazenamento OCI configurado em modo **somente leitura**.

### Distribuição final por prefixo

| Prefixo | Antes (baseline) | Depois (H17-06) | Variação |
|---|---:|---:|---:|
| `originais/` | 9 | 11 | +2 |
| `metadados/` | 7 | 9 | +2 |
| `historicos/` | 5 | 8 | +3 |
| `resultados/` | 5 | 8 | +3 |
| `processados/` | 0 | 1 | +1 |
| `auditoria_humana/` | 0 | 2 | +2 |
| `revisoes/` | 0 | 1 | +1 |
| `testes/` | 3 | 3 | 0 |
| **Total** | **29** | **43** | **+14** |

**Todos os 29 objetos históricos** apresentaram, ao final, os mesmos nomes, tamanhos e SHA-256 da baseline. **Todos os 14 objetos novos** apresentaram os tamanhos e SHA-256 registrados nas respectivas evidências de lote.

## 5. Critérios de aceite e resultado

| Critério | Verificação | Status |
|---|---|---|
| Índice de rotina segregado em `processados/` | DOC-001 / R005 | APROVADO |
| Índice de auditoria segregado em `auditoria_humana/` | DOC-005 / R002, A e B | APROVADO |
| Persistência e integridade do resultado | Três resultados e seus vínculos | APROVADO |
| Persistência e recuperação da revisão humana | HTTP 201, leitura e consultas | APROVADO |
| Revisão ligada à execução exata | Revisão A aponta ao resultado A | APROVADO |
| Reprocessamento sem herança de revisão | Consulta atual aponta a B sem revisão | APROVADO |
| Preservação dos objetos originais | 29 SHA-256 históricos inalterados | APROVADO |
| Preservação da execução A e sua revisão | Comparação após execução B | APROVADO |
| Limite de novos objetos | 14 de 14 autorizados | CUMPRIDO |
| Nenhum Gemini real na H17 | Extração por fixture sintética | CUMPRIDO |

## 6. Evidências disponíveis na estação de homologação

Diretório local do executor: `%USERPROFILE%\mediflow-h17-evidencias\`

- `baseline_pre_h17.json` — referência de SHA-256 dos 29 objetos históricos.
- `h17_doc001_lote1.json` — DOC-001, cinco objetos novos.
- `h17_doc005_execucao_a_lote2.json` — DOC-005, execução A, cinco objetos novos.
- `h17_doc005_revisao_a_lote3.json` — revisão da execução A, um objeto novo.
- `h17_doc005_execucao_b_lote4.json` — reprocessamento DOC-005, execução B, três objetos novos.
- `h17_auditoria_final_20261120T175457949094Z.json` — auditoria final independente e somente de leitura.

Esses arquivos permaneceram na máquina do executor; o presente relatório foi consolidado a partir das **saídas de terminal compartilhadas** e da leitura do código de auditoria. Para arquivamento ou revisão por terceiros, preservar os arquivos JSON originais junto às evidências do projeto, sob acesso adequado. Não adicionar credenciais OCI nem chaves privadas.

## 7. Limitações e ressalvas

1. A H17 usou **somente amostras textuais sintéticas** para exercitar o fluxo de persistência. A extração por Gemini real e o processamento multimodal pertencem à evidência anterior da H16, não à H17.
2. As verificações comprovam **integridade e não sobrescrita pelo fluxo testado**. Não constituem garantia de imutabilidade administrativa permanente do bucket, de Object Lock, de versionamento ou de proteção contra operadores privilegiados.
3. A API de demonstração/revisão é **local e sem autenticação real**; não deve ser publicada ou usada com dados reais de pacientes.
4. A H17 não constitui validação clínica, auditoria de segurança de produção, benchmark de desempenho, garantia de custo zero ou homologação de recuperabilidade frente a falhas de rede/incidentes concorrentes.
5. Em caso de HTTP 502 após tentativa de upload, a existência física do objeto pode ser incerta. A recuperação exige reconciliação por leitura; **não se devem executar retries cegos**.
6. A auditoria confirmou o estado do bucket **no momento da execução**. Alterações futuras exigem novo inventário, sem extrapolar a conclusão no tempo.

## 8. Conclusão

**H17 — HOMOLOGAÇÃO TÉCNICA APROVADA NO ESCOPO DEFINIDO.** Foram criados exatamente **14 novos objetos sintéticos** na OCI real, totalizando **43 objetos**. Os **29 objetos históricos foram preservados** por comparação de SHA-256, os três resultados e três índices novos foram validados, e a revisão humana foi persistida e recuperada sem herança indevida após reprocessamento.

A validação de persistência, revisão humana e reprocessamento na OCI está concluída. Este relatório foi integrado ao repositório pelo [PR #66](https://github.com/No-Country-simulation/G10-BRASIL-EQUIPO17/pull/66).

As alterações posteriores da interface e do fluxo de revisão humana foram validadas com testes offline e FakeOCI, conforme o [PR #67](https://github.com/No-Country-simulation/G10-BRASIL-EQUIPO17/pull/67). Essas evidências complementam, mas não ampliam retroativamente, o escopo da homologação real de 20/11/2026, que registrou uma revisão com ação `aprovar`.

A autorização para as 14 gravações sintéticas foi integralmente utilizada. Esta atualização documental não realizou novas gravações nem novas consultas OCI e não altera as evidências registradas.

**Status final:** `AUDITORIA_FINAL_H17: APROVADA` — `CODIGO_SAIDA: 0`.
