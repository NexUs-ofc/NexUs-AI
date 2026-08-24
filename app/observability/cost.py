GROQ_OPENAI_GPT_OSS_20B_PRICE_PER_1M_INPUT_TOKENS_USD = 0.10
GROQ_OPENAI_GPT_OSS_20B_PRICE_PER_1M_OUTPUT_TOKENS_USD = 0.50


def estimate_cost_usd(input_tokens: int, output_tokens: int) -> float:
    custo_input = (input_tokens / 1_000_000) * GROQ_OPENAI_GPT_OSS_20B_PRICE_PER_1M_INPUT_TOKENS_USD
    custo_output = (output_tokens / 1_000_000) * GROQ_OPENAI_GPT_OSS_20B_PRICE_PER_1M_OUTPUT_TOKENS_USD

    return round(custo_input + custo_output, 8)


def extrair_tokens(resposta) -> tuple[int, int]:
    usage = getattr(resposta, "usage_metadata", None)

    if not usage:
        return 0, 0

    return usage.get("input_tokens", 0), usage.get("output_tokens", 0)
