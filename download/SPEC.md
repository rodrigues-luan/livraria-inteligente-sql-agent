# SPEC.md · Como construir, etapa por etapa

> Execute **uma etapa por vez**, só quando pedido. Regras de negócio (R1–R7, M1–M4) e dicionário estão no **CONTEXTO.md**.

```
books.toscrape.com ──► bronze.livros ──► prata.livros ──► ouro.livros / ouro.categorias ──► agente SQL
     (Etapa 1)            (cru)            (Etapa 2)              (Etapa 3)                   (Etapa 4)
```

---

## Etapa 1 · Scraping → bronze
**Entrega:** `requirements.txt`, `.env.exemplo`, `sql/00_bronze.sql`, `01_scraper_bronze.py`, `aplicar_sql.py`

Requisitos
- Tabela `bronze.livros` (`id bigserial`, `fonte_url text`, `payload jsonb`, `_execucao_id text`, `_ingestao_em timestamptz default now()`).
- Raspar a **página de detalhe** de cada livro (a listagem não tem UPC nem estoque). Campos do `payload`: ver CONTEXTO.md §2.
- **Bronze é cru:** grava os textos exatamente como vieram. Nenhuma limpeza.
- **Append-only:** cada execução insere de novo, sem upsert.
- Parâmetro `--paginas N` (20 livros por página). Até 8 requisições em paralelo, com `User-Agent` próprio.
- Conexão via `DATABASE_URL` do `.env`. O script cria a tabela se ela não existir.
- `aplicar_sql.py`: utilitário que **o próprio agente usa** nas etapas seguintes.
  `python aplicar_sql.py sql/arquivo.sql` executa o arquivo; `python aplicar_sql.py --query "select ..."` imprime o resultado.

Critérios de aceite
- `python 01_scraper_bronze.py --paginas 2` grava 40 linhas.
- Rodar 2× → `select count(*), count(distinct payload->>'upc') from bronze.livros` = 80 e 40.
- `select payload from bronze.livros limit 3` mostra os textos crus (`£`/`Â£`, `star-rating Three`, `In stock (N available)`).

---

## Etapa 2 · Prata
**Entrega:** `sql/01_prata.sql` (view `prata.livros`), aplicado no banco pelo agente: `python aplicar_sql.py sql/01_prata.sql`

Requisitos
- Aplicar **R1 a R7** do CONTEXTO.md, com `-- R<n>` em cada linha que aplica regra.
- Colunas exatamente como no dicionário (CONTEXTO.md §4).

Critérios de aceite
- `count(*) = count(distinct upc)`.
- Nenhum `preco_gbp`, `rating` ou `estoque_qtd` nulo.
- Nenhuma categoria `Default` ou `Add a comment`.

---

## Etapa 3 · Ouro
**Entrega:** `sql/02_ouro.sql` (views `ouro.livros` e `ouro.categorias`), aplicado com `python aplicar_sql.py sql/02_ouro.sql`

Requisitos
- Métricas **M1 a M4** do CONTEXTO.md.
- `ouro.livros` = prata + `valor_estoque_gbp`, `faixa_preco`, `bem_avaliado`.
- `ouro.categorias` = 1 linha por categoria (colunas no dicionário).

Critérios de aceite
- `sum(qtd_titulos)` em `ouro.categorias` = `count(*)` em `prata.livros`.
- `faixa_preco` só tem os 3 valores definidos em M3.

---

## Etapa 4 · Agente SQL
**Entrega:** `04_sql_agent.py`

Requisitos
- Loop: pergunta → LLM gera **um** SQL em bloco ` ```sql ` → executa → LLM responde em português.
- **Contexto do agente (o coração da etapa):** o system prompt é montado a cada execução com
  1. instruções do agente (papel, só prata/ouro, um SELECT por vez, perguntar se ambíguo);
  2. **o `CONTEXTO.md` inteiro**, lido do disco;
  3. o **schema real** de `prata` e `ouro`, lido do `information_schema`.
- Flag `--sem-contexto`: só a instrução mínima + o schema de **todas** as tabelas (para comparar em aula).
- Guardrails: só `SELECT`/`WITH`, transação `read only`, `statement_timeout` de 10 s, `limit 50`, até 3 tentativas com o erro devolvido ao LLM.
- Provedor e modelo por `.env`: `LLM_PROVIDER` (openai|anthropic), `LLM_MODEL`.
- Imprimir o SQL gerado, o resultado e a resposta.

Critérios de aceite
- Acerta as 4 perguntas do PRD com o contexto ligado.
- Nunca consulta `bronze` com o contexto ligado.
