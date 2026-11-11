"""Pruebas del Escáner Minero.

    python -m pytest -q
"""

from radar import pauta as P
from radar.buscador import Base
from radar.empresas import clave

B = Base.cargar()


def test_normalizacion_une_variantes_de_nombre():
    assert clave("CIA MINERA PODEROSA S A") == clave("COMPAÑIA MINERA PODEROSA S.A.")
    assert clave("SOUTHERN PERU COPPER CORPORATION SUCURSAL DEL PERU") == clave("SOUTHERN PERU COPPER CORPORATION")


def test_busqueda_por_nombre_y_por_ruc():
    assert B.buscar("bambas")["nombre"].tolist() == ["MINERA LAS BAMBAS S.A."]
    assert len(B.buscar("20538428524")) == 1


def test_perfil_reune_todas_las_fuentes():
    p = B.perfil(B.buscar("bambas")["empresa_id"].iloc[0])
    texto = p.como_texto()
    for etiqueta in ("[F1]", "[F3]", "[F4]", "[F5]", "[F6]"):
        assert etiqueta in texto
    assert len(p.oxi) == 3


def test_ficha_sin_ia_pasa_la_verificacion():
    p = B.perfil(B.buscar("southern")["empresa_id"].iloc[0])
    assert P.verificar(P.generar_sin_ia(p), p) == []


def test_verificador_marca_cifras_inventadas():
    p = B.perfil(B.buscar("southern")["empresa_id"].iloc[0])
    ficha = P.generar_sin_ia(p)
    ficha.datos_clave.append(P.DatoClave(dato="Contaminó 4 321 hectáreas.", fuente="F3"))
    assert P.verificar(ficha, p)


def test_produccion_y_canon_del_anuario():
    p = B.perfil(B.buscar("bambas")["empresa_id"].iloc[0])
    cobre = p.produccion[(p.produccion["metal"] == "cobre") & (p.produccion["anio"] == 2025)]
    assert 0.1 < cobre["participacion"].iloc[0] < 0.2
    assert "APURIMAC" in set(p.transferencias_donde_opera()["departamento"])
