import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import discord

from src.admins import admin_ids, is_admin
from src.cogs.admin import ADMIN_PAGES, AdminCog, AdminPanel, admin_page
from src.cogs.league import LeagueCog

# ID fictício de um admin extra, configurado por variável de ambiente como no bot real.
EXTRA_ADMIN = 111111111111111111
os.environ["MEMI_ADMIN_IDS"] = str(EXTRA_ADMIN)


def context(user_id, manage_guild=False):
    return SimpleNamespace(
        author=SimpleNamespace(
            id=user_id, guild_permissions=SimpleNamespace(manage_guild=manage_guild)
        ),
        guild=SimpleNamespace(id=555),
        reply=AsyncMock(),
    )


class AdminTests(unittest.TestCase):
    def test_owner_and_extra_admin_are_admins_and_env_adds_more(self):
        with patch.dict("os.environ", {"MEMI_ADMIN_IDS": f"{EXTRA_ADMIN}, 111, 222;abc"}):
            ids = admin_ids()
        self.assertTrue({EXTRA_ADMIN, 111, 222} <= ids)
        self.assertNotIn(0, ids)  # sem MEMI_OWNER_ID, ninguém vira dono por acaso
        self.assertTrue(is_admin(EXTRA_ADMIN))
        self.assertTrue(is_admin(str(EXTRA_ADMIN)))
        self.assertFalse(is_admin(123))
        self.assertFalse(is_admin(None))

    def test_admin_commands_accept_extra_admin_and_refuse_others(self):
        cog = AdminCog(SimpleNamespace(database_path=":memory:"))
        self.assertTrue(asyncio.run(cog.cog_check(context(EXTRA_ADMIN))))
        stranger = context(123)
        self.assertFalse(asyncio.run(cog.cog_check(stranger)))
        stranger.reply.assert_awaited()

    def test_championship_admin_is_bot_admin_or_server_manager(self):
        cog = LeagueCog(SimpleNamespace(database_path=":memory:"))
        self.assertTrue(cog._is_admin(context(EXTRA_ADMIN)))
        self.assertTrue(cog._is_admin(context(123, manage_guild=True)))
        self.assertFalse(cog._is_admin(context(123)))


class AdminPanelTests(unittest.IsolatedAsyncioTestCase):
    def test_every_page_fits_in_discord(self):
        for key in ADMIN_PAGES:
            embed = admin_page(key)
            self.assertLessEqual(len(embed.fields), 25, key)
            self.assertLessEqual(len(embed), 6000, key)
            for field in embed.fields:
                self.assertLessEqual(len(field.name), 256)
                self.assertLessEqual(len(field.value), 1024)
        commands = " ".join(field.name for key in ADMIN_PAGES for field in admin_page(key).fields)
        for name in ("jogador", "adiantar", "pausar", "backup", "reiniciar", "duplicados"):
            self.assertIn(name, commands)

    async def test_buttons_switch_pages_only_for_whoever_opened(self):
        owner = SimpleNamespace(id=EXTRA_ADMIN)
        view = AdminPanel(owner)
        self.assertEqual(len(view.children), len(ADMIN_PAGES))
        button = next(item for item in view.children if item.custom_id == "admin:campeonato")
        interaction = SimpleNamespace(
            user=SimpleNamespace(id=EXTRA_ADMIN),
            response=SimpleNamespace(edit_message=AsyncMock(), send_message=AsyncMock()),
        )
        await button.callback(interaction)
        embed = interaction.response.edit_message.await_args.kwargs["embed"]
        self.assertIn("Campeonato", embed.title)
        self.assertEqual(button.style, discord.ButtonStyle.primary)
        stranger = SimpleNamespace(
            user=SimpleNamespace(id=1),
            response=SimpleNamespace(edit_message=AsyncMock(), send_message=AsyncMock()),
        )
        await button.callback(stranger)
        stranger.response.edit_message.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
