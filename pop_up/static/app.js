/* ==========================================================================
   MOODLE DESKTOP ASSISTANT - CONECTOR REAL CON MOODLE CENTROS (SEVILLA)
   Ubicación: pop_up/static/app.js
   ========================================================================== */

const DEFAULT_MOODLE_URL = "https://educacionadistancia.juntadeandalucia.es/centros/sevilla/my/";

let appData = null;
let currentView = "dashboard";
let currentTaskFilter = "all";
let globalSearchQuery = "";

const nowDate = new Date();
let moodleCalYear = nowDate.getFullYear();
let moodleCalMonth = nowDate.getMonth();
let moodleSelectedDay = null;

let personalCalYear = nowDate.getFullYear();
let personalCalMonth = nowDate.getMonth();
let personalSelectedDay = null;

// Estado Pomodoro
let pomoTotalSeconds = 25 * 60;
let pomoRemainingSeconds = 25 * 60;
let pomoRunning = false;
let pomoInterval = null;

const MONTH_NAMES_ES = [
  "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
  "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
];

const DAY_NAMES_ES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"];

const VIEW_TITLES = {
  "dashboard": "🏠 Resumen General del Estudiante",
  "profile": "🔐 Iniciar Sesión y Sincronizar con Moodle",
  "tasks": "✅ Mis Tareas y Entregas de Moodle",
  "moodle-calendar": "🎓 Calendario de Moodle (Clic en tarea → Google)",
  "personal-calendar": "🗓️ Mi Calendario Personal (Añadir Eventos y Recordatorios)",
  "schedule": "⏰ Mi Horario de Clases Modificable",
  "studio": "🧠 Estudio Pomodoro, Calculadora de Notas y Apuntes"
};

// ---------------------------------------------------------------------------
// INICIALIZACIÓN Y PERSISTENCIA
// ---------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", async () => {
  startLiveClock();
  setupKeyboardShortcuts();
  await fetchAppState();
  const todayIso = toIsoDate(new Date());
  const qpDateInput = document.getElementById("qpDate");
  if (qpDateInput) qpDateInput.value = todayIso;

  // Si aún no ha iniciado sesión en Moodle, abrir directamente la pestaña de Iniciar Sesión
  if (appData && appData.profile && !appData.profile.linked) {
    switchView("profile");
  }
});

function startLiveClock() {
  const el = document.getElementById("liveClock");
  const tick = () => {
    const d = new Date();
    const datePart = d.toLocaleDateString("es-ES", { weekday: "short", day: "2-digit", month: "short" });
    const timePart = d.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    if (el) el.textContent = `${datePart} • ${timePart}`;
  };
  tick();
  setInterval(tick, 1000);
}

function setupKeyboardShortcuts() {
  window.addEventListener("keydown", (e) => {
    if (e.altKey) {
      const map = {
        "1": "profile",
        "2": "dashboard",
        "3": "tasks",
        "4": "moodle-calendar",
        "5": "personal-calendar",
        "6": "schedule",
        "7": "studio"
      };
      if (map[e.key]) {
        e.preventDefault();
        switchView(map[e.key]);
      }
    }
  });
}

async function fetchAppState() {
  try {
    const resp = await fetch("/api/state");
    const json = await resp.json();
    if (json && json.ok && json.data) {
      appData = json.data;
      localStorage.setItem("moodle_assistant_real_state", JSON.stringify(appData));
      renderAll();
      return;
    }
  } catch (_err) {
    const cached = localStorage.getItem("moodle_assistant_real_state");
    if (cached) {
      appData = JSON.parse(cached);
    } else {
      appData = getCleanInitialData();
    }
    renderAll();
  }
}

async function persistState(toastMsg = "") {
  localStorage.setItem("moodle_assistant_real_state", JSON.stringify(appData));
  try {
    await fetch("/api/state", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ data: appData })
    });
  } catch (_err) {}
  renderAll();
  if (toastMsg) showToast(toastMsg);
}

// ---------------------------------------------------------------------------
// NAVEGACIÓN ENTRE VISTAS ("QUE PUEDA MOVERME")
// ---------------------------------------------------------------------------
function switchView(viewId) {
  currentView = viewId;
  document.querySelectorAll(".nav-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.getAttribute("data-view") === viewId);
  });
  document.querySelectorAll(".view-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === `view-${viewId}`);
  });
  const titleEl = document.getElementById("topbarTitle");
  if (titleEl && VIEW_TITLES[viewId]) {
    titleEl.textContent = VIEW_TITLES[viewId];
  }
  renderAll();
}

function handleGlobalSearch(val) {
  globalSearchQuery = (val || "").trim().toLowerCase();
  if (globalSearchQuery && currentView !== "tasks") {
    switchView("tasks");
  } else {
    renderAll();
  }
}

// ---------------------------------------------------------------------------
// ABRIR EN GOOGLE CHROME (AL PINCHAR EN TAREA DEL CALENDARIO DE MOODLE)
// ---------------------------------------------------------------------------
async function openTaskInGoogle(taskId, forceGoogleSearch = false) {
  const task = (appData.moodleTasks || []).find((t) => t.id === taskId);
  if (!task) return;

  const profile = appData.profile || {};
  const openMode = forceGoogleSearch
    ? "google_search"
    : (profile.openMode === "google_search" ? "google_search" : "direct");

  const searchQuery = `Moodle ${profile.university || ""} ${task.course || ""} ${task.title || ""}`.trim();
  const targetUrl = task.moodleUrl || profile.moodleEntryUrl || DEFAULT_MOODLE_URL;

  await openInGoogle(targetUrl, searchQuery, openMode);
}

async function openInGoogle(url, query, mode = "direct") {
  showToast(`🌐 Abriendo en Google Chrome: "${query || url}"...`);
  try {
    const resp = await fetch("/api/open-google", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, query, mode })
    });
    const json = await resp.json();
    if (json && json.ok) return;
  } catch (_err) {}

  let finalUrl = (url || "").trim();
  if (mode === "google_search" || !finalUrl.startsWith("http")) {
    finalUrl = `https://www.google.com/search?q=${encodeURIComponent(query || url || "Moodle")}`;
  }
  window.open(finalUrl, "_blank", "noopener");
}

function openMyMoodleCampus() {
  const prof = (appData && appData.profile) || {};
  const url = prof.moodleEntryUrl || prof.moodleBaseUrl || DEFAULT_MOODLE_URL;
  openInGoogle(url, "Moodle Centros Sevilla", "direct");
}

async function launchFloatingPopup() {
  try {
    const resp = await fetch("/api/launch-popup", { method: "POST" });
    const json = await resp.json();
    if (json && json.ok) {
      showToast("📌 Mini Pop-Up Flotante abierto en tu escritorio (puedes arrastrarlo libremente).");
    } else {
      showToast("⚠️ " + (json.error || "No se pudo lanzar el Pop-Up"), true);
    }
  } catch (_e) {
    showToast("💡 Ejecuta Iniciar_Asistente_Moodle.bat o popup_widget.py para usar el Pop-Up nativo.");
  }
}

// ---------------------------------------------------------------------------
// RENDERIZADO GENERAL
// ---------------------------------------------------------------------------
function renderAll() {
  if (!appData) return;
  updateCoursesDatalist();
  renderSidebarAndBadges();
  renderDashboard();
  renderProfileForm();
  renderTasksView();
  renderMoodleCalendar();
  renderPersonalCalendar();
  renderWeeklySchedule();
  renderStudioView();
}

function updateCoursesDatalist() {
  const dl = document.getElementById("moodleCoursesDatalist");
  if (!dl) return;
  const courses = (appData.courses || []).map((c) => c.fullname);
  const fromTasks = (appData.moodleTasks || []).map((t) => t.course);
  const unique = Array.from(new Set([...courses, ...fromTasks].filter(Boolean)));
  dl.innerHTML = unique.map((c) => `<option value="${escapeAttr(c)}"></option>`).join("");
}

