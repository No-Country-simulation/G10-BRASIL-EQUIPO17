"""Ponte I1/I3: ExtracaoIA -> ConsultaRAG -> RecuperacaoRAG.

Este módulo não importa o PR #16 (ainda em Draft), não decide regras e não
executa consultas externas. O construtor de ConsultaRAG é injetado quando I3
estiver integrado à develop. Uso exclusivo com documentos sintéticos do MVP.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

from mediflow_contracts.models import ExtracaoIA, RecuperacaoRAG


class RecuperadorDeConsultas(Protocol):
    """Porta estrutural do I3: buscar(ConsultaRAG) -> RecuperacaoRAG."""

    def buscar(self, consulta: Any) -> RecuperacaoRAG: ...


# Vocabulário controlado: não interpolar campos livres de ExtracaoIA na busca.
_TIPO_BUSCA = {
    "receituario": "receituario receita medicamento dosagem",
    "laudo_laboratorial": "laudo laboratorial exame resultados",
    "laudo_imagem": "laudo imagem exame achados",
    "solicitacao_exame": "solicitacao exame guia",
    "relatorio_alta": "relatorio alta documento",
    "atestado": "atestado documento",
    "outro_desconhecido": "tipo desconhecido documento auditoria",
}
_STATUS_PROBLEMA = ("ausente", "ilegivel", "conflitante")


def construir_texto_consulta(extracao: ExtracaoIA) -> str:
    """Produz termos para *referências*, nunca indicação de prioridade.

    Somente categorias/estados de campo. Exclui deliberadamente nomes,
    identificadores, valores laboratoriais, medicamentos, CID, evidências,
    transcrição de urgência e qualquer texto livre extraído pela IA.
    """
    if not isinstance(extracao, ExtracaoIA):
        raise TypeError("ExtracaoIA validada é obrigatória.")

    termos = [
        _TIPO_BUSCA[extracao.tipo_documento],
        "campos minimos validacao documental",
    ]
    nome_status = extracao.dados_extraidos.paciente.nome_status
    if nome_status in _STATUS_PROBLEMA:
        termos.append(f"nome {nome_status}")

    if extracao.dados_extraidos.medicamentos:
        termos.append("medicamento")
        estados_dosagem = {
            medicamento.dosagem_status for medicamento in extracao.dados_extraidos.medicamentos
        }
        for estado in _STATUS_PROBLEMA:
            if estado in estados_dosagem:
                termos.append(f"dosagem {estado}")

    return " ".join(termos)


@dataclass(frozen=True, slots=True)
class AdaptadorRAGI3:
    """Implementa ProvedorRAG do I1 sem depender do código ainda não mergeado.

    Após #16: AdaptadorRAGI3(
        recuperador=criar_recuperador_padrao(), fabrica_consulta=ConsultaRAG
    ). Não criar consultas reais ou iniciar serviços no import.
    """

    recuperador: RecuperadorDeConsultas
    fabrica_consulta: Callable[..., Any]
    limite: int = 3

    def __post_init__(self) -> None:
        if not callable(getattr(self.recuperador, "buscar", None)):
            raise TypeError("Recuperador I3 com método buscar é obrigatório.")
        if not callable(self.fabrica_consulta):
            raise TypeError("Construtor de ConsultaRAG é obrigatório.")
        if type(self.limite) is not int or not 1 <= self.limite <= 10:
            raise ValueError("limite deve ser um inteiro entre 1 e 10.")

    def buscar(self, extracao: ExtracaoIA) -> RecuperacaoRAG:
        texto = construir_texto_consulta(extracao)
        consulta = self.fabrica_consulta(texto=texto, limite=self.limite)
        if (
            getattr(consulta, "texto", None) != texto
            or getattr(consulta, "limite", None) != self.limite
        ):
            raise ValueError("Construtor de ConsultaRAG retornou parâmetros inconsistentes.")

        # I1 converte exceções em status=falha, sem promover RAG a motor de decisão.
        retorno = self.recuperador.buscar(consulta)
        return RecuperacaoRAG.model_validate(retorno).model_copy(deep=True)
