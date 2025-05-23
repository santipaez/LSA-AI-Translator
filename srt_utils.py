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

def markdown_to_srt(markdown_text):
    """
    Convierte una transcripción en formato Markdown (con timestamps específicos) a formato SRT.
    Formato de timestamp esperado en Markdown: (HH:MM:SS-HH:MM:SS) Texto o (MM:SS-MM:SS) Texto
    """
    srt_output = []
    counter = 1

    # Regex para capturar: **(START-END) TITULO_OPCIONAL**\nTEXTO_PRINCIPAL
    # Permite H:MM:SS o M:SS para timestamps.
    # Captura el título y el texto principal por separado.
    pattern = re.compile(
        r"\*\*\(" +
        r"(((\d{1,2}:\d{2}:\d{2}|\d{1,2}:\d{2}))-" +
        r"((\d{1,2}:\d{2}:\d{2}|\d{1,2}:\d{2})))" +
        r"\)\s*" +
        r"(.*?)\*\*\s*\n" +
        r"(.*?)" +
        r"(?=\n\n\*\*\(|\Z)",  # Lookahead para el inicio del siguiente bloque **( o fin del string
        re.DOTALL
    )

    for match in pattern.finditer(markdown_text):
        try:
            start_ts_str = match.group(1)  # Timestamp de inicio completo, ej: "0:01" o "0:01:00"
            end_ts_str = match.group(3)    # Timestamp de fin completo
            title_content = match.group(5).strip() # Contenido del título (puede estar vacío si no hay título explícito)
            text_content = match.group(6).strip()  # Cuerpo del texto después del título y newline

            h_start, m_start, s_start = parse_ts(start_ts_str)
            h_end, m_end, s_end = parse_ts(end_ts_str)

            srt_start_time = format_srt_time(h_start, m_start, s_start)
            srt_end_time = format_srt_time(h_end, m_end, s_end)

            # Determinar el contenido final para el SRT.
            # Si hay texto principal, se usa ese. Si no, se usa el título (si existe).
            final_srt_text = text_content
            if not final_srt_text and title_content:
                final_srt_text = title_content
            
            # Si después de todo, el contenido es solo espacios en blanco o vacío, omitir el bloque.
            if not final_srt_text.strip():
                # print(f"WARN: Bloque de subtítulo vacío para {start_ts_str}-{end_ts_str}. Omitiendo.")
                continue

            srt_output.append(str(counter))
            srt_output.append(f"{srt_start_time} --> {srt_end_time}")
            # Reemplazar múltiples saltos de línea por uno solo en el texto del SRT
            cleaned_text = re.sub(r'\n{2,}', '\n', final_srt_text).strip()
            srt_output.append(cleaned_text)
            srt_output.append("")

            counter += 1
        except ValueError as e:
            print(f"WARN (ValueError): Omitiendo bloque por error en timestamp: {e}. Bloque: '{match.group(0)[:60]}...'")
        except Exception as e_block:
            print(f"WARN (Exception): Omitiendo bloque por error inesperado: {e_block}. Bloque: '{match.group(0)[:60]}...'")

    if not srt_output and markdown_text.strip(): # Solo mostrar si había texto en markdown
        print("WARN: markdown_to_srt no generó bloques. Revisar formato de entrada o regex.")
        # print(f"DEBUG markdown_to_srt: Entrada recibida (primeros 500 chars):\n{markdown_text[:500]}")

    return "\n".join(srt_output)

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