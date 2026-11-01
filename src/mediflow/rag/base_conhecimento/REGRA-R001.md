---
fonte_id: R001
titulo: Regra de roteamento R001: marcador de urgência explícito confirmado
versao: 0.1
origem: rules/roteamento.yaml
---
Origem: rules/roteamento.yaml (versão 0.1). Simulação administrativa para o Hackathon, não é protocolo clínico. Condição: marcador de urgência explícito confirmado no documento. Destino: fila prioritária de avaliação humana. Requer revisão humana: sim. Prioridade: possível urgência. Justificativa da regra: marcador explícito de alerta no documento, que exige avaliação humana prioritária.

Uso no RAG: referência documental interna. O RAG apenas recupera e cita esta ficha; a execução das condições, a precedência e os destinos são do motor determinístico de regras (I4).
