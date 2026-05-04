from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from typing import Any

from database import connect, get_setting, now_text, rows_to_dicts


SPAM_SIGNALS = {
    "aproveite",
    "clique",
    "comprar agora",
    "desconto imperdivel",
    "emprestimo",
    "gratis",
    "imperdivel",
    "oferta relampago",
    "promocao",
    "renda extra",
    "urgente",
}


def _parse_datetime(value: object) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _normalize_text(value: str) -> str:
    replacements = str.maketrans("áàâãéêíóôõúç", "aaaaeeiooouc")
    return re.sub(r"\s+", " ", value.lower().translate(replacements)).strip()


def risk_level(score: int) -> str:
    if score >= 75:
        return "crítico"
    if score >= 50:
        return "alto"
    if score >= 25:
        return "moderado"
    return "baixo"


def assess_campaign(campaign_id: int) -> dict[str, Any]:
    with connect() as conn:
        campaign = conn.execute("SELECT * FROM campaigns WHERE id = ?", (campaign_id,)).fetchone()
        if not campaign:
            raise ValueError("Campanha não encontrada.")

        contacts = conn.execute(
            """
            SELECT contacts.*
            FROM campaign_contacts
            JOIN contacts ON contacts.id = campaign_contacts.contact_id
            WHERE campaign_contacts.campaign_id = ?
            """,
            (campaign_id,),
        ).fetchall()

        recent = conn.execute(
            """
            SELECT status, COUNT(*) AS total
            FROM message_logs
            WHERE created_at >= ?
            GROUP BY status
            """,
            ((datetime.now() - timedelta(days=30)).isoformat(timespec="seconds"),),
        ).fetchall()
        variant_rows = conn.execute(
            """
            SELECT body
            FROM campaign_variants
            WHERE campaign_id = ?
            """,
            (campaign_id,),
        ).fetchall()

    campaign_data = dict(campaign)
    contact_data = rows_to_dicts(contacts)
    total = len(contact_data)
    if total == 0:
        return _build_result(campaign_id, 100, ["Campanha sem contatos."], campaign_data, {})

    no_opt_in = sum(1 for item in contact_data if not int(item.get("opt_in") or 0))
    opted_out = sum(1 for item in contact_data if item.get("opt_out_at"))
    blacklisted = sum(1 for item in contact_data if int(item.get("blacklisted") or 0))
    missing_proof = sum(
        1
        for item in contact_data
        if int(item.get("opt_in") or 0) and (not item.get("opt_in_source") or not item.get("opt_in_at"))
    )

    now = datetime.now()
    outside_24h = 0
    for item in contact_data:
        inbound_at = _parse_datetime(item.get("last_inbound_at"))
        if not inbound_at or now - inbound_at > timedelta(hours=24):
            outside_24h += 1

    score = 5
    notes: list[str] = []

    unauthorized_rate = (no_opt_in + opted_out + blacklisted) / total
    if unauthorized_rate:
        score += round(55 * min(unauthorized_rate, 1))
        notes.append(f"{no_opt_in + opted_out + blacklisted} contato(s) sem autorização, com opt-out ou blacklist.")

    proof_rate = missing_proof / total
    if proof_rate:
        score += round(25 * min(proof_rate, 1))
        notes.append(f"{missing_proof} contato(s) com opt-in sem prova completa de origem/data.")

    category = str(campaign_data.get("message_category") or "marketing")
    template_name = str(campaign_data.get("template_name") or "").strip()
    if category != "service" and not template_name:
        score += 35
        notes.append("Campanha iniciada pela empresa sem template aprovado.")
    if category == "service" and outside_24h:
        score += round(45 * min(outside_24h / total, 1))
        notes.append(f"{outside_24h} contato(s) fora da janela de atendimento de 24h.")

    daily_limit = max(int(float(get_setting("daily_send_limit", "500") or 500)), 1)
    if total > daily_limit:
        score += 30
        notes.append("Quantidade de contatos acima do limite diário configurado.")
    elif total > daily_limit * 0.8:
        score += 15
        notes.append("Quantidade de contatos perto do limite diário configurado.")

    interval = float(get_setting("send_interval_seconds", "2") or 2)
    if interval < 1:
        score += 20
        notes.append("Intervalo de envio muito curto.")
    elif interval < 2:
        score += 10
        notes.append("Intervalo de envio abaixo do recomendado para aquecimento.")

    message = _normalize_text(str(campaign_data.get("message") or ""))
    spam_hits = sorted(signal for signal in SPAM_SIGNALS if signal in message)
    if spam_hits:
        score += min(20, 5 * len(spam_hits))
        notes.append("Texto contém sinais comerciais agressivos: " + ", ".join(spam_hits[:4]) + ".")

    configured = bool(
        get_setting("whatsapp_phone_number_id", "")
        and (get_setting("whatsapp_token_protected", "") or os.environ.get("MEZZOLD_WHATSAPP_TOKEN", ""))
    )
    dry_run = get_setting("whatsapp_dry_run", "1") == "1"
    delivery_mode = get_setting("delivery_mode", "official_api")
    if delivery_mode == "manual_assisted":
        score += 30
        notes.append("Modo sem API oficial: apenas manual assistido por link wa.me, sem envio automático.")
    elif delivery_mode != "official_api":
        score += 45
        notes.append("Modo de envio não reconhecido como Cloud API oficial.")

    if delivery_mode == "official_api" and not dry_run and not configured:
        score += 50
        notes.append("Envio real sem configuração oficial completa da Cloud API.")

    recent_counts = {str(row["status"]): int(row["total"]) for row in recent}
    recent_total = sum(recent_counts.values())
    if recent_total >= 20:
        failed = recent_counts.get("falhou", 0)
        blocked = recent_counts.get("bloqueado", 0) + recent_counts.get("sem_autorizacao", 0)
        quality_rate = (failed + blocked) / recent_total
        if quality_rate > 0.15:
            score += 20
            notes.append("Histórico recente tem taxa alta de falhas/bloqueios.")
        elif quality_rate > 0.05:
            score += 10
            notes.append("Histórico recente tem falhas suficientes para monitorar qualidade.")

    smart_enabled = get_setting("smart_send_enabled", "0") == "1"
    variant_count = len({str(row["body"]).strip() for row in variant_rows if str(row["body"]).strip()})
    if smart_enabled and variant_count < 3:
        score += 35
        notes.append("Disparo inteligente ativo exige pelo menos 3 mensagens diferentes.")

    if not notes:
        notes.append("Campanha alinhada aos controles atuais de opt-in, template e volume.")

    details = {
        "total_contacts": total,
        "no_opt_in": no_opt_in,
        "opted_out": opted_out,
        "blacklisted": blacklisted,
        "missing_proof": missing_proof,
        "outside_24h": outside_24h,
        "daily_limit": daily_limit,
        "interval": interval,
        "template_required": category != "service",
        "has_template": bool(template_name),
        "delivery_mode": delivery_mode,
        "dry_run": dry_run,
        "smart_send_enabled": smart_enabled,
        "variant_count": variant_count,
    }
    return _build_result(campaign_id, min(score, 100), notes, campaign_data, details)


def _build_result(
    campaign_id: int,
    score: int,
    notes: list[str],
    campaign: dict[str, Any],
    details: dict[str, Any],
) -> dict[str, Any]:
    return {
        "campaign_id": campaign_id,
        "campaign_name": campaign.get("name", ""),
        "score": int(max(0, min(score, 100))),
        "level": risk_level(int(max(0, min(score, 100)))),
        "notes": notes,
        "details": details,
        "updated_at": now_text(),
    }


def refresh_campaign_risk(campaign_id: int) -> dict[str, Any]:
    result = assess_campaign(campaign_id)
    with connect() as conn:
        conn.execute(
            """
            UPDATE campaigns
            SET risk_score = ?, risk_level = ?, risk_notes = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                result["score"],
                result["level"],
                "\n".join(result["notes"]),
                result["updated_at"],
                campaign_id,
            ),
        )
    return result


def list_campaign_risks() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT id
            FROM campaigns
            ORDER BY created_at DESC
            """
        ).fetchall()

    results = []
    for row in rows:
        results.append(refresh_campaign_risk(int(row["id"])))
    return results
