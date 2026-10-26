"""Executa um arquivo .sql no banco ou imprime o resultado de uma consulta.

Uso:
    python aplicar_sql.py sql/arquivo.sql
    python aplicar_sql.py --query "select ..."
"""
import argparse
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv


def conectar() -> psycopg.Connection:
    load_dotenv()
    url = os.getenv("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL não definida no .env")
    return psycopg.connect(url)


def aplicar_arquivo(caminho: str) -> None:
    sql = Path(caminho).read_text(encoding="utf-8")
    with conectar() as conn:
        conn.execute(sql)
    print(f"OK: {caminho} aplicado")


def imprimir_tabela(colunas: list[str], linhas: list[tuple]) -> None:
    valores = [[("" if v is None else str(v)) for v in linha] for linha in linhas]
    larguras = [max([len(c)] + [len(l[i]) for l in valores]) for i, c in enumerate(colunas)]
    print(" | ".join(c.ljust(w) for c, w in zip(colunas, larguras)))
    print("-+-".join("-" * w for w in larguras))
    for linha in valores:
        print(" | ".join(v.ljust(w) for v, w in zip(linha, larguras)))
    print(f"({len(linhas)} linha(s))")


def executar_consulta(sql: str) -> None:
    with conectar() as conn, conn.cursor() as cur:
        cur.execute(sql)
        if cur.description is None:
            print(f"OK: {cur.rowcount} linha(s) afetada(s)")
            return
        imprimir_tabela([d.name for d in cur.description], cur.fetchall())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("arquivo", nargs="?", help="arquivo .sql a executar")
    grupo.add_argument("--query", help="consulta a executar e imprimir")
    args = parser.parse_args()

    if args.query:
        executar_consulta(args.query)
    else:
        aplicar_arquivo(args.arquivo)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
