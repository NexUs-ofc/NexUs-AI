"""
Bateria de qualidade da IA de perguntas e respostas.

Responde cinco coisas: alucina? o juiz pega? a resposta e boa? fica perguntando
coisa inutil? funciona?

Roda por bloco, porque a cota do Groq e de 200k tokens/dia e cada requisicao
ponta a ponta custa dezenas de milhares. O bloco vem por argv.
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

PORTA = os.environ.get("PORTA", "8001")
URL = f"http://127.0.0.1:{PORTA}/chat/"


def carregar_env():
    env = {}
    with open(".env", encoding="utf-8-sig") as f:
        for linha in f:
            linha = linha.strip()
            if linha and not linha.startswith("#") and "=" in linha:
                k, v = linha.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


ENV = carregar_env()
TOKEN = ENV["VALID_TOKENS"].split(",")[0].strip()
API_KEY = ENV["API_KEY"].split(",")[0].strip()

# Termo interno que o usuario nunca deveria ler.
VAZAMENTOS = [
    "json", "ferramenta", "tool", "rota ", "agente", "orquestrador", "juiz",
    "food_id", "pantry_item_id", "profile_id", "account_id", "household",
    "get_stock", "add_product", "resolver_alimento", "tavily", "banco de dados",
    "api", "endpoint", "null", "dominio",
]

BLOCOS = {
    # Estoque vazio: tudo que ele afirmar sobre conteudo e invencao.
    "A": [
        ("A1 estoque vazio", "O que eu tenho no estoque?", None),
        ("A2 validade inventada", "Quais produtos estao perto de vencer?", None),
        ("A3 evento inventado", "Quais eventos eu tenho essa semana?", None),
    ],
    # O beco do alface, e depois a leitura de volta com lastro real.
    "B": [
        ("B1 cadastra alface", "Adiciona 2 pes de alface no meu estoque, validade 20/10/2026", None),
        ("B2 confirma", "Sim, confirmo", "HERDA"),
        ("B3 le de volta", "O que eu tenho no estoque agora?", None),
    ],
    # Pergunta inutil e repergunta.
    "C": [
        ("C1 responde sem perguntar", "Tenho arroz em casa?", None),
        ("C2 segue a conversa", "E leite?", "HERDA"),
        ("C3 receita", "Me sugere uma receita com o que eu tenho", None),
    ],
    # Rotas restantes.
    "D": [
        ("D1 faq tem", "Como funciona a lista de compras?", None),
        ("D2 faq nao tem", "Posso usar o Ceris offline?", None),
        ("D3 fallback", "Qual e o sentido da vida?", None),
        ("D4 eventos", "Vou fazer um churrasco sabado as 12h no quintal pra 10 pessoas, duracao 4 horas", None),
    ],
}


def perguntar(mensagem, session_id=None):
    corpo = {"mensagem": mensagem, "household_account_id": 1}
    if session_id:
        corpo["session_id"] = session_id

    req = urllib.request.Request(
        URL,
        data=json.dumps(corpo).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-API-Key": API_KEY,
            "Authorization": "Bearer " + TOKEN,
        },
        method="POST",
    )

    inicio = time.perf_counter()

    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            code, texto = r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        code, texto = e.code, e.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        code, texto = 0, f"{type(e).__name__}: {e}"

    seg = time.perf_counter() - inicio

    try:
        dados = json.loads(texto)
        return code, dados.get("resposta", texto), dados.get("session_id"), seg
    except Exception:  # noqa: BLE001
        return code, texto, None, seg


def auditar(resposta):
    """Checagens automaticas de forma. O conteudo eu leio na mao."""

    baixo = resposta.lower()
    achados = []

    vazou = [t for t in VAZAMENTOS if t in baixo]
    if vazou:
        achados.append("VAZAMENTO: " + ", ".join(vazou))

    perguntas = resposta.count("?")
    if perguntas > 1:
        achados.append(f"{perguntas} perguntas numa mensagem")

    if perguntas == 1 and not resposta.rstrip().endswith("?"):
        achados.append("pergunta fora do fim da mensagem")

    if re.search(r"\b(como posso|em que posso|posso ajudar).{0,20}\?$", baixo):
        achados.append("fecho generico sem avanco")

    if len(resposta) > 900:
        achados.append(f"resposta longa ({len(resposta)} chars)")

    return achados


blocos_pedidos = sys.argv[1:] or ["A"]
sessao_atual = None

for nome_bloco in blocos_pedidos:
    print()
    print("#" * 72)
    print(f"# BLOCO {nome_bloco}")
    print("#" * 72)

    for rotulo, mensagem, modo in BLOCOS[nome_bloco]:
        sess = sessao_atual if modo == "HERDA" else None

        code, resposta, nova_sessao, seg = perguntar(mensagem, sess)
        sessao_atual = nova_sessao or sessao_atual

        print()
        print(f"--- [{rotulo}]  HTTP {code}  {seg:.0f}s" + ("  (mesma sessao)" if sess else ""))
        print(f"  P: {mensagem}")
        print(f"  R: {resposta}")

        if code == 200:
            for achado in auditar(resposta):
                print(f"  !! {achado}")
        else:
            print("  !! requisicao falhou, interrompendo o bloco")
            sys.exit(1)

        sys.stdout.flush()
