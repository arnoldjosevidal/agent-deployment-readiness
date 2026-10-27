# ADR — criterios de salida Gate A y entrada a fase 1

## A. Salida documental de fase 0

| ID | Criterio objetivo | Documento que lo satisface | Qué no se atribuye |
|---|---|---|---|
| GA-01 | Mandato/alcance y numeración originales identificados; Windows/Nemotron/Nebius y MVP fijados | CONTRATO, apartado 1; referencia a reconciliación | Cierre funcional o autorización de gasto |
| GA-02 | 39 por modo, 78 posiciones únicas, 3 benignos/36 atacados por modo y una ronda | PLAN_78; CONTRATO 2 | Ejecución de episodios |
| GA-03 | A y G definidos, única intervención de portero; mismas herramientas/prompt/parser/evaluación | CONTRATO 3; PERFIL | Comparación ya ejecutada |
| GA-04 | Política completa, determinista y fail-closed, contexto/argumentos, ALLOW/BLOCK/REQUIRE_APPROVAL sin concesión humana | POLITICA_PORTERO_INDEPENDIENTE | Implementación o pruebas de sus validadores |
| GA-05 | Procedencia documentada desde instrucciones públicas/capacidades, sin ground_truth/outcomes como constructores | PROCEDENCIA; FUENTES_Y_PROCEDENCIA | Cegamiento o independencia estadística |
| GA-06 | Perfil de comparabilidad, orden/semillas, caps y fuentes candidato; incertidumbre de proveedor declarada | PERFIL; CONTRATO 2/5 | Disponibilidad/coste/revisión de proveedor verificados |
| GA-07 | Métricas, booleanos, denominadores, datos desconocidos y faltantes establecidos | CONTRATO 6 | Umbral de eficacia/S2 o resultados nuevos |
| GA-08 | Eventos/IDs, evidencia durable, privacidad, integridad y no sobrescritura definidos | CONTRATO 7 | Certificación del runtime de fase 1 |
| GA-09 | Errores, reintentos, reservas, paradas, parciales y recuperación predeclarados | CONTRATO 8/9 | Reejecuciones autorizadas |
| GA-10 | Alcance de conclusiones, kill/pivot y veredicto conservador establecidos, opcionales fuera del gate | CONTRATO 1/9 | Mejora causal, deploy real o eficacia Nemotron |
| GA-11 | Freeze versionado, SHA-256 y acta emitidos; fuentes/checkpoints conservados | MANIFEST, SELLADO, ACTA; REVISION_DOCUMENTAL | Firma humana/custodia inmutable o checkpoint experimental |
| GA-12 | Separación clara de fase 1 y de toda autorización externa | Este documento y ACTA | Permiso implícito de continuar |

La revisión de estos criterios es documental: concordancia, integridad y completitud de las especificaciones. No es una batería de tests y no ejecuta el portero, benchmark, modelo, scripts de producto o parsers del runtime.

## B. Requisitos exactos para iniciar fase 1 — todavía NO iniciada

1. **Nuevo mandato explícito de fase 1**, limitado inicialmente a integración offline si así se solicita. Referenciar freeze_id, hash de MANIFEST y acta PASS; no inferir autorización por haber cerrado Gate A.
2. **Copia/versión aislada** nueva o rama apropiada autorizada; reutilizar R/PREP por hashes, sin modificar raíz histórica, checkpoints, candidato público congelado o este freeze. Conservar el contrato lógico A/G y sus límites; no reabrir B/C/E/S2.
3. **Implementar** en ese mandato posterior el runner completo, validadores de política conforme al JSON, contextos confiables, parser común, bypass A trazado como NOT_APPLICABLE, runtime simulado y persistencia por modelo/herramienta/evaluación. La API exact-match histórica y sus eventos no implementan por sí solos los validadores/decisión N/A nuevos; demostrar conformidad y compatibilidad acotada, sin editar R.
4. **Preflight offline reproducible** de versiones, instrucciones legítimas/S1 permitido y compatibilidad de cada par, catálogo/esquemas, fixtures/estados, vectores/payloads, seeds y parámetros; fijar hashes efectivos en un manifiesto runtime separado. No abrir S2 o resolver incompatibilidades excluyendo casos según resultados. Si cambia una condición del diseño, nueva versión documental antes de cualquier dato nuevo.
5. **Pruebas offline posteriores autorizadas**, con fixtures/mocks/red denegada, para igualdad de condiciones, reglas y feedback, bypass local A, ALLOW/BLOCK/REQUIRE_APPROVAL sin ejecución no autorizada, eventos completos, métricas/estados, límites, fallos y no sobrescritura. Registrar resultados reales; los 67/101 históricos no sustituyen estas verificaciones nuevas de integración.

Los puntos anteriores son requisitos/alcance propuesto, **no trabajo ejecutado ni autorizado por este mandato de Gate A**.

## C. Requisitos adicionales antes de cualquier integración real de fase 1

- Nuevo permiso específico para solicitudes a Nebius, con sesión/config_hash/expiry y límites finitos, gasto/créditos y fuente de precio. Permiso offline no basta. Autorización actual: cero.
- Cota de tokens de payload completo verificada para modelo/tokenizer, parámetros aceptados y límites por llamada/episodio/lote; sin retries ocultos. Si falta revisión de pesos, declarar NOT_EXPOSED; registrar identidad visible y detener por deriva, sin inventar hashes internos.
- Credenciales bajo control del operador Windows, nunca en chat/argv/logs. Sink durable listo, redacción y privacidad revisadas, entorno exclusivamente simulado para herramientas, no correo/cloud real ni VPS.
- Manifest runtime fijado, salida nueva de evidencia, stop seguro e integridad acreditados; definir qué caso mínimo del plan se usará en la integración y si puede contar para el lote por su mismo freeze/configuración. No duplicar ni reemplazar silenciosamente resultados.
- Si la integración mínima se ejecuta antes del freeze runtime definitivo o difiere de condiciones, etiquetarla INTEGRATION_ONLY y no contarla entre los 78. Si se ejecuta como posición predeclarada con el mismo freeze/runtime y cobertura válida, conservarla sin repetir y vincularla al piloto. La autorización del caso mínimo nunca autoriza automáticamente el lote completo de fase 2.

## D. Cierre de fase 1 y fronteras

Gate B requiere integración completa acreditada, medición fiable y un caso S1 controlado por modo, con trazas de modelo/herramientas/evaluación y errores, ejecutado solo con permisos adecuados; no es necesario que un ataque triunfe para reconocer una integración válida. El piloto 39+39 y su tabla pertenecen a fase 2; no se inicia desde Gate A. Demo/README/Git siguen siendo preparación paralela hasta sus gates de producto/release. Publicación/licencia, APIs reales y S2 requieren decisiones distintas.

Al terminar Gate A, mantener fases 1/2 BLOQUEADAS para cierre funcional y 3–6 PENDIENTES, con fase 0 CERRADA únicamente si todos GA-01…GA-12 quedan documentados/verificados. Detenerse.
