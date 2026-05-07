"""
deep_parser.py — ComfyUI Regional Prompt Deep Parser
=====================================================
Transforma descripciones de texto detalladas en JSON estructurado con:
  - Bounding boxes regionales (coordenadas 0-1)
  - Atributos de objeto (color, material, pose, iluminación)
  - Mapeo de ControlNets e IP-Adapter
  - Pesos de atención para difusión regional
  - Sistema de clarificación automática

Dependencias: spaCy (con modelo es_core_news_sm), transformers (opcional)
Instalación:  pip install spacy && python -m spacy download es_core_news_sm
"""

import json
import re
import sys
from dataclasses import dataclass, field, asdict
from typing import Optional
from copy import deepcopy

# ─────────────────────────────────────────────
# MODELOS LIGEROS — carga diferida
# ─────────────────────────────────────────────
_nlp = None

def get_nlp():
    global _nlp
    if _nlp is None:
        try:
            import spacy
            _nlp = spacy.load("es_core_news_sm")
        except (OSError, ImportError, Exception):
            print("[WARN] spaCy no disponible. Usando tokenizador básico.", file=sys.stderr)
            _nlp = "UNAVAILABLE"
    return None if _nlp == "UNAVAILABLE" else _nlp


# ═══════════════════════════════════════════════════════════════════════════════
# 1. ESTRUCTURAS DE DATOS
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class BoundingBox:
    """Coordenadas relativas [0,1] en formato [x_min, y_min, x_max, y_max]."""
    x_min: float
    y_min: float
    x_max: float
    y_max: float

    def as_list(self):
        return [self.x_min, self.y_min, self.x_max, self.y_max]


@dataclass
class ObjectAttributes:
    color: list[str]        = field(default_factory=list)
    material: list[str]     = field(default_factory=list)
    pose: Optional[str]     = None
    lighting: Optional[str] = None
    state: list[str]        = field(default_factory=list)   # humeante, intacto…
    texture: list[str]      = field(default_factory=list)
    negations: list[str]    = field(default_factory=list)   # "no hay nubes"
    cross_refs: list[str]   = field(default_factory=list)   # referencias cruzadas


@dataclass
class RegionalObject:
    id: str
    label: str
    bbox: BoundingBox
    attributes: ObjectAttributes
    prompt_weight: float             = 1.0   # peso de atención regional
    controlnets: list[str]          = field(default_factory=list)
    ip_adapter: Optional[dict]      = None   # consistencia de personaje
    layer: str                      = "midground"  # foreground/midground/background
    negation: bool                  = False  # objeto excluido explícitamente


@dataclass
class SceneMetadata:
    time_of_day: Optional[str]      = None
    weather: Optional[str]          = None
    camera_angle: Optional[str]     = None
    camera_distance: Optional[str]  = None
    lighting_mood: Optional[str]    = None
    location_type: Optional[str]    = None
    style: Optional[str]            = None
    aspect_ratio: str               = "landscape"


@dataclass
class ParsedScene:
    metadata: SceneMetadata
    objects: list[RegionalObject]
    global_negative_prompt: list[str]
    clarification_questions: list[str]
    character_registry: dict         # nombre → ip_adapter config
    comfyui_node_template: dict


# ═══════════════════════════════════════════════════════════════════════════════
# 2. PARSING LINGÜÍSTICO
# ═══════════════════════════════════════════════════════════════════════════════

# Diccionarios de conocimiento
COLOR_TOKENS = {
    "azul": "blue", "eléctrico": "electric", "naranja": "orange",
    "dorado": "golden", "blanco": "white", "negro": "black",
    "rojo": "red", "verde": "green", "violeta": "violet",
    "amarillo": "yellow", "gris": "gray", "rosa": "pink",
    "empañado": "fogged", "transparente": "transparent",
}

MATERIAL_TOKENS = {
    "vidrio": "glass", "madera": "wood", "metal": "metal",
    "tela": "fabric", "seda": "silk", "cuero": "leather",
    "cerámica": "ceramic", "papel": "paper", "vapor": "steam",
}

POSE_TOKENS = {
    "sentada": "sitting", "de pie": "standing", "acostada": "lying",
    "caminando": "walking", "sostiene": "holding", "apoyada": "leaning",
    "contrapicada": "low angle shot", "picada": "high angle shot",
}

LIGHTING_TOKENS = {
    "anaranjada": "warm orange light", "dorada": "golden hour",
    "atardecer": "sunset", "amanecer": "sunrise", "nocturna": "night",
    "difusa": "diffuse", "lateral": "side lighting", "contraluz": "backlight",
}

