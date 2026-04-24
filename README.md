# Telegram Temp Mail Bot (Python)

A Telegram bot that lets each user:

- auto-create a local account on first `/start`
- use `/mail` with an inline keyboard menu
- create a new temporary email address (nice generated username)
- list all their current temporary addresses
- delete addresses they do not want
- open inboxes and read incoming messages (including links) in Telegram

## Tech Stack

- Python 3.10+
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
- [mail.tm API](https://docs.mail.tm/)
- JSON file storage (`bot_data.json`)

## 1) Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2) Configure bot token

Copy the example config:

```bash
cp config.example.json config.json
```

Open `config.json` and set:

- `telegram_bot_token`: your Telegram bot token from BotFather

You can also change:

- `database_path`: where user/mailbox data is stored
- `mail_tm_base_url`: temp mail API base URL

## 3) Run

```bash
python bot.py
```

## Commands

- `/start` - registers user account on first use
- `/mail` - opens inline keyboard menu

## Notes

- Deleting a mailbox removes it from local storage and also tries to remove it on mail.tm.
- Inbox messages are fetched live; the bot extracts and shows HTTP/HTTPS links.
- Message bodies are truncated to keep Telegram message size safe.
