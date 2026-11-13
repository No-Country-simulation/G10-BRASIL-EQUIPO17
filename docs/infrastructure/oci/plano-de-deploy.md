# Plano de Deploy — MediFlow na OCI (Always Free)

## 1. Objetivo

Documentar o estado atual da infraestrutura OCI e estabelecer uma proposta de implantação do MediFlow utilizando recursos elegíveis ao modelo Always Free da Oracle Cloud Infrastructure.

O objetivo é disponibilizar a aplicação para demonstração e testes do hackathon, priorizando baixo custo, simplicidade operacional e segurança.

Este documento apresenta uma proposta técnica e seus pré-requisitos. Não representa autorização para provisionar recursos ou alterar a infraestrutura compartilhada.

## 2. Estado atual da infraestrutura

**Compartment:** `mediflow-dev`
**Região:** Brazil East (São Paulo)
**Modalidade planejada:** OCI Always Free

### 2.1 Recursos identificados

- Object Storage: bucket `mediflow-docs-dev`.
- Notifications: tópico `mediflow-alertas-dev`.
- Monitoring: alarme `mediflow-storage-capacity-dev` (desabilitado).
- Logging: grupo `_Audit`.
- IAM: policies relacionadas à auditoria e ao acesso ao Object Storage.

### 2.2 Recursos não identificados na consulta ao compartment

- VCNs.
- Subnets.
- Internet Gateways, NAT Gateways e Service Gateways.
- Compute Instances.
- Load Balancers.
- Vault.

A ausência desses recursos foi constatada na consulta ao compartment e não deve ser interpretada como ausência em toda a tenancy.

## 3. Arquitetura proposta para o Always Free

A proposta inicial é utilizar uma única instância OCI Compute Ampere A1 para hospedar a aplicação MediFlow.

A arquitetura prevista é composta pelos seguintes elementos:

1. **VCN:** rede virtual isolada para os recursos da aplicação.
2. **Subnet pública:** sub-rede destinada à instância de hospedagem, caso seja adotado acesso direto pela internet.
3. **Internet Gateway:** permitir comunicação entre a instância e a internet, conforme as regras de roteamento e segurança.
4. **Compute Instance:** máquina virtual Linux utilizando a forma `VM.Standard.A1.Flex`.
5. **Aplicação MediFlow:** execução da API e dos componentes da aplicação na instância.
6. **Object Storage:** utilização do bucket existente `mediflow-docs-dev` para armazenamento de documentos, conforme as necessidades da aplicação.
7. **Monitoring e Logging:** acompanhamento da infraestrutura e da aplicação.

### 3.1 Configuração inicial de Compute

A configuração pretendida para a instância é:

| Parâmetro | Configuração proposta |
|---|---|
| Serviço | OCI Compute |
| Shape | `VM.Standard.A1.Flex` |
| Arquitetura | ARM64 (Ampere) |
| OCPUs | Até 2 |
| Memória | Até 12 GB |
| Sistema operacional | Distribuição Linux compatível |
| Armazenamento | Boot Volume dentro da cota Always Free |
| Finalidade | Hospedagem da aplicação MediFlow |

A utilização da capacidade máxima gratuita depende dos limites compartilhados da tenancy e da disponibilidade de recursos na região principal.

A compatibilidade das dependências e imagens utilizadas pelo projeto com a arquitetura ARM64 deverá ser validada antes da criação da instância.

### 3.2 Limites gratuitos relevantes

Os principais limites a considerar no planejamento são:

| Recurso | Cota Always Free relevante |
|---|---|
| Compute Ampere A1 | 1.500 OCPU-horas e 9.000 GB-horas mensais, equivalentes a até 2 OCPUs e 12 GB de memória continuamente |
| Block Volume | 200 GB combinados para volumes de inicialização e volumes em blocos |
| Object Storage | Até 20 GB no cenário de conta exclusivamente Always Free |
| Compute AMD Micro | Até duas instâncias `VM.Standard.E2.1.Micro` |
| Load Balancer | Primeiros 10 Mbps elegíveis ao Always Free |

As cotas são compartilhadas na tenancy, e não exclusivas do MediFlow. Os recursos devem ser criados na região principal (*home region*) quando exigido pela modalidade Always Free.

Os limites e a elegibilidade deverão ser confirmados no Console OCI antes do provisionamento.

## 4. Estratégia de implantação da aplicação

A implantação deverá seguir as seguintes etapas:

1. Revisar a estrutura do projeto e identificar os comandos de inicialização da aplicação.
2. Confirmar a versão do Python e as dependências necessárias.
3. Validar a compatibilidade das bibliotecas e imagens com ARM64.
4. Preparar a aplicação para execução no ambiente Linux.
5. Avaliar a utilização de Docker para empacotamento e execução dos componentes.
6. Configurar as variáveis de ambiente necessárias.
7. Instalar e configurar as dependências na instância.
8. Configurar o serviço para inicialização automática após reinicializações.
9. Publicar a aplicação e validar seu acesso externo.
10. Realizar testes funcionais e de integração.

A utilização de Docker é uma alternativa recomendada para padronizar o ambiente, desde que todas as imagens utilizadas tenham suporte à arquitetura ARM64.

## 5. Rede e segurança

A configuração de rede proposta deverá contemplar:

