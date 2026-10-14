"""Widget de chat reutilisable (Claude via l'API Anthropic), present sur
chaque page.

Historique de conversation partage entre toutes les pages via
``st.session_state`` (pour que la meme discussion se poursuive quand on
navigue) ; chaque page fournit son propre contexte texte (donnees/resultats
qu'elle affiche), reinjecte dans le prompt systeme a chaque appel, pour que
la reponse suivante reste ancree sur ce qui est visible a l'ecran.

La cle API est lue depuis ``st.secrets`` (``.streamlit/secrets.toml``) si
disponible, sinon depuis la variable d'environnement ``ANTHROPIC_API_KEY``.
Acces API payant (pay-as-you-go), hors abonnement Claude.ai / Claude Code.
"""

from __future__ import annotations

import os

import streamlit as st

from athlete.memory import append_conversation_summary, append_profil_note, charger_contexte_utilisateur

_MODEL_DEFAUT = "claude-sonnet-5"


def _get_api_key() -> str | None:
    try:
        cle = st.secrets.get("ANTHROPIC_API_KEY")
    except Exception:
        cle = None
    return cle or os.environ.get("ANTHROPIC_API_KEY")


def _get_client():
    api_key = _get_api_key()
    if not api_key:
        return None
    import anthropic

    return anthropic.Anthropic(api_key=api_key)


def _construire_system_prompt(contexte_page: str) -> str:
    ctx = charger_contexte_utilisateur()
    p = ctx.profil_numerique
    return (
        "Tu es un assistant qui aide Florian a analyser sa preparation "
        "triathlon (70.3 / XL, cadre polarise 80/20). Reponds en francais, "
        "de facon concise et actionnable.\n\n"
        f"Profil physiologique : FC max {p.fc_max}, FC repos {p.fc_repos}, "
        f"poids {p.poids_kg} kg, FC seuil estimee {p.fc_seuil_estime}.\n\n"
        f"Profil libre (objectifs, contraintes, preferences) :\n{ctx.profil_libre_md}\n\n"
        f"Resume des echanges passes :\n{ctx.historique_conversations_md}\n\n"
        f"Contexte de la page actuelle :\n{contexte_page}"
    )


def widget_chat(key_prefix: str, contexte_page: str) -> None:
    """A appeler une fois par page, apres calcul de ses resultats.

    ``contexte_page`` : courte chaine texte resumant ce que la page affiche
    (quelques metriques deja calculees, pas un dump de dataframe complet).
    """
    st.session_state.setdefault("chat_messages", [])

    with st.sidebar.expander("💬 Discuter avec Claude", expanded=False):
        client = _get_client()
        if client is None:
            st.warning(
                "ANTHROPIC_API_KEY non definie (variable d'environnement ou "
                "`.streamlit/secrets.toml`)."
            )
            return

        for msg in st.session_state["chat_messages"]:
            st.chat_message(msg["role"]).write(msg["content"])

        prompt = st.chat_input("Poser une question...", key=f"{key_prefix}_chat_input")
        if prompt:
            st.session_state["chat_messages"].append({"role": "user", "content": prompt})
            st.chat_message("user").write(prompt)

            system = _construire_system_prompt(contexte_page)
            with client.messages.stream(
                model=os.environ.get("ANTHROPIC_CHAT_MODEL", _MODEL_DEFAUT),
                max_tokens=1024,
                system=system,
                messages=st.session_state["chat_messages"],
            ) as stream:
                reponse = st.chat_message("assistant").write_stream(stream.text_stream)
            st.session_state["chat_messages"].append({"role": "assistant", "content": reponse})

        if st.session_state["chat_messages"]:
            if st.button("💾 Sauvegarder cette conversation dans la memoire", key=f"{key_prefix}_save_chat"):
                resume = "\n".join(
                    f"- {m['role']}: {m['content'][:300]}" for m in st.session_state["chat_messages"][-10:]
                )
                append_conversation_summary(resume, page=key_prefix)
                st.success("Ajoute a user/conversations.md")

        st.divider()
        note = st.text_input("Ajouter une note durable au profil", key=f"{key_prefix}_profil_note")
        if st.button("💾 Enregistrer la note de profil", key=f"{key_prefix}_save_note") and note:
            append_profil_note(note)
            st.success("Ajoute a user/profil.md")
