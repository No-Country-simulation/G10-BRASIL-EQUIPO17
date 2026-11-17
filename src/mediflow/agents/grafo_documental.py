"""Grafo condicional I4 para o roteamento documental administrativo v0.1.

O LangGraph coordena as etapas e materializa cada caminho R001-R006;
MotorRegrasDeterministico e os YAMLs sao a unica fonte de decisao.
Nenhuma chamada de LLM/RAG/OCI ou acesso HTTP ocorre neste modulo.
Somente documentos sintéticos; não é triagem clínica.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypedDict

from mediflow.rules.motor_deterministico import MotorRegrasDeterministico
from mediflow_contracts.models import EntradaProcessada, ExtracaoIA, RecuperacaoRAG, ResultadoTriagem

REGRAS = ("R001", "R002", "R003", "R004", "R005", "R006")


class EstadoDocumental(TypedDict, total=False):
    extracao: ExtracaoIA
    entrada: EntradaProcessada
    rag: RecuperacaoRAG
    alerta_textual_confirmado: bool
    resultado: ResultadoTriagem
    rota_confirmada: str


def _validar_estado(estado: EstadoDocumental) -> dict:
    if (
        not isinstance(estado.get("extracao"), ExtracaoIA)
        or not isinstance(estado.get("entrada"), EntradaProcessada)
        or not isinstance(estado.get("rag"), RecuperacaoRAG)
        or type(estado.get("alerta_textual_confirmado")) is not bool
    ):
        raise TypeError("Estado do agente incompatível com os contratos v0.1.")
    return {"extracao": estado["extracao"].model_copy(deep=True)}


def _proxima_rota(estado: EstadoDocumental) -> str:
    resultado = estado["resultado"]
    regra = resultado.decisao_roteamento.regra_principal
    if regra not in REGRAS or regra not in resultado.decisao_roteamento.regras_disparadas:
        raise ValueError("Decisão de roteamento inconsistente.")
    return regra


def _marcar_rota(regra: str):
    def executar(estado: EstadoDocumental) -> dict:
        resultado = estado["resultado"]
        if resultado.decisao_roteamento.regra_principal != regra:
            raise ValueError("Rota do grafo diferente da regra principal.")
        return {"rota_confirmada": regra}
    return executar


def _concluir(estado: EstadoDocumental) -> dict:
    if estado.get("rota_confirmada") != _proxima_rota(estado):
        raise ValueError("O grafo não confirmou o encaminhamento.")
    return {"rota_confirmada": estado["rota_confirmada"]}


@dataclass(slots=True)
class GrafoDocumentalI4:
    """Implementa DecisorTriagem com StateGraph condicional R001-R006.

    A validacao do documento original/confirmacao independente e feita por
    ServicoTriagem antes da chamada de decidir(). Nao executa esse passo aqui.
    O grafo NUNCA invoca servicos remotos nem decide com texto livre do RAG.
    """

    motor: MotorRegrasDeterministico = field(default_factory=MotorRegrasDeterministico)
    _grafo: object = field(init=False, repr=False)

    def __post_init__(self) -> None:
        # Dependência já declarada em pyproject.toml [ai], import tardio.
        from langgraph.graph import END, START, StateGraph

        fluxo = StateGraph(EstadoDocumental)
        fluxo.add_node("validar_contratos", _validar_estado)
        fluxo.add_node("avaliar_regras", self._avaliar_regras)
        for regra in REGRAS:
            fluxo.add_node(f"rota_{regra}", _marcar_rota(regra))
        fluxo.add_node("concluir", _concluir)

        fluxo.add_edge(START, "validar_contratos")
        fluxo.add_edge("validar_contratos", "avaliar_regras")
        fluxo.add_conditional_edges(
            "avaliar_regras", _proxima_rota,
            {regra: f"rota_{regra}" for regra in REGRAS},
        )
        for regra in REGRAS:
            fluxo.add_edge(f"rota_{regra}", "concluir")
        fluxo.add_edge("concluir", END)
        self._grafo = fluxo.compile()

    def _avaliar_regras(self, estado: EstadoDocumental) -> dict:
        return {"resultado": self.motor.decidir(
            estado["extracao"],
            entrada=estado["entrada"],
            rag=estado["rag"],
            alerta_textual_confirmado=estado["alerta_textual_confirmado"],
        )}

    def decidir(
        self,
        extracao: ExtracaoIA,
        *,
        entrada: EntradaProcessada,
        rag: RecuperacaoRAG,
        alerta_textual_confirmado: bool,
    ) -> ResultadoTriagem:
        estado: EstadoDocumental = {
            "extracao": extracao.model_copy(deep=True) if isinstance(extracao, ExtracaoIA) else extracao,
            "entrada": entrada.model_copy(deep=True) if isinstance(entrada, EntradaProcessada) else entrada,
            "rag": rag.model_copy(deep=True) if isinstance(rag, RecuperacaoRAG) else rag,
            "alerta_textual_confirmado": alerta_textual_confirmado,
        }
        final = self._grafo.invoke(estado)
        resultado = ResultadoTriagem.model_validate(final["resultado"])
        if final.get("rota_confirmada") != resultado.decisao_roteamento.regra_principal:
            raise ValueError("O grafo retornou uma rota inconsistente.")
        return resultado.model_copy(deep=True)
