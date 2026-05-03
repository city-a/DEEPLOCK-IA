/// ========== DATOS DE LA EMPRESA ==========
const WEB_DATA = {
    empresa: "Deeplock-IA desarrolla soluciones de automatización inteligente...",
    mision: "Ayudar a empresas a crecer mediante automatización inteligente...",
    vision: "Convertirnos en la plataforma líder de automatización empresarial en Latinoamérica.",
    objetivos: ["Optimizar procesos empresariales", "Aumentar ventas mediante IA", "Reducir tiempos de respuesta", "Mejorar la experiencia del cliente"],
    beneficios: ["Respuestas instantáneas 24/7", "Aumento en conversión de clientes", "Reducción de costos operativos", "Automatización de procesos repetitivos", "Mejora en experiencia del cliente"],
    planes: [
        { nombre: "PLAY", precio: "$49.000", caracteristicas: "200 mensajes, chat web, respuestas automáticas.", ideal: "Negocios pequeños que empiezan." },
        { nombre: "ESTÁNDAR", precio: "$149.000", caracteristicas: "2.000 mensajes, IA inteligente, Web + WhatsApp, captura de leads.", ideal: "Empresas en crecimiento, tiendas online." },
        { nombre: "PREMIUM", precio: "$299.000", caracteristicas: "Mensajes ilimitados, IA personalizada, integraciones, analíticas.", ideal: "Grandes empresas o alto volumen." }
    ],
    urlPagoBase: "https://deeplock.com/pagar"
};

// ========== CONFIGURACIÓN ==========
let config = {
    botName: "Sofía",
    companyName: "Deeplock-IA",
    tone: "amigable",
    systemPrompt: "Eres un asistente experto en chatbots. Responde de forma breve pero completa, usa frases cortas.",
    contactInfo: "Email: hola@deeplock.com | Tel: +34 900 123 456",
    responseMode: "local_only", // Ahora lo controlan los botones: 'local_only' o 'hybrid'
    faq: [
        { pregunta: "¿Qué planes tienen?", respuesta: "Tenemos tres planes: PLAY ($49.000/mes), ESTÁNDAR ($149.000) y PREMIUM ($299.000). ¿Quieres que te ayude a elegir?" },
        { pregunta: "¿Cómo contacto?", respuesta: "Escríbenos a hola@deeplock.com o visita nuestra web." }
    ],
    purchaseSession: null
};

// Cargar configuración guardada
const stored = localStorage.getItem("chatbotConfig");
if (stored) {
    try {
        const parsed = JSON.parse(stored);
        config = { ...config, ...parsed };
    } catch(e) {}
}
function saveConfigToLocal() {
    const toStore = { ...config };
    delete toStore.purchaseSession;
    localStorage.setItem("chatbotConfig", JSON.stringify(toStore));
}

// ========== DETECCIÓN DE INTERNET ==========
let isOnline = true;
let statusDiv = null;

async function checkInternetConnection() {
    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 5000);
        const response = await fetch('https://www.google.com/favicon.ico', { method: 'HEAD', cache: 'no-store', signal: controller.signal });
        clearTimeout(timeoutId);
        isOnline = response.ok;
    } catch(e) {
        isOnline = false;
    }
    // Actualizar texto de estado según el modo y conexión
    if (statusDiv) {
        if (config.responseMode === 'local_only') {
            statusDiv.innerText = "🔒 Modo Local activado. Respuestas rápidas sin internet.";
        } else if (config.responseMode === 'hybrid') {
            if (isOnline) statusDiv.innerText = "🌐 Modo Online activado. Usando IA externa.";
            else statusDiv.innerText = "⚠️ Modo Online sin conexión. Cambiando temporalmente a Local.";
        } else {
            statusDiv.innerText = "Bot listo.";
        }
    }
    return isOnline;
}

setInterval(checkInternetConnection, 30000);

