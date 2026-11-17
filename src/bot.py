"""Inicialização independente do bot Discord FUT.AE."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv

from src.admin_tools import backup_if_due
from src.db import (
    DATABASE_PATH,
    ROOT,
    initialize_database,
    keep_database_open,
    normalize_player_name,
)

LOGGER = logging.getLogger("memi")
PREFIX = ".."
SLOW_COMMAND_SECONDS = 1.0
EVENT_LOOP_STALL_SECONDS = 1.0
BACKUP_CHECK_SECONDS = 3600
INTERACTION_ERROR_TEXT = "Algo deu errado com essa ação. Tente de novo em instantes."


async def report_interaction_error(interaction: discord.Interaction, error: Exception) -> None:
    """Registra a falha e avisa só quem clicou, sem deixar a interação sem resposta."""
    LOGGER.error("Falha numa interação", exc_info=(type(error), error, error.__traceback__))
    try:
        if interaction.response.is_done():
            await interaction.followup.send(INTERACTION_ERROR_TEXT, ephemeral=True)
        else:
            await interaction.response.send_message(INTERACTION_ERROR_TEXT, ephemeral=True)
    except discord.HTTPException:
        LOGGER.warning("Não consegui avisar sobre a falha: a interação já expirou.")


async def _view_on_error(self, interaction, error, item) -> None:
    await report_interaction_error(interaction, error)


async def _modal_on_error(self, interaction, error) -> None:
    await report_interaction_error(interaction, error)


discord.ui.View.on_error = _view_on_error
discord.ui.Modal.on_error = _modal_on_error


def command_prefix(bot: commands.Bot, message: discord.Message) -> list[str]:
    """Aceita `..` em qualquer combinação de maiúsculas."""
    prefixes = commands.when_mentioned(bot, message)
    start = (message.content or "")[: len(PREFIX)]
    if start.casefold() == PREFIX:
        prefixes.append(start)
    return prefixes


class MemiBot(commands.Bot):
    def __init__(self, database_path: str | Path = DATABASE_PATH):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(
            command_prefix=command_prefix,
            case_insensitive=True,
            strip_after_prefix=True,
            help_command=None,
            intents=intents,
        )
        self.database_path = Path(database_path)
        # Só o bot de verdade (`main`) faz backup e vigia travamentos; os testes não.
        self.maintenance_enabled = False
        self._background_tasks: list[asyncio.Task] = []
        self._offline_since: float | None = None
        self.tree.on_error = report_interaction_error
        self.before_invoke(self._mark_command_start)
        self.after_invoke(self._log_slow_command)

    async def _mark_command_start(self, context: commands.Context) -> None:
        context.started_at = time.perf_counter()

    async def _log_slow_command(self, context: commands.Context) -> None:
        elapsed = time.perf_counter() - getattr(context, "started_at", time.perf_counter())
        if elapsed >= SLOW_COMMAND_SECONDS:
            LOGGER.warning("Comando lento: %s levou %.1f s", context.command, elapsed)

    async def _watch_event_loop(self) -> None:
        """Avisa no log quando algo segura o bot inteiro, inclusive em botões e menus."""
        while True:
            started = time.perf_counter()
            await asyncio.sleep(1)
            stalled = time.perf_counter() - started - 1
            if stalled >= EVENT_LOOP_STALL_SECONDS:
                LOGGER.warning("Bot travado por %.1f s", stalled)

    async def _backup_forever(self) -> None:
        while True:
            try:
                created = await asyncio.to_thread(backup_if_due, self.database_path)
                if created:
                    LOGGER.info("Backup do banco criado: %s", created.name)
            except Exception:
                LOGGER.exception("Falha ao criar o backup do banco.")
            await asyncio.sleep(BACKUP_CHECK_SECONDS)

    async def on_disconnect(self) -> None:
        if self._offline_since is None:
            self._offline_since = time.perf_counter()
            LOGGER.warning("Conexão com o Discord caiu.")

    def _log_reconnected(self) -> None:
        if self._offline_since is not None:
            LOGGER.warning(
                "Conexão com o Discord voltou depois de %.1f s.",
                time.perf_counter() - self._offline_since,
            )
            self._offline_since = None

    async def on_resumed(self) -> None:
        self._log_reconnected()

    async def on_ready(self) -> None:
        self._log_reconnected()
        # Registra os /comandos (/wish, /scout…) no Discord uma vez por execução.
        if not getattr(self, "_slash_synced", False):
            self._slash_synced = True
            try:
                synced = await self.tree.sync()
                LOGGER.info("Comandos de barra registrados: %s", len(synced))
            except discord.HTTPException:
                LOGGER.exception("Não consegui registrar os comandos de barra.")
        LOGGER.info(
            "Bot pronto: %s (%s); message_content=%s; comandos=%s",
            self.user,
            self.user.id if self.user else "desconhecido",
            self.intents.message_content,
            len(self.commands),
        )
        await self.change_presence(activity=discord.Game(name="..ajuda"))

    async def get_context(self, origin, *, cls=commands.Context):
        """Aceita o comando com ou sem acento (..tática = ..tatica)."""
        context = await super().get_context(origin, cls=cls)
        if context.command is None and context.invoked_with:
            context.command = self.all_commands.get(
                normalize_player_name(context.invoked_with).replace(" ", "")
            )
        return context

    async def setup_hook(self) -> None:
        started = time.perf_counter()
        initialize_database(self.database_path)
        schema_done = time.perf_counter()
        await self.load_extension("src.cogs.game")
        await self.load_extension("src.cogs.economy")
        await self.load_extension("src.cogs.rolls")
        await self.load_extension("src.cogs.trades")
        await self.load_extension("src.cogs.team")
        await self.load_extension("src.cogs.matches")
        await self.load_extension("src.cogs.league")
        await self.load_extension("src.cogs.club")
        await self.load_extension("src.cogs.admin")
        await self.load_extension("src.cogs.casino")
        await self.load_extension("src.cogs.groups")
        extensions_done = time.perf_counter()
        from src.encyclopedia import prepare_game_data

        report = prepare_game_data(self.database_path)
        LOGGER.info("Extensões do MEMI carregadas; dados sincronizados: %s", report)
        LOGGER.info(
            "Inicialização: banco %.1f s, extensões %.1f s, dados %.1f s.",
            schema_done - started,
            extensions_done - schema_done,
            time.perf_counter() - extensions_done,
        )
        if self.maintenance_enabled:
            self._background_tasks = [
                asyncio.create_task(self._watch_event_loop()),
                asyncio.create_task(self._backup_forever()),
            ]

    async def on_command_error(
        self,
        context: commands.Context,
        error: commands.CommandError,
    ) -> None:
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.MissingRequiredArgument):
            command_name = context.command.name if context.command else "comando"
            await context.reply(
                f"Falta um argumento. Use `..{command_name} {error.param.name}`.",
                mention_author=False,
            )
            return
        if isinstance(error, commands.BadArgument):
            await context.reply(
                "Não consegui entender esse argumento. Confira `..ajuda`.",
                mention_author=False,
            )
            return
        LOGGER.error(
            "Falha no comando %s",
            context.command.qualified_name if context.command else "desconhecido",
            exc_info=(type(error), error, error.__traceback__),
        )
        try:
            await context.reply(
                "Ocorreu um erro ao executar o comando. Tente novamente mais tarde.",
                mention_author=False,
            )
        except discord.HTTPException:
            LOGGER.warning("Não consegui avisar sobre a falha no canal.")


def create_bot(database_path: str | Path = DATABASE_PATH) -> MemiBot:
    """Cria uma instância pronta para conectar ao Discord."""
    return MemiBot(database_path)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    load_dotenv(ROOT / ".env")
    token = os.getenv("DISCORD_BOT_TOKEN")
    token_file = ROOT / "token.txt"
    if not token and token_file.is_file():
        token = token_file.read_text(encoding="utf-8").strip()
    if not token:
        raise SystemExit(
            "Configure DISCORD_BOT_TOKEN no arquivo .env ou coloque o token FUT.AE em token.txt."
        )
    bot = create_bot()
    bot.maintenance_enabled = True
    try:
        with keep_database_open(bot.database_path):
            bot.run(token, log_handler=None)
    except discord.LoginFailure as error:
        LOGGER.error("O Discord recusou o token configurado.")
        raise SystemExit(1) from error
    except discord.PrivilegedIntentsRequired as error:
        LOGGER.error("Ative Message Content Intent na página de configuração do bot Discord.")
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