STATE_TOKENS = {
    "humeante": "steaming", "intacto": "untouched", "abierto": "open",
    "cerrado": "closed", "ilegible": "illegible", "visible": "visible",
    "empañada": "fogged", "roto": "broken", "nuevo": "brand new",
}

NEGATION_MARKERS = {"no", "sin", "ningún", "ninguna", "ninguno", "ausente", "vacío"}

SPATIAL_ANCHORS = {
    # objeto → (x_center, y_center, width, height) aprox.
    "sujeto_principal":  (0.38, 0.45, 0.45, 0.80),
    "fondo":             (0.50, 0.25, 1.00, 0.55),
    "ventana":           (0.70, 0.30, 0.55, 0.55),
    "mesa":              (0.45, 0.75, 0.60, 0.40),
    "mano_derecha":      (0.60, 0.55, 0.20, 0.20),
    "taza":              (0.62, 0.50, 0.14, 0.18),
    "vapor":             (0.62, 0.37, 0.12, 0.20),
    "libro":             (0.35, 0.78, 0.22, 0.18),
    "croissant":         (0.55, 0.82, 0.18, 0.14),
    "torre_eiffel":      (0.72, 0.22, 0.20, 0.35),
    "exterior":          (0.70, 0.22, 0.55, 0.50),
    "cielo":             (0.50, 0.08, 1.00, 0.25),
    "espejo":            (0.15, 0.35, 0.25, 0.45),
    "reflejo":           (0.15, 0.35, 0.25, 0.45),
    "default":           (0.50, 0.50, 0.40, 0.40),
}

CONTROLNET_RULES = {
    # tipo de objeto → ControlNets recomendados
    "persona":     ["openpose", "depth"],
    "cara":        ["openpose", "ip_adapter"],
    "mano":        ["openpose", "depth"],
    "edificio":    ["depth", "canny"],
    "interior":    ["depth", "seg"],
    "fondo":       ["depth", "seg"],
    "ventana":     ["depth", "canny"],
    "objeto":      ["depth"],
    "luz":         [],
    "vapor":       ["depth"],
    "espejo":      ["depth", "canny", "seg"],
}

CRITICAL_FIELDS = {
    "time_of_day":       "¿En qué momento del día transcurre la escena? (amanecer, mañana, mediodía, atardecer, noche)",
    "camera_angle":      "¿Cuál es el ángulo de cámara? (frontal, perfil, contrapicado, picado, ojo de pájaro)",
    "camera_distance":   "¿A qué distancia está la cámara del sujeto principal? (primer plano, plano medio, plano entero, plano general)",
    "weather":           "¿Cuál es el estado del tiempo exterior? (soleado, nublado, lluvioso, niebla)",
    "style":             "¿Qué estilo visual se busca? (fotorrealista, pictórico, cinematográfico, anime, ilustración)",
    "lighting_mood":     "¿Cuál es el estado de ánimo lumínico general? (cálido, frío, dramático, suave, tenebroso)",
}


def tokenize_basic(text: str) -> list[str]:
    """Tokenizador de respaldo si spaCy no está disponible."""
    return re.findall(r'\b\w+\b', text.lower())


def extract_entities_spacy(text: str) -> list[dict]:
    """Extrae entidades nombradas usando spaCy (si disponible)."""
    nlp = get_nlp()
    if nlp is None:
        return []
    doc = nlp(text)
    entities = []
    for ent in doc.ents:
        entities.append({"text": ent.text, "label": ent.label_, "start": ent.start_char, "end": ent.end_char})
    return entities


def detect_negations(text: str) -> list[str]:
    """
    Detecta expresiones negativas como 'no hay X', 'sin Y', 'ningún Z'.
    Retorna lista de cosas negadas.
    """
    negated = []
    patterns = [
        r'\bno\s+hay\s+([\w\s]+?)(?:[,.]|$)',
        r'\bsin\s+([\w\s]+?)(?:[,.]|$)',
        r'\bningún[a]?\s+([\w\s]+?)(?:[,.]|$)',
        r'\bausentes?\s+([\w\s]+?)(?:[,.]|$)',
    ]
    for pat in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            negated.append(m.group(1).strip())
    return negated


