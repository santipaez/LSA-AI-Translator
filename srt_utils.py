import re

def parse_ts(ts_str):
    """
    Analiza una cadena de tiempo en formato HH:MM:SS o MM:SS y devuelve una tupla (h, m, s).
    """
    parts = ts_str.split(':')
    if len(parts) == 3:  # Formato HH:MM:SS
        h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
    elif len(parts) == 2:  # Formato MM:SS
        h, m, s = 0, int(parts[0]), int(parts[1])
    else:
        raise ValueError(f"Formato de tiempo inválido: {ts_str}")
    return h, m, s

def format_srt_time(h, m, s, ms=0):
    """
    Formatea horas, minutos, segundos y milisegundos al formato de tiempo SRT HH:MM:SS,mmm.
    """
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def time_to_seconds(h, m, s):
    """
    Convierte tiempo en horas, minutos y segundos a segundos totales.
    """
    return h * 3600 + m * 60 + s

def seconds_to_time(total_seconds):
    """
    Convierte segundos totales a tupla (h, m, s).
    """
    h = int(total_seconds // 3600)
    m = int((total_seconds % 3600) // 60)
    s = int(total_seconds % 60)
    return h, m, s

def split_long_text(text, max_length=80):
    """
    Divide texto largo en líneas más cortas, respetando palabras.
    """
    if len(text) <= max_length:
        return [text]
    
    words = text.split()
    lines = []
    current_line = ""
    
    for word in words:
        if len(current_line + " " + word) <= max_length:
            current_line = current_line + " " + word if current_line else word
        else:
            if current_line:
                lines.append(current_line.strip())
                current_line = word
            else:
                # Palabra muy larga, dividirla
                lines.append(word[:max_length])
                current_line = word[max_length:]
    
    if current_line:
        lines.append(current_line.strip())
    
    return lines

def optimize_srt_blocks(srt_content, max_duration=10, max_chars=160):
    """
    Optimiza bloques SRT dividiendo los que son demasiado largos o tienen mucho texto.
    """
    if not srt_content.strip():
        return srt_content
    
    blocks = srt_content.strip().split('\n\n')
    optimized_blocks = []
    counter = 1
    
    for block in blocks:
        if not block.strip():
            continue
            
        lines = block.strip().split('\n')
        if len(lines) < 3:
            continue
            
        try:
            # Parsear tiempo
            time_line = lines[1]
            if ' --> ' not in time_line:
                continue
                
            start_time_str, end_time_str = time_line.split(' --> ')
            
            # Convertir a formato parseable
            start_time_clean = start_time_str.replace(',', ':').split(':')
            end_time_clean = end_time_str.replace(',', ':').split(':')
            
            start_h, start_m, start_s = int(start_time_clean[0]), int(start_time_clean[1]), int(start_time_clean[2])
            end_h, end_m, end_s = int(end_time_clean[0]), int(end_time_clean[1]), int(end_time_clean[2])
            
            start_seconds = time_to_seconds(start_h, start_m, start_s)
            end_seconds = time_to_seconds(end_h, end_m, end_s)
            duration = end_seconds - start_seconds
            
            text_content = '\n'.join(lines[2:])
            
            # Limpiar el texto antes de procesarlo
            text_content = clean_subtitle_text(text_content)
            if not text_content.strip():
                continue
            
            # Si el bloque es corto o tiene poco texto, mantenerlo
            if duration <= max_duration and len(text_content) <= max_chars:
                optimized_blocks.append(f"{counter}\n{time_line}\n{text_content}")
                counter += 1
                continue
            
            # Dividir texto largo en líneas
            text_lines = split_long_text(text_content, max_length=max_chars//2)
            
            # Si hay mucho texto, dividir en múltiples bloques
            if len(text_lines) > 2 or duration > max_duration:
                num_parts = max(len(text_lines) // 2, int(duration / max_duration))
                num_parts = max(1, min(num_parts, 5))  # Límite razonable
                
                time_per_part = duration / num_parts
                
                for i in range(num_parts):
                    part_start = start_seconds + (i * time_per_part)
                    part_end = start_seconds + ((i + 1) * time_per_part)
                    
                    part_start_h, part_start_m, part_start_s = seconds_to_time(part_start)
                    part_end_h, part_end_m, part_end_s = seconds_to_time(part_end)
                    
                    part_start_time = format_srt_time(part_start_h, part_start_m, part_start_s)
                    part_end_time = format_srt_time(part_end_h, part_end_m, part_end_s)
                    
                    # Asignar texto a esta parte
                    lines_per_part = max(1, len(text_lines) // num_parts)
                    start_line = i * lines_per_part
                    end_line = min((i + 1) * lines_per_part, len(text_lines))
                    
                    if i == num_parts - 1:  # Última parte toma todo lo restante
                        end_line = len(text_lines)
                    
                    part_text = '\n'.join(text_lines[start_line:end_line])
                    part_text = clean_subtitle_text(part_text)
                    
                    if part_text.strip():
                        optimized_blocks.append(f"{counter}\n{part_start_time} --> {part_end_time}\n{part_text}")
                        counter += 1
            else:
                # Mantener el bloque pero con texto optimizado
                optimized_text = '\n'.join(text_lines[:2])  # Máximo 2 líneas
                optimized_text = clean_subtitle_text(optimized_text)
                if optimized_text.strip():
                    optimized_blocks.append(f"{counter}\n{time_line}\n{optimized_text}")
                    counter += 1
                
        except (ValueError, IndexError) as e:
            print(f"WARN: Error procesando bloque SRT: {e}. Manteniendo original.")
            # Mantener bloque original si hay error
            optimized_blocks.append(f"{counter}\n" + '\n'.join(lines[1:]))
            counter += 1
    
    return '\n\n'.join(optimized_blocks) + '\n'

def markdown_to_srt(markdown_text):
    """
    Convierte una transcripción en formato Markdown (con timestamps específicos) a formato SRT.
    Ahora es más flexible: acepta títulos con o sin dos puntos, y bloques con o sin título.
    Formato de timestamp esperado: (HH:MM:SS-HH:MM:SS) o (M:SS-M:SS), con o sin título, y texto principal.
    """
    srt_output = []
    counter = 1

    # Regex más flexible:
    # - Permite **(0:00-0:05) Título opcional:** o **(0:00-0:05)**
    # - El título puede terminar en : o no, y puede estar vacío
    # - El texto puede estar en la misma línea o en la siguiente
    pattern = re.compile(
        r"""
        \*\*\(\s*
        (\d{1,2}:\d{2}(?::\d{2})?)\s*-\s*(\d{1,2}:\d{2}(?::\d{2})?)
        \)\s*
        ([^\n\*]*)?  # Título opcional (puede terminar en : o no)
        \*\*:?\s*\n?  # Cierra los asteriscos, dos puntos opcional, salto de línea opcional
        ([\s\S]*?)(?=\n\*\*\(|\Z)  # Texto principal hasta el próximo bloque o fin
        """,
        re.MULTILINE | re.VERBOSE
    )

    for match in pattern.finditer(markdown_text):
        try:
            start_ts_str = match.group(1).strip()
            end_ts_str = match.group(2).strip()
            title_content = (match.group(3) or '').strip(' :')  # Quita espacios y dos puntos
            text_content = (match.group(4) or '').strip()

            h_start, m_start, s_start = parse_ts(start_ts_str)
            h_end, m_end, s_end = parse_ts(end_ts_str)

            srt_start_time = format_srt_time(h_start, m_start, s_start)
            srt_end_time = format_srt_time(h_end, m_end, s_end)

            # Si hay texto principal, se usa ese. Si no, se usa el título (si existe).
            final_srt_text = text_content if text_content else title_content
            if not final_srt_text.strip():
                continue

            # Limpiar el texto de elementos no deseados
            cleaned_text = clean_subtitle_text(final_srt_text)
            if not cleaned_text.strip():
                continue

            srt_output.append(str(counter))
            srt_output.append(f"{srt_start_time} --> {srt_end_time}")
            srt_output.append(cleaned_text)
            srt_output.append("")
            counter += 1
        except Exception as e_block:
            print(f"WARN (Exception): Omitiendo bloque por error inesperado: {e_block}. Bloque: '{match.group(0)[:60]}...'")

    if not srt_output and markdown_text.strip():
        print("WARN: markdown_to_srt no generó bloques. Revisar formato de entrada o regex.")
    
    # Generar SRT inicial
    initial_srt = "\n".join(srt_output)
    
    # Optimizar bloques largos
    optimized_srt = optimize_srt_blocks(initial_srt)
    
    return optimized_srt

def clean_subtitle_text(text):
    """
    Limpia el texto de subtítulos eliminando elementos no deseados como timestamps,
    nombres de hablantes, comillas de transcripción, sobreimpresos, anotaciones de LSA, etc.
    """
    if not text:
        return ""
    
    # Eliminar completamente las líneas que empiecen con "Anotaciones de LSA:"
    lines = text.split('\n')
    cleaned_lines = []
    
    for line in lines:
        line = line.strip()
        # Saltar líneas de anotaciones de LSA completamente
        if line.startswith("Anotaciones de LSA:"):
            continue
        
        # Eliminar timestamps en formato (H:MM-H:MM) o (HH:MM:SS-HH:MM:SS)
        line = re.sub(r'\(\s*\d{1,2}:\d{2}(?::\d{2})?\s*-\s*\d{1,2}:\d{2}(?::\d{2})?\s*\)', '', line)
        
        # Eliminar nombres de hablantes al inicio de líneas (Ej: "Juan Pérez:", "Luciana Doeyo:")
        # Patrón más amplio que incluye nombres con mayúsculas y roles entre paréntesis
        line = re.sub(r'^[A-ZÁÉÍÓÚÑ][a-záéíóúñ\s]*\s*(\([^)]*\))?\s*:\s*', '', line)
        
        # Eliminar roles genéricos (Presentador:, Entrevistado:, etc.)
        line = re.sub(r'^(Presentador|Entrevistado|Reportero|Conductor|Invitado|Periodista|Hablante)\s*[a-záéíóúñ\s]*\s*(\([^)]*\))?\s*:\s*', '', line, flags=re.IGNORECASE)
        
        # Eliminar referencias a sobreimpresos y elementos visuales
        line = re.sub(r'(Sobreimpreso|Logo|Imagen de fondo|Gráfico|Montaje)\s*:\s*[^.]*\.?', '', line, flags=re.IGNORECASE)
        
        # Eliminar descripciones de señas entre paréntesis con patrones específicos
        line = re.sub(r'\(Realiza seña de[^)]*\)', '', line, flags=re.IGNORECASE)
        line = re.sub(r'\(Seña de[^)]*\)', '', line, flags=re.IGNORECASE)
        line = re.sub(r'\(Hablante[^)]*\)', '', line, flags=re.IGNORECASE)
        
        # Eliminar otras descripciones de acciones entre paréntesis
        line = re.sub(r'\([^)]*\)', '', line)
        
        # Eliminar comillas que envuelven todo el texto o líneas completas
        if (line.startswith('"') and line.endswith('"')) or (line.startswith("'") and line.endswith("'")):
            line = line[1:-1].strip()
        # También eliminar comillas solo al inicio o solo al final si están aisladas
        if line.startswith('"') and not '"' in line[1:]:
            line = line[1:].strip()
        if line.endswith('"') and not '"' in line[:-1]:
            line = line[:-1].strip()
        if line.startswith("'") and not "'" in line[1:]:
            line = line[1:].strip()
        if line.endswith("'") and not "'" in line[:-1]:
            line = line[:-1].strip()
        
        if line:  # Solo añadir líneas no vacías
            cleaned_lines.append(line)
    
    text = '\n'.join(cleaned_lines)
    
    # Limpiar espacios extra y líneas vacías
    text = re.sub(r'\n\s*\n', '\n', text)  # Múltiples saltos de línea
    text = re.sub(r'\s+', ' ', text)  # Múltiples espacios
    text = text.strip()
    
    return text

if __name__ == '__main__':
    # Ejemplo de uso (se puede descomentar para probar independientemente)
    sample_markdown = """
(0:01-0:05) Este es el primer subtítulo.
Con múltiples líneas.

(0:06-0:10) Este es el segundo subtítulo.
    (0:10-0:12) Este es el tercero, muy corto.
    """
    # srt_output = markdown_to_srt(sample_markdown)
    # print("--- Ejemplo de Salida SRT ---")
    # print(srt_output)
    
    # print("\n--- Prueba 2 ---")
    # sample_markdown_2 = """
    # (0:00-0:06) Auspiciantes:
    # Se muestra el logo de "CG" (Caption Group).
    # (0:06-0:11) Auspiciante: La Suipachense
    # Aparece el logo de "La Suipachense" junto a dos personas sosteniendo productos de la marca.
    # (0:11-0:43) Apertura del Noticiero
    # Secuencia de apertura con gráficos abstractos en tonos azules y rojos.
    # (0:43-1:22) Introducción de Presentadores
    # Lautaro Castiglia (Presentador): "Hola a todos. Bienvenidos a este programa de noticias."
    # Lucía Fauve (Presentadora): "Sí, este programa..."
    # Lautaro Castiglia (Presentador): "...de noticias."
    # (1:22:30-1:23:00) Esto es una prueba con horas.
    # Texto de prueba con horas.
    # """
    # srt_output_2 = markdown_to_srt(sample_markdown_2)
    # print(srt_output_2)
    pass 