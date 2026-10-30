---
fonte_id: CAMPOS-MINIMOS
titulo: Campos mínimos por categoria de documento
versao: 0.1
---
Origem: rules/validacao.yaml (versão 0.1). Campos usados para simular completude documental, sem inferência clínica. Receituário: paciente.nome, medicamentos[].nome, medicamentos[].dosagem_texto. Laudo laboratorial: paciente.nome, exame.nome, exame.conclusao, exame.resultados[]. Laudo de imagem: paciente.nome, exame.nome, exame.conclusao. Solicitação de exame: paciente.nome, procedimentos[]. Relatório de alta: paciente.nome, resumo, data_admissao, data_alta. Atestado: paciente.nome, data_emissao, afastamento_periodo. Outro desconhecido: nenhum campo mínimo.
