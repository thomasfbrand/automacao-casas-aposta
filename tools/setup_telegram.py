"""Assistente do Telegram: configura TUDO e grava no .env.

  python -m tools.setup_telegram

O que ele faz, em ordem:
  1. cria o .env (a partir do .env.example) se ainda não existir;
  2. pede o api_id e o api_hash (https://my.telegram.org) e grava no .env;
  3. faz o login da sua conta (Telegram manda o código para o app; se tiver senha de 2 etapas, ele pede);
  4. procura o grupo das tips (Soltaram Bets / Betador Machine) entre os seus chats e deixa você escolher;
  5. lê as últimas mensagens do grupo e mostra quantas ele reconheceria como tip (confirma que está no grupo certo);
  6. grava TG_CHANNEL no .env e manda um "robô conectado" nas suas Mensagens Salvas.

O login e o código são digitados por VOCÊ no terminal; nada disso passa por outro lugar.
"""
import asyncio
import re
import shutil
import sys
from pathlib import Path

from telethon import TelegramClient

from bot.tip_parser import is_cancel, parse_tip

ENV = Path(".env")
KEYWORDS = ("soltaram", "betador", "machine", "bet a dor", "betadormachine")


def ensure_env() -> None:
    if not ENV.exists():
        example = Path(".env.example")
        if example.exists():
            shutil.copy(example, ENV)
        else:
            ENV.write_text("", encoding="utf-8")
        print("• .env criado")


def get_env(key: str) -> str:
    for line in ENV.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return ""


def set_env(key: str, value: str) -> None:
    lines = ENV.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            break
    else:
        lines.append(f"{key}={value}")
    ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")


def ask_credentials() -> tuple[int, str]:
    api_id, api_hash = get_env("TG_API_ID"), get_env("TG_API_HASH")
    if api_id.isdigit() and re.fullmatch(r"[0-9a-fA-F]{32}", api_hash or ""):
        print(f"• usando api_id {api_id} já gravado no .env")
        return int(api_id), api_hash
    print("\nPasso 1/4 — credenciais do Telegram")
    print("  Abra https://my.telegram.org → 'API development tools' → crie o app e copie os dois valores.")
    while True:
        api_id = input("  api_id (só números): ").strip()
        if api_id.isdigit():
            break
        print("  → precisa ser um número.")
    while True:
        api_hash = input("  api_hash (32 caracteres): ").strip()
        if re.fullmatch(r"[0-9a-fA-F]{32}", api_hash):
            break
        print("  → precisa ter 32 caracteres (letras a-f e números).")
    set_env("TG_API_ID", api_id)
    set_env("TG_API_HASH", api_hash)
    print("  ✓ gravado no .env")
    return int(api_id), api_hash


async def find_group(client: TelegramClient):
    print("\nPasso 3/4 — achando o grupo das tips")
    dialogs = [d async for d in client.iter_dialogs()]
    matches = [d for d in dialogs if any(k in (d.name or "").lower() for k in KEYWORDS)]
    pool = matches
    if not matches:
        print("  Não achei nenhum chat com 'soltaram', 'betador' ou 'machine' no nome.")
        term = input("  Digite parte do nome do grupo: ").strip().lower()
        pool = [d for d in dialogs if term and term in (d.name or "").lower()]
    if not pool:
        print("  Nenhum chat encontrado. Confirme que a sua conta está no grupo e rode de novo.")
        sys.exit(1)
    print()
    for n, d in enumerate(pool, 1):
        kind = "canal" if d.is_channel and not d.is_group else "grupo" if d.is_group else "chat"
        user = getattr(d.entity, "username", None)
        print(f"  [{n}] {d.name}  ({kind}{', @' + user if user else ''})  id={d.id}")
    if len(pool) == 1:
        choice = pool[0]
        print("  → único resultado, vou usar ele.")
    else:
        while True:
            raw = input("  Qual é o das tips? número: ").strip()
            if raw.isdigit() and 1 <= int(raw) <= len(pool):
                choice = pool[int(raw) - 1]
                break
    return choice


async def sanity_check(client: TelegramClient, dialog) -> None:
    print("\nPasso 4/4 — conferindo as últimas mensagens do grupo")
    msgs = await client.get_messages(dialog, limit=40)
    tips = cancels = other = 0
    for m in msgs:
        text = m.raw_text or ""
        if is_cancel(text):
            cancels += 1
        elif parse_tip(text).ok:
            tips += 1
        else:
            other += 1
    print(f"  Das últimas {len(msgs)} mensagens: {tips} tips válidas (Live/over), {cancels} cancelamentos, {other} outras.")
    for m in msgs[:3]:
        first = (m.raw_text or "").strip().splitlines()[:1]
        print("   •", (first[0][:70] if first else "(sem texto)"))
    if tips == 0:
        print("  ⚠️ Nenhuma tip reconhecida nas últimas mensagens. Pode ser que o grupo esteja parado ou que o")
        print("     formato tenha mudado. Se este for o grupo certo, siga em frente e me mande um exemplo.")


async def main() -> None:
    ensure_env()
    api_id, api_hash = ask_credentials()
    session = get_env("TG_SESSION") or "tg_session"
    print("\nPasso 2/4 — login no Telegram (o código chega no app do Telegram)")
    client = TelegramClient(session, api_id, api_hash)
    await client.start()
    me = await client.get_me()
    print(f"  ✓ conectado como {me.first_name or ''} (@{me.username or 'sem username'})")

    dialog = await find_group(client)
    await sanity_check(client, dialog)

    set_env("TG_CHANNEL", str(dialog.id))
    set_env("TG_NOTIFY", "me")
    print(f"\n✓ TG_CHANNEL={dialog.id} gravado no .env")
    try:
        await client.send_message("me", "✅ Robô de apostas conectado ao Telegram. Avisos chegam aqui (Mensagens Salvas).")
        print("✓ mandei um teste nas suas Mensagens Salvas — confira no app.")
    except Exception as exc:
        print("  (não consegui mandar o teste:", exc, ")")
    await client.disconnect()
    print("\nPronto. O arquivo", f"{session}.session", "guarda o seu login: NÃO compartilhe.")


if __name__ == "__main__":
    asyncio.run(main())
