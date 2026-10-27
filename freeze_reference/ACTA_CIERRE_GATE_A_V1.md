# ADR — acta de cierre documental de FASE 0 / GATE A V1

**Veredicto: PASS DOCUMENTAL. FASE 0 / GATE A CERRADA.**

Freeze: `ADR_GATE_A_MVP_FREEZE_V1_20261015`. Fecha documental de referencia: 15/10/2026. Cierre técnico realizado por Codex bajo el mandato explícito de Arnold «CIERRE FASE 0 / GATE A». No constituye firma humana, autorización de gasto, publicación, implementación o evaluación experimental.

## 1. Alcance que se cierra

Se consolida el contrato MVP de Nemotron mediante Nebius sobre portátil Windows; comparación S1 **39 casos sin portero +39 con portero =78**, 3 benignos y 36 atacados por modo; una ronda. Se definen el bypass A y la política manual G de solo lectura de calendario, condiciones comunes, métricas/denominadores, trazas, errores, paradas, recursos y límites de las conclusiones. B/C/E/no-inferioridad/S2 no bloquean este MVP.

El informe de reconciliación del 15/10 sigue siendo la referencia histórica de numeración/requisitos. Esta acta lo suplementa exclusivamente con el cierre de su pendiente de fase 0; no reescribe su diagnóstico a la fecha de corte ni declara cerradas fases posteriores.

## 2. Evidencias documentales fijadas

- `CONTRATO_OPERATIVO_MVP_V1.md`: ambos modos, perfil, observables, reglas de interpretación/parada y alcance de readiness.
- `POLITICA_PORTERO_INDEPENDIENTE_V1.json`: tres capacidades de lectura ALLOW; send_email REQUIRE_APPROVAL sin ejecución/concesión; default BLOCK; contexto del host, argumentos y prioridades completos.
- `PROCEDENCIA_POLITICA_V1.md` y `FUENTES_Y_PROCEDENCIA_V1.json`: instrucciones públicas y firmas/docstrings; sin ground_truth, respuestas esperadas, exact_args oráculo o outcomes como constructores. El conocimiento histórico del diseñador se declara; no se afirma cegamiento.
- `PERFIL_COMPARABILIDAD_V1.json`: hardware/OS, versiones previstas, modelo, mensaje común, decodificación, reglas de igualdad, caps técnicos y autorización activa cero.
- `PLAN_78_EPISODIOS_V1.json`: 78 posiciones únicas/39 pares, orden predeclarado; ninguna ejecutada y sin resultados sintéticos disfrazados.
- `CRITERIOS_GATE_A_Y_ENTRADA_FASE1_V1.md`: salida documental y requisitos separados de implementación offline/llamadas reales.
- `REVISION_DOCUMENTAL_GATE_A_V1.json`: GA-01…GA-12 PASS por cotejo documental y hashes; no es un log de pruebas de producto.
- `REFERENCIAS_PREVIAS_NO_MODIFICABLES_V1.json`: 564 archivos anteriores fijados por SHA-256, incluidos checkpoints y fuentes; todos coinciden antes de persistir. Se comprueban otra vez al sellar.

Huellas principales de especificación:

| Artefacto | SHA-256 |
|---|---|
| Política | `5456972d96b332e5a0746a95d44cb8e749512259b123c57edb4039c60a202c27` |
| Perfil | `8d45bbdc7e630bdd686beebb95bd0d52714b9d041ad20bf7995f9b0db165e674` |
| Plan 78 | `b2e73ec4cf42e1570e1b89d40e856913b6a039b73a85dc3d5524566c1534f71d` |

El manifiesto de bytes `MANIFEST_SHA256.json` y el `SELLADO_DOCUMENTAL.json` final fijan el conjunto canónico. El sello enlaza el hash del manifiesto; el recibo de mi_agente enlaza el sello. Manifiesto y sello quedan excluidos del propio manifiesto para evitar autorreferencias. No hay custodia hardware inmutable ni firma externa; no sobrescribir este paquete.

## 3. Resultado por criterio

