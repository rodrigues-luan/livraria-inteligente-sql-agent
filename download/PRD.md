# PRD.md · Livraria Inteligente

## Problema
A diretoria da livraria (fictícia, com catálogo do books.toscrape.com) quer saber **o que tem em catálogo, quanto vale o estoque e o que vende bem avaliado**. Hoje, cada pergunta vira um pedido ao time de dados, que demora dias.

## Objetivo
Uma base confiável, atualizada por scraping, e um **agente que responde em português** perguntas de negócio consultando essa base.

## Usuários
| quem | precisa de |
|---|---|
| Diretoria comercial | resposta rápida, em português, com o número certo |
| Time de dados | pipeline simples de manter e reexecutar |

## Perguntas que o produto PRECISA responder
1. Qual categoria tem o maior valor em estoque, em reais?
2. Quantos livros bem avaliados custam menos de £20?
3. Quantos livros únicos temos na base?
4. Qual o preço médio por faixa de preço?

## Escopo
- **Dentro:** scraping do catálogo, camadas bronze/prata/ouro no Supabase, agente SQL de linha de comando.
- **Fora:** interface web, agendamento, histórico de preço, vendas (o site não tem).

## Métricas de sucesso
- O agente acerta as **4 perguntas** acima.
- A prata não tem duplicidade: `count(*) = count(distinct upc)`.
- O pipeline roda de novo sem quebrar nada (idempotente).
- O agente **nunca** lê a bronze.
