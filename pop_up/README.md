# 🎓 Moodle Desktop Assistant (Moodle Centros Sevilla • Dark Edition)

Aplicación de escritorio en **tema oscuro** conectada directamente a tu perfil de Moodle (`https://educacionadistancia.juntadeandalucia.es/centros/sevilla/my/`).

## 🚀 Cómo iniciar la aplicación

1. **Modo Aplicación de Escritorio Completa**:
   - Haz doble clic en **`Iniciar_Asistente_Moodle.bat`** o ejecuta en terminal:
     ```bash
     python app.py
     ```
2. **Modo Mini Pop-Up Flotante de Escritorio (Arrastrable y Always-On-Top)**:
   - Haz doble clic en **`Modo_PopUp_Flotante.bat`**, pulsa el botón **"📌 Mini Pop-Up Flotante"** dentro de la aplicación, o ejecuta:
     ```bash
     python popup_widget.py
     ```

---

## 🔐 Conexión Real con tu Perfil de Moodle

Al abrir la aplicación por primera vez (sin ningún dato de ejemplo pre-cargado), se abre directamente la pestaña **"🔐 Iniciar Sesión Moodle"**:

1. **Inicio de Sesión Directo (Usuario y Contraseña de Moodle / IdEA)**:
   - El enlace `https://educacionadistancia.juntadeandalucia.es/centros/sevilla/my/` ya viene configurado por defecto.
   - Introduce tu **Usuario de Moodle / IdEA (Séneca)** y tu **Contraseña** y pulsa **"🔐 Iniciar Sesión y Sincronizar Todo mi Moodle"**.
   - El conector [`MoodleSessionConnector`](file:///c:/Users/Dani/Desktop/nuevo-proyecto/pop_up/app.py) inicia sesión en el servidor de la Junta de Andalucía y descarga automáticamente:
     - Tu **nombre completo e identificador de estudiante**.
     - Todas tus **asignaturas/cursos matriculados** (con acceso directo para abrirlos en Google Chrome o añadirlos con un clic a tu Horario de Clases).
     - Todas las **tareas, entregas, cuestionarios y eventos** de tu línea de tiempo y calendario de Moodle.
     - Tus **calificaciones y elementos evaluables** para la calculadora de media ponderada.
2. **Métodos adicionales incluidos**:
   - Sincronización mediante **URL del Calendario `.ics` de Moodle** o subida de archivo `.ics`.
   - Sincronización por **Cookie `MoodleSession`** (útil si accedes mediante Cl@ve o Certificado Digital) o **Token WebService (`wstoken`)**.
