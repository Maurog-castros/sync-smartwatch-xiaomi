from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

from health_agent_bridge.export_archive import export_file_sha256
from health_agent_bridge.whatsapp_sync_state import WhatsAppSyncState


def _require_playwright():
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise SystemExit(
            "Playwright no instalado. Ejecuta:\n"
            "  pip install -r requirements-automation.txt\n"
            "  playwright install chromium"
        ) from error
    return sync_playwright, PlaywrightTimeoutError


def _is_logged_in(page) -> bool:
    selectors = (
        '[data-testid="chat-list"]',
        '#pane-side',
        'div[aria-label="Chat list"]',
    )
    for selector in selectors:
        try:
            if page.locator(selector).first.is_visible(timeout=3000):
                return True
        except Exception:
            continue
    return False


def _open_self_chat(page, chat_title: str, playwright_timeout) -> None:
    time.sleep(2)
    direct_selectors = (
        f'#pane-side span[title*="{chat_title}"]',
        '#pane-side span:has-text("(Tú)")',
        '#pane-side span:has-text("(You)")',
        f'[data-testid="cell-frame-container"]:has-text("{chat_title}")',
        f'span[dir="auto"][title*="{chat_title}"]',
    )
    for selector in direct_selectors:
        locator = page.locator(selector).first
        try:
            if locator.is_visible(timeout=3000):
                locator.click()
                return
        except playwright_timeout:
            continue

    search_selectors = (
        '[data-testid="chat-list-search"]',
        'div[contenteditable="true"][data-tab="3"]',
        'div[title="Buscar un chat o iniciar uno nuevo"]',
        'div[aria-label="Buscar un chat o iniciar uno nuevo"]',
        'div[role="textbox"][contenteditable="true"]',
    )
    search_box = None
    for selector in search_selectors:
        locator = page.locator(selector).first
        try:
            if locator.is_visible(timeout=2000):
                search_box = locator
                break
        except playwright_timeout:
            continue
    if search_box is None:
        page.screenshot(path="storage/logs/whatsapp-debug.png", full_page=True)
        raise RuntimeError(
            "No se encontro la barra de busqueda de WhatsApp Web. "
            "Screenshot: storage/logs/whatsapp-debug.png"
        )

    search_box.click()
    search_box.fill(chat_title)
    time.sleep(1.5)

    chat_patterns = (
        re.compile(re.escape(chat_title), re.I),
        re.compile(r"\(Tú\)", re.I),
        re.compile(r"\(You\)", re.I),
    )
    for pattern in chat_patterns:
        candidate = page.get_by_role("listitem").filter(has_text=pattern).first
        try:
            if candidate.is_visible(timeout=3000):
                candidate.click()
                return
        except playwright_timeout:
            continue

    page.locator(f'span[title*="{chat_title}"]').first.click(timeout=10000)


def _find_latest_zip_locator(page, filename: str, playwright_timeout):
    candidates = (
        page.locator(f'span[title="{filename}"]'),
        page.get_by_text(filename, exact=True),
        page.locator(f'span:has-text("{filename}")'),
    )
    for locator in candidates:
        try:
            count = locator.count()
        except Exception:
            continue
        if count > 0:
            return locator.nth(count - 1)
    raise RuntimeError(f"No se encontro ningun mensaje con archivo {filename}")


def _click_download(page, zip_locator, playwright_timeout) -> None:
    zip_locator.scroll_into_view_if_needed(timeout=10000)
    zip_locator.click(timeout=10000)
    time.sleep(0.5)

    download_selectors = (
        '[data-icon="download"]',
        'span[data-icon="download"]',
        'button[aria-label*="Descargar"]',
        'button[aria-label*="Download"]',
        '[title="Descargar"]',
        '[title="Download"]',
    )
    for selector in download_selectors:
        button = page.locator(selector).last
        try:
            if button.is_visible(timeout=2000):
                button.click()
                return
        except playwright_timeout:
            continue

    # Fallback: click the document bubble itself.
    zip_locator.click(timeout=10000)


