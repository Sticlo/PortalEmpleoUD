(() => {
  const views = ["inicio", "hv", "ofertas", "cv"];

  const statusEl = document.getElementById("hv-status");
  const statusStrip = document.getElementById("status-strip");
  const toast = document.getElementById("toast");
  const radar = document.getElementById("radar");
  const btnBuscar = document.getElementById("btn-buscar");
  const radarSub = document.getElementById("radar-sub");
  const searchLive = document.getElementById("search-live");
  const resultsHead = document.getElementById("results-head");
  const offersList = document.getElementById("offers-list");
  const form = document.getElementById("hv-form");
  const paper = document.getElementById("ats-preview");

  const portals = ["Computrabajo", "Elempleo", "Indeed", "LinkedIn"];
  let step = 0;
  const totalSteps = 4;
  let skills = ["Python", "SQL", "Git", "APIs REST", "Playwright"];

  const offerCopy = {
    python: {
      title: "CV para: Practicante Backend Python",
      body: "Desarrolladora con experiencia en Python, SQL, Git, APIs y automatización (Playwright). Busco práctica backend para aportar en integraciones y calidad de entrega.",
      gap: "La oferta pide Docker y no está en tu HV — no lo incluimos en el CV.",
    },
    qa: {
      title: "CV para: Práctica QA Automation",
      body: "Estudiante de Ingeniería de Sistemas (7º) con experiencia en automatización con Playwright, Python y Git. Busco práctica en QA Automation para aplicar pruebas sistemáticas.",
      gap: "Sin gaps críticos respecto a tu HV.",
    },
    junior: {
      title: "CV para: Desarrollador Junior",
      body: "Developer con 3 años de experiencia en Python, SQL, Git y APIs. Estudiante UD en 7º semestre. Busco primer rol junior enfocado en desarrollo e integraciones.",
      gap: "La oferta puede pedir frontend (React) — no está en tu HV, no lo inventamos.",
    },
    datos: {
      title: "CV para: Practicante de Datos",
      body: "Estudiante UD con experiencia en SQL, automatización y reportes. Busco práctica en datos para apoyar limpieza, consultas y generación de insights.",
      gap: "Si piden Power BI avanzado y no está en tu HV, no lo agregamos.",
    },
    devops: {
      title: "CV para: Soporte técnico / DevOps Jr",
      body: "Developer con experiencia en automatización, Git y scripts. Interesada en práctica de soporte/DevOps junior para aprender monitoreo y despliegues.",
      gap: "Linux no está en tu HV — se menciona disposición a aprender, no dominio.",
    },
  };

  function show(name) {
    if (!views.includes(name)) return;

    views.forEach((id) => {
      const el = document.getElementById(`view-${id}`);
      const on = id === name;
      el.classList.toggle("active", on);
      el.hidden = !on;
    });

    document.querySelectorAll(".nav-link").forEach((btn) => {
      btn.classList.toggle(
        "active",
        btn.dataset.go === name || (name === "cv" && btn.dataset.go === "ofertas")
      );
    });

    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function flash(msg) {
    toast.textContent = msg;
    toast.hidden = false;
    clearTimeout(flash._t);
    flash._t = setTimeout(() => {
      toast.hidden = true;
    }, 1800);
  }

  function markHvSaved() {
    const nombre = form.nombre.value.trim() || "tu HV";
    statusEl.textContent = `HV ATS de ${nombre} lista · ya puedes buscar con IA`;
    statusStrip.classList.add("ready");
  }

  function setStep(n) {
    step = Math.max(0, Math.min(totalSteps - 1, n));

    document.querySelectorAll(".ats-panel").forEach((panel) => {
      const on = Number(panel.dataset.panel) === step;
      panel.classList.toggle("active", on);
      panel.hidden = !on;
    });

    document.querySelectorAll(".ats-step").forEach((btn) => {
      const i = Number(btn.dataset.step);
      btn.classList.toggle("active", i === step);
      btn.classList.toggle("done", i < step);
    });

    document.getElementById("ats-prev").hidden = step === 0;
    document.getElementById("ats-next").hidden = step === totalSteps - 1;
    document.getElementById("ats-finish").hidden = step !== totalSteps - 1;
  }

  function val(name) {
    const el = form.elements[name];
    if (!el) return "";
    if (el instanceof RadioNodeList) {
      return form.querySelector(`input[name="${name}"]:checked`)?.value || "";
    }
    return el.value;
  }

  function updatePreview() {
    const set = (id, text) => {
      const el = document.getElementById(id);
      if (el) el.textContent = text || "—";
    };

    set("pv-nombre", val("nombre"));
    set("pv-contacto", val("contacto"));
    set("pv-ciudad", val("ciudad"));
    set("pv-busca", val("busca"));
    set("pv-carrera", `${val("carrera")} — ${val("semestre")}`);
    set("pv-uni", val("universidad"));
    set("pv-cargo", val("cargo"));
    set("pv-empresa", val("empresa"));
    set("pv-periodo", val("periodo"));

    const logros = val("logros")
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean);
    const ul = document.getElementById("pv-logros");
    ul.innerHTML = logros.length
      ? logros.map((l) => `<li>${escapeHtml(l)}</li>`).join("")
      : "<li>Agrega logros reales, uno por línea</li>";

    document.getElementById("pv-skills").textContent = skills.length
      ? skills.join(" · ")
      : "Agrega tus skills";

    paper.classList.remove("flash");
    void paper.offsetWidth;
    paper.classList.add("flash");
  }

  function escapeHtml(str) {
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function renderSkills() {
    const box = document.getElementById("skill-chips");
    box.innerHTML = skills
      .map(
        (s, i) =>
          `<span class="skill-chip">${escapeHtml(s)}<button type="button" data-rm="${i}" aria-label="Quitar">×</button></span>`
      )
      .join("");
    document.getElementById("skills-hidden").value = skills.join(", ");
    updatePreview();
  }

  function addSkill() {
    const input = document.getElementById("skill-input");
    const raw = input.value.trim();
    if (!raw) return;
    raw.split(",").forEach((part) => {
      const s = part.trim();
      if (s && !skills.some((x) => x.toLowerCase() === s.toLowerCase())) {
        skills.push(s);
      }
    });
    input.value = "";
    renderSkills();
  }

  function resetRadar() {
    radar.classList.remove("scanning", "done");
    resultsHead.hidden = true;
    offersList.hidden = true;
    searchLive.hidden = true;
    searchLive.textContent = "";
    btnBuscar.disabled = false;
    btnBuscar.textContent = "Buscar ahora";
    radarSub.textContent =
      "Computrabajo · Elempleo · Indeed · LinkedIn — solo lo reciente que encaja con tu HV.";
  }

  async function runSearch() {
    resetRadar();
    btnBuscar.disabled = true;
    btnBuscar.textContent = "Buscando…";
    radar.classList.add("scanning");
    searchLive.hidden = false;

    for (const p of portals) {
      searchLive.textContent = `Revisando ${p}… ofertas de las últimas 72 h`;
      await wait(550);
    }

    searchLive.textContent = "Filtrando por encaje con tu HV…";
    await wait(500);

    radar.classList.remove("scanning");
    radar.classList.add("done");
    searchLive.textContent = "Listo · 6 ofertas con buen potencial";
    radarSub.textContent = "Resultados listos. Elige una y prepara tu CV ATS en un clic.";
    btnBuscar.textContent = "Buscar de nuevo";
    btnBuscar.disabled = false;

    resultsHead.hidden = false;
    offersList.hidden = false;

    [...offersList.children].forEach((card, i) => {
      card.style.animationDelay = `${0.04 + i * 0.07}s`;
    });

    flash("Ofertas actualizadas");
  }

  function wait(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

  document.querySelectorAll("[data-go]").forEach((el) => {
    el.addEventListener("click", () => show(el.dataset.go));
  });

  document.querySelectorAll(".ats-step").forEach((btn) => {
    btn.addEventListener("click", () => setStep(Number(btn.dataset.step)));
  });

  document.getElementById("ats-next").addEventListener("click", () => setStep(step + 1));
  document.getElementById("ats-prev").addEventListener("click", () => setStep(step - 1));

  form.addEventListener("input", updatePreview);
  form.addEventListener("change", updatePreview);

  document.getElementById("skill-add").addEventListener("click", addSkill);
  document.getElementById("skill-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      addSkill();
    }
  });

  document.getElementById("skill-chips").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-rm]");
    if (!btn) return;
    skills.splice(Number(btn.dataset.rm), 1);
    renderSkills();
  });

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    markHvSaved();
    flash("Hoja de vida ATS guardada");
    show("ofertas");
    resetRadar();
    setTimeout(runSearch, 350);
  });

  btnBuscar.addEventListener("click", runSearch);

  document.querySelectorAll("[data-offer]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const key = btn.dataset.offer;
      const data = offerCopy[key];
      if (!data) return;
      document.getElementById("cv-title").textContent = data.title;
      document.getElementById("cv-body").textContent = data.body;
      document.getElementById("cv-gap").innerHTML = `<strong>Ojo:</strong> ${data.gap}`;
      show("cv");
    });
  });

  document.getElementById("btn-copy").addEventListener("click", async () => {
    const text = document.getElementById("cv-preview").innerText;
    try {
      await navigator.clipboard.writeText(text);
      flash("CV copiado");
    } catch {
      flash("Selecciona y copia el texto");
    }
  });

  document.getElementById("btn-done").addEventListener("click", () => show("ofertas"));

  renderSkills();
  setStep(0);
  updatePreview();
  show("inicio");
})();
