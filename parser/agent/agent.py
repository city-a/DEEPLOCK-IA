"""
agent.py — Deeplock Clarification Agent
========================================
Toma un prompt del usuario, lo analiza con el Deep Parser,
hace preguntas de clarificación interactivas y genera un nuevo JSON completo.
"""
import json
from deep_parser import deep_parse, scene_to_dict, ParsedScene

def run_clarification_loop(prompt: str) -> dict:
    print("\n" + "="*60)
    print("   DEEPLOCK AGENT — Clarificación interactiva")
    print("="*60)
    
    # Primer análisis
    print("\n🔍 Analizando tu descripción...")
    scene = deep_parse(prompt)
    result = scene_to_dict(scene)
    
    # Mostrar preguntas detectadas
    questions = result.get("clarification_questions", [])
    if not questions:
        print("✅ ¡Tu descripción ya es muy completa! No necesito más detalles.")
        return result
    
    print(f"\n📋 He detectado {len(questions)} detalles que faltan. Vamos a completarlos:\n")
    
    # Ir respondiendo una por una
    answers = {}
    for i, q in enumerate(questions, 1):
        print(f"[{i}/{len(questions)}] {q}")
        ans = input("Tu respuesta (o 'omitir' para dejarlo en blanco): ").strip()
        if ans.lower() != 'omitir' and ans != '':
            answers[q] = ans
        else:
            answers[q] = None
        print()
    
    # Reconstruir el prompt enriquecido con las respuestas
    enriched_prompt = prompt + "\n\nDetalles adicionales:\n"
    for q, ans in answers.items():
        if ans:
            enriched_prompt += f"- {q} → {ans}\n"
    
    print("🔄 Re-analizando con todos los detalles...")
    scene2 = deep_parse(enriched_prompt)
    final_result = scene_to_dict(scene2)
    
    print("\n✅ JSON final listo. Aquí está tu escena completa:\n")
    print(json.dumps(final_result, ensure_ascii=False, indent=2))
    
    # Guardar en archivo
    with open("deep_parser_final.json", "w", encoding="utf-8") as f:
        f.write(json.dumps(final_result, ensure_ascii=False, indent=2))
    print("\n💾 JSON guardado en 'deep_parser_final.json'")
    
    return final_result

# Modo demo si se ejecuta directamente
if __name__ == "__main__":
    prompt = """Una mujer joven con un vestido azul eléctrico, sentada en un café parisino al atardecer.
Sostiene una taza de café humeante en la mano derecha, el vapor forma espirales.
Al fondo, la Torre Eiffel visible a través de una ventana empañada.
La luz anaranjada del sol golpea su perfil izquierdo.
En la mesa hay un libro abierto con letras ilegibles y un croissant intacto.
La composición es una vista desde el interior, ligeramente contrapicada.
No hay otras personas."""
    
    run_clarification_loop(prompt)
