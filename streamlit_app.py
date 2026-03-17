import os
import re
import io
import zipfile
from typing import List, Optional, Tuple
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


def fetch_pdf_for_guid(
    url: str, headers: dict, guid: str
) -> Tuple[bool, str, Optional[bytes], Optional[str]]:
    guid_url = f"{url.rstrip('/')}/{quote(guid, safe='')}"

    try:
        resp = requests.get(guid_url, headers=headers, timeout=(10, 120))
    except requests.RequestException as exc:
        return False, f"{guid}: request error: {exc}", None, None

    if resp.status_code >= 400:
        body = (resp.text or "").strip()
        detail = body[:300] if body else "(empty body)"
        return False, f"{guid}: status={resp.status_code}, body={detail}", None, None

    content_type = (resp.headers.get("Content-Type") or "").lower()
    if "application/pdf" not in content_type and not resp.content.startswith(b"%PDF"):
        body = (resp.text or "").strip()
        detail = body[:300] if body else "(binary/non-text body)"
        return (
            False,
            f"{guid}: non-PDF response, Content-Type={content_type}, body={detail}",
            None,
            None,
        )

    filename = f"{safe_filename(guid)}.pdf"
    return True, f"{guid} -> {filename}", resp.content, filename


def run_download(
    api_key: str, base_url: str, guids: List[str]
) -> Tuple[int, int, List[str], List[Tuple[str, bytes]]]:
    headers = {
        "X-ApiKey": api_key,
        "Content-Type": "application/json",
        "Accept": "application/pdf, application/json",
    }

    success_count = 0
    fail_count = 0
    logs: List[str] = []
    files: List[Tuple[str, bytes]] = []

    progress = st.progress(0)
    status = st.empty()

    for i, guid in enumerate(guids, start=1):
        status.write(f"Downloading {i}/{len(guids)}: `{guid}`")
        ok, message, pdf_bytes, filename = fetch_pdf_for_guid(base_url, headers, guid)
        logs.append(message)

        if ok and pdf_bytes is not None and filename is not None:
            success_count += 1
            files.append((filename, pdf_bytes))
        else:
            fail_count += 1

        progress.progress(i / len(guids))

    status.write("Done")
    return success_count, fail_count, logs, files


def build_zip_bytes(files: List[Tuple[str, bytes]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for filename, data in files:
            zf.writestr(filename, data)
    return buffer.getvalue()


def main() -> None:
    st.set_page_config(page_title="Clarivate PDF Downloader", page_icon="P", layout="centered")
    st.title("Clarivate PDF Downloader")
    st.caption("Download PDFs from GUID list and save locally")

    default_api_key = os.environ.get("IP_DATA_API", "").strip()
    base_url = os.environ.get(
        "PATENT_PDF_API_URL", "https://api.clarivate.com/patents/document/pdf/"
    ).strip()

    with st.form("download_form"):
        api_key = st.text_input("API Key", value=default_api_key, type="password")
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

    st.info(f"Targets: {len(guids)}")

    success, failed, logs, files = run_download(api_key.strip(), base_url, guids)

    st.success(f"Completed: success={success}, failed={failed}")
    if files:
        zip_data = build_zip_bytes(files)
        st.download_button(
            label=f"Download ZIP ({len(files)} files)",
            data=zip_data,
            file_name="clarivate_pdfs.zip",
            mime="application/zip",
            type="primary",
        )

    with st.expander("Logs", expanded=True):
        for line in logs:
            if "->" in line:
                st.write(f"[OK] {line}")
            else:
                st.write(f"[NG] {line}")


if __name__ == "__main__":
    main()
