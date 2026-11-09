# Referencia de variables · ENAHO 2024

| Variable | Módulo | Significado |
|---|---|---|
| `conglome`, `vivienda`, `hogar` | todos | Llave del hogar (texto, con ceros iniciales) |
| `codperso` | 02, 05 | Número de la persona dentro del hogar |
| `ubigeo` | 34, 02 | Distrito (6 dígitos). `ubigeo[:2]` = departamento, `ubigeo[:4]` = provincia |
| `estrato` | 34 | 1–5 urbano, 6–8 rural (`urbano = estrato <= 5`) |
| `dominio` | 34 | 8 = Lima Metropolitana |
| `pobreza` | 34 | 1 pobre extremo, 2 pobre no extremo, 3 no pobre (`pobre = pobreza <= 2`) |
| `mieperho`, `factor07` | 34 | Miembros del hogar y factor de expansión del hogar |
| `p204`, `p205`, `p206` | 02 | Residencia habitual: `(p204==1 & p205==2) | (p204==2 & p206==1)` |
| `p207`, `p208a` | 02 | Sexo (1 hombre, 2 mujer) y edad |
| `facpob07` | 02 | Factor de expansión de personas: úsalo para toda tasa de personas |
| `ocu500` | 05 | 1 = ocupado |
| `p506r4` | 05 | Rama de actividad, CIIU rev. 4. Minería: divisiones 05, 07, 08 y clase 0990 |

## Variables construidas por `limpiar.py`

| Variable | Definición |
|---|---|
| `distrito_minero` | El `ubigeo` del hogar tiene al menos una unidad minera metálica (subterránea o superficial) según `datos/unidades_mineras.csv` (MINEM, repositorio del curso, sesión 06) |
| `provincia_minera` | Lo mismo a nivel de provincia (`ubigeo[:4]`) |
| `trabaja_mineria` | Persona ocupada cuya rama CIIU rev. 4 es minería (excluye 06, petróleo y gas) |
| `hogar_minero` | Hogar con al menos un miembro residente que trabaja en minería |

## Advertencias

- La ENAHO **no encuesta viviendas colectivas** (campamentos mineros, cuarteles, hoteles): los trabajadores
  que viven en campamentos solo aparecen si son residentes habituales de un hogar particular.
- No es representativa por distrito ni por provincia: los resultados de `distrito_minero` son de una muestra
  de conglomerados y deben leerse como descriptivos, con su `n_muestra`.
- Lima (15) y Callao (07) son departamentos distintos.
