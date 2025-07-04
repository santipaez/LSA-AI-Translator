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
        os.remove(full_output_path)

    # Limpiar URL de YouTube (eliminar parámetros de playlist, etc.)
    clean_url = clean_youtube_url(youtube_url)
    print(f"URL original: {youtube_url}")
    print(f"URL limpia: {clean_url}")

    # Primero, verificar qué formatos están disponibles para diagnóstico
    try:
        print("DEBUG: Verificando formatos disponibles para el video...")
        list_formats_cmd = [
            "yt-dlp",
            "--list-formats",
            "--no-warnings",
            clean_url
        ]
        formats_result = subprocess.run(list_formats_cmd, capture_output=True, text=True, timeout=60)
        if formats_result.returncode == 0:
            print(f"DEBUG: Formatos disponibles:\n{formats_result.stdout[:500]}...")
        else:
            print(f"WARN: No se pudieron listar formatos: {formats_result.stderr}")
            # Si no se pueden listar formatos, el video probablemente no está disponible
            raise RuntimeError(f"Video no disponible o con restricciones: {formats_result.stderr}")
    except subprocess.TimeoutExpired:
        print("WARN: Timeout al verificar formatos disponibles")
    except Exception as e:
        print(f"WARN: Error verificando formatos: {e}")

    # Configuraciones de formato con fallbacks más amplios
    format_configs = [
        # Configuraciones específicas de MP4
        {"format": "best[ext=mp4][height<=720]", "description": "MP4 720p o menor"},
        {"format": "best[ext=mp4][height<=480]", "description": "MP4 480p o menor"},
        {"format": "best[ext=mp4]", "description": "Mejor MP4 disponible"},
        
        # Configuraciones más generales
        {"format": "best[height<=720]", "description": "Mejor video 720p o menor (cualquier formato)"},
        {"format": "best[height<=480]", "description": "Mejor video 480p o menor (cualquier formato)"},
        {"format": "best", "description": "Mejor formato disponible"},
        
        # Fallbacks básicos
        {"format": "worst", "description": "Formato más básico disponible"},
        
        # Último recurso - solo audio + cualquier video
        {"format": "bestaudio+worstvideo", "description": "Audio + video básico"}
    ]

    last_error = None
    for i, config in enumerate(format_configs, 1):
        try:
            print(f"Intento {i}/{len(format_configs)}: {config['description']}")
            
            # Comando base de yt-dlp con parámetros más robustos
            cmd = [
                "yt-dlp",
                "--format", config["format"],
                "--output", full_output_path,
                "--no-warnings",
                "--no-check-certificate", 
                "--ignore-errors",
                "--socket-timeout", "30",
                "--retries", "3",
                "--fragment-retries", "3",
                "--no-playlist",  # Asegurar que no descarga toda la playlist
                clean_url
            ]
            
            print(f"Ejecutando: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=300)
            print(f"Salida de yt-dlp: {result.stdout[:200]}...")
            
            # Verificar que el archivo se descargó correctamente
            if os.path.exists(full_output_path) and os.path.getsize(full_output_path) > 1024:  # >1KB
                print(f"Descarga exitosa con configuración {i}: {config['description']}")
                break
            else:
                print(f"Archivo no válido con configuración {i}, intentando siguiente...")
                continue
                
        except subprocess.CalledProcessError as e:
            last_error = e
            print(f"Error en intento {i}: {e}")
            print(f"stderr: {e.stderr}")
            
            # Analizar errores específicos
            if "Requested format is not available" in e.stderr:
                print(f"WARN: Formato {config['format']} no disponible para este video")
            elif "Video unavailable" in e.stderr or "Private video" in e.stderr:
                print(f"ERROR: Video no disponible o privado: {e.stderr}")
                break  # No seguir intentando si el video no está disponible
            elif "Sign in to confirm your age" in e.stderr:
                print(f"ERROR: Video con restricción de edad: {e.stderr}")
                break  # No seguir intentando si hay restricción de edad
            
            if i == len(format_configs):  # Último intento
                break
            continue
            
        except subprocess.TimeoutExpired:
            print(f"WARN: Timeout en intento {i}")
            if i == len(format_configs):
                raise RuntimeError(f"Timeout durante descarga después de {len(format_configs)} intentos")
            continue
            
        except Exception as e:
            last_error = e
            print(f"Error inesperado en intento {i}: {e}")
            if i == len(format_configs):  # Último intento
                break
            continue

    # Si no se descargó nada, lanzar error detallado
    if not os.path.exists(full_output_path) or os.path.getsize(full_output_path) <= 1024:
        error_msg = f"No se pudo descargar el video después de {len(format_configs)} intentos. URL: {clean_url}"
        if last_error:
            if "Requested format is not available" in str(last_error):
                error_msg += "\n\nEste video parece tener problemas de disponibilidad o restricciones específicas. Posibles causas:\n"
                error_msg += "- Video con restricciones geográficas\n"
                error_msg += "- Video privado o eliminado\n"
                error_msg += "- Video con restricción de edad\n"
                error_msg += "- Problemas temporales con YouTube\n"
                error_msg += f"\nÚltimo error: {last_error.stderr}"
            else:
                error_msg += f"\nÚltimo error: {last_error}"
        raise RuntimeError(error_msg)

    # Obtener metadatos del video (título y descripción)
    try:
        # Comando para obtener metadatos (parámetros corregidos)
        metadata_cmd = [
            "yt-dlp", 
            "--print", "title",
            "--print", "description", 
            "--no-download",
            "--no-warnings",
            "--no-playlist",
            "--socket-timeout", "15",
            clean_url
        ]
        
        print(f"Obteniendo metadatos: {' '.join(metadata_cmd)}")
        metadata_result = subprocess.run(metadata_cmd, capture_output=True, text=True, check=True, timeout=60)
        
        lines = metadata_result.stdout.strip().split('\n')
        title = lines[0] if len(lines) > 0 else "Título no disponible"
        description = lines[1] if len(lines) > 1 else "Descripción no disponible"
        
        print(f"Título obtenido: {title}")
        print(f"Descripción obtenida: {description[:100]}...")
        
    except Exception as e:
        print(f"Error al obtener metadatos: {e}")
        title = "Video de YouTube"
        description = "Descripción no disponible"

    return output_filename_only, title, description

def clean_youtube_url(url):
    """
    Limpia una URL de YouTube removiendo parámetros de playlist y otros parámetros innecesarios.
    Extrae solo el video ID y reconstruye una URL limpia.
    """
    import re
    from urllib.parse import urlparse, parse_qs
    
    # Patrones para extraer video ID de diferentes tipos de URLs de YouTube
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]+)',
        r'youtube\.com/v/([a-zA-Z0-9_-]+)',
        r'youtube\.com/watch\?.*v=([a-zA-Z0-9_-]+)'
    ]
    
    video_id = None
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            video_id = match.group(1)
            break
    
    if not video_id:
        # Si no se puede extraer el ID, devolver la URL original
        print(f"WARN: No se pudo extraer video ID de {url}, usando URL original")
        return url
    
    # Construir URL limpia
    clean_url = f"https://www.youtube.com/watch?v={video_id}"
    return clean_url

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