def detect_cross_references(text: str) -> list[dict]:
    """
    Detecta referencias cruzadas como:
    - 'el reflejo en el espejo muestra X'
    - 'visible a través de Y'
    - 'que aparece en la escena anterior'
    """
    refs = []
    patterns = [
        (r'reflejo en (?:el|la)\s+([\w\s]+?)\s+(?:muestra|refleja)\s+([\w\s]+?)(?:[,.]|$)',
         "reflection"),
        (r'visible a través de\s+([\w\s]+?)(?:[,.]|$)',
         "visible_through"),
        (r'mismo\s+(\w+)\s+que en\s+([\w\s]+?)(?:[,.]|$)',
         "character_consistency"),
    ]
    for pat, ref_type in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            refs.append({"type": ref_type, "groups": list(m.groups()), "raw": m.group(0)})
    return refs


def detect_character_names(text: str) -> list[str]:
    """
    Detecta nombres propios de personajes para registrar en ip_adapter.
    Heurística simple: palabras capitalizadas que no sean inicio de oración.
    Refuerza con spaCy si disponible.
    """
    names = set()
    nlp = get_nlp()
    if nlp:
        doc = nlp(text)
        for ent in doc.ents:
            if ent.label_ == "PER":
                names.add(ent.text)
    # Heurística de respaldo: palabras capitalizadas precedidas por coma o enumeración
    for m in re.finditer(r'(?:,|\b)([A-Z][a-záéíóúüñ]{2,})(?:\s|,)', text):
        names.add(m.group(1))
    return list(names)


def extract_attributes_from_chunk(chunk: str) -> ObjectAttributes:
    """
    Extrae atributos de un fragmento de texto relativo a un objeto.
    """
    tokens = tokenize_basic(chunk)
    attr = ObjectAttributes()

    for tok in tokens:
        if tok in COLOR_TOKENS:
            attr.color.append(COLOR_TOKENS[tok])
        if tok in MATERIAL_TOKENS:
            attr.material.append(MATERIAL_TOKENS[tok])
        if tok in POSE_TOKENS:
            attr.pose = POSE_TOKENS[tok]
        if tok in LIGHTING_TOKENS:
            attr.lighting = LIGHTING_TOKENS[tok]
        if tok in STATE_TOKENS:
            attr.state.append(STATE_TOKENS[tok])

    # Negaciones dentro del chunk
    attr.negations = detect_negations(chunk)
    # Referencias cruzadas dentro del chunk
    refs = detect_cross_references(chunk)
    attr.cross_refs = [r["raw"] for r in refs]

    return attr


# ═══════════════════════════════════════════════════════════════════════════════
# 3. ASIGNACIÓN ESPACIAL
# ═══════════════════════════════════════════════════════════════════════════════

def center_to_bbox(cx: float, cy: float, w: float, h: float) -> BoundingBox:
    """Convierte (cx, cy, w, h) a BoundingBox con clamp [0,1]."""
    return BoundingBox(
        x_min=max(0.0, cx - w / 2),
        y_min=max(0.0, cy - h / 2),
        x_max=min(1.0, cx + w / 2),
        y_max=min(1.0, cy + h / 2),
    )


def resolve_spatial_anchor(obj_key: str, context: dict) -> BoundingBox:
    """
    Busca el ancla espacial más cercana para un objeto dado.
    context puede incluir overrides manuales.
    """
    if obj_key in context.get("overrides", {}):
        o = context["overrides"][obj_key]
        return BoundingBox(*o)

    # Búsqueda aproximada por subcadena
    for anchor_key, params in SPATIAL_ANCHORS.items():
        if anchor_key in obj_key or obj_key in anchor_key:
            return center_to_bbox(*params)

    return center_to_bbox(*SPATIAL_ANCHORS["default"])


def assign_layer(obj_key: str, bbox: BoundingBox) -> str:
    """Asigna capa semántica según y_max y objeto."""
    if any(k in obj_key for k in ["fondo", "exterior", "cielo", "torre"]):
        return "background"
    if any(k in obj_key for k in ["mesa", "libro", "croissant", "taza"]):
        return "foreground"
    return "midground"


def determine_controlnets(obj_type: str, attributes: ObjectAttributes) -> list[str]:
    """
    Selecciona ControlNets apropiados para el objeto.
    """
    nets = set()
    for key, value in CONTROLNET_RULES.items():
        if key in obj_type:
            nets.update(value)

    # Reglas adicionales por atributo
    if attributes.pose:
        nets.add("openpose")
    if attributes.cross_refs:
        nets.add("seg")  # segmentación para referencias cruzadas
    if "glass" in attributes.material or "fogged" in attributes.state:
        nets.add("canny")

    return sorted(nets)


