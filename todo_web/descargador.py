import os
import re
import shutil
import socket
import tempfile
import threading
import time
from io import StringIO
from ipaddress import ip_address
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote, urlsplit
from uuid import uuid4

from flask import Blueprint, Response, current_app, jsonify, render_template, request, send_from_directory, url_for
from flask_wtf.csrf import generate_csrf, validate_csrf
from wtforms.validators import ValidationError
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

app2 = Blueprint("descargas_ok", __name__)
BASE_DIR = Path(__file__).resolve().parent
CARPETA_DESCARGA = BASE_DIR / "descarga"
TEMPORALES_ANDROID = Path(tempfile.gettempdir()) / "todo4-android"
TEMP_TTL_SECONDS = 3600
CONTADORES_DESCARGAS = {"audio": 0, "video": 0}
LOCK_CONTADORES = threading.Lock()
DESCARGAS_WEB: dict[str, dict[str, object]] = {}
LOCK_DESCARGAS_WEB = threading.Lock()
CANDIDATOS_FFMPEG = (
    os.environ.get("FFMPEG_LOCATION"),
    shutil.which("ffmpeg"),
    BASE_DIR / "ffmpeg" / "bin" / "ffmpeg.exe",
    BASE_DIR / "ffmpeg" / "ffmpeg.exe",
    BASE_DIR / "ffmpeg" / "ffmpeg",
)
FFMPEG = next((str(Path(ruta).resolve()) for ruta in CANDIDATOS_FFMPEG if ruta and Path(ruta).is_file()), None)
NODE = shutil.which("node")
YT_DLP_JS_RUNTIMES = {"node": {"path": NODE}} if NODE else {"node": {}}


@app2.route("/csrf-token", methods=["GET"])
def csrf_token_app():
    respuesta = jsonify(csrf_token=generate_csrf())
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@app2.route("/server", methods=["GET"])
def listar_rutas_servidor():
    carpetas_excluidas = {".git", "__pycache__", ".venv", "venv"}
    rutas: list[dict[str, str]] = []
    for carpeta, directorios, archivos in os.walk(BASE_DIR, topdown=True, followlinks=False):
        directorios[:] = sorted(nombre for nombre in directorios if nombre not in carpetas_excluidas)
        ruta_carpeta = Path(carpeta).resolve()
        for nombre in sorted(archivos):
            nombre_minusculas = nombre.lower()
            if nombre == ".env" or "cookie" in nombre_minusculas or "secret" in nombre_minusculas or nombre.endswith(".pyc"):
                continue
            ruta_archivo = ruta_carpeta / nombre
            ruta_repo = ruta_archivo.relative_to(BASE_DIR).as_posix()
            rutas.append({"ruta": str(ruta_archivo.resolve()), "github": f"https://github.com/andresok10/todo_web/blob/main/todo_web/{quote(ruta_repo)}"})
    ruta_ffmpeg = FFMPEG or "No detectado"
    ruta_node = NODE or "No detectado"
    datos_servidor = {
        "rutas": rutas,
        "raiz": str(BASE_DIR),
        "carpeta_temporal": str(TEMPORALES_ANDROID),
        "ruta_ffmpeg": ruta_ffmpeg,
        "ruta_node": ruta_node,
    }
    if request.args.get("format") == "json":
        respuesta = jsonify(datos_servidor)
        respuesta.headers["Cache-Control"] = "no-store"
        return respuesta
    return render_template("app.html", panel="server", rutas=rutas, raiz=str(BASE_DIR), carpeta_temporal=str(TEMPORALES_ANDROID), ruta_ffmpeg=ruta_ffmpeg, ruta_node=ruta_node)


