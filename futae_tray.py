"""FUT.AE na bandeja do Windows.

Use este arquivo para iniciar o FUT.AE sem manter um terminal aberto:

    python futae_tray.py
    python futae_tray.py --instalar
    python futae_tray.py --desinstalar

O token é lido de DISCORD_BOT_TOKEN no .env ou de token.txt na pasta do bot.
Nenhum token é escrito em logs.
"""

import asyncio
import concurrent.futures
import logging
import os
import socket
import subprocess
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

PASTA = Path(__file__).resolve().parent
os.chdir(PASTA)
sys.path.insert(0, str(PASTA))

ARQ_LOG = PASTA / "futae_bot.log"
ARQ_LOG_ERROS = PASTA / "futae_bot_erros.log"
ARQ_LOGO = PASTA / "assets" / "logo-futae.jpg"
NOME_ATALHO = "FUTAEBOT.vbs"
PORTA_UNICA = 47655


def pasta_inicializacao() -> Path:
    return Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Startup"


def instalar() -> None:
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.exists():
        pythonw = Path(sys.executable)
    linha = (
        f'CreateObject("Wscript.Shell").Run '
        f'"""{pythonw}"" ""{Path(__file__).resolve()}""", 0, False'
    )
    destino = pasta_inicializacao() / NOME_ATALHO
    destino.write_text(linha + "\r\n", encoding="utf-16")
    print(f"Instalado: {destino}")


def desinstalar() -> None:
    destino = pasta_inicializacao() / NOME_ATALHO
    if destino.exists():
        destino.unlink()
        print("Inicialização automática removida.")
    else:
        print("A inicialização automática não estava instalada.")


if len(sys.argv) > 1:
    if sys.argv[1] in ("--instalar", "--install"):
        instalar()
    elif sys.argv[1] in ("--desinstalar", "--uninstall"):
        desinstalar()
    else:
        print(__doc__)
    raise SystemExit(0)


import pystray  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from src.bot import create_bot  # noqa: E402
from src.db import ROOT, keep_database_open  # noqa: E402

ARQ_LOG.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[RotatingFileHandler(ARQ_LOG, maxBytes=2_000_000, backupCount=3, encoding="utf-8")],
)
_handler_erros = RotatingFileHandler(
    ARQ_LOG_ERROS, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
)
_handler_erros.setLevel(logging.ERROR)
logging.getLogger().addHandler(_handler_erros)
LOGGER = logging.getLogger("futae.tray")

estado = {"loop": None, "bot": None, "icone": None, "reiniciar": False, "fechamento": None}


def criar_imagem():
    if ARQ_LOGO.is_file():
        imagem = Image.open(ARQ_LOGO).convert("RGBA")
        imagem.thumbnail((60, 60), Image.Resampling.LANCZOS)
        tela = Image.new("RGBA", (64, 64), (0, 0, 0, 255))
        tela.paste(imagem, ((64 - imagem.width) // 2, (64 - imagem.height) // 2))
        return tela
    imagem = Image.new("RGBA", (64, 64), (34, 160, 80, 255))
    desenho = ImageDraw.Draw(imagem)
    desenho.text((22, 23), "F", fill=(255, 255, 255, 255))
    return imagem


def ler_token() -> str:
    load_dotenv(ROOT / ".env")
    token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
    if token:
        return token
    caminho = ROOT / "token.txt"
    if caminho.is_file():
        linhas = [
            linha.strip()
            for linha in caminho.read_text(encoding="utf-8").splitlines()
            if linha.strip()
        ]
        return linhas[0] if linhas else ""
    return ""


def rodar_bot() -> None:
    token = ler_token()
    if not token:
        LOGGER.error("Falta o token do FUT.AE em .env ou token.txt.")
        if estado["icone"]:
            estado["icone"].title = "FUT.AE - token ausente"
        return

    bot = create_bot()
    bot.maintenance_enabled = True
    estado["bot"] = bot

    async def principal():
        estado["loop"] = asyncio.get_running_loop()
        try:
            await bot.start(token)
        except Exception:
            LOGGER.exception("O FUT.AE parou por erro.")

    with keep_database_open(bot.database_path):
        asyncio.run(principal())
    if estado["icone"]:
        estado["icone"].stop()


def abrir_pasta(icone, item) -> None:
    os.startfile(PASTA)


def abrir_log(icone, item) -> None:
    ARQ_LOG.touch(exist_ok=True)
    os.startfile(ARQ_LOG)


def abrir_log_erros(icone, item) -> None:
    ARQ_LOG_ERROS.touch(exist_ok=True)
    os.startfile(ARQ_LOG_ERROS)


def reiniciar(icone, item) -> None:
    loop = estado["loop"]
    bot = estado["bot"]
    if loop and loop.is_running() and bot:
        estado["fechamento"] = asyncio.run_coroutine_threadsafe(bot.close(), loop)
    estado["reiniciar"] = True
    icone.stop()


def sair(icone, item) -> None:
    loop = estado["loop"]
    bot = estado["bot"]
    if loop and loop.is_running() and bot:
        asyncio.run_coroutine_threadsafe(bot.close(), loop).result(timeout=10)
    icone.stop()


def main() -> None:
    trava = socket.socket()
    try:
        trava.bind(("127.0.0.1", PORTA_UNICA))
    except OSError:
        LOGGER.error("O FUT.AE já está em execução.")
        return

    menu = pystray.Menu(
        pystray.MenuItem("Abrir pasta do bot", abrir_pasta),
        pystray.MenuItem("Logs", abrir_log),
        pystray.MenuItem("Logs de erros", abrir_log_erros),
        pystray.MenuItem("Reiniciar", reiniciar),
        pystray.MenuItem("Desligar", sair),
    )
    estado["icone"] = pystray.Icon("futaebot", criar_imagem(), "FUT.AE", menu)
    threading.Thread(target=rodar_bot, daemon=True).start()
    estado["icone"].run()
    fechamento = estado["fechamento"]
    if fechamento is not None:
        try:
            fechamento.result(timeout=10)
        except (concurrent.futures.CancelledError, TimeoutError):
            LOGGER.warning("O Discord cancelou o fechamento durante o reinício; continuando.")
        except Exception:
            LOGGER.exception("Falha ao fechar o bot antes do reinício.")
    trava.close()
    if estado["reiniciar"]:
        subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve())],
            cwd=str(PASTA),
            close_fds=True,
        )


if __name__ == "__main__":
    main()
