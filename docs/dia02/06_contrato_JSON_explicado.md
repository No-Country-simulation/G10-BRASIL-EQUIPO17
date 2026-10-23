# Para que serve o Contrato JSON do MediFlow?

O contrato JSON é um acordo entre os módulos que estabelece **nomes, tipos e formato dos dados**. Não é um contrato jurídico. Ele impede, por exemplo, que a IA envie `nome_paciente` enquanto o roteador espere `paciente.nome`.

O Dia 2 prevê três contratos:

1. `schemas/entrada_texto.schema.json`: dados aceitos na API para entrada textual;
2. `schemas/extracao_ia.schema.json`: saída padronizada da IA multimodal;
3. `schemas/resultado_triagem.schema.json`: resultado consolidado a ser consumido pela interface e persistência.

Os modelos Pydantic, fonte canônica, ficam em `src/mediflow_contracts/models.py`. O JSON Schema deriva deles e **não deve ser editado à mão**.

### Exemplo didático reduzido (não representa sozinho um JSON válido do contrato completo)

```json
{
  "tipo_documento": "receituario",
  "paciente": {"nome": "Maria Exemplo"},
  "medicamento": {"nome": "Amoxicilina", "dosagem_texto": null, "dosagem_status": "ilegivel"}
}
```

O resultado real segue a estrutura aninhada em `ExtracaoIA` e `DadosExtraidos`. Pydantic verifica, por exemplo, que `dosagem_status="ilegivel"` **não pode** coexistir com uma `dosagem_texto` supostamente legível.

Após validação, o motor de regras aplica **R002 (ambiguidade crítica)** e encaminha para revisão humana. Se houver um marcador prioritário R001 confirmado, a urgência prevalece.

O contrato não garante que a IA compreendeu corretamente um documento: ele garante que **o formato é válido e algumas incoerências estruturais foram evitadas**. Correção factual exige confronto com o documento e testes próprios.
