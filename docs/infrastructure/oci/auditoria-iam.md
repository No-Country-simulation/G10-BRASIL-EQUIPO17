# Auditoria de IAM — OCI

## Resultado da verificação inicial

Durante a consulta ao menu Identity & Security da OCI, foram identificadas as seguintes limitações:

| Recurso | Resultado |
|---|---|
| Domains | Nenhum domínio visível |
| Users | Opção não disponível |
| Groups | Opção não disponível |
| Policies | Opção disponível |

Os grupos `mediflow-storage-devs`, `mediflow-infra-auditors` e `mediflow-infra-ops` foram informados pelo responsável pela infraestrutura, mas não foi possível verificar diretamente seus detalhes e associações.

**Observação:** a ausência de opções de consulta não comprova a inexistência dos recursos. A auditoria de usuários e grupos permanece parcialmente pendente devido às permissões disponíveis para a conta.

## Policies identificadas

Durante a consulta ao menu Policies da OCI, foram identificadas quatro policies relacionadas ao MediFlow:

| Policy | Statements | Descrição |
|---|---:|---|
| `mediflow-infra-audit-policy` | 8 | Consulta para auditoria IAM, infraestrutura e observabilidade |
| `mediflow-i2-object-storage-policy` | 4 | Leitura e gerenciamento de objetos no bucket do projeto |
| `mediflow-devs-storage-access-policy` | 2 | Leitura de buckets e gerenciamento de objetos |
| `mediflow-storage-policy` | 1 | Gerenciamento de buckets e objetos |

### Divergência identificada

A policy `mediflow-monitoring-ops-policy`, anteriormente informada como existente, não foi localizada na listagem consultada.

É necessário confirmar com o responsável pela infraestrutura se essa policy foi renomeada, substituída ou se está em outro escopo.

**Observação:** as instruções das quatro policies ainda precisam ser analisadas para verificar o escopo e o princípio do menor privilégio.

## Análise da policy mediflow-infra-audit-policy

**Grupo associado:** `mediflow-infra-auditors`
**Domínio:** `Default`
**Compartment:** `mediflow-dev`
**Quantidade de statements:** 8

### Permissões identificadas

- `inspect policies`
- `inspect all-resources`
- `read instances`
- `read virtual-network-family`
- `read metrics`
- `read alarms`
- `read log-groups`
- `read audit-events`

### Avaliação de segurança

As oito instruções estão limitadas ao compartment `mediflow-dev`.

As permissões identificadas são de consulta e leitura, sem concessões explícitas de gerenciamento ou alteração de recursos.

A permissão `inspect all-resources` oferece visibilidade ampla dos recursos do compartment, devendo ser mantida apenas para integrantes que realmente necessitem dessa abrangência.

**Conclusão:** a policy apresenta uma configuração compatível com atividades de auditoria de infraestrutura e observabilidade, respeitando o escopo do compartment.

**Limitação:** não foi possível verificar diretamente os membros do grupo devido à indisponibilidade da consulta de Groups na interface da conta.

## Análise da policy mediflow-i2-object-storage-policy

**Grupo associado:** `mediflow-i2-devs`
**Domínio:** `Default`
**Compartment:** `mediflow-dev`
**Quantidade de statements:** 4

### Permissões identificadas

1. `read buckets` no compartment `mediflow-dev`.
2. `read objects` no bucket `mediflow-docs-dev`.
3. `manage objects` com `OBJECT_CREATE` no caminho `originais/I2-*/`.
4. `manage objects` com `OBJECT_CREATE` no caminho `metadados/I2-*/`.

### Avaliação de segurança

- A leitura dos objetos está restrita ao bucket `mediflow-docs-dev`.
- A criação de objetos está limitada aos caminhos específicos destinados à equipe I2.
- A condição `request.permission='OBJECT_CREATE'` restringe a permissão de gerenciamento às operações de criação.
- A permissão `read buckets` possui escopo mais amplo, abrangendo os buckets do compartment `mediflow-dev`.

### Recomendações

- Avaliar se a leitura de metadados de todos os buckets do compartment é realmente necessária.
- Confirmar se a restrição aos caminhos `originais/I2-*/` e `metadados/I2-*/` corresponde à organização de armazenamento definida pelo projeto.
- Manter o princípio do menor privilégio.

**Conclusão:** a policy apresenta restrições específicas para criação de objetos, mas possui uma permissão de consulta de buckets com escopo mais amplo.

## Análise da policy mediflow-devs-storage-access-policy

**Grupo associado:** `mediflow-storage-devs`
**Domínio:** `Default`
**Compartment:** `mediflow-dev`
**Quantidade de statements:** 2

### Permissões identificadas

1. `read buckets` no compartment `mediflow-dev`.
2. `read objects` no bucket `mediflow-docs-dev`.

### Avaliação de segurança

- A policy concede somente permissões de leitura.
- A consulta de buckets abrange o compartment `mediflow-dev`.
- A leitura dos objetos está restrita ao bucket `mediflow-docs-dev`.
- Não foram identificadas permissões explícitas de criação, exclusão ou gerenciamento de objetos.

### Comparação com a policy da equipe I2

A policy apresenta permissões de leitura semelhantes às da `mediflow-i2-object-storage-policy`.

A diferença é que a policy da equipe I2 também concede criação de objetos em caminhos específicos.

Essa diferenciação pode representar uma separação intencional de responsabilidades entre as equipes.

**Conclusão:** a policy apresenta permissões de leitura compatíveis com o acesso de consulta ao armazenamento do MediFlow.

## Análise da policy mediflow-storage-policy

**Grupo associado:** `Administrators`
**Domínio:** `Default`
**Compartment:** `mediflow-dev`
**Quantidade de statements:** 1

### Permissão identificada

- `manage object-family` no compartment `mediflow-dev`.

### Avaliação de segurança

A policy concede permissões administrativas amplas sobre os recursos da família Object Storage no compartment `mediflow-dev`.

O escopo da permissão está limitado ao compartment do MediFlow.

### Ponto de atenção

É necessário verificar se os integrantes do grupo `Administrators` realmente precisam desse nível de acesso ao Object Storage do projeto.

Recomenda-se manter o acesso administrativo restrito às pessoas responsáveis pela gestão da infraestrutura.

**Limitação:** não foi possível verificar diretamente os integrantes do grupo `Administrators` devido à indisponibilidade da consulta de Groups na interface da conta.