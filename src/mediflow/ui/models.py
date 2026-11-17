"""
Tradução do contrato v0.1 da API para o modelo usado pelas páginas.

A API devolve `ResultadoTriagem` (src/mediflow_contracts/models.py). As páginas
nunca leem esse JSON cru: passam sempre por `normalize_document`, que o
converte num dicionário com estrutura garantida e rótulos legíveis. Um campo
em falta degrada a UI ("—") em vez de a partir. É o único sítio da UI que
conhece os nomes de campos do contrato.
"""

from __future__ import annotations

from typing import Any

from mediflow.ui.config import (
    DESTINATIONS, DOCUMENT_TYPES, DONE_STATUSES, FIELD_STATUS_LABELS, LOW_CONFIDENCE_THRESHOLD,
    PRIORITIES, REVIEW_STATUSES, RULES, STATUSES,
)

# Valor do contrato -> chave interna da UI.
_PRIORITY_FROM_CONTRACT = {spec["contract"]: key for key, spec in PRIORITIES.items()}
_STATUS_FROM_CONTRACT = {spec["contract"]: key for key, spec in STATUSES.items() if "contract" in spec}
# Chave interna -> valor do contrato (para enviar correções da auditoria).
PRIORITY_TO_CONTRACT = {key: spec["contract"] for key, spec in PRIORITIES.items()}


