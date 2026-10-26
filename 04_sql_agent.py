"""Agente SQL: responde em português perguntas de negócio consultando prata e ouro.

Uso:
    python 04_sql_agent.py                      # loop interativo (sair: Enter vazio)
    python 04_sql_agent.py --pergunta "..."     # uma pergunta e sai
    python 04_sql_agent.py --sem-contexto       # sem CONTEXTO.md, schema de todas as tabelas
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from aplicar_sql import conectar, imprimir_tabela

CAMINHO_CONTEXTO = Path(__file__).parent / "download" / "CONTEXTO.md"
SCHEMAS_DO_AGENTE = ["prata", "ouro"]
SCHEMAS_DE_SISTEMA = [
    "pg_catalog", "information_schema", "pg_toast", "auth", "storage", "realtime",
    "extensions", "graphql", "graphql_public", "vault", "pgsodium", "pgsodium_masks",
    "net", "supabase_functions", "supabase_migrations", "cron", "pgbouncer",
]
MAX_TENTATIVAS = 3
LIMITE_LINHAS = 50
TIMEOUT_CONSULTA = "10s"
MODELO_PADRAO = {"anthropic": "claude-opus-5-5"}

INSTRUCOES_AGENTE = f"""Você é o agente SQL da Livraria Inteligente e atende a diretoria comercial.
- Responda perguntas de negócio consultando um banco PostgreSQL.
- Use SOMENTE as views dos schemas `prata` e `ouro`. Nunca consulte `bronze`.
- Prefira `ouro` quando a métrica já estiver pronta lá.
- Gere exatamente UM comando SELECT (ou WITH ... SELECT) por vez, dentro de um bloco ```sql```.
- Siga à risca as regras de negócio e métricas do CONTEXTO.md abaixo.
- O resultado será limitado a {LIMITE_LINHAS} linhas; agregue no SQL quando precisar de totais.
- Se a pergunta for ambígua, NÃO gere SQL: faça uma pergunta de esclarecimento curta.
- Depois de receber o resultado, responda em português, de forma direta, com o número certo e a moeda.
- Se alguém perguntar algo fora do contexto de livros e do livraria, NÃO responda, apenas direcione para qual pergunta você pode responder"""

INSTRUCAO_MINIMA = """Você é um agente SQL. Gere um SELECT PostgreSQL num bloco ```sql``` para responder a pergunta.
Depois de receber o resultado, responda em português."""


def ler_schema(schemas: list[str] | None) -> str:
    sql = """
        select table_schema, table_name, column_name, data_type
        from information_schema.columns
        where {filtro}
        order by table_schema, table_name, ordinal_position
    """
    with conectar() as conn:
        if schemas:
            linhas = conn.execute(sql.format(filtro="table_schema = any(%s)"), [schemas]).fetchall()
        else:
            filtro = "table_schema <> all(%s) and table_schema not like 'pg\\_%%'"
            linhas = conn.execute(sql.format(filtro=filtro), [SCHEMAS_DE_SISTEMA]).fetchall()

    tabelas: dict[str, list[str]] = {}
    for schema, tabela, coluna, tipo in linhas:
        tabelas.setdefault(f"{schema}.{tabela}", []).append(f"{coluna} {tipo}")
    return "\n".join(f"- {nome}({', '.join(colunas)})" for nome, colunas in tabelas.items())


def montar_system_prompt(sem_contexto: bool) -> str:
    if sem_contexto:
        return f"{INSTRUCAO_MINIMA}\n\n# Schema do banco\n{ler_schema(None)}"
    contexto = CAMINHO_CONTEXTO.read_text(encoding="utf-8")
    schema = ler_schema(SCHEMAS_DO_AGENTE)
    return f"{INSTRUCOES_AGENTE}\n\n# CONTEXTO.md\n{contexto}\n\n# Schema real (prata e ouro)\n{schema}"


class ClienteLLM:
    def __init__(self) -> None:
        self.provedor = os.getenv("LLM_PROVIDER", "anthropic").lower()
        self.modelo = os.getenv("LLM_MODEL") or MODELO_PADRAO.get(self.provedor)
        if self.provedor not in ("anthropic", "openai"):
            sys.exit("LLM_PROVIDER deve ser 'anthropic' ou 'openai'")
        if not self.modelo:
            sys.exit(f"Defina LLM_MODEL no .env para o provedor {self.provedor}")
        if self.provedor == "anthropic":
            import anthropic
            self.cliente = anthropic.Anthropic()
        else:
            import openai
            self.cliente = openai.OpenAI()

    def responder(self, system: str, mensagens: list[dict]) -> str:
        if self.provedor == "anthropic":
            return self._responder_anthropic(system, mensagens)
        return self._responder_openai(system, mensagens)

    def _responder_anthropic(self, system: str, mensagens: list[dict]) -> str:
        resposta = self.cliente.messages.create(
            model=self.modelo,
            max_tokens=16000,
            cache_control={"type": "ephemeral"},
            system=system,
            messages=mensagens,
        )
        if resposta.stop_reason == "refusal":
            return "(o modelo recusou a solicitação)"
        return "".join(b.text for b in resposta.content if b.type == "text")

    def _responder_openai(self, system: str, mensagens: list[dict]) -> str:
        resposta = self.cliente.chat.completions.create(
            model=self.modelo,
            messages=[{"role": "system", "content": system}, *mensagens],
        )
        return resposta.choices[0].message.content or ""


def extrair_sql(texto: str) -> str | None:
    blocos = re.findall(r"```sql\s*(.*?)```", texto, flags=re.DOTALL | re.IGNORECASE)
    return blocos[0].strip() if blocos else None


def remover_comentarios(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return re.sub(r"--[^\n]*", " ", sql)


def validar_sql(sql: str, bloquear_bronze: bool) -> str:
    """Devolve o SQL limpo ou levanta ValueError com o motivo."""
    limpo = remover_comentarios(sql).strip().rstrip(";").strip()
    if ";" in limpo:
        raise ValueError("Envie apenas UM comando SQL.")
    if not re.match(r"(?is)^(select|with)\b", limpo):
        raise ValueError("Só são permitidos comandos SELECT ou WITH.")
    if bloquear_bronze and re.search(r"(?i)\bbronze\s*\.", limpo):
        raise ValueError("O schema bronze é proibido. Use apenas prata e ouro.")
    return limpo


def executar_somente_leitura(sql: str) -> tuple[list[str], list[tuple]]:
    with conectar() as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute(f"set local statement_timeout = '{TIMEOUT_CONSULTA}'")
            cur.execute(f"select * from (\n{sql}\n) as consulta limit {LIMITE_LINHAS}")
            colunas = [d.name for d in cur.description]
            linhas = cur.fetchall()
        conn.rollback()
    return colunas, linhas


def resultado_para_llm(colunas: list[str], linhas: list[tuple]) -> str:
    registros = [dict(zip(colunas, linha)) for linha in linhas]
    return json.dumps(registros, ensure_ascii=False, default=str)


def perguntar(llm: ClienteLLM, system: str, historico: list[dict], pergunta: str, bloquear_bronze: bool) -> dict:
    """Devolve {tentativas: [{sql, erro}], colunas, linhas, resposta}; colunas é None se nenhum SQL rodou."""
    historico.append({"role": "user", "content": pergunta})
    resultado = {"tentativas": [], "colunas": None, "linhas": None, "resposta": None}

    for _ in range(MAX_TENTATIVAS):
        texto = llm.responder(system, historico)
        historico.append({"role": "assistant", "content": texto})

        sql = extrair_sql(texto)
        if sql is None:
            resultado["resposta"] = texto
            return resultado

        tentativa = {"sql": sql, "erro": None}
        resultado["tentativas"].append(tentativa)
        try:
            colunas, linhas = executar_somente_leitura(validar_sql(sql, bloquear_bronze))
        except (ValueError, psycopg.Error) as erro:
            tentativa["erro"] = str(erro)
            historico.append({"role": "user", "content": f"A consulta falhou com o erro abaixo. Corrija e envie um novo SQL.\n{erro}"})
            continue

        historico.append({
            "role": "user",
            "content": f"Resultado da consulta (JSON):\n{resultado_para_llm(colunas, linhas)}\n\n"
                       "Responda a pergunta original em português, sem gerar SQL.",
        })
        resposta = llm.responder(system, historico)
        historico.append({"role": "assistant", "content": resposta})
        resultado.update(colunas=colunas, linhas=linhas, resposta=resposta)
        return resultado

    resultado["resposta"] = f"Não consegui uma consulta válida em {MAX_TENTATIVAS} tentativas."
    return resultado


def responder_pergunta(llm: ClienteLLM, system: str, historico: list[dict], pergunta: str, bloquear_bronze: bool) -> None:
    resultado = perguntar(llm, system, historico, pergunta, bloquear_bronze)
    for numero, tentativa in enumerate(resultado["tentativas"], start=1):
        print(f"\n🧾 SQL gerado (tentativa {numero}):\n{tentativa['sql']}")
        if tentativa["erro"]:
            print(f"\n⚠️  Erro: {tentativa['erro']}")
    if resultado["colunas"] is not None:
        print("\n📊 Resultado:")
        imprimir_tabela(resultado["colunas"], resultado["linhas"])
    print(f"\n💬 {resultado['resposta']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sem-contexto", action="store_true", help="sem CONTEXTO.md; schema de todas as tabelas")
    parser.add_argument("--pergunta", help="responde uma única pergunta e sai")
    args = parser.parse_args()

    load_dotenv()
    llm = ClienteLLM()
    system = montar_system_prompt(args.sem_contexto)
    bloquear_bronze = not args.sem_contexto
    modo = "SEM contexto" if args.sem_contexto else "COM contexto"
    print(f"Agente SQL · {llm.provedor}/{llm.modelo} · {modo}")

    historico: list[dict] = []
    if args.pergunta:
        responder_pergunta(llm, system, historico, args.pergunta, bloquear_bronze)
        return

    while pergunta := input("\n❓ Pergunta: ").strip():
        responder_pergunta(llm, system, historico, pergunta, bloquear_bronze)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
