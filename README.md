# PetroReports Suite 🛢️
## Well Intervention, Workover & Completions (IADC Reporting & Learning System)

Aplicación de ingeniería de petróleos para la auditoría, control de cambios pedagógico, recomendaciones QA/QC multiespecialista y traducción estandarizada IADC de reportes de intervención de pozos.

---

### 1. Inicio Rápido (En 1 Clic)

- **Opción A (Fácil)**: Haga doble clic en el archivo [`INICIAR_APP.bat`](file:///c:/Users/renes/OneDrive/Escritorio/FEC/APP%20Reportes/INICIAR_APP.bat).
- **Opción B (Terminal)**:
  ```bash
  python run_app.py
  ```

Una vez iniciada:
* **En su PC**: Abra su navegador en [http://localhost:8000](http://localhost:8000).
* **En su Celular**: Conéctese al mismo Wi-Fi del pozo o campamento e ingrese a la dirección IP local mostrada en la consola (ej. `http://192.168.1.XX:8000`).

---

### 2. El Flujo de las 4 Cajas

1. **Caja 1: Entrada Cruda (Español)**
   - Pegue el reporte de campo o notas de WhatsApp.
   - Cuenta con botón para cargar el ejemplo real de **Yopo-1** con 1 clic.
   - Suma y concilia automáticamente las 24 horas del día.
2. **Caja 2: Control de Cambios & Aprendizaje (Diff Visual)**
   - Resalta en rojo tachado (`<s>...</s>`) los errores (fechas imposibles como 31/11, cálculos erróneos como 146 ft vs. 416 ft, o jerga informal).
   - Resalta en verde (`<b>...</b>`) la corrección técnica propuesta.
   - Incluye tarjetas con **lecciones de ingeniería** para elevar sus hábitos de reporte.
   - Botón `[✔️ Aplicar a Caja 1]` para sincronizar el texto corregido.
3. **Caja 3: Auditoría QA/QC de los 7 Agentes**
   - Muestra las alertas de los especialistas:
     - 🟢 **Tally & Mecánica**: Sobretensión, holguras de drift, velocidades en ft/hr.
     - 🔴 **Fluidos & Cemento**: Espesores reales y balance hidrostático de tapones.
     - 🟡 **PCE / Wireline**: Pruebas de lubricadores y 100% detonación.
     - 🟣 **Levantamiento Artificial (BES/Varillas/Gas Lift)**: Aislamiento Megger y recuento de partes.
     - 🟠 **HSE & NPT**: Clasificación de tormentas y eventos de seguridad IADC.
     - 🏆 **Director Líder**: Integridad de barreras bajo NORSOK D-010.
4. **Caja 4: Traducción IADC Oficial (Inglés)**
   - Narrativa ejecutiva con siglas internacionales (`POOH`, `RIH`, `HMBP`, `WOC`, `PUW`, `SOW`, etc.).
   - Botón `[📋 Copiar al Portapapeles]` para pegar en OpenWells, DIMS o en su correo.
   - Botón `[⭐ Guardar en Memoria]` para que el sistema aprenda su estándar preferido.

---

### 3. Memoria de Aprendizaje & Nivel de Madurez (0% a 100%)

- La barra superior mide el nivel técnico del reporte:
  - **Nivel 1 (Básico)**: Diámetro y peso.
  - **Nivel 2 (Estándar)**: + Rosca y Grado de acero (L-80 / N-80).
  - **Nivel 3 (Élite Internacional)**: + Rango 2, Box x Pin, velocidades y presiones.
- La memoria local se guarda en [`data/learning_memory.json`](file:///c:/Users/renes/OneDrive/Escritorio/FEC/APP%20Reportes/data/learning_memory.json).

---

### 4. Conectividad IA (Modo Híbrido)

- **Modo Offline (Sin Internet)**: Funciona de inmediato sin necesidad de API Key, utilizando el motor de reglas petroleras locales de alta precisión.
- **Modo Google Gemini (En la Nube)**: Si desea activar el modelo más avanzado, haga clic en el botón `[🔑 API Key]` en la barra superior y pegue su clave gratuita de Google AI Studio.