def extract_sample_frames(video_path, output_dir="temp_frames", num_frames=2):
    """
    Extrae frames de muestra del video para validación de contenido LSA.
    Extrae frames en momentos específicos (25% y 75% del video) para análisis rápido.
    
    Args:
        video_path: Ruta al archivo de video
        output_dir: Directorio temporal para guardar frames
        num_frames: Número de frames a extraer (default: 2)
    
    Returns:
        List[str]: Lista de rutas a los frames extraídos
    """
    import tempfile
    import shutil
    
    # Crear directorio temporal
    temp_dir = os.path.join(tempfile.gettempdir(), output_dir)
    os.makedirs(temp_dir, exist_ok=True)
    
    # Limpiar frames anteriores
    for file in os.listdir(temp_dir):
        if file.endswith(('.jpg', '.jpeg', '.png')):
            try:
                os.remove(os.path.join(temp_dir, file))
            except:
                pass
    
    frame_paths = []
    
    try:
        # Obtener duración del video primero
        duration_cmd = [
            'ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', video_path
        ]
        
        duration_result = subprocess.run(duration_cmd, capture_output=True, text=True, timeout=30)
        if duration_result.returncode != 0:
            raise RuntimeError(f"No se pudo obtener duración del video: {duration_result.stderr}")
        
        total_duration = float(duration_result.stdout.strip())
        
        # Calcular timestamps para extraer frames (25%, 50%, 75% del video)
        timestamps = []
        if num_frames >= 1:
            timestamps.append(total_duration * 0.5)  # Frame del medio
        if num_frames >= 2:
            timestamps.extend([total_duration * 0.25, total_duration * 0.75])  # Inicio y final
        if num_frames >= 3 and len(timestamps) < 3:
            timestamps.append(total_duration * 0.1)  # Frame temprano adicional
        
        # Limitar a los timestamps solicitados
        timestamps = timestamps[:num_frames]
        
        for i, timestamp in enumerate(timestamps):
            frame_filename = f"sample_frame_{i+1}_{int(timestamp)}s.jpg"
            frame_path = os.path.join(temp_dir, frame_filename)
            
            # Comando ffmpeg para extraer frame en timestamp específico
            extract_cmd = [
                'ffmpeg', '-y', '-i', video_path,
                '-ss', str(timestamp),
                '-vframes', '1',
                '-q:v', '2',  # Alta calidad
                frame_path
            ]
            
            print(f"DEBUG: Extrayendo frame en {timestamp:.1f}s: {frame_filename}")
            result = subprocess.run(extract_cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0 and os.path.exists(frame_path):
                frame_paths.append(frame_path)
                print(f"DEBUG: Frame extraído exitosamente: {frame_path}")
            else:
                print(f"WARN: No se pudo extraer frame en {timestamp}s: {result.stderr}")
        
        if not frame_paths:
            raise RuntimeError("No se pudieron extraer frames del video para validación")
        
        return frame_paths
        
    except Exception as e:
        # Limpiar directorio temporal en caso de error
        try:
            shutil.rmtree(temp_dir)
        except:
            pass
        raise RuntimeError(f"Error extrayendo frames de muestra: {e}")

def cleanup_sample_frames(frame_paths):
    """
    Limpia los frames temporales después de usarlos.
    """
    for frame_path in frame_paths:
        try:
            if os.path.exists(frame_path):
                os.remove(frame_path)
                print(f"DEBUG: Frame temporal eliminado: {frame_path}")
        except Exception as e:
            print(f"WARN: No se pudo eliminar frame temporal {frame_path}: {e}")
    
    # Intentar eliminar directorio temporal si está vacío
    try:
        temp_dir = os.path.dirname(frame_paths[0]) if frame_paths else None
        if temp_dir and os.path.exists(temp_dir) and not os.listdir(temp_dir):
            os.rmdir(temp_dir)
            print(f"DEBUG: Directorio temporal eliminado: {temp_dir}")
    except:
        pass