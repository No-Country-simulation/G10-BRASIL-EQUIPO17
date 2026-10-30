---
fonte_id: STATUS-CAMPO
titulo: Status dos campos extraídos
versao: 0.1
---
Origem: src/mediflow_contracts/models.py (StatusCampo). Cada campo extraído tem um status: legível, ausente, ilegível ou conflitante. Nome e dosagem só podem ter valor quando o status é legível, e o status legível exige valor. Um campo que não esteja legível nunca recebe valor preenchido por suposição.
