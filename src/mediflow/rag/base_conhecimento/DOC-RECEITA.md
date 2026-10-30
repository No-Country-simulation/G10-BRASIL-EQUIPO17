---
fonte_id: DOC-RECEITA
titulo: Ficha do tipo de documento: Receituário
versao: 0.1
---
Campos mínimos de um receituário para a completude documental, segundo rules/validacao.yaml (versão 0.1): nome do paciente, nome de cada medicamento e dosagem em texto de cada medicamento. Cada campo extraído tem um status: legível, ausente, ilegível ou conflitante. Paciente com nome não legível (V001) e receituário com medicamento sem dose legível (V002) são validações críticas e seguem para auditoria humana. Nome do profissional ausente gera apenas aviso (V003). Campo ausente ou ilegível nunca é preenchido por suposição.
