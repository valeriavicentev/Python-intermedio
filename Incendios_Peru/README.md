# Incendios en el Perú · ¿Cuánto se quemó y qué se quemó?

> Borrador. Se completa con los resultados al final del ejercicio (Sesión 14).

## Cómo correrlo

```bash
pip install -r requirements.txt
python 01_focos.py                    # focos VIIRS 7 días y ranking de incendios
python 02_dnbr.py --id N --solo-listar  # fechas y % de nubes de Sentinel-2 en la zona
python 02_dnbr.py --id N              # dNBR, hectáreas por severidad y distrito, mapa
python 03_cobertura.py                # cruce con ESA WorldCover
```