// ========== CONOCIMIENTO LOCAL ==========
function buscarEnWeb(pregunta) {
    const q = pregunta.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
    if (q.includes("plan") || q.includes("precio") || q.includes("costo") || q.includes("cuánto") || q.includes("cuanto")) {
        let respuesta = `Planes de ${config.companyName}:\n`;
        for (let p of WEB_DATA.planes) {
            respuesta += `• ${p.nombre}: ${p.precio} - ${p.caracteristicas}\n`;
        }
        respuesta += "\n¿Te ayudo a elegir el mejor? Escribe 'quiero comprar'.";
        return respuesta;
    }
    if (q.includes("mision") || q.includes("misión")) return `Misión: ${WEB_DATA.mision}`;
    if (q.includes("vision") || q.includes("visión")) return `Visión: ${WEB_DATA.vision}`;
    if (q.includes("objetivo")) return `Objetivos: ${WEB_DATA.objetivos.join(", ")}.`;
    if (q.includes("beneficio") || q.includes("ventaja")) return `Beneficios:\n${WEB_DATA.beneficios.map(b => `✓ ${b}`).join("\n")}`;
    if (q.includes("quienes") || q.includes("empresa")) return WEB_DATA.empresa;
    if (q.includes("play")) return `Plan PLAY: ${WEB_DATA.planes[0].precio} - ${WEB_DATA.planes[0].caracteristicas}`;
    if (q.includes("estándar") || q.includes("estandar")) return `Plan ESTÁNDAR: ${WEB_DATA.planes[1].precio} - ${WEB_DATA.planes[1].caracteristicas}`;
    if (q.includes("premium")) return `Plan PREMIUM: ${WEB_DATA.planes[2].precio} - ${WEB_DATA.planes[2].caracteristicas}`;
    return null;
}

function buscarEnFAQ(pregunta) {
    const q = pregunta.toLowerCase();
    for (let item of config.faq) {
        if (q.includes(item.pregunta.toLowerCase())) return item.respuesta;
    }
    return null;
}

// ========== FLUJO DE COMPRA ==========
function esIntencionCompra(mensaje) {
    const txt = mensaje.toLowerCase();
    const keywords = ["comprar", "adquirir", "quiero un plan", "necesito un chatbot", "presupuesto", "contratar", "costo plan", "mejor plan"];
    return keywords.some(k => txt.includes(k));
}
function iniciarFlujoCompra() {
    config.purchaseSession = { paso: 1, respuestas: {} };
    return "Excelente. Te ayudaré a encontrar el plan ideal. ¿Cuál es tu tipo de negocio? (Ej: tienda online, restaurante, consultoría, freelance)";
}
async function procesarRespuestaCompra(mensaje) {
    const session = config.purchaseSession;
    if (!session) return null;
    if (session.paso === 1) {
        session.respuestas.tipo = mensaje;
        session.paso = 2;
        return "¿Cuántos clientes o conversaciones estimas al mes? (Ej: 100, 500, 2000, mas de 5000)";
    }
    if (session.paso === 2) {
        session.respuestas.volumen = mensaje;
        session.paso = 3;
        return "¿Qué funcionalidades buscas? (respuestas automaticas, WhatsApp, IA avanzada, integraciones)";
    }
    if (session.paso === 3) {
        session.respuestas.funciones = mensaje;
        session.paso = 4;
        return "¿Cuál es tu presupuesto mensual aproximado? (Ej: menos de 50.000, 50-150.000, mas de 150.000)";
    }
    if (session.paso === 4) {
        session.respuestas.presupuesto = mensaje;
        let planRecomendado = WEB_DATA.planes[0];
        const vol = parseInt(session.respuestas.volumen) || 0;
        const func = session.respuestas.funciones.toLowerCase();
        const pres = session.respuestas.presupuesto.toLowerCase();
        if (vol > 2000 || func.includes("ia avanzada") || pres.includes("mas de 150")) planRecomendado = WEB_DATA.planes[2];
        else if (vol > 500 || func.includes("whatsapp") || pres.includes("50-150")) planRecomendado = WEB_DATA.planes[1];
        const urlPago = `${WEB_DATA.urlPagoBase}?plan=${planRecomendado.nombre.toLowerCase()}&negocio=${encodeURIComponent(session.respuestas.tipo)}`;
        const respuestaHTML = `
            <strong>Recomendación:</strong> El plan que mejor se adapta es <strong>${planRecomendado.nombre}</strong> (${planRecomendado.precio}).<br>
            Caracteristicas: ${planRecomendado.caracteristicas}<br><br>
            <a href="${urlPago}" target="_blank" class="pay-button">PAGAR AHORA</a><br><br>
            ¿Necesitas mas ayuda?
        `;
        config.purchaseSession = null;
        return { html: respuestaHTML, isHtml: true };
    }
    return null;
}

// ========== IA EXTERNA ==========
async function consultarIA(pregunta) {
    if (config.responseMode !== 'hybrid') return null;
    if (!isOnline) return null;
    try {
        const tonoHint = config.tone === "formal" ? "Se formal y preciso." : (config.tone === "divertido" ? "Usa un tono divertido." : "Usa un tono amigable.");
        const prompt = `${config.systemPrompt} ${tonoHint} Responde de forma breve, maximo 3 lineas. Pregunta: ${pregunta}`;
        const url = `https://text.pollinations.ai/prompt/${encodeURIComponent(prompt)}`;
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 8000);
        const res = await fetch(url, { signal: controller.signal });
        clearTimeout(timeoutId);
        if (!res.ok) throw new Error();
        let texto = await res.text();
        if (texto.length > 400) texto = texto.substring(0, 400) + "...";
        return texto.trim();
    } catch(e) {
        return null;
    }
}

