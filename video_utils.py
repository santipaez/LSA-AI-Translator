import subprocess
import os

UPLOAD_FOLDER_NAME = 'uploads' # Coincidir con app.py

def download_video_and_get_info(youtube_url, output_filename_only="video_descargado.mp4"):
    """
    Downloads a YouTube video using yt-dlp into the UPLOAD_FOLDER_NAME 
    and extracts its title and description.
    Returns (path_relative_to_uploads_folder, title, description).
    Raises RuntimeError on failure.
    """
    # Ensure the upload folder exists (aunque app.py ya lo hace, es bueno tenerlo aquí por si se usa standalone)
    os.makedirs(UPLOAD_FOLDER_NAME, exist_ok=True)

    # Ruta completa del archivo de salida dentro de la carpeta uploads
    full_output_path = os.path.join(UPLOAD_FOLDER_NAME, output_filename_only)

    # Remove previous file if exists
    if os.path.exists(full_output_path):
        try:
            os.remove(full_output_path)
        except Exception as e:
            raise RuntimeError(f"No se pudo eliminar el archivo anterior: {e}")

    # Get title and description
    command_info = [
        'yt-dlp',
        '--print', '%(title)s\n%(description)s',
        '--no-playlist',
        '--quiet',
        '--skip-download',
        youtube_url
    ]
    try:
        result = subprocess.run(command_info, capture_output=True, text=True, timeout=30, encoding='utf-8', errors='ignore')
        if result.returncode != 0:
            raise RuntimeError(f"Error al obtener información del video: {result.stderr}")
        lines = result.stdout.strip().split('\n')
        title = lines[0] if len(lines) > 0 else "Título no encontrado"
        description = "\n".join(lines[1:]) if len(lines) > 1 else "Descripción no encontrada"
    except Exception as e:
        raise RuntimeError(f"Error al extraer título/descripción: {e}")

    # Download video
    command_download = [
        'yt-dlp',
        '-o', full_output_path, # Guardar en la carpeta uploads
        '-f', 'bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/best',
        '--merge-output-format', 'mp4',
        '--no-playlist',
        '--quiet',
        youtube_url
    ]
    try:
        result = subprocess.run(command_download, capture_output=True, text=True, timeout=600)
        if result.returncode != 0 or not os.path.exists(full_output_path):
            raise RuntimeError(f"Error al descargar el video: {result.stderr}")
    except Exception as e:
        raise RuntimeError(f"Error durante la descarga del video: {e}")

    return output_filename_only, title, description # Devolver solo el nombre del archivo, ya que se asume que está en 'uploads' 