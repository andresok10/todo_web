import os
import re
import shutil
import socket
import sqlite3
import tempfile
import time
from contextlib import closing
from ipaddress import ip_address
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit
from uuid import uuid4

from flask import Blueprint, current_app, jsonify, request, send_from_directory, url_for
from flask_wtf.csrf import generate_csrf, validate_csrf
from wtforms.validators import ValidationError
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

app2 = Blueprint("descargas_ok", __name__)
BASE_DIR = Path(__file__).resolve().parent
CARPETA_DESCARGA = BASE_DIR / "descarga"
TEMPORALES_ANDROID = Path(tempfile.gettempdir()) / "todo4-android"
TEMP_TTL_SECONDS = 3600


@app2.route("/csrf-token", methods=["GET"])
def csrf_token_app():
    respuesta = jsonify(csrf_token=generate_csrf())
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@app2.route("/descarga", methods=["POST"])
def descargax():
    try:
        validate_csrf(request.headers.get("X-CSRFToken"))
    except ValidationError:
        return jsonify(status="error", msg="Sesión vencida. Recarga la página."), 400
    payload: object = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(status="error", msg="Envía un objeto JSON válido."), 400
    data = cast(dict[str, object], payload)
    destino = data.get("destination", "web")
    if not isinstance(destino, str) or destino not in ("web", "android"):
        return jsonify(status="error", msg="Destino de descarga inválido."), 400
    url = data.get("url")
    tipo = data.get("download_type", "video")
    if not isinstance(url, str) or len(url) > 4096 or not isinstance(tipo, str) or tipo not in ("audio", "video"):
        return jsonify(status="error", msg="URL o tipo de descarga inválido."), 400
    url = url.strip()
    try:
        partes = urlsplit(url)
        # Solo plataformas conocidas: impide usar la app para consultar servicios internos.
        host = (partes.hostname or "").lower()
        dominios = ("youtube.com", "youtu.be", "facebook.com", "fb.watch", "tiktok.com", "instagram.com", "vimeo.com")
        if (
            partes.scheme not in ("https", "http")
            or partes.username
            or partes.password
            or partes.port not in (None, 80, 443)
        ):
            raise ValueError
        if not any(host == d or host.endswith("." + d) for d in dominios):
            raise ValueError
        direcciones = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        if not direcciones or any(not ip_address(item[4][0]).is_global for item in direcciones):
            raise ValueError
    except (ValueError, OSError):
        return jsonify(status="error", msg="Usa una URL pública de YouTube, Facebook, TikTok, Instagram o Vimeo."), 400
    candidatos = [
        os.environ.get("FFMPEG_LOCATION"),
        shutil.which("ffmpeg"),
        BASE_DIR / "ffmpeg" / "bin" / "ffmpeg.exe",
        BASE_DIR / "ffmpeg" / "ffmpeg.exe",
        BASE_DIR / "ffmpeg" / "ffmpeg",
    ]
    ffmpeg = next((str(Path(c)) for c in candidatos if c and Path(c).is_file()), None)
    if not ffmpeg:
        return jsonify(
            status="error", msg="Falta FFmpeg. Instálalo o configura FFMPEG_LOCATION con la ruta del ejecutable."
        ), 503
    CARPETA_DESCARGA.mkdir(parents=True, exist_ok=True)
    prefijo = "audio" if tipo == "audio" else "video"
    numeros = [int(m[1]) for f in CARPETA_DESCARGA.iterdir()
               if (m := re.fullmatch(rf"{prefijo}([1-9][0-9]*)\..+", f.name))]
    # Guarda la numeración aunque el archivo temporal de Android se elimine.
    with closing(sqlite3.connect(BASE_DIR / "contadores.sqlite3", timeout=30)) as conexion, conexion:
        conexion.execute("CREATE TABLE IF NOT EXISTS contadores (tipo TEXT PRIMARY KEY, numero INTEGER NOT NULL)")
        conexion.execute("BEGIN IMMEDIATE")
        anterior = conexion.execute("SELECT numero FROM contadores WHERE tipo = ?", (prefijo,)).fetchone()
        numero = max(max(numeros, default=0), anterior[0] if anterior else 0) + 1
        conexion.execute("INSERT INTO contadores VALUES (?, ?) ON CONFLICT(tipo) DO UPDATE SET numero=excluded.numero", (prefijo, numero))
    identificador = f"{prefijo}{numero}"
    temporal = destino == "android" or os.environ.get("RENDER") == "true" or os.environ.get("TEMPORARY_DOWNLOADS") == "1"
    token = uuid4().hex if temporal else None
    carpeta = TEMPORALES_ANDROID / token if token else CARPETA_DESCARGA
    carpeta.mkdir(parents=True, exist_ok=True)
    if token:
        for vieja in TEMPORALES_ANDROID.iterdir():
            if re.fullmatch(r"[0-9a-f]{32}", vieja.name) and vieja.is_dir() and vieja.stat().st_mtime < time.time() - TEMP_TTL_SECONDS and not any(vieja.glob("*.reserve")):
                shutil.rmtree(vieja, ignore_errors=True)
    reserva = carpeta / f"{identificador}.reserve"
    reserva.touch(exist_ok=False)
    try:
        with YoutubeDL(
            {
                "outtmpl": str(carpeta / f"{identificador}.%(ext)s"),
                "noplaylist": True,
                "ffmpeg_location": ffmpeg,
                "quiet": True,
                "no_warnings": True,
                "socket_timeout": 30,
                "retries": 2,
                "max_filesize": 500 * 1024 * 1024,
                "format": "bestaudio/best" if tipo == "audio" else "bestvideo+bestaudio/best",
                "postprocessors": ([{"key": "FFmpegExtractAudio", "preferredcodec": "m4a"}] if tipo == "audio" else []),
                "merge_output_format": "mkv",
            }
        ) as ydl:
            ydl.extract_info(url, download=True)
        archivos = [
            f
            for f in carpeta.glob(f"{identificador}.*")
            if f.is_file() and f.suffix in (".m4a", ".mp4", ".mkv", ".webm", ".mov", ".flv", ".3gp", ".ogg", ".mp3")
        ]
        if len(archivos) != 1 or archivos[0].stat().st_size == 0:
            raise DownloadError("No se generó un archivo multimedia completo.")
        archivo = archivos[0]
        return jsonify(
            status="success",
            msg=f"Descarga lista: {archivo.name}" if token else f"Archivo guardado en: {archivo}",
            download_url=url_for(
                "descargas_ok.serve_download", output_file=archivo.name, token=token
            ),
            download_to_browser=bool(token and destino == "web"),
            extension=archivo.suffix.lstrip("."),
            file_name=archivo.name,
        )
    except (DownloadError, OSError):
        current_app.logger.exception("Falló la descarga multimedia")
        for parcial in carpeta.glob(f"{identificador}.*"):
            if parcial.is_file():
                try:
                    parcial.unlink(missing_ok=True)
                except OSError:
                    current_app.logger.warning("No se pudo eliminar el archivo parcial: %s", parcial)
        if token:
            shutil.rmtree(carpeta, ignore_errors=True)
        return jsonify(
            status="error", msg="No se pudo descargar. Comprueba el enlace, su disponibilidad y la versión de yt-dlp."
        ), 502
    finally:
        try:
            reserva.unlink(missing_ok=True)
        except OSError:
            current_app.logger.warning("No se pudo retirar la reserva: %s", reserva)


@app2.route("/server/<path:output_file>")
@app2.route("/server/android/<token>/<output_file>")
def serve_download(output_file, token=None):
    if not re.fullmatch(r"(?:audio|video)[1-9][0-9]*\.[a-z0-9]{2,5}", output_file):
        return jsonify(status="error", msg="Archivo no encontrado."), 404
    if token is not None:
        if not re.fullmatch(r"[0-9a-f]{32}", token):
            return jsonify(status="error", msg="Archivo no encontrado."), 404
        temporal = TEMPORALES_ANDROID / token
        respuesta = send_from_directory(temporal, output_file, as_attachment=True, conditional=False, max_age=0)
        respuesta.headers["Cache-Control"] = "no-store"
        # Cierra primero el archivo y elimina después la copia temporal enviada.
        respuesta.direct_passthrough = False
        respuesta.call_on_close(lambda: shutil.rmtree(temporal, ignore_errors=True))
        return respuesta
    return send_from_directory(CARPETA_DESCARGA, output_file, as_attachment=True, conditional=True)
