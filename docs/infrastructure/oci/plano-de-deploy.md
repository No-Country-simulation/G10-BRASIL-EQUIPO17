# Plano de Deploy — MediFlow na OCI

## 1. Objetivo

Documentar o estado atual da infraestrutura OCI e estabelecer os pré-requisitos para uma futura implantação do MediFlow.

Este documento apresenta recomendações e pendências. Não representa autorização para provisionar recursos.

## 2. Estado atual da infraestrutura

Compartment: `mediflow-dev`
Região: Brazil East (São Paulo)

### Recursos identificados

- Object Storage: bucket `mediflow-docs-dev`.
- Notifications: tópico `mediflow-alertas-dev`.
- Monitoring: alarme `mediflow-storage-capacity-dev` (desabilitado).
- Logging: grupo `_Audit`.
- IAM: policies relacionadas à auditoria e ao acesso ao Object Storage.

### Recursos não identificados na consulta ao compartment

- VCNs.
- Subnets.
- Internet Gateways, NAT Gateways e Service Gateways.
- Compute Instances.
- Load Balancers.
- Vault.

A ausência desses recursos foi constatada na consulta ao compartment e não deve ser interpretada como ausência em toda a tenancy.

## 3. Pré-requisitos para implantação

Antes de qualquer provisionamento, será necessário:

1. Definir a arquitetura de hospedagem da API e da interface do MediFlow.
2. Definir se a implantação será realizada em Compute, serviço gerenciado ou plataforma externa.
3. Avaliar a necessidade de VCN, sub-redes e gateways.
4. Definir regras de segurança de rede e exposição dos serviços.
5. Confirmar as permissões IAM necessárias.
6. Definir armazenamento, retenção e proteção dos documentos.
7. Planejar logs, métricas, alarmes e notificações.
8. Avaliar custos e limites dos recursos escolhidos.

## 4. Recomendações de segurança

- Manter o bucket `mediflow-docs-dev` privado.
- Aplicar o princípio do menor privilégio nas policies IAM.
- Não armazenar credenciais diretamente no código ou repositório.
- Utilizar variáveis de ambiente ou mecanismo seguro de gerenciamento de segredos.
- Avaliar o uso de HTTPS e controles de acesso para os serviços publicados.
- Definir política de retenção e recuperação de documentos.
- Utilizar somente dados sintéticos na demonstração do hackathon.

## 5. Monitoramento e observabilidade

- Manter o acompanhamento da métrica `StoredBytes`.
- Avaliar a habilitação do alarme `mediflow-storage-capacity-dev` após validação e autorização.
- Validar a entrega de notificações pelo tópico `mediflow-alertas-dev`.
- Avaliar a criação e configuração de logs para os componentes da aplicação.
- Definir procedimentos de resposta a falhas e indisponibilidade.

## 6. Pendências e dependências

| Pendência | Responsável / dependência |
|---|---|
| Definição da arquitetura de deploy | Alinhamento com Bertone e equipe |
| Decisão sobre Compute ou serviço gerenciado | Alinhamento técnico |
| Definição da arquitetura de rede | Aprovação do responsável pela infraestrutura |
| Avaliação de custos | Antes do provisionamento |
| Validação das permissões IAM | Responsável pela infraestrutura |
| Teste de entrega de notificações | Autorização para teste controlado |
| Definição de retenção dos documentos | Alinhamento com a equipe |

## 7. Restrições

Nenhum recurso de infraestrutura adicional foi provisionado durante esta atividade.

Alterações em políticas IAM globais, recursos administrativos ou infraestrutura compartilhada dependem de aprovação do responsável pela infraestrutura.

## 8. Conclusão

A infraestrutura existente já disponibiliza armazenamento de objetos, notificações, auditoria e monitoramento básico de capacidade.

Entretanto, a arquitetura necessária para hospedar e publicar a aplicação ainda precisa ser definida e aprovada.

Este plano serve como base para o planejamento da implantação futura do MediFlow na OCI.