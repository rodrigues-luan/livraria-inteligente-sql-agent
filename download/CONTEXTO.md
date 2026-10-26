# CONTEXTO.md · Memória viva do projeto

> **Leia este arquivo antes de qualquer tarefa.** Ele vence o SPEC e o PRD em caso de conflito. **Atualize ao final de cada etapa** (§1 e §5). O agente SQL também lê este arquivo inteiro.

## 1\. Estado do projeto

| etapa | status | observação |
| :---- | :---- | :---- |
| 1 · Scraping → bronze | ✅ feito (22/10) | `--paginas 2` 2× → 80 linhas / 40 UPCs; payload cru (`Â£`, `star-rating …`, `In stock (N available)`). Em 26/10 a bronze tem 1.080 linhas / 1.000 UPCs (carga completa + testes) → prata e ouro com 1.000 livros |
| 2 · Prata | ✅ feito (22/10) | view `prata.livros` (R1–R7): 40 linhas = 40 UPCs; 0 nulos em preço/rating/estoque; 0 `Default`/`Add a comment` |
| 3 · Ouro | ✅ feito (22/10) | views `ouro.livros` (M1–M3) e `ouro.categorias`: Σ`qtd_titulos` = 40 = prata; `faixa_preco` só com os 3 valores de M3 |
| 4 · Agente SQL | ✅ feito (26/10) | `anthropic/claude-opus-5-5`, com contexto: acertou as 4 perguntas do PRD (Nonfiction R$ 231.287,47 · 75 livros · 1.000 únicos · £14,80 / £30,06 / £49,91), conferidas direto no banco; nenhuma consulta à bronze |

&nbsp;

**Próximo passo:** projeto completo. Opcional: comparar com `--sem-contexto` em aula\.
## 2\. Fonte de dados: books.toscrape.com

- Site público feito para treinar scraping. 50 páginas × 20 livros \= 1.000 livros.  
- Listagem: `https://books.toscrape.com/catalogue/page-{n}.html` → links em `article.product_pod h3 a`.  
- Detalhe do livro: título em `div.product_main h1`; preço em `div.product_main p.price_color`; avaliação na classe de `p.star-rating` (ex.: `star-rating Three`); tabela `table.table` com `UPC`, `Availability`, `Number of reviews`; categoria no 3º link de `ul.breadcrumb`.  
- **Encoding:** o site não declara charset. Com `requests`, o `£` costuma chegar como `Â£`. Na bronze isso fica como veio; R2 resolve na prata.  
- Campos do `payload` na bronze: `url`, `titulo`, `preco_raw`, `rating_raw`, `estoque_raw`, `upc`, `n_reviews_raw`, `categoria_raw`, `descricao`.

## 3\. Regras de negócio

**Bronze → prata**

- **R1 · Chave e duplicidade:** chave \= `upc`. Manter só a linha com o `_ingestao_em` mais recente.  
- **R2 · Preço:** extrair só o número de `preco_raw` → `preco_gbp numeric(10,2)`. Moeda \= libra (GBP).  
- **R3 · Avaliação:** `star-rating One..Five` → `rating` 1..5.  
- **R4 · Estoque:** de `In stock (22 available)` extrair `22` → `estoque_qtd int`. Sem número \= 0\.  
- **R5 · Reviews:** `n_reviews_raw` → `n_reviews int`.  
- **R6 · Categoria:** `Default` e `Add a comment` não são categorias → `Sem categoria`.  
- **R7 · Texto:** remover espaços nas pontas.

**Métricas (ouro)**

- **M1 · Valor em estoque** \= `preco_gbp × estoque_qtd`.  
- **M2 · Bem avaliado** \= `rating >= 4`.  
- **M3 · Faixa de preço:** `até £20` (\< 20\) · `£20–40` (20 a \< 40\) · `acima de £40` (≥ 40).  
- **M4 · Moeda das respostas:** GBP. Se pedirem reais, usar o câmbio de §5. Rankings de categoria **excluem** `Sem categoria`, salvo pedido explícito.

## 4\. Dicionário de dados

**prata.livros** (1 linha \= 1 livro): `upc` · `titulo` · `categoria` · `preco_gbp` · `rating` · `estoque_qtd` · `n_reviews` · `url` · `_ingestao_em`

**ouro.livros:** prata \+ `valor_estoque_gbp` (M1) · `faixa_preco` (M3) · `bem_avaliado` (M2, bool)

**ouro.categorias** (1 linha \= 1 categoria): `categoria` · `qtd_titulos` · `preco_medio_gbp` · `rating_medio` · `estoque_unidades` · `valor_estoque_gbp` · `pct_bem_avaliados`

## 5\. Decisões

| data | decisão | motivo | quem |
| :---- | :---- | :---- | :---- |
| 08/10 | Bronze append-only; dedup só na prata | preservar o que veio de cada execução | Eng. Dados |
| 08/10 | Prata e ouro como views | base pequena, sempre atualizada | Eng. Dados |
| 08/10 | Câmbio fixo **£1 \= R\$ 7,20** | relatório da diretoria em reais (valor fictício da aula) | Financeiro |
| 08/10 | Agente SQL só lê `prata` e `ouro` | bronze tem lixo e duplicidade | Eng. Dados |
| 26/10 | Interface Streamlit (`05_app_streamlit.py`) sobre o mesmo agente | pedido do usuário; amplia o PRD, que deixava interface web fora | Usuário |
| 22/10 | Código na raiz do projeto; `.md` de contexto ficam em `download/` | estrutura do AGENTS.md §3 | Agente |
| 22/10 | `DATABASE_URL` = conexão direta (`db.<ref>.supabase.co:5432`, sslmode=require) | `.env` só tinha a senha; conexão direta (IPv6) funcionou | Agente |
| 22/10 | `rating_raw` guarda a classe inteira (`star-rating Three`); `_execucao_id` = uuid curto por execução | bronze crua, rastreável por execução | Agente |
| 22/10 | R1: empate de `_ingestao_em` desempata por `id` desc | mesma execução pode repetir o timestamp | Agente |
| 22/10 | R2: preço extraído por regex numérica, ignorando `£`/`Â£` | encoding do site varia | Agente |
| 22/10 | `ouro.categorias` **inclui** `Sem categoria`; a exclusão de M4 é feita na consulta de ranking | Σ`qtd_titulos` precisa bater com a prata | Agente |
| 22/10 | `ouro.categorias`: médias com 2 casas; `pct_bem_avaliados` em % (0–100, 1 casa) | leitura direta pela diretoria | Agente |
| 22/10 | Bronze carregada com as 50 páginas (1.080 linhas; prata = 1.000 livros) | perguntas do PRD sobre a base completa | Agente |
| 22/10 | Agente: `limit 50` aplicado envolvendo o SQL numa subconsulta; bronze bloqueada por regex só com contexto ligado | guardrail não depende do LLM; `--sem-contexto` serve de comparação | Agente |
| 22/10 | Agente: modelo padrão `claude-opus-5-5` quando `LLM_PROVIDER=anthropic` e `LLM_MODEL` vazio; flag extra `--pergunta` para rodar uma pergunta só | facilitar o teste de aceite | Agente |

&nbsp;

## 6\. Pendências

- Guardar histórico de preço (SCD2)? → fora do escopo de hoje.