function renderSidebarAndBadges() {
  const prof = appData.profile || {};
  const isLinked = Boolean(prof.linked);

  document.getElementById("sbAvatar").textContent = prof.avatarInitials || "MD";
  document.getElementById("sbStudentName").textContent = prof.studentName || (prof.username ? prof.username : "Sin sesión iniciada");
  document.getElementById("sbUniversity").textContent = prof.university || "Moodle Centros Sevilla";

  const dot = document.getElementById("sbStatusDot");
  if (dot) {
    dot.style.background = isLinked ? "var(--accent-emerald)" : "var(--accent-amber)";
    dot.style.boxShadow = isLinked ? "0 0 8px var(--accent-emerald)" : "0 0 8px var(--accent-amber)";
  }

  const badgeLogin = document.getElementById("badgeLoginStatus");
  if (badgeLogin) {
    badgeLogin.textContent = isLinked ? "Activo" : "Conectar";
    badgeLogin.className = isLinked ? "nav-badge" : "nav-badge moodle";
  }

  const pendingTasks = (appData.moodleTasks || []).filter((t) => t.status !== "completed");
  document.getElementById("badgePendingTasks").textContent = pendingTasks.length;
  document.getElementById("badgeMoodleCal").textContent = (appData.moodleTasks || []).length;
  document.getElementById("badgePersonalCal").textContent = (appData.personalEvents || []).filter((e) => !e.completed).length;
}

// ---------------------------------------------------------------------------
// VISTA 1: DASHBOARD
// ---------------------------------------------------------------------------
function renderDashboard() {
  const prof = appData.profile || {};
  const banner = document.getElementById("unlinkedAlertBanner");
  if (banner) {
    banner.style.display = prof.linked ? "none" : "block";
  }

  const tasks = appData.moodleTasks || [];
  const pending = tasks.filter((t) => t.status !== "completed");
  pending.sort((a, b) => `${a.dueDate} ${a.dueTime}`.localeCompare(`${b.dueDate} ${b.dueTime}`));

  const urgentCount = pending.filter((t) => getDaysRemaining(t.dueDate) <= 3 && getDaysRemaining(t.dueDate) >= 0).length;
  document.getElementById("kpiPendingMoodle").textContent = pending.length;
  document.getElementById("kpiUrgentMoodle").textContent = `${urgentCount} entregas en los próximos 3 días`;

  const courses = appData.courses || [];
  const personalActive = (appData.personalEvents || []).filter((e) => !e.completed);
  personalActive.sort((a, b) => `${a.date} ${a.time}`.localeCompare(`${b.date} ${b.time}`));

  document.getElementById("kpiCoursesCount").textContent = courses.length;
  document.getElementById("kpiPersonalCount").textContent = `${personalActive.length} eventos en calendario personal`;

  const schedule = appData.schedule || [];
  document.getElementById("kpiScheduleCount").textContent = `${schedule.length} bloques`;

  const pomo = appData.pomodoroStats || { completedSessions: 0, totalMinutes: 0 };
  document.getElementById("kpiStudyMinutes").textContent = `${pomo.totalMinutes || 0} min`;
  document.getElementById("kpiStudySessions").textContent = `${pomo.completedSessions || 0} sesiones completadas`;

  // Próximas tareas de Moodle
  const dashTasksEl = document.getElementById("dashboardMoodleTasks");
  if (pending.length === 0) {
    dashTasksEl.innerHTML = prof.linked
      ? `<div style="padding:18px; text-align:center; color:var(--accent-emerald); font-weight:600;">🎉 No tienes entregas pendientes en tu calendario de Moodle.</div>`
      : `<div style="padding:18px; text-align:center; color:var(--text-muted);">
           Todavía no has sincronizado tus tareas de Moodle.
           <div style="margin-top:10px;">
             <button class="btn btn-moodle btn-sm" onclick="switchView('profile')">🔐 Iniciar Sesión en Moodle Sevilla</button>
           </div>
         </div>`;
  } else {
    dashTasksEl.innerHTML = pending.slice(0, 6).map((t) => buildMoodleTaskCardHtml(t)).join("");
  }

  // Eventos personales
  const dashPersEl = document.getElementById("dashboardPersonalEvents");
  if (personalActive.length === 0) {
    dashPersEl.innerHTML = `<div style="padding:14px; color:var(--text-muted);">Tu calendario personal está vacío. Pulsa "+ Añadir Evento" para apuntar exámenes, tutorías o estudio.</div>`;
  } else {
    dashPersEl.innerHTML = personalActive.slice(0, 4).map((ev) => buildPersonalEventCardHtml(ev)).join("");
  }

  // Resumen de Perfil
  document.getElementById("dashboardProfileSummary").innerHTML = `
    <div style="display:flex; justify-content:space-between;">
      <span style="color:var(--text-muted);">Estado:</span>
      <strong style="color:${prof.linked ? 'var(--accent-emerald)' : 'var(--accent-amber)'};">
        ${prof.linked ? '✔ Conectado a Moodle' : '⏳ Pendiente de iniciar sesión'}
      </strong>
    </div>
    <div style="display:flex; justify-content:space-between;">
      <span style="color:var(--text-muted);">Estudiante:</span>
      <strong>${escapeHtml(prof.studentName || prof.username || "Sin configurar")}</strong>
    </div>
    <div style="display:flex; justify-content:space-between;">
      <span style="color:var(--text-muted);">Centro / Plataforma:</span>
      <strong>${escapeHtml(prof.university || "Moodle Centros Sevilla")}</strong>
    </div>
    <div style="display:flex; justify-content:space-between;">
      <span style="color:var(--text-muted);">Última sincronización:</span>
      <span>${escapeHtml(prof.lastSync || "Sin sincronizar")}</span>
    </div>
    <div style="display:flex; gap:8px; margin-top:6px;">
      <button class="btn btn-moodle btn-sm" style="flex:1;" onclick="openMyMoodleCampus()">🌐 Abrir mi Moodle en Google</button>
      <button class="btn btn-outline btn-sm" onclick="resyncMoodleNow()">🔄 Actualizar</button>
    </div>
  `;

  // Cursos sincronizados en el Dashboard
  const dashCoursesEl = document.getElementById("dashboardCoursesList");
  if (courses.length === 0) {
    dashCoursesEl.innerHTML = `<div style="padding:12px; color:var(--text-muted); font-size:12.5px;">Inicia sesión en Moodle para ver aquí todas tus asignaturas matriculadas.</div>`;
  } else {
    dashCoursesEl.innerHTML = courses.map((c) => `
      <div class="task-item" style="border-left-color:${c.color || '#6366f1'}; padding:10px 12px;">
        <div style="flex:1;">
          <div style="font-weight:700; font-size:13.5px; cursor:pointer;" onclick="openInGoogle('${escapeAttr(c.viewurl)}', '${escapeAttr(c.fullname)}', 'direct')">
            📚 ${escapeHtml(c.fullname)}
          </div>
          ${c.shortname ? `<div style="font-size:11px; color:var(--text-muted);">${escapeHtml(c.shortname)}</div>` : ""}
        </div>
        <div style="display:flex; gap:6px;">
          <button class="btn btn-outline btn-sm" onclick="openScheduleModalForCourse('${escapeAttr(c.fullname)}', '${escapeAttr(c.viewurl)}', '${escapeAttr(c.color || '#6366f1')}')" title="Añadir esta asignatura a mi horario">
            ⏰ +Horario
          </button>
          <button class="btn btn-moodle btn-sm" onclick="openInGoogle('${escapeAttr(c.viewurl)}', '${escapeAttr(c.fullname)}', 'direct')">
            🌐 Ir
          </button>
        </div>
      </div>
    `).join("");
  }

  // Clases de hoy
  const jsDay = new Date().getDay();
  const mondayIdx = jsDay === 0 ? 6 : jsDay - 1;
  const todaysClasses = schedule
    .filter((c) => Number(c.day) === mondayIdx)
    .sort((a, b) => (a.startTime || "").localeCompare(b.startTime || ""));

  const todaySchedEl = document.getElementById("dashboardTodaySchedule");
  if (todaysClasses.length === 0) {
    document.getElementById("kpiNextClassText").textContent = "Sin clases asignadas hoy";
    todaySchedEl.innerHTML = `
      <div style="padding:12px; color:var(--text-muted); font-size:13px;">
        No tienes clases apuntadas para hoy (${DAY_NAMES_ES[mondayIdx] || "Domingo"}).
        <br/><a href="javascript:void(0)" onclick="switchView('schedule')" style="color:var(--accent-primary);">Añadir mis clases en el Horario →</a>
      </div>`;
  } else {
    document.getElementById("kpiNextClassText").textContent = `Hoy: ${todaysClasses.length} clases en tu horario`;
    todaySchedEl.innerHTML = todaysClasses.map((c) => `
      <div class="task-item" style="border-left-color:${c.color || '#6366f1'};" onclick="openScheduleModal('${c.id}')">
        <div>
          <div style="font-size:12px; color:var(--accent-cyan); font-family:monospace; font-weight:700;">
            ⏰ ${escapeHtml(c.startTime)} - ${escapeHtml(c.endTime)} • ${escapeHtml(c.type || 'Clase')}
          </div>
          <div style="font-weight:700; font-size:14px; margin-top:2px;">${escapeHtml(c.subject)}</div>
          <div style="font-size:12px; color:var(--text-secondary);">📍 ${escapeHtml(c.room || 'Aula')} ${c.teacher ? '• 👨‍🏫 ' + escapeHtml(c.teacher) : ''}</div>
        </div>
        <button class="btn btn-outline btn-sm" onclick="event.stopPropagation(); openInGoogle('${escapeAttr(c.moodleCourseUrl || '')}', 'Moodle ${escapeAttr(c.subject)}', 'direct')">
          🌐 Curso
        </button>
      </div>
    `).join("");
  }
}

