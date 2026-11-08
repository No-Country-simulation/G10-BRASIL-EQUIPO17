# MediFlow — Registro da homologação H09: persistência real na OCI

**Data da execução:** 08/11/2026 (BRT)  
**Responsável pela execução:** I1 — Arquitetura, FastAPI e backend/integração OCI  
**Referência de código:** `develop` — commit `10d69c0` (`fix(api): reforçar consistência dos resultados da triagem`, PR #28)  
**Ambiente:** desenvolvimento, Oracle Cloud Infrastructure (Object Storage)  
**Bucket:** `mediflow-docs-dev`  
**Cenário:** `DOC-001` — laudo laboratorial sintético de rotina  
**Critério:** H09 de [`16_criterios_homologacao_mvp.md`](16_criterios_homologacao_mvp.md)  
**Resultado:** **APROVADO REAL CONTROLADO — apenas o componente de persistência OCI**

## 1. Objetivo e limite da homologação

Verificar com o **serviço real Oracle Object Storage** que o código do MediFlow consegue registrar o original e seu manifesto, persistir histórico e resultado associados a **uma mesma execução**, recuperá-los por download e confirmar integridade e coerência das referências.

Esta execução **não homologa a triagem ponta a ponta**. O resultado `R005` foi carregado do exemplo sintético versionado no repositório, **sem executar o motor de regras I4**. Não houve comunicação real com Gemini, execução de RAG definitivo, LangGraph, requisição HTTP FastAPI ou integração com a interface I6.

## 2. Insumos e implementação testada

- Original sintético: `amostras/pdf/DOC-001_laudo_laboratorial_rotina.pdf`.
- Resultado demonstrativo: `exemplos/DOC-001_resultado.json` (`R005`, `processado`, inicialmente com `armazenamento_oci.status = pendente`).
- Utilitário executado localmente: `scripts/homologar_h09_oci_real.py` (modo `--execute`).
- Cliente OCI real: `mediflow.storage.oci_storage.OCIStorage`.
- Persistência real: `mediflow.storage.triage_persistence.persistir_resultado`.
- Dependências locais: Python e SDK `oci`, com credenciais acessadas pelo perfil OCI do responsável; **nenhuma credencial foi armazenada neste registro**.

> O script executado foi preparado para esta homologação. Se ele não for incluído no PR de documentação, a reexecução exigirá obter a cópia local utilizada no teste. Recomenda-se versioná-lo em `scripts/` após revisão, sem executá-lo automaticamente na CI.

## 3. Procedimento realizado

1. Conferir a branch `develop`, commit de referência e testes automatizados da persistência.
2. Preparar identificadores inéditos de arquivo e execução (UUIDs), evitando reutilização de chaves.
3. Restringir explicitamente o teste ao bucket de desenvolvimento `mediflow-docs-dev`.
4. Gravar o **original PDF sintético** com criação condicional (`If-None-Match: *`), baixar e comparar os bytes e o hash SHA-256.
5. Construir e gravar o **manifesto JSON** (`ReciboArquivo`) com criação condicional, baixar e validar seu conteúdo e a associação com o original.
6. Invocar `persistir_resultado` com o recibo e a **fixture** `ResultadoTriagem` para gravar **histórico e resultado** em chaves inéditas, com confirmação de escrita e leitura.
7. Recuperar o resultado (`ResultadoTriagem`) e o histórico JSON; conferir identidade do documento, arquivo, execução, estado final e as referências gravadas.
8. Conferir os quatro objetos no bucket e preservar suas chaves para eventual retenção/limpeza futura.

### Padrão dos quatro objetos

```text
originais/DOC-001/<arquivo_id>.pdf
metadados/DOC-001/<arquivo_id>.json
historicos/DOC-001/<arquivo_id>/<execucao_id>.json
resultados/DOC-001/<arquivo_id>/<execucao_id>.json
```

Os identificadores completos foram mantidos no registro operacional da execução, não neste documento público. Os quatro objetos **permanecem no bucket**: o procedimento não executa exclusão automática.

## 4. Evidências obtidas

| Verificação | Resultado observado |
|---|---|
| Criação e leitura do original sintético | Aprovada |
| Criação e validação do manifesto | Aprovada |
| Persistência do histórico com código real do MediFlow | Aprovada |
| Persistência do resultado com código real do MediFlow | Aprovada |
| Leitura de retorno e consistência das associações | Aprovada |
| Quantidade de objetos confirmados | **4 de 4** |
| Falhas informadas pela execução | Nenhuma |

Trecho sanitizado da saída apresentada pelo executor:

```text
[1/4] Gravando e conferindo original...
[2/4] Gravando e conferindo manifesto...
[3/4] Persistindo historico e resultado via codigo real I1/OCI...
[4/4] Validando as leituras e as associacoes...
H09: APROVADO REAL CONTROLADO - Object Storage (4 objetos verificados)
Decisao R005: FIXTURE SINTETICA; nao houve execucao do motor I4.
Sem delecao automatica: registrar as 4 chaves para retencao/limpeza futura.
```

**Verificações automatizadas anteriores, na mesma versão local:** `24 passed` em `tests/test_triage_persistence.py` e `tests/test_triage_persistence_adapter.py`. Esses 24 testes utilizam armazenamento simulado; **não** representam chamadas à OCI real.

**CI do commit de referência:** Python 3.12 e 3.13 aprovados após o merge do PR #28. A CI **não executou** o teste H09 contra a OCI real.

## 5. Critérios de aceite e conclusão

**H09: aprovado real controlado no cenário DOC-001**, pois a execução efetuou gravação e leitura no Object Storage real e comprovou integridade e associação de histórico e resultado à mesma execução.

A classificação é **restrita ao armazenamento**. O valor `R005` no JSON persistido é um **dado de fixture**, não uma decisão obtida por IA ou por motor determinístico homologado.

### Não comprovado por este teste

- **H01 completo:** upload pelo endpoint HTTP da API (o script acessou a OCI diretamente).
- **H02 negativo real:** adulteração intencional e bloqueio do processamento em OCI real (há testes com simulação).
- **H03/H04:** qualidade da extração Gemini/OCR com serviço real.
- **H05–H08:** RAG definitivo, confirmação independente de alerta e motor I4 reais.
- **H10 real:** falha parcial de gravação ou leitura em Object Storage real (há testes com simulação).
- **H11:** habilitação segura e composição real do endpoint `/processar`.
- Homologação dos três cenários DOC-001, DOC-002 e DOC-005 ponta a ponta.

## 6. Retenção, segurança e próximos passos

- Manter somente arquivos **sintéticos** em testes; não registrar dados reais de pacientes.
- Não divulgar chaves privadas, tokens, arquivo `~/.oci/config`, cabeçalhos de autorização ou logs contendo credenciais.
- Registrar as quatro chaves criadas em controle operacional privado para futura retenção ou limpeza autorizada; não executar exclusão automática nem repetir o teste sem necessidade.
- Preparar H10 por **injeção controlada de falhas em ambiente de testes**, sem provocar falhas destrutivas no bucket.
- Revalidar H09 quando houver mudança relevante no cliente OCI, adaptador de persistência ou composição final da aplicação.
- Prosseguir com as homologações dos demais integrantes sem alterar o significado desta evidência.

## 7. Reprodução autorizada (não executar na CI)

O comando abaixo **cria quatro objetos novos** a cada execução. Usá-lo somente com perfil OCI autorizado, ambiente de desenvolvimento e ciência do custo/retenção dos objetos.

```powershell
# Na raiz do repositório, com SDK OCI e perfil local já configurados.
$env:MEDIFLOW_ENV = "development"
$env:OCI_BUCKET = "mediflow-docs-dev"
# OCI_CONFIG_FILE e OCI_CONFIG_PROFILE devem apontar para o perfil autorizado.

# Planejamento: não acessa nem escreve na OCI.
.\.venv\Scripts\python.exe .\scripts\homologar_h09_oci_real.py

# Execução autorizada: cria e confirma quatro novos objetos.
.\.venv\Scripts\python.exe .\scripts\homologar_h09_oci_real.py --execute
```

**Não incluir credenciais, identificadores completos das chaves, prints não sanitizados ou resultados clínicos reais na documentação pública.**
