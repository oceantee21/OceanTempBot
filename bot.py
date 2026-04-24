from __future__ import annotations

import html
import logging
from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from config import load_config
from storage import JsonStorage, Mailbox
from tempmail_client import MailTmClient, TempMailError

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
LOGGER = logging.getLogger(__name__)

MENU_CB = "menu:home"
NEW_MAILBOX_CB = "menu:new_mailbox"
LIST_MAILBOXES_CB = "menu:list_mailboxes"
DELETE_PICK_CB = "menu:delete_pick"
INBOX_PICK_CB = "menu:inbox_pick"


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Create New Email", callback_data=NEW_MAILBOX_CB)],
            [InlineKeyboardButton("List My Emails", callback_data=LIST_MAILBOXES_CB)],
            [InlineKeyboardButton("Open Inbox", callback_data=INBOX_PICK_CB)],
            [InlineKeyboardButton("Delete Email", callback_data=DELETE_PICK_CB)],
        ]
    )


def back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Back to /mail menu", callback_data=MENU_CB)]]
    )


def mailbox_picker_kb(prefix: str, addresses: list[str]) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(addr, callback_data=f"{prefix}:{addr}")] for addr in addresses]
    buttons.append([InlineKeyboardButton("Back to menu", callback_data=MENU_CB)])
    return InlineKeyboardMarkup(buttons)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    storage: JsonStorage = context.application.bot_data["storage"]
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return

    _, created = storage.ensure_user(
        telegram_user_id=user.id,
        telegram_chat_id=chat.id,
        username=user.username,
        first_name=user.first_name,
    )

    if created:
        text = (
            "Welcome! Your account has been created.\n\n"
            "Use /mail to manage your temporary emails and open inboxes."
        )
    else:
        text = "Welcome back! Use /mail to open the mailbox menu."

    await update.message.reply_text(text)


async def mail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return
    storage: JsonStorage = context.application.bot_data["storage"]
    storage.ensure_user(user.id, chat.id, user.username, user.first_name)

    await update.message.reply_text("Mailbox menu:", reply_markup=main_menu_kb())


async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()

    user = query.from_user
    storage: JsonStorage = context.application.bot_data["storage"]
    tempmail: MailTmClient = context.application.bot_data["tempmail"]
    record = storage.get_user(user.id)
    if not record:
        # Safety net in case user skipped /start.
        chat = update.effective_chat
        if chat:
            record, _ = storage.ensure_user(user.id, chat.id, user.username, user.first_name)
        else:
            return

    if query.data == MENU_CB:
        await query.edit_message_text("Mailbox menu:", reply_markup=main_menu_kb())
        return

    if query.data == NEW_MAILBOX_CB:
        await handle_new_mailbox(query, storage, tempmail, user.id, user.username)
        return

    if query.data == LIST_MAILBOXES_CB:
        await handle_list_mailboxes(query, record.mailboxes)
        return

    if query.data == DELETE_PICK_CB:
        await handle_delete_picker(query, record.mailboxes)
        return

    if query.data == INBOX_PICK_CB:
        await handle_inbox_picker(query, record.mailboxes)
        return

    if query.data.startswith("delete:"):
        address = query.data.split(":", 1)[1]
        await handle_delete(query, storage, tempmail, user.id, address)
        return

    if query.data.startswith("inbox:"):
        address = query.data.split(":", 1)[1]
        await handle_inbox_list(query, storage, tempmail, user.id, address)
        return

    if query.data.startswith("msg:"):
        _, address, message_id = query.data.split(":", 2)
        await handle_message_read(query, storage, tempmail, user.id, address, message_id)
        return


async def handle_new_mailbox(
    query,
    storage: JsonStorage,
    tempmail: MailTmClient,
    telegram_user_id: int,
    username: str | None,
) -> None:
    try:
        address, password, account_id = await tempmail.create_account(username)
    except TempMailError as exc:
        await query.edit_message_text(
            f"Could not create a temp mailbox:\n{exc}",
            reply_markup=back_kb(),
        )
        return

    storage.add_mailbox(
        telegram_user_id,
        Mailbox(
            address=address,
            password=password,
            account_id=account_id,
            created_at=datetime.now(timezone.utc).isoformat(),
        ),
    )
    await query.edit_message_text(
        f"New temporary email created:\n`{address}`",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=back_kb(),
    )


async def handle_list_mailboxes(query, mailboxes: list[Mailbox]) -> None:
    if not mailboxes:
        await query.edit_message_text(
            "You do not have any temporary emails yet.",
            reply_markup=back_kb(),
        )
        return

    lines = ["Your temporary emails:"]
    for idx, mailbox in enumerate(mailboxes, start=1):
        lines.append(f"{idx}. {mailbox.address}")
    await query.edit_message_text("\n".join(lines), reply_markup=back_kb())