// ---------------------------------------------------------------------------
// VISTA 2: INICIAR SESIÓN EN MOODLE Y SINCRONIZACIÓN REAL
// ---------------------------------------------------------------------------
function applySevillaPlatformPreset(val) {
  if (!val || val === "custom") return;
  const el = document.getElementById("profMoodleEntryUrl");
  if (el) el.value = val;
}

function renderProfileForm() {
  const prof = appData.profile || {};
  const setVal = (id, val) => {
    const el = document.getElementById(id);
    if (el && document.activeElement !== el) el.value = val || "";
  };
  const entryUrl = prof.moodleEntryUrl || DEFAULT_MOODLE_URL;
  setVal("profMoodleEntryUrl", entryUrl);
  setVal("profAuthType", prof.authType || "auto");
  const presetEl = document.getElementById("profPlatformPreset");
  if (presetEl && document.activeElement !== presetEl) {
    const matchOpt = Array.from(presetEl.options).some((o) => o.value === entryUrl);
    presetEl.value = matchOpt ? entryUrl : "custom";
  }
  setVal("profUsername", prof.username || "");
  setVal("profStudentName", prof.studentName || "");
  setVal("profDegree", prof.degree || "");
  setVal("profOpenMode", prof.openMode || "both");
  setVal("profIcsUrl", prof.icsUrl || "");
  setVal("profSessionCookie", prof.sessionCookie || "");
  setVal("profApiToken", prof.apiToken || "");

  const badge = document.getElementById("profileSyncBadge");
  if (badge) {
    badge.textContent = prof.linked ? `Conectado (${prof.lastSync})` : "Sin sesión iniciada";
    badge.className = prof.linked ? "pill done" : "pill soon";
  }

  // Renderizar cursos detectados en la pestaña de perfil
  const coursesContainer = document.getElementById("profileSyncedCoursesContainer");
  if (coursesContainer) {
    const courses = appData.courses || [];
    if (courses.length === 0) {
      coursesContainer.innerHTML = `
        <div style="padding:18px; text-align:center; color:var(--text-muted); font-size:13px;">
          Aún no se han cargado asignaturas. Inicia sesión a la izquierda con tu cuenta de Moodle Centros Sevilla para ver aquí todos tus cursos y tareas reales.
        </div>`;
    } else {
      coursesContainer.innerHTML = courses.map((c) => `
        <div class="task-item" style="border-left-color:${c.color || '#6366f1'};">
          <div style="flex:1;">
            <div style="font-weight:700; font-size:13.5px;">📚 ${escapeHtml(c.fullname)}</div>
            <div style="font-size:11.5px; color:var(--text-muted);">${escapeHtml(c.shortname || '')}</div>
          </div>
          <div style="display:flex; gap:6px;">
            <button class="btn btn-outline btn-sm" onclick="openScheduleModalForCourse('${escapeAttr(c.fullname)}', '${escapeAttr(c.viewurl)}', '${escapeAttr(c.color || '#6366f1')}')">
              ⏰ Añadir a Horario
            </button>
            <button class="btn btn-moodle btn-sm" onclick="openInGoogle('${escapeAttr(c.viewurl)}', '${escapeAttr(c.fullname)}', 'direct')">
              🌐 Abrir en Moodle
            </button>
          </div>
        </div>
      `).join("");
    }
  }
}

function togglePasswordVisibility() {
  const inp = document.getElementById("profPassword");
  if (!inp) return;
  inp.type = inp.type === "password" ? "text" : "password";
}

async function loginAndSyncMoodle(e) {
  if (e) e.preventDefault();
  const btn = document.getElementById("btnLoginMoodleSubmit");
  const originalText = btn ? btn.textContent : "";
  if (btn) {
    btn.disabled = true;
    btn.textContent = "⏳ Conectando con Moodle y descargando tus datos...";
  }

  const authTypeEl = document.getElementById("profAuthType");
  const payload = {
    moodleEntryUrl: document.getElementById("profMoodleEntryUrl").value.trim() || DEFAULT_MOODLE_URL,
    authType: authTypeEl ? authTypeEl.value : "auto",
    username: document.getElementById("profUsername").value.trim(),
    password: document.getElementById("profPassword").value,
    studentName: document.getElementById("profStudentName").value.trim(),
    degree: document.getElementById("profDegree").value.trim(),
    openMode: document.getElementById("profOpenMode").value,
    icsUrl: document.getElementById("profIcsUrl").value.trim(),
    sessionCookie: document.getElementById("profSessionCookie").value.trim(),
    apiToken: document.getElementById("profApiToken").value.trim()
  };

  try {
    const resp = await fetch("/api/login-moodle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const json = await resp.json();
    if (json && json.ok) {
      appData = json.data;
      localStorage.setItem("moodle_assistant_real_state", JSON.stringify(appData));
      renderAll();
      showToast("✅ " + (json.message || "Sesión iniciada y datos sincronizados desde tu Moodle."));
    } else {
      showToast("⚠️ " + (json.error || "No se pudo conectar con Moodle. Revisa usuario/contraseña."), true);
    }
  } catch (err) {
    showToast("⚠️ Error de red al conectar con el servidor local: " + err, true);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = originalText;
    }
  }
}

async function resyncMoodleNow() {
  const prof = (appData && appData.profile) || {};
  const passwordEl = document.getElementById("profPassword");
  const currentPwd = passwordEl ? passwordEl.value : "";

  if (!prof.linked && !currentPwd && !prof.icsUrl && !prof.apiToken && !prof.sessionCookie) {
    switchView("profile");
    showToast("🔐 Introduce tu usuario y contraseña de Moodle para sincronizar.");
    return;
  }

  showToast("🔄 Sincronizando calendario, cursos y tareas desde tu Moodle...");
  try {
    const resp = await fetch("/api/sync-moodle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        moodleEntryUrl: prof.moodleEntryUrl || DEFAULT_MOODLE_URL,
        username: prof.username || "",
        password: currentPwd
      })
    });
    const json = await resp.json();
    if (json && json.ok) {
      appData = json.data;
      localStorage.setItem("moodle_assistant_real_state", JSON.stringify(appData));
      renderAll();
      showToast("✅ " + (json.message || "Datos actualizados desde tu Moodle."));
    } else {
      switchView("profile");
      showToast("⚠️ " + (json.error || "Inicia sesión de nuevo para sincronizar."), true);
    }
  } catch (_e) {
    showToast("⚠️ No se pudo conectar con el servidor local.", true);
  }
}

function handleIcsFileSelected(event) {
  const file = event.target.files && event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = async (ev) => {
    const icsContent = ev.target.result;
    try {
      const resp = await fetch("/api/sync-moodle", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ icsContent })
      });
      const json = await resp.json();
      if (json && json.ok) {
        appData = json.data;
        renderAll();
        showToast("📅 " + json.message);
      } else {
        showToast("⚠️ No se pudo procesar el archivo .ics", true);
      }
    } catch (_err) {
      showToast("⚠️ Error leyendo archivo .ics", true);
    }
  };
  reader.readAsText(file);
}

// ---------------------------------------------------------------------------
// VISTA 3: MIS TAREAS DE MOODLE
// ---------------------------------------------------------------------------
function setTaskFilter(filterVal, btnEl) {
  currentTaskFilter = filterVal;
  document.querySelectorAll("#taskFilterTabs .filter-tab").forEach((b) => b.classList.remove("active"));
  if (btnEl) btnEl.classList.add("active");
  renderTasksView();
}

