# Fairground Form Tester

Isolated Playwright automation for `https://fairground.fi/421614/rewards`.

The only piece adapted from the uploaded PudgyWorld bot is the IMAP mail helper. The rest of the project is new and standalone.

## Setup

```bash
cd ~/fairground-form-tester
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env
chmod 600 .env
```

Edit `.env`:

```bash
FAIRGROUND_PRIVATE_KEY=0x...
FAIRGROUND_EMAIL_DATA=mail@example.com:imap_app_password
```

`FAIRGROUND_EMAIL_DATA` also supports an alias format:

```bash
FAIRGROUND_EMAIL_DATA=login@example.com:imap_app_password:alias@example.com
```

## Run

```bash
. .venv/bin/activate
python -m fairground_tester.main
```

For visual debugging:

```bash
FAIRGROUND_HEADLESS=false python -m fairground_tester.main --headed --debug
```

To check only wallet connection without entering email:

```bash
python -m fairground_tester.main --stop-after-wallet
```

## Mail Database

Import a `login:password:alias` mail list into SQLite:

```bash
python scripts/import_mails.py data/mails.txt
```

The database is stored at `data/accounts.db`.

If a run fails, the script writes:

- `artifacts/failure.png`
- `artifacts/failure.html`

## Notes

- Private keys and email credentials are only read from `.env`; they are not stored in source files.
- The wallet is injected into the page as an EIP-1193 provider and can sign `personal_sign`, `eth_sign`, and typed-data requests.
- The default chain id is Arbitrum Sepolia: `421614` / `0x66eee`.
- The script intentionally does not support `eth_sendTransaction`.
- If Cloudflare Turnstile blocks the email step, the script stops with a clear diagnostic instead of waiting for an email that was never sent.
