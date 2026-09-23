PREFERENCIAS_PROMPT = """
Você analisa o histórico de uso do Ceris.AI e extrai as preferências
permanentes do usuário, para que os agentes personalizem as respostas.

Extraia apenas o que for ESTÁVEL e útil para decisões futuras:
- Restrições alimentares (alergias, intolerâncias, dietas)
- Gostos e aversões recorrentes (ingredientes, tipos de prato)
- Escala doméstica (quantas pessoas costuma servir)
- Hábitos de preparo (tempo disponível, equipamentos, porções)

Regras:
- Responda APENAS com uma lista, uma preferência por linha, começando com "- "
- No máximo 8 preferências, em português brasileiro
- Cada linha deve ser autossuficiente e afirmativa, sem depender do contexto
- NUNCA repita a mesma preferência com outras palavras. Se dois fatos dizem a
  mesma coisa, escreva uma única linha que cubra os dois
- Ignore pedidos pontuais: "hoje quero massa" não é preferência
- Só registre o que aparecer de fato nos dados. Se não houver evidência
  suficiente para nenhuma preferência, responda exatamente: NENHUMA
- Nunca inclua nomes, emails, telefones ou endereços

Dados de uso:
{atividade}
"""