async def handle_delete_picker(query, mailboxes: list[Mailbox]) -> None:
    if not mailboxes:
        await query.edit_message_text(
            "No emails to delete yet.",
            reply_markup=back_kb(),
        )
        return
    addresses = [m.address for m in mailboxes]
    await query.edit_message_text(
        "Select an email to delete:",
        reply_markup=mailbox_picker_kb("delete", addresses),
    )


async def handle_inbox_picker(query, mailboxes: list[Mailbox]) -> None:
    if not mailboxes:
        await query.edit_message_text(
            "Create an email first, then open its inbox.",
            reply_markup=back_kb(),
        )
        return
    addresses = [m.address for m in mailboxes]
    await query.edit_message_text(
        "Select an inbox to open:",
        reply_markup=mailbox_picker_kb("inbox", addresses),
    )


async def handle_delete(
    query,
    storage: JsonStorage,
    tempmail: MailTmClient,
    telegram_user_id: int,
    address: str,
) -> None:
    user = storage.get_user(telegram_user_id)
    if not user:
        await query.edit_message_text("User record missing.", reply_markup=back_kb())
        return

    mailbox = next((m for m in user.mailboxes if m.address == address), None)
    if not mailbox:
        await query.edit_message_text("Mailbox not found.", reply_markup=back_kb())
        return

    storage.delete_mailbox(telegram_user_id, address)
    if mailbox.account_id:
        try:
            await tempmail.delete_account(mailbox.address, mailbox.password, mailbox.account_id)
        except TempMailError:
            # Local deletion still succeeds; remote deletion is best-effort.
            pass

    await query.edit_message_text(f"Deleted `{address}`.", parse_mode=ParseMode.MARKDOWN, reply_markup=back_kb())


async def handle_inbox_list(
    query,
    storage: JsonStorage,
    tempmail: MailTmClient,
    telegram_user_id: int,
    address: str,
) -> None:
    user = storage.get_user(telegram_user_id)
    if not user:
        await query.edit_message_text("User record missing.", reply_markup=back_kb())
        return

    mailbox = next((m for m in user.mailboxes if m.address == address), None)
    if not mailbox:
        await query.edit_message_text("Mailbox not found.", reply_markup=back_kb())
        return

    try:
        messages = await tempmail.list_messages(mailbox.address, mailbox.password)
    except TempMailError as exc:
        await query.edit_message_text(
            f"Failed to fetch inbox:\n{exc}",
            reply_markup=back_kb(),
        )
        return

    if not messages:
        await query.edit_message_text(
            f"Inbox for `{address}` is empty.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=back_kb(),
        )
        return

    buttons = []
    for msg in messages[:10]:
        short_subject = (msg.subject[:35] + "...") if len(msg.subject) > 38 else msg.subject
        label = f"{short_subject} ({msg.sender})"
        buttons.append(
            [InlineKeyboardButton(label, callback_data=f"msg:{address}:{msg.id}")]
        )
    buttons.append([InlineKeyboardButton("Back to menu", callback_data=MENU_CB)])
    await query.edit_message_text(
        f"Inbox for `{address}`:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def handle_message_read(
    query,
    storage: JsonStorage,
    tempmail: MailTmClient,
    telegram_user_id: int,
    address: str,
    message_id: str,
) -> None:
    user = storage.get_user(telegram_user_id)
    if not user:
        await query.edit_message_text("User record missing.", reply_markup=back_kb())
        return

    mailbox = next((m for m in user.mailboxes if m.address == address), None)
    if not mailbox:
        await query.edit_message_text("Mailbox not found.", reply_markup=back_kb())
        return

    try:
        details = await tempmail.get_message(mailbox.address, mailbox.password, message_id)
    except TempMailError as exc:
        await query.edit_message_text(
            f"Failed to read message:\n{exc}",
            reply_markup=back_kb(),
        )
        return

    body = details.text.strip() or details.html.strip() or "(empty body)"
    if len(body) > 2500:
        body = body[:2500] + "\n...(truncated)"

    lines = [
        f"<b>From:</b> {html.escape(details.sender)}",
        f"<b>Subject:</b> {html.escape(details.subject)}",
        "",
        html.escape(body),
    ]
    if details.links:
        lines.append("")
        lines.append("<b>Links found:</b>")
        for link in details.links:
            safe_link = html.escape(link)
            lines.append(f"- <a href=\"{safe_link}\">{safe_link}</a>")

    text = "\n".join(lines)

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=False,
        reply_markup=InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Back to menu", callback_data=MENU_CB)],
                [InlineKeyboardButton("Back to inbox list", callback_data=f"inbox:{address}")],
            ]
        ),
    )


def run() -> None:
    cfg = load_config("config.json")
    storage = JsonStorage(cfg.database_path)
    tempmail = MailTmClient(cfg.mail_tm_base_url)

    app = Application.builder().token(cfg.telegram_bot_token).build()
    app.bot_data["storage"] = storage
    app.bot_data["tempmail"] = tempmail

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("mail", mail))
    app.add_handler(CallbackQueryHandler(callbacks))

    LOGGER.info("Bot is running.")
    app.run_polling()


if __name__ == "__main__":
    run()