// ========== RESPUESTA PRINCIPAL ==========
async function obtenerRespuesta(mensaje) {
    try {
        if (config.purchaseSession) {
            const r = await procesarRespuestaCompra(mensaje);
            if (r) return r;
        }
        if (esIntencionCompra(mensaje) && !config.purchaseSession) {
            return { text: iniciarFlujoCompra(), isHtml: false };
        }
        let resp = buscarEnWeb(mensaje);
        if (resp) return { text: resp, isHtml: false };
        resp = buscarEnFAQ(mensaje);
        if (resp) return { text: resp, isHtml: false };

        if (config.responseMode === 'hybrid' && isOnline) {
            const iaResp = await consultarIA(mensaje);
            if (iaResp) return { text: iaResp, isHtml: false };
        }
        // Respuesta amigable cuando no encuentra información
        if (config.responseMode === 'local_only' || !isOnline) {
            return { text: "No encuentro esa información en mi base local. Te sugiero preguntar por 'Planes', 'Precios', 'Beneficios' o 'Comprar'. ¿En qué más puedo ayudarte?", isHtml: false };
        } else {
            return { text: `No pude resolver tu pregunta. Intenta con "Planes", "Precios" o contacta a ${config.contactInfo}`, isHtml: false };
        }
    } catch(e) {
        return { text: "Ocurrió un error. Inténtalo de nuevo.", isHtml: false };
    }
}

// ========== UI Y EVENTOS ==========
let chatBox, splashDiv, inputField, sendBtn, isGenerating = false;

