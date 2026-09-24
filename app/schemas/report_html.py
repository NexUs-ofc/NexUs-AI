from html import escape

ESTILO = """
* { box-sizing: border-box; }
body {
  font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif;
  color: #1f2937; background: #ffffff;
  margin: 0 auto; padding: 40px 32px; max-width: 900px; line-height: 1.55;
}
header { border-bottom: 3px solid #7c3aed; padding-bottom: 18px; margin-bottom: 28px; }
h1 { margin: 0; font-size: 26px; }
header p { margin: 6px 0 0; color: #6b7280; font-size: 14px; }
h2 {
  font-size: 15px; text-transform: uppercase; letter-spacing: .04em;
  color: #7c3aed; margin: 32px 0 12px; padding-bottom: 6px;
  border-bottom: 1px solid #ede9fe;
}
table { width: 100%; border-collapse: collapse; margin: 10px 0 4px; font-size: 14px; }
th {
  text-align: left; background: #f3f4f6; color: #4b5563;
  font-size: 12px; text-transform: uppercase; letter-spacing: .03em;
  padding: 9px 12px; border-bottom: 2px solid #d1d5db;
}
td { padding: 9px 12px; border-bottom: 1px solid #f3f4f6; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
.destaques { display: flex; gap: 14px; flex-wrap: wrap; margin: 14px 0 4px; }
.destaque {
  flex: 1 1 180px; background: #f3f4f6; border-radius: 10px; padding: 14px 16px;
}
.destaque .rotulo {
  font-size: 11px; font-weight: 700; color: #7c3aed;
  text-transform: uppercase; letter-spacing: .03em;
}
.destaque .valor { font-size: 22px; font-weight: 700; margin-top: 4px; }
.destaque .nota { font-size: 12px; color: #6b7280; margin-top: 2px; }
.nota-bloco {
  background: #ede9fe; border: 1px solid #ddd6fe; border-radius: 10px;
  padding: 14px 16px; color: #4c1d95; font-size: 13px; margin: 14px 0;
}
.alerta-bloco {
  background: #fef3c7; border: 1px solid #fde68a; border-radius: 10px;
  padding: 14px 16px; color: #92400e; font-size: 13px; margin: 14px 0;
}
code {
  background: #f3f4f6; padding: 2px 6px; border-radius: 4px;
  font-size: 13px; font-family: Consolas, Monaco, monospace;
}
pre {
  background: #f3f4f6; padding: 14px 16px; border-radius: 8px;
  font-size: 13px; overflow-x: auto; font-family: Consolas, Monaco, monospace;
}
footer {
  margin-top: 40px; padding-top: 16px; border-top: 1px solid #d1d5db;
  color: #6b7280; font-size: 12px;
}
@media print {
  body { padding: 0; max-width: none; }
  h2 { break-after: avoid; }
  table, .destaques { break-inside: avoid; }
}
"""


def _brl(valor) -> str:
    if valor is None:
        return "—"

    texto = f"{valor:,.4f}".replace(",", "X").replace(".", ",").replace("X", ".")

    return f"R$ {texto}"


def _usd(valor) -> str:
    return "—" if valor is None else f"US$ {valor:,.6f}"


def _seg(valor) -> str:
    return f"{valor:.2f} s"