@app2.route("/descarga", methods=["POST"])
def descargax():
    es_formulario = not request.is_json

    def respuesta(estado: str, mensaje: str, codigo: int, datos: dict[str, object] | None = None) -> tuple[str | Response, int]:
        contenido: dict[str, object] = {"status": estado, "msg": mensaje}
        if datos is not None:
            contenido.update(datos)
        if es_formulario:
            return render_template(
                "app.html",
                panel="descarga_resultado",
                estado=estado,
                msg=mensaje,
                download_url=contenido.get("download_url"),
                file_name=contenido.get("file_name"),
                progreso=100 if estado == "success" else 0,
            ), codigo
        return jsonify(contenido), codigo

    try:
        token_csrf = request.headers.get("X-CSRFToken") if request.is_json else request.form.get("csrf_token")
        validate_csrf(token_csrf)
    except ValidationError:
        return respuesta("error", "Sesión vencida. Recarga la página.", 400)
    if request.is_json:
        payload: object = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return respuesta("error", "Envía un objeto JSON válido.", 400)
        data = cast(dict[str, object], payload)
    else:
        data = cast(dict[str, object], request.form.to_dict())
    destino = data.get("destination", "web")
    if not isinstance(destino, str) or destino not in ("web", "android"):
        return respuesta("error", "Destino de descarga inválido.", 400)
    url = data.get("url")
    tipo = data.get("download_type", "video")
    if not isinstance(url, str) or len(url) > 4096 or not isinstance(tipo, str) or tipo not in ("audio", "video"):
        return respuesta("error", "URL o tipo de descarga inválido.", 400)
    url = url.strip()
    try:
        partes = urlsplit(url)
        # Solo plataformas conocidas: impide usar la app para consultar servicios internos.
        host = (partes.hostname or "").lower()
        dominios = ("youtube.com", "youtu.be", "facebook.com", "fb.watch", "tiktok.com", "instagram.com", "vimeo.com")
        if partes.scheme not in ("https", "http") or partes.username or partes.password or partes.port not in (None, 80, 443):
            raise ValueError
        if not any(host == d or host.endswith("." + d) for d in dominios):
            raise ValueError
        direcciones = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        if not direcciones or any(not ip_address(item[4][0]).is_global for item in direcciones):
            raise ValueError
    except ValueError, OSError:
        return respuesta("error", "Usa una URL pública de YouTube, Facebook, TikTok, Instagram o Vimeo.", 400)
    if not FFMPEG:
        return respuesta("error", "Falta FFmpeg. Instálalo o configura FFMPEG_LOCATION con la ruta del ejecutable.", 503)
    prefijo = "audio" if tipo == "audio" else "video"

    def siguiente_numero() -> int:
        with LOCK_CONTADORES:
            maximo = CONTADORES_DESCARGAS[prefijo]
            for carpeta_existente in (CARPETA_DESCARGA, TEMPORALES_ANDROID):
                if not carpeta_existente.is_dir():
                    continue
                archivos = carpeta_existente.rglob("*") if carpeta_existente == TEMPORALES_ANDROID else carpeta_existente.iterdir()
                for archivo_existente in archivos:
                    match = re.fullmatch(rf"{prefijo}([1-9][0-9]*)\..+", archivo_existente.name)
                    if archivo_existente.is_file() and match:
                        maximo = max(maximo, int(match[1]))
            numero = maximo + 1
            CONTADORES_DESCARGAS[prefijo] = numero
            return numero

    def procesar_descarga(job_id: str | None = None) -> dict[str, object]:
        try:
            CARPETA_DESCARGA.mkdir(parents=True, exist_ok=True)
            numero = siguiente_numero()
        except OSError:
            current_app.logger.exception("No se pudo asignar el nombre consecutivo")
            return {"status": "error", "msg": "No se pudo asignar un nombre consecutivo al archivo."}

        identificador = f"{prefijo}{numero}"
        temporal = destino == "android" or os.environ.get("RENDER") == "true" or os.environ.get("TEMPORARY_DOWNLOADS") == "1"
        token = uuid4().hex if temporal else None
        carpeta = TEMPORALES_ANDROID / token if token else CARPETA_DESCARGA
        reserva = carpeta / f"{identificador}.reserve"
        cookies_buffer: StringIO | None = None
        try:
            carpeta.mkdir(parents=True, exist_ok=True)
            if token:
                for vieja in TEMPORALES_ANDROID.iterdir():
                    if re.fullmatch(r"[0-9a-f]{32}", vieja.name) and vieja.is_dir() and vieja.stat().st_mtime < time.time() - TEMP_TTL_SECONDS and not any(vieja.glob("*.reserve")):
                        shutil.rmtree(vieja, ignore_errors=True)
            reserva.touch(exist_ok=False)
            cookies_file = os.environ.get("YOUTUBE_COOKIES_FILE", "").strip()
            if cookies_file and Path(cookies_file).is_file():
                cookies_buffer = StringIO(Path(cookies_file).read_text(encoding="utf-8"))

            def progreso_yt_dlp(informacion: dict[str, object]) -> None:
                if job_id is None:
                    return
                estado_hook = informacion.get("status")
                archivo_hook = Path(str(informacion.get("filename", identificador))).name
                with LOCK_DESCARGAS_WEB:
                    job = DESCARGAS_WEB.get(job_id)
                    if job is None:
                        return
                    job["updated"] = time.time()
                    if estado_hook == "downloading":
                        actual = informacion.get("downloaded_bytes")
                        total = informacion.get("total_bytes") or informacion.get("total_bytes_estimate")
                        if isinstance(actual, (int, float)) and isinstance(total, (int, float)) and total > 0:
                            porcentaje = min(99, max(0, int(actual * 100 / total)))
                            anterior = job.get("progreso")
                            job["progreso"] = max(porcentaje, int(anterior)) if isinstance(anterior, (int, float)) else porcentaje
                            job["msg"] = f"Descargando {archivo_hook}: {job['progreso']}%"
                        else:
                            job["progreso"] = None
                            job["msg"] = f"Descargando {archivo_hook}…"
                    elif estado_hook == "finished":
                        progreso_actual = job.get("progreso")
                        progreso_entero = int(progreso_actual) if isinstance(progreso_actual, (int, float)) else 0
                        job["progreso"] = max(90, progreso_entero)
                        job["msg"] = "Preparando el archivo…"

            opciones: dict[str, Any] = {
                "outtmpl": str(carpeta / f"{identificador}.%(ext)s"),
                "noplaylist": True,
                "ffmpeg_location": FFMPEG,
                **({"cookiefile": cookies_buffer} if cookies_buffer is not None else {}),
                "js_runtimes": YT_DLP_JS_RUNTIMES,
                "quiet": True,
                "no_warnings": True,
                "socket_timeout": 30,
                "retries": 2,
                "max_filesize": 500 * 1024 * 1024,
                "format": "bestaudio/best" if tipo == "audio" else "bestvideo+bestaudio/best",
                "postprocessors": ([{"key": "FFmpegExtractAudio", "preferredcodec": "m4a"}] if tipo == "audio" else []),
                "merge_output_format": "mkv",
                "progress_hooks": [progreso_yt_dlp],
            }
            with YoutubeDL(cast(Any, opciones)) as ydl:
                ydl.extract_info(url, download=True)

            archivos = [f for f in carpeta.glob(f"{identificador}.*") if f.is_file() and f.suffix in (".m4a", ".mp4", ".mkv", ".webm", ".mov", ".flv", ".3gp", ".ogg", ".mp3")]
            if len(archivos) != 1 or archivos[0].stat().st_size == 0:
                raise DownloadError("No se generó un archivo multimedia completo.")
            archivo = archivos[0]
            nombre_normalizado = carpeta / f"{identificador}{archivo.suffix.lower()}"
            if archivo != nombre_normalizado:
                archivo.rename(nombre_normalizado)
                archivo = nombre_normalizado
            enlace_descarga = (
                f"/server/android/{token}/{quote(archivo.name)}"
                if token
                else f"/server/{quote(archivo.name)}"
            )
            return {
                "status": "success",
                "msg": f"{archivo.name} descargado",
                "download_url": enlace_descarga,
                "download_to_browser": bool(token and destino == "web"),
                "extension": archivo.suffix.lstrip("."),
                "file_name": archivo.name,
            }
        except Exception as error:
            current_app.logger.exception("Falló la descarga multimedia")
            for parcial in carpeta.glob(f"{identificador}.*"):
                if parcial.is_file():
                    try:
                        parcial.unlink(missing_ok=True)
                    except OSError:
                        current_app.logger.warning("No se pudo eliminar el archivo parcial: %s", parcial)
            if token:
                shutil.rmtree(carpeta, ignore_errors=True)
            detalle = str(error).lower()
            if isinstance(error, DownloadError) and "sign in to confirm" in detalle:
                mensaje = "YouTube bloqueó la descarga desde Render. Configura un archivo de cookies de YouTube como secreto y define YOUTUBE_COOKIES_FILE."
            else:
                mensaje = "No se pudo descargar. Comprueba el enlace, su disponibilidad y la versión de yt-dlp."
            return {"status": "error", "msg": mensaje}
        finally:
            if cookies_buffer is not None:
                cookies_buffer.close()
            try:
                reserva.unlink(missing_ok=True)
            except OSError:
                current_app.logger.warning("No se pudo retirar la reserva: %s", reserva)

    if es_formulario:
        job_id = uuid4().hex
        ahora_job = time.time()
        with LOCK_DESCARGAS_WEB:
            for id_viejo, job_viejo in list(DESCARGAS_WEB.items()):
                creado = job_viejo.get("created")
                if isinstance(creado, (int, float)) and ahora_job - creado > TEMP_TTL_SECONDS:
                    DESCARGAS_WEB.pop(id_viejo, None)
            DESCARGAS_WEB[job_id] = {
                "status": "processing",
                "msg": "Conectando y preparando la descarga…",
                "progreso": None,
                "created": ahora_job,
                "updated": ahora_job,
                "download_started": False,
            }
        aplicacion = cast(Any, current_app)._get_current_object()

        def ejecutar_descarga_web() -> None:
            try:
                with aplicacion.app_context():
                    resultado = procesar_descarga(job_id)
            except Exception:
                aplicacion.logger.exception("No se pudo finalizar la tarea de descarga web")
                resultado = {"status": "error", "msg": "No se pudo completar la descarga."}
            with LOCK_DESCARGAS_WEB:
                job = DESCARGAS_WEB.get(job_id)
                if job is not None:
                    job.update(resultado)
                    job["progreso"] = 100 if resultado.get("status") == "success" else 0
                    job["updated"] = time.time()

        threading.Thread(target=ejecutar_descarga_web, name=f"descarga-{job_id[:8]}", daemon=True).start()
        return render_template(
            "app.html",
            panel="descarga_progreso",
            estado="processing",
            msg="Conectando y preparando la descarga…",
            progreso=None,
            estado_url=url_for("descargas_ok.estado_descarga_web", job_id=job_id),
        ), 202

    resultado = procesar_descarga()
    return respuesta(
        str(resultado.get("status", "error")),
        str(resultado.get("msg", "No se pudo descargar.")),
        200 if resultado.get("status") == "success" else 502,
        {k: v for k, v in resultado.items() if k not in ("status", "msg")},
    )


