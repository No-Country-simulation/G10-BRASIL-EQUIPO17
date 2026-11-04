
import json
import re

from mediflow_contracts.models import EntradaTexto, ExtracaoIA

def validar_extracao(
    documento_id: str,
    resposta_modelo: str,
    documento_texto: str | None = None,
) -> ExtracaoIA:
    """Valida o JSON, o contrato e as referências das evidências."""

    try:
        dados = json.loads(resposta_modelo)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "A resposta do modelo não é um JSON válido."
        ) from exc

    if not isinstance(dados, dict):
        raise ValueError("A resposta do modelo deve ser um objeto JSON.")

    if dados.get("documento_id") != documento_id:
        raise ValueError(
            "O documento_id da resposta não corresponde à entrada."
        )

    resultado = ExtracaoIA.model_validate(dados)

    if documento_texto is not None:
        paginas = {
            int(numero): texto
            for numero, texto in re.findall(
                r"\[Página (\d+)\]\s*(.*?)(?=\[Página \d+\]|\Z)",
                documento_texto,
                flags=re.DOTALL,
            )
        }

        normalizar = lambda texto: " ".join(texto.split())

        for evidencia in resultado.evidencias:
            if evidencia.pagina is None:
                continue

            texto_pagina = paginas.get(evidencia.pagina)

            if texto_pagina is None:
                raise ValueError(
                    "A evidência referencia uma página inexistente."
                )

            normalizar = lambda texto: " ".join(texto.split())

            if normalizar(evidencia.trecho_documento) not in normalizar(
                texto_pagina
            ):
                raise ValueError(
                    "O trecho da evidência não foi encontrado na página informada."
                )

    return resultado


def preparar_entrada(entrada: EntradaTexto) -> dict:
    """
    Prepara os dados para serem enviados ao modelo de IA.
    Ainda não realiza uma chamada externa.
    """
    return {
        "documento_id": entrada.documento_id,
        "documento_texto": entrada.documento_texto,
        "instrucao": (
            "Extraia somente informações presentes no documento. "
            "Não invente dados. Marque campos ausentes ou ilegíveis "
            "conforme o contrato de extração."
        ),
    }
