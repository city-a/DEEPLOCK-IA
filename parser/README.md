# Deeplock Deep Parser

Transforma descripciones ultra-detalladas en un JSON estructurado con:
- Bounding boxes regionales (0-1) para cada objeto.
- Atributos (color, material, pose, iluminación, estado).
- Mapeo automático de ControlNets e IP-Adapter.
- Plantilla de nodos para ComfyUI con prompting regional.
- Preguntas de clarificación para datos faltantes.

## 🧠 ¿Por qué?
Los generadores actuales ignoran relaciones espaciales complejas. Deeplock fuerza al modelo a respetar cada detalle, abriendo un control casi determinístico sobre la generación.

## ⚡ Demostración rápida
```bash
pip install spacy
python -m spacy download es_core_news_sm
python deep_parser.py "Una mujer joven con un vestido azul eléctrico, sentada en un café..."