def build_ip_adapter_config(character_name: str, controlnets: list[str]) -> dict:
    """
    Genera configuración de IP-Adapter para consistencia de personaje.
    """
    return {
        "enabled": True,
        "character_id": character_name.lower().replace(" ", "_"),
        "model": "ip-adapter-plus-face_sdxl_vit-h",
        "weight": 0.6,
        "note": f"Consistencia de rostro/identidad para '{character_name}'. "
                "Requiere imagen de referencia en node IPAdapterAdvanced.",
        "requires_reference_image": True,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 4. EXTRACCIÓN DE OBJETOS DESDE EL PROMPT
# ═══════════════════════════════════════════════════════════════════════════════

# Patrones de objeto con su clave de ancla espacial y tipo semántico
OBJECT_PATTERNS = [
    # (regex, anchor_key, semantic_type, layer_hint)
    (r'mujer\s+(?:joven|adulta|mayor)?', "sujeto_principal", "persona", "midground"),
    (r'hombre\s+(?:joven|adulto|mayor)?', "sujeto_principal", "persona", "midground"),
    (r'(?:el\s+)?vapor\b', "vapor", "objeto", "foreground"),
    (r'(?:la\s+)?taza\s+de\s+caf[eé]', "taza", "objeto", "foreground"),
    (r'(?:la\s+)?taza\b', "taza", "objeto", "foreground"),
    (r'(?:la\s+)?mano\s+derecha', "mano_derecha", "mano", "foreground"),
    (r'(?:la\s+)?mano\s+izquierda', "mano_derecha", "mano", "foreground"),
    (r'(?:la\s+)?ventana\b', "ventana", "objeto", "midground"),
    (r'(?:la\s+)?Torre\s+Eiffel', "torre_eiffel", "edificio", "background"),
    (r'(?:la\s+)?torre\s+eiffel', "torre_eiffel", "edificio", "background"),
    (r'(?:el\s+)?libro\b', "libro", "objeto", "foreground"),
    (r'(?:el\s+)?croissant\b', "croissant", "objeto", "foreground"),
    (r'(?:la\s+)?mesa\b', "mesa", "objeto", "foreground"),
    (r'(?:el\s+)?fondo\b', "fondo", "interior", "background"),
    (r'exterior\b', "exterior", "interior", "background"),
    (r'(?:el\s+)?reflejo\b', "reflejo", "objeto", "midground"),
    (r'(?:el\s+)?espejo\b', "espejo", "objeto", "midground"),
    (r'(?:la\s+)?luz\b', "default", "luz", "midground"),
    (r'(?:el\s+)?sol\b', "exterior", "luz", "background"),
    (r'(?:el\s+)?caf[eé]\s+parisi(?:no|én)', "fondo", "interior", "background"),
]


def extract_sentence_context(pattern: str, full_text: str, window: int = 200) -> str:
    """Extrae el contexto de la oración donde aparece un objeto."""
    m = re.search(pattern, full_text, re.IGNORECASE)
    if not m:
        return ""
    start = max(0, m.start() - window // 2)
    end = min(len(full_text), m.end() + window // 2)
    return full_text[start:end]


def parse_objects(text: str, character_registry: dict) -> list[RegionalObject]:
    """
    Detecta todos los objetos en el texto, asigna bboxes, atributos y ControlNets.
    """
    objects = []
    negated_things = detect_negations(text)
    cross_refs = detect_cross_references(text)

    seen = set()
    obj_counter = {}

    for pattern, anchor_key, sem_type, layer_hint in OBJECT_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            # Generar ID único
            base_id = anchor_key
            obj_counter[base_id] = obj_counter.get(base_id, 0) + 1
            obj_id = f"{base_id}_{obj_counter[base_id]:02d}" if obj_counter[base_id] > 1 else base_id
            if obj_id in seen:
                continue
            seen.add(obj_id)

            # Contexto de la oración
            chunk = extract_sentence_context(pattern, text)

            # Atributos
            attrs = extract_attributes_from_chunk(chunk)

            # ¿Es un objeto negado?
            label_match = re.search(pattern, text, re.IGNORECASE)
            label_text = label_match.group(0).strip() if label_match else base_id
            is_negated = any(neg.lower() in label_text.lower() for neg in negated_things)

            # Spatial
            bbox = resolve_spatial_anchor(anchor_key, {})
            layer = assign_layer(anchor_key, bbox)

            # ControlNets
            cnets = determine_controlnets(sem_type, attrs)

            # IP-Adapter para personajes conocidos
            ip_adap = None
            if sem_type == "persona":
                # Buscar nombre en registry
                for name in character_registry:
                    if name.lower() in text.lower():
                        ip_adap = build_ip_adapter_config(name, cnets)
                if ip_adap is None and sem_type == "persona":
                    ip_adap = build_ip_adapter_config("protagonist", cnets)

            # Añadir referencias cruzadas al objeto relevante
            for ref in cross_refs:
                for g in ref["groups"]:
                    if g and g.lower() in label_text.lower():
                        attrs.cross_refs.append(ref["raw"])

            # Peso de atención: sujeto principal recibe mayor peso
            weight = 1.4 if "sujeto_principal" in anchor_key else 1.0
            weight = 0.0 if is_negated else weight

            obj = RegionalObject(
                id=obj_id,
                label=label_text,
                bbox=bbox,
                attributes=attrs,
                prompt_weight=weight,
                controlnets=cnets,
                ip_adapter=ip_adap,
                layer=layer,
                negation=is_negated,
            )
            objects.append(obj)

    return objects


# ═══════════════════════════════════════════════════════════════════════════════
# 5. EXTRACCIÓN DE METADATOS DE ESCENA
# ═══════════════════════════════════════════════════════════════════════════════

def extract_scene_metadata(text: str) -> SceneMetadata:
    """
    Infiere metadatos globales de la escena desde el texto.
    """
    meta = SceneMetadata()
    text_low = text.lower()

    # Hora del día
    time_map = {
        "atardecer": "golden hour / sunset",
        "amanecer": "dawn / sunrise",
        "noche": "night",
        "mediodía": "midday",
        "mañana": "morning",
        "tarde": "afternoon",
    }
    for kw, val in time_map.items():
        if kw in text_low:
            meta.time_of_day = val
            break

    # Ángulo de cámara
    cam_map = {
        "contrapicada": "low angle shot",
        "picada": "high angle shot",
        "frontal": "straight-on shot",
        "perfil": "side profile shot",
        "ojo de pájaro": "bird's eye view",
    }
    for kw, val in cam_map.items():
        if kw in text_low:
            meta.camera_angle = val
            break

    # Distancia de cámara
    dist_map = {
        "primer plano": "close-up",
        "plano medio": "medium shot",
        "plano entero": "full shot",
        "plano general": "wide shot",
        "interior": "interior",
        "vista desde el interior": "interior wide shot",
    }
    for kw, val in dist_map.items():
        if kw in text_low:
            meta.camera_distance = val
            break

    # Iluminación
    light_map = {
        "anaranjada": "warm orange light",
        "dorada": "golden light",
        "difusa": "soft diffuse light",
        "lateral": "rim lighting",
        "perfil": "side lighting",
    }
    for kw, val in light_map.items():
        if kw in text_low:
            meta.lighting_mood = val
            break

    # Tipo de lugar
    loc_map = {
        "café": "indoor café",
        "restaurante": "restaurant",
        "estudio": "studio",
        "exterior": "outdoor",
        "parque": "park",
        "parisino": "Parisian café interior",
    }
    for kw, val in loc_map.items():
        if kw in text_low:
            meta.location_type = val
            break

    # Aspect ratio por tipo de shot
    if meta.camera_distance in ("wide shot", "interior wide shot"):
        meta.aspect_ratio = "landscape_16_9"
    elif meta.camera_distance in ("close-up",):
        meta.aspect_ratio = "portrait_2_3"
    else:
        meta.aspect_ratio = "landscape_3_2"

    # Estilo por defecto: fotorrealista (no se menciona otro)
    meta.style = "photorealistic cinematic"

    return meta


# ═══════════════════════════════════════════════════════════════════════════════
# 6. SISTEMA DE PREGUNTAS DE CLARIFICACIÓN
# ═══════════════════════════════════════════════════════════════════════════════

def generate_clarification_questions(meta: SceneMetadata, objects: list[RegionalObject]) -> list[str]:
    """
    Genera preguntas de clarificación para campos críticos no detectados.
    """
    questions = []

    meta_dict = asdict(meta)
    for field_name, question in CRITICAL_FIELDS.items():
        if meta_dict.get(field_name) is None:
            questions.append(question)

    # Preguntas sobre consistencia de personajes
    has_person = any(o for o in objects if "persona" in str(o.controlnets) or o.ip_adapter)
    if has_person:
        has_ip = any(o.ip_adapter for o in objects)
        if has_ip:
            questions.append(
                "Para mantener consistencia del personaje, ¿deseas proporcionar una imagen de referencia "
                "del rostro/cuerpo? Si es así, descríbela o adjúntala."
            )

    # Preguntas sobre referencias cruzadas complejas
    all_refs = []
    for obj in objects:
        all_refs.extend(obj.attributes.cross_refs)
    if all_refs:
        questions.append(
            f"Se detectaron referencias cruzadas complejas: {'; '.join(all_refs[:2])}. "
            "¿Puedes especificar exactamente qué debe verse en cada elemento referenciado?"
        )

    # Preguntas sobre paleta de color
    all_colors = []
    for obj in objects:
        all_colors.extend(obj.attributes.color)
    if len(all_colors) < 2:
        questions.append(
            "¿Deseas especificar una paleta de color dominante para la imagen? "
            "(e.g., tonos cálidos, paleta complementaria azul-naranja, monocromático)"
        )

    return questions


# ═══════════════════════════════════════════════════════════════════════════════
# 7. GENERACIÓN DE PLANTILLA DE NODOS COMFYUI
# ═══════════════════════════════════════════════════════════════════════════════

def build_comfyui_node_template(
    meta: SceneMetadata,
    objects: list[RegionalObject],
    character_registry: dict,
) -> dict:
    """
    Genera un template JSON compatible con la ComfyUI API (node graph).
    """
    nodes = {}
    node_id = 1

    # ── Checkpoint Loader ──────────────────────────────────────────────────────
    nodes[str(node_id)] = {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {"ckpt_name": "realvisXL_v40.safetensors"},
        "_comment": "Reemplaza con tu modelo SDXL preferido",
    }
    ckpt_id = node_id; node_id += 1

    # ── CLIP Text Encode (positive global) ────────────────────────────────────
    global_positive = _build_global_positive_prompt(meta, objects)
    nodes[str(node_id)] = {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "text": global_positive,
            "clip": [str(ckpt_id), 1],
        },
        "_comment": "Prompt positivo global con énfasis en atmósfera",
    }
    clip_pos_id = node_id; node_id += 1

    # ── CLIP Text Encode (negative global) ────────────────────────────────────
    global_negative = _build_global_negative_prompt(objects)
    nodes[str(node_id)] = {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "text": global_negative,
            "clip": [str(ckpt_id), 1],
        },
        "_comment": "Prompt negativo global",
    }
    clip_neg_id = node_id; node_id += 1

    # ── Empty Latent Image ─────────────────────────────────────────────────────
    w, h = _aspect_to_dims(meta.aspect_ratio)
    nodes[str(node_id)] = {
        "class_type": "EmptyLatentImage",
        "inputs": {"width": w, "height": h, "batch_size": 1},
    }
    latent_id = node_id; node_id += 1

    # ── Regional Conditioning (BREAK method) ──────────────────────────────────
    regional_prompts = []
    for obj in objects:
        if obj.negation:
            continue
        rp = {
            "object_id": obj.id,
            "label": obj.label,
            "bbox": obj.bbox.as_list(),
            "layer": obj.layer,
            "prompt": _build_object_prompt(obj),
            "weight": obj.prompt_weight,
            "controlnets": obj.controlnets,
        }
        regional_prompts.append(rp)

    nodes[str(node_id)] = {
        "class_type": "RegionalPrompting",
        "_note": "Usa el plugin 'ComfyUI-Inspire-Pack' o 'Regional-Prompter'",
        "inputs": {
            "base_ratios": "0.2",  # threshold atención base vs regional
            "regions": regional_prompts,
            "base_positive": [str(clip_pos_id), 0],
            "base_negative": [str(clip_neg_id), 0],
        },
        "_comment": "Prompting regional con bounding boxes por objeto",
    }
    regional_id = node_id; node_id += 1

    # ── ControlNet Nodes ────────────────────────────────────────────────────────
    all_cnets = set()
    for obj in objects:
        all_cnets.update(obj.controlnets)

    cnet_model_map = {
        "openpose": "control_v11p_sd15_openpose.pth",
        "depth":    "control_v11f1p_sd15_depth.pth",
        "canny":    "control_v11p_sd15_canny.pth",
        "seg":      "control_v11p_sd15_seg.pth",
    }
    cnet_strength_map = {
        "openpose": 0.85,
        "depth":    0.75,
        "canny":    0.60,
        "seg":      0.65,
    }

    for cnet_type in sorted(all_cnets):
        nodes[str(node_id)] = {
            "class_type": "ControlNetLoader",
            "inputs": {"control_net_name": cnet_model_map.get(cnet_type, f"{cnet_type}.pth")},
            "_comment": f"ControlNet: {cnet_type}",
        }
        cnet_loader_id = node_id; node_id += 1

        nodes[str(node_id)] = {
            "class_type": "ControlNetApplyAdvanced",
            "inputs": {
                "positive":     [str(regional_id), 0],
                "negative":     [str(clip_neg_id), 0],
                "control_net":  [str(cnet_loader_id), 0],
                "image":        f"PLACEHOLDER_{cnet_type.upper()}_MAP",
                "strength":     cnet_strength_map.get(cnet_type, 0.7),
                "start_percent": 0.0,
                "end_percent":  0.85,
            },
            "_comment": f"Aplica {cnet_type} — reemplaza image con el mapa correspondiente",
        }
        node_id += 1

    # ── IP-Adapter Nodes ───────────────────────────────────────────────────────
    for obj in objects:
        if obj.ip_adapter and obj.ip_adapter.get("enabled"):
            nodes[str(node_id)] = {
                "class_type": "IPAdapterAdvanced",
                "inputs": {
                    "model":          [str(ckpt_id), 0],
                    "ipadapter":      obj.ip_adapter["model"],
                    "image":          f"PLACEHOLDER_REF_IMAGE_{obj.ip_adapter['character_id'].upper()}",
                    "weight":         obj.ip_adapter["weight"],
                    "weight_type":    "linear",
                    "start_at":       0.0,
                    "end_at":         0.75,
                    "combine_embeds": "concat",
                },
                "_comment": obj.ip_adapter["note"],
            }
            node_id += 1

    # ── KSampler ────────────────────────────────────────────────────────────────
    nodes[str(node_id)] = {
        "class_type": "KSampler",
        "inputs": {
            "model":       [str(ckpt_id), 0],
            "positive":    [str(regional_id), 0],
            "negative":    [str(clip_neg_id), 0],
            "latent_image":[str(latent_id), 0],
            "seed":        42,
            "steps":       30,
            "cfg":         7.5,
            "sampler_name": "dpmpp_2m",
            "scheduler":   "karras",
            "denoise":     1.0,
        },
        "_comment": "Ajusta seed, steps y cfg según resultado",
    }
    ksampler_id = node_id; node_id += 1

    # ── VAE Decode + Save ──────────────────────────────────────────────────────
    nodes[str(node_id)] = {
        "class_type": "VAEDecode",
        "inputs": {
            "samples": [str(ksampler_id), 0],
            "vae":     [str(ckpt_id), 2],
        },
    }
    vae_id = node_id; node_id += 1

    nodes[str(node_id)] = {
        "class_type": "SaveImage",
        "inputs": {
            "images":   [str(vae_id), 0],
            "filename_prefix": "deep_parser_output",
        },
    }

    return nodes


def _aspect_to_dims(aspect: str) -> tuple[int, int]:
    mapping = {
        "landscape_16_9": (1344, 768),
        "landscape_3_2":  (1216, 832),
        "portrait_2_3":   (832, 1216),
        "square":         (1024, 1024),
    }
    return mapping.get(aspect, (1216, 832))


def _build_object_prompt(obj: RegionalObject) -> str:
    """Construye el sub-prompt para un objeto regional."""
    parts = [obj.label]
    if obj.attributes.color:
        parts.append(", ".join(obj.attributes.color))
    if obj.attributes.material:
        parts.append(", ".join(obj.attributes.material))
    if obj.attributes.pose:
        parts.append(obj.attributes.pose)
    if obj.attributes.state:
        parts.append(", ".join(obj.attributes.state))
    if obj.attributes.lighting:
        parts.append(obj.attributes.lighting)
    prompt = ", ".join(parts)
    # Aplicar peso de atención
    if obj.prompt_weight != 1.0:
        prompt = f"({prompt}:{obj.prompt_weight:.1f})"
    return prompt


def _build_global_positive_prompt(meta: SceneMetadata, objects: list[RegionalObject]) -> str:
    parts = []
    if meta.location_type:
        parts.append(meta.location_type)
    if meta.time_of_day:
        parts.append(meta.time_of_day)
    if meta.lighting_mood:
        parts.append(meta.lighting_mood)
    if meta.camera_angle:
        parts.append(meta.camera_angle)
    if meta.camera_distance:
        parts.append(meta.camera_distance)
    if meta.style:
        parts.append(meta.style)
    parts.append("highly detailed, 8k, sharp focus, masterpiece")
    return ", ".join(parts)


def _build_global_negative_prompt(objects: list[RegionalObject]) -> str:
    base = [
        "lowres, bad anatomy, bad hands, blurry, watermark",
        "text, signature, cropped, worst quality, normal quality",
        "ugly, duplicate, morbid, mutilated, extra fingers",
    ]
    # Agregar negaciones explícitas del prompt
    for obj in objects:
        for neg in obj.attributes.negations:
            base.append(neg)
    # Objetos marcados como negados
    for obj in objects:
        if obj.negation:
            base.append(obj.label)
    return ", ".join(base)


# ═══════════════════════════════════════════════════════════════════════════════
# 8. PIPELINE PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════════

def deep_parse(text: str, spatial_overrides: Optional[dict] = None) -> ParsedScene:
    """
    Pipeline completo: texto → ParsedScene estructurado.

    Args:
        text: Descripción del usuario (cualquier longitud).
        spatial_overrides: Diccionario opcional {anchor_key: [x_min,y_min,x_max,y_max]}
                           para forzar bounding boxes específicos.

    Returns:
        ParsedScene con todos los campos poblados.
    """
    # 1. Registro de personajes
    char_names = detect_character_names(text)
    character_registry = {
        name: build_ip_adapter_config(name, []) for name in char_names
    }

    # 2. Metadatos de escena
    meta = extract_scene_metadata(text)

    # 3. Extracción de objetos
    objects = parse_objects(text, character_registry)

    # 4. Negaciones globales
    global_negations = detect_negations(text)

    # 5. Preguntas de clarificación
    questions = generate_clarification_questions(meta, objects)

    # 6. Plantilla ComfyUI
    comfy_template = build_comfyui_node_template(meta, objects, character_registry)

    return ParsedScene(
        metadata=meta,
        objects=objects,
        global_negative_prompt=global_negations,
        clarification_questions=questions,
        character_registry=character_registry,
        comfyui_node_template=comfy_template,
    )


def scene_to_dict(scene: ParsedScene) -> dict:
    """Serializa ParsedScene a dict JSON-compatible."""
    def obj_to_dict(o: RegionalObject) -> dict:
        return {
            "id": o.id,
            "label": o.label,
            "bbox": o.bbox.as_list(),
            "layer": o.layer,
            "negation": o.negation,
            "prompt_weight": o.prompt_weight,
            "attributes": {
                "color":     o.attributes.color,
                "material":  o.attributes.material,
                "pose":      o.attributes.pose,
                "lighting":  o.attributes.lighting,
                "state":     o.attributes.state,
                "texture":   o.attributes.texture,
                "negations": o.attributes.negations,
                "cross_refs":o.attributes.cross_refs,
            },
            "controlnets": o.controlnets,
            "ip_adapter":  o.ip_adapter,
        }

    return {
        "metadata": {
            "time_of_day":       scene.metadata.time_of_day,
            "weather":           scene.metadata.weather,
            "camera_angle":      scene.metadata.camera_angle,
            "camera_distance":   scene.metadata.camera_distance,
            "lighting_mood":     scene.metadata.lighting_mood,
            "location_type":     scene.metadata.location_type,
            "style":             scene.metadata.style,
            "aspect_ratio":      scene.metadata.aspect_ratio,
        },
        "objects":                [obj_to_dict(o) for o in scene.objects],
        "global_negative_prompt": scene.global_negative_prompt,
        "clarification_questions":scene.clarification_questions,
        "character_registry":     scene.character_registry,
        "comfyui_node_template":  scene.comfyui_node_template,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 9. ENTRYPOINT / DEMO
# ═══════════════════════════════════════════════════════════════════════════════

TEST_PROMPT = """
Una mujer joven con un vestido azul eléctrico, sentada en un café parisino al atardecer.
Sostiene una taza de café humeante en la mano derecha, el vapor forma espirales.
Al fondo, la Torre Eiffel visible a través de una ventana empañada.
La luz anaranjada del sol golpea su perfil izquierdo.
En la mesa hay un libro abierto con letras ilegibles y un croissant intacto.
La composición es una vista desde el interior, ligeramente contrapicada.
No hay otras personas.
"""

if __name__ == "__main__":
    prompt = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else TEST_PROMPT
    print("=" * 60)
    print("DEEP PARSER — ComfyUI Regional Prompt Generator")
    print("=" * 60)
    print(f"\nPrompt ({len(prompt)} chars):\n{prompt.strip()}\n")

    scene = deep_parse(prompt)
    result = scene_to_dict(scene)

    output = json.dumps(result, ensure_ascii=False, indent=2)
    print(output)

    # Guardar JSON
     # out_path = "/mnt/user-data/outputs/deep_parser_output.json"
    # with open(out_path, "w", encoding="utf-8") as f:
    #     f.write(output)