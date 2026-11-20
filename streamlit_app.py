"""
Optional minimal web UI.   Run:  streamlit run streamlit_app.py
It uses exactly the same agent as main.py — only the display is different.
"""

import streamlit as st

from helpdesk.agent import ask

st.set_page_config(page_title="Nimbus Helpdesk", page_icon="💬")
st.title("💬 Nimbus HR/IT Helpdesk")
st.caption("Ask about leave, work from home, IT, expenses, conduct, or a leave balance (e.g. E102).")

# st.session_state survives page re-runs, so we keep the chat history there.
if "history" not in st.session_state:
    st.session_state.history = []

for role, text in st.session_state.history:
    st.chat_message(role).markdown(text)

if question := st.chat_input("Type your question..."):
    st.chat_message("user").markdown(question)
    with st.spinner("Thinking..."):
        try:
            result = ask(question)
            answer = result["answer"]
        except Exception as e:
            result, answer = None, f"Sorry, something went wrong: {e}"
    st.chat_message("assistant").markdown(answer)
    if result:
        with st.expander("Details (tools & guardrails)"):
            st.json({"tools": result["tool_log"], "guardrails": result["notes"]})
    st.session_state.history += [("user", question), ("assistant", answer)]