def _d(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> list:
    return value if isinstance(value, list) else []


def _field_value(value: Any, status: str | None) -> str:
    """Valor de um campo com `StatusCampo`: o texto se legível, senão o estado entre parênteses."""
    if value:
        return str(value)
    return FIELD_STATUS_LABELS.get(status or "", "—")


def _flags(raw: dict, validation: dict, decision: dict, confidence: float | None) -> list[str]:
    """Sinalizações a mostrar, derivadas da validação e da decisão de roteamento."""
    rules = _l(decision.get("regras_disparadas"))
    illegible = _l(validation.get("campos_ilegiveis"))
    flags = []
    if "R001" in rules:
        flags.append("alerta_critico")
    if any("dosagem" in str(f) for f in illegible):
        flags.append("dosagem_ilegivel")
    if any("dosagem" not in str(f) for f in illegible):
        flags.append("campo_ilegivel")
    if validation.get("campos_ausentes"):
        flags.append("campo_em_falta")
    if validation.get("conflitos"):
        flags.append("campo_conflitante")
    if raw.get("status") == "falha":
        flags.append("falha_tecnica")
    if decision.get("regra_principal") == "R006":
        flags.append("sem_roteamento_automatico")
    if not flags and validation.get("integridade_documental") == "insuficiente":
        flags.append("integridade_insuficiente")
    flags += [str(a["codigo"]) for a in _l(decision.get("alertas")) if isinstance(a, dict) and a.get("codigo")]
    if confidence is not None and confidence < LOW_CONFIDENCE_THRESHOLD:
        flags.append("baixa_confianca")
    return list(dict.fromkeys(flags))


def _medications(data: dict) -> list[dict]:
    return [
        {"name": m.get("nome") or "—",
         "dosage": _field_value(m.get("dosagem_texto"), m.get("dosagem_status"))}
        for m in map(_d, _l(data.get("medicamentos")))
    ]


def _exams(data: dict) -> list[dict]:
    """Exame do laudo, resultados laboratoriais e procedimentos solicitados, numa só lista."""
    exam = _d(data.get("exame"))
    rows = []
    if exam.get("nome"):
        rows.append({"name": exam["nome"], "notes": exam.get("conclusao") or exam.get("achados") or ""})
    for r in map(_d, _l(exam.get("resultados"))):
        value = " ".join(str(v) for v in (r.get("valor_texto"), r.get("unidade")) if v)
        rows.append({"name": r.get("parametro") or "—", "notes": value})
    rows += [{"name": str(p), "notes": "procedimento solicitado"} for p in _l(data.get("procedimentos"))]
    return rows


def _rules(decision: dict) -> list[dict]:
    """Regras disparadas, com o principal em primeiro lugar e o texto do catálogo."""
    fired = _l(decision.get("regras_disparadas"))
    main = decision.get("regra_principal")
    ordered = ([main] if main in fired else []) + [r for r in fired if r != main]
    return [{"id": rid, "main": rid == main, **RULES.get(rid, {"name": rid})} for rid in ordered]


def _received_at(raw: dict) -> str | None:
    """Hora de receção: o primeiro evento com data (ou o campo da extensão da UI)."""
    for event in map(_d, _l(raw.get("eventos"))):
        if event.get("timestamp_utc"):
            return event["timestamp_utc"]
    return raw.get("recebido_em")


def normalize_document(raw: dict | None) -> dict:
    """Converte um `ResultadoTriagem` (v0.1) num dicionário com estrutura garantida."""
    raw = raw or {}
    entry = _d(raw.get("entrada"))
    classification = _d(raw.get("classificacao"))
    data = _d(raw.get("dados_extraidos"))
    patient = _d(data.get("paciente"))
    professional = _d(data.get("profissional"))
    validation = _d(raw.get("validacao"))
    decision = _d(raw.get("decisao_roteamento"))
    rag = _d(raw.get("rag"))
    review = raw.get("revisao_humana")  # extensão aditiva da v0.1 (null até a decisão)

    quality = _d(classification.get("indicador_qualidade"))
    confidence = quality.get("valor")
    try:
        confidence = float(confidence) if confidence is not None else None
    except (TypeError, ValueError):
        confidence = None

    status = _STATUS_FROM_CONTRACT.get(raw.get("status"), raw.get("status") or "received")
    if isinstance(review, dict) and review.get("acao") in REVIEW_STATUSES:
        status = REVIEW_STATUSES[review["acao"]]

    doc_type = classification.get("tipo_documento")
    destination = decision.get("destino_principal")
    channel = entry.get("canal_origem")
    filename = entry.get("nome_arquivo") or ("(texto livre)" if entry.get("tipo_entrada") == "texto" else "—")

    return {
        "id": str(raw.get("documento_id") or "—"),
        "filename": filename,
        "received_at": _received_at(raw),
        "status": status,
        "priority": _PRIORITY_FROM_CONTRACT.get(classification.get("nivel_prioridade_documental"), "ambiguidade"),
        "destination": DESTINATIONS.get(destination, destination or "—"),
        "destination_id": destination,
        "requires_review": bool(decision.get("requer_revisao_humana")),
        "confidence": confidence,
        "flags": _flags(raw, validation, decision, confidence),
        "extracted": {
            "patient_name": _field_value(patient.get("nome"), patient.get("nome_status")),
            "patient_name_status": patient.get("nome_status"),
            "patient_id": patient.get("identificador") or "—",
            "patient_age": patient.get("idade"),
            "doctor_name": professional.get("nome") or "—",
            "doctor_license": professional.get("crm_texto") or "—",
            "document_type": DOCUMENT_TYPES.get(doc_type, doc_type or "—"),
            "document_type_id": doc_type,
            "specialty": classification.get("especialidade_texto"),
            # Só preenchidos quando escritos no documento (o CID nunca é sugerido pela IA).
            "references": {
                "Emissão": data.get("data_emissao"),
                "Solicitação": data.get("data_solicitacao"),
                "Admissão": data.get("data_admissao"),
                "Alta": data.get("data_alta"),
                "Afastamento": data.get("afastamento_periodo"),
                "Guia": data.get("identificacao_guia"),
                "CID documentado": data.get("cid_documentado"),
            },
            "document_date": (data.get("data_emissao") or data.get("data_solicitacao")
                              or data.get("data_alta") or "—"),
            "medications": _medications(data),
            "exams": _exams(data),
            "notes": data.get("resumo") or data.get("descricao_documento") or data.get("afastamento_periodo") or "",
        },
        "validation": {
            "integrity": validation.get("integridade_documental") or "—",
            "missing": _l(validation.get("campos_ausentes")),
            "illegible": _l(validation.get("campos_ilegiveis")),
            "conflicts": _l(validation.get("conflitos")),
            "notes": _l(validation.get("observacoes")),
        },
        "evidence": {
            "document": [
                {"field": e.get("campo", "—"), "excerpt": e.get("trecho_documento", ""), "page": e.get("pagina")}
                for e in map(_d, _l(raw.get("evidencias")))
            ],
            "rag_status": rag.get("status") or "nao_consultado",
            "sources": [
                {"title": f.get("titulo") or f.get("fonte_id") or "Fonte", "excerpt": f.get("trecho_relevante"),
                 "ref": f.get("url") or f.get("fonte_id"), "version": f.get("versao"), "score": None}
                for f in map(_d, _l(rag.get("fontes")))
            ],
            "rules_fired": _rules(decision),
            "justification": decision.get("justificativa") or "",
        },
        "alerts": [
            {"code": str(a.get("codigo") or "—"), "message": a.get("mensagem") or ""}
            for a in map(_d, _l(decision.get("alertas")))
        ],
        "channel": channel or "—",
        "trace": {
            "input_type": entry.get("tipo_entrada") or "—",
            "sha256": entry.get("sha256"),
            "contract_version": raw.get("contrato_versao") or "—",
            "rules_version": decision.get("versao_regras") or "—",
            "quality_method": quality.get("metodo") or "nao_calculado",
            "quality_criteria": _l(quality.get("criterios")),
            "storage": _d(raw.get("armazenamento_oci")),
            "events": [
                {"code": e.get("codigo") or "—", "description": e.get("descricao") or "",
                 "timestamp": e.get("timestamp_utc")}
                for e in map(_d, _l(raw.get("eventos")))
            ],
        },
        "review": {
            "action": review.get("acao"), "reviewer": review.get("revisor"),
            "comment": review.get("comentario"), "reviewed_at": review.get("revisado_em"),
        } if isinstance(review, dict) else None,
        "raw": raw,
    }


def compute_stats(documents: list[dict]) -> dict:
    """Calcula as métricas do dashboard a partir da lista de documentos (crus, v0.1)."""
    docs = [normalize_document(d) for d in documents]
    by_status: dict[str, int] = {}
    by_priority: dict[str, int] = {}
    by_destination: dict[str, int] = {}
    for d in docs:
        by_status[d["status"]] = by_status.get(d["status"], 0) + 1
        by_priority[d["priority"]] = by_priority.get(d["priority"], 0) + 1
        by_destination[d["destination"]] = by_destination.get(d["destination"], 0) + 1

    return {
        "total": len(docs),
        "processed": sum(by_status.get(s, 0) for s in DONE_STATUSES),
        "urgent": by_priority.get("urgente", 0),
        "pending_review": by_status.get("pending_review", 0),
        "by_status": by_status,
        "by_priority": by_priority,
        "by_destination": by_destination,
    }