function renderTasksView() {
  const tasks = appData.moodleTasks || [];

  const courseSelect = document.getElementById("taskCourseFilter");
  const selectedCourse = courseSelect ? courseSelect.value : "all";
  const coursesFromProfile = (appData.courses || []).map((c) => c.fullname);
  const coursesFromTasks = tasks.map((t) => t.course);
  const courses = Array.from(new Set([...coursesFromProfile, ...coursesFromTasks].filter(Boolean)));

  if (courseSelect) {
    courseSelect.innerHTML = `<option value="all">Todas las asignaturas (${courses.length})</option>` +
      courses.map((c) => `<option value="${escapeAttr(c)}" ${c === selectedCourse ? "selected" : ""}>${escapeHtml(c)}</option>`).join("");
  }

  let filtered = tasks.slice();
  if (currentTaskFilter !== "all") {
    filtered = filtered.filter((t) => t.status === currentTaskFilter);
  }
  if (selectedCourse && selectedCourse !== "all") {
    filtered = filtered.filter((t) => t.course === selectedCourse);
  }
  if (globalSearchQuery) {
    filtered = filtered.filter((t) =>
      (t.title || "").toLowerCase().includes(globalSearchQuery) ||
      (t.course || "").toLowerCase().includes(globalSearchQuery) ||
      (t.description || "").toLowerCase().includes(globalSearchQuery)
    );
  }

  filtered.sort((a, b) => `${a.dueDate} ${a.dueTime}`.localeCompare(`${b.dueDate} ${b.dueTime}`));

  const container = document.getElementById("allTasksListContainer");
  if (!container) return;

  if (filtered.length === 0) {
    container.innerHTML = `
      <div style="padding:28px; text-align:center; color:var(--text-muted);">
        No hay tareas para mostrar en este filtro.
        <div style="margin-top:10px; display:flex; justify-content:center; gap:10px;">
          <button class="btn btn-moodle btn-sm" onclick="switchView('profile')">🔐 Sincronizar con mi Moodle</button>
          <button class="btn btn-primary btn-sm" onclick="openTaskModal()">+ Añadir Tarea Manual</button>
        </div>
      </div>`;
    return;
  }

  container.innerHTML = filtered.map((t) => buildMoodleTaskCardHtml(t, true)).join("");
}

function buildMoodleTaskCardHtml(t, showFullActions = false) {
  const isDone = t.status === "completed";
  const daysLeft = getDaysRemaining(t.dueDate);
  let badgeHtml = "";
  if (isDone) {
    badgeHtml = `<span class="pill done">✔ Entregada</span>`;
  } else if (daysLeft < 0) {
    badgeHtml = `<span class="pill urgent">⚠️ Vencida (${Math.abs(daysLeft)}d)</span>`;
  } else if (daysLeft === 0) {
    badgeHtml = `<span class="pill urgent">🔥 Vence HOY a las ${escapeHtml(t.dueTime)}</span>`;
  } else if (daysLeft <= 3) {
    badgeHtml = `<span class="pill urgent">⏳ Faltan ${daysLeft} días</span>`;
  } else {
    badgeHtml = `<span class="pill soon">📅 En ${daysLeft} días</span>`;
  }

  return `
    <div class="task-item ${isDone ? 'completed' : ''}" style="border-left-color:${t.color || '#6366f1'};">
      <div class="task-left">
        <input type="checkbox" class="task-check" ${isDone ? "checked" : ""} onchange="toggleTaskCompleted('${t.id}', this.checked)" title="Marcar como entregada / pendiente" />
        <div style="flex:1;">
          <div class="task-title" onclick="openTaskInGoogle('${t.id}', false)" title="Pincha para abrir esta tarea de Moodle en Google Chrome">
            ${escapeHtml(t.title)}
          </div>
          <div class="task-meta">
            <span class="pill" style="background:${t.color || '#6366f1'}33; color:#e0e7ff; border:1px solid ${t.color || '#6366f1'}66;">
              🎓 ${escapeHtml(t.course)}
            </span>
            <span>📅 ${formatDateReadable(t.dueDate)} (${escapeHtml(t.dueTime || '23:55')})</span>
            ${badgeHtml}
          </div>
          ${t.description ? `<div style="font-size:12px; color:var(--text-muted); margin-top:5px;">${escapeHtml(t.description)}</div>` : ""}
        </div>
      </div>
      <div class="task-actions">
        <button class="btn btn-moodle btn-sm" onclick="openTaskInGoogle('${t.id}', false)" title="Ir a la tarea en Google Chrome">
          🌐 Ir en Google
        </button>
        ${showFullActions ? `
          <button class="btn btn-outline btn-sm" onclick="openTaskInGoogle('${t.id}', true)" title="Buscar en Google">
            🔍 Buscar
          </button>
          <button class="btn btn-outline btn-sm" onclick="openTaskModal('${t.id}')" title="Editar tarea">✏️</button>
          <button class="btn btn-danger btn-sm" onclick="deleteMoodleTask('${t.id}')" title="Eliminar tarea">🗑️</button>
        ` : ""}
      </div>
    </div>
  `;
}

async function toggleTaskCompleted(taskId, checked) {
  const t = (appData.moodleTasks || []).find((x) => x.id === taskId);
  if (!t) return;
  t.status = checked ? "completed" : "pending";
  await persistState(checked ? "✅ Tarea marcada como entregada" : "↩️ Tarea marcada como pendiente");
}

async function deleteMoodleTask(taskId) {
  appData.moodleTasks = (appData.moodleTasks || []).filter((x) => x.id !== taskId);
  await persistState("🗑️ Tarea eliminada.");
}

// ---------------------------------------------------------------------------
// VISTA 4: CALENDARIO OFICIAL DE MOODLE (CLIC -> LLEVA A ELLA EN GOOGLE)
// ---------------------------------------------------------------------------
function changeMoodleCalMonth(delta) {
  moodleCalMonth += delta;
  if (moodleCalMonth < 0) {
    moodleCalMonth = 11;
    moodleCalYear--;
  } else if (moodleCalMonth > 11) {
    moodleCalMonth = 0;
    moodleCalYear++;
  }
  moodleSelectedDay = null;
  renderMoodleCalendar();
}

function resetMoodleCalToday() {
  const d = new Date();
  moodleCalYear = d.getFullYear();
  moodleCalMonth = d.getMonth();
  moodleSelectedDay = toIsoDate(d);
  renderMoodleCalendar();
}

function clearMoodleDayFilter() {
  moodleSelectedDay = null;
  renderMoodleCalendar();
}

function renderMoodleCalendar() {
  const titleEl = document.getElementById("moodleCalMonthTitle");
  if (titleEl) titleEl.textContent = `${MONTH_NAMES_ES[moodleCalMonth]} ${moodleCalYear}`;

  const gridEl = document.getElementById("moodleCalendarGrid");
  if (!gridEl) return;

  const cells = buildMonthCells(moodleCalYear, moodleCalMonth);
  const todayIso = toIsoDate(new Date());
  const tasks = appData.moodleTasks || [];

  gridEl.innerHTML = cells.map((cell) => {
    const dayTasks = tasks.filter((t) => t.dueDate === cell.iso);
    const isToday = cell.iso === todayIso;
    const isSelected = cell.iso === moodleSelectedDay;

    const chipsHtml = dayTasks.map((t) => `
      <div class="cal-event-chip"
           style="background:${t.color || '#f97316'}; ${t.status === 'completed' ? 'opacity:0.5; text-decoration:line-through;' : ''}"
           onclick="event.stopPropagation(); openTaskInGoogle('${t.id}', false)"
           title="🌐 Pincha para abrir '${escapeAttr(t.title)}' (${escapeAttr(t.course)}) en Google Chrome">
        🌐 ${escapeHtml(t.dueTime || '')} ${escapeHtml(t.title)}
      </div>
    `).join("");

    return `
      <div class="cal-cell ${cell.inMonth ? '' : 'other-month'} ${isToday ? 'today' : ''} ${isSelected ? 'selected' : ''}"
           onclick="selectMoodleCalDay('${cell.iso}')">
        <div class="cal-day-num">
          <span>${cell.dayNum}</span>
          ${dayTasks.length > 0 ? `<span class="pill" style="font-size:10px; padding:1px 6px;">${dayTasks.length}</span>` : ""}
        </div>
        ${chipsHtml}
      </div>
    `;
  }).join("");

  const sideTitleEl = document.getElementById("moodleCalSideTitle");
  const sideListEl = document.getElementById("moodleCalSideList");
  let sideTasks = [];

  if (moodleSelectedDay) {
    sideTitleEl.textContent = `Entregas del ${formatDateReadable(moodleSelectedDay)}`;
    sideTasks = tasks.filter((t) => t.dueDate === moodleSelectedDay);
  } else {
    const monthPrefix = `${moodleCalYear}-${String(moodleCalMonth + 1).padStart(2, "0")}`;
    sideTitleEl.textContent = `Entregas en ${MONTH_NAMES_ES[moodleCalMonth]} ${moodleCalYear}`;
    sideTasks = tasks.filter((t) => (t.dueDate || "").startsWith(monthPrefix));
  }

  sideTasks.sort((a, b) => `${a.dueDate} ${a.dueTime}`.localeCompare(`${b.dueDate} ${b.dueTime}`));

  if (sideTasks.length === 0) {
    sideListEl.innerHTML = `
      <div style="padding:18px; text-align:center; color:var(--text-muted);">
        No hay tareas de Moodle en este periodo.
        <div style="margin-top:10px; display:flex; gap:8px; justify-content:center; flex-wrap:wrap;">
          <button class="btn btn-moodle btn-sm" onclick="resyncMoodleNow()">🔄 Sincronizar Moodle</button>
          <button class="btn btn-primary btn-sm" onclick="openTaskModal('', '${moodleSelectedDay || toIsoDate(new Date())}')">+ Añadir entrega</button>
        </div>
      </div>`;
  } else {
    sideListEl.innerHTML = sideTasks.map((t) => buildMoodleTaskCardHtml(t, true)).join("");
  }
}

