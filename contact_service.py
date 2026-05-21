from __future__ import annotations

from typing import Any

import contacts


ContactError = contacts.ContactError
ImportSummary = contacts.ImportSummary
LeadMergeSummary = contacts.LeadMergeSummary


def normalize_phone(phone: str) -> str:
    return contacts.normalize_phone(phone)


def is_valid_phone(phone: str) -> bool:
    return contacts.is_valid_phone(phone)


def list_contacts(
    search: str = "",
    group_name: str = "",
    only_authorized: bool = False,
) -> list[dict[str, object]]:
    items = contacts.list_contacts(search=search, group_name=group_name)
    if not only_authorized:
        return items
    return [item for item in items if item.get("opt_in") and not item.get("blacklisted")]


def search_contacts(term: str, group_name: str = "") -> list[dict[str, object]]:
    return list_contacts(search=term, group_name=group_name)


def list_contacts_by_folder(folder_name: str, search: str = "") -> list[dict[str, object]]:
    return contacts.list_contacts_by_folder(folder_name, search=search)


def export_contacts_csv(path_text: str, group_name: str = "", search: str = "") -> int:
    return contacts.export_contacts_csv(path_text, group_name=group_name, search=search)


def list_used_contacts(folder_name: str = "", search: str = "", limit: int = 1000) -> list[dict[str, object]]:
    return contacts.list_used_contacts(folder_name=folder_name, search=search, limit=limit)


def get_contact(contact_id: int) -> dict[str, object] | None:
    return contacts.get_contact(contact_id)


def list_groups() -> list[str]:
    return contacts.list_groups()


def create_folder(name: str) -> int:
    return contacts.create_folder(name)


def list_folders() -> list[dict[str, object]]:
    return contacts.list_folders()


def rename_folder(folder_id: int, new_name: str) -> None:
    contacts.rename_folder(folder_id, new_name)


def delete_folder(folder_id: int) -> int:
    return contacts.delete_folder(folder_id)


def add_contact_to_folder(contact_id: int, folder_name: str) -> None:
    contacts.add_contact_to_folder(contact_id, folder_name)


def set_contact_primary_folder(contact_id: int, folder_name: str) -> None:
    contacts.set_contact_primary_folder(contact_id, folder_name)


def create_contact(
    name: str,
    phone: str,
    email: str = "",
    group_name: str = "",
    opt_in: int = 1,
    opt_in_source: str = "manual",
    opt_in_category: str = "marketing",
    opt_in_at: str = "",
    consent_notes: str = "",
    notes: str = "",
    blacklisted: bool = False,
) -> int:
    contact_id = contacts.add_contact(
        name,
        phone,
        email,
        group_name,
        opt_in,
        opt_in_source,
        opt_in_category,
        opt_in_at,
        consent_notes,
        notes,
    )
    if blacklisted:
        contacts.set_blacklist(contact_id, True)
    return contact_id


def add_contact(
    name: str,
    phone: str,
    email: str = "",
    group_name: str = "",
    opt_in: int = 1,
    opt_in_source: str = "manual",
    opt_in_category: str = "marketing",
    opt_in_at: str = "",
    consent_notes: str = "",
    notes: str = "",
) -> int:
    return create_contact(
        name,
        phone,
        email,
        group_name,
        opt_in,
        opt_in_source,
        opt_in_category,
        opt_in_at,
        consent_notes,
        notes,
    )


def upsert_contact(
    name: str,
    phone: str,
    email: str = "",
    group_name: str = "",
    opt_in: int = 1,
    opt_in_source: str = "",
    opt_in_category: str = "marketing",
    opt_in_at: str = "",
    consent_notes: str = "",
    notes: str = "",
) -> tuple[int, bool]:
    return contacts.upsert_contact(
        name,
        phone,
        email,
        group_name,
        opt_in,
        opt_in_source,
        opt_in_category,
        opt_in_at,
        consent_notes,
        notes,
    )


def update_contact(contact_id: int, **fields: object) -> None:
    contacts.update_contact(contact_id, **fields)


def save_contact(contact_id: int = 0, **fields: object) -> int:
    if contact_id:
        contacts.update_contact(contact_id, **fields)
        return contact_id

    blacklisted = bool(fields.pop("blacklisted", False))
    return create_contact(
        str(fields.get("name") or ""),
        str(fields.get("phone") or ""),
        str(fields.get("email") or ""),
        str(fields.get("group_name") or ""),
        int(bool(fields.get("opt_in", True))),
        str(fields.get("opt_in_source") or "manual"),
        str(fields.get("opt_in_category") or "marketing"),
        str(fields.get("opt_in_at") or ""),
        str(fields.get("consent_notes") or ""),
        str(fields.get("notes") or ""),
        blacklisted=blacklisted,
    )


def delete_contact(contact_id: int) -> None:
    contacts.delete_contact(contact_id)


def set_blacklist(contact_id: int, blocked: bool) -> None:
    contacts.set_blacklist(contact_id, blocked)


def mark_opt_out(contact_id: int, reason: str = "") -> None:
    contacts.mark_opt_out(contact_id, reason)


def register_inbound_message(phone: str, opted_in: bool = True, source: str = "whatsapp") -> None:
    contacts.register_inbound_message(phone, opted_in=opted_in, source=source)


def import_contacts(path_text: str, folder_name: str = "") -> ImportSummary:
    return contacts.import_contacts(path_text, folder_name=folder_name)


def extract_leads_from_text(text: str) -> list[dict[str, str]]:
    return contacts.extract_leads_from_text(text)


def merge_lead_results(
    current: list[dict[str, object]],
    incoming: list[dict[str, object]],
) -> tuple[list[dict[str, str]], LeadMergeSummary]:
    return contacts.merge_lead_results(current, incoming)


def import_leads(leads: list[dict[str, object]], folder_name: str = "") -> ImportSummary:
    return contacts.import_leads(leads, folder_name=folder_name)


def list_used_phones(limit: int = 1000) -> list[dict[str, Any]]:
    from campaigns import list_sent_numbers

    return list_sent_numbers(limit=limit)


def mark_contact_as_used(
    contact_id: int,
    status: str = "enviado",
    campaign_id: int | None = None,
    message_body: str = "",
    provider_message_id: str = "",
    action_url: str = "",
) -> None:
    contact = get_contact(contact_id)
    if not contact:
        raise ContactError("Contato não encontrado.")

    from campaigns import log_message

    log_message(
        campaign_id,
        contact_id,
        str(contact.get("phone") or ""),
        str(contact.get("name") or ""),
        status,
        provider_message_id=provider_message_id,
        action_url=action_url,
        message_body=message_body,
    )
