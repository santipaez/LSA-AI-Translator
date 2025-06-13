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

def incrustar_subtitulos_moviepy(video_path, srt_path, output_path=None):
    """
    Incrusta subtítulos SRT en un video usando MoviePy.
    Si output_path no se especifica, genera uno automáticamente.
    Devuelve la ruta del video generado.
    """
    try:
        from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip
        from moviepy.video.tools.subtitles import SubtitlesClip
        import pysrt
    except ImportError as e:
        raise RuntimeError(f"Error importando librerías de MoviePy: {e}. Asegúrate de que moviepy esté instalado.")
    
    if not output_path:
        base, ext = os.path.splitext(video_path)
        output_path = f"{base}_con_subtitulos{ext}"
    
    try:
        # Cargar video
        print(f"DEBUG: Cargando video desde {video_path}")
        video = VideoFileClip(video_path)
        
        # Función para generar subtítulos como TextClip
        def make_textclip(txt):
            # Configuración de estilo para los subtítulos
            return TextClip(txt, 
                          fontsize=24, 
                          color='white', 
                          font='Arial-Bold',
                          stroke_color='black', 
                          stroke_width=1,
                          method='caption',
                          size=(video.w * 0.8, None)).set_position(('center', 'bottom')).set_margin(40)
        
        # Cargar subtítulos SRT
        print(f"DEBUG: Cargando subtítulos desde {srt_path}")
        generator = lambda txt: make_textclip(txt)
        subtitles = SubtitlesClip(srt_path, generator)
        
        # Combinar video con subtítulos
        print("DEBUG: Combinando video con subtítulos")
        final_video = CompositeVideoClip([video, subtitles])
        
        # Escribir video final
        print(f"DEBUG: Escribiendo video final a {output_path}")
        final_video.write_videofile(
            output_path,
            codec='libx264',
            audio_codec='aac',
            temp_audiofile='temp-audio.m4a',
            remove_temp=True,
            verbose=False,
            logger=None  # Reduce output
        )
        
        # Limpiar recursos
        video.close()
        final_video.close()
        
        print(f"DEBUG: Video con subtítulos generado exitosamente: {output_path}")
        return output_path
        
    except Exception as e:
        print(f"ERROR MoviePy: {e}")
        raise RuntimeError(f"Error al incrustar subtítulos con MoviePy: {e}")

def incrustar_subtitulos_ffmpeg(video_path, srt_path, output_path=None):
    """
    Incrusta subtítulos SRT en un video usando FFmpeg.
    Si output_path no se especifica, genera uno automáticamente.
    Devuelve la ruta del video generado.
    """
    if not output_path:
        base, ext = os.path.splitext(video_path)
        output_path = f"{base}_con_subtitulos{ext}"

    # Verificar que los archivos existen
    if not os.path.exists(video_path):
        raise RuntimeError(f"El archivo de video no existe: {video_path}")
    if not os.path.exists(srt_path):
        raise RuntimeError(f"El archivo SRT no existe: {srt_path}")

    # Convertir rutas a absolutas y normalizar
    srt_abspath = os.path.abspath(srt_path)
    srt_abspath = srt_abspath.replace('\\', '/')
    
    # Configurar filtro de subtítulos con mejor estilo
    filtro_subs = f"subtitles={srt_abspath}:force_style='Fontsize=18,PrimaryColour=&Hffffff,OutlineColour=&H000000,Outline=1,Shadow=1,MarginV=50'"

    comando = [
        "ffmpeg",
        "-y",  # Sobrescribir archivo existente
        "-i", video_path,
        "-vf", filtro_subs,
        "-c:v", "libx264",  # Codec de video específico
        "-c:a", "copy",     # Copiar audio sin recodificar
        "-preset", "fast",  # Preset más rápido
        output_path
    ]
    
    print(f"DEBUG: Ejecutando comando FFmpeg: {' '.join(comando)}")
    resultado = subprocess.run(comando, capture_output=True, text=True, timeout=900)  # Timeout de 15 minutos
    
    if resultado.returncode != 0:
        print(f"[FFmpeg STDERR]:\n{resultado.stderr}")
        raise RuntimeError(f"Error al incrustar subtítulos con FFmpeg: {resultado.stderr}")
    
    if not os.path.exists(output_path):
        raise RuntimeError(f"FFmpeg no generó el archivo esperado: {output_path}")
    
    print(f"DEBUG: Video con subtítulos generado exitosamente con FFmpeg: {output_path}")
    return output_path

def incrustar_subtitulos(video_path, srt_path, output_path=None, prefer_method='moviepy'):
    """
    Incrusta subtítulos en un video usando el método preferido.
    Intenta con MoviePy primero, luego con FFmpeg como fallback.
    """
    if not output_path:
        base, ext = os.path.splitext(video_path)
        output_path = f"{base}_con_subtitulos{ext}"
    
    methods = ['moviepy', 'ffmpeg'] if prefer_method == 'moviepy' else ['ffmpeg', 'moviepy']
    
    for method in methods:
        try:
            if method == 'moviepy':
                print("DEBUG: Intentando incrustar subtítulos con MoviePy...")
                return incrustar_subtitulos_moviepy(video_path, srt_path, output_path)
            else:
                print("DEBUG: Intentando incrustar subtítulos con FFmpeg...")
                return incrustar_subtitulos_ffmpeg(video_path, srt_path, output_path)
        except Exception as e:
            print(f"DEBUG: {method} falló: {e}")
            if method == methods[-1]:  # Si es el último método, propagar error
                raise
            else:
                print(f"DEBUG: Intentando con método alternativo...")
                continue
    
    raise RuntimeError("Todos los métodos de incrustación de subtítulos fallaron")