- Criar uma VCN dedicada ao ambiente MediFlow, mediante aprovação.
- Criar uma sub-rede adequada à estratégia de acesso escolhida.
- Configurar Internet Gateway e regras de roteamento, caso seja utilizada uma sub-rede pública.
- Restringir o acesso SSH à instância, permitindo somente origens autorizadas.
- Liberar apenas as portas necessárias para o funcionamento da aplicação.
- Avaliar a utilização de HTTPS para acesso externo.
- Manter o bucket `mediflow-docs-dev` privado.
- Aplicar o princípio do menor privilégio nas policies IAM.
- Não armazenar credenciais diretamente no código ou repositório.
- Utilizar variáveis de ambiente ou mecanismo seguro de gerenciamento de segredos.

Uma sub-rede privada com saída controlada poderá ser avaliada em uma evolução futura, caso a arquitetura exija esse nível adicional de isolamento.

### 5.1 Restrição de exposição pública

A aplicação MediFlow não deverá ser exposta publicamente antes da implementação e validação dos seguintes controles de segurança:

- Autenticação de usuários.
- Autorização e controle de permissões de acesso.
- Comunicação protegida por HTTPS/TLS.
- Controles de acesso à aplicação e à infraestrutura.

Até que esses requisitos sejam atendidos, o acesso à aplicação deverá permanecer restrito a ambientes controlados e origens autorizadas.

A disponibilização pública da aplicação dependerá de validação técnica e aprovação do responsável pela infraestrutura.

## 6. Armazenamento e persistência

O bucket `mediflow-docs-dev` poderá ser utilizado para armazenar documentos e arquivos necessários à aplicação.

Antes da implantação, será necessário:

- Confirmar quais documentos precisam ser persistidos.
- Definir a integração da aplicação com o Object Storage.
- Avaliar a necessidade de banco de dados e sua modalidade de hospedagem.
- Definir política de retenção e recuperação dos documentos.
- Monitorar o consumo de armazenamento para respeitar os limites gratuitos.

A definição da persistência deverá ser alinhada com o responsável pela arquitetura e pela API.

## 7. Monitoramento e observabilidade

A infraestrutura deverá aproveitar os recursos de monitoramento já identificados:

- Acompanhar a métrica `StoredBytes` do bucket `mediflow-docs-dev`.
- Avaliar a habilitação do alarme `mediflow-storage-capacity-dev` após validação e autorização.
- Validar a entrega de notificações pelo tópico `mediflow-alertas-dev`.
- Avaliar a configuração de logs para os componentes da aplicação.
- Monitorar a disponibilidade da instância e o consumo de CPU e memória.
- Definir procedimentos de resposta a falhas e indisponibilidade.

O alarme de capacidade permanece desabilitado até a realização de teste controlado e autorização do responsável pela infraestrutura.

## 8. Controle de custos e limites Always Free

A implantação deverá respeitar as cotas dos serviços elegíveis ao Always Free.

Antes de provisionar qualquer recurso, será necessário:

1. Confirmar a identificação `Always Free-eligible` no Console OCI.
2. Verificar o consumo atual da tenancy em relação às cotas gratuitas.
3. Confirmar a região principal da tenancy.
4. Evitar a criação de recursos pagos ou pertencentes exclusivamente ao período de avaliação gratuita.
5. Acompanhar o consumo de armazenamento, processamento e tráfego.
6. Avaliar os custos de serviços complementares antes de sua utilização.

A modalidade Always Free possui limites de utilização. O uso acima das cotas ou de recursos não elegíveis poderá gerar cobranças, conforme o tipo de conta e a configuração da tenancy.

## 9. Pendências e dependências

| Pendência | Responsável / dependência |
|---|---|
| Validação da arquitetura de deploy | Alinhamento com Bertone e equipe |
| Confirmação da estratégia de hospedagem | Alinhamento técnico |
| Validação da compatibilidade ARM64 | Equipe de desenvolvimento |
| Definição da arquitetura de rede | Aprovação do responsável pela infraestrutura |
| Verificação das cotas Always Free disponíveis | Responsável pela infraestrutura |
| Definição da persistência e banco de dados | Alinhamento com a equipe |
| Configuração de HTTPS e acesso externo | Equipe de infraestrutura |
| Validação das permissões IAM | Responsável pela infraestrutura |
| Teste de entrega de notificações | Autorização para teste controlado |
| Provisionamento da instância | Aprovação do responsável pela infraestrutura |

## 10. Restrições

- Nenhum recurso de hospedagem ou infraestrutura de rede foi provisionado durante esta atividade.
- O alarme `mediflow-storage-capacity-dev` foi criado e permanece desabilitado.
- O provisionamento de novos recursos depende de aprovação do responsável pela infraestrutura.
- Alterações em políticas IAM globais, recursos administrativos ou infraestrutura compartilhada dependem de autorização.
- A implantação deverá utilizar exclusivamente recursos elegíveis ao Always Free, respeitando as cotas disponíveis.
- O projeto deverá utilizar somente dados sintéticos na demonstração do hackathon.

## 11. Conclusão

A infraestrutura existente já disponibiliza armazenamento de objetos, notificações, auditoria e monitoramento básico de capacidade.

Para a futura implantação do MediFlow, propõe-se utilizar uma instância OCI Compute Ampere A1, integrada a uma VCN e aos serviços de armazenamento e monitoramento existentes, respeitando os limites do modelo Always Free.

A execução do deploy depende da validação da arquitetura com a equipe, da compatibilidade da aplicação com ARM64, da definição da persistência e da aprovação do responsável pela infraestrutura.

Este documento estabelece uma proposta inicial de implantação do MediFlow na OCI, que poderá ser refinada conforme a evolução do projeto.