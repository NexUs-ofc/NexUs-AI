from app.schemas.flow import app


def main():
    historico = []

    while True:
        mensagem = input("\nVocê: ")
        if mensagem.lower() in ("sair", "exit", "quit"):
            break

        resultado = app.invoke({
            "mensagem": mensagem,
            "historico": historico,
            "rota": "",
            "resposta_agente": "",
            "resposta_final": "",
            "guardrail_entrada": False,
            "guardrail_saida": False,
            "mapa_pii": {},
        })

        resposta = resultado["resposta_final"]
        print(f"\nCeris: {resposta}")

        historico.append({"role": "user", "content": mensagem})
        historico.append({"role": "assistant", "content": resposta})


if __name__ == "__main__":
    main()
