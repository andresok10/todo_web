import calendar
from decimal import ROUND_HALF_UP, Decimal
from typing import Callable, Protocol, cast

import pendulum
from babel.dates import get_month_names
from flask import Blueprint, jsonify, render_template, request
from flask_wtf import FlaskForm
from wtforms import DecimalField, StringField
from wtforms.validators import InputRequired, NumberRange

app1 = Blueprint("calendario", __name__)


class _FormularioValidable(Protocol):
    validate_on_submit: Callable[[], bool]


class FormEdad(FlaskForm):
    fecha = StringField("Fecha de nacimiento", validators=[InputRequired()])


class FormDescuento(FlaskForm):
    monto = DecimalField("Monto", validators=[InputRequired(), NumberRange(min=0)])
    porc = DecimalField("Porcentaje", validators=[InputRequired(), NumberRange(min=0, max=100)])


@app1.route("/", methods=["GET", "POST"])
@app1.route("/api", methods=["GET", "POST"], endpoint="api")
def calendario_app():
    ahora = pendulum.now("America/Guayaquil")
    hoy = ahora.start_of("day")
    f1, f2 = FormEdad(), FormDescuento()
    nombres = get_month_names("wide", locale="es")
    meses = [{"nombre": nombres[m], "mes_numero": m, "semanas": calendar.Calendar().monthdayscalendar(ahora.year, m)} for m in range(ahora.month, 13)]
    edad_anos = edad_meses = edad_dias = None
    signo = fn = cumple = msg = ""
    mensaje_edad = ""
    dias_hasta_cumple = descuento = None
    api = request.path == "/api"
    if api and request.method == "GET":
        return jsonify(
            anio=ahora.year,
            hoy=ahora.day,
            hoy_mes=ahora.month,
            meses=meses,
        )

    datos_api: dict[str, object] = {}
    if api:
        contenido_json = request.get_json(silent=True)
        if isinstance(contenido_json, dict):
            datos_api = cast(dict[str, object], contenido_json)
    panel = request.form.get("panel", request.args.get("panel", "calculadoras"))
    if panel not in ("calculadoras", "descargas", "calendario"):
        panel = "calculadoras"
    accion_api = datos_api.get("accion")
    accion = accion_api if isinstance(accion_api, str) else None
    if not api:
        accion = request.form.get("accion")
    if (request.method == "POST" or api) and accion == "edad":
        fecha_api = datos_api.get("fecha")
        fecha_recibida = fecha_api if api else f1.fecha.data
        fecha = fecha_recibida if isinstance(fecha_recibida, str) else ""
        fecha_valida = bool(fecha.strip())
        if fecha_valida if api else cast(_FormularioValidable, f1).validate_on_submit():
            try:
                nacimiento = pendulum.from_format(fecha.strip(), "DD/MM/YYYY", tz="America/Guayaquil")
                if nacimiento > hoy:
                    raise ValueError("Fecha futura")
                periodo = nacimiento.diff(hoy)
                edad_anos, edad_meses, edad_dias = periodo.years, periodo.months, periodo.remaining_days
                # El 29 de febrero se celebra el 28 en los años no bisiestos.
                cumple_d = nacimiento.set(year=hoy.year, day=min(nacimiento.day, calendar.monthrange(hoy.year, nacimiento.month)[1]))
                if cumple_d < hoy:
                    year = hoy.year + 1
                    cumple_d = nacimiento.set(year=year, day=min(nacimiento.day, calendar.monthrange(year, nacimiento.month)[1]))
                dias_hasta_cumple = max(0, cumple_d.start_of("day").diff(hoy).in_days())
                limites = [
                    (120, "Capricornio"),
                    (219, "Acuario"),
                    (321, "Piscis"),
                    (420, "Aries"),
                    (521, "Tauro"),
                    (621, "Géminis"),
                    (723, "Cáncer"),
                    (823, "Leo"),
                    (923, "Virgo"),
                    (1023, "Libra"),
                    (1122, "Escorpio"),
                    (1222, "Sagitario"),
                    (1232, "Capricornio"),
                ]
                signo = next(nombre for limite, nombre in limites if nacimiento.month * 100 + nacimiento.day < limite)
                fn, cumple = nacimiento.format("DD/MM/YYYY"), cumple_d.format("DD/MM/YYYY")
                mensaje_cumple = "¡Feliz cumpleaños!" if dias_hasta_cumple == 0 else f"Faltan {dias_hasta_cumple} días para tu cumpleaños."
                mensaje_edad = (
                    f"Edad: {edad_anos} años, {edad_meses} meses, {edad_dias} días\n"
                    f"Signo: {signo}\nNacimiento: {fn}\nPróximo cumpleaños: {cumple}\n"
                    f"{mensaje_cumple}"
                )
            except ValueError:
                msg = "Ingresa una fecha válida, no futura, con formato DD/MM/AAAA."
        else:
            msg = "Ingresa tu fecha de nacimiento."
    elif (request.method == "POST" or api) and accion == "descuento":
        if api:
            try:
                monto = Decimal(str(datos_api.get("monto", "")))
                porcentaje = Decimal(str(datos_api.get("porcentaje", "")))
            except Exception:
                monto = porcentaje = None
            datos_descuento_validos = (
                monto is not None and porcentaje is not None
                and monto.is_finite() and porcentaje.is_finite()
                and monto >= 0 and Decimal(0) <= porcentaje <= Decimal(100)
            )
        else:
            monto, porcentaje = f2.monto.data, f2.porc.data
            datos_descuento_validos = (
                cast(_FormularioValidable, f2).validate_on_submit()
                and monto is not None and porcentaje is not None
            )
        if datos_descuento_validos and monto is not None and porcentaje is not None:
            try:
                descuento = (monto * (1 - porcentaje / Decimal(100))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            except Exception:
                msg = "No se pudo calcular el descuento con esos valores."
        else:
            msg = "Ingresa un monto mayor o igual a cero y un porcentaje entre 0 y 100."
    elif (request.method == "POST" or api):
        msg = "Selecciona una operación válida."

    if api:
        if msg:
            return jsonify(status="error", msg=msg), 400
        if accion == "edad":
            return jsonify(status="success", msg=mensaje_edad)
        return jsonify(status="success", msg=f"Total: ${descuento:.2f}")
    return render_template(
        "app.html",
        ahora=ahora,
        meses=meses,
        f1=f1,
        f2=f2,
        edad_anos=edad_anos,
        edad_meses=edad_meses,
        edad_dias=edad_dias,
        signo=signo,
        fn=fn,
        cumple=cumple,
        dias_hasta_cumple=dias_hasta_cumple,
        panel=panel,
        descuento=descuento,
        msg=msg,
    )
