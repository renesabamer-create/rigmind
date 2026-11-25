# RigMind — Asistente de reportes de pozo

Herramienta **personal** para auditar, completar y traducir el reporte de una operación
de pozo que cubre un lapso de tiempo (un turno, media jornada o el día completo).

```
Caja 1  pego el reporte crudo (español, el lapso que sea)
Caja 2  auditoría: corrige lo demostrable, marca lo que falta completar
Caja 3  hallazgos con evidencia (línea + cita + norma) y checklist por operación
Caja 4  traducción a inglés de operaciones con las siglas de la industria
```

---

## 1. Arranque

```bash
pip install -r requirements.txt
python run_app.py
```

Abra <http://localhost:8000>. Por defecto el servidor escucha **solo en este computador**.
Para usarlo desde el celular en la misma red: `python run_app.py --lan` (queda sin
autenticación: úselo solo en una red de confianza).

También puede usar `INICIAR_APP.bat`.

---

## 2. Qué hace la auditoría (Caja 2 y 3)

**Lapso, no 24 horas forzadas.** Usted define el rango (`Desde` – `Hasta`). La app calcula
la cobertura real, detecta huecos y operaciones solapadas, y avisa si el reporte empieza
después del inicio del lapso (informativo, no error).

**Errores demostrables, corregidos en el texto y con evidencia:**

| Verificación | Ejemplo |
|---|---|
| Espesor de tapón | 5720 − 5331 = 389 ft, no 146 ft |
| Avance de juntas | 4/150 jtas = 2.7 %, no 5.0 % |
| Cargas de rig move | 3/4 cargas = 75 % |
| Unidades | “68000 klbs” → 68 klb (68,000 lb) |
| Prueba en baja (API 53) | 250–350 psi y mínimo 5 min |
| Fechas | 31/11 no existe: se señala, **no se inventa** la fecha |
| Sacos vs volumen | bbl × 5.615 / rendimiento ≈ sx |
| Contexto del pozo | profundidad > PBTD, prueba > rating del BOP |

Cada hallazgo trae: gravedad, mensaje, **línea y cita**, norma o práctica aplicable y la
corrección sugerida.

**Completitud por operación.** Detecta la maniobra principal de cada bloque horario
(POOH, RIH, HMBP, tapón de cemento, prueba de BOP, circulación, wireline, rig move, ESP,
NPT, charla de seguridad, wellhead) y exige los parámetros que un revisor pediría.
Los eventos consecutivos de la misma maniobra se agrupan (sentar el HMBP y luego
liberarlo/probarlo cuentan como una sola operación).

Solo los campos **obligatorios** faltantes se marcan dentro del texto como
`[completar: ...]`; los recomendados quedan en el checklist para no ensuciar el reporte.

**Sugerencias de redacción** para frases vacías (“se continúa con las operaciones”,
“varios”, “aprox.”, “ok” suelto).

---

## 3. Traducción (Caja 4)

- Usa el glosario ES→EN incluido en el prompt (POOH, RIH, HMBP, WOC, TOC, PJSM, MLE,
  superbandas, carta Barton, etc.).
- Después de traducir **verifica objetivamente**: español residual, pares número+unidad
  conservados y siglas estándar presentes. No dice “certificado”: dice qué encontró.
- Si la IA falla o no hay clave, entrega un **borrador offline marcado** (diccionario local,
  mezcla inglés y español) y lo advierte. Nunca sustituye en silencio.

Proveedores: DeepSeek, OpenAI, Anthropic, Groq y Gemini. La clave se guarda en
`%LOCALAPPDATA%\RigMind\api_key` (fuera de OneDrive) y no se muestra en la interfaz.

---

## 4. Historial y entrega

- **💾 Guardar**: archiva el reporte (pozo, fecha, lapso, español, inglés, hallazgos y
  completitud) en `data/rigmind.db` (SQLite local). El selector **Historial** del encabezado
  reabre cualquier turno anterior.
- **⬇ Word / ⬇ Excel**: descarga el DOR con encabezado, tabla de hallazgos con evidencia y
  norma, texto en español y texto en inglés. El Excel agrega hojas de operaciones y hallazgos.
- El archivo exportado incluye la nota de que es un borrador que requiere revisión y firma.

---

## 5. Pruebas

```bash
python tests/run_tests.py     # sin dependencias
# o: python -m pytest -q
```

Cubren cronología (huecos, solapes, medianoche), aritmética, completitud agrupada,
escape de HTML y verificación de traducción.

---

## 6. Estructura

```
run_app.py                  arranque local (--lan opcional)
src/app.py                  API FastAPI + shell HTML
src/static/app.js|app.css   interfaz
src/engine/period.py        lapso: eventos, cobertura, huecos, solapes
src/engine/completeness.py  operaciones y parámetros exigidos
src/engine/text_rules.py    glosario, tipeo, números+unidades, español residual
src/engine/auditor.py       orquestador, aritmética, evidencia, diff
src/engine/qaqc_auditor.py  llamada al LLM auditor (multi-proveedor)
src/engine/translator.py    traducción + verificación
src/engine/store.py         historial SQLite (data/rigmind.db)
src/engine/export.py        exportación .docx / .xlsx
src/engine/llm_network.py   HTTP/SSL hacia los proveedores
tests/                      pruebas del motor
data/well_profiles.json     BOP, drift y PBTD por pozo (validación)
.agents/                    documentación de roles para el asistente de código (no se ejecuta)
```

---

## 7. Límites conocidos (dichos de frente)

- El motor determinista cubre las operaciones más comunes. Una maniobra poco frecuente
  puede no tener checklist propio; en ese caso solo se revisan cronología, aritmética y
  encabezado.
- La detección de operación es por lenguaje: si el reporte está muy abreviado o en otro
  idioma, el checklist puede no activarse.
- El borrador offline **no es un DOR**: es un apoyo para no perder el trabajo.
- La app no entrega el formato propietario de OpenWells/WellView; exporta `.docx`/`.xlsx` estándar.
- La revisión humana sigue siendo obligatoria. La herramienta señala y demuestra; no firma.

---

## 8. Siguientes pasos sugeridos

1. Ampliar checklists: pesca/molinenda, squeeze, coiled tubing y snubbing.
2. Exportar la tabla de operaciones al formato que pida la operadora (además del DOR genérico).
3. Aprender de sus correcciones (comparar lo que usted editó en la Caja 2 con lo auditado).
4. Banco de reportes reales anonimizados para medir precisión y falsos positivos.
5. Adjuntar fotos/anexos del turno al reporte guardado.
