# Auditoria de Segurança — Object Storage

**Bucket:** `mediflow-docs-dev`
**Compartment:** `mediflow-dev`

## Configurações identificadas

| Configuração | Estado |
|---|---|
| Visibility | Private |
| Encryption Key | Oracle managed key |
| Object Versioning | Disabled |

## Análise

- O bucket está privado, restringindo o acesso público.
- A criptografia em repouso está habilitada por padrão no Object Storage, utilizando chave gerenciada pela Oracle.
- O versionamento está desabilitado, deixando os objetos mais expostos à perda de versões anteriores em caso de sobrescrita ou exclusão.

## Recomendações

1. Manter o bucket privado.
2. Avaliar a ativação do versionamento para permitir recuperação de versões anteriores.
3. Avaliar políticas de ciclo de vida para controlar o armazenamento e os custos.
4. Avaliar futuramente o uso de chaves gerenciadas pelo cliente, caso os requisitos de segurança justifiquem a utilização do OCI Vault.

**Importante:** nenhuma configuração foi alterada durante esta auditoria.

## Configurações adicionais

| Configuração | Estado identificado |
|---|---|
| Emit Object Events | Disabled |
| Auto-Tiering | Disabled |
| Lifecycle Policy | Nenhuma cadastrada |

## Análise complementar

- A emissão de eventos de objetos está desabilitada. Recomenda-se avaliar sua utilização para futuras integrações e automações do MediFlow.
- O Auto-Tiering está desabilitado. Sua ativação deverá depender do perfil de acesso e do volume de armazenamento.
- Não existem políticas de ciclo de vida cadastradas. Recomenda-se avaliar regras de retenção e descarte conforme os requisitos do projeto.

**Observação:** as configurações foram apenas consultadas. Nenhuma alteração foi realizada.