function selectMoodleCalDay(isoDate) {
  moodleSelectedDay = isoDate;
  renderMoodleCalendar();
}

// ---------------------------------------------------------------------------
// VISTA 5: MI CALENDARIO PERSONAL (AÑADIR COSAS PROPIAS)
// ---------------------------------------------------------------------------
function changePersonalCalMonth(delta) {
  personalCalMonth += delta;
  if (personalCalMonth < 0) {
    personalCalMonth = 11;
    personalCalYear--;
  } else if (personalCalMonth > 11) {
    personalCalMonth = 0;
    personalCalYear++;
  }
  personalSelectedDay = null;
  renderPersonalCalendar();
}

function resetPersonalCalToday() {
  const d = new Date();
  personalCalYear = d.getFullYear();
  personalCalMonth = d.getMonth();
  personalSelectedDay = toIsoDate(d);
  const qpDate = document.getElementById("qpDate");
  if (qpDate) qpDate.value = personalSelectedDay;
  renderPersonalCalendar();
}

function clearPersonalDayFilter() {
  personalSelectedDay = null;
  renderPersonalCalendar();
}

function renderPersonalCalendar() {
  const titleEl = document.getElementById("personalCalMonthTitle");
  if (titleEl) titleEl.textContent = `${MONTH_NAMES_ES[personalCalMonth]} ${personalCalYear}`;

  const gridEl = document.getElementById("personalCalendarGrid");
  if (!gridEl) return;

  const cells = buildMonthCells(personalCalYear, personalCalMonth);
  const todayIso = toIsoDate(new Date());
  const events = appData.personalEvents || [];

  gridEl.innerHTML = cells.map((cell) => {
    const dayEvents = events.filter((ev) => ev.date === cell.iso);
    const isToday = cell.iso === todayIso;
    const isSelected = cell.iso === personalSelectedDay;

    const chipsHtml = dayEvents.map((ev) => `
      <div class="cal-event-chip"
           style="background:${ev.color || '#06b6d4'}; ${ev.completed ? 'opacity:0.45; text-decoration:line-through;' : ''}"
           onclick="event.stopPropagation(); openPersonalEventModal('${ev.id}')"
           title="${escapeAttr(ev.title)} (${escapeAttr(ev.time || '')})">
        📌 ${escapeHtml(ev.time || '')} ${escapeHtml(ev.title)}
      </div>
    `).join("");

    return `
      <div class="cal-cell ${cell.inMonth ? '' : 'other-month'} ${isToday ? 'today' : ''} ${isSelected ? 'selected' : ''}"
           onclick="selectPersonalCalDay('${cell.iso}')">
        <div class="cal-day-num">
          <span>${cell.dayNum}</span>
          ${dayEvents.length > 0 ? `<span class="pill" style="font-size:10px; padding:1px 6px;">${dayEvents.length}</span>` : ""}
        </div>
        ${chipsHtml}
      </div>
    `;
  }).join("");

  const sideTitleEl = document.getElementById("personalCalSideTitle");
  const sideListEl = document.getElementById("personalCalSideList");
  let listEvents = [];

  if (personalSelectedDay) {
    sideTitleEl.textContent = `Eventos del ${formatDateReadable(personalSelectedDay)}`;
    listEvents = events.filter((e) => e.date === personalSelectedDay);
  } else {
    sideTitleEl.textContent = "Todos Mis Eventos Personales";
    listEvents = events.slice();
  }

  listEvents.sort((a, b) => `${a.date} ${a.time}`.localeCompare(`${b.date} ${b.time}`));

  if (listEvents.length === 0) {
    sideListEl.innerHTML = `<div style="padding:16px; text-align:center; color:var(--text-muted);">No hay eventos en esta fecha. Usa el formulario superior para añadir tus propios recordatorios o exámenes.</div>`;
  } else {
    sideListEl.innerHTML = listEvents.map((ev) => buildPersonalEventCardHtml(ev)).join("");
  }
}

function selectPersonalCalDay(isoDate) {
  personalSelectedDay = isoDate;
  const qpDate = document.getElementById("qpDate");
  if (qpDate) qpDate.value = isoDate;
  renderPersonalCalendar();
}

function buildPersonalEventCardHtml(ev) {
  return `
    <div class="task-item ${ev.completed ? 'completed' : ''}" style="border-left-color:${ev.color || '#38bdf8'};">
      <div class="task-left">
        <input type="checkbox" class="task-check" ${ev.completed ? "checked" : ""} onchange="togglePersonalEventDone('${ev.id}', this.checked)" />
        <div>
          <div class="task-title" onclick="openPersonalEventModal('${ev.id}')">${escapeHtml(ev.title)}</div>
          <div class="task-meta">
            <span class="pill">${escapeHtml(ev.category || 'Personal')}</span>
            <span>📅 ${formatDateReadable(ev.date)} • ⏰ ${escapeHtml(ev.time || '')}</span>
          </div>
          ${ev.notes ? `<div style="font-size:12px; color:var(--text-muted); margin-top:4px;">${escapeHtml(ev.notes)}</div>` : ""}
        </div>
      </div>
      <div class="task-actions">
        <button class="btn btn-outline btn-sm" onclick="openPersonalEventModal('${ev.id}')">✏️</button>
        <button class="btn btn-danger btn-sm" onclick="deletePersonalEvent('${ev.id}')">🗑️</button>
      </div>
    </div>
  `;
}

async function saveQuickPersonalEvent(e) {
  e.preventDefault();
  const title = document.getElementById("qpTitle").value.trim();
  const date = document.getElementById("qpDate").value;
  const time = document.getElementById("qpTime").value || "17:00";
  const category = document.getElementById("qpCategory").value;
  if (!title || !date) return;

  const colorMap = {
    "Estudio": "#38bdf8",
    "Examen": "#f43f5e",
    "Tutoría": "#a855f7",
    "Grupo": "#10b981",
    "Personal": "#f59e0b"
  };

  appData.personalEvents = appData.personalEvents || [];
  appData.personalEvents.push({
    id: "pers-" + Date.now(),
    title,
    date,
    time,
    category,
    color: colorMap[category] || "#38bdf8",
    notes: "",
    completed: false
  });

  document.getElementById("qpTitle").value = "";
  await persistState("🗓️ Evento añadido a tu Calendario Personal.");
}

async function togglePersonalEventDone(evId, done) {
  const ev = (appData.personalEvents || []).find((x) => x.id === evId);
  if (!ev) return;
  ev.completed = done;
  await persistState(done ? "✅ Recordatorio completado" : "↩️ Recordatorio reactivado");
}

async function deletePersonalEvent(evId) {
  appData.personalEvents = (appData.personalEvents || []).filter((x) => x.id !== evId);
  await persistState("🗑️ Evento eliminado de tu calendario personal.");
}

