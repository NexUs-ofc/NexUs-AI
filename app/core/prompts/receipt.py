RECEIPT_ENRICH_PROMPT = """Você recebe o texto de uma nota fiscal de supermercado brasileira lido por OCR (com erros) e uma lista de itens já extraídos por regras.

Sua tarefa, para CADA item da lista (mantenha a mesma ordem e o mesmo "id"), é devolver apenas o nome:
- "name": nome legível do produto em português, expandindo abreviações de nota (ex.: "AMAC.COMFORT 500ML" -> "Amaciante Comfort 500ml", "CHOC.LACTA 20G" -> "Chocolate Lacta 20g", "LTE COND" -> "Leite Condensado"). Corrija erros óbvios de OCR (ex.: "500ME" -> "500ml").

Regras:
- NÃO invente itens, preços, quantidades ou códigos de barras. Não adicione nem remova itens.
- Se o item não tiver descrição, procure no texto do OCR a linha correspondente. Se não achar, responda exatamente "Item não identificado". NUNCA repita o nome de outro item da lista nem deduza o produto pelo preço.
- Responda SOMENTE com JSON no formato: {"items": [{"id": 0, "name": "..."}]}
"""

RECEIPT_CLASSIFY_PROMPT = """Você classifica produtos de supermercado brasileiro em categorias.

Para CADA item recebido (mantenha a mesma ordem e o mesmo "id"):
- "category": EXATAMENTE uma das categorias permitidas.
- "shelf_life_days": estimativa típica de validade em dias para esse produto fechado.

Regras:
- Não adicione nem remova itens.
- Se o nome for "Item não identificado" ou não permitir decidir, use a categoria "Outros".
- Responda SOMENTE com JSON no formato: {"items": [{"id": 0, "category": "...", "shelf_life_days": 30}]}

Categorias permitidas: {categories}
"""

RECEIPT_EXTRACT_PROMPT = """Você recebe uma nota fiscal de supermercado brasileira (texto de OCR com erros, ou a imagem da nota).
Extraia os produtos comprados. Ignore cabeçalho, impostos, forma de pagamento e troco.

Para cada produto:
- "raw_text": descrição como aparece na nota
- "name": nome legível em português, expandindo abreviações
- "ean": código de barras de 8 a 14 dígitos se aparecer, senão null (copie exatamente, não invente)
- "quantity": quantidade (número)
- "unit": "un", "kg", "g", "l" ou "ml"
- "unit_price": preço unitário (número) ou null
- "category": EXATAMENTE uma das categorias permitidas
- "shelf_life_days": estimativa típica de validade em dias

Também extraia "store" (nome da loja), "purchase_date" (AAAA-MM-DD ou null) e "total" (número ou null).
Responda SOMENTE com JSON: {"store": ..., "purchase_date": ..., "total": ..., "items": [...]}

Categorias permitidas: {categories}
"""
