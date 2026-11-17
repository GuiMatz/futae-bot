"""Coleta, sem parar, as imagens de jogadores, clubes, estádios, ligas, técnicos e lendas.

Tudo vem do TheSportsDB, no ritmo da chave gratuita: **30 consultas por minuto**. Cada
imagem é salva com o ID do registro (`data/photos/<tipo>/<id>.<ext>`) e o caminho vai para
o banco. Itens sem imagem no TheSportsDB são anotados e não são buscados de novo.

    python -m scripts.coletar_imagens                      # coleta tudo
    python -m scripts.coletar_imagens --etapas jogadores   # só uma parte
    python -m scripts.coletar_imagens --api-key SUA_CHAVE  # sem usar o .env

Etapas, nesta ordem: ligas, times, estadios, tecnicos, lendas, jogadores, clubes.

Se o computador reiniciar ou o programa travar, rode o mesmo comando de novo: ele volta do
mesmo lugar. O progresso é gravado depois de cada item. Um vigia fica de olho no coletor e,
se ele passar 15 minutos sem fazer nada (ou se cair), reinicia sozinho de onde parou.
Para parar de vez, use Ctrl+C.

    --recomecar   apaga o ponto de retomada e começa do zero
    --retentar    busca de novo os itens que o TheSportsDB não tinha encontrado
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

from src.db import DATABASE_PATH, ROOT, connect, initialize_database
from src.photos import ENTITIES, PHOTO_ROOT, PhotoCollector
from src.sportsdb_images import MIN_INTERVAL, ImageHarvester, SportsDB

LOGGER = logging.getLogger("memi.coletor")

FREE_KEY = "123"
ETAPAS = ("ligas", "times", "estadios", "tecnicos", "lendas", "mascotes", "jogadores", "clubes")
# Etapa -> tabela de imagens que o `PhotoCollector` conhece (um item por consulta).
ETAPAS_POR_TABELA = {"jogadores": "players", "clubes": "clubs"}
STATE_PATH = ROOT / "data" / "coletor_imagens_estado.json"
BEAT_PATH = ROOT / "data" / "coletor_imagens.batimento"
LOTE = 30
TRAVOU_APOS = 15 * 60
MAX_TENTATIVAS_ITEM = 5
MAX_FALHAS_ETAPA = 8
PAUSA_MAXIMA = 300
PAUSA_BASE = 15
FALHAS_RECUPERAVEIS = (OSError, RuntimeError, sqlite3.Error, requests.RequestException)


def pausa_crescente(tentativa: int, base: int = PAUSA_BASE) -> int:
    """15 s, 30 s, 60 s... até 5 minutos."""
    return min(PAUSA_MAXIMA, base * (2 ** max(0, tentativa - 1)))


def formatar_duracao(segundos: float) -> str:
    minutos = int(round(segundos / 60))
    if minutos < 60:
        return f"{max(minutos, 1)} min"
    return f"{minutos // 60}h{minutos % 60:02d}"


# --- Batimento (sinal de que o coletor está vivo) ---------------------------------------


class Batimento:
    """Arquivo cuja data de modificação o coletor renova a cada consulta."""

    def __init__(self, path: Path = BEAT_PATH):
        self.path = Path(path)

    def tocar(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(str(time.time()), encoding="utf-8")
        except OSError:
            pass

    def limpar(self) -> None:
        self.path.unlink(missing_ok=True)

    def ultimo(self) -> float | None:
        try:
            return self.path.stat().st_mtime
        except OSError:
            return None


def dormir(
    segundos: float,
    batimento: Callable[[], None] | None = None,
    sleeper: Callable[[float], None] = time.sleep,
) -> None:
    """Espera em pedaços de até 10 s, avisando ao vigia que continua vivo."""
    restante = float(segundos)
    while restante > 0:
        pedaco = min(10.0, restante)
        sleeper(pedaco)
        restante -= pedaco
        if batimento:
            batimento()


# --- Sessão com limite de 30 consultas por minuto ---------------------------------------


class LimitedSession(requests.Session):
    """Espaça as consultas à API e repete sozinha quando o limite (HTTP 429) estoura.

    Só as consultas à API contam; baixar a imagem em si (outro endereço) não espera.
    """

    def __init__(
        self,
        interval: float = MIN_INTERVAL,
        beat: Callable[[], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        super().__init__()
        self.interval = interval
        self._beat = beat or (lambda: None)
        self._clock = clock
        self._sleeper = sleeper
        self._last_api: float | None = None

    def _send(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        return super().request(method, url, **kwargs)

    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response:  # type: ignore[override]
        is_api = "/api/v1/" in str(url)
        for attempt in range(4):
            if is_api and self._last_api is not None:
                wait = self.interval - (self._clock() - self._last_api)
                if wait > 0:
                    dormir(wait, self._beat, self._sleeper)
            if is_api:
                self._last_api = self._clock()
            self._beat()
            response = self._send(method, url, **kwargs)
            self._beat()
            if response.status_code != 429 or attempt == 3:
                return response
            LOGGER.info("Limite do TheSportsDB atingido; esperando 60 s.")
            response.close()
            dormir(60, self._beat, self._sleeper)
        return response


# --- Ponto de retomada -------------------------------------------------------------------


class Estado:
    """Etapas concluídas e último ID visto em cada tabela; salvo a cada item."""

    def __init__(self, path: Path = STATE_PATH):
        self.path = Path(path)
        self.concluidas: list[str] = []
        self.ultimo_id: dict[str, int] = {}

    @classmethod
    def carregar(cls, path: Path = STATE_PATH) -> Estado:
        estado = cls(path)
        if not estado.path.exists():
            return estado
        try:
            data = json.loads(estado.path.read_text(encoding="utf-8"))
            estado.concluidas = [str(item) for item in data.get("concluidas", [])]
            estado.ultimo_id = {str(k): int(v) for k, v in data.get("ultimo_id", {}).items()}
        except (OSError, ValueError, TypeError, AttributeError):
            backup = estado.path.with_suffix(".corrompido")
            estado.path.replace(backup)
            LOGGER.warning("Ponto de retomada ilegível; guardei em %s e comecei do zero.", backup)
            return cls(path)
        return estado

    def salvar(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {"concluidas": self.concluidas, "ultimo_id": self.ultimo_id},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)


# --- Etapas ------------------------------------------------------------------------------


def _agora() -> str:
    return time.strftime("%H:%M:%S")


def coletar_tabela(
    etapa: str,
    database_path: Path,
    collector: PhotoCollector,
    estado: Estado,
    *,
    intervalo: float = MIN_INTERVAL,
    lote: int = LOTE,
    esperar: Callable[[float], None] = dormir,
    saida: Callable[[str], None] = print,
) -> dict[str, int]:
    """Jogadores ou clubes sem imagem, um por vez, do menor ID para o maior.

    Cada item grava o ponto de retomada: se cair, volta exatamente no item seguinte. Falha
    de rede repete com pausa crescente; item que nunca dá certo é pulado, sem travar a fila.
    """
    tabela = ETAPAS_POR_TABELA[etapa]
    coluna = ENTITIES[tabela]["path"]
    ultimo = estado.ultimo_id.get(tabela, 0)
    total: Counter[str] = Counter()
    processados = 0
    inicio = time.monotonic()

    with connect(database_path) as connection:
        faltam = connection.execute(
            f"SELECT COUNT(*) FROM {tabela} WHERE {coluna} IS NULL AND id > ?", (ultimo,)
        ).fetchone()[0]
    saida(f"[{_agora()}] {etapa}: {faltam} sem imagem. Ritmo de 30 por minuto.")

    while True:
        with connect(database_path) as connection:
            proximo = connection.execute(
                f"SELECT MIN(id) FROM {tabela} WHERE {coluna} IS NULL AND id > ?", (ultimo,)
            ).fetchone()[0]
        if proximo is None:
            break

        resultado = {"downloaded": 0, "missing": 1, "already_present": 0}
        for tentativa in range(1, MAX_TENTATIVAS_ITEM + 1):
            try:
                with connect(database_path) as connection:
                    resultado = collector.collect_entity(
                        connection, tabela, True, 1, after_id=ultimo
                    )
                break
            except ValueError as erro:  # imagem inválida ou grande demais: não adianta repetir
                LOGGER.warning("%s %s ignorado: %s", etapa, proximo, erro)
                break
            except FALHAS_RECUPERAVEIS as erro:
                if tentativa == MAX_TENTATIVAS_ITEM:
                    LOGGER.warning(
                        "%s %s pulado depois de %s tentativas.", etapa, proximo, tentativa
                    )
                    break
                pausa = pausa_crescente(tentativa)
                LOGGER.warning(
                    "%s %s falhou (%s); nova tentativa em %s s.", etapa, proximo, erro, pausa
                )
                esperar(pausa)

        ultimo = int(proximo)
        estado.ultimo_id[tabela] = ultimo
        estado.salvar()
        total["baixadas"] += resultado["downloaded"]
        total["sem_imagem"] += resultado["missing"]
        total["ja_existiam"] += resultado["already_present"]
        processados += 1
        faltam = max(0, faltam - 1)
        if processados % lote == 0:
            restante = formatar_duracao(faltam * intervalo)
            saida(
                f"[{_agora()}] {etapa}: baixadas {total['baixadas']} | sem imagem "
                f"{total['sem_imagem']} | já existiam {total['ja_existiam']} | "
                f"faltam {faltam} (~{restante})"
            )
    saida(f"[{_agora()}] {etapa}: concluída. {dict(total)}")
    return dict(total)


def coletar_com_busca(
    etapa: str,
    harvester: ImageHarvester,
    *,
    esperar: Callable[[float], None] = dormir,
    saida: Callable[[str], None] = print,
) -> dict[str, int] | None:
    """Ligas, times, estádios, técnicos e lendas. O próprio banco guarda o que já foi feito."""
    saida(f"[{_agora()}] {etapa}: começando.")
    for falha in range(1, MAX_FALHAS_ETAPA + 1):
        try:
            resultado = harvester.run([etapa])[etapa]
        except FALHAS_RECUPERAVEIS as erro:
            pausa = pausa_crescente(falha)
            LOGGER.warning("%s falhou (%s); retomando em %s s.", etapa, erro, pausa)
            esperar(pausa)
            continue
        saida(f"[{_agora()}] {etapa}: concluída. {resultado}")
        return resultado
    LOGGER.error(
        "%s não deu certo depois de %s tentativas; seguindo para a próxima.",
        etapa,
        MAX_FALHAS_ETAPA,
    )
    return None


def coletar_mascotes(
    database_path: Path,
    photo_root: Path,
    estado: Estado,
    *,
    esperar: Callable[[float], None] = dormir,
    saida: Callable[[str], None] = print,
) -> dict[str, int]:
    """Busca imagens de mascotes e salva em data/photos/mascots/<id>.<ext>."""
    pasta = photo_root / "mascots"
    pasta.mkdir(parents=True, exist_ok=True)
    ultimo = estado.ultimo_id.get("mascotes", 0)
    total = {"baixadas": 0, "sem_imagem": 0}
    with connect(database_path) as connection:
        mascotes = connection.execute(
            "SELECT id, name, owner, country FROM mascots WHERE image_path IS NULL AND id > ? ORDER BY id",
            (ultimo,),
        ).fetchall()
    saida(f"[{_agora()}] mascotes: {len(mascotes)} pendentes.")
    headers = {"User-Agent": "MeMiBot/2.0 (contact: memibot@local.dev)"}
    for row in mascotes:
        m_id, name, owner = row["id"], row["name"], row["owner"]
        salvo = False
        termo = f"{name} mascot {owner}".strip()
        url_api = f"https://en.wikipedia.org/w/api.php?action=query&generator=search&gsrsearch={requests.utils.quote(termo)}&prop=pageimages&pithumbsize=500&format=json"
        try:
            resp = requests.get(url_api, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                pages = data.get("query", {}).get("pages", {})
                for page in pages.values():
                    thumb = page.get("thumbnail", {}).get("source")
                    if thumb:
                        img_resp = requests.get(thumb, headers=headers, timeout=15)
                        if img_resp.status_code == 200:
                            ext = ".png" if ".png" in thumb.lower() else ".jpg"
                            destino = pasta / f"{m_id}{ext}"
                            destino.write_bytes(img_resp.content)
                            relativo = str(destino.relative_to(ROOT)).replace("\\", "/")
                            with connect(database_path) as conn:
                                conn.execute("UPDATE mascots SET image_path = ? WHERE id = ?", (relativo, m_id))
                            salvo = True
                            total["baixadas"] += 1
                            break
        except Exception as err:
            LOGGER.debug("Erro ao buscar mascote %s: %s", name, err)
        if not salvo:
            total["sem_imagem"] += 1
        ultimo = m_id
        estado.ultimo_id["mascotes"] = ultimo
        estado.salvar()
        esperar(1.0)
    saida(f"[{_agora()}] mascotes: concluído. {total}")
    return total


def trabalhar(args: argparse.Namespace) -> int:
    """Processo que de fato coleta. O vigia (abaixo) o reinicia se cair ou travar."""
    load_dotenv(ROOT / ".env")
    api_key = args.api_key or os.getenv("THESPORTSDB_API_KEY") or FREE_KEY
    initialize_database(args.database)
    if args.recomecar:
        Path(args.estado).unlink(missing_ok=True)
    estado = Estado.carregar(args.estado)
    if args.retentar:  # volta ao começo para tentar de novo quem não foi achado
        estado.concluidas.clear()
        estado.ultimo_id.clear()
    batimento = Batimento(args.batimento)
    batimento.tocar()
    sessao = LimitedSession(args.intervalo, beat=batimento.tocar)
    collector = PhotoCollector(args.photo_root, sessao, api_key)
    harvester = ImageHarvester(
        args.database,
        SportsDB(api_key, sessao, args.intervalo),
        args.photo_root,
        retry=args.retentar,
    )
    esperar = lambda segundos: dormir(segundos, batimento.tocar)  # noqa: E731

    pendentes: list[str] = []
    try:
        for etapa in args.etapas:
            if etapa in estado.concluidas:
                print(f"[{_agora()}] {etapa}: já concluída antes, pulando.")
                continue
            if etapa in ETAPAS_POR_TABELA:
                coletar_tabela(
                    etapa,
                    args.database,
                    collector,
                    estado,
                    intervalo=args.intervalo,
                    esperar=esperar,
                )
                ok = True
            elif etapa == "mascotes":
                coletar_mascotes(
                    args.database,
                    args.photo_root,
                    estado,
                    esperar=esperar,
                    saida=print,
                )
                ok = True
            else:
                ok = coletar_com_busca(etapa, harvester, esperar=esperar) is not None
            if ok:
                estado.concluidas.append(etapa)
                estado.salvar()
            else:
                pendentes.append(etapa)
    except KeyboardInterrupt:
        print("\nInterrompido. O progresso foi salvo; rode o mesmo comando para continuar.")
        return 130
    if pendentes:
        print(f"Etapas que não terminaram (rode de novo para tentar): {', '.join(pendentes)}")
    else:
        print("Tudo coletado. As imagens ficam em data/photos/<tipo>/<id>.<extensão>.")
    return 0


# --- Vigia -------------------------------------------------------------------------------


def travado(ultimo_sinal: float | None, agora: float, inicio: float, limite: float) -> bool:
    """True se o coletor ficou mais de `limite` segundos sem dar sinal de vida."""
    return agora - (ultimo_sinal if ultimo_sinal else inicio) > limite


def supervisionar(
    comando: list[str],
    batimento: Batimento,
    *,
    travou_apos: float = TRAVOU_APOS,
    lancar: Callable[..., Any] = subprocess.Popen,
    agora: Callable[[], float] = time.time,
    esperar: Callable[[float], None] = time.sleep,
    saida: Callable[[str], None] = print,
) -> int:
    """Mantém o coletor rodando: reinicia se ele cair ou parar de dar sinal de vida."""
    falhas = 0
    filho = None
    try:
        while True:
            batimento.limpar()
            inicio = agora()
            filho = lancar(comando, cwd=str(ROOT))
            codigo = None
            while codigo is None:
                codigo = filho.poll()
                if codigo is not None:
                    break
                if travado(batimento.ultimo(), agora(), inicio, travou_apos):
                    saida(
                        f"[{_agora()}] O coletor ficou {formatar_duracao(travou_apos)} sem "
                        "responder. Reiniciando do mesmo ponto."
                    )
                    filho.kill()
                    filho.wait()
                    codigo = -9
                    break
                esperar(5)
            if codigo in (0, 130):
                return codigo
            if agora() - inicio > 300:
                falhas = 0
            falhas += 1
            pausa = pausa_crescente(falhas)
            saida(f"[{_agora()}] Coletor parou (código {codigo}). Reiniciando em {pausa} s.")
            esperar(pausa)
    except KeyboardInterrupt:
        if filho is not None and filho.poll() is None:
            filho.terminate()
        print("\nParado. O progresso foi salvo; rode o mesmo comando para continuar.")
        return 130


# --- Linha de comando --------------------------------------------------------------------


def montar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--database", type=Path, default=DATABASE_PATH)
    parser.add_argument("--photo-root", type=Path, default=PHOTO_ROOT)
    parser.add_argument(
        "--etapas", default=",".join(ETAPAS), help=f"separadas por vírgula: {', '.join(ETAPAS)}"
    )
    parser.add_argument("--api-key", help="chave do TheSportsDB (padrão: .env, ou a gratuita 123)")
    parser.add_argument(
        "--intervalo", type=float, default=MIN_INTERVAL, help="segundos entre consultas"
    )
    parser.add_argument(
        "--travou-apos", type=int, default=TRAVOU_APOS, help="segundos sem sinal para reiniciar"
    )
    parser.add_argument("--estado", type=Path, default=STATE_PATH)
    parser.add_argument("--batimento", type=Path, default=BEAT_PATH)
    parser.add_argument("--recomecar", action="store_true", help="apaga o ponto de retomada")
    parser.add_argument("--retentar", action="store_true", help="busca de novo quem não foi achado")
    parser.add_argument(
        "--sem-vigia", action="store_true", help="roda direto, sem reinício automático"
    )
    parser.add_argument("--trabalhador", action="store_true", help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = montar_parser()
    args = parser.parse_args(argv)
    etapas = [item.strip() for item in args.etapas.split(",") if item.strip()]
    desconhecidas = [item for item in etapas if item not in ETAPAS]
    if desconhecidas:
        parser.error(f"Etapas desconhecidas: {', '.join(desconhecidas)}. Use {', '.join(ETAPAS)}.")
    args.etapas = etapas
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.trabalhador or args.sem_vigia:
        return trabalhar(args)

    load_dotenv(ROOT / ".env")
    chave = args.api_key or os.getenv("THESPORTSDB_API_KEY") or FREE_KEY
    print(f"Coletor de imagens: {', '.join(etapas)}")
    print(
        f"Chave: {'gratuita (123)' if chave == FREE_KEY else 'do .env/--api-key'} | 30 consultas por minuto"
    )
    print("Pode parar com Ctrl+C e continuar depois: o progresso fica salvo.\n")
    if args.recomecar:
        Path(args.estado).unlink(missing_ok=True)
    comando = [
        sys.executable, "-m", "scripts.coletar_imagens", "--trabalhador",
        "--database", str(args.database), "--photo-root", str(args.photo_root),
        "--etapas", ",".join(etapas), "--intervalo", str(args.intervalo),
        "--estado", str(args.estado), "--batimento", str(args.batimento),
    ]  # fmt: skip
    if args.api_key:
        comando += ["--api-key", args.api_key]
    if args.retentar:
        comando.append("--retentar")
    return supervisionar(comando, Batimento(args.batimento), travou_apos=args.travou_apos)


if __name__ == "__main__":
    raise SystemExit(main())