def download_export_zip(
    *,
    profile_dir: Path,
    storage_dir: Path,
    chat_title: str,
    filename: str,
    headless: bool,
    timeout_seconds: int,
) -> dict[str, object]:
    sync_playwright, playwright_timeout = _require_playwright()
    profile_dir.mkdir(parents=True, exist_ok=True)
    incoming_dir = storage_dir / "incoming"
    incoming_dir.mkdir(parents=True, exist_ok=True)
    target_zip = storage_dir / filename
    temp_zip = incoming_dir / filename
    state_path = storage_dir / "whatsapp_sync_state.json"
    state = WhatsAppSyncState.load(state_path)

    if temp_zip.exists():
        temp_zip.unlink()

    launch_kwargs: dict[str, object] = {
        "user_data_dir": str(profile_dir),
        "headless": headless,
        "accept_downloads": True,
        "downloads_path": str(incoming_dir),
        "viewport": {"width": 1440, "height": 960},
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
        ],
    }
    browser_channel = os.environ.get("PLAYWRIGHT_BROWSER_CHANNEL", "chrome")
    browser_executable = os.environ.get("PLAYWRIGHT_BROWSER_EXECUTABLE")
    if browser_executable:
        launch_kwargs["executable_path"] = browser_executable
    else:
        launch_kwargs["channel"] = browser_channel

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(**launch_kwargs)
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(timeout_seconds * 1000)
        page.goto("https://web.whatsapp.com/", wait_until="domcontentloaded")
        time.sleep(3)

        if not _is_logged_in(page):
            if headless:
                context.close()
                raise RuntimeError(
                    "WhatsApp Web no tiene sesion activa. Ejecuta primero:\n"
                    "  python scripts/whatsapp_download_export.py --login"
                )
            print(
                "Escanea el codigo QR en la ventana del navegador. "
                "La sesion quedara guardada para los cron jobs.",
                file=sys.stderr,
            )
            page.wait_for_selector('[data-testid="chat-list"], #pane-side', timeout=180000)

        _open_self_chat(page, chat_title, playwright_timeout)
        zip_locator = _find_latest_zip_locator(page, filename, playwright_timeout)
        message_label = zip_locator.inner_text(timeout=5000).strip()

        with page.expect_download(timeout=timeout_seconds * 1000) as download_info:
            _click_download(page, zip_locator, playwright_timeout)
        download = download_info.value
        download.save_as(str(temp_zip))
        context.close()

    if not temp_zip.exists() or temp_zip.stat().st_size == 0:
        raise RuntimeError("La descarga de WhatsApp no genero un archivo valido")

    file_hash = export_file_sha256(temp_zip)
    if (
        state.last_download_sha256 == file_hash
        and state.last_download_size == temp_zip.stat().st_size
    ):
        return {
            "downloaded": False,
            "skip_reason": "whatsapp_file_unchanged",
            "target_zip": str(target_zip),
            "sha256": file_hash,
            "message_label": message_label,
        }

    shutil.copy2(temp_zip, target_zip)
    state.last_download_path = str(target_zip)
    state.last_download_sha256 = file_hash
    state.last_download_size = temp_zip.stat().st_size
    state.last_message_label = message_label
    state.last_sync_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    state.save(state_path)

    return {
        "downloaded": True,
        "skip_reason": None,
        "target_zip": str(target_zip),
        "sha256": file_hash,
        "size_bytes": temp_zip.stat().st_size,
        "message_label": message_label,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download Apple Health export zip from WhatsApp Web self chat.",
    )
    parser.add_argument("--profile-dir", type=Path, default=Path("storage/whatsapp-playwright-profile"))
    parser.add_argument("--storage-dir", type=Path, default=Path("storage"))
    parser.add_argument(
        "--chat-title",
        default=os.environ.get("WHATSAPP_SELF_CHAT_TITLE", "Mauro Castro Pers"),
    )
    parser.add_argument(
        "--filename",
        default=os.environ.get("WHATSAPP_EXPORT_FILENAME", "exportar.zip"),
    )
    parser.add_argument("--login", action="store_true", help="Open headed browser to scan QR once.")
    parser.add_argument("--headless", action="store_true", default=False)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    args = parser.parse_args()

    headless = args.headless and not args.login
    result = download_export_zip(
        profile_dir=args.profile_dir,
        storage_dir=args.storage_dir,
        chat_title=args.chat_title,
        filename=args.filename,
        headless=headless,
        timeout_seconds=args.timeout_seconds,
    )
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
