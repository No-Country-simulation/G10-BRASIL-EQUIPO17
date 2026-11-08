# Inventário da Infraestrutura OCI — MediFlow

## 1. Objetivo

Este documento apresenta o inventário inicial dos recursos de infraestrutura utilizados pelo projeto MediFlow na Oracle Cloud Infrastructure (OCI).

O objetivo é registrar os recursos existentes, suas finalidades e o estado de validação, servindo como base para as atividades de auditoria de segurança, monitoramento e planejamento de deploy.

## 2. Ambiente

| Propriedade | Informação |
|---|---|
| Tenancy | marcosgasco |
| Região | Brazil East (São Paulo) |
| Compartment | mediflow-dev |
| Ambiente | Desenvolvimento |
| Projeto | MediFlow |

## 3. Recursos identificados

| Recurso | Identificação | Situação |
|---|---|---|
| Object Storage Bucket | mediflow-docs-dev | Existente |
| Notifications Topic | mediflow-alertas-dev | Existente |
| Alarm Definition | mediflow-storage-capacity-dev | Criado e desativado |
| IAM Group | mediflow-storage-devs | Existente |
| IAM Group | mediflow-infra-auditors | Existente |
| IAM Group | mediflow-infra-ops | Existente |
| IAM Policy | mediflow-monitoring-ops-policy | Existente |

## 4. Validações realizadas

- Acesso ao compartment mediflow-dev.
- Acesso ao bucket mediflow-docs-dev.
- Acesso à seção Monitoring.
- Criação do alarme mediflow-storage-capacity-dev.
- Consulta aos detalhes do alarme após sua criação.
- Confirmação de que o alarme permanece desativado.

## 5. Recursos pendentes de levantamento

Os itens abaixo ainda precisam ser investigados diretamente no Console OCI:

- Instâncias de Compute.
- Virtual Cloud Networks (VCNs): nenhuma identificada no compartment mediflow-dev durante a consulta inicial.
- Sub-redes.
- Security Lists e Network Security Groups.
- Load Balancers.
- Vault e gerenciamento de chaves.
- Logging e Audit.
- Métricas e alarmes adicionais.

### Resultado da auditoria de Networking

Durante a consulta ao compartment `mediflow-dev`, não foram identificados recursos de rede:

- VCNs: nenhuma identificada.
- Subnets: nenhuma identificada.
- Internet Gateways: nenhum identificado.
- NAT Gateways: nenhum identificado.
- Service Gateways: nenhum identificado.

**Observação:** a ausência desses recursos foi constatada na consulta inicial ao compartment. A arquitetura de rede necessária deverá ser definida conforme a estratégia de implantação da aplicação.

### Resultado da auditoria de Compute

Durante a consulta ao serviço Compute no compartment `mediflow-dev`, não foram identificadas instâncias de máquinas virtuais (Compute Instances).

**Observação:** não há instâncias de Compute identificadas para hospedar a aplicação MediFlow nesse compartment. A necessidade de provisionamento deverá ser avaliada durante o planejamento de deploy.

### Resultado da auditoria de Load Balancers

Durante a consulta ao serviço Load Balancer no compartment `mediflow-dev`, não foram identificados balanceadores de carga.

**Observação:** não há Load Balancers identificados para distribuir o tráfego de uma eventual aplicação hospedada na OCI. A necessidade desse recurso deverá ser avaliada conforme a arquitetura de deploy.

### Resultado da auditoria de Vault

Durante a consulta ao serviço Vault no compartment `mediflow-dev`, não foram identificados recursos Vault.

**Observação:** não foi identificado um Vault nesse compartment para gerenciamento centralizado de chaves de criptografia e segredos. A necessidade de utilização desse serviço deverá ser avaliada conforme os requisitos de segurança e a arquitetura de implantação do MediFlow.

### Resultado da auditoria de Logging

Durante a consulta ao serviço Logging no compartment `mediflow-dev`, foi identificado o seguinte grupo de logs:

- Log Group: `_Audit`

**Observação:** a existência do grupo foi confirmada. Ainda é necessário verificar quais logs estão associados a ele e se estão habilitados.

### Resultado da auditoria de Audit

Durante a consulta aos registros do grupo `_Audit`, foram identificados eventos de auditoria relacionados ao serviço Logging.

Na amostra consultada, foram encontrados cinco eventos com as seguintes características:

- Usuário: Matheus Medeiros.
- Operação: `GET`.
- Tipo: `com.oraclecloud.logging.ListLogGroups`.
- Status: `200` (sucesso).

**Observação:** os registros demonstram que atividades de consulta ao serviço Logging estão sendo auditadas. A amostra não é suficiente para confirmar a cobertura de auditoria de todas as operações e recursos do ambiente.

## 6. Observações

- Não foi identificada uma VCN no compartment mediflow-dev durante o levantamento inicial. A necessidade de criação de infraestrutura de rede deverá ser avaliada conforme a arquitetura de deploy.

Este inventário representa o levantamento inicial do ambiente de desenvolvimento.

A existência de um recurso não significa que todas as suas configurações de segurança ou funcionamento tenham sido auditadas.

As informações pendentes deverão ser verificadas antes da elaboração das recomendações definitivas.
