# Escopo do Ceris e contrato da Cerita

Este documento descreve o que o código atual permite afirmar. Ele não substitui
a política de privacidade, os termos do produto nem uma decisão de produto.

## O que o app e a IA fazem

- O app organiza estoque doméstico, listas, receitas salvas, eventos, locais,
  leitura de código de barras e leitura de nota fiscal.
- A Cerita responde dúvidas sobre o app, consulta estoque e validade, sugere
  receitas e ajuda com eventos e listas.
- A inclusão de produtos no estoque é feita pelas telas do app, inclusive pelos
  fluxos de código de barras e nota fiscal. O chat não cadastra produtos.
- Uma receita pode considerar o estoque, exigir explicitamente itens do estoque
  ou ignorá-lo quando a pessoa pedir. O agente não deve declarar disponibilidade
  sem evidência do estoque.
- Alterações de domínio passam por autorização antes da persistência. Se a
  validação negar, for ambígua ou falhar, a ferramenta de escrita não deve
  executar a operação.

## Fontes da FAQ

`scripts/bases/NexUs_FAQs.json` é a fonte canônica para a FAQ vetorial. O script
`scripts/qdrant_injection.py` envia seus pares de pergunta e resposta à coleção
`nexus_faqs`, com a resposta pura nos metadados.

`scripts/bases/NexUs_FAQs.md` e os documentos técnicos não são fontes de
recuperação para o agente de FAQ. O retriever consulta apenas `nexus_faqs`; uma
resposta ausente não deve ser completada por uma seção do manual ou por
conhecimento geral do modelo.

## Memória e isolamento

- A conversa ativa é persistida no MongoDB com `account_id` e `session_id`.
- A consulta de histórico exige ambos e a escolha de sessão recente é limitada
  à conta autenticada.
- O prompt recebe uma janela limitada de mensagens para controlar custo. O
  recorte do prompt não exclui mensagens salvas. A receita ou assunto ativo
  pode ser transportado em campos estruturados do histórico.
- Ao encerrar a sessão, um resumo pode ser gravado no Qdrant com o identificador
  da conta. A busca de memória filtra por essa conta; resumos de sessões
  anteriores da mesma conta podem ser recuperados intencionalmente.
- Não há um único saver global que compartilhe a memória entre contas.

## Afirmações que precisam de confirmação do produto

O código confirma o uso de provedores de modelo e de serviços de armazenamento;
quando tracing está habilitado, também há envio de traces ao LangSmith. A
resposta da FAQ sobre compartilhamento de dados e o texto de privacidade do app
devem explicar esse processamento com base na política oficial. Não afirmar
“nenhum compartilhamento com terceiros” sem essa validação.

No mobile, encontrei permissão e canais de notificação do Android, mas não uma
tela de preferências da conta para escolher notificações. A FAQ deve orientar a
pessoa a usar as configurações do aparelho até o produto confirmar outro fluxo.

Os contatos de suporte aparecem no JSON, mas a revisão de saída mascara
endereços de e-mail e telefones. O fluxo de suporte precisa ser confirmado e
testado antes de prometer que a Cerita consegue entregar esses contatos.

Não declare conformidade legal, prazo de retenção, política de venda ou exclusão
de dados sem correspondência com os documentos oficiais e com as rotas
disponíveis no produto.
