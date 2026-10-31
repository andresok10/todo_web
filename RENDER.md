# Publicar Todo en Render

Publica esta carpeta `todo_web` como raíz de un repositorio de GitHub. Las carpetas `todo_android` y `todo_render` son clientes Android y no se suben como backend de Render.

## Despliegue

1. Crea un repositorio y sube los archivos de esta carpeta, incluidos Dockerfile, requirements.txt, render.yaml, templates y static. No subas ffmpeg de Windows, descarga, contadores.sqlite3 ni archivos .env.
2. En Render elige New > Blueprint y conecta ese repositorio. Render encontrará render.yaml, instalará FFmpeg para Linux y Deno para yt-dlp, y arrancará Flask con Gunicorn.
3. Si usas New > Web Service: selecciona Docker, Dockerfile Path `./Dockerfile`, Docker Context `.` y deja Docker Command vacío. Configura SECRET_KEY con un valor aleatorio y TEMPORARY_DOWNLOADS=1. El Dockerfile configura FFmpeg y el puerto automáticamente.
4. Abre la URL HTTPS que Render asigne. Verifica Calculadoras, Descargas y Calendario.
5. Usa esa misma URL en los dos clientes Android mediante las propiedades Gradle `flaskBaseUrl` (todo_android) y `webBaseUrl` (todo_render), y vuelve a generar sus APK. El usuario no necesita escribir el servidor en pantalla.

## Archivos y estado

En Render el servidor genera el archivo temporal, lo envía y elimina su copia al cerrar la respuesta. Los temporales abandonados de más de una hora se limpian en la siguiente solicitud temporal. No se provisiona un disco ni un servicio de pago con este Blueprint.

El contador SQLite es pequeño, pero en el disco efímero puede reiniciarse al recrearse o desplegarse el servicio. Para mantener la numeración global entre despliegues hace falta almacenar ese contador en una base persistente; no es necesario conservar los vídeos o audios.

## Diseño compartido

La web sirve static/todo-compacto.css y static/todo-compacto.js. El cliente WebView todo_render incluye una copia para aplicar el mismo diseño cuando termine de cargar la página. Ejecuta el script `../sincronizar_diseno.ps1` después de editar los estilos o la navegación. El cliente nativo todo_android usa la misma paleta y distribución con Compose.
