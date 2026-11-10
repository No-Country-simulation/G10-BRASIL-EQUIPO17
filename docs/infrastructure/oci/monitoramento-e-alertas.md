# Monitoramento e Alertas — OCI

## Alarme de capacidade do Object Storage

**Nome:** `mediflow-storage-capacity-dev`
**Compartment:** `mediflow-dev`
**Métrica:** `StoredBytes`
**Namespace:** `oci_objectstorage`
**Bucket monitorado:** `mediflow-docs-dev`
**Limite configurado:** 1 GiB (1.073.741.824 bytes)
**Condição:** Maior que o limite configurado
**Severidade:** Warning
**Estado:** Disabled

### Expressão de consulta (MQL)

```text
StoredBytes[1h]{resourceDisplayName = "mediflow-docs-dev"}.mean() > 1073741824
```

### Parâmetros de avaliação

| Parâmetro | Valor |
|---|---|
| Intervalo | 1 hora |
| Estatística | Mean |
| Dimensão | `resourceDisplayName` |
| Valor da dimensão | `mediflow-docs-dev` |
| Operador | Maior que (`>`) |
| Limite | 1.073.741.824 bytes |
| Severidade | Warning |

### Configuração de notificações

**Serviço:** OCI Notifications
**Tópico:** `mediflow-alertas-dev`

### Validações realizadas

- Alarme criado com sucesso.
- Alarme localizado na lista de definições.
- Detalhes do alarme consultados.
- Estado Disabled confirmado.
- Tópico `mediflow-alertas-dev` confirmado como destino.

### Limitações

O alarme permanece desabilitado para evitar notificações durante os testes.

Não foi realizado teste de disparo do alarme nem confirmação de entrega de e-mail.

### Recomendação

Realizar posteriormente um teste controlado de notificação, mediante autorização do responsável pela infraestrutura.

## Resultado da consulta no Metrics Explorer

Foi realizada uma consulta no OCI Metrics Explorer com os seguintes parâmetros:

- Compartment: `mediflow-dev`
- Namespace: `oci_objectstorage`
- Métrica: `StoredBytes`
- Statistic: `Mean`
- Interval: `1 hour`
- Dimension: `resourceDisplayName = mediflow-docs-dev`
- Período: últimos 7 dias.

**Resultado:** gráfico apresentado com dados da métrica `StoredBytes`.

### Conclusão

Foi possível confirmar a disponibilidade de dados da métrica utilizada pelo alarme `mediflow-storage-capacity-dev`.

O alarme permanece desabilitado e não foi realizado teste de disparo ou entrega de notificações.

### Interpretação visual da métrica

O gráfico apresentou valores aproximadamente entre 300.000 e 350.000 bytes durante o período consultado.

Foi observado um pequeno aumento no meio do período, seguido de estabilidade até o final.

**Conclusão:** a métrica `StoredBytes` apresenta dados disponíveis para o bucket monitorado, permitindo acompanhar sua evolução de armazenamento.