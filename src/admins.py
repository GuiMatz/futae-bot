"""Quem administra o bot: o dono e os admins extras.

Uma lista só para tudo: os comandos `..admin` do FUT.AE, os comandos de dono do bot
principal (`..read`, `..reiniciar`...) e os de campeonato (`ativar`, `jogar`, `adiantar`,
que também aceitam quem tem Gerenciar servidor). Para incluir mais gente sem mexer no
código, use a variável `MEMI_ADMIN_IDS` com os IDs separados por vírgula.

Nenhum ID fica no código: o dono vem de `MEMI_OWNER_ID` e os admins extras de
`MEMI_ADMIN_IDS` (veja o `.env.example`).
"""

from __future__ import annotations

import os

# Sem dono definido por padrão (0 = ninguém). Configure `MEMI_OWNER_ID` no `.env`.
OWNER_ID = 0
EXTRA_ADMINS: set[int] = set()


def owner_id() -> int:
    value = os.getenv("MEMI_OWNER_ID", "").strip()
    return int(value) if value.isdigit() else OWNER_ID


def admin_ids() -> set[int]:
    extra = {
        int(value)
        for value in os.getenv("MEMI_ADMIN_IDS", "").replace(";", ",").split(",")
        if value.strip().isdigit()
    }
    return {owner_id(), OWNER_ID, *EXTRA_ADMINS, *extra} - {0}


def is_admin(user_id: int | str | None) -> bool:
    try:
        return int(user_id) in admin_ids()
    except (TypeError, ValueError):
        return False
