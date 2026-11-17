"""`..ajuda <comando>`: explicação e exemplos de cada comando do FUT.AE.

A lista geral (`..ajuda` sem nada) continua nas páginas de cada bot; aqui fica o detalhe.
Aceita o nome ou qualquer alias (`..ajuda sw` mostra o `..starwish`).
"""

from __future__ import annotations

import discord

# Comando -> (uso, explicação, exemplos).
COMMAND_HELP: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "roll": (
        "..roll",
        "Sorteia um jogador. Livre: o botão **Reivindicar** contrata (1 por ciclo de 30 min, "
        "mais as contratações extras). Seu: ganha uma bola. De outra pessoa: Memilets. O botão "
        "**Rolar de novo** rola sem digitar.",
        ("..roll",),
    ),
    "daily": (
        "..daily",
        "Memilets uma vez por dia (mais com cosméticos, upgrades e torre). A resposta mostra as "
        "missões do dia e o botão para resgatar as prontas.",
        ("..daily",),
    ),
    "tu": (
        "..tu",
        "Timers da conta (rolls, claim, daily) com atalhos: Rolar, Daily, Missões, Ativar "
        "rolls e Inventário.",
        ("..tu",),
    ),
    "carteira": (
        "..carteira",
        "Saldo, elenco, rolls (do ciclo, ativos e guardados), wishes e timers, com os mesmos "
        "atalhos do `..tu`.",
        ("..carteira",),
    ),
    "shop": (
        "..shop",
        "A loja inteira: caixas, pacotes, all-in, upgrades e torre, com botões de compra. "
        "Botão cinza = falta saldo (mostra quanto).",
        ("..shop", "..loja"),
    ),
    "crates": (
        "..crates [epica] [1|5|10]",
        "Caixas com rolls guardados, cosméticos, bônus, caixas e pacotes. Garantia: Raro em 15 "
        "caixas sem Raro, Épico em 50 sem Épico e Lendário em 200 sem Lendário. A caixa épica "
        "nunca vem só com o básico.",
        ("..crates", "..crates 10", "..crates epica 5"),
    ),
    "pacote": (
        "..pacote [epico]",
        "Uma carta livre do mercado (nunca Base). A do pacote comum vende na hora por 50%; a do "
        "épico, pelo valor cheio. As duas ficam 1 hora sem poder ser doadas ou trocadas.",
        ("..pacote", "..pacote epico"),
    ),
    "allin": (
        "..allin",
        "Aposta: uma roleta com 1 chance em 10 de Ícone ou melhor; nas outras fatias, uma "
        "carta comum. Sem Ícone livre no mercado, não gira e não cobra.",
        ("..allin",),
    ),
    "inventario": (
        "..inventario",
        "Caixas e pacotes ganhos nas caixas. **Abrir** abre um (de graça); **Abrir todas as "
        "caixas** abre até 20 num lote.",
        ("..inventario", "..inv"),
    ),
    "ativar": (
        "..ativar <quantidade>",
        "Ativa rolls guardados das caixas: valem depois dos rolls do ciclo, e cada 10 ativados "
        "dão +1 contratação extra (a sobra conta para a próxima).",
        ("..ativar 10", "..ativar 25"),
    ),
    "upgrade": (
        "..upgrade [nome]",
        "Upgrades permanentes (rolls, wishes, Star Wish, daily…). Sempre pede confirmação.",
        ("..upgrade", "..upgrade olheiro"),
    ),
    "construir": (
        "..construir [1-12]",
        "A torre do Centro de Treinamento: menu para escolher o andar e botão de destruir "
        "(devolve tudo).",
        ("..construir", "..construir 7", "..destruir"),
    ),
    "wish": (
        "..wish [jogador]",
        "Marca um jogador que você quer: ele aparece mais protegido para você quando alguém "
        "rola. Sem nome, mostra suas wishes. Também como `/wish`, com sugestões.",
        ("..wish Vini Jr", "..wl"),
    ),
    "starwish": (
        "..starwish [jogador]",
        "Wish especial: aumenta a chance de o jogador aparecer nos seus rolls.",
        ("..sw Haaland",),
    ),
    "vender": (
        "..vender [jogador | filtro]",
        "Vende jogadores. Sem nada, abre o painel. Filtros vendem vários de uma vez (sem "
        "titulares nem protegidos), sempre com o total antes.",
        ("..vender Fulano", "..vender base", "..vender abaixo 70", "..vender posicao ZAG"),
    ),
    "proteger": (
        "..proteger [jogador]",
        "Liga/desliga o 🔒: o jogador some de todas as vendas.",
        ("..proteger Fulano",),
    ),
    "dar": (
        "..dar @pessoa <jogador | valor>",
        "Doa um jogador ou Memilets, com confirmação. A outra pessoa não precisa aceitar.",
        ("..dar @Ana Fulano", "..dar @Ana 5000"),
    ),
    "pay": (
        "..pay @pessoa <quantia>",
        "Manda Memilets para outra pessoa, com confirmação.",
        ("..pay @Ana 5000", "..pagar @Ana 1.000"),
    ),
    "comparar": (
        "..comparar @pessoa",
        "Seu time e o da pessoa lado a lado: as duas escalações, força por setor (▲ em quem é "
        "melhor), melhor jogador, valor do elenco, forma, confronto direto e o prognóstico "
        "da partida (simulada 500 vezes, você em casa).",
        ("..comparar @Ana", "..vs @Ana"),
    ),
    "mercado": (
        "..mercado",
        "Jogadores à venda por outras pessoas, com ordem (mais novos, mais baratos, melhores) "
        "e um menu para comprar. Quem vende paga 5% de taxa.",
        ("..mercado",),
    ),
    "anunciar": (
        "..anunciar <jogador> <preço>",
        "Põe um jogador seu à venda no mercado. A carta fica no seu elenco até alguém "
        "comprar. Até 10 anúncios, valem 3 dias. Protegidos não podem ser anunciados.",
        ("..anunciar Vini Jr 50000", "..anunciar Haaland 120k"),
    ),
    "anuncios": (
        "..anuncios",
        "Os seus anúncios, com o menu para tirar algum do mercado.",
        ("..anuncios",),
    ),
    "troca": (
        "..troca @pessoa",
        "Abre uma proposta de troca de jogadores e Memilets; os dois confirmam.",
        ("..troca @Ana",),
    ),
    "elenco": (
        "..elenco [@pessoa]",
        "O elenco em cartas, com menu para ordenar.",
        ("..elenco", "..elenco @Ana"),
    ),
    "scout": (
        "..scout <jogador>",
        "A carta e os dados de um jogador. Também como `/scout`, com sugestões.",
        ("..scout Messi", "..im Messi"),
    ),
    "missoes": (
        "..missoes",
        "Missões do dia e da semana, com o botão para resgatar as prontas.",
        ("..missoes",),
    ),
    "time": (
        "..time",
        "Seu time: escalação, tática e personalização num menu só.",
        ("..time",),
    ),
    "amistoso": (
        "..amistoso @pessoa [idaevolta] [aposta <valor>]",
        "Um amistoso contra outro time; o primeiro do dia em casa gera renda. Com "
        "`idaevolta`, são dois jogos: ida na sua casa e volta na do outro; vale o placar "
        "somado (empate no agregado vai para os pênaltis no fim da volta). Com `aposta`, o "
        "outro aceita, cada um entra com o valor e quem vence leva tudo (sem renda).",
        (
            "..amistoso @Ana",
            "..amistoso @Ana idaevolta",
            "..amistoso @Ana aposta 1000",
            "..amistoso @Ana ida aposta 5k",
        ),
    ),
    "desafio": (
        "..desafio",
        "Partidas contra times lendários (clubes brasileiros de todos os tempos, seleções "
        "lendárias e a Seleção Mundial). Escada de 28 degraus com prêmio em cada um, chefão "
        "do dia (1 tentativa), chefão da semana (3 tentativas) e desafio livre contra quem "
        "você escolher.",
        ("..desafio", "..pve"),
    ),
    "cassino": (
        "..cassino [valor]",
        "Cassino: cara ou coroa (2x), caça-níquel "
        "(três iguais até 250x), roleta (cor/par 2x, dúzia 3x, número 36x) e minas (cada casa "
        "segura aumenta o prêmio; saque quando quiser). Aposta de 100 a 100.000.",
        ("..cassino", "..bet 5000", "..apostar 10k"),
    ),
    "penaltis": (
        "..penaltis @pessoa [aposta]",
        "Disputa de pênaltis: quem bate escolhe o canto e quem defende escolhe onde pular, "
        "em segredo. 5 cobranças para cada lado e morte súbita. Com aposta, quem vence leva "
        "o pote.",
        ("..penaltis @Ana", "..penaltis @Ana 2000"),
    ),
    "campeonato": (
        "..campeonato [tabela | agenda [@pessoa] | copa | historico]",
        "Painel do Pontos Corridos e da Copa IOS com botões (Resumo, Tabela, Agenda, Copa, "
        "Campeões). Quem tem o time completo entra sozinho; os jogos são todo dia no horário do "
        "servidor. Admins: `status`, `jogar`, `adiantar`, `pausar`, `retomar`, `horario`, "
        "`remover`, `cancelar`.",
        ("..campeonato", "..campeonato agenda @Ana", "..campeonato status"),
    ),
    "pontos": (
        "..pontos [rodada N]",
        "Pontos Corridos: a tabela com o seu próximo jogo, e os jogos de qualquer rodada. Os 2 "
        "primeiros fazem a final. Admins: `adiantar` (joga já a próxima rodada), `encerrar "
        "confirmar` (acaba os pontos corridos e marca a final) e `refazer @pessoa` (refaz o jogo "
        "de hoje).",
        ("..pontos", "..pontos rodada 3", "..pontos adiantar"),
    ),
    "copa": (
        "..copa",
        "Copa IOS: a chave com o seu próximo jogo. Começa depois da final do Pontos Corridos, uma fase "
        "por dia. Admins: `adiantar` (joga já a próxima fase), `sortear` (sorteia de novo antes "
        "de começar), `wo @pessoa` (W.O. no próximo jogo) e `refazer @pessoa`.",
        ("..copa", "..copa adiantar", "..copa wo @Ana"),
    ),
    "grupo": (
        "..grupo [criar | convidar | aceitar | otimizar | mover | vender | escalar | elenco]",
        "Grupo de clubes: junte as suas contas (cada uma segue com o seu clube e joga por si) e "
        "gerencie todas pela Principal. `otimizar` põe o melhor XI possível na Principal, o que "
        "sobra na Secundária e assim por diante, mostrando o plano antes. `mover <jogador> "
        "<conta>`, `vender [conta] [filtro]` (venda em massa em todas as contas), `escalar` e "
        "`elenco`. A conta convidada aceita com `..grupo aceitar` e pode sair quando quiser. "
        "Transferências travam 15 min antes dos jogos do campeonato.",
        (
            "..grupo criar Grupo Exemplo",
            "..grupo convidar @conta2",
            "..grupo otimizar",
            "..grupo mover Vinícius 2",
            "..grupo vender abaixo 70",
        ),
    ),
}


def command_help_embed(bot, name: str) -> discord.Embed | None:
    """Embed com o uso e os exemplos de `name` (nome ou alias); None se não existe."""
    command = bot.get_command(name.strip().lower().removeprefix(".."))
    if command is None:
        return None
    usage, text, examples = COMMAND_HELP.get(
        command.name, (f"..{command.name}", command.help or "Sem descrição ainda.", ())
    )
    embed = discord.Embed(
        title=f"❔ ..{command.name}", description=text, color=discord.Color.blurple()
    )
    embed.add_field(name="Uso", value=f"`{usage}`", inline=False)
    if examples:
        embed.add_field(
            name="Exemplos", value="\n".join(f"`{example}`" for example in examples), inline=False
        )
    if command.aliases:
        embed.add_field(
            name="Também funciona como",
            value=" · ".join(f"`..{alias}`" for alias in command.aliases),
            inline=False,
        )
    return embed