def montar_html(dados: dict) -> str:
    if dados.get("erro"):
        return (
            "<!DOCTYPE html><html lang='pt-BR'><head><meta charset='utf-8'>"
            f"<title>Relatório — erro</title><style>{ESTILO}</style></head><body>"
            "<header><h1>Relatório de Observabilidade</h1></header>"
            f"<div class='alerta-bloco'>{escape(dados['erro'])}</div>"
            "</body></html>"
        )

    partes = []
    ad = partes.append

    cotacao = dados["cotacao"]
    req = dados["requisicoes"]
    tempo = dados["tempo_total"]
    custo = dados["custo"]
    resolucao = dados["resolucao"]
    roi = dados["roi"]
    projecao = dados["projecao"]

    ad("<!DOCTYPE html><html lang='pt-BR'><head><meta charset='utf-8'>")
    ad("<meta name='viewport' content='width=device-width, initial-scale=1'>")
    ad("<title>Relatório de Observabilidade — Ceris.AI</title>")
    ad(f"<style>{ESTILO}</style></head><body>")

    ad("<header><h1>Relatório de Observabilidade</h1>")
    ad(
        f"<p>Ceris.AI — ms-ia · projeto <code>{escape(dados['projeto'])}</code> · "
        f"últimos {req and dados['periodo']['dias']} dias · "
        f"gerado em {escape(dados['gerado_em'])}</p></header>"
    )

    if not req["total"]:
        ad(
            "<div class='alerta-bloco'><strong>Sem requisições no período.</strong> "
            "O relatório precisa de runs <code>ceris_chat_request</code> no LangSmith. "
            "Gere tráfego com a instrumentação ativa antes de usar estes números.</div>"
        )

    ad("<h2>1. Volume e confiabilidade</h2>")
    ad("<div class='destaques'>")
    ad(f"<div class='destaque'><div class='rotulo'>Requisições</div><div class='valor'>{req['total']}</div><div class='nota'>no período</div></div>")
    ad(f"<div class='destaque'><div class='rotulo'>Índice de erros</div><div class='valor'>{req['taxa_erro_pct']}%</div><div class='nota'>{req['com_erro']} com falha</div></div>")
    ad(f"<div class='destaque'><div class='rotulo'>Sessões</div><div class='valor'>{resolucao['sessoes']}</div><div class='nota'>{resolucao['mensagens_por_sessao']} msg/sessão</div></div>")
    ad(f"<div class='destaque'><div class='rotulo'>Chamadas de LLM</div><div class='valor'>{custo['chamadas_llm']}</div><div class='nota'>{req['runs_coletadas']} runs</div></div>")
    ad("</div>")

    if dados["erros"]:
        ad("<table><tr><th>Quando</th><th>Erro</th></tr>")
        for erro in dados["erros"]:
            ad(f"<tr><td>{escape(erro['quando'])}</td><td>{escape(erro['detalhe'])}</td></tr>")
        ad("</table>")

    ad("<h2>2. Tempo total de resposta</h2>")
    ad("<table><tr><th>Média</th><th class='num'>Mediana</th><th class='num'>P95</th><th class='num'>Mínimo</th><th class='num'>Máximo</th></tr>")
    ad(
        f"<tr><td>{_seg(tempo['media_s'])}</td><td class='num'>{_seg(tempo['mediana_s'])}</td>"
        f"<td class='num'>{_seg(tempo['p95_s'])}</td><td class='num'>{_seg(tempo['min_s'])}</td>"
        f"<td class='num'>{_seg(tempo['max_s'])}</td></tr></table>"
    )
    ad("<div class='nota-bloco'>A mediana costuma representar melhor o comportamento típico que a média, que é puxada por casos extremos.</div>")

    ad("<h2>3. Latência interagentes</h2>")

    if dados["agentes"]:
        ad("<table><tr><th>Agente</th><th class='num'>Chamadas</th><th class='num'>Média</th><th class='num'>Mediana</th><th class='num'>P95</th></tr>")
        for item in dados["agentes"]:
            ad(
                f"<tr><td><code>{escape(item['nome'])}</code></td><td class='num'>{item['chamadas']}</td>"
                f"<td class='num'>{_seg(item['media_s'])}</td><td class='num'>{_seg(item['mediana_s'])}</td>"
                f"<td class='num'>{_seg(item['p95_s'])}</td></tr>"
            )
        ad("</table>")
    else:
        ad("<p>Nenhum span de agente no período.</p>")

    if dados["etapas"]:
        ad("<h2>4. Etapas do pipeline</h2>")
        ad("<table><tr><th>Etapa</th><th class='num'>Chamadas</th><th class='num'>Média</th><th class='num'>Mediana</th><th class='num'>P95</th></tr>")
        for item in dados["etapas"]:
            ad(
                f"<tr><td><code>{escape(item['nome'])}</code></td><td class='num'>{item['chamadas']}</td>"
                f"<td class='num'>{_seg(item['media_s'])}</td><td class='num'>{_seg(item['mediana_s'])}</td>"
                f"<td class='num'>{_seg(item['p95_s'])}</td></tr>"
            )
        ad("</table>")

    ad("<h2>5. Custo</h2>")
    ad("<div class='destaques'>")
    ad(f"<div class='destaque'><div class='rotulo'>Total do período</div><div class='valor'>{_brl(custo['total_brl'])}</div><div class='nota'>{_usd(custo['total_usd'])}</div></div>")
    ad(f"<div class='destaque'><div class='rotulo'>Por requisição</div><div class='valor'>{_brl(custo['por_requisicao_brl'])}</div><div class='nota'>{_usd(custo['por_requisicao_usd'])}</div></div>")
    ad(f"<div class='destaque'><div class='rotulo'>Por resolução</div><div class='valor'>{_brl(resolucao['custo_brl'])}</div><div class='nota'>uma sessão de conversa</div></div>")
    ad("</div>")
    ad(
        f"<p>Tokens: <strong>{custo['tokens_entrada']:,}</strong> de entrada e "
        f"<strong>{custo['tokens_saida']:,}</strong> de saída. "
        f"Modelos: {escape(', '.join(f'{k} ({v})' for k, v in custo['modelos'].items()) or '—')}.</p>"
    )

    ad("<h2>6. Custo estimado por volume de usuários</h2>")
    ad(f"<div class='nota-bloco'><strong>Suposição declarada:</strong> cada usuário envia {projecao['mensagens_semana']} mensagens por semana.</div>")
    ad("<table><tr><th>Cenário</th><th class='num'>Mensagens/semana</th><th class='num'>Custo/semana</th><th class='num'>Custo/mês</th></tr>")
    for cenario in projecao["cenarios"]:
        ad(
            f"<tr><td>{cenario['usuarios']} usuários semanais</td>"
            f"<td class='num'>{cenario['mensagens_semana']:,}</td>"
            f"<td class='num'>{_brl(cenario['semanal_brl'])}</td>"
            f"<td class='num'>{_brl(cenario['mensal_brl'])}</td></tr>"
        )
    ad("</table>")

    ad("<h2>7. Custo / Retorno (ROI)</h2>")
    ad("<pre>ROI (%) = (economia_mensal − custo_mensal) ÷ custo_mensal × 100</pre>")
    ad(f"<p>Lado do custo, medido: <strong>{_brl(roi['custo_mensal_brl'])}</strong> por household/mês.</p>")

    if roi["roi_pct"] is not None:
        ad(
            f"<div class='destaques'><div class='destaque'><div class='rotulo'>ROI</div>"
            f"<div class='valor'>{roi['roi_pct']}%</div>"
            f"<div class='nota'>economia assumida de {_brl(roi['economia_mensal_brl'])}/mês</div></div></div>"
        )
    else:
        ad(
            "<div class='alerta-bloco'><strong>Pendente.</strong> O lado da economia não é "
            "derivável da observabilidade — depende de uma suposição de negócio sobre quanto "
            "o Ceris evita de desperdício por household/mês. Informe o parâmetro "
            "<code>economia_mensal_brl</code> para calcular.</div>"
        )

    ad("<h2>8. Metodologia</h2>")
    ad("<table><tr><th>Item</th><th>Origem</th></tr>")
    ad("<tr><td>Tempo total de resposta</td><td>duração das runs <code>ceris_chat_request</code> no LangSmith</td></tr>")
    ad("<tr><td>Latência interagentes</td><td>duração dos spans <code>agente_*</code>, deduplicados por trace</td></tr>")
    ad("<tr><td>Índice de erros</td><td>runs raiz com <code>status = error</code> sobre o total</td></tr>")
    ad("<tr><td>Custo</td><td>campo <code>total_cost</code> que o LangSmith calcula por chamada de LLM, somado por período</td></tr>")
    ad("<tr><td>Custo por resolução</td><td>custo total ÷ <code>session_id</code> distintos nos metadados</td></tr>")
    ad("<tr><td>Projeção por volume</td><td>custo médio por requisição × mensagens/semana × nº de usuários</td></tr>")
    ad(
        f"<tr><td>Conversão para real</td><td>{escape(cotacao['fonte'])}"
        + (f", cotação de venda de {escape(cotacao['data'])}: R$ {cotacao['venda']}" if cotacao.get("venda") else " — indisponível")
        + "</td></tr>"
    )
    ad("</table>")

    ad(
        "<footer>Relatório gerado automaticamente a partir do LangSmith. "
        "Os valores em real usam a cotação PTAX do Banco Central na data indicada.</footer>"
    )
    ad("</body></html>")

    return "".join(partes)
