"""Motor determinístico de roteamento documental do MediFlow (v0.1).

Não acessa Gemini, RAG externo, OCI nem endpoints HTTP. Respeita a
precedência R001-R006 definida em rules/roteamento.yaml; lê os campos mínimos
em rules/validacao.yaml. Uso apenas educacional com documentos sintéticos.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

import yaml

from mediflow_contracts.models import (
    Alerta,
    Classificacao,
    DecisaoRoteamento,
    EntradaProcessada,
    Evento,
    ExtracaoIA,
    RecuperacaoRAG,
    ResultadoTriagem,
    Validacao,
)

_RAIZ = Path(__file__).resolve().parents[3]
_ARQUIVO_ROTEAMENTO = _RAIZ / "rules" / "roteamento.yaml"
_ARQUIVO_VALIDACAO = _RAIZ / "rules" / "validacao.yaml"
_ORDEM_CANONICA = ("R001", "R002", "R003", "R004", "R005", "R006")
_CONDICOES = {
    "marcador_urgencia_explicito_confirmado",
    "ambiguidade_critica",
    "solicitacao_exame_completa",
    "receituario_completo",
    "documento_rotina_completo",
    "fallback",
}
_CAMPOS_PERMITIDOS = {
    "paciente.nome", "medicamentos[].nome", "medicamentos[].dosagem_texto",
    "exame.nome", "exame.conclusao", "exame.resultados[]", "procedimentos[]",
    "resumo", "data_admissao", "data_alta", "data_emissao", "afastamento_periodo",
}
_DESTINOS_PERMITIDOS = {
    "fila_prioritaria_avaliacao_humana", "auditoria_humana",
    "auditoria_autorizacoes", "fila_farmacia_documental",
    "prontuario_documental", "fila_erros_tecnicos",
}
_PRIORIDADES = {"rotina", "possivel_urgencia", "indeterminada"}
_TIPOS_ROTINA = {"laudo_laboratorial", "laudo_imagem", "relatorio_alta", "atestado"}


def _ler_yaml(caminho: Path) -> dict:
    dados = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    if not isinstance(dados, dict) or str(dados.get("versao")) != "0.1":
        raise ValueError("Configuração de regras com versão ou estrutura inválida.")
    return dados


def _carregar_configuracao(
    caminho_roteamento: Path, caminho_validacao: Path,
) -> tuple[dict, dict[str, tuple[str, ...]]]:
    roteamento = _ler_yaml(caminho_roteamento)
    validacao = _ler_yaml(caminho_validacao)

    ordem = roteamento.get("precedencia")
    regras = roteamento.get("regras")
    campos = validacao.get("campos_minimos_por_categoria")
    if (
        ordem != list(_ORDEM_CANONICA)
        or not isinstance(regras, list)
        or len(regras) != len(_ORDEM_CANONICA)
        or not isinstance(campos, dict)
    ):
        raise ValueError("Precedência, regras ou campos mínimos inválidos.")

    mapa_regras: dict[str, dict] = {}
    for regra in regras:
        if not isinstance(regra, dict):
            raise ValueError("Regra de roteamento inválida.")
        ident = regra.get("id")
        if (
            ident not in _ORDEM_CANONICA
            or ident in mapa_regras
            or regra.get("condicao") not in _CONDICOES
            or regra.get("destino") not in _DESTINOS_PERMITIDOS
            or regra.get("prioridade") not in _PRIORIDADES
            or type(regra.get("requer_revisao_humana")) is not bool
            or not isinstance(regra.get("justificativa"), str)
            or not regra["justificativa"].strip()
        ):
            raise ValueError("Regra de roteamento inconsistente.")
        mapa_regras[ident] = regra.copy()
    if set(mapa_regras) != set(_ORDEM_CANONICA):
        raise ValueError("Conjunto de regras incompleto.")
    for ident, condicao in zip(_ORDEM_CANONICA, (
        "marcador_urgencia_explicito_confirmado", "ambiguidade_critica",
        "solicitacao_exame_completa", "receituario_completo",
        "documento_rotina_completo", "fallback",
    )):
        if mapa_regras[ident]["condicao"] != condicao:
            raise ValueError("A associação entre ID e condição das regras foi modificada.")

    # Regras v0.1 possuem destinos e revisões fixos neste incremento. Não
    # permitir configurações que transformem alertas/ambiguidade em rotina.
    esperado = {
        "R001": ("fila_prioritaria_avaliacao_humana", "possivel_urgencia", True),
        "R002": ("auditoria_humana", "indeterminada", True),
        "R003": ("auditoria_autorizacoes", "rotina", False),
        "R004": ("fila_farmacia_documental", "rotina", False),
        "R005": ("prontuario_documental", "rotina", False),
        "R006": ("auditoria_humana", "indeterminada", True),
    }
    for ident, (destino, prioridade, revisao) in esperado.items():
        r = mapa_regras[ident]
        if (r["destino"], r["prioridade"], r["requer_revisao_humana"]) != (
            destino, prioridade, revisao
        ):
            raise ValueError(f"Configuração insegura da regra {ident}.")
    for regra in mapa_regras.values():
        if regra["destino"] in {"auditoria_humana", "fila_erros_tecnicos", "fila_prioritaria_avaliacao_humana"} and not regra["requer_revisao_humana"]:
            raise ValueError("Destino de exceção deve exigir revisão humana.")

    mapa_campos: dict[str, tuple[str, ...]] = {}
    for categoria, obrigatorios in campos.items():
        if not isinstance(categoria, str) or not isinstance(obrigatorios, list):
            raise ValueError("Campos mínimos inválidos.")
        if not all(c in _CAMPOS_PERMITIDOS for c in obrigatorios):
            raise ValueError("Campo mínimo não reconhecido no contrato.")
        mapa_campos[categoria] = tuple(obrigatorios)
    categorias_esperadas = {
        "receituario", "laudo_laboratorial", "laudo_imagem", "solicitacao_exame",
        "relatorio_alta", "atestado", "outro_desconhecido",
    }
    if set(mapa_campos) != categorias_esperadas or mapa_campos["outro_desconhecido"]:
        raise ValueError("Categorias de validação incompletas.")

    # V001-V004 sao validadas como configuracao: não permitir que uma alteração
    # no YAML silenciosamente desative ou rebaixe verificações documentais.
    validacoes_esperadas = {
        "V001": ("paciente_nome_nao_legivel", "critico", "auditoria_humana"),
        "V002": ("receituario_com_medicamento_sem_dose_legivel", "critico", "auditoria_humana"),
        "V003": ("profissional_nome_ausente", "aviso", "manter_aviso"),
        "V004": ("laudo_imagem_sem_conclusao", "critico", "auditoria_humana"),
    }
    validacoes = validacao.get("validacoes")
    if (
        not isinstance(validacoes, list)
        or len(validacoes) != len(validacoes_esperadas)
        or validacao.get("status_de_campo") != ["legivel", "ausente", "ilegivel", "conflitante"]
    ):
        raise ValueError("Catálogo V001-V004 inválido.")
    encontrados = set()
    for item in validacoes:
        if not isinstance(item, dict):
            raise ValueError("Validação documental inválida.")
        ident = item.get("id")
        if ident in encontrados or ident not in validacoes_esperadas:
            raise ValueError("Identificador de validação inválido.")
        encontrados.add(ident)
        if (item.get("condicao"), item.get("nivel"), item.get("encaminhamento")) != validacoes_esperadas[ident]:
            raise ValueError(f"Validação {ident} alterada ou insegura.")
    if encontrados != set(validacoes_esperadas):
        raise ValueError("Validações documentais incompletas.")

    return mapa_regras, mapa_campos


def _classificar_campos(
    extracao: ExtracaoIA, obrigatorios: tuple[str, ...],
) -> tuple[list[str], list[str], list[str], list[str]]:
    dados = extracao.dados_extraidos
    ausentes: list[str] = []
    ilegiveis: list[str] = []
    conflitos: list[str] = []
    avisos: list[str] = []

    def registrar(campo: str, estado: str) -> None:
        if estado == "ilegivel":
            ilegiveis.append(campo)
        elif estado == "conflitante":
            conflitos.append(campo)
        else:
            ausentes.append(campo)

    for campo in obrigatorios:
        if campo == "paciente.nome":
            if dados.paciente.nome_status != "legivel":
                registrar(campo, dados.paciente.nome_status)
            elif not dados.paciente.nome or not dados.paciente.nome.strip():
                registrar(campo, "ausente")
        elif campo in {"medicamentos[].nome", "medicamentos[].dosagem_texto"}:
            if not dados.medicamentos:
                if "medicamentos[]" not in ausentes:
                    ausentes.append("medicamentos[]")
                continue
            for indice, medicamento in enumerate(dados.medicamentos):
                if campo.endswith(".nome"):
                    if not medicamento.nome or not medicamento.nome.strip():
                        registrar(f"medicamentos[{indice}].nome", "ausente")
                elif medicamento.dosagem_status != "legivel":
                    registrar(f"medicamentos[{indice}].dosagem_texto", medicamento.dosagem_status)
                elif not medicamento.dosagem_texto or not medicamento.dosagem_texto.strip():
                    registrar(f"medicamentos[{indice}].dosagem_texto", "ausente")
        elif campo == "exame.nome":
            if not dados.exame.nome or not dados.exame.nome.strip():
                ausentes.append(campo)
        elif campo == "exame.conclusao":
            if not dados.exame.conclusao or not dados.exame.conclusao.strip():
                ausentes.append(campo)
        elif campo == "exame.resultados[]":
            if not dados.exame.resultados:
                ausentes.append(campo)
        elif campo == "procedimentos[]":
            if not dados.procedimentos:
                ausentes.append(campo)
        elif not getattr(dados, campo, None) or (
            isinstance(getattr(dados, campo, None), str)
            and not getattr(dados, campo).strip()
        ):
            ausentes.append(campo)

    # V003: aviso administrativo, sem forçar auditoria nem inventar profissional.
    if not dados.profissional.nome or not dados.profissional.nome.strip():
        avisos.append("V003: nome do profissional ausente.")
    return ausentes, ilegiveis, conflitos, avisos


@dataclass(frozen=True, slots=True)
class MotorRegrasDeterministico:
    """Implementa DecisorTriagem esperado pelo ServicoTriagem do I1.

    Carrega YAML uma vez, valida a precedência e não usa o RAG como voto.
    Caminhos explícitos são aceitos para testes e ambientes controlados.
    """

    arquivo_roteamento: Path = _ARQUIVO_ROTEAMENTO
    arquivo_validacao: Path = _ARQUIVO_VALIDACAO
    _regras: Mapping[str, dict] = field(init=False, repr=False)
    _campos: Mapping[str, tuple[str, ...]] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        regras, campos = _carregar_configuracao(
            Path(self.arquivo_roteamento), Path(self.arquivo_validacao)
        )
        object.__setattr__(self, "_regras", regras)
        object.__setattr__(self, "_campos", campos)

    def decidir(
        self,
        extracao: ExtracaoIA,
        *,
        entrada: EntradaProcessada,
        rag: RecuperacaoRAG,
        alerta_textual_confirmado: bool,
    ) -> ResultadoTriagem:
        if (
            not isinstance(extracao, ExtracaoIA)
            or not isinstance(entrada, EntradaProcessada)
            or not isinstance(rag, RecuperacaoRAG)
            or type(alerta_textual_confirmado) is not bool
        ):
            raise TypeError("Parâmetros de decisão devem seguir os contratos v0.1.")

        ausentes, ilegiveis, conflitos, avisos = _classificar_campos(
            extracao, self._campos[extracao.tipo_documento]
        )
        incompleto = bool(ausentes or ilegiveis or conflitos)
        suficiente = not incompleto and extracao.tipo_documento != "outro_desconhecido"
        sinais = {
            "marcador_urgencia_explicito_confirmado": alerta_textual_confirmado,
            "ambiguidade_critica": incompleto,
            "solicitacao_exame_completa": suficiente and extracao.tipo_documento == "solicitacao_exame",
            "receituario_completo": suficiente and extracao.tipo_documento == "receituario",
            "documento_rotina_completo": suficiente and extracao.tipo_documento in _TIPOS_ROTINA,
            "fallback": True,
        }
        disparadas = [
            ident for ident in _ORDEM_CANONICA[:-1]
            if sinais[self._regras[ident]["condicao"]]
        ]
        if not disparadas:
            disparadas = ["R006"]
        principal = self._regras[disparadas[0]]
        exige_revisao = principal["requer_revisao_humana"]

        if alerta_textual_confirmado and incompleto:
            avisos.append("Ambiguidade documental concomitante; alerta prioritário mantido.")

        return ResultadoTriagem(
            documento_id=extracao.documento_id,
            status="aguardando_auditoria" if exige_revisao else "processado",
            entrada=entrada.model_copy(deep=True),
            classificacao=Classificacao(
                tipo_documento=extracao.tipo_documento,
                especialidade_texto=extracao.especialidade_texto,
                nivel_prioridade_documental=principal["prioridade"],
                # IndicadorQualidade permanece não calculado, nunca confiança inventada.
            ),
            dados_extraidos=extracao.dados_extraidos.model_copy(deep=True),
            evidencias=[e.model_copy(deep=True) for e in extracao.evidencias],
            validacao=Validacao(
                integridade_documental=(
                    "indeterminada" if extracao.tipo_documento == "outro_desconhecido"
                    else "insuficiente" if incompleto else "suficiente"
                ),
                campos_ausentes=ausentes,
                campos_ilegiveis=ilegiveis,
                conflitos=conflitos,
                observacoes=avisos,
            ),
            rag=rag.model_copy(deep=True),
            decisao_roteamento=DecisaoRoteamento(
                destino_principal=principal["destino"],
                requer_revisao_humana=exige_revisao,
                regra_principal=principal["id"],
                regras_disparadas=disparadas,
                justificativa=principal["justificativa"],
                versao_regras="0.1",
                alertas=[
                    Alerta(
                        codigo="ALERTA_DOCUMENTAL",
                        mensagem="Marcador explícito no original: avaliação humana prioritária.",
                    )
                ] if alerta_textual_confirmado else [],
            ),
            eventos=[
                Evento(codigo="REGRA_APLICADA", descricao=f"Regra {principal['id']} aplicada por precedência.")
            ],
        )


def validar_metadados_resultado(resultado: ResultadoTriagem) -> bool:
    """Confere a saida contra as regras canonicas do I4, sem recalcular a decisao.

    I1 usa esta verificacao para rejeitar destino, prioridade ou status que
    discordem do catalogo validado pelo motor deterministico.
    """
    if not isinstance(resultado, ResultadoTriagem):
        return False

    regras, _ = _carregar_configuracao(
        _ARQUIVO_ROTEAMENTO, _ARQUIVO_VALIDACAO
    )
    decisao = resultado.decisao_roteamento
    regra = regras.get(decisao.regra_principal)
    if regra is None:
        return False

    status_esperado = (
        "aguardando_auditoria"
        if regra["requer_revisao_humana"]
        else "processado"
    )
    return (
        decisao.destino_principal == regra["destino"]
        and decisao.requer_revisao_humana == regra["requer_revisao_humana"]
        and resultado.classificacao.nivel_prioridade_documental == regra["prioridade"]
        and resultado.status == status_esperado
        and decisao.versao_regras == "0.1"
    )