// ---------------------------------------------------------------------------
// VISTA 6: HORARIO DE CLASES MODIFICABLE
// ---------------------------------------------------------------------------
function renderWeeklySchedule() {
  const grid = document.getElementById("weeklyScheduleGrid");
  if (!grid) return;

  const schedule = appData.schedule || [];
  const jsDay = new Date().getDay();
  const todayIdx = jsDay === 0 ? 6 : jsDay - 1;

  grid.innerHTML = DAY_NAMES_ES.map((dayName, dayIdx) => {
    const dayClasses = schedule
      .filter((c) => Number(c.day) === dayIdx)
      .sort((a, b) => (a.startTime || "").localeCompare(b.startTime || ""));

    const blocksHtml = dayClasses.length === 0
      ? `<div style="font-size:12px; color:var(--text-muted); text-align:center; padding:24px 6px;">
           Sin clases<br/>
           <button class="btn btn-outline btn-sm" style="margin-top:8px; font-size:11px;" onclick="openScheduleModal('', ${dayIdx})">+ Añadir</button>
         </div>`
      : dayClasses.map((c) => `
          <div class="class-block" style="border-left-color:${c.color || '#6366f1'};" onclick="openScheduleModal('${c.id}')" title="Haz clic para modificar o eliminar esta clase">
            <div class="class-time">${escapeHtml(c.startTime)} - ${escapeHtml(c.endTime)}</div>
            <div class="class-subject">${escapeHtml(c.subject)}</div>
            <div class="class-details">
              <span>📍 ${escapeHtml(c.room || 'Aula')} • <strong style="color:#e2e8f0;">${escapeHtml(c.type || 'Teoría')}</strong></span>
              ${c.teacher ? `<span>👨‍🏫 ${escapeHtml(c.teacher)}</span>` : ""}
            </div>
          </div>
        `).join("");

    return `
      <div class="schedule-day-col ${dayIdx === todayIdx ? 'today-col' : ''}">
        <div class="schedule-day-header">
          <span>${dayName} ${dayIdx === todayIdx ? '<span class="pill done" style="font-size:10px;">HOY</span>' : ''}</span>
          <button class="btn btn-outline btn-sm" style="padding:2px 7px;" onclick="openScheduleModal('', ${dayIdx})" title="Añadir clase el ${dayName}">+</button>
        </div>
        ${blocksHtml}
      </div>
    `;
  }).join("");
}

function autoFillScheduleCourseUrl(subjectVal) {
  const match = (appData.courses || []).find(
    (c) => (c.fullname || "").toLowerCase() === (subjectVal || "").trim().toLowerCase()
  );
  if (match) {
    const urlInput = document.getElementById("smMoodleUrl");
    const colorInput = document.getElementById("smColor");
    if (urlInput && !urlInput.value) urlInput.value = match.viewurl || "";
    if (colorInput && match.color) colorInput.value = match.color;
  }
}

function openScheduleModalForCourse(courseName, courseUrl, courseColor) {
  switchView("schedule");
  openScheduleModal("", 0);
  document.getElementById("smSubject").value = courseName || "";
  document.getElementById("smMoodleUrl").value = courseUrl || "";
  if (courseColor) document.getElementById("smColor").value = courseColor;
}

// ---------------------------------------------------------------------------
// VISTA 7: ESTUDIO POMODORO, CALCULADORA DE NOTAS Y NOTAS RÁPIDAS
// ---------------------------------------------------------------------------
function renderStudioView() {
  const selectEl = document.getElementById("pomoLinkedTaskSelect");
  if (selectEl) {
    const prev = selectEl.value;
    const pending = (appData.moodleTasks || []).filter((t) => t.status !== "completed");
    selectEl.innerHTML = `<option value="">🎯 Vincular sesión a una tarea de Moodle...</option>` +
      pending.map((t) => `<option value="${t.id}" ${t.id === prev ? "selected" : ""}>[${escapeHtml(t.course)}] ${escapeHtml(t.title)}</option>`).join("");
  }

  const gradesContainer = document.getElementById("gradesCalculatorContainer");
  if (gradesContainer) {
    const grades = appData.grades || [];
    if (grades.length === 0) {
      gradesContainer.innerHTML = `
        <div style="padding:18px; text-align:center; color:var(--text-muted);">
          Inicia sesión en Moodle para cargar automáticamente tus asignaturas y calificaciones, o pulsa "+ Añadir Asignatura".
        </div>`;
    } else {
      gradesContainer.innerHTML = grades.map((g, gIdx) => {
        let earnedWeighted = 0;
        let completedWeight = 0;
        let remainingWeight = 0;

        (g.items || []).forEach((it) => {
          const w = Number(it.weight) || 0;
          if (it.score !== null && it.score !== "" && !isNaN(Number(it.score))) {
            earnedWeighted += (Number(it.score) * w) / 100;
            completedWeight += w;
          } else {
            remainingWeight += w;
          }
        });

        const currentAvg = completedWeight > 0 ? ((earnedWeighted / completedWeight) * 100).toFixed(2) : "—";
        const neededForPass = remainingWeight > 0
          ? Math.max(0, ((5.0 - earnedWeighted) / (remainingWeight / 100))).toFixed(2)
          : "0.00";
        const neededForTarget = remainingWeight > 0
          ? Math.max(0, (((g.targetGrade || 7.0) - earnedWeighted) / (remainingWeight / 100))).toFixed(2)
          : "0.00";

        const rowsHtml = (g.items || []).map((it, iIdx) => `
          <div style="display:grid; grid-template-columns: 1.5fr 90px 90px 34px; gap:8px; align-items:center; margin-top:6px;">
            <input type="text" class="form-control" style="padding:5px 8px; font-size:12.5px;" value="${escapeAttr(it.name)}"
                   onchange="updateGradeItem(${gIdx}, ${iIdx}, 'name', this.value)" />
            <input type="number" class="form-control" style="padding:5px 8px; font-size:12.5px;" value="${it.weight}" min="0" max="100"
                   onchange="updateGradeItem(${gIdx}, ${iIdx}, 'weight', this.value)" title="Peso %" placeholder="% Peso" />
            <input type="number" step="0.1" min="0" max="10" class="form-control" style="padding:5px 8px; font-size:12.5px;"
                   value="${it.score !== null && it.score !== undefined ? it.score : ''}"
                   placeholder="Nota / 10"
                   onchange="updateGradeItem(${gIdx}, ${iIdx}, 'score', this.value)" title="Nota sobre 10" />
            <button class="btn btn-danger btn-sm" style="padding:4px;" onclick="removeGradeItem(${gIdx}, ${iIdx})">✕</button>
          </div>
        `).join("");

        return `
          <div style="background:var(--bg-elevated); border:1px solid var(--border-subtle); border-left:4px solid ${g.color || '#6366f1'}; border-radius:10px; padding:14px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
              <strong style="font-size:14.5px;">📚 ${escapeHtml(g.subject)}</strong>
              <div style="display:flex; gap:6px;">
                <button class="btn btn-outline btn-sm" onclick="addGradeItem(${gIdx})">+ Evaluable</button>
                <button class="btn btn-danger btn-sm" onclick="deleteGradeSubject(${gIdx})">🗑️</button>
              </div>
            </div>
            <div style="display:flex; gap:14px; flex-wrap:wrap; font-size:12px; color:var(--text-secondary); margin-bottom:8px; background:var(--bg-surface); padding:8px 10px; border-radius:8px;">
              <span>Media actual: <strong style="color:var(--accent-emerald);">${currentAvg}/10</strong></span>
              <span>Puntos acumulados: <strong>${earnedWeighted.toFixed(2)} pts</strong> (${completedWeight}% evaluado)</span>
              <span>Necesitas para Aprobar (5.0): <strong style="color:#fde68a;">${neededForPass}/10</strong></span>
              <span>Para Objetivo (${g.targetGrade || 7}): <strong style="color:#93c5fd;">${neededForTarget}/10</strong></span>
            </div>
            ${rowsHtml}
          </div>
        `;
      }).join("");
    }
  }

  const notesContainer = document.getElementById("quickNotesContainer");
  if (notesContainer) {
    const notes = appData.notes || [];
    if (notes.length === 0) {
      notesContainer.innerHTML = `<div style="color:var(--text-muted); text-align:center; padding:16px;">No hay apuntes rápidos guardados todavía.</div>`;
    } else {
      notesContainer.innerHTML = notes.map((n) => `
        <div class="task-item" style="border-left-color:${n.color || '#6366f1'}; align-items:flex-start;">
          <div style="flex:1;">
            <div style="display:flex; align-items:center; gap:8px;">
              <strong style="font-size:14px;">${escapeHtml(n.title)}</strong>
              <span class="pill">${escapeHtml(n.course || 'General')}</span>
            </div>
            <pre style="white-space:pre-wrap; font-family:inherit; font-size:12.5px; color:var(--text-secondary); margin-top:6px;">${escapeHtml(n.content)}</pre>
          </div>
          <button class="btn btn-danger btn-sm" onclick="deleteQuickNote('${n.id}')">🗑️</button>
        </div>
      `).join("");
    }
  }
}

