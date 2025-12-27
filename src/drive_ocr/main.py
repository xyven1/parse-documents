import argparse
import base64
import os
from collections.abc import Generator
from pathlib import Path

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import Resource, build
from googleapiclient.http import MediaIoBaseDownload
from openai import OpenAI
from pydantic import BaseModel

# ----------------------------
# Data models
# ----------------------------


class AnalysisResult(BaseModel):
    title: str
    language: str | None
    date: str | None
    type: str
    from_: str | None = None
    to: str | None = None
    text_markdown: str
    translated_markdown: str | None = None


class DocumentMetadata(BaseModel):
    title: str
    language: str | None
    date: str | None
    type: str
    from_: str | None
    to: str | None


# ----------------------------
# Google Drive
# ----------------------------

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def drive_service() -> Resource:
    creds: Credentials = Credentials.from_service_account_file(
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"],
        scopes=SCOPES,
    )
    return build("drive", "v3", credentials=creds)


class GoogleFileMetadata(BaseModel):
    id: str
    name: str
    mimeType: str


class FileMetadata(BaseModel):
    id: str
    name: str
    mimeType: str
    parents: list[str] | None = None


def list_images_recursive(
    service: Resource,
    folder_id: str,
    *,
    parents: list[str] = [],
) -> Generator[FileMetadata, None, None]:
    """Recursively list all images in a Google Drive folder."""
    query = f"'{folder_id}' in parents and trashed = false"
    page_token: str | None = None
    while True:
        resp = (
            service.files()
            .list(
                q=query,
                fields="nextPageToken, files(id, name, mimeType)",
                pageToken=page_token,
            )
            .execute()
        )

        for file in resp.get("files", []):
            mime_type: str = file.get("mimeType", "")
            if mime_type == "application/vnd.google-apps.folder":
                yield from list_images_recursive(
                    service, file["id"], parents=parents + [file["name"]]
                )
            elif mime_type.startswith("image/"):
                file_meta = GoogleFileMetadata.model_validate(file)
                yield FileMetadata(
                    id=file_meta.id,
                    name=file_meta.name,
                    mimeType=file_meta.mimeType,
                    parents=parents,
                )
        page_token = resp.get("nextPageToken")
        if not page_token:
            break


def download_file(service: Resource, file_id: str, dest: Path) -> None:
    request = service.files().get_media(fileId=file_id)
    with dest.open("wb") as f:
        downloader = MediaIoBaseDownload(f, request)
        done: bool = False
        while not done:
            _, done = downloader.next_chunk()


# ----------------------------
# OpenAI Vision
# ----------------------------


def image_to_base64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("utf-8")


def analyze_image(client: OpenAI, image_path: Path) -> AnalysisResult:
    b64: str = image_to_base64(image_path)

    prompt: str = """
You are performing OCR and document analysis.

Return a JSON object with:
- title
- language (null if English)
- date (ISO 8601 if found, else null)
- type (letter, check, telegram, drawing, unknown, etc.)
- from_ (null if not applicable)
- to (null if not applicable)
- text_markdown (faithful OCR in Markdown)
- translated_markdown (ONLY if non-English, else null)
"""

    print(f"Analyzing image '{image_path}' with OpenAI...")
    resp = client.chat.completions.create(
        model="gpt-5.2",
        messages=[
            {"role": "system", "content": "You are a precise OCR engine."},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                    },
                ],
            },
        ],
        response_format={"type": "json_object"},
    )
    content = resp.choices[0].message.content

    if content is None:
        raise ValueError("No content returned from OpenAI")

    return AnalysisResult.model_validate_json(content)


# ----------------------------
# Main
# ----------------------------


def main() -> None:
    parser = argparse.ArgumentParser()
    _ = parser.add_argument(
        "drive_folder_id", help="ID of the Google Drive folder to process"
    )
    _ = parser.add_argument("-o", "--out", default="out", help="Output folder")
    _ = parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List files without downloading or processing",
    )
    args = parser.parse_args()

    out_dir: Path = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    dry_run = bool(args.dry_run)
    drive_folder_id = str(args.drive_folder_id)

    drive = drive_service()
    client = OpenAI()

    images = [list_images_recursive(drive, drive_folder_id).__next__()]
    for file in images:
        if dry_run:
            print(f"[DRY RUN] Found image: {file}")
            continue

        doc_dir: Path = out_dir / file.id
        if not doc_dir.exists():
            doc_dir.mkdir()
        image_path = doc_dir / file.name
        metadata_path = doc_dir / "metadata.json"

        if image_path.exists():
            print(f"Image already exists, skipping download: {image_path}")
        else:
            download_file(drive, file.id, image_path)

        if metadata_path.exists():
            print(f"Metadata already exists, skipping analysis: {metadata_path}")
            continue

        analysis = analyze_image(client, image_path)

        _ = (doc_dir / "text.md").write_text(analysis.text_markdown)

        translated = analysis.translated_markdown
        if translated is not None:
            _ = (doc_dir / "translated.md").write_text(translated)

        metadata = DocumentMetadata(
            title=analysis.title,
            language=analysis.language,
            date=analysis.date,
            type=analysis.type,
            from_=analysis.from_,
            to=analysis.to,
        )

        _ = metadata_path.write_text(metadata.model_dump_json(indent=2))

        print(f"Processed: {file.name} → {doc_dir}")


if __name__ == "__main__":
    main()