@app2.route("/descarga/estado/<job_id>", methods=["GET"])
def estado_descarga_web(job_id: str):
    if not re.fullmatch(r"[0-9a-f]{32}", job_id):
        return "Descarga no encontrada.", 404
    with LOCK_DESCARGAS_WEB:
        registro = DESCARGAS_WEB.get(job_id)
        if registro is None:
            return render_template(
                "app.html",
                panel="descarga_progreso",
                estado="error",
                msg="La descarga ya no está disponible. Inicia otra descarga.",
                progreso=0,
            ), 404
        datos = dict(registro)
        url_archivo = datos.get("download_url")
        if datos.get("status") == "success" and not datos.get("download_started"):
            datos["download_started"] = True
            registro["download_started"] = True
        else:
            url_archivo = None
    return render_template(
        "app.html",
        panel="descarga_progreso",
        estado=datos.get("status", "processing"),
        msg=datos.get("msg", "Procesando descarga…"),
        progreso=datos.get("progreso"),
        estado_url=url_for("descargas_ok.estado_descarga_web", job_id=job_id),
        download_url=url_archivo,
    )


@app2.route("/server/<path:output_file>")
@app2.route("/server/android/<token>/<output_file>")
def serve_download(output_file, token=None):
    if not re.fullmatch(r"(?:audio|video)[1-9][0-9]*\.[a-z0-9]{2,5}", output_file):
        return jsonify(status="error", msg="Archivo no encontrado."), 404
    if token is not None:
        if not re.fullmatch(r"[0-9a-f]{32}", token):
            return jsonify(status="error", msg="Archivo no encontrado."), 404
        temporal = TEMPORALES_ANDROID / token
        respuesta_archivo = send_from_directory(temporal, output_file, as_attachment=True, conditional=False, max_age=0)
        respuesta_archivo.headers["Cache-Control"] = "no-store"
        respuesta_archivo.headers["X-Flask-Message"] = f"{output_file} descargado"
        # Cierra primero el archivo y elimina después la copia temporal enviada.
        respuesta_archivo.direct_passthrough = False
        limpieza = threading.Timer(30, shutil.rmtree, args=(temporal,), kwargs={"ignore_errors": True})
        limpieza.daemon = True
        respuesta_archivo.call_on_close(limpieza.start)
        return respuesta_archivo
    respuesta_archivo = send_from_directory(CARPETA_DESCARGA, output_file, as_attachment=True, conditional=True)
    respuesta_archivo.headers["X-Flask-Message"] = f"{output_file} descargado"
    return respuesta_archivo
