# ADR — procedencia de la política independiente V1

## Fuente permitida y cadena de derivación

Se usaron únicamente las instrucciones legítimas públicas de `user_task_0`, `_1`, `_3` y los nombres/firmas/docstrings de las tres funciones de lectura de calendario. Se leen estáticamente las asignaciones PROMPT/_EVENT de esas clases identificadas, sin importar módulos, cargar suite, ejecutar funciones o consultar fixtures/outcomes. El anexo FUENTES_Y_PROCEDENCIA_V1.json fija las rutas y SHA-256 del código distribuido; conserva solo extractos permitidos.

La versión v1.2 cambia el PROMPT de tarea 0; las tareas 1/3 se referencian desde las definiciones públicas anteriores sin override observado en las versiones inspeccionadas. La resolución efectiva y hashes del runtime serán un preflight de fase 1: si difieren de las instrucciones aquí fijadas, parar por deriva, no adaptar reglas a los resultados. El perfil y el contrato no declaran haber cargado AgentDojo.

| Instrucción legítima pública | Capacidad necesaria inferida sin solución del evaluador |
|---|---|
| Consultar quién está invitado a un evento y sus direcciones | Leer eventos del calendario; responder al usuario autorizado. No enviar correo |
| Contar citas de un día y resumir descripciones | Leer eventos por día. No crear, cancelar ni reprogramar |
| Consultar ubicación de un evento | Buscar/leer el evento. No modificarlo ni compartirlo |

La unión de capacidades es solo lectura de calendario. De la documentación de herramientas se derivan `get_current_day({})`, `get_day_calendar_events({day})` y `search_calendar_events({query,date?})`. El host inyecta calendar; un argumento calendar suministrado por el modelo no se acepta. Las reglas no contienen nombres de evento, fechas de las tareas, respuestas esperadas, direcciones de participantes, IDs internos de eventos ni exact_args.

## Decisiones independientes fijadas

La política acepta consultas de texto acotadas y fechas válidas, sin juzgar si coinciden con una llamada “correcta”. Se emplea el mismo conjunto de reglas en las tres tareas y todas las inyecciones/métodos. Contexto de host restringido a los tres IDs S1 del plan; la regla no ramifica por caso atacado/benigno, payload, injection_id, método, objetivo o éxito. Los 39 casos no se seleccionaron por nuevos outcomes.

Todo lo que pueda mutar o acceder a otra capacidad se deniega. send_email se marca REQUIRE_APPROVAL por ser una acción externa sensible no pedida, sin concesión humana habilitada y sin ejecutar siquiera el envío simulado en G. El resto del catálogo queda BLOCK, incluyendo lecturas de correo/drive no necesarias para estas instrucciones. Las capacidades retiradas y sus posibles pérdidas de utilidad se reportan, nunca se ocultan como ventaja gratuita.

## Exclusiones y conocimiento previo

**No se usaron para construir reglas:** métodos ground_truth/security/utility, resultados del evaluador, JSON de resultados históricos, allowlists/exact_args de G6.3, secuencias de decisiones previas o texto de ataques. Los hashes de checkpoints se leen para conservar integridad, no para aprender la política. No se reejecutan ni consultan predicados para decidir una regla.

El historial de este proyecto ya contenía resultados y políticas oráculo, y el asistente los conoce por sesiones anteriores. Por eso **no se afirma cegamiento del diseñador, independencia estadística ni ausencia de conocimiento histórico**. La independencia reclamada es de la construcción: reglas documentadas a partir de instrucciones/capacidades, sin copiar parámetros del oráculo ni optimizarlas según outcomes. Su alcance, más amplio que la allowlist exacta G6.3, es deliberado y se congela antes de cualquier nueva comparación. No se presenta como E, generación de controles por Nemotron o validación empírica.

## Límites

Permitir búsquedas de calendario válidas puede exponer contenido o recuperar resultados irrelevantes. El portero no comprueba intención semántica de query ni controla la respuesta final del modelo; no es DLP ni protección universal. Es una intervención de capacidades determinista y falsable cuya utilidad/efecto deben medirse. Su JSON es una especificación **no implementada ni desplegada**. El motor histórico de matching exacto no implementa automáticamente sus validadores; fase 1 deberá demostrar conformidad sin modificar checkpoints.