function setPomodoroPreset(minutes, label) {
  resetWebPomodoro();
  pomoTotalSeconds = minutes * 60;
  pomoRemainingSeconds = pomoTotalSeconds;
  document.getElementById("pomoModeLabel").textContent = label;
  updatePomoDigits();
}

function updatePomoDigits() {
  const m = Math.floor(pomoRemainingSeconds / 60);
  const s = pomoRemainingSeconds % 60;
  const el = document.getElementById("pomoDigits");
  if (el) el.textContent = `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function toggleWebPomodoro() {
  const btn = document.getElementById("btnPomoStart");
  pomoRunning = !pomoRunning;
  if (pomoRunning) {
    btn.textContent = "⏸ Pausar";
    pomoInterval = setInterval(async () => {
      if (pomoRemainingSeconds > 0) {
        pomoRemainingSeconds--;
        updatePomoDigits();
      } else {
        clearInterval(pomoInterval);
        pomoRunning = false;
        btn.textContent = "▶ Iniciar Enfoque";
        playCompletionBeep();
        appData.pomodoroStats = appData.pomodoroStats || { completedSessions: 0, totalMinutes: 0 };
        appData.pomodoroStats.completedSessions += 1;
        appData.pomodoroStats.totalMinutes += Math.round(pomoTotalSeconds / 60);
        pomoRemainingSeconds = pomoTotalSeconds;
        updatePomoDigits();
        await persistState("🍅 ¡Sesión Pomodoro completada! Tiempo sumado a tus estadísticas.");
      }
    }, 1000);
  } else {
    clearInterval(pomoInterval);
    btn.textContent = "▶ Reanudar";
  }
}

function resetWebPomodoro() {
  clearInterval(pomoInterval);
  pomoRunning = false;
  pomoRemainingSeconds = pomoTotalSeconds;
  updatePomoDigits();
  const btn = document.getElementById("btnPomoStart");
  if (btn) btn.textContent = "▶ Iniciar Enfoque";
}

function playCompletionBeep() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.value = 660;
    gain.gain.value = 0.12;
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    setTimeout(() => osc.stop(), 350);
  } catch (_e) {}
}

async function updateGradeItem(gIdx, iIdx, field, val) {
  const item = appData.grades[gIdx].items[iIdx];
  if (field === "name") item.name = val;
  if (field === "weight") item.weight = Number(val) || 0;
  if (field === "score") item.score = val === "" ? null : Number(val);
  await persistState();
}

async function addGradeItem(gIdx) {
  appData.grades[gIdx].items.push({ name: "Actividad Moodle", weight: 10, score: null });
  await persistState();
}

async function removeGradeItem(gIdx, iIdx) {
  appData.grades[gIdx].items.splice(iIdx, 1);
  await persistState();
}

async function addNewGradeSubject() {
  const name = prompt("Nombre de la asignatura:");
  if (!name || !name.trim()) return;
  appData.grades = appData.grades || [];
  appData.grades.push({
    id: "grd-" + Date.now(),
    subject: name.trim(),
    color: "#6366f1",
    targetGrade: 7.0,
    items: [
      { name: "Actividades Moodle", weight: 40, score: null },
      { name: "Examen Final", weight: 60, score: null }
    ]
  });
  await persistState("📊 Asignatura añadida a la calculadora.");
}

async function deleteGradeSubject(gIdx) {
  appData.grades.splice(gIdx, 1);
  await persistState("🗑️ Asignatura eliminada de la calculadora.");
}

async function addQuickNote(e) {
  e.preventDefault();
  const title = document.getElementById("noteTitleInput").value.trim();
  const course = document.getElementById("noteCourseInput").value.trim() || "General";
  const content = document.getElementById("noteContentInput").value.trim();
  if (!title || !content) return;

  appData.notes = appData.notes || [];
  appData.notes.unshift({
    id: "note-" + Date.now(),
    title,
    course,
    content,
    color: "#6366f1",
    updatedAt: toIsoDate(new Date())
  });

  document.getElementById("noteTitleInput").value = "";
  document.getElementById("noteContentInput").value = "";
  await persistState("📝 Nota rápida guardada.");
}

async function deleteQuickNote(noteId) {
  appData.notes = (appData.notes || []).filter((n) => n.id !== noteId);
  await persistState("🗑️ Nota eliminada.");
}

// ---------------------------------------------------------------------------
// MODALES DE CREACIÓN Y EDICIÓN
// ---------------------------------------------------------------------------
function openTaskModal(taskId = "", defaultDate = "") {
  const modal = document.getElementById("taskModalBackdrop");
  const existing = (appData.moodleTasks || []).find((t) => t.id === taskId);

  document.getElementById("tmId").value = existing ? existing.id : "";
  document.getElementById("tmTitle").value = existing ? existing.title : "";
  document.getElementById("tmCourse").value = existing ? existing.course : "";
  document.getElementById("tmCourseCode").value = existing ? (existing.courseCode || "") : "";
  document.getElementById("tmDueDate").value = existing ? existing.dueDate : (defaultDate || toIsoDate(new Date()));
  document.getElementById("tmDueTime").value = existing ? (existing.dueTime || "23:55") : "23:55";
  document.getElementById("tmPriority").value = existing ? (existing.priority || "medium") : "medium";
  document.getElementById("tmColor").value = existing ? (existing.color || "#6366f1") : "#6366f1";
  document.getElementById("tmMoodleUrl").value = existing ? (existing.moodleUrl || "") : "";
  document.getElementById("tmDescription").value = existing ? (existing.description || "") : "";

  modal.classList.add("open");
}

function closeTaskModal() {
  document.getElementById("taskModalBackdrop").classList.remove("open");
}

async function submitTaskModal(e) {
  e.preventDefault();
  const id = document.getElementById("tmId").value;
  const title = document.getElementById("tmTitle").value.trim();
  const course = document.getElementById("tmCourse").value.trim();
  const courseCode = document.getElementById("tmCourseCode").value.trim() || course.slice(0, 6).toUpperCase();
  const dueDate = document.getElementById("tmDueDate").value;
  const dueTime = document.getElementById("tmDueTime").value || "23:55";
  const priority = document.getElementById("tmPriority").value;
  const color = document.getElementById("tmColor").value;
  let moodleUrl = document.getElementById("tmMoodleUrl").value.trim();
  const description = document.getElementById("tmDescription").value.trim();

  if (!moodleUrl) {
    const matchedCourse = (appData.courses || []).find((c) => (c.fullname || "").toLowerCase() === course.toLowerCase());
    if (matchedCourse && matchedCourse.viewurl) {
      moodleUrl = matchedCourse.viewurl;
    } else {
      moodleUrl = `https://www.google.com/search?q=${encodeURIComponent("Moodle " + course + " " + title)}`;
    }
  }

  appData.moodleTasks = appData.moodleTasks || [];
  if (id) {
    const idx = appData.moodleTasks.findIndex((t) => t.id === id);
    if (idx >= 0) {
      appData.moodleTasks[idx] = Object.assign(appData.moodleTasks[idx], {
        title, course, courseCode, dueDate, dueTime, priority, color, moodleUrl, description
      });
    }
  } else {
    appData.moodleTasks.push({
      id: "moodle-manual-" + Date.now(),
      title,
      course,
      courseCode,
      dueDate,
      dueTime,
      status: "pending",
      priority,
      color,
      moodleUrl,
      description,
      source: "moodle"
    });
  }

  closeTaskModal();
  await persistState("🎓 Tarea guardada en el Calendario de Moodle.");
}

