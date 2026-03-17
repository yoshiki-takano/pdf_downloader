import os
import re
from pathlib import Path
from typing import List, Tuple
from urllib.parse import quote

import requests
import streamlit as st


def safe_filename(text: str) -> str:
    invalid = '<>:"/\\|?*'
    out = text
    for ch in invalid:
        out = out.replace(ch, "_")
    out = re.sub(r"(?:_?\d{8})$", "", out)
    return out.strip() or "document"


def parse_guid_input(raw: str) -> List[str]:
    items = [line.strip() for line in raw.splitlines()]
    return [x for x in items if x]


def download_pdf_for_guid(url: str, headers: dict, guid: str, out_dir: Path) -> Tuple[bool, str]:
    guid_url = f"{url.rstrip('/')}/{quote(guid, safe='')}"

    try:
        resp = requests.get(guid_url, headers=headers, timeout=(10, 120))
    except requests.RequestException as exc:
        return False, f"{guid}: request error: {exc}"

    if resp.status_code >= 400:
        body = (resp.text or "").strip()
        detail = body[:300] if body else "(empty body)"
        return False, f"{guid}: status={resp.status_code}, body={detail}"

    content_type = (resp.headers.get("Content-Type") or "").lower()
    if "application/pdf" not in content_type and not resp.content.startswith(b"%PDF"):
        body = (resp.text or "").strip()
        detail = body[:300] if body else "(binary/non-text body)"
        return False, f"{guid}: non-PDF response, Content-Type={content_type}, body={detail}"

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{safe_filename(guid)}.pdf"
    out_path.write_bytes(resp.content)
    return True, f"{guid} -> {out_path}"


def run_download(api_key: str, base_url: str, guids: List[str], out_dir: Path) -> Tuple[int, int, List[str]]:
    headers = {
        "X-ApiKey": api_key,
        "Content-Type": "application/json",
        "Accept": "application/pdf, application/json",
    }

    success_count = 0
    fail_count = 0
    logs: List[str] = []

    progress = st.progress(0)
    status = st.empty()

    for i, guid in enumerate(guids, start=1):
        status.write(f"Downloading {i}/{len(guids)}: `{guid}`")
        ok, message = download_pdf_for_guid(base_url, headers, guid, out_dir)
        logs.append(message)

        if ok:
            success_count += 1
        else:
            fail_count += 1

        progress.progress(i / len(guids))

    status.write("Done")
    return success_count, fail_count, logs


def main() -> None:
    st.set_page_config(page_title="Clarivate PDF Downloader", page_icon="P", layout="centered")
    st.title("Clarivate PDF Downloader")
    st.caption("Download PDFs from GUID list and save locally")

    default_api_key = os.environ.get("IP_DATA_API", "").strip()

    with st.form("download_form"):
        api_key = st.text_input("API Key (IP_DATA_API)", value=default_api_key, type="password")
        base_url = st.text_input(
            "API URL",
            value="https://api.clarivate.com/patents/document/pdf/",
        )
        out_dir_text = st.text_input("Output directory", value="pdf_out")
        guid_text = st.text_area(
            "GUID list (one per line)",
            value="\n".join(
                [
                    "JP2005135453A_20050526",
                    "JP07589393B220241125",
                    "JP2023011735A_20230124",
                    "WO2021243294A120211202",
                ]
            ),
            height=180,
        )

        submitted = st.form_submit_button("Start download", type="primary")

    if not submitted:
        return

    if not api_key.strip():
        st.error("API Key is empty. Enter it or set IP_DATA_API in your environment.")
        return

    guids = parse_guid_input(guid_text)
    if not guids:
        st.error("GUID list is empty. Add at least one GUID.")
        return

    out_dir = Path(out_dir_text).expanduser()

    st.info(f"Targets: {len(guids)} / Output: `{out_dir}`")

    success, failed, logs = run_download(api_key.strip(), base_url.strip(), guids, out_dir)

    st.success(f"Completed: success={success}, failed={failed}")
    with st.expander("Logs", expanded=True):
        for line in logs:
            if "->" in line:
                st.write(f"[OK] {line}")
            else:
                st.write(f"[NG] {line}")


if __name__ == "__main__":
    main()