| Criterio | Resultado | Evidencia |
|---|---|---|
| GA-01 | PASS documental | CRITERIOS/REVISION_DOCUMENTAL y sus referencias; Scope and authoritative reconciliation linked |
| GA-02 | PASS documental | CRITERIOS/REVISION_DOCUMENTAL y sus referencias; Explicit unique 78-row NOT_RUN plan; same 39 cases per mode |
| GA-03 | PASS documental | CRITERIOS/REVISION_DOCUMENTAL y sus referencias; Pair metadata and shared system/tool/runtime constraints defined |
| GA-04 | PASS documental | CRITERIOS/REVISION_DOCUMENTAL y sus referencias; Static policy specification complete; no policy execution performed |
| GA-05 | PASS documental | CRITERIOS/REVISION_DOCUMENTAL y sus referencias; Only permitted instruction/signature extracts support capability rules; no event/date solution rules; history familiarity disclosed |
| GA-06 | PASS documental | CRITERIOS/REVISION_DOCUMENTAL y sus referencias; Comparable parameters/caps/seeds fixed; actual authorization zero and runtime dependencies explicitly future |
| GA-07 | PASS documental | CRITERIOS/REVISION_DOCUMENTAL y sus referencias; Metrics, denominators, missingness and boolean polarity explicitly specified |
| GA-08 | PASS documental | CRITERIOS/REVISION_DOCUMENTAL y sus referencias; Durable trace/privacy/evidence specification present |
| GA-09 | PASS documental | CRITERIOS/REVISION_DOCUMENTAL y sus referencias; Errors/stops/reruns defined with no behavioral cherry-picking |
| GA-10 | PASS documental | CRITERIOS/REVISION_DOCUMENTAL y sus referencias; Conservative claims and no extra research/S2 requirement |
| GA-11 | PASS documental | CRITERIOS/REVISION_DOCUMENTAL y sus referencias; Versioned payloads ready; previous files intact; manifest/seal verified on canonical persistence |
| GA-12 | PASS documental | CRITERIOS/REVISION_DOCUMENTAL y sus referencias; Phase1 and real authorization separated; stop after documentary close |

No queda una decisión de diseño indispensable pendiente para cerrar Gate A. Las reglas de G están definidas de forma comprobable y no contienen parámetros oráculo o una regla dependiente de si un ataque tuvo éxito. Hay incertidumbres de implementación/proveedor, explícitamente fuera de este cierre documental, que impiden ejecutar o cerrar fase 1 hoy.

## 4. Requisitos exactos de entrada a fase 1

**Para iniciar solo integración offline:** nuevo mandato explícito; referencia a este freeze/manifiesto/acta; copia aislada sin tocar originales; implementación del circuito A/G y validadores/feedback conforme a la especificación; preflight de versiones, S1/pares/fixtures, esquemas y hashes; regresiones de conformidad con red denegada y evidencias persistidas, únicamente cuando se autoricen. Se puede proponer ese mandato, no se ejecuta en esta sesión.

**Antes de cualquier llamada real, además:** autorización específica de sesión/configuración con caps y gasto/créditos aprobados, precio/cota de tokens verificados, identidad/parámetros de proveedor registrados, credenciales del operador sin exposición, privacidad/sink durables y runtime de herramientas exclusivamente simulado. El permiso para un caso mínimo no concede el lote completo de fase 2. Estos permisos y comprobaciones aún faltan y siguen bloqueando llamadas reales.

La fuente de implementación actual R/PREP es referencia, no conformidad automática con esta nueva política: matching exacto histórico no implementa sus validadores, y la traza A exige NOT_APPLICABLE, no un ALLOW inventado. No se afirma compatibilidad completa ni resultado de tests nuevos.

## 5. Estado de fases y parada

| Fase | Estado al cerrar este mandato |
|---|---|
| Selección ADR | CERRADA, sin reabrir |
| 0 / Gate A | CERRADA documentalmente por esta acta |
| 1 / Gate B | BLOQUEADA para cierre funcional; no iniciada por este mandato |
| 2 | BLOQUEADA; 0/78 nuevos resultados MVP |
| 3–6 | PENDIENTES; demo/README/Git siguen como preparación paralela |

**Primera fase abierta ahora: FASE 1.** No se renumera ni se cierra ninguna otra fase. El próximo mandato puede limitarse a integración offline de fase 1 conforme al freeze; aún debe solicitarse/autorizarse por separado. No publicar ni elegir licencia final ni abrir S2.

**Operaciones de este mandato:** documentos/JSON, lectura estática de instrucciones/firmas y verificación de conteos/hash. Código operativo modificado: 0. Tests nuevos de producto: 0. Modelos/episodios: 0. Llamadas Nebius/APIs: 0. Créditos/gasto: 0. S2: sellado. El presupuesto real sigue en cero. No se genera checkpoint experimental ni se reutilizan fixtures como resultados.

El PASS se hace efectivo con la persistencia y verificación del manifiesto/sello canónicos y la continuidad actualizada. **Detenerse al terminar Gate A.**