function openPersonalEventModal(evId = "") {
  const modal = document.getElementById("personalEventModalBackdrop");
  const existing = (appData.personalEvents || []).find((x) => x.id === evId);

  document.getElementById("pmId").value = existing ? existing.id : "";
  document.getElementById("pmTitle").value = existing ? existing.title : "";
  document.getElementById("pmDate").value = existing ? existing.date : (personalSelectedDay || toIsoDate(new Date()));
  document.getElementById("pmTime").value = existing ? (existing.time || "17:00") : "17:00";
  document.getElementById("pmCategory").value = existing ? (existing.category || "Estudio") : "Estudio";
  document.getElementById("pmColor").value = existing ? (existing.color || "#38bdf8") : "#38bdf8";
  document.getElementById("pmNotes").value = existing ? (existing.notes || "") : "";

  modal.classList.add("open");
}

function closePersonalEventModal() {
  document.getElementById("personalEventModalBackdrop").classList.remove("open");
}

async function submitPersonalEventModal(e) {
  e.preventDefault();
  const id = document.getElementById("pmId").value;
  const title = document.getElementById("pmTitle").value.trim();
  const date = document.getElementById("pmDate").value;
  const time = document.getElementById("pmTime").value;
  const category = document.getElementById("pmCategory").value;
  const color = document.getElementById("pmColor").value;
  const notes = document.getElementById("pmNotes").value.trim();

  appData.personalEvents = appData.personalEvents || [];
  if (id) {
    const idx = appData.personalEvents.findIndex((x) => x.id === id);
    if (idx >= 0) {
      appData.personalEvents[idx] = Object.assign(appData.personalEvents[idx], {
        title, date, time, category, color, notes
      });
    }
  } else {
    appData.personalEvents.push({
      id: "pers-" + Date.now(),
      title,
      date,
      time,
      category,
      color,
      notes,
      completed: false
    });
  }

  closePersonalEventModal();
  await persistState("🗓️ Evento guardado en Mi Calendario Personal.");
}

function openScheduleModal(schedId = "", defaultDay = 0) {
  const modal = document.getElementById("scheduleModalBackdrop");
  const existing = (appData.schedule || []).find((x) => x.id === schedId);

  document.getElementById("smId").value = existing ? existing.id : "";
  document.getElementById("smSubject").value = existing ? existing.subject : "";
  document.getElementById("smDay").value = existing ? Number(existing.day) : defaultDay;
  document.getElementById("smType").value = existing ? (existing.type || "Teoría") : "Teoría";
  document.getElementById("smStartTime").value = existing ? existing.startTime : "08:15";
  document.getElementById("smEndTime").value = existing ? existing.endTime : "09:15";
  document.getElementById("smRoom").value = existing ? existing.room : "";
  document.getElementById("smTeacher").value = existing ? (existing.teacher || "") : "";
  document.getElementById("smColor").value = existing ? (existing.color || "#6366f1") : "#6366f1";
  document.getElementById("smMoodleUrl").value = existing ? (existing.moodleCourseUrl || "") : "";

  document.getElementById("btnDeleteClassModal").style.display = existing ? "inline-flex" : "none";
  modal.classList.add("open");
}

function closeScheduleModal() {
  document.getElementById("scheduleModalBackdrop").classList.remove("open");
}

async function submitScheduleModal(e) {
  e.preventDefault();
  const id = document.getElementById("smId").value;
  const subject = document.getElementById("smSubject").value.trim();
  const day = Number(document.getElementById("smDay").value);
  const type = document.getElementById("smType").value;
  const startTime = document.getElementById("smStartTime").value;
  const endTime = document.getElementById("smEndTime").value;
  const room = document.getElementById("smRoom").value.trim();
  const teacher = document.getElementById("smTeacher").value.trim();
  const color = document.getElementById("smColor").value;

  const matchedCourse = (appData.courses || []).find((c) => (c.fullname || "").toLowerCase() === subject.toLowerCase());
  const moodleCourseUrl = document.getElementById("smMoodleUrl").value.trim()
    || (matchedCourse ? matchedCourse.viewurl : "")
    || (appData.profile && appData.profile.moodleEntryUrl)
    || DEFAULT_MOODLE_URL;

  appData.schedule = appData.schedule || [];
  if (id) {
    const idx = appData.schedule.findIndex((x) => x.id === id);
    if (idx >= 0) {
      appData.schedule[idx] = { id, subject, day, type, startTime, endTime, room, teacher, color, moodleCourseUrl };
    }
  } else {
    appData.schedule.push({
      id: "sch-user-" + Date.now(),
      subject, day, type, startTime, endTime, room, teacher, color, moodleCourseUrl
    });
  }

  closeScheduleModal();
  await persistState("⏰ Horario de clases actualizado.");
}

async function deleteCurrentScheduleClass() {
  const id = document.getElementById("smId").value;
  if (!id) return;
  appData.schedule = (appData.schedule || []).filter((x) => x.id !== id);
  closeScheduleModal();
  await persistState("🗑️ Clase eliminada del horario.");
}

// ---------------------------------------------------------------------------
// EXPORTACIÓN Y LIMPIEZA
// ---------------------------------------------------------------------------
function exportBackupJson() {
  const blob = new Blob([JSON.stringify(appData, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `moodle_assistant_backup_${toIsoDate(new Date())}.json`;
  a.click();
  URL.revokeObjectURL(url);
  showToast("⬇️ Copia de seguridad JSON descargada.");
}

async function clearAllAppData() {
  if (!confirm("¿Seguro que deseas vaciar todos los datos guardados y cerrar la sesión de Moodle?")) return;
  try {
    const resp = await fetch("/api/clear-all", { method: "POST" });
    const json = await resp.json();
    if (json && json.ok) {
      appData = json.data;
      localStorage.removeItem("moodle_assistant_real_state");
      renderAll();
      switchView("profile");
      showToast("🗑️ Todos los datos han sido vaciados.");
    }
  } catch (_e) {
    localStorage.removeItem("moodle_assistant_real_state");
    location.reload();
  }
}

// ---------------------------------------------------------------------------
// UTILIDADES
// ---------------------------------------------------------------------------
function toIsoDate(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function getDaysRemaining(isoDate) {
  if (!isoDate) return 99;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const target = new Date(isoDate + "T00:00:00");
  return Math.round((target - today) / (1000 * 60 * 60 * 24));
}

function formatDateReadable(isoDate) {
  if (!isoDate) return "";
  const parts = isoDate.split("-");
  if (parts.length !== 3) return isoDate;
  return `${parts[2]}/${parts[1]}/${parts[0]}`;
}

function buildMonthCells(year, month) {
  const firstDay = new Date(year, month, 1);
  const lastDay = new Date(year, month + 1, 0);
  const startOffset = (firstDay.getDay() + 6) % 7;
  const totalDays = lastDay.getDate();

  const cells = [];
  for (let i = startOffset - 1; i >= 0; i--) {
    const d = new Date(year, month, -i);
    cells.push({ iso: toIsoDate(d), dayNum: d.getDate(), inMonth: false });
  }
  for (let dNum = 1; dNum <= totalDays; dNum++) {
    const d = new Date(year, month, dNum);
    cells.push({ iso: toIsoDate(d), dayNum: dNum, inMonth: true });
  }
  const targetLen = cells.length > 35 ? 42 : 35;
  let nextDay = 1;
  while (cells.length < targetLen) {
    const d = new Date(year, month + 1, nextDay++);
    cells.push({ iso: toIsoDate(d), dayNum: d.getDate(), inMonth: false });
  }
  return cells;
}

function showToast(msg, isWarning = false) {
  const container = document.getElementById("toastContainer");
  if (!container) return;
  const toast = document.createElement("div");
  toast.className = "toast";
  if (isWarning) toast.style.borderLeftColor = "#f59e0b";
  toast.textContent = msg;
  container.appendChild(toast);
  setTimeout(() => {
    toast.remove();
  }, 3800);
}

function escapeHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function escapeAttr(str) {
  return String(str ?? "")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function getCleanInitialData() {
  return {
    profile: {
      linked: false,
      studentName: "",
      username: "",
      university: "Moodle Centros - Junta de Andalucía (Sevilla)",
      degree: "",
      moodleEntryUrl: DEFAULT_MOODLE_URL,
      moodleBaseUrl: "https://educacionadistancia.juntadeandalucia.es/centros/sevilla",
      moodleProfileUrl: "https://educacionadistancia.juntadeandalucia.es/centros/sevilla/user/profile.php",
      openMode: "both",
      avatarInitials: "MD",
      lastSync: "Sin sincronizar"
    },
    courses: [],
    moodleTasks: [],
    personalEvents: [],
    schedule: [],
    grades: [],
    notes: [],
    pomodoroStats: { completedSessions: 0, totalMinutes: 0 }
  };
}
