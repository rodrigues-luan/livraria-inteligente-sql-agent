"""Interface web do agente SQL.

Uso:
    streamlit run 05_app_streamlit.py
"""
import importlib

import streamlit as st
from dotenv import load_dotenv

agente = importlib.import_module("04_sql_agent")

PERGUNTAS_DO_PRD = [
    "Qual categoria tem o maior valor em estoque, em reais?",
    "Quantos livros bem avaliados custam menos de £20?",
    "Quantos livros únicos temos na base?",
    "Qual o preço médio por faixa de preço?",
]


@st.cache_resource
def carregar_llm() -> "agente.ClienteLLM":
    load_dotenv()
    return agente.ClienteLLM()


@st.cache_data(ttl=600)
def carregar_system_prompt(sem_contexto: bool) -> str:
    return agente.montar_system_prompt(sem_contexto)


def mostrar_resultado(resultado: dict) -> None:
    for numero, tentativa in enumerate(resultado["tentativas"], start=1):
        rotulo = "SQL gerado" if len(resultado["tentativas"]) == 1 else f"SQL gerado · tentativa {numero}"
        st.caption(rotulo)
        st.code(tentativa["sql"], language="sql")
        if tentativa["erro"]:
            st.warning(f"Erro: {tentativa['erro']}")
    if resultado["colunas"] is not None:
        st.caption(f"Resultado do banco ({len(resultado['linhas'])} linha(s))")
        st.dataframe([dict(zip(resultado["colunas"], linha)) for linha in resultado["linhas"]], hide_index=True)
    st.markdown(resultado["resposta"])


def main() -> None:
    st.set_page_config(page_title="Livraria Inteligente", page_icon="📚")
    st.title("📚 Livraria Inteligente")

    with st.sidebar:
        sem_contexto = st.toggle("Sem contexto (comparação da aula)", value=False)
        st.caption("Perguntas do PRD")
        exemplo = next((p for p in PERGUNTAS_DO_PRD if st.button(p, use_container_width=True)), None)
        if st.button("Limpar conversa", type="secondary"):
            st.session_state.clear()
            st.rerun()

    llm = carregar_llm()
    st.caption(f"{llm.provedor}/{llm.modelo} · {'SEM' if sem_contexto else 'COM'} contexto")

    if st.session_state.get("sem_contexto") != sem_contexto:
        st.session_state.update(sem_contexto=sem_contexto, historico=[], conversa=[])

    for pergunta, resultado in st.session_state.conversa:
        with st.chat_message("user"):
            st.markdown(pergunta)
        with st.chat_message("assistant"):
            mostrar_resultado(resultado)

    pergunta = st.chat_input("Pergunte sobre o catálogo...") or exemplo
    if not pergunta:
        return

    with st.chat_message("user"):
        st.markdown(pergunta)
    with st.chat_message("assistant"):
        with st.spinner("Consultando o banco..."):
            resultado = agente.perguntar(
                llm, carregar_system_prompt(sem_contexto), st.session_state.historico,
                pergunta, bloquear_bronze=not sem_contexto,
            )
        mostrar_resultado(resultado)
    st.session_state.conversa.append((pergunta, resultado))


if __name__ == "__main__":
    main()
