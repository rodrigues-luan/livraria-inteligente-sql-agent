"""Raspa books.toscrape.com e grava o conteúdo cru em bronze.livros (append-only).

Uso:
    python 01_scraper_bronze.py --paginas 2
"""
import argparse
import os
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin

import psycopg
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from psycopg.types.json import Jsonb

URL_LISTAGEM = "https://books.toscrape.com/catalogue/page-{n}.html"
MAX_PARALELO = 8
TIMEOUT_S = 30
HEADERS = {"User-Agent": "livraria-inteligente-scraper/1.0 (aula engenharia de contexto)"}
SQL_BRONZE = Path(__file__).parent / "sql" / "00_bronze.sql"

sessao = requests.Session()
sessao.headers.update(HEADERS)


def baixar_html(url: str) -> BeautifulSoup:
    resposta = sessao.get(url, timeout=TIMEOUT_S)
    resposta.raise_for_status()
    return BeautifulSoup(resposta.text, "html.parser")


def links_da_pagina(n: int) -> list[str]:
    url = URL_LISTAGEM.format(n=n)
    soup = baixar_html(url)
    return [urljoin(url, a["href"]) for a in soup.select("article.product_pod h3 a")]


def texto_ou_none(elemento) -> str | None:
    return elemento.get_text() if elemento else None


def tabela_produto(soup: BeautifulSoup) -> dict[str, str]:
    return {
        linha.th.get_text(): linha.td.get_text()
        for linha in soup.select("table.table tr")
        if linha.th and linha.td
    }


def classe_rating(soup: BeautifulSoup) -> str | None:
    p = soup.select_one("p.star-rating")
    return " ".join(p.get("class", [])) if p else None


def categoria_breadcrumb(soup: BeautifulSoup) -> str | None:
    links = soup.select("ul.breadcrumb a")
    return links[2].get_text() if len(links) >= 3 else None


def descricao_produto(soup: BeautifulSoup) -> str | None:
    cabecalho = soup.select_one("#product_description")
    return texto_ou_none(cabecalho.find_next_sibling("p")) if cabecalho else None


def extrair_livro(url: str) -> dict:
    soup = baixar_html(url)
    tabela = tabela_produto(soup)
    return {
        "url": url,
        "titulo": texto_ou_none(soup.select_one("div.product_main h1")),
        "preco_raw": texto_ou_none(soup.select_one("div.product_main p.price_color")),
        "rating_raw": classe_rating(soup),
        "estoque_raw": tabela.get("Availability"),
        "upc": tabela.get("UPC"),
        "n_reviews_raw": tabela.get("Number of reviews"),
        "categoria_raw": categoria_breadcrumb(soup),
        "descricao": descricao_produto(soup),
    }


def raspar(paginas: int) -> list[dict]:
    with ThreadPoolExecutor(max_workers=MAX_PARALELO) as pool:
        links = [link for lista in pool.map(links_da_pagina, range(1, paginas + 1)) for link in lista]
        print(f"{len(links)} livros encontrados em {paginas} página(s)")
        return list(pool.map(extrair_livro, links))


def gravar_bronze(livros: list[dict], execucao_id: str) -> None:
    load_dotenv()
    url = os.getenv("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL não definida no .env")
    with psycopg.connect(url) as conn:
        conn.execute(SQL_BRONZE.read_text(encoding="utf-8"))
        with conn.cursor() as cur:
            cur.executemany(
                "insert into bronze.livros (fonte_url, payload, _execucao_id) values (%s, %s, %s)",
                [(livro["url"], Jsonb(livro), execucao_id) for livro in livros],
            )
    print(f"{len(livros)} linhas gravadas em bronze.livros (execução {execucao_id})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--paginas", type=int, default=50, help="páginas da listagem (20 livros cada)")
    args = parser.parse_args()

    execucao_id = uuid.uuid4().hex[:12]
    gravar_bronze(raspar(args.paginas), execucao_id)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