function initUI() {
    chatBox = document.getElementById('chat');
    splashDiv = document.getElementById('splashText');
    inputField = document.getElementById('msg');
    statusDiv = document.getElementById('statusMsg');
    sendBtn = document.getElementById('sendBtn');

    // Botones de modo
    const modeLocalBtn = document.getElementById('modeLocalBtn');
    const modeOnlineBtn = document.getElementById('modeOnlineBtn');

    function setActiveMode(mode) {
        if (mode === 'local_only') {
            config.responseMode = 'local_only';
            modeLocalBtn.classList.add('active');
            modeOnlineBtn.classList.remove('active');
            modeLocalBtn.style.background = "#2563eb";
            modeLocalBtn.style.color = "white";
            modeOnlineBtn.style.background = "#cbd5e1";
            modeOnlineBtn.style.color = "#0f172a";
            statusDiv.innerText = "🔒 Modo Local activado. Respuestas desde conocimiento interno.";
        } else {
            config.responseMode = 'hybrid';
            modeOnlineBtn.classList.add('active');
            modeLocalBtn.classList.remove('active');
            modeOnlineBtn.style.background = "#2563eb";
            modeOnlineBtn.style.color = "white";
            modeLocalBtn.style.background = "#cbd5e1";
            modeLocalBtn.style.color = "#0f172a";
            if (isOnline) statusDiv.innerText = "🌐 Modo Online activado. Usando IA externa.";
            else statusDiv.innerText = "⚠️ Sin conexión a internet. Activar modo Local para mejor experiencia.";
        }
        saveConfigToLocal();
    }

    modeLocalBtn.addEventListener('click', () => setActiveMode('local_only'));
    modeOnlineBtn.addEventListener('click', () => setActiveMode('hybrid'));

    // Establecer estado inicial según configuración guardada
    if (config.responseMode === 'local_only') setActiveMode('local_only');
    else setActiveMode('hybrid');

    // Sugerencias: al hacer clic, enviar esa pregunta
    const suggestionBtns = document.querySelectorAll('.suggestion-btn');
    suggestionBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const pregunta = btn.getAttribute('data-pregunta');
            if (pregunta) {
                inputField.value = pregunta;
                enviar();
            }
        });
    });

    function updateSplashVisibility() {
        const hasMessages = chatBox.children.length > 1;
        splashDiv.style.display = hasMessages ? 'none' : 'block';
    }

    function agregarMensaje(contenido, tipo, isHtml = false) {
        const div = document.createElement('div');
        div.classList.add('msg', tipo);
        if (isHtml) div.innerHTML = contenido;
        else div.innerText = contenido;
        chatBox.appendChild(div);
        chatBox.scrollTop = chatBox.scrollHeight;
        updateSplashVisibility();
    }

    function reemplazarUltimoMensaje(contenido, tipo, isHtml = false) {
        const last = chatBox.lastChild;
        if (last && last.classList && last.classList.contains('thinking')) {
            last.classList.remove('thinking');
            last.classList.add(tipo);
            if (isHtml) last.innerHTML = contenido;
            else last.innerText = contenido;
        } else {
            agregarMensaje(contenido, tipo, isHtml);
        }
        chatBox.scrollTop = chatBox.scrollHeight;
        updateSplashVisibility();
    }

    window.enviar = async function() {
        if (isGenerating) {
            agregarMensaje("Espera un momento, aún estoy respondiendo.", "bot-msg");
            return;
        }
        const texto = inputField.value.trim();
        if (!texto) return;
        agregarMensaje(texto, "user-msg");
        inputField.value = "";
        inputField.disabled = true;
        statusDiv.innerText = `${config.botName} está pensando...`;
        agregarMensaje("PENSANDO...", "thinking");
        isGenerating = true;

        let respuestaObj;
        try {
            respuestaObj = await obtenerRespuesta(texto);
        } catch(e) {
            respuestaObj = { text: "Error inesperado. Intenta de nuevo.", isHtml: false };
        }

        if (respuestaObj && respuestaObj.html) reemplazarUltimoMensaje(respuestaObj.html, "bot-msg", true);
        else if (respuestaObj && respuestaObj.text) reemplazarUltimoMensaje(respuestaObj.text, "bot-msg", false);
        else reemplazarUltimoMensaje("No lo sé, estoy aprendiendo. Contacta con " + config.contactInfo, "bot-msg", false);

        // Restaurar estado del status según modo
        if (config.responseMode === 'local_only') statusDiv.innerText = "🔒 Modo Local activado.";
        else if (config.responseMode === 'hybrid' && isOnline) statusDiv.innerText = "🌐 Modo Online activado.";
        else if (config.responseMode === 'hybrid' && !isOnline) statusDiv.innerText = "⚠️ Sin conexión. Cambia a Local.";
        else statusDiv.innerText = "Bot listo.";
        isGenerating = false;
        inputField.disabled = false;
        inputField.focus();
    };

    sendBtn.addEventListener('click', enviar);
    inputField.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && !isGenerating) {
            e.preventDefault();
            enviar();
        }
    });

    // Mensaje de bienvenida
    const bienvenida = `Hola, soy ${config.botName} de ${config.companyName}. Conozco planes, precios y beneficios. Usa los botones de sugerencia o escribe tu pregunta.`;
    agregarMensaje(bienvenida, "bot-msg");
}

// ========== CONFIGURACIÓN MODAL (sin cambios significativos) ==========
function applyConfigToUI() {
    document.getElementById("botNameInput").value = config.botName;
    document.getElementById("companyNameInput").value = config.companyName;
    document.getElementById("toneSelect").value = config.tone;
    document.getElementById("systemPromptInput").value = config.systemPrompt;
    document.getElementById("contactInfoInput").value = config.contactInfo;
    renderFaqList();
    document.getElementById("botNameDisplay").innerText = config.botName;
}
function renderFaqList() { /* igual que antes */ }
function escapeHtml(str) { /* igual */ }
function saveConfig() {
    config.botName = document.getElementById("botNameInput").value;
    config.companyName = document.getElementById("companyNameInput").value;
    config.tone = document.getElementById("toneSelect").value;
    config.systemPrompt = document.getElementById("systemPromptInput").value;
    config.contactInfo = document.getElementById("contactInfoInput").value;
    document.getElementById("botNameDisplay").innerText = config.botName;
    saveConfigToLocal();
    alert("Configuración guardada.");
    closeModal();
}
function addFaq() {
    config.faq.push({ pregunta: "Nueva pregunta", respuesta: "Nueva respuesta" });
    renderFaqList();
}
const modal = document.getElementById("adminModal");
function openModal() { modal.style.display = "flex"; applyConfigToUI(); }
function closeModal() { modal.style.display = "none"; }
document.getElementById("openSettingsBtn").addEventListener("click", openModal);
document.getElementById("closeModalBtn").addEventListener("click", closeModal);
document.getElementById("saveConfigBtn").addEventListener("click", saveConfig);
document.getElementById("addFaqBtn").addEventListener("click", addFaq);
window.addEventListener("click", (e) => { if (e.target === modal) closeModal(); });

document.addEventListener("DOMContentLoaded", () => {
    initUI();
    checkInternetConnection();
});