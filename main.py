from app.schemas.flow import app


def main():
    historico = []

    while True:
        mensagem = input("\n >>: ")
        if mensagem.lower() in ("sari", "exit", "quit"):
            break

        resultado = app.invoke({
            "mensagem": mensagem,
            "historico": historico,
            "rota": "",
            "resposta_agente": "",
            "resposta_final": "",
            "entrada_aprovada": False,
            "saida_aprovada": False,
            "mapa_pii": {},
            "household_account_id": 1,
            "account_id": 1,
        })

        resposta = resultado["resposta_final"]
        print(f"\nCeris: {resposta}")

        historico.append({"role": "user", "content": mensagem})
        historico.append({"role": "assistant", "content": resposta})


if __name__ == "__main__":
    